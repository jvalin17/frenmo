import logging
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import login_required
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.currency import CURRENCY_SYMBOLS
from app.services.direct import find_or_create_direct_group, is_direct, pair_group_is_settled
from app.services.friendship import (
    accept_friend_request,
    get_friend_list,
    get_pair_simplify,
    get_pending_requests,
    is_friend,
    reject_friend_request,
    remove_friend,
    search_users_by_email,
    send_friend_request,
    set_pair_simplify,
)
from app.services.settlement import net_for, settle_all, settle_all_plan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/friends", tags=["friends"])
templates = Jinja2Templates(directory="app/templates")


def mask_email(email: str) -> str:
    """Mask email for privacy: j***n@gmail.com"""
    local, domain = email.split("@")
    masked_local = local[0] + "***" if len(local) <= 2 else local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"


@router.get("/", response_class=HTMLResponse)
@login_required
async def friends_page(request: Request, q: str = "", db: AsyncSession = Depends(get_db)):
    user = await db.get(User, request.state.user_id)
    from app.services.balance import get_friend_balance_detail

    friends = await get_friend_list(db, request.state.user_id)
    pending = await get_pending_requests(db, request.state.user_id)

    # Load balance details for each friend
    friend_balances = {}
    for friend in friends:
        friend_balances[friend.id] = await get_friend_balance_detail(
            db, request.state.user_id, friend.id
        )

    # Resolve sender names for pending requests
    pending_with_names = []
    for friendship in pending:
        sender = await db.get(User, friendship.user_id)
        if sender:
            pending_with_names.append({
                "id": friendship.id,
                "sender_name": sender.name,
                "sender_email": mask_email(sender.email),
            })

    search_results = []
    if q:
        found_users = await search_users_by_email(db, q, exclude_user_id=request.state.user_id)
        # Check existing friendship status for each result
        friend_ids = {f.id for f in friends}
        for found_user in found_users:
            search_results.append({
                "id": found_user.id,
                "name": found_user.name,
                "email": mask_email(found_user.email),
                "is_friend": found_user.id in friend_ids,
            })

    return templates.TemplateResponse(
        request,
        "friends/index.html",
        {
            "user": user,
            "friends": friends,
            "friend_balances": friend_balances,
            "pending": pending_with_names,
            "search_results": search_results,
            "query": q,
            "mask_email": mask_email,
            "sym": CURRENCY_SYMBOLS,
        },
    )


@router.post("/request/{target_user_id}")
@login_required
async def send_request(request: Request, target_user_id: int, db: AsyncSession = Depends(get_db)):
    await send_friend_request(db, from_user_id=request.state.user_id, to_user_id=target_user_id)
    logger.info("Friend request sent: from=%d to=%d", request.state.user_id, target_user_id)
    return RedirectResponse(url="/friends", status_code=303)


@router.post("/accept/{friendship_id}")
@login_required
async def accept_request(request: Request, friendship_id: int, db: AsyncSession = Depends(get_db)):
    await accept_friend_request(db, friendship_id=friendship_id, user_id=request.state.user_id)
    logger.info(
        "Friend request accepted: friendship=%d by user=%d", friendship_id, request.state.user_id
    )
    return RedirectResponse(url="/friends", status_code=303)


@router.post("/reject/{friendship_id}")
@login_required
async def reject_request(request: Request, friendship_id: int, db: AsyncSession = Depends(get_db)):
    await reject_friend_request(db, friendship_id=friendship_id, user_id=request.state.user_id)
    logger.info(
        "Friend request rejected: friendship=%d by user=%d", friendship_id, request.state.user_id
    )
    return RedirectResponse(url="/friends", status_code=303)


@router.post("/remove/{friend_id}")
@login_required
async def remove(request: Request, friend_id: int, db: AsyncSession = Depends(get_db)):
    # Like leaving a group: only at zero balance in the pair group (requirements F5)
    if not await pair_group_is_settled(db, request.state.user_id, friend_id):
        return RedirectResponse(
            url=f"/friends?error=settle_first&friend={friend_id}", status_code=303
        )
    await remove_friend(db, user_id=request.state.user_id, friend_id=friend_id)
    logger.info("Friend removed: user=%d friend=%d", request.state.user_id, friend_id)
    return RedirectResponse(url="/friends", status_code=303)


@router.post("/add-to-group/{group_id}/{friend_id}")
@login_required
async def add_friend_to_group(
    request: Request, group_id: int, friend_id: int, db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select

    # Verify current user is a member of the group
    membership = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == request.state.user_id,
        )
    )
    if membership.scalar_one_or_none() is None:
        return RedirectResponse(url="/", status_code=303)

    # A pair group never gains members (AD-6)
    if is_direct(await db.get(Group, group_id)):
        return RedirectResponse(url=f"/groups/{group_id}", status_code=303)

    # Verify the target is actually an accepted friend
    if not await is_friend(db, request.state.user_id, friend_id):
        return RedirectResponse(url=f"/groups/{group_id}", status_code=303)

    # Check friend is not already a member
    existing = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == friend_id,
        )
    )
    if existing.scalar_one_or_none() is None:
        new_member = GroupMember(group_id=group_id, user_id=friend_id)
        db.add(new_member)
        await db.flush()

        # Auto-friendship with all existing members
        from app.services.friendship import ensure_friendship

        existing_members = await db.execute(
            select(GroupMember.user_id).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id != friend_id,
            )
        )
        for row in existing_members.all():
            await ensure_friendship(db, friend_id, row[0])

        # Recalculate existing equal-split expenses to include new member
        from app.services.expense import recalculate_splits_for_new_member

        await recalculate_splits_for_new_member(db, group_id, friend_id)
        await db.commit()
        logger.info(
            "Friend %d added to group %d by user %d",
            friend_id, group_id, request.state.user_id,
        )

    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)


# ---------------------------------------------------------------------------
# Direct (one-to-one) expenses: requirements/direct-expenses.md F2, AD-6
# ---------------------------------------------------------------------------


@router.post("/{friend_id}/direct")
@login_required
async def direct_expense(request: Request, friend_id: int, db: AsyncSession = Depends(get_db)):
    """Open the normal expense form inside the hidden pair group, creating it on first use."""
    group = await find_or_create_direct_group(db, request.state.user_id, friend_id)
    if group is None:
        return RedirectResponse(url="/friends", status_code=303)
    await db.commit()
    return RedirectResponse(url=f"/expenses/new/{group.id}", status_code=303)


@router.get("/{friend_id}/settle-all", response_class=HTMLResponse)
@login_required
async def settle_all_confirm(
    request: Request, friend_id: int, currency: str = "", db: AsyncSession = Depends(get_db)
):
    """Show exactly which per-group settlements 'Settle all' would record."""
    user_id = request.state.user_id
    user = await db.get(User, user_id)
    friend = await db.get(User, friend_id)
    if friend is None or not await is_friend(db, user_id, friend_id):
        return RedirectResponse(url="/friends", status_code=303)

    currency = currency.strip().upper()[:3]
    entries = await settle_all_plan(db, user_id, friend_id, currency) if currency else []
    names = {user_id: "You", friend_id: friend.name}
    return templates.TemplateResponse(
        request,
        "friends/settle_all.html",
        {
            "user": user,
            "friend": friend,
            "currency": currency,
            "entries": [
                {
                    "group_name": e.group_name,
                    "debtor": names[e.debtor_id],
                    "creditor": names[e.creditor_id],
                    "amount": e.amount,
                }
                for e in entries
            ],
            "net": net_for(entries, user_id),
            "batch_id": uuid.uuid4().hex,
            "sym": CURRENCY_SYMBOLS,
        },
    )


@router.post("/{friend_id}/settle-all")
@login_required
async def settle_all_submit(
    request: Request,
    friend_id: int,
    currency: str = Form(""),
    batch_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Record one settlement per group, all in one transaction."""
    currency = currency.strip().upper()[:3]
    batch_id = batch_id.strip()[:64]
    if not currency or not batch_id:
        return RedirectResponse(url="/friends", status_code=303)
    written = await settle_all(db, request.state.user_id, friend_id, currency, batch_id=batch_id)
    if written is None:
        return RedirectResponse(url="/friends", status_code=303)
    await db.commit()
    logger.info(
        "Settle all: user=%d friend=%d currency=%s settlements=%d batch=%s",
        request.state.user_id, friend_id, currency, len(written), batch_id,
    )
    return RedirectResponse(url="/friends", status_code=303)


@router.post("/{friend_id}/simplify")
@login_required
async def toggle_simplify(request: Request, friend_id: int, db: AsyncSession = Depends(get_db)):
    """Flip the pair's simplify flag; both users see the same mode."""
    current = await get_pair_simplify(db, request.state.user_id, friend_id)
    if await set_pair_simplify(db, request.state.user_id, friend_id, not current):
        await db.commit()
    return RedirectResponse(url="/friends", status_code=303)

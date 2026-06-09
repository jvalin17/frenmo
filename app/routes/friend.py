import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import login_required
from app.models.group import GroupMember
from app.models.user import User
from app.services.friendship import (
    accept_friend_request,
    get_friend_list,
    get_pending_requests,
    reject_friend_request,
    remove_friend,
    search_users_by_email,
    send_friend_request,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/friends", tags=["friends"])
templates = Jinja2Templates(directory="app/templates")


def mask_email(email: str) -> str:
    """Mask email for privacy: j***n@gmail.com"""
    local, domain = email.split("@")
    if len(local) <= 2:
        masked_local = local[0] + "***"
    else:
        masked_local = local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"


@router.get("/", response_class=HTMLResponse)
@login_required
async def friends_page(request: Request, q: str = "", db: AsyncSession = Depends(get_db)):
    user = await db.get(User, request.state.user_id)
    friends = await get_friend_list(db, request.state.user_id)
    pending = await get_pending_requests(db, request.state.user_id)

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
            "pending": pending_with_names,
            "search_results": search_results,
            "query": q,
            "mask_email": mask_email,
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
    logger.info("Friend request accepted: friendship=%d by user=%d", friendship_id, request.state.user_id)
    return RedirectResponse(url="/friends", status_code=303)


@router.post("/reject/{friendship_id}")
@login_required
async def reject_request(request: Request, friendship_id: int, db: AsyncSession = Depends(get_db)):
    await reject_friend_request(db, friendship_id=friendship_id, user_id=request.state.user_id)
    logger.info("Friend request rejected: friendship=%d by user=%d", friendship_id, request.state.user_id)
    return RedirectResponse(url="/friends", status_code=303)


@router.post("/remove/{friend_id}")
@login_required
async def remove(request: Request, friend_id: int, db: AsyncSession = Depends(get_db)):
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
        await db.commit()
        logger.info("Friend %d added to group %d by user %d", friend_id, group_id, request.state.user_id)

    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)

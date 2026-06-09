import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import login_required
from app.models.group import Group, GroupMember
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/groups", tags=["groups"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/new", response_class=HTMLResponse)
@login_required
async def new_group_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, request.state.user_id)
    return templates.TemplateResponse(request, "group/new.html", {"user": user})


@router.post("/new")
@login_required
async def create_group(
    request: Request,
    name: str = Form(...),
    group_type: str = Form("other"),
    group_currency: str = Form("USD"),
    db: AsyncSession = Depends(get_db),
):
    group = Group(name=name.strip(), type=group_type, currency=group_currency, created_by=request.state.user_id)
    db.add(group)
    await db.flush()

    member = GroupMember(group_id=group.id, user_id=request.state.user_id)
    db.add(member)
    await db.commit()

    logger.info("Group created: group_id=%d by user_id=%d", group.id, request.state.user_id)
    return RedirectResponse(url=f"/groups/{group.id}", status_code=303)


@router.get("/{group_id}", response_class=HTMLResponse)
@login_required
async def group_detail(request: Request, group_id: int, db: AsyncSession = Depends(get_db)):
    user_id = request.state.user_id
    user = await db.get(User, user_id)

    # Verify membership
    membership = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id, GroupMember.user_id == user_id
        )
    )
    if membership.scalar_one_or_none() is None:
        return RedirectResponse(url="/", status_code=303)

    group = await db.get(Group, group_id)
    if group is None:
        return RedirectResponse(url="/", status_code=303)

    # Get members
    members_result = await db.execute(
        select(User)
        .join(GroupMember, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group_id)
    )
    members = members_result.scalars().all()

    # Get expenses (non-deleted)
    from app.models.expense import Expense

    expenses_result = await db.execute(
        select(Expense)
        .where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
        .order_by(Expense.created_at.desc())
    )
    expenses = expenses_result.scalars().all()

    # Get balances
    from app.services.balance import get_group_balances, simplify_debts

    balances = await get_group_balances(db, group_id)
    simplified = simplify_debts(balances)

    # Map user IDs to names
    member_names = {m.id: m.name for m in members}

    # Get friends not already in this group (for "add from friends")
    from app.services.friendship import get_friend_list

    all_friends = await get_friend_list(db, user_id)
    member_ids = {m.id for m in members}
    available_friends = [f for f in all_friends if f.id not in member_ids]

    # Get comments for all expenses
    from app.services.comments import get_comments

    expense_comments = {}
    for expense in expenses:
        expense_comments[expense.id] = await get_comments(db, expense.id)

    # Get exchange rates for converter widget
    from app.services.currency import get_exchange_rates

    rates = await get_exchange_rates()

    return templates.TemplateResponse(
        request,
        "group/detail.html",
        {
            "user": user,
            "group": group,
            "members": members,
            "expenses": expenses,
            "balances": balances,
            "simplified": simplified,
            "member_names": member_names,
            "available_friends": available_friends,
            "expense_comments": expense_comments,
            "rates": rates,
        },
    )


@router.post("/{group_id}/settings")
@login_required
async def update_group_settings(request: Request, group_id: int, db: AsyncSession = Depends(get_db)):
    user_id = request.state.user_id
    # Verify membership
    membership = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id, GroupMember.user_id == user_id
        )
    )
    if membership.scalar_one_or_none() is None:
        return RedirectResponse(url="/", status_code=303)

    group = await db.get(Group, group_id)
    if group is None:
        return RedirectResponse(url="/", status_code=303)

    form_data = await request.form()
    new_name = form_data.get("name", "").strip()
    new_currency = form_data.get("currency", group.currency)

    if new_name:
        group.name = new_name
    group.currency = new_currency
    await db.commit()
    logger.info("Group settings updated: group=%d by user=%d", group_id, user_id)
    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)


@router.get("/{group_id}/charts", response_class=HTMLResponse)
@login_required
async def group_charts(request: Request, group_id: int, db: AsyncSession = Depends(get_db)):
    user_id = request.state.user_id
    user = await db.get(User, user_id)

    # Verify membership
    membership = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id, GroupMember.user_id == user_id
        )
    )
    if membership.scalar_one_or_none() is None:
        return RedirectResponse(url="/", status_code=303)

    group = await db.get(Group, group_id)
    if group is None:
        return RedirectResponse(url="/", status_code=303)

    from app.services.charts import get_category_breakdown, get_member_spending, get_monthly_spending

    category_data = await get_category_breakdown(db, group_id)
    monthly_data = await get_monthly_spending(db, group_id)
    member_data = await get_member_spending(db, group_id)

    # Resolve member names
    members_result = await db.execute(
        select(User)
        .join(GroupMember, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group_id)
    )
    members = members_result.scalars().all()
    member_names = {m.id: m.name for m in members}

    return templates.TemplateResponse(
        request,
        "group/charts.html",
        {
            "user": user,
            "group": group,
            "category_data": category_data,
            "monthly_data": monthly_data,
            "member_data": member_data,
            "member_names": member_names,
        },
    )


@router.get("/{group_id}/invite", response_class=HTMLResponse)
@login_required
async def invite_page(request: Request, group_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, request.state.user_id)
    group = await db.get(Group, group_id)
    if group is None:
        return RedirectResponse(url="/", status_code=303)

    invite_url = f"{request.base_url}groups/join/{group.invite_token}"
    return templates.TemplateResponse(
        request, "group/invite.html", {"user": user, "group": group, "invite_url": invite_url}
    )


@router.get("/join/{token}")
@login_required
async def join_group(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Group).where(Group.invite_token == token))
    group = result.scalar_one_or_none()
    if group is None:
        return RedirectResponse(url="/", status_code=303)

    # Check if already a member
    existing = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group.id, GroupMember.user_id == request.state.user_id
        )
    )
    if existing.scalar_one_or_none() is None:
        member = GroupMember(group_id=group.id, user_id=request.state.user_id)
        db.add(member)
        await db.commit()
        logger.info(
            "User %d joined group %d via invite", request.state.user_id, group.id
        )

    return RedirectResponse(url=f"/groups/{group.id}", status_code=303)

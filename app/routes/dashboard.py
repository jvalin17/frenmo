from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import login_required
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.balance import get_group_balances, get_overall_balances

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
@login_required
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = request.state.user_id
    user = await db.get(User, user_id)

    result = await db.execute(
        select(Group)
        .join(GroupMember, Group.id == GroupMember.group_id)
        .where(GroupMember.user_id == user_id)
        .order_by(Group.created_at.desc())
    )
    groups = result.scalars().all()

    # Overall balances across all groups
    overall = await get_overall_balances(db, user_id)

    # Resolve user names for balances
    balance_names = {}
    for other_id in overall:
        other_user = await db.get(User, other_id)
        if other_user:
            balance_names[other_id] = other_user.name

    # Per-group balances for current user
    group_balances = {}
    for group in groups:
        balances = await get_group_balances(db, group.id)
        user_net = balances.get(user_id, 0)
        group_balances[group.id] = user_net

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "groups": groups,
            "overall_balances": overall,
            "balance_names": balance_names,
            "group_balances": group_balances,
        },
    )

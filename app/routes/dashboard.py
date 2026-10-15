from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import login_required
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.balance import (
    get_user_balances,
    hero_state,
    order_people,
    summarize_by_currency,
)
from app.services.currency import CURRENCY_SYMBOLS
from app.services.direct import is_direct
from app.services.friendship import get_friend_list

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
    all_groups = result.scalars().all()
    # Pair groups count in every balance but never appear in a group list
    groups = [g for g in all_groups if not is_direct(g)]

    # People balances (per currency) and the user's net in each group, one pass per group
    overall, group_balances = await get_user_balances(db, user_id, all_groups)
    hero_totals = summarize_by_currency(overall)
    hero_status = hero_state(hero_totals)

    balance_names = {}
    for other_id in overall:
        other_user = await db.get(User, other_id)
        if other_user:
            balance_names[other_id] = other_user.name

    # Balances queue: one card per person, people you owe first (requirements F4)
    queue = []
    for other_id in order_people(overall, balance_names):
        lines = sorted(overall[other_id].items())
        owed = [(currency, -net) for currency, net in lines if net < 0]
        queue.append({
            "id": other_id,
            "name": balance_names.get(other_id, "?"),
            "lines": lines,
            "pay": owed[0] if owed else None,  # (currency, amount) of the first debt you owe
        })
    friends = await get_friend_list(db, user_id)
    settled_count = sum(1 for f in friends if f.id not in overall)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "groups": groups,
            "overall_balances": overall,
            "hero_totals": hero_totals,
            "hero_state": hero_status,
            "sym": CURRENCY_SYMBOLS,
            "balance_names": balance_names,
            "group_balances": group_balances,
            "queue": queue,
            "settled_count": settled_count,
        },
    )

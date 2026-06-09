import logging
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import login_required
from app.models.expense import Expense
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.expense import create_expense_with_splits, soft_delete_expense

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/expenses", tags=["expenses"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/new/{group_id}", response_class=HTMLResponse)
@login_required
async def new_expense_page(request: Request, group_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, request.state.user_id)
    group = await db.get(Group, group_id)

    members_result = await db.execute(
        select(User)
        .join(GroupMember, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == group_id)
    )
    members = members_result.scalars().all()

    return templates.TemplateResponse(
        request,
        "expense/new.html",
        {"user": user, "group": group, "members": members},
    )


@router.post("/new/{group_id}")
@login_required
async def create_expense(
    request: Request,
    group_id: int,
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    description = form_data.get("description", "").strip()
    amount_str = form_data.get("amount", "0")
    split_type = form_data.get("split_type", "equal")
    paid_by = int(form_data.get("paid_by", request.state.user_id))
    category = form_data.get("category", "")
    currency = form_data.get("currency", "INR")

    # Convert amount to smallest unit (cents/paise) — input is in main unit
    try:
        amount_float = float(amount_str)
        amount_paise = round(amount_float * 100)
    except ValueError:
        return RedirectResponse(url=f"/groups/{group_id}", status_code=303)

    if amount_paise <= 0 or not description:
        return RedirectResponse(url=f"/groups/{group_id}", status_code=303)

    # Get selected members
    selected_member_ids = [int(v) for k, v in form_data.multi_items() if k == "split_with"]
    if not selected_member_ids:
        # Default: split with all group members
        members_result = await db.execute(
            select(GroupMember.user_id).where(GroupMember.group_id == group_id)
        )
        selected_member_ids = [row[0] for row in members_result.all()]

    # Parse per-member values based on split type
    member_values = {}
    if split_type in ("exact", "percent"):
        for member_id in selected_member_ids:
            val = form_data.get(f"amount_{member_id}", "0")
            try:
                member_values[member_id] = float(val)
            except ValueError:
                member_values[member_id] = 0
    elif split_type == "shares":
        for member_id in selected_member_ids:
            val = form_data.get(f"shares_{member_id}", "1")
            try:
                member_values[member_id] = float(val)
            except ValueError:
                member_values[member_id] = 1
    elif split_type == "full":
        full_owes = int(form_data.get("full_owes", paid_by))
        # Get all group members for full split
        members_result = await db.execute(
            select(GroupMember.user_id).where(GroupMember.group_id == group_id)
        )
        selected_member_ids = [row[0] for row in members_result.all()]

    idempotency_key = str(uuid.uuid4())

    # For full split, pass owes_user_id via member_values
    if split_type == "full":
        member_values = {"full_owes": full_owes}

    await create_expense_with_splits(
        db=db,
        group_id=group_id,
        description=description,
        amount_paise=amount_paise,
        currency=currency,
        split_type=split_type,
        paid_by=paid_by,
        created_by=request.state.user_id,
        member_ids=selected_member_ids,
        member_values=member_values,
        category=category or None,
        idempotency_key=idempotency_key,
    )

    logger.info("Expense created: group=%d amount=%d", group_id, amount_paise)
    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)


@router.get("/{expense_id}/edit", response_class=HTMLResponse)
@login_required
async def edit_expense_page(request: Request, expense_id: int, db: AsyncSession = Depends(get_db)):
    expense = await db.get(Expense, expense_id)
    if expense is None or expense.created_by != request.state.user_id or expense.deleted_at is not None:
        return RedirectResponse(url="/", status_code=303)

    user = await db.get(User, request.state.user_id)
    group = await db.get(Group, expense.group_id)
    members_result = await db.execute(
        select(User)
        .join(GroupMember, User.id == GroupMember.user_id)
        .where(GroupMember.group_id == expense.group_id)
    )
    members = members_result.scalars().all()

    return templates.TemplateResponse(
        request,
        "expense/edit.html",
        {"user": user, "group": group, "expense": expense, "members": members},
    )


@router.post("/{expense_id}/edit")
@login_required
async def edit_expense(request: Request, expense_id: int, db: AsyncSession = Depends(get_db)):
    from app.services.expense import update_expense

    form_data = await request.form()
    description = form_data.get("description", "").strip()
    amount_str = form_data.get("amount", "0")
    split_type = form_data.get("split_type", "equal")
    paid_by = int(form_data.get("paid_by", request.state.user_id))
    category = form_data.get("category", "")
    currency = form_data.get("currency", "USD")

    try:
        amount_paise = round(float(amount_str) * 100)
    except ValueError:
        return RedirectResponse(url=f"/expenses/{expense_id}/edit", status_code=303)

    if amount_paise <= 0 or not description:
        return RedirectResponse(url=f"/expenses/{expense_id}/edit", status_code=303)

    selected_member_ids = [int(v) for k, v in form_data.multi_items() if k == "split_with"]
    member_values = {}
    if split_type in ("exact", "percent"):
        for member_id in selected_member_ids:
            val = form_data.get(f"amount_{member_id}", "0")
            try:
                member_values[member_id] = float(val)
            except ValueError:
                member_values[member_id] = 0

    expense = await update_expense(
        db=db,
        expense_id=expense_id,
        user_id=request.state.user_id,
        description=description,
        amount_paise=amount_paise,
        currency=currency,
        split_type=split_type,
        paid_by=paid_by,
        category=category or None,
        member_ids=selected_member_ids or None,
        member_values=member_values or None,
    )

    if expense is None:
        return RedirectResponse(url="/", status_code=303)

    logger.info("Expense edited: expense_id=%d by user=%d", expense_id, request.state.user_id)
    return RedirectResponse(url=f"/groups/{expense.group_id}", status_code=303)


@router.post("/{expense_id}/delete")
@login_required
async def delete_expense(request: Request, expense_id: int, db: AsyncSession = Depends(get_db)):
    from datetime import datetime

    expense = await db.get(Expense, expense_id)
    if expense is None or expense.created_by != request.state.user_id:
        return RedirectResponse(url="/", status_code=303)

    group_id = expense.group_id
    if expense.deleted_at is None:
        expense.deleted_at = datetime.utcnow()
        await db.commit()
    logger.info("Expense soft-deleted: expense_id=%d by user=%d", expense_id, request.state.user_id)
    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)

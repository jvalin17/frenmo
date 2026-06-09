import logging

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import login_required
from app.models.group import Group, GroupMember
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/statement", tags=["statement"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/{group_id}", response_class=HTMLResponse)
@login_required
async def statement_page(request: Request, group_id: int, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    user = await db.get(User, request.state.user_id)
    group = await db.get(Group, group_id)

    # Verify membership
    membership = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id, GroupMember.user_id == request.state.user_id
        )
    )
    if membership.scalar_one_or_none() is None or group is None:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request,
        "statement/upload.html",
        {"user": user, "group": group, "transactions": None, "bank": None, "error": None},
    )


@router.post("/{group_id}/parse", response_class=HTMLResponse)
@login_required
async def parse_statement(
    request: Request,
    group_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    user = await db.get(User, request.state.user_id)
    group = await db.get(Group, group_id)

    membership = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id, GroupMember.user_id == request.state.user_id
        )
    )
    if membership.scalar_one_or_none() is None or group is None:
        return RedirectResponse(url="/", status_code=303)

    # Read file bytes, then immediately discard
    file_bytes = await file.read()
    await file.close()

    # Parse dates from form
    form_data = await request.form()
    date_from = form_data.get("date_from", "").strip() or None
    date_to = form_data.get("date_to", "").strip() or None

    # Process statement
    from app.services.statement.extractor import process_statement

    result = process_statement(file_bytes, date_from=date_from, date_to=date_to)

    # Wipe file bytes from memory
    del file_bytes

    return templates.TemplateResponse(
        request,
        "statement/upload.html",
        {
            "user": user,
            "group": group,
            "transactions": result["transactions"],
            "bank": result["bank"],
            "error": result["error"],
        },
    )


@router.post("/{group_id}/import")
@login_required
async def import_expenses(request: Request, group_id: int, db: AsyncSession = Depends(get_db)):
    import uuid
    from sqlalchemy import select

    from app.models.group import GroupMember
    from app.services.expense import create_expense_with_splits

    membership = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id, GroupMember.user_id == request.state.user_id
        )
    )
    if membership.scalar_one_or_none() is None:
        return RedirectResponse(url="/", status_code=303)

    group = await db.get(Group, group_id)
    form_data = await request.form()

    # Get all member IDs for equal split
    members_result = await db.execute(
        select(GroupMember.user_id).where(GroupMember.group_id == group_id)
    )
    member_ids = [row[0] for row in members_result.all()]

    # Import selected transactions
    imported_count = 0
    for key, value in form_data.multi_items():
        if key.startswith("tx_") and value == "on":
            index = key.replace("tx_", "")
            description = form_data.get(f"desc_{index}", "").strip()
            amount_str = form_data.get(f"amount_{index}", "0")

            try:
                amount_cents = int(amount_str)
            except ValueError:
                continue

            if amount_cents <= 0 or not description:
                continue

            await create_expense_with_splits(
                db=db,
                group_id=group_id,
                description=description,
                amount_paise=amount_cents,
                currency=group.currency,
                split_type="equal",
                paid_by=request.state.user_id,
                created_by=request.state.user_id,
                member_ids=member_ids,
                idempotency_key=str(uuid.uuid4()),
            )
            imported_count += 1

    logger.info("Imported %d expenses from statement to group %d", imported_count, group_id)
    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)

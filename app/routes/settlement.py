import logging
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import login_required
from app.services.expense import create_expense_with_splits

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settlements", tags=["settlements"])


@router.post("/new/{group_id}")
@login_required
async def record_settlement(
    request: Request,
    group_id: int,
    from_user: int = Form(...),
    to_user: int = Form(...),
    amount: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        amount_paise = round(float(amount) * 100)
    except ValueError:
        return RedirectResponse(url=f"/groups/{group_id}", status_code=303)

    if amount_paise <= 0 or from_user == to_user:
        return RedirectResponse(url=f"/groups/{group_id}", status_code=303)

    # Settlement: from_user paid to_user. Recorded as an expense where
    # from_user paid and to_user owes the full amount.
    await create_expense_with_splits(
        db=db,
        group_id=group_id,
        description="Settlement",
        amount_paise=amount_paise,
        split_type="exact",
        paid_by=from_user,
        created_by=request.state.user_id,
        member_ids=[to_user],
        member_values={to_user: amount_paise / 100},
        expense_type="settlement",
        idempotency_key=str(uuid.uuid4()),
    )

    logger.info(
        "Settlement recorded: group=%d from=%d to=%d amount=%d",
        group_id, from_user, to_user, amount_paise,
    )
    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)

from collections import OrderedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense, ExpenseSplit


async def get_category_breakdown(db: AsyncSession, group_id: int) -> dict[str, int]:
    """Total spending by category for a group. Returns {category: amount_paise}."""
    result = await db.execute(
        select(
            func.coalesce(Expense.category, "other").label("cat"),
            func.sum(Expense.amount).label("total"),
        )
        .where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
        .group_by("cat")
        .order_by(func.sum(Expense.amount).desc())
    )
    return {row.cat: row.total for row in result.all()}


async def get_monthly_spending(db: AsyncSession, group_id: int) -> dict[str, int]:
    """Total spending by month for a group. Returns {"YYYY-MM": amount_paise}."""
    result = await db.execute(
        select(Expense.created_at, Expense.amount)
        .where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
        .order_by(Expense.created_at)
    )
    monthly: dict[str, int] = {}
    for row in result.all():
        month_key = row.created_at.strftime("%Y-%m")
        monthly[month_key] = monthly.get(month_key, 0) + row.amount
    return OrderedDict(sorted(monthly.items()))


async def get_member_spending(db: AsyncSession, group_id: int) -> dict[int, int]:
    """Total amount paid by each member. Returns {user_id: total_paid_paise}."""
    result = await db.execute(
        select(
            Expense.paid_by,
            func.sum(Expense.amount).label("total"),
        )
        .where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
        .group_by(Expense.paid_by)
    )
    return {row.paid_by: row.total for row in result.all()}

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense, ExpenseSplit


def compute_equal_splits(amount_paise: int, member_ids: list[int]) -> dict[int, int]:
    """Split amount equally. Distribute remainder paise to first N members."""
    count = len(member_ids)
    if count == 0:
        return {}
    base = amount_paise // count
    remainder = amount_paise % count

    splits = {}
    for index, member_id in enumerate(member_ids):
        splits[member_id] = base + (1 if index < remainder else 0)
    return splits


def compute_exact_splits(amount_paise: int, member_values: dict[int, float]) -> dict[int, int]:
    """Exact split — values are in rupees, convert to paise. Must sum to total."""
    splits = {}
    total = 0
    for member_id, value in member_values.items():
        paise = round(value * 100)
        splits[member_id] = paise
        total += paise

    # Adjust rounding error on last member
    if total != amount_paise and splits:
        last_id = list(splits.keys())[-1]
        splits[last_id] += amount_paise - total

    return splits


def compute_percent_splits(amount_paise: int, member_values: dict[int, float]) -> dict[int, int]:
    """Percentage split — values are percentages. Must sum to 100."""
    splits = {}
    total = 0
    for member_id, percent in member_values.items():
        paise = round(amount_paise * percent / 100)
        splits[member_id] = paise
        total += paise

    # Adjust rounding error on last member
    if total != amount_paise and splits:
        last_id = list(splits.keys())[-1]
        splits[last_id] += amount_paise - total

    return splits


async def create_expense_with_splits(
    db: AsyncSession,
    group_id: int,
    description: str,
    amount_paise: int,
    split_type: str,
    paid_by: int,
    created_by: int,
    member_ids: list[int],
    member_values: dict[int, float] | None = None,
    category: str | None = None,
    idempotency_key: str | None = None,
    expense_type: str = "expense",
    currency: str = "INR",
) -> Expense:
    """Create expense + splits atomically."""
    # Check idempotency
    if idempotency_key:
        existing = await db.execute(
            select(Expense).where(Expense.idempotency_key == idempotency_key)
        )
        found = existing.scalar_one_or_none()
        if found:
            return found

    # Compute splits
    if split_type == "equal":
        owed_splits = compute_equal_splits(amount_paise, member_ids)
    elif split_type == "exact" and member_values:
        owed_splits = compute_exact_splits(amount_paise, member_values)
    elif split_type == "percent" and member_values:
        owed_splits = compute_percent_splits(amount_paise, member_values)
    else:
        owed_splits = compute_equal_splits(amount_paise, member_ids)

    # Create expense
    expense = Expense(
        group_id=group_id,
        description=description,
        amount=amount_paise,
        currency=currency,
        split_type=split_type,
        expense_type=expense_type,
        category=category,
        paid_by=paid_by,
        created_by=created_by,
        idempotency_key=idempotency_key,
    )
    db.add(expense)
    await db.flush()

    # Create splits — payer gets paid_amount = total, each member gets owed_amount
    for member_id, owed_amount in owed_splits.items():
        split = ExpenseSplit(
            expense_id=expense.id,
            user_id=member_id,
            paid_amount=amount_paise if member_id == paid_by else 0,
            owed_amount=owed_amount,
        )
        db.add(split)

    # If payer is not in the split list, still record their payment
    if paid_by not in owed_splits:
        split = ExpenseSplit(
            expense_id=expense.id,
            user_id=paid_by,
            paid_amount=amount_paise,
            owed_amount=0,
        )
        db.add(split)

    await db.commit()
    await db.refresh(expense)
    return expense


async def update_expense(
    db: AsyncSession,
    expense_id: int,
    user_id: int,
    description: str | None = None,
    amount_paise: int | None = None,
    currency: str | None = None,
    category: str | None = None,
    split_type: str | None = None,
    paid_by: int | None = None,
    member_ids: list[int] | None = None,
    member_values: dict[int, float] | None = None,
) -> Expense | None:
    """Update an expense. Only the creator can edit. Recomputes splits if amount/split changes."""
    expense = await db.get(Expense, expense_id)
    if expense is None or expense.created_by != user_id or expense.deleted_at is not None:
        return None

    # Update scalar fields
    if description is not None:
        expense.description = description
    if currency is not None:
        expense.currency = currency
    if category is not None:
        expense.category = category
    if paid_by is not None:
        expense.paid_by = paid_by
    if split_type is not None:
        expense.split_type = split_type

    amount_changed = amount_paise is not None and amount_paise != expense.amount
    if amount_paise is not None:
        expense.amount = amount_paise

    expense.updated_at = datetime.utcnow()

    # Recompute splits if amount, split_type, or members changed
    needs_recompute = amount_changed or split_type is not None or member_ids is not None
    if needs_recompute:
        # Delete old splits
        old_splits = await db.execute(
            select(ExpenseSplit).where(ExpenseSplit.expense_id == expense_id)
        )
        for old_split in old_splits.scalars().all():
            await db.delete(old_split)
        await db.flush()

        # Get current member_ids if not provided
        if member_ids is None:
            from app.models.group import GroupMember
            members_result = await db.execute(
                select(GroupMember.user_id).where(GroupMember.group_id == expense.group_id)
            )
            member_ids = [row[0] for row in members_result.all()]

        current_split_type = split_type or expense.split_type
        current_amount = expense.amount
        current_paid_by = paid_by or expense.paid_by

        # Compute new splits
        if current_split_type == "equal":
            owed_splits = compute_equal_splits(current_amount, member_ids)
        elif current_split_type == "exact" and member_values:
            owed_splits = compute_exact_splits(current_amount, member_values)
        elif current_split_type == "percent" and member_values:
            owed_splits = compute_percent_splits(current_amount, member_values)
        else:
            owed_splits = compute_equal_splits(current_amount, member_ids)

        # Create new splits
        for member_id, owed_amount in owed_splits.items():
            new_split = ExpenseSplit(
                expense_id=expense.id,
                user_id=member_id,
                paid_amount=current_amount if member_id == current_paid_by else 0,
                owed_amount=owed_amount,
            )
            db.add(new_split)

        if current_paid_by not in owed_splits:
            db.add(ExpenseSplit(
                expense_id=expense.id,
                user_id=current_paid_by,
                paid_amount=current_amount,
                owed_amount=0,
            ))

    await db.commit()
    await db.refresh(expense)
    return expense


async def soft_delete_expense(db: AsyncSession, expense_id: int) -> None:
    expense = await db.get(Expense, expense_id)
    if expense and expense.deleted_at is None:
        expense.deleted_at = datetime.utcnow()
        await db.commit()

"""Expense service — DB operations for creating, updating, and recalculating expenses.

Pure split computation lives in app/services/splits.py.
This module handles DB reads/writes and transaction coordination.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense, ExpenseSplit

# Re-export pure functions so existing imports don't break
from app.services.splits import (  # noqa: F401
    compute_effective_shares,
    compute_equal_splits,
    compute_exact_splits,
    compute_full_split,
    compute_percent_splits,
    compute_shares_splits,
    compute_splits,
)


# ---------------------------------------------------------------------------
# Shared helper: delete old splits → create new splits → handle payer
# ---------------------------------------------------------------------------

async def replace_expense_splits(
    db: AsyncSession,
    expense: Expense,
    owed_splits: dict[int, int],
) -> list[ExpenseSplit]:
    """Delete all existing splits for an expense and create new ones.

    Handles the payer edge case (payer not in split list gets a payment-only row).
    Returns the list of new ExpenseSplit objects (not yet flushed).
    """
    old_result = await db.execute(
        select(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id)
    )
    for old_split in old_result.scalars().all():
        await db.delete(old_split)
    await db.flush()

    new_splits = []
    for user_id, owed_amount in owed_splits.items():
        split = ExpenseSplit(
            expense_id=expense.id,
            user_id=user_id,
            paid_amount=expense.amount if user_id == expense.paid_by else 0,
            owed_amount=owed_amount,
        )
        db.add(split)
        new_splits.append(split)

    if expense.paid_by not in owed_splits:
        payer_split = ExpenseSplit(
            expense_id=expense.id,
            user_id=expense.paid_by,
            paid_amount=expense.amount,
            owed_amount=0,
        )
        db.add(payer_split)
        new_splits.append(payer_split)

    return new_splits


# ---------------------------------------------------------------------------
# Bulk recalculation helpers (shared query + batch write pattern)
# ---------------------------------------------------------------------------

RECALCABLE_SPLIT_TYPES = ["equal", "shares"]


async def _batch_load_splits(
    db: AsyncSession, expense_ids: list[int],
) -> dict[int, list[ExpenseSplit]]:
    """Load all splits for a list of expense IDs in a single query."""
    if not expense_ids:
        return {}
    result = await db.execute(
        select(ExpenseSplit).where(ExpenseSplit.expense_id.in_(expense_ids))
    )
    splits_by_expense: dict[int, list[ExpenseSplit]] = {}
    for split in result.scalars().all():
        splits_by_expense.setdefault(split.expense_id, []).append(split)
    return splits_by_expense


async def _batch_replace_splits(
    db: AsyncSession,
    replacements: list[tuple[Expense, dict[int, int]]],
) -> int:
    """Batch delete+create splits for multiple expenses. Returns count."""
    if not replacements:
        return 0

    to_delete = []
    to_create = []
    for expense, owed_splits in replacements:
        # Collect old splits for deletion
        old_result = await db.execute(
            select(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id)
        )
        to_delete.extend(old_result.scalars().all())

        # Build new splits
        for user_id, owed_amount in owed_splits.items():
            to_create.append(ExpenseSplit(
                expense_id=expense.id,
                user_id=user_id,
                paid_amount=expense.amount if user_id == expense.paid_by else 0,
                owed_amount=owed_amount,
            ))
        if expense.paid_by not in owed_splits:
            to_create.append(ExpenseSplit(
                expense_id=expense.id,
                user_id=expense.paid_by,
                paid_amount=expense.amount,
                owed_amount=0,
            ))

    # Phase 1: delete all old splits
    for old_split in to_delete:
        await db.delete(old_split)
    await db.flush()

    # Phase 2: create all new splits
    for new_split in to_create:
        db.add(new_split)
    await db.flush()

    return len(replacements)


# ---------------------------------------------------------------------------
# Recalculate group splits (on settings change)
# ---------------------------------------------------------------------------

async def recalculate_group_splits(
    db: AsyncSession,
    group_id: int,
    member_shares: dict[int, int],
) -> int:
    """Recalculate splits for all equal/shares expenses using new share weights.

    Called when group default_shares change in settings.
    Does NOT commit — caller controls the transaction boundary.
    """
    # Only recalculate equal-split expenses (shares-type have custom weights)
    result = await db.execute(
        select(Expense)
        .where(
            Expense.group_id == group_id,
            Expense.split_type == "equal",
            Expense.expense_type == "expense",
            Expense.deleted_at.is_(None),
        )
        .with_for_update()
    )
    expenses = result.scalars().all()
    if not expenses:
        return 0

    expense_ids = [e.id for e in expenses]
    splits_by_expense = await _batch_load_splits(db, expense_ids)

    replacements = []
    for expense in expenses:
        old_splits = splits_by_expense.get(expense.id, [])
        participant_ids = [s.user_id for s in old_splits]
        if not participant_ids:
            continue

        expense_shares = {uid: float(member_shares.get(uid, 1)) for uid in participant_ids}
        new_owed = compute_shares_splits(expense.amount, expense_shares)
        replacements.append((expense, new_owed))

    return await _batch_replace_splits(db, replacements)


# ---------------------------------------------------------------------------
# Recalculate splits when a new member joins
# ---------------------------------------------------------------------------

async def recalculate_splits_for_new_member(
    db: AsyncSession,
    group_id: int,
    new_member_id: int,
) -> int:
    """Add a new member to all equal/shares expenses and recalculate.

    Called when a user joins a group (invite or add-friend).
    Does NOT commit — caller controls the transaction boundary.
    """
    from app.models.group import GroupMember

    shares_result = await db.execute(
        select(GroupMember.user_id, GroupMember.default_shares)
        .where(GroupMember.group_id == group_id)
    )
    member_shares = {row[0]: row[1] for row in shares_result.all()}

    result = await db.execute(
        select(Expense)
        .where(
            Expense.group_id == group_id,
            Expense.split_type.in_(RECALCABLE_SPLIT_TYPES),
            Expense.expense_type == "expense",
            Expense.deleted_at.is_(None),
        )
        .with_for_update()
    )
    expenses = result.scalars().all()
    if not expenses:
        return 0

    expense_ids = [e.id for e in expenses]
    splits_by_expense = await _batch_load_splits(db, expense_ids)

    replacements = []
    for expense in expenses:
        old_splits = splits_by_expense.get(expense.id, [])
        participant_ids = [s.user_id for s in old_splits]
        if not participant_ids:
            continue

        # Check total_splits cap
        if expense.total_splits and new_member_id not in participant_ids:
            current_share_sum = sum(
                float(member_shares.get(uid, 1)) for uid in participant_ids
            )
            if current_share_sum >= expense.total_splits:
                continue

        if new_member_id not in participant_ids:
            participant_ids.append(new_member_id)

        expense_shares = {uid: float(member_shares.get(uid, 1)) for uid in participant_ids}
        new_owed = compute_shares_splits(
            expense.amount, expense_shares, total_splits=expense.total_splits,
        )
        replacements.append((expense, new_owed))

    return await _batch_replace_splits(db, replacements)


# ---------------------------------------------------------------------------
# Lazy repair: fix missing members on page load
# ---------------------------------------------------------------------------

async def repair_missing_splits(
    db: AsyncSession,
    group_id: int,
) -> int:
    """Detect and fix group members missing from equal/shares expenses.

    Fast pre-check without locks — only acquires FOR UPDATE if repair is needed.
    """
    from app.models.group import GroupMember

    members_result = await db.execute(
        select(GroupMember.user_id, GroupMember.default_shares)
        .where(GroupMember.group_id == group_id)
    )
    member_shares = {row[0]: row[1] for row in members_result.all()}
    member_ids = set(member_shares.keys())
    if not member_ids:
        return 0

    # Fast pre-check: read-only scan
    result = await db.execute(
        select(Expense.id).where(
            Expense.group_id == group_id,
            Expense.split_type.in_(RECALCABLE_SPLIT_TYPES),
            Expense.expense_type == "expense",
            Expense.deleted_at.is_(None),
        )
    )
    candidate_ids = [row[0] for row in result.all()]
    if not candidate_ids:
        return 0

    splits_by_expense = await _batch_load_splits(db, candidate_ids)

    needs_repair_ids = []
    for expense_id in candidate_ids:
        old_splits = splits_by_expense.get(expense_id, [])
        split_user_ids = {s.user_id for s in old_splits}
        if member_ids - split_user_ids:
            needs_repair_ids.append(expense_id)

    if not needs_repair_ids:
        return 0

    # Lock only expenses needing repair
    locked_result = await db.execute(
        select(Expense).where(Expense.id.in_(needs_repair_ids)).with_for_update()
    )
    expenses = locked_result.scalars().all()

    # Re-fetch splits after locking
    splits_by_expense = await _batch_load_splits(db, needs_repair_ids)

    replacements = []
    for expense in expenses:
        old_splits = splits_by_expense.get(expense.id, [])
        split_user_ids = {s.user_id for s in old_splits}

        missing = member_ids - split_user_ids
        if not missing:
            continue

        # Check total_splits cap
        if expense.total_splits:
            current_share_sum = sum(
                float(member_shares.get(uid, 1)) for uid in split_user_ids
            )
            if current_share_sum >= expense.total_splits:
                continue

        all_participant_ids = list(split_user_ids | member_ids)

        # Trim to fit total_splits
        if expense.total_splits:
            total_so_far = sum(
                float(member_shares.get(uid, 1)) for uid in all_participant_ids
            )
            if total_so_far > expense.total_splits:
                all_participant_ids = list(split_user_ids)
                for mid in (member_ids - split_user_ids):
                    new_sum = sum(
                        float(member_shares.get(uid, 1)) for uid in all_participant_ids
                    ) + float(member_shares.get(mid, 1))
                    if new_sum <= expense.total_splits:
                        all_participant_ids.append(mid)

        expense_shares = {
            uid: float(member_shares.get(uid, 1)) for uid in all_participant_ids
        }
        new_owed = compute_shares_splits(
            expense.amount, expense_shares, total_splits=expense.total_splits,
        )
        replacements.append((expense, new_owed))

    return await _batch_replace_splits(db, replacements)


# ---------------------------------------------------------------------------
# Create expense + splits
# ---------------------------------------------------------------------------

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
    total_splits: int | None = None,
) -> Expense:
    """Create expense + splits atomically."""
    if idempotency_key:
        existing = await db.execute(
            select(Expense).where(Expense.idempotency_key == idempotency_key)
        )
        found = existing.scalar_one_or_none()
        if found:
            return found

    owed_splits = compute_splits(
        amount_paise, split_type, member_ids, member_values, total_splits,
    )

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
        total_splits=total_splits,
    )
    db.add(expense)
    await db.flush()

    for member_id, owed_amount in owed_splits.items():
        db.add(ExpenseSplit(
            expense_id=expense.id,
            user_id=member_id,
            paid_amount=amount_paise if member_id == paid_by else 0,
            owed_amount=owed_amount,
        ))

    if paid_by not in owed_splits:
        db.add(ExpenseSplit(
            expense_id=expense.id,
            user_id=paid_by,
            paid_amount=amount_paise,
            owed_amount=0,
        ))

    await db.commit()
    await db.refresh(expense)
    return expense


# ---------------------------------------------------------------------------
# Update expense
# ---------------------------------------------------------------------------

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
    """Update an expense. Only the creator can edit. Recomputes splits if needed."""
    expense = await db.get(Expense, expense_id)
    if expense is None or expense.created_by != user_id or expense.deleted_at is not None:
        return None

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

    needs_recompute = amount_changed or split_type is not None or member_ids is not None
    if needs_recompute:
        if member_ids is None:
            from app.models.group import GroupMember
            members_result = await db.execute(
                select(GroupMember.user_id).where(
                    GroupMember.group_id == expense.group_id
                )
            )
            member_ids = [row[0] for row in members_result.all()]

        owed_splits = compute_splits(
            expense.amount,
            split_type or expense.split_type,
            member_ids,
            member_values,
        )
        await replace_expense_splits(db, expense, owed_splits)

    await db.commit()
    await db.refresh(expense)
    return expense


# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------

async def soft_delete_expense(db: AsyncSession, expense_id: int) -> None:
    expense = await db.get(Expense, expense_id)
    if expense and expense.deleted_at is None:
        expense.deleted_at = datetime.utcnow()
        await db.commit()

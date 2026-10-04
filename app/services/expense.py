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


def compute_shares_splits(
    amount_paise: int,
    member_shares: dict[int, float],
    total_splits: int | None = None,
) -> dict[int, int]:
    """Shares/weights split — values are share counts. Distribute proportionally.

    If total_splits is provided, divide by total_splits instead of sum(member_shares).
    This allows "split by N" where N > current member count — pending shares stay unassigned.
    """
    if not member_shares:
        return {}
    denominator = float(total_splits) if total_splits else sum(member_shares.values())
    if denominator == 0:
        return {}

    splits = {}
    total_assigned = 0
    members = list(member_shares.items())
    for member_id, shares in members[:-1]:
        paise = round(amount_paise * shares / denominator)
        splits[member_id] = paise
        total_assigned += paise

    # Last member gets their proportional share (NOT remainder when total_splits is set)
    last_id, last_shares = members[-1]
    if total_splits:
        splits[last_id] = round(amount_paise * last_shares / denominator)
    else:
        splits[last_id] = amount_paise - total_assigned
    return splits


def compute_full_split(amount_paise: int, owes_user_id: int, member_ids: list[int]) -> dict[int, int]:
    """Full split — one person owes the entire amount, everyone else owes 0."""
    splits = {}
    for member_id in member_ids:
        splits[member_id] = amount_paise if member_id == owes_user_id else 0
    return splits


async def recalculate_group_splits(
    db: AsyncSession,
    group_id: int,
    member_shares: dict[int, int],
) -> int:
    """Recalculate splits for all 'equal' expenses in a group using new share weights.

    Only affects non-deleted, non-settlement expenses with split_type='equal'.
    Does NOT commit — caller controls the transaction boundary.
    Returns the number of expenses recalculated.
    """
    # Fetch all equal expenses in the group, with row-level lock for thread safety
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

    # Batch-load all splits for these expenses (single query, no N+1)
    expense_ids = [e.id for e in expenses]
    all_splits_result = await db.execute(
        select(ExpenseSplit).where(ExpenseSplit.expense_id.in_(expense_ids))
    )
    splits_by_expense: dict[int, list[ExpenseSplit]] = {}
    for s in all_splits_result.scalars().all():
        splits_by_expense.setdefault(s.expense_id, []).append(s)

    count = 0
    for expense in expenses:
        old_splits = splits_by_expense.get(expense.id, [])
        participant_ids = [s.user_id for s in old_splits]

        if not participant_ids:
            continue

        # Build per-expense shares from group defaults
        expense_shares = {uid: float(member_shares.get(uid, 1)) for uid in participant_ids}

        # Compute new splits
        new_owed = compute_shares_splits(expense.amount, expense_shares)

        # Delete old splits
        for old_split in old_splits:
            await db.delete(old_split)
        await db.flush()

        # Create new splits
        for uid, owed_amount in new_owed.items():
            db.add(ExpenseSplit(
                expense_id=expense.id,
                user_id=uid,
                paid_amount=expense.amount if uid == expense.paid_by else 0,
                owed_amount=owed_amount,
            ))

        # If payer not in participants, still record their payment
        if expense.paid_by not in new_owed:
            db.add(ExpenseSplit(
                expense_id=expense.id,
                user_id=expense.paid_by,
                paid_amount=expense.amount,
                owed_amount=0,
            ))

        count += 1

    await db.flush()
    return count


async def recalculate_splits_for_new_member(
    db: AsyncSession,
    group_id: int,
    new_member_id: int,
) -> int:
    """Add a new member to all equal/shares-split expenses in a group and recalculate.

    Called when a user joins a group (invite or add-friend).
    Only affects non-deleted, non-settlement, equal or shares-split expenses.
    Does NOT commit — caller controls the transaction boundary.
    Returns the number of expenses recalculated.
    """
    from app.models.group import GroupMember

    # Get all member shares for the group (including the new member)
    shares_result = await db.execute(
        select(GroupMember.user_id, GroupMember.default_shares)
        .where(GroupMember.group_id == group_id)
    )
    member_shares = {row[0]: row[1] for row in shares_result.all()}

    # Fetch all equal/shares expenses in the group, with row-level lock
    result = await db.execute(
        select(Expense)
        .where(
            Expense.group_id == group_id,
            Expense.split_type.in_(["equal", "shares"]),
            Expense.expense_type == "expense",
            Expense.deleted_at.is_(None),
        )
        .with_for_update()
    )
    expenses = result.scalars().all()

    if not expenses:
        return 0

    # Batch-load all splits for these expenses (single query, no N+1)
    expense_ids = [e.id for e in expenses]
    all_splits_result = await db.execute(
        select(ExpenseSplit).where(ExpenseSplit.expense_id.in_(expense_ids))
    )
    splits_by_expense: dict[int, list[ExpenseSplit]] = {}
    for s in all_splits_result.scalars().all():
        splits_by_expense.setdefault(s.expense_id, []).append(s)

    # Phase 1: compute new splits and collect all deletes
    to_delete = []
    to_create = []
    count = 0
    for expense in expenses:
        old_splits = splits_by_expense.get(expense.id, [])
        participant_ids = [s.user_id for s in old_splits]

        if not participant_ids:
            continue

        # If total_splits is set, check if there's room for the new member
        if expense.total_splits and new_member_id not in participant_ids:
            current_share_sum = sum(
                float(member_shares.get(uid, 1)) for uid in participant_ids
            )
            if current_share_sum >= expense.total_splits:
                continue  # no room — all splits claimed

        # Add new member to participants
        if new_member_id not in participant_ids:
            participant_ids.append(new_member_id)

        # Build per-expense shares from group defaults
        expense_shares = {uid: float(member_shares.get(uid, 1)) for uid in participant_ids}
        new_owed = compute_shares_splits(
            expense.amount, expense_shares, total_splits=expense.total_splits,
        )

        to_delete.extend(old_splits)

        for uid, owed_amount in new_owed.items():
            to_create.append(ExpenseSplit(
                expense_id=expense.id,
                user_id=uid,
                paid_amount=expense.amount if uid == expense.paid_by else 0,
                owed_amount=owed_amount,
            ))

        if expense.paid_by not in new_owed:
            to_create.append(ExpenseSplit(
                expense_id=expense.id,
                user_id=expense.paid_by,
                paid_amount=expense.amount,
                owed_amount=0,
            ))

        count += 1

    # Phase 2: flush deletes, then add inserts
    for old_split in to_delete:
        await db.delete(old_split)
    await db.flush()

    for new_split in to_create:
        db.add(new_split)
    await db.flush()

    return count


async def repair_missing_splits(
    db: AsyncSession,
    group_id: int,
) -> int:
    """Detect and fix group members missing from equal/shares-split expenses.

    Lazy self-repair: called on group detail page load.
    Fast pre-check without locks — only acquires FOR UPDATE if repair is needed.
    Returns the number of expenses repaired.
    """
    from app.models.group import GroupMember

    # Get all current group members and their shares
    members_result = await db.execute(
        select(GroupMember.user_id, GroupMember.default_shares)
        .where(GroupMember.group_id == group_id)
    )
    member_shares = {row[0]: row[1] for row in members_result.all()}
    member_ids = set(member_shares.keys())

    if not member_ids:
        return 0

    # Fast pre-check: read-only scan to find expenses needing repair
    result = await db.execute(
        select(Expense.id)
        .where(
            Expense.group_id == group_id,
            Expense.split_type.in_(["equal", "shares"]),
            Expense.expense_type == "expense",
            Expense.deleted_at.is_(None),
        )
    )
    candidate_ids = [row[0] for row in result.all()]

    if not candidate_ids:
        return 0

    # Check which expenses are missing members (read-only, no lock)
    all_splits_result = await db.execute(
        select(ExpenseSplit).where(ExpenseSplit.expense_id.in_(candidate_ids))
    )
    splits_by_expense: dict[int, list[ExpenseSplit]] = {}
    for s in all_splits_result.scalars().all():
        splits_by_expense.setdefault(s.expense_id, []).append(s)

    needs_repair_ids = []
    for expense_id in candidate_ids:
        old_splits = splits_by_expense.get(expense_id, [])
        split_user_ids = {s.user_id for s in old_splits}
        if member_ids - split_user_ids:
            needs_repair_ids.append(expense_id)

    if not needs_repair_ids:
        return 0

    # Only now lock the specific expenses that need repair
    locked_result = await db.execute(
        select(Expense)
        .where(Expense.id.in_(needs_repair_ids))
        .with_for_update()
    )
    expenses = locked_result.scalars().all()

    # Re-fetch splits for locked expenses (state may have changed)
    repair_splits_result = await db.execute(
        select(ExpenseSplit).where(ExpenseSplit.expense_id.in_(needs_repair_ids))
    )
    splits_by_expense = {}
    for s in repair_splits_result.scalars().all():
        splits_by_expense.setdefault(s.expense_id, []).append(s)

    # Phase 1: compute new splits and collect all deletes
    to_delete = []
    to_create = []
    count = 0
    for expense in expenses:
        old_splits = splits_by_expense.get(expense.id, [])
        split_user_ids = {s.user_id for s in old_splits}

        missing = member_ids - split_user_ids
        if not missing:
            continue

        # If total_splits is set, only add members if there's room
        if expense.total_splits:
            current_share_sum = sum(
                float(member_shares.get(uid, 1)) for uid in split_user_ids
            )
            if current_share_sum >= expense.total_splits:
                continue  # no room

        all_participant_ids = list(split_user_ids | member_ids)

        # If total_splits caps the participants, only add as many as fit
        if expense.total_splits:
            total_so_far = sum(
                float(member_shares.get(uid, 1)) for uid in all_participant_ids
            )
            # Trim new members if they'd exceed total_splits
            if total_so_far > expense.total_splits:
                all_participant_ids = list(split_user_ids)
                for mid in (member_ids - split_user_ids):
                    new_sum = sum(
                        float(member_shares.get(uid, 1)) for uid in all_participant_ids
                    ) + float(member_shares.get(mid, 1))
                    if new_sum <= expense.total_splits:
                        all_participant_ids.append(mid)

        expense_shares = {uid: float(member_shares.get(uid, 1)) for uid in all_participant_ids}
        new_owed = compute_shares_splits(
            expense.amount, expense_shares, total_splits=expense.total_splits,
        )

        to_delete.extend(old_splits)

        for uid, owed_amount in new_owed.items():
            to_create.append(ExpenseSplit(
                expense_id=expense.id,
                user_id=uid,
                paid_amount=expense.amount if uid == expense.paid_by else 0,
                owed_amount=owed_amount,
            ))

        if expense.paid_by not in new_owed:
            to_create.append(ExpenseSplit(
                expense_id=expense.id,
                user_id=expense.paid_by,
                paid_amount=expense.amount,
                owed_amount=0,
            ))

        count += 1

    # Phase 2: flush deletes, then add inserts
    for old_split in to_delete:
        await db.delete(old_split)
    await db.flush()

    for new_split in to_create:
        db.add(new_split)
    await db.flush()
    return count


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
        # When total_splits is set, use shares logic with 1 share per member
        if total_splits:
            equal_shares = dict.fromkeys(member_ids, 1.0)
            owed_splits = compute_shares_splits(
                amount_paise, equal_shares, total_splits=total_splits,
            )
        else:
            owed_splits = compute_equal_splits(amount_paise, member_ids)
    elif split_type == "exact" and member_values:
        owed_splits = compute_exact_splits(amount_paise, member_values)
    elif split_type == "percent" and member_values:
        owed_splits = compute_percent_splits(amount_paise, member_values)
    elif split_type == "shares" and member_values:
        owed_splits = compute_shares_splits(amount_paise, member_values, total_splits=total_splits)
    elif split_type == "full" and member_values and "full_owes" in member_values:
        owed_splits = compute_full_split(amount_paise, int(member_values["full_owes"]), member_ids)
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
        total_splits=total_splits,
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
        elif current_split_type == "shares" and member_values:
            owed_splits = compute_shares_splits(current_amount, member_values)
        elif current_split_type == "full" and member_values and "full_owes" in member_values:
            owed_splits = compute_full_split(current_amount, int(member_values["full_owes"]), member_ids)
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

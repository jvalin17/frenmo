"""Tests for recalculating expense splits when group default shares change."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.expense import create_expense_with_splits, recalculate_group_splits


@pytest.fixture
async def trip_group(db_session: AsyncSession):
    """Group with 3 members: Alice, Bob, Charlie."""
    alice = User(email="a@test.com", name="Alice", password_hash="h")
    bob = User(email="b@test.com", name="Bob", password_hash="h")
    charlie = User(email="c@test.com", name="Charlie", password_hash="h")
    db_session.add_all([alice, bob, charlie])
    await db_session.flush()

    group = Group(name="Trip", created_by=alice.id, invite_token=f"tok_{uuid.uuid4().hex[:8]}")
    db_session.add(group)
    await db_session.flush()

    db_session.add_all([
        GroupMember(group_id=group.id, user_id=alice.id),
        GroupMember(group_id=group.id, user_id=bob.id),
        GroupMember(group_id=group.id, user_id=charlie.id),
    ])
    await db_session.commit()
    return group, alice, bob, charlie


async def _get_splits(db: AsyncSession, expense_id: int) -> dict[int, ExpenseSplit]:
    result = await db.execute(
        select(ExpenseSplit).where(ExpenseSplit.expense_id == expense_id)
    )
    return {s.user_id: s for s in result.scalars().all()}


class TestRecalculateGroupSplits:

    async def test_recalculate_updates_equal_expenses(self, db_session, trip_group):
        """Equal expense should be recalculated with new shares."""
        group, alice, bob, charlie = trip_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Hotel",
            amount_paise=9000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id, charlie.id],
        )

        # Before: each owes 3000
        splits = await _get_splits(db_session, expense.id)
        assert splits[alice.id].owed_amount == 3000

        # Recalculate with charlie=3 shares (spouse)
        new_shares = {alice.id: 1, bob.id: 1, charlie.id: 3}
        count = await recalculate_group_splits(db_session, group.id, new_shares)
        await db_session.commit()

        # After: A=1800, B=1800, C=5400 (1/5, 1/5, 3/5 of 9000)
        splits = await _get_splits(db_session, expense.id)
        assert splits[alice.id].owed_amount == 1800
        assert splits[bob.id].owed_amount == 1800
        assert splits[charlie.id].owed_amount == 5400
        assert count == 1

    async def test_recalculate_ignores_shares_type(self, db_session, trip_group):
        """Expenses with split_type='shares' should not be recalculated."""
        group, alice, bob, charlie = trip_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Custom split",
            amount_paise=10000, split_type="shares", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            member_values={alice.id: 2.0, bob.id: 3.0},
        )

        splits_before = await _get_splits(db_session, expense.id)
        bob_owed_before = splits_before[bob.id].owed_amount

        await recalculate_group_splits(db_session, group.id, {alice.id: 1, bob.id: 1, charlie.id: 3})
        await db_session.commit()

        splits_after = await _get_splits(db_session, expense.id)
        assert splits_after[bob.id].owed_amount == bob_owed_before  # unchanged

    async def test_recalculate_ignores_exact_type(self, db_session, trip_group):
        """Expenses with split_type='exact' should not be recalculated."""
        group, alice, bob, charlie = trip_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Exact",
            amount_paise=10000, split_type="exact", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            member_values={alice.id: 70.0, bob.id: 30.0},
        )

        splits_before = await _get_splits(db_session, expense.id)

        await recalculate_group_splits(db_session, group.id, {alice.id: 1, bob.id: 1, charlie.id: 3})
        await db_session.commit()

        splits_after = await _get_splits(db_session, expense.id)
        assert splits_after[alice.id].owed_amount == splits_before[alice.id].owed_amount

    async def test_recalculate_ignores_deleted_expenses(self, db_session, trip_group):
        """Soft-deleted expenses should not be recalculated."""
        group, alice, bob, charlie = trip_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Deleted",
            amount_paise=6000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id, charlie.id],
        )
        from app.services.expense import soft_delete_expense
        await soft_delete_expense(db_session, expense.id)

        count = await recalculate_group_splits(db_session, group.id, {alice.id: 1, bob.id: 1, charlie.id: 3})
        assert count == 0

    async def test_recalculate_ignores_settlements(self, db_session, trip_group):
        """Settlement expenses should not be recalculated."""
        group, alice, bob, charlie = trip_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Settlement",
            amount_paise=5000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            expense_type="settlement",
        )

        count = await recalculate_group_splits(db_session, group.id, {alice.id: 1, bob.id: 1, charlie.id: 3})
        assert count == 0

    async def test_recalculate_preserves_paid_amount(self, db_session, trip_group):
        """After recalculation, payer's paid_amount should still equal expense amount."""
        group, alice, bob, charlie = trip_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Taxi",
            amount_paise=5000, split_type="equal", paid_by=bob.id,
            created_by=alice.id, member_ids=[alice.id, bob.id, charlie.id],
        )

        await recalculate_group_splits(db_session, group.id, {alice.id: 1, bob.id: 1, charlie.id: 2})
        await db_session.commit()

        splits = await _get_splits(db_session, expense.id)
        assert splits[bob.id].paid_amount == 5000  # bob paid
        assert splits[alice.id].paid_amount == 0
        assert splits[charlie.id].paid_amount == 0

    async def test_recalculate_multiple_expenses(self, db_session, trip_group):
        """Multiple equal expenses in the same group all get recalculated."""
        group, alice, bob, charlie = trip_group

        e1 = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Hotel",
            amount_paise=9000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id, charlie.id],
        )
        e2 = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Dinner",
            amount_paise=6000, split_type="equal", paid_by=bob.id,
            created_by=bob.id, member_ids=[alice.id, bob.id, charlie.id],
        )

        count = await recalculate_group_splits(db_session, group.id, {alice.id: 1, bob.id: 1, charlie.id: 3})
        await db_session.commit()

        assert count == 2

        s1 = await _get_splits(db_session, e1.id)
        assert s1[charlie.id].owed_amount == 5400  # 3/5 of 9000

        s2 = await _get_splits(db_session, e2.id)
        assert s2[charlie.id].owed_amount == 3600  # 3/5 of 6000

    async def test_recalculate_no_equal_expenses_is_noop(self, db_session, trip_group):
        """Group with only non-equal expenses returns 0."""
        group, alice, bob, charlie = trip_group

        await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Custom",
            amount_paise=10000, split_type="shares", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            member_values={alice.id: 1.0, bob.id: 1.0},
        )

        count = await recalculate_group_splits(db_session, group.id, {alice.id: 1, bob.id: 1, charlie.id: 3})
        assert count == 0

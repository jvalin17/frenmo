"""Tests for split-by-N: total_splits independent of member count, fractional shares."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.expense import create_expense_with_splits, recalculate_splits_for_new_member
from app.services.splits import compute_shares_splits


class TestComputeSharesSplitsWithTotalShares:

    def test_compute_shares_splits_with_total_splits(self):
        """$600 split by 6: Alice(3)=$300, Bob(1)=$100. Only $400 assigned."""
        member_shares = {1: 3.0, 2: 1.0}
        result = compute_shares_splits(60000, member_shares, total_splits=6)
        assert result[1] == 30000  # Alice: 3/6 * 60000
        assert result[2] == 10000  # Bob: 1/6 * 60000
        assert sum(result.values()) == 40000  # only 4/6 assigned

    def test_total_splits_all_claimed(self):
        """When all shares are claimed, total == amount."""
        member_shares = {1: 3.0, 2: 2.0, 3: 1.0}
        result = compute_shares_splits(60000, member_shares, total_splits=6)
        assert sum(result.values()) == 60000

    def test_total_splits_none_uses_member_sum(self):
        """When total_splits is None, behaves like before."""
        member_shares = {1: 3.0, 2: 1.0}
        result = compute_shares_splits(60000, member_shares, total_splits=None)
        assert result[1] == 45000  # 3/4 * 60000
        assert result[2] == 15000  # 1/4 * 60000
        assert sum(result.values()) == 60000

    def test_fractional_kid_share(self):
        """Kid gets 0.5 share: family of 2 adults + 1 kid = 2.5 shares out of 3."""
        member_shares = {1: 1.0, 2: 1.0, 3: 0.5}
        result = compute_shares_splits(30000, member_shares, total_splits=3)
        # 1/3 * 30000 = 10000, 1/3 * 30000 = 10000, 0.5/3 * 30000 = 5000
        assert result[1] == 10000
        assert result[2] == 10000
        assert result[3] == 5000
        # Only 2.5/3 assigned = 25000
        assert sum(result.values()) == 25000

    def test_fractional_shares_without_total_splits(self):
        """Fractional shares work normally without total_splits."""
        member_shares = {1: 1.0, 2: 0.5}
        result = compute_shares_splits(15000, member_shares)
        # 1/1.5 * 15000 = 10000, 0.5/1.5 * 15000 = 5000
        assert result[1] == 10000
        assert result[2] == 5000


@pytest.fixture
async def split_n_group(db_session: AsyncSession):
    """Group with Alice, Bob. Charlie will join later."""
    alice = User(email="alice@test.com", name="Alice", password_hash="h")
    bob = User(email="bob@test.com", name="Bob", password_hash="h")
    charlie = User(email="charlie@test.com", name="Charlie", password_hash="h")
    db_session.add_all([alice, bob, charlie])
    await db_session.flush()

    group = Group(
        name="Trip", created_by=alice.id,
        invite_token=f"tok_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(group)
    await db_session.flush()

    db_session.add_all([
        GroupMember(group_id=group.id, user_id=alice.id),
        GroupMember(group_id=group.id, user_id=bob.id),
    ])
    await db_session.commit()
    return group, alice, bob, charlie


class TestSplitByNIntegration:

    async def test_create_expense_with_total_splits(self, db_session, split_n_group):
        """Create expense with total_splits=4, only 2 members."""
        group, alice, bob, charlie = split_n_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Hotel",
            amount_paise=40000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            total_splits=4,
        )

        assert expense.total_splits == 4

        # Each member gets 1/4 = 10000
        splits_result = await db_session.execute(
            select(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id)
        )
        splits = {s.user_id: s for s in splits_result.scalars().all()}
        assert splits[alice.id].owed_amount == 10000
        assert splits[bob.id].owed_amount == 10000
        # Only 20000 of 40000 assigned — 20000 pending for future members

    async def test_new_member_gets_pending_share(self, db_session, split_n_group):
        """When Charlie joins, he gets 1 share from the pending pool."""
        group, alice, bob, charlie = split_n_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Hotel",
            amount_paise=40000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            total_splits=4,
        )

        # Charlie joins
        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.flush()
        await recalculate_splits_for_new_member(db_session, group.id, charlie.id)
        await db_session.commit()

        splits_result = await db_session.execute(
            select(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id)
        )
        splits = {s.user_id: s for s in splits_result.scalars().all()}
        # Now 3/4 assigned: Alice=10000, Bob=10000, Charlie=10000
        assert charlie.id in splits
        assert splits[charlie.id].owed_amount == 10000
        assert splits[alice.id].owed_amount == 10000

    async def test_no_share_when_total_splits_full(self, db_session, split_n_group):
        """When all splits are claimed, new member does NOT get added."""
        group, alice, bob, charlie = split_n_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Dinner",
            amount_paise=20000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            total_splits=2,  # exactly 2 members, no room
        )

        # Charlie joins — but total_splits=2 already filled by Alice+Bob
        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.flush()
        await recalculate_splits_for_new_member(db_session, group.id, charlie.id)
        await db_session.commit()

        splits_result = await db_session.execute(
            select(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id)
        )
        splits = {s.user_id: s for s in splits_result.scalars().all()}
        # Charlie should NOT be in this expense — no room
        assert charlie.id not in splits

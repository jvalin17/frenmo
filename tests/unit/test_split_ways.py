"""Tests for split_ways — group-level default and expense-level override.

Scenario: 5 people went on a trip (4 adults + 1 kid).
Only 2 are on the app. Expenses should still be divided by 5.
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.expense import (
    create_expense_with_splits,
    recalculate_group_splits,
    recalculate_splits_for_new_member,
    repair_missing_splits,
    resolve_split_ways,
)


@pytest.fixture
async def trip_group(db_session):
    """Group with 2 members but default_split_ways=5."""
    alice = User(name="Alice", email="alice@sw.com", password_hash="x")
    bob = User(name="Bob", email="bob@sw.com", password_hash="x")
    db_session.add_all([alice, bob])
    await db_session.flush()

    group = Group(
        name="Trip", created_by=alice.id, currency="USD",
        default_split_ways=5,
        invite_token=f"tok_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(group)
    await db_session.flush()

    db_session.add(GroupMember(group_id=group.id, user_id=alice.id, default_shares=1))
    db_session.add(GroupMember(group_id=group.id, user_id=bob.id, default_shares=2))
    await db_session.commit()
    return alice, bob, group


class TestGroupDefaultSplitWays:

    @pytest.mark.asyncio
    async def test_group_stores_default_split_ways(self, db_session, trip_group):
        """TC1: Group model stores default_split_ways."""
        _, _, group = trip_group
        assert group.default_split_ways == 5

    @pytest.mark.asyncio
    async def test_settings_saves_default_split_ways(self, db_session, trip_group):
        """TC2: Settings route saves default_split_ways on group."""
        _, _, group = trip_group
        # Simulate what the settings route does
        group.default_split_ways = 8
        await db_session.commit()
        await db_session.refresh(group)
        assert group.default_split_ways == 8

        # Clear it
        group.default_split_ways = None
        await db_session.commit()
        await db_session.refresh(group)
        assert group.default_split_ways is None

    @pytest.mark.asyncio
    async def test_group_default_split_ways_nullable(self, db_session):
        """default_split_ways=None means split among current members."""
        user = User(name="Solo", email="solo@sw.com", password_hash="x")
        db_session.add(user)
        await db_session.flush()
        group = Group(
            name="Normal", created_by=user.id, currency="USD",
            invite_token=f"tok_{uuid.uuid4().hex[:8]}",
        )
        db_session.add(group)
        await db_session.commit()
        assert group.default_split_ways is None


class TestExpenseInheritsGroupSplitWays:

    @pytest.mark.asyncio
    async def test_expense_inherits_group_split_ways(self, db_session, trip_group):
        """TC3: Expense inherits group default_split_ways when not overridden."""
        alice, bob, group = trip_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Hotel",
            amount_paise=50000, split_type="shares",
            paid_by=alice.id, created_by=alice.id,
            member_ids=[alice.id, bob.id],
            member_values={alice.id: 1.0, bob.id: 2.0},
            currency="USD",
        )

        assert expense.split_ways == 5

    @pytest.mark.asyncio
    async def test_split_amounts_use_split_ways_denominator(self, db_session, trip_group):
        """TC4: $500 split 5 ways: Alice=1/5=$100, Bob=2/5=$200."""
        alice, bob, group = trip_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Hotel",
            amount_paise=50000, split_type="shares",
            paid_by=alice.id, created_by=alice.id,
            member_ids=[alice.id, bob.id],
            member_values={alice.id: 1.0, bob.id: 2.0},
            currency="USD",
        )

        splits_result = await db_session.execute(
            select(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id)
        )
        owed_by_user = {s.user_id: s.owed_amount for s in splits_result.scalars().all()}
        assert owed_by_user[alice.id] == 10000  # 1/5 of 50000
        assert owed_by_user[bob.id] == 20000    # 2/5 of 50000


class TestResolveSplitWays:
    """Unit tests for resolve_split_ways helper."""

    def test_resolve_split_ways_expense_override_takes_priority(self):
        """Per-expense split_ways wins over group default."""
        expense = Expense(split_ways=3)
        group = Group(name="G", created_by=1, default_split_ways=5)
        assert resolve_split_ways(expense, group) == 3

    def test_falls_back_to_group_default(self):
        """When expense.split_ways is NULL, use group default."""
        expense = Expense(split_ways=None)
        group = Group(name="G", created_by=1, default_split_ways=5)
        assert resolve_split_ways(expense, group) == 5

    def test_none_when_both_unset(self):
        """When neither is set, returns None."""
        expense = Expense(split_ways=None)
        group = Group(name="G", created_by=1, default_split_ways=None)
        assert resolve_split_ways(expense, group) is None

    def test_none_when_no_group(self):
        """When group is None, returns None."""
        expense = Expense(split_ways=None)
        assert resolve_split_ways(expense, None) is None


class TestRecalculationUsesGroupDefault:
    """Bug: recalculation paths ignore group.default_split_ways on old expenses."""

    @pytest.fixture
    async def group_with_old_expense(self, db_session):
        """Group with default_split_ways=5, but expense has split_ways=NULL (pre-existing)."""
        alice = User(name="Alice", email="alice@rc.com", password_hash="x")
        bob = User(name="Bob", email="bob@rc.com", password_hash="x")
        charlie = User(name="Charlie", email="charlie@rc.com", password_hash="x")
        db_session.add_all([alice, bob, charlie])
        await db_session.flush()

        group = Group(
            name="Oregon Trip", created_by=alice.id, currency="USD",
            default_split_ways=5,
            invite_token=f"tok_{uuid.uuid4().hex[:8]}",
        )
        db_session.add(group)
        await db_session.flush()

        db_session.add(GroupMember(group_id=group.id, user_id=alice.id, default_shares=1))
        db_session.add(GroupMember(group_id=group.id, user_id=bob.id, default_shares=2))
        await db_session.flush()

        # Create expense WITHOUT split_ways (simulates old expense before feature existed)
        expense = Expense(
            group_id=group.id, description="Hotel", amount=50000,
            split_type="shares", paid_by=alice.id, created_by=alice.id,
            currency="USD", split_ways=None,
        )
        db_session.add(expense)
        await db_session.flush()

        # Manually create splits as if split_ways was not set (divided by 3 = 1+2)
        db_session.add(ExpenseSplit(
            expense_id=expense.id, user_id=alice.id,
            paid_amount=50000, owed_amount=16667,  # 1/3
        ))
        db_session.add(ExpenseSplit(
            expense_id=expense.id, user_id=bob.id,
            paid_amount=0, owed_amount=33333,  # 2/3
        ))
        await db_session.commit()
        return alice, bob, charlie, group, expense

    @pytest.mark.asyncio
    async def test_recalculate_group_splits_uses_group_default(
        self, db_session, group_with_old_expense,
    ):
        """recalculate_group_splits should use group.default_split_ways for old expenses."""
        alice, bob, charlie, group, expense = group_with_old_expense

        await recalculate_group_splits(
            db_session, group.id,
            member_shares={alice.id: 1, bob.id: 2},
        )
        await db_session.commit()

        splits_result = await db_session.execute(
            select(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id)
        )
        owed = {s.user_id: s.owed_amount for s in splits_result.scalars().all()}
        # With split_ways=5: Alice=1/5=10000, Bob=2/5=20000
        assert owed[alice.id] == 10000, f"Expected 10000 (1/5), got {owed[alice.id]}"
        assert owed[bob.id] == 20000, f"Expected 20000 (2/5), got {owed[bob.id]}"

    @pytest.mark.asyncio
    async def test_new_member_join_uses_group_default(
        self, db_session, group_with_old_expense,
    ):
        """recalculate_splits_for_new_member should use group.default_split_ways."""
        alice, bob, charlie, group, expense = group_with_old_expense

        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id, default_shares=1))
        await db_session.flush()

        await recalculate_splits_for_new_member(db_session, group.id, charlie.id)
        await db_session.commit()

        splits_result = await db_session.execute(
            select(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id)
        )
        owed = {s.user_id: s.owed_amount for s in splits_result.scalars().all()}
        # With split_ways=5: Alice=1/5=10000, Bob=2/5=20000, Charlie=1/5=10000
        assert owed[alice.id] == 10000, f"Expected 10000 (1/5), got {owed[alice.id]}"
        assert owed[bob.id] == 20000, f"Expected 20000 (2/5), got {owed[bob.id]}"
        assert owed[charlie.id] == 10000, f"Expected 10000 (1/5), got {owed[charlie.id]}"

    @pytest.mark.asyncio
    async def test_repair_fixes_stale_split_ways_on_page_load(
        self, db_session, group_with_old_expense,
    ):
        """repair_missing_splits should recalculate when expense.split_ways is NULL
        but group.default_split_ways is set — auto-fix on page load."""
        alice, bob, charlie, group, expense = group_with_old_expense

        # All members are present (no missing members), but splits are wrong
        # because they were computed without split_ways=5
        await repair_missing_splits(db_session, group.id)
        await db_session.commit()

        splits_result = await db_session.execute(
            select(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id)
        )
        owed = {s.user_id: s.owed_amount for s in splits_result.scalars().all()}
        # With split_ways=5: Alice=1/5=10000, Bob=2/5=20000
        assert owed[alice.id] == 10000, f"Expected 10000 (1/5), got {owed[alice.id]}"
        assert owed[bob.id] == 20000, f"Expected 20000 (2/5), got {owed[bob.id]}"

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
from app.services.expense import create_expense_with_splits


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

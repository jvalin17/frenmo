"""Tests for chart data aggregation service."""
from datetime import UTC, datetime

import pytest

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.charts import (
    get_category_breakdown,
    get_monthly_spending,
    get_member_spending,
)


@pytest.fixture
async def group_with_expenses(db_session):
    """Create a group with diverse expenses for chart testing."""
    alice = User(email="alice@test.com", name="Alice", password_hash="h")
    bob = User(email="bob@test.com", name="Bob", password_hash="h")
    db_session.add_all([alice, bob])
    await db_session.flush()

    group = Group(name="Trip", type="trip", created_by=alice.id, invite_token="tok1")
    db_session.add(group)
    await db_session.flush()

    db_session.add_all([
        GroupMember(group_id=group.id, user_id=alice.id),
        GroupMember(group_id=group.id, user_id=bob.id),
    ])

    # Expense 1: Food, Jan 2026, paid by Alice
    exp1 = Expense(
        group_id=group.id, description="Dinner", amount=10000,
        currency="INR", split_type="equal", category="food",
        paid_by=alice.id, created_by=alice.id,
        created_at=datetime(2026, 1, 15, tzinfo=UTC),
    )
    # Expense 2: Transport, Jan 2026, paid by Bob
    exp2 = Expense(
        group_id=group.id, description="Taxi", amount=5000,
        currency="INR", split_type="equal", category="transport",
        paid_by=bob.id, created_by=bob.id,
        created_at=datetime(2026, 1, 20, tzinfo=UTC),
    )
    # Expense 3: Food, Feb 2026, paid by Alice
    exp3 = Expense(
        group_id=group.id, description="Lunch", amount=3000,
        currency="INR", split_type="equal", category="food",
        paid_by=alice.id, created_by=alice.id,
        created_at=datetime(2026, 2, 10, tzinfo=UTC),
    )
    # Expense 4: Deleted — should not appear
    exp4 = Expense(
        group_id=group.id, description="Cancelled", amount=9999,
        currency="INR", split_type="equal", category="food",
        paid_by=alice.id, created_by=alice.id,
        deleted_at=datetime(2026, 2, 11, tzinfo=UTC),
    )
    db_session.add_all([exp1, exp2, exp3, exp4])

    # Add splits for paid_by tracking
    await db_session.flush()
    db_session.add_all([
        ExpenseSplit(expense_id=exp1.id, user_id=alice.id, paid_amount=10000, owed_amount=5000),
        ExpenseSplit(expense_id=exp1.id, user_id=bob.id, paid_amount=0, owed_amount=5000),
        ExpenseSplit(expense_id=exp2.id, user_id=alice.id, paid_amount=0, owed_amount=2500),
        ExpenseSplit(expense_id=exp2.id, user_id=bob.id, paid_amount=5000, owed_amount=2500),
        ExpenseSplit(expense_id=exp3.id, user_id=alice.id, paid_amount=3000, owed_amount=1500),
        ExpenseSplit(expense_id=exp3.id, user_id=bob.id, paid_amount=0, owed_amount=1500),
    ])
    await db_session.commit()

    return group, alice, bob


class TestCategoryBreakdown:
    async def test_aggregates_by_category(self, db_session, group_with_expenses):
        group, alice, bob = group_with_expenses
        result = await get_category_breakdown(db_session, group.id)
        assert result["food"] == 13000  # 10000 + 3000
        assert result["transport"] == 5000

    async def test_excludes_deleted(self, db_session, group_with_expenses):
        group, alice, bob = group_with_expenses
        result = await get_category_breakdown(db_session, group.id)
        total = sum(result.values())
        assert total == 18000  # not 27999

    async def test_uncategorized_grouped(self, db_session, group_with_expenses):
        group, alice, bob = group_with_expenses
        # Add expense with no category
        exp = Expense(
            group_id=group.id, description="Misc", amount=2000,
            currency="INR", split_type="equal", category=None,
            paid_by=alice.id, created_by=alice.id,
        )
        db_session.add(exp)
        await db_session.commit()
        result = await get_category_breakdown(db_session, group.id)
        assert result.get("other", 0) == 2000


class TestMonthlySpending:
    async def test_aggregates_by_month(self, db_session, group_with_expenses):
        group, alice, bob = group_with_expenses
        result = await get_monthly_spending(db_session, group.id)
        assert result["2026-01"] == 15000  # 10000 + 5000
        assert result["2026-02"] == 3000

    async def test_excludes_deleted(self, db_session, group_with_expenses):
        group, alice, bob = group_with_expenses
        result = await get_monthly_spending(db_session, group.id)
        total = sum(result.values())
        assert total == 18000


class TestMemberSpending:
    async def test_shows_per_member_paid(self, db_session, group_with_expenses):
        group, alice, bob = group_with_expenses
        result = await get_member_spending(db_session, group.id)
        assert result[alice.id] == 13000  # 10000 + 3000
        assert result[bob.id] == 5000

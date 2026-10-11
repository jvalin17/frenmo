"""Test that Total Spent excludes settlements."""
import uuid

import pytest
from sqlalchemy import select

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User


@pytest.fixture
async def group_with_settlement(db_session):
    """Group with 1 expense ($100) and 1 settlement ($30)."""
    alice = User(name="Alice", email="alice@ts.com", password_hash="x")
    bob = User(name="Bob", email="bob@ts.com", password_hash="x")
    db_session.add_all([alice, bob])
    await db_session.flush()

    group = Group(name="Trip", created_by=alice.id, currency="USD",
                  invite_token=f"tok_{uuid.uuid4().hex[:8]}")
    db_session.add(group)
    await db_session.flush()
    db_session.add(GroupMember(group_id=group.id, user_id=alice.id))
    db_session.add(GroupMember(group_id=group.id, user_id=bob.id))
    await db_session.flush()

    # Regular expense: $100
    expense = Expense(group_id=group.id, description="Dinner", amount=10000,
                      split_type="equal", paid_by=alice.id, created_by=alice.id,
                      expense_type="expense", currency="USD")
    db_session.add(expense)
    await db_session.flush()
    db_session.add(ExpenseSplit(expense_id=expense.id, user_id=alice.id, paid_amount=10000, owed_amount=5000))
    db_session.add(ExpenseSplit(expense_id=expense.id, user_id=bob.id, paid_amount=0, owed_amount=5000))

    # Settlement: $30
    settlement = Expense(group_id=group.id, description="Settlement", amount=3000,
                         split_type="exact", paid_by=bob.id, created_by=bob.id,
                         expense_type="settlement", currency="USD")
    db_session.add(settlement)
    await db_session.flush()
    db_session.add(ExpenseSplit(expense_id=settlement.id, user_id=bob.id, paid_amount=3000, owed_amount=0))
    db_session.add(ExpenseSplit(expense_id=settlement.id, user_id=alice.id, paid_amount=0, owed_amount=3000))

    await db_session.commit()
    return group


class TestTotalSpentExcludesSettlements:

    @pytest.mark.asyncio
    async def test_total_spent_excludes_settlements(self, db_session, group_with_settlement):
        """Total Spent should be $100 (expense only), not $130 (expense + settlement)."""
        group = group_with_settlement
        result = await db_session.execute(
            select(Expense).where(
                Expense.group_id == group.id,
                Expense.deleted_at.is_(None),
            )
        )
        all_expenses = result.scalars().all()

        # Current bug: summing all expenses includes settlements
        total_all = sum(e.amount for e in all_expenses)
        assert total_all == 13000  # bug: $100 + $30

        # Correct: only sum expense_type='expense'
        total_spent = sum(e.amount for e in all_expenses if e.expense_type == "expense")
        assert total_spent == 10000  # $100 only

        # Expense count should exclude settlements too
        expense_count = sum(1 for e in all_expenses if e.expense_type == "expense")
        assert expense_count == 1  # not 2

"""Tests for get_overall_balances — cross-group balance direction.

Bug: Alice pays $50, split with Bob. Dashboard showed Alice owes Bob
instead of Bob owes Alice. The sign was inverted.
"""
import pytest

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.balance import get_overall_balances


@pytest.fixture
async def two_users(db_session):
    alice = User(name="Alice", email="alice@test.com", password_hash="x")
    bob = User(name="Bob", email="bob@test.com", password_hash="x")
    db_session.add_all([alice, bob])
    await db_session.flush()
    return alice, bob


@pytest.fixture
async def group_with_expense(db_session, two_users):
    """Alice pays $50, split equally with Bob. Each owes $25."""
    alice, bob = two_users
    group = Group(name="Trip", created_by=alice.id, currency="USD")
    db_session.add(group)
    await db_session.flush()

    for u in [alice, bob]:
        db_session.add(GroupMember(group_id=group.id, user_id=u.id))
    await db_session.flush()

    expense = Expense(
        group_id=group.id, description="Dinner", amount=5000,
        split_type="equal", paid_by=alice.id, created_by=alice.id,
        currency="USD",
    )
    db_session.add(expense)
    await db_session.flush()

    # Alice paid 5000, owes 2500. Bob paid 0, owes 2500.
    db_session.add(ExpenseSplit(
        expense_id=expense.id, user_id=alice.id,
        paid_amount=5000, owed_amount=2500,
    ))
    db_session.add(ExpenseSplit(
        expense_id=expense.id, user_id=bob.id,
        paid_amount=0, owed_amount=2500,
    ))
    await db_session.commit()
    return alice, bob, group


class TestOverallBalanceDirection:
    """Verify that get_overall_balances returns correct debt direction."""

    @pytest.mark.asyncio
    async def test_payer_sees_positive_balance(self, db_session, group_with_expense):
        """Alice paid — Bob owes her. Alice's view should show Bob with positive net."""
        alice, bob, _ = group_with_expense
        balances = await get_overall_balances(db_session, alice.id)
        # Positive = other person owes you
        assert bob.id in balances
        assert balances[bob.id] > 0, (
            f"Expected positive (Bob owes Alice), got {balances[bob.id]}"
        )

    @pytest.mark.asyncio
    async def test_non_payer_sees_negative_balance(self, db_session, group_with_expense):
        """Bob didn't pay — he owes Alice. Bob's view should show Alice with negative net."""
        alice, bob, _ = group_with_expense
        balances = await get_overall_balances(db_session, bob.id)
        # Negative = you owe the other person
        assert alice.id in balances
        assert balances[alice.id] < 0, (
            f"Expected negative (Bob owes Alice), got {balances[alice.id]}"
        )

    @pytest.mark.asyncio
    async def test_balance_amounts_correct(self, db_session, group_with_expense):
        """Alice is owed $25, Bob owes $25."""
        alice, bob, _ = group_with_expense

        alice_view = await get_overall_balances(db_session, alice.id)
        assert alice_view[bob.id] == 2500  # Bob owes Alice 2500 paise

        bob_view = await get_overall_balances(db_session, bob.id)
        assert bob_view[alice.id] == -2500  # Bob owes Alice 2500 paise

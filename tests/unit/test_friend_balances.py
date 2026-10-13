"""Tests for per-friend balance with group breakdown and settlement history."""
import uuid

import pytest

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.balance import get_friend_balance_detail
from app.services.friendship import ensure_friendship


@pytest.fixture
async def friend_balance_setup(db_session):
    """Two users in two groups with expenses and a settlement."""
    marco = User(name="Marco", email="marco@fb.com", password_hash="x")
    sana = User(name="Sana", email="sana@fb.com", password_hash="x")
    db_session.add_all([marco, sana])
    await db_session.flush()

    await ensure_friendship(db_session, marco.id, sana.id)

    # Group 1: Oregon Trip — Marco paid $100, split equally
    trip = Group(name="Oregon Trip", created_by=marco.id, currency="USD",
                 invite_token=f"tok_{uuid.uuid4().hex[:8]}")
    db_session.add(trip)
    await db_session.flush()
    db_session.add(GroupMember(group_id=trip.id, user_id=marco.id))
    db_session.add(GroupMember(group_id=trip.id, user_id=sana.id))
    await db_session.flush()

    expense1 = Expense(group_id=trip.id, description="Hotel", amount=10000,
                       split_type="equal", paid_by=marco.id, created_by=marco.id, currency="USD")
    db_session.add(expense1)
    await db_session.flush()
    db_session.add(
        ExpenseSplit(expense_id=expense1.id, user_id=marco.id, paid_amount=10000, owed_amount=5000)
    )
    db_session.add(
        ExpenseSplit(expense_id=expense1.id, user_id=sana.id, paid_amount=0, owed_amount=5000)
    )

    # Group 2: Groceries — Marco paid $60, split equally
    groceries = Group(name="Groceries", created_by=marco.id, currency="USD",
                      invite_token=f"tok_{uuid.uuid4().hex[:8]}")
    db_session.add(groceries)
    await db_session.flush()
    db_session.add(GroupMember(group_id=groceries.id, user_id=marco.id))
    db_session.add(GroupMember(group_id=groceries.id, user_id=sana.id))
    await db_session.flush()

    expense2 = Expense(group_id=groceries.id, description="Veggies", amount=6000,
                       split_type="equal", paid_by=marco.id, created_by=marco.id, currency="USD")
    db_session.add(expense2)
    await db_session.flush()
    db_session.add(
        ExpenseSplit(expense_id=expense2.id, user_id=marco.id, paid_amount=6000, owed_amount=3000)
    )
    db_session.add(
        ExpenseSplit(expense_id=expense2.id, user_id=sana.id, paid_amount=0, owed_amount=3000)
    )

    # Settlement: Sana paid Marco $20 in Oregon Trip
    settlement = Expense(group_id=trip.id, description="Settlement", amount=2000,
                         split_type="exact", paid_by=sana.id, created_by=sana.id,
                         expense_type="settlement", currency="USD")
    db_session.add(settlement)
    await db_session.flush()
    db_session.add(
        ExpenseSplit(expense_id=settlement.id, user_id=sana.id, paid_amount=2000, owed_amount=0)
    )
    db_session.add(
        ExpenseSplit(expense_id=settlement.id, user_id=marco.id, paid_amount=0, owed_amount=2000)
    )

    await db_session.commit()
    return marco, sana, trip, groceries


class TestGetFriendBalanceDetail:

    @pytest.mark.asyncio
    async def test_get_friend_balance_detail_net_total(self, db_session, friend_balance_setup):
        """Net = $50 (trip) + $30 (groceries) - $20 (settlement) = $60 owed by Sana."""
        marco, sana, _, _ = friend_balance_setup
        detail = await get_friend_balance_detail(db_session, marco.id, sana.id)

        # From Marco's perspective: Sana owes him
        assert detail["net_balances"] == {"USD": 6000}  # $60 total, single currency

    @pytest.mark.asyncio
    async def test_get_friend_balance_detail_per_group(self, db_session, friend_balance_setup):
        """Shows breakdown per shared group."""
        marco, sana, trip, groceries = friend_balance_setup
        detail = await get_friend_balance_detail(db_session, marco.id, sana.id)

        group_balances = {g["group_id"]: g["balance"] for g in detail["groups"]}
        # Trip: $50 owed - $20 settled = $30 remaining
        assert group_balances[trip.id] == 3000
        # Groceries: $30 owed
        assert group_balances[groceries.id] == 3000

    @pytest.mark.asyncio
    async def test_get_friend_balance_detail_settlements(self, db_session, friend_balance_setup):
        """Shows settlement history between the two users."""
        marco, sana, _, _ = friend_balance_setup
        detail = await get_friend_balance_detail(db_session, marco.id, sana.id)

        assert len(detail["settlements"]) == 1
        assert detail["settlements"][0]["amount"] == 2000
        assert detail["settlements"][0]["paid_by"] == sana.id

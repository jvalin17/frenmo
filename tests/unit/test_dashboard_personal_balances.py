"""Dashboard balances are personal: only money between you and each person.

Bug: Alice paid for a trip split five ways. Bob paid his share back.
Bob's dashboard still showed the other three people owing *him*, because
get_overall_balances summed each person's net across every shared expense
instead of the debt between that person and the viewer.
"""
import uuid

import pytest

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.balance import bilateral_debts, get_overall_balances, get_user_balances


def _session_cookie(user_id: int) -> dict:
    from app.middleware.auth import session_serializer

    return {"frenmo_session": session_serializer.dumps({"user_id": user_id})}


async def _settlement(db, group, payer, receiver, amount):
    """payer hands `amount` to receiver, recorded the way /settlements/new does."""
    expense = Expense(
        group_id=group.id, description="Settlement", amount=amount, split_type="exact",
        paid_by=payer.id, created_by=payer.id, expense_type="settlement",
        currency=group.currency, idempotency_key=uuid.uuid4().hex,
    )
    db.add(expense)
    await db.flush()
    db.add_all([
        ExpenseSplit(expense_id=expense.id, user_id=receiver.id, paid_amount=0, owed_amount=amount),
        ExpenseSplit(expense_id=expense.id, user_id=payer.id, paid_amount=amount, owed_amount=0),
    ])
    await db.flush()
    return expense


@pytest.fixture
async def five_way_trip(db_session):
    """Alice paid $500 for Lake Tahoe, split equally five ways ($100 each)."""
    names = ["Alice Chen", "Bob Okafor", "Carol Mendes", "Dev Patel", "Esha Rao"]
    users = [
        User(
            name=n,
            email=f"{n.split()[0].lower()}.{uuid.uuid4().hex[:6]}@example.com",
            password_hash="h",
        )
        for n in names
    ]
    db_session.add_all(users)
    await db_session.flush()

    group = Group(
        name="Lake Tahoe", created_by=users[0].id, currency="USD",
        invite_token=f"tok_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(group)
    await db_session.flush()
    db_session.add_all([GroupMember(group_id=group.id, user_id=u.id) for u in users])

    expense = Expense(
        group_id=group.id, description="Cabin", amount=50000, split_type="equal",
        paid_by=users[0].id, created_by=users[0].id, currency="USD",
    )
    db_session.add(expense)
    await db_session.flush()
    db_session.add_all([
        ExpenseSplit(
            expense_id=expense.id, user_id=u.id,
            paid_amount=50000 if u is users[0] else 0, owed_amount=10000,
        )
        for u in users
    ])
    await db_session.commit()
    return users, group


class TestDashboardBalancesArePersonal:
    @pytest.mark.asyncio
    async def test_non_payer_only_owes_the_payer(self, db_session, five_way_trip):
        """Before paying, Bob owes Alice $100 and nothing involves the other three."""
        (alice, bob, *_), _ = five_way_trip
        assert await get_overall_balances(db_session, bob.id) == {alice.id: {"USD": -10000}}

    @pytest.mark.asyncio
    async def test_settled_member_sees_nothing_owed(self, db_session, five_way_trip):
        """After Bob pays Alice his $100 he is settled with everyone."""
        (alice, bob, carol, dev, esha), group = five_way_trip
        await _settlement(db_session, group, bob, alice, 10000)
        await db_session.commit()

        assert await get_overall_balances(db_session, bob.id) == {}
        assert await get_overall_balances(db_session, alice.id) == {
            carol.id: {"USD": 10000}, dev.id: {"USD": 10000}, esha.id: {"USD": 10000},
        }

    @pytest.mark.asyncio
    async def test_dashboard_pages_differ_per_viewer(self, client, db_session, five_way_trip):
        (alice, bob, *_), group = five_way_trip
        await _settlement(db_session, group, bob, alice, 10000)
        await db_session.commit()

        bob_page = await client.get("/", cookies=_session_cookie(bob.id))
        assert bob_page.status_code == 200
        assert "All settled up" in bob_page.text
        assert "owes you" not in bob_page.text
        assert "$300.00" not in bob_page.text

        alice_page = await client.get("/", cookies=_session_cookie(alice.id))
        assert "You are owed" in alice_page.text
        assert "$300.00" in alice_page.text
        assert "Bob Okafor" not in alice_page.text  # settled people are not listed


def test_bilateral_debts():
    # Carol -> Alice 100, Bob -> Alice 40, Alice -> Dev 25; Esha -> Dev 10 does not involve Alice
    simplified = [(3, 1, 10000), (2, 1, 4000), (1, 4, 2500), (5, 4, 1000)]
    assert bilateral_debts(simplified, user_id=1) == {3: 10000, 2: 4000, 4: -2500}
    assert bilateral_debts(simplified, user_id=5) == {4: -1000}
    assert bilateral_debts([], user_id=1) == {}
    # Opposite transfers between the same pair cancel out and are dropped
    assert bilateral_debts([(2, 1, 500), (1, 2, 500)], user_id=1) == {}


@pytest.mark.asyncio
async def test_get_user_balances(db_session, five_way_trip):
    """One call yields the People balances and the viewer's net per group."""
    (alice, bob, carol, dev, esha), group = five_way_trip
    await _settlement(db_session, group, bob, alice, 10000)
    await db_session.commit()

    people, per_group = await get_user_balances(db_session, alice.id, [group])
    assert people == {carol.id: {"USD": 10000}, dev.id: {"USD": 10000}, esha.id: {"USD": 10000}}
    assert per_group == {group.id: 30000}

    people, per_group = await get_user_balances(db_session, bob.id, [group])
    assert people == {}
    assert per_group == {group.id: 0}

    assert await get_user_balances(db_session, bob.id, []) == ({}, {})

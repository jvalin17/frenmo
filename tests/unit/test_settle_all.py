"""Settle all with a friend: one settlement per group, one transaction (D2, D2a, AD-3)."""
import uuid

import pytest
from sqlalchemy import func, select

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services import settlement as settlement_service
from app.services.balance import fold_per_currency, shared_group_balances
from app.services.direct import find_or_create_direct_group
from app.services.friendship import ensure_friendship
from app.services.settlement import SettleEntry, net_for, settle_all, settle_all_plan


async def _group(db, name, currency, owner, members):
    group = Group(
        name=name, created_by=owner.id, currency=currency,
        invite_token=f"tok_{uuid.uuid4().hex[:8]}",
    )
    db.add(group)
    await db.flush()
    db.add_all([GroupMember(group_id=group.id, user_id=m.id) for m in members])
    await db.flush()
    return group


async def _equal_expense(db, group, description, amount, payer, other):
    expense = Expense(
        group_id=group.id, description=description, amount=amount, split_type="equal",
        paid_by=payer.id, created_by=payer.id, currency=group.currency,
    )
    db.add(expense)
    await db.flush()
    half = amount // 2
    db.add_all([
        ExpenseSplit(
            expense_id=expense.id, user_id=payer.id, paid_amount=amount, owed_amount=half
        ),
        ExpenseSplit(
            expense_id=expense.id, user_id=other.id, paid_amount=0, owed_amount=amount - half
        ),
    ])
    await db.flush()
    return expense


@pytest.fixture
async def rahul_owes_1485(db_session):
    """Goa Trip (INR): Priya paid ₹3,000 → Rahul owes ₹1,500.
    Direct pair group (INR): Rahul paid ₹30 → Priya owes ₹15.
    Seattle Flat (USD): Rahul paid $90 → Priya owes $45 (must stay untouched by an INR settle-all).
    """
    priya = User(
        name="Priya Nair", email=f"priya.{uuid.uuid4().hex[:6]}@example.com",
        password_hash="h", default_currency="INR",
    )
    rahul = User(
        name="Rahul Verma", email=f"rahul.{uuid.uuid4().hex[:6]}@example.com",
        password_hash="h", default_currency="USD",
    )
    db_session.add_all([priya, rahul])
    await db_session.flush()
    await ensure_friendship(db_session, priya.id, rahul.id)

    goa = await _group(db_session, "Goa Trip", "INR", priya, [priya, rahul])
    await _equal_expense(db_session, goa, "Villa", 300000, priya, rahul)
    # Pair group takes Priya's default currency: INR
    direct = await find_or_create_direct_group(db_session, priya.id, rahul.id)
    await _equal_expense(db_session, direct, "Chai", 3000, rahul, priya)
    seattle = await _group(db_session, "Seattle Flat", "USD", rahul, [priya, rahul])
    await _equal_expense(db_session, seattle, "Groceries", 9000, rahul, priya)
    await db_session.commit()
    return priya, rahul, goa, direct, seattle


async def _settlement_count(db):
    return (await db.execute(
        select(func.count()).select_from(Expense).where(Expense.expense_type == "settlement")
    )).scalar_one()


@pytest.mark.asyncio
async def test_shared_group_balances(db_session, rahul_owes_1485):
    priya, rahul, goa, direct, seattle = rahul_owes_1485
    rows = await shared_group_balances(db_session, priya.id, rahul.id)
    assert {(r["group_id"], r["currency"], r["balance"]) for r in rows} == {
        (goa.id, "INR", 150000), (direct.id, "INR", -1500), (seattle.id, "USD", -4500),
    }
    assert {r["group_name"] for r in rows} == {
        "Goa Trip", "Priya Nair & Rahul Verma", "Seattle Flat",
    }
    # Mirror from Rahul's side
    mirror = await shared_group_balances(db_session, rahul.id, priya.id)
    assert {(r["group_id"], r["balance"]) for r in mirror} == {
        (goa.id, -150000), (direct.id, 1500), (seattle.id, 4500),
    }


def test_fold_per_currency():
    rows = [
        {"currency": "INR", "balance": 150000}, {"currency": "INR", "balance": -1500},
        {"currency": "USD", "balance": -4500}, {"currency": "EUR", "balance": 700},
        {"currency": "EUR", "balance": -700},
    ]
    # EUR nets to zero and is dropped
    assert fold_per_currency(rows) == {"INR": 148500, "USD": -4500}
    assert fold_per_currency([]) == {}


def test_net_for():
    entries = [
        SettleEntry(group_id=1, group_name="Goa Trip", currency="INR",
                    debtor_id=2, creditor_id=1, amount=150000),
        SettleEntry(group_id=5, group_name="Direct", currency="INR",
                    debtor_id=1, creditor_id=2, amount=1500),
    ]
    assert net_for(entries, user_id=1) == 148500   # Priya receives ₹1,485 net
    assert net_for(entries, user_id=2) == -148500  # Rahul pays ₹1,485 net
    assert net_for([], user_id=1) == 0


@pytest.mark.asyncio
async def test_settle_all_plan(db_session, rahul_owes_1485):
    priya, rahul, goa, direct, seattle = rahul_owes_1485
    plan = await settle_all_plan(db_session, priya.id, rahul.id, "INR")
    assert plan == [
        SettleEntry(group_id=goa.id, group_name="Goa Trip", currency="INR",
                    debtor_id=rahul.id, creditor_id=priya.id, amount=150000),
        SettleEntry(group_id=direct.id, group_name="Priya Nair & Rahul Verma", currency="INR",
                    debtor_id=priya.id, creditor_id=rahul.id, amount=1500),
    ]
    assert net_for(plan, priya.id) == 148500
    # Nothing to settle in a currency they do not share
    assert await settle_all_plan(db_session, priya.id, rahul.id, "EUR") == []


@pytest.mark.asyncio
async def test_settle_all(db_session, rahul_owes_1485):
    priya, rahul, goa, direct, seattle = rahul_owes_1485
    # Rahul's view before: he owes ₹1,485 net and $0 → mirror of Priya's +₹1,485
    assert fold_per_currency(await shared_group_balances(db_session, rahul.id, priya.id)) == {
        "INR": -148500, "USD": 4500,
    }

    written = await settle_all(db_session, priya.id, rahul.id, "INR", batch_id="batch-a1")
    await db_session.commit()

    assert [(e.group_id, e.paid_by, e.amount, e.currency, e.expense_type) for e in written] == [
        (goa.id, rahul.id, 150000, "INR", "settlement"),
        (direct.id, priya.id, 1500, "INR", "settlement"),
    ]
    assert await _settlement_count(db_session) == 2
    # Every INR group is settled on both sides; the USD flat is untouched
    assert fold_per_currency(await shared_group_balances(db_session, priya.id, rahul.id)) == {
        "USD": -4500,
    }
    assert fold_per_currency(await shared_group_balances(db_session, rahul.id, priya.id)) == {
        "USD": 4500,
    }


@pytest.mark.asyncio
async def test_settle_all_is_per_currency(db_session, rahul_owes_1485):
    priya, rahul, goa, direct, seattle = rahul_owes_1485
    plan = await settle_all_plan(db_session, priya.id, rahul.id, "USD")
    assert plan == [
        SettleEntry(group_id=seattle.id, group_name="Seattle Flat", currency="USD",
                    debtor_id=priya.id, creditor_id=rahul.id, amount=4500),
    ]
    written = await settle_all(db_session, priya.id, rahul.id, "USD", batch_id="batch-b2")
    await db_session.commit()
    assert len(written) == 1 and written[0].currency == "USD"
    # INR balances are exactly as before: never converted, never touched
    assert fold_per_currency(await shared_group_balances(db_session, priya.id, rahul.id)) == {
        "INR": 148500,
    }


@pytest.mark.asyncio
async def test_settle_all_is_atomic(db_session, rahul_owes_1485, monkeypatch):
    priya, rahul, *_ = rahul_owes_1485
    priya_id, rahul_id = priya.id, rahul.id  # the rollback below expires the ORM objects
    real_create = settlement_service.create_expense_with_splits
    calls = {"n": 0}

    async def fail_on_second(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated database failure on the second group")
        return await real_create(*args, **kwargs)

    monkeypatch.setattr(settlement_service, "create_expense_with_splits", fail_on_second)
    with pytest.raises(RuntimeError):
        await settle_all(db_session, priya_id, rahul_id, "INR", batch_id="batch-c3")
    await db_session.rollback()

    assert await _settlement_count(db_session) == 0
    assert fold_per_currency(await shared_group_balances(db_session, priya_id, rahul_id)) == {
        "INR": 148500, "USD": -4500,
    }


@pytest.mark.asyncio
async def test_settle_all_is_idempotent_per_batch(db_session, rahul_owes_1485):
    priya, rahul, *_ = rahul_owes_1485
    first = await settle_all(db_session, priya.id, rahul.id, "INR", batch_id="batch-d4")
    await db_session.commit()
    second = await settle_all(db_session, priya.id, rahul.id, "INR", batch_id="batch-d4")
    await db_session.commit()
    assert second == []  # nothing left to settle, nothing written
    assert await _settlement_count(db_session) == 2
    assert {e.idempotency_key for e in first} == {
        f"settle-all:batch-d4:{first[0].group_id}", f"settle-all:batch-d4:{first[1].group_id}",
    }


@pytest.mark.asyncio
async def test_settle_all_refuses_non_friends(db_session, rahul_owes_1485):
    priya, rahul, *_ = rahul_owes_1485
    stranger = User(
        name="Dev Patel", email=f"dev.{uuid.uuid4().hex[:6]}@example.com", password_hash="h"
    )
    db_session.add(stranger)
    await db_session.flush()
    assert await settle_all(db_session, priya.id, stranger.id, "INR", batch_id="x") is None
    assert await settle_all(db_session, priya.id, priya.id, "INR", batch_id="x") is None
    assert await _settlement_count(db_session) == 0

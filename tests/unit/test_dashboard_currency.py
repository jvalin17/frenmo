"""Dashboard currency handling.

Overall balances are kept per currency (the group's currency) and the
dashboard renders each group's symbol instead of a hardcoded "$".
"""
import uuid

import pytest

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.balance import get_overall_balances
from app.services.friendship import ensure_friendship


def _session_cookie(user_id: int) -> dict:
    from app.middleware.auth import session_serializer

    return {"frenmo_session": session_serializer.dumps({"user_id": user_id})}


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


async def _equal_expense(db, group, description, amount, payer, other, currency):
    expense = Expense(
        group_id=group.id, description=description, amount=amount, split_type="equal",
        paid_by=payer.id, created_by=payer.id, currency=currency,
    )
    db.add(expense)
    await db.flush()
    half = amount // 2
    rest = amount - half
    db.add_all([
        ExpenseSplit(expense_id=expense.id, user_id=payer.id, paid_amount=amount, owed_amount=half),
        ExpenseSplit(expense_id=expense.id, user_id=other.id, paid_amount=0, owed_amount=rest),
    ])
    return expense


@pytest.fixture
async def mixed_currency_dashboard(db_session):
    """Priya and Rahul share Goa Trip (INR) and Seattle Flat (USD).

    Goa Trip: Priya paid ₹4,000 → Rahul owes ₹2,000.
    Seattle Flat: Rahul paid $90 → Priya owes $45.
    """
    priya = User(name="Priya", email="priya.nair@example.com", password_hash="h")
    rahul = User(name="Rahul", email="rahul.verma@example.com", password_hash="h")
    db_session.add_all([priya, rahul])
    await db_session.flush()
    await ensure_friendship(db_session, priya.id, rahul.id)

    goa = await _group(db_session, "Goa Trip", "INR", priya, [priya, rahul])
    seattle = await _group(db_session, "Seattle Flat", "USD", rahul, [priya, rahul])
    await _equal_expense(db_session, goa, "Beach shack", 400000, priya, rahul, "INR")
    await _equal_expense(db_session, seattle, "Groceries", 9000, rahul, priya, "USD")
    await db_session.commit()
    return priya, rahul, goa, seattle


class TestOverallBalancesPerCurrency:
    @pytest.mark.asyncio
    async def test_overall_balances_keyed_by_group_currency(
        self, db_session, mixed_currency_dashboard
    ):
        priya, rahul, _, _ = mixed_currency_dashboard
        balances = await get_overall_balances(db_session, priya.id)
        assert balances == {rahul.id: {"INR": 200000, "USD": -4500}}

        balances = await get_overall_balances(db_session, rahul.id)
        assert balances == {priya.id: {"INR": -200000, "USD": 4500}}


class TestDashboardRendersGroupCurrency:
    @pytest.mark.asyncio
    async def test_hero_and_people_show_each_currency(
        self, client, db_session, mixed_currency_dashboard
    ):
        priya, _, _, _ = mixed_currency_dashboard
        resp = await client.get("/", cookies=_session_cookie(priya.id))
        assert resp.status_code == 200

        # Hero totals, one per currency
        assert "₹2000.00" in resp.text
        assert "$45.00" in resp.text
        # People pills with the group symbol
        assert "owes you ₹2000.00" in resp.text
        assert "you owe $45.00" in resp.text
        # Never a cross-currency total (200000 - 4500 = 195500)
        assert "1955.00" not in resp.text
        assert "$2000.00" not in resp.text

    @pytest.mark.asyncio
    async def test_group_rows_use_group_symbol(self, client, db_session, mixed_currency_dashboard):
        priya, _, _, _ = mixed_currency_dashboard
        resp = await client.get("/", cookies=_session_cookie(priya.id))

        assert "gets back ₹2000.00" in resp.text
        assert "owes $45.00" in resp.text
        assert "gets back $2000.00" not in resp.text


class TestSummarizeByCurrency:
    def test_summarize_by_currency(self):
        from app.services.balance import summarize_by_currency

        rows = summarize_by_currency({7: {"USD": -4500, "INR": 200000}, 9: {"USD": 1200}})
        assert [(r.currency, r.owed, r.owe, r.net) for r in rows] == [
            ("INR", 200000, 0, 200000),
            ("USD", 1200, 4500, -3300),
        ]

    def test_net(self):
        from app.services.balance import CurrencyTotal

        assert CurrencyTotal("USD", owed=500, owe=200).net == 300
        assert CurrencyTotal("INR", owed=0, owe=4500).net == -4500

    def test_hero_state(self):
        from app.services.balance import hero_state, summarize_by_currency

        assert hero_state(summarize_by_currency({})) == "settled"
        assert hero_state(summarize_by_currency({7: {"USD": 500}})) == "positive"
        assert hero_state(summarize_by_currency({7: {"USD": -500}})) == "negative"
        assert hero_state(summarize_by_currency({7: {"USD": -500, "INR": 900}})) == "mixed"
        # Owed and owe in one currency cancel to zero -> settled
        assert hero_state(summarize_by_currency({7: {"USD": -500}, 9: {"USD": 500}})) == "settled"


class TestLegacyNullCurrencyBackfilled:
    """Databases created before the currency columns existed get them via
    ALTER TABLE ADD COLUMN with no default, so every existing row is NULL.
    The startup migration must backfill those rows, otherwise grouping and
    sorting balances by currency would raise on None.
    """

    @pytest.mark.asyncio
    async def test_startup_migration_backfills_null_currency(self):
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.database import Base, migrate_schema

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            def seed(sync_conn):
                from sqlalchemy.orm import Session

                with Session(bind=sync_conn) as session:
                    maria = User(name="Maria", email="maria.garcia@example.com", password_hash="h")
                    session.add(maria)
                    session.flush()
                    session.add(
                        Group(name="Old Flat", created_by=maria.id, invite_token="tok_legacy1")
                    )
                    session.commit()

            await conn.run_sync(seed)
            # Simulate a database from before the currency columns existed:
            # migrate_schema re-adds them via ALTER TABLE ADD COLUMN, which leaves NULLs.
            await conn.execute(text("ALTER TABLE groups DROP COLUMN currency"))
            await conn.execute(text("ALTER TABLE users DROP COLUMN default_currency"))
            await conn.run_sync(migrate_schema)
            group_currency = (
                await conn.execute(text("SELECT currency FROM groups WHERE id = 1"))
            ).scalar()
            user_currency = (
                await conn.execute(text("SELECT default_currency FROM users WHERE id = 1"))
            ).scalar()
        await engine.dispose()
        assert group_currency == "USD"
        assert user_currency == "USD"

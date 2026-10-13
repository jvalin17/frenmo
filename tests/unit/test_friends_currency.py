"""Friends page currency handling.

Balances must carry each group's currency and never be summed across
currencies; the template must render the group's symbol, not a hardcoded "$".
"""
import uuid

import pytest

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.balance import get_friend_balance_detail
from app.services.currency import CURRENCY_SYMBOLS
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
async def mixed_currency_friends(db_session):
    """Priya and Rahul share an INR group (Goa Trip) and a USD group (Seattle Flat).

    Goa Trip: Priya paid ₹4,000 → Rahul owes ₹2,000.
    Seattle Flat: Rahul paid $90 → Priya owes $45.
    Settlement in Goa Trip: Rahul paid Priya ₹500.
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

    settlement = Expense(
        group_id=goa.id, description="Settlement", amount=50000, split_type="exact",
        paid_by=rahul.id, created_by=rahul.id, expense_type="settlement", currency="INR",
    )
    db_session.add(settlement)
    await db_session.flush()
    db_session.add_all([
        ExpenseSplit(expense_id=settlement.id, user_id=rahul.id, paid_amount=50000, owed_amount=0),
        ExpenseSplit(expense_id=settlement.id, user_id=priya.id, paid_amount=0, owed_amount=50000),
    ])

    await db_session.commit()
    return priya, rahul, goa, seattle


class TestCurrencySymbols:
    def test_symbol_map_covers_supported_currencies(self):
        assert CURRENCY_SYMBOLS["INR"] == "₹"
        assert CURRENCY_SYMBOLS["USD"] == "$"
        assert CURRENCY_SYMBOLS["EUR"] == "€"
        assert CURRENCY_SYMBOLS["GBP"] == "£"
        assert CURRENCY_SYMBOLS["JPY"] == "¥"


class TestFriendBalanceDetailCurrency:
    @pytest.mark.asyncio
    async def test_net_balances_are_kept_per_currency(self, db_session, mixed_currency_friends):
        """₹2,000 owed minus ₹500 settled stays in INR; the $45 Priya owes stays in USD."""
        priya, rahul, _, _ = mixed_currency_friends
        detail = await get_friend_balance_detail(db_session, priya.id, rahul.id)

        assert detail["net_balances"] == {"INR": 150000, "USD": -4500}
        assert "net_balance" not in detail, "a single cross-currency total must not be exposed"

    @pytest.mark.asyncio
    async def test_group_breakdown_carries_group_currency(self, db_session, mixed_currency_friends):
        priya, rahul, goa, seattle = mixed_currency_friends
        detail = await get_friend_balance_detail(db_session, priya.id, rahul.id)

        by_group = {g["group_id"]: g for g in detail["groups"]}
        assert by_group[goa.id]["currency"] == "INR"
        assert by_group[goa.id]["balance"] == 150000
        assert by_group[seattle.id]["currency"] == "USD"
        assert by_group[seattle.id]["balance"] == -4500

    @pytest.mark.asyncio
    async def test_settlements_carry_group_currency(self, db_session, mixed_currency_friends):
        priya, rahul, _, _ = mixed_currency_friends
        detail = await get_friend_balance_detail(db_session, priya.id, rahul.id)

        assert len(detail["settlements"]) == 1
        assert detail["settlements"][0]["currency"] == "INR"
        assert detail["settlements"][0]["amount"] == 50000


class TestFriendsPageRendersGroupCurrency:
    @pytest.mark.asyncio
    async def test_header_shows_one_pill_per_currency(
        self, client, db_session, mixed_currency_friends
    ):
        priya, _, _, _ = mixed_currency_friends
        resp = await client.get("/friends/", cookies=_session_cookie(priya.id))
        assert resp.status_code == 200

        assert "owes you ₹1500.00" in resp.text
        assert "you owe $45.00" in resp.text
        # Never a cross-currency sum (₹1500 - $45 = 145500 paise/cents)
        assert "1455.00" not in resp.text

    @pytest.mark.asyncio
    async def test_breakdown_and_history_use_group_symbol(
        self, client, db_session, mixed_currency_friends
    ):
        priya, _, _, _ = mixed_currency_friends
        resp = await client.get("/friends/", cookies=_session_cookie(priya.id))

        assert "₹500.00" in resp.text, "settlement in the INR group must render with ₹"
        assert "$500.00" not in resp.text, "INR settlement must not be rendered with $"
        assert "$1500.00" not in resp.text, "INR group balance must not be rendered with $"


class TestSettlementStoresGroupCurrency:
    @pytest.mark.asyncio
    async def test_recorded_settlement_uses_group_currency(
        self, client, db_session, mixed_currency_friends
    ):
        """A settlement posted in the USD group must not fall back to the expense default (INR)."""
        from sqlalchemy import select

        priya, rahul, _, seattle = mixed_currency_friends
        resp = await client.post(
            f"/settlements/new/{seattle.id}",
            data={"from_user": priya.id, "to_user": rahul.id, "amount": "20.00"},
            cookies=_session_cookie(priya.id),
        )
        assert resp.status_code == 303

        row = await db_session.execute(
            select(Expense).where(
                Expense.group_id == seattle.id, Expense.expense_type == "settlement"
            )
        )
        settlement = row.scalar_one()
        assert settlement.amount == 2000
        assert settlement.currency == "USD"

    @pytest.mark.asyncio
    async def test_non_member_cannot_record_settlement(
        self, client, db_session, mixed_currency_friends
    ):
        from sqlalchemy import func, select

        priya, rahul, _, seattle = mixed_currency_friends
        outsider = User(name="Dev", email="dev.kapoor@example.com", password_hash="h")
        db_session.add(outsider)
        await db_session.commit()

        resp = await client.post(
            f"/settlements/new/{seattle.id}",
            data={"from_user": priya.id, "to_user": rahul.id, "amount": "20.00"},
            cookies=_session_cookie(outsider.id),
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

        count = await db_session.scalar(
            select(func.count()).select_from(Expense).where(
                Expense.group_id == seattle.id, Expense.expense_type == "settlement"
            )
        )
        assert count == 0

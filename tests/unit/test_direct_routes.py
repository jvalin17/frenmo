"""Friend-page routes for direct expenses (requirements F2, F5; architecture AD-6)."""
import uuid

import pytest
from sqlalchemy import func, select

from app.models.expense import Expense, ExpenseSplit
from app.models.friendship import Friendship
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.direct import (
    find_or_create_direct_group,
    lookup_direct_group,
    pair_group_is_settled,
    pair_key_for,
)
from app.services.friendship import (
    ensure_friendship,
    get_pair_simplify,
    is_friend,
    set_pair_simplify,
)
from app.services.settlement import settle_all


def _cookie(user_id: int) -> dict:
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


async def _settlements(db):
    return (await db.execute(
        select(func.count()).select_from(Expense).where(Expense.expense_type == "settlement")
    )).scalar_one()


@pytest.fixture
async def people(db_session):
    """Priya (INR) and Rahul (USD) are friends; Dev is a stranger to Rahul and a friend of Priya."""
    priya = User(
        name="Priya Nair", email=f"priya.{uuid.uuid4().hex[:6]}@example.com",
        password_hash="h", default_currency="INR",
    )
    rahul = User(
        name="Rahul Verma", email=f"rahul.{uuid.uuid4().hex[:6]}@example.com",
        password_hash="h", default_currency="USD",
    )
    dev = User(name="Dev Patel", email=f"dev.{uuid.uuid4().hex[:6]}@example.com", password_hash="h")
    db_session.add_all([priya, rahul, dev])
    await db_session.flush()
    await ensure_friendship(db_session, priya.id, rahul.id)
    await ensure_friendship(db_session, priya.id, dev.id)
    await db_session.commit()
    return priya, rahul, dev


@pytest.fixture
async def rahul_owes_1485(db_session, people):
    """Goa Trip (INR): Rahul owes ₹1,500. Pair group (INR): Priya owes ₹15.
    Seattle Flat (USD): Priya owes $45."""
    priya, rahul, dev = people
    goa = await _group(db_session, "Goa Trip", "INR", priya, [priya, rahul])
    await _equal_expense(db_session, goa, "Villa", 300000, priya, rahul)
    direct = await find_or_create_direct_group(db_session, priya.id, rahul.id)
    await _equal_expense(db_session, direct, "Chai", 3000, rahul, priya)
    seattle = await _group(db_session, "Seattle Flat", "USD", rahul, [priya, rahul])
    await _equal_expense(db_session, seattle, "Groceries", 9000, rahul, priya)
    await db_session.commit()
    return priya, rahul, dev, goa, direct, seattle


@pytest.mark.asyncio
async def test_direct_expense(client, db_session, people):
    priya, rahul, dev = people
    resp = await client.post(
        f"/friends/{rahul.id}/direct", cookies=_cookie(priya.id), follow_redirects=False
    )
    assert resp.status_code == 303
    pair = await lookup_direct_group(db_session, pair_key_for(priya.id, rahul.id))
    assert pair is not None
    assert resp.headers["location"] == f"/expenses/new/{pair.id}"

    form = await client.get(resp.headers["location"], cookies=_cookie(priya.id))
    assert form.status_code == 200
    assert "Priya Nair" in form.text and "Rahul Verma" in form.text
    assert "Dev Patel" not in form.text


@pytest.mark.asyncio
async def test_direct_expense_refuses_non_friends(client, db_session, people):
    priya, rahul, dev = people
    resp = await client.post(
        f"/friends/{dev.id}/direct", cookies=_cookie(rahul.id), follow_redirects=False
    )
    assert resp.status_code == 303 and resp.headers["location"] == "/friends"
    count = (await db_session.execute(
        select(func.count()).select_from(Group).where(Group.type == "direct")
    )).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_settle_all_confirm(client, db_session, rahul_owes_1485):
    priya, rahul, *_ = rahul_owes_1485
    resp = await client.get(
        f"/friends/{rahul.id}/settle-all", params={"currency": "INR"}, cookies=_cookie(priya.id)
    )
    assert resp.status_code == 200
    assert "Goa Trip" in resp.text and "1500.00" in resp.text
    assert "Priya Nair &amp; Rahul Verma" in resp.text and "15.00" in resp.text
    assert "1485.00" in resp.text  # the net cash Rahul hands over
    assert 'name="batch_id"' in resp.text and 'name="currency" value="INR"' in resp.text
    assert "Seattle Flat" not in resp.text  # USD is never mixed in

    empty = await client.get(
        f"/friends/{rahul.id}/settle-all", params={"currency": "EUR"}, cookies=_cookie(priya.id)
    )
    assert empty.status_code == 200
    assert "Nothing to settle" in empty.text and 'name="batch_id"' not in empty.text


@pytest.mark.asyncio
async def test_settle_all_submit(client, db_session, rahul_owes_1485):
    priya, rahul, *_ = rahul_owes_1485
    resp = await client.post(
        f"/friends/{rahul.id}/settle-all",
        data={"currency": "INR", "batch_id": "batch-r1"},
        cookies=_cookie(priya.id), follow_redirects=False,
    )
    assert resp.status_code == 303 and resp.headers["location"] == "/friends"
    assert await _settlements(db_session) == 2

    again = await client.post(
        f"/friends/{rahul.id}/settle-all",
        data={"currency": "INR", "batch_id": "batch-r1"},
        cookies=_cookie(priya.id), follow_redirects=False,
    )
    assert again.status_code == 303
    assert await _settlements(db_session) == 2

    missing = await client.post(
        f"/friends/{rahul.id}/settle-all", data={"batch_id": "batch-r2"},
        cookies=_cookie(priya.id), follow_redirects=False,
    )
    assert missing.status_code == 303
    assert await _settlements(db_session) == 2


@pytest.mark.asyncio
async def test_set_pair_simplify(db_session, people):
    priya, rahul, dev = people
    assert await get_pair_simplify(db_session, priya.id, rahul.id) is True
    assert await set_pair_simplify(db_session, rahul.id, priya.id, False) is True
    await db_session.commit()
    assert await get_pair_simplify(db_session, priya.id, rahul.id) is False
    assert await get_pair_simplify(db_session, rahul.id, priya.id) is False
    # No accepted friendship: nothing to set, default reads True
    assert await set_pair_simplify(db_session, rahul.id, dev.id, False) is False
    assert await get_pair_simplify(db_session, rahul.id, dev.id) is True


@pytest.mark.asyncio
async def test_toggle_simplify(client, db_session, people):
    priya, rahul, dev = people
    resp = await client.post(
        f"/friends/{rahul.id}/simplify", cookies=_cookie(priya.id), follow_redirects=False
    )
    assert resp.status_code == 303 and resp.headers["location"] == "/friends"
    assert await get_pair_simplify(db_session, rahul.id, priya.id) is False
    await client.post(f"/friends/{priya.id}/simplify", cookies=_cookie(rahul.id))
    assert await get_pair_simplify(db_session, priya.id, rahul.id) is True


@pytest.mark.asyncio
async def test_pair_group_is_settled(db_session, rahul_owes_1485):
    priya, rahul, dev, goa, direct, seattle = rahul_owes_1485
    assert await pair_group_is_settled(db_session, priya.id, dev.id) is True  # no pair group
    assert await pair_group_is_settled(db_session, priya.id, rahul.id) is False
    await settle_all(db_session, priya.id, rahul.id, "INR", batch_id="b")
    await db_session.commit()
    assert await pair_group_is_settled(db_session, rahul.id, priya.id) is True


@pytest.mark.asyncio
async def test_remove_friend_blocked_until_direct_balance_is_zero(
    client, db_session, rahul_owes_1485
):
    priya, rahul, dev, goa, direct, seattle = rahul_owes_1485
    resp = await client.post(
        f"/friends/remove/{rahul.id}", cookies=_cookie(priya.id), follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/friends?error=settle_first&friend={rahul.id}"
    assert await is_friend(db_session, priya.id, rahul.id) is True

    await settle_all(db_session, priya.id, rahul.id, "INR", batch_id="b")
    await db_session.commit()
    resp = await client.post(
        f"/friends/remove/{rahul.id}", cookies=_cookie(priya.id), follow_redirects=False
    )
    assert resp.headers["location"] == "/friends"
    assert await is_friend(db_session, priya.id, rahul.id) is False
    assert await db_session.get(Group, direct.id) is not None  # history is kept


@pytest.mark.asyncio
async def test_new_routes_require_login_and_friendship(client, db_session, people):
    priya, rahul, dev = people
    for method, path in [
        ("post", f"/friends/{priya.id}/direct"),
        ("get", f"/friends/{priya.id}/settle-all?currency=INR"),
        ("post", f"/friends/{priya.id}/settle-all"),
        ("post", f"/friends/{priya.id}/simplify"),
    ]:
        anon = await getattr(client, method)(path, follow_redirects=False)
        assert (anon.status_code, anon.headers["location"]) == (303, "/auth/login"), path
        # Dev is logged in but not Rahul's friend
        stranger = await getattr(client, method)(
            path.replace(f"/friends/{priya.id}", f"/friends/{rahul.id}"),
            cookies=_cookie(dev.id), follow_redirects=False,
        )
        assert (stranger.status_code, stranger.headers["location"]) == (303, "/friends"), path
    assert await _settlements(db_session) == 0
    pending = (await db_session.execute(
        select(func.count()).select_from(Friendship)
    )).scalar_one()
    assert pending == 2

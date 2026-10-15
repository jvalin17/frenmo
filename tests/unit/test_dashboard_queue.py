"""Dashboard balances queue (requirements F4, mockup 'Dashboard · rails', single queue)."""
import uuid

import pytest

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.balance import order_people
from app.services.direct import find_or_create_direct_group
from app.services.friendship import ensure_friendship


def _cookie(user_id: int) -> dict:
    from app.middleware.auth import session_serializer

    return {"frenmo_session": session_serializer.dumps({"user_id": user_id})}


async def _group(db, name, currency, owner, members, group_type="other"):
    group = Group(
        name=name, created_by=owner.id, currency=currency, type=group_type,
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
async def priya_dashboard(db_session):
    """Priya's world:
    Goa Trip (INR, trip): Priya paid ₹3,000 with Rahul → Rahul owes ₹1,500;
                          Priya paid ₹1,000 with Esha → Esha owes ₹500.
    Pair group with Rahul (USD, Rahul created it): Priya paid $60 → Rahul owes $30.
    Seattle Flat (USD, home): Rahul paid $90 → Priya owes $45.
    Dev is a friend with nothing shared.
    Rahul's USD net for Priya: +30 − 45 = −15 (you owe $15.00)."""
    priya = User(
        name="Priya Nair", email=f"priya.{uuid.uuid4().hex[:6]}@example.com",
        password_hash="h", default_currency="INR",
    )
    rahul = User(
        name="Rahul Verma", email=f"rahul.{uuid.uuid4().hex[:6]}@example.com",
        password_hash="h", default_currency="USD",
    )
    esha = User(
        name="Esha Rao", email=f"esha.{uuid.uuid4().hex[:6]}@example.com", password_hash="h"
    )
    dev = User(name="Dev Patel", email=f"dev.{uuid.uuid4().hex[:6]}@example.com", password_hash="h")
    db_session.add_all([priya, rahul, esha, dev])
    await db_session.flush()
    for friend in (rahul, esha, dev):
        await ensure_friendship(db_session, priya.id, friend.id)

    goa = await _group(db_session, "Goa Trip", "INR", priya, [priya, rahul, esha], "trip")
    await _equal_expense(db_session, goa, "Villa", 300000, priya, rahul)
    await _equal_expense(db_session, goa, "Scooter", 100000, priya, esha)
    direct = await find_or_create_direct_group(db_session, rahul.id, priya.id)  # USD
    await _equal_expense(db_session, direct, "Lunch", 6000, priya, rahul)
    seattle = await _group(db_session, "Seattle Flat", "USD", rahul, [priya, rahul], "home")
    await _equal_expense(db_session, seattle, "Groceries", 9000, rahul, priya)
    await db_session.commit()
    return priya, rahul, esha, dev, goa, direct, seattle


def _queue(html: str) -> str:
    start = html.index('data-rail="balances"')
    return html[start:html.index('data-rail="groups"')]


def test_order_people():
    names = {2: "Rahul Verma", 5: "Esha Rao", 9: "Aarav Shah", 7: "Zoya Khan"}
    people = {
        2: {"INR": 150000, "USD": -1500},  # you owe him something → first
        5: {"INR": 50000},
        9: {"EUR": -700},                  # you owe → first block, by name
        7: {"USD": 1200},
    }
    assert order_people(people, names) == [9, 2, 5, 7]
    assert order_people({}, names) == []


@pytest.mark.asyncio
async def test_queue_one_card_per_person_you_owe_first(client, db_session, priya_dashboard):
    priya, rahul, esha, dev, *_ = priya_dashboard
    html = (await client.get("/", cookies=_cookie(priya.id))).text
    queue = _queue(html)
    assert queue.count("Rahul Verma") == 1 and queue.count("Esha Rao") == 1
    assert "Dev Patel" not in queue  # settled people get no card
    assert queue.index("Rahul Verma") < queue.index("Esha Rao")
    rahul_card = queue[queue.index("Rahul Verma"):queue.index("Esha Rao")]
    assert "you owe $15.00" in rahul_card and "owes you ₹1500.00" in rahul_card
    assert "owes you ₹500.00" in queue[queue.index("Esha Rao"):]
    assert "That's everyone" in queue and "Settled with 1 other" in queue


@pytest.mark.asyncio
async def test_card_actions(client, db_session, priya_dashboard):
    priya, rahul, esha, dev, *_ = priya_dashboard
    queue = _queue((await client.get("/", cookies=_cookie(priya.id))).text)
    rahul_link = f'href="/friends/#friend-{rahul.id}"'
    esha_link = f'href="/friends/#friend-{esha.id}"'
    assert rahul_link in queue and esha_link in queue  # the whole card is the link
    rahul_card = queue[queue.index(rahul_link):queue.index(esha_link)]
    esha_card = queue[queue.index(esha_link):queue.index("That's everyone")]
    assert "Pay $15.00" in rahul_card and "Remind" not in rahul_card
    assert "Remind" in esha_card and "Pay " not in esha_card


@pytest.mark.asyncio
async def test_groups_rail_hides_pair_group_but_totals_include_it(
    client, db_session, priya_dashboard
):
    priya, rahul, esha, dev, goa, direct, seattle = priya_dashboard
    html = (await client.get("/", cookies=_cookie(priya.id))).text
    rail = html[html.index('data-rail="groups"'):]
    assert "Goa Trip" in rail and "Seattle Flat" in rail and "New group" in rail
    assert f'href="/groups/{direct.id}"' not in rail
    assert "Priya Nair &amp; Rahul Verma" not in html and "You &amp; Rahul" not in html
    # Without the pair group's +$30 the USD line would read $45.00; with it, $15.00
    assert "you owe $15.00" in html and "you owe $45.00" not in _queue(html)
    assert "gets back ₹2000.00" in rail and "owes $45.00" in rail


@pytest.mark.asyncio
async def test_totals_per_currency(client, db_session, priya_dashboard):
    priya, *_ = priya_dashboard
    html = (await client.get("/", cookies=_cookie(priya.id))).text
    assert "+₹2000.00" in html and "−$15.00" in html
    assert "1985" not in html and "2015" not in html  # never ₹2000 ± $15
    assert "2 currencies" in html


@pytest.mark.asyncio
async def test_all_settled_dashboard(client, db_session, priya_dashboard):
    priya, rahul, esha, dev, goa, direct, seattle = priya_dashboard
    html = (await client.get("/", cookies=_cookie(dev.id))).text
    assert "All settled up" in html
    assert "Pay " not in _queue(html) and "Remind" not in _queue(html)
    assert "That's everyone" in _queue(html)
    assert "New group" in html

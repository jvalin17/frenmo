"""Friends page controls for direct expenses (requirements F2, mockup 'Friends page')."""
import uuid

import pytest

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.balance import shared_group_balances
from app.services.direct import find_or_create_direct_group
from app.services.friendship import ensure_friendship, set_pair_simplify


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


@pytest.fixture
async def scenario(db_session):
    """Priya ↔ Rahul: Goa Trip (INR) Rahul owes ₹1,500; pair group (INR) Priya owes ₹15;
    Seattle Flat (USD) Priya owes $45. Esha is a friend with nothing shared."""
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
    db_session.add_all([priya, rahul, esha])
    await db_session.flush()
    await ensure_friendship(db_session, priya.id, rahul.id)
    await ensure_friendship(db_session, priya.id, esha.id)
    goa = await _group(db_session, "Goa Trip", "INR", priya, [priya, rahul])
    await _equal_expense(db_session, goa, "Villa", 300000, priya, rahul)
    direct = await find_or_create_direct_group(db_session, priya.id, rahul.id)
    await _equal_expense(db_session, direct, "Chai", 3000, rahul, priya)
    seattle = await _group(db_session, "Seattle Flat", "USD", rahul, [priya, rahul])
    await _equal_expense(db_session, seattle, "Groceries", 9000, rahul, priya)
    await db_session.commit()
    return priya, rahul, esha, goa, direct, seattle


def _form(html: str, action: str) -> str:
    """The <form ...> element whose action is `action`, up to its </form>."""
    marker = f'action="{action}"'
    assert marker in html, f"no form posting to {action}"
    start = html.rfind("<form", 0, html.index(marker))
    return html[start:html.index("</form>", start)]


@pytest.mark.asyncio
async def test_shared_group_rows_carry_group_type(db_session, scenario):
    priya, rahul, esha, goa, direct, seattle = scenario
    rows = await shared_group_balances(db_session, priya.id, rahul.id)
    assert {r["group_id"]: r["type"] for r in rows} == {
        goa.id: "other", direct.id: "direct", seattle.id: "other",
    }


@pytest.mark.asyncio
async def test_friend_card_has_add_expense_and_direct_history(client, db_session, scenario):
    priya, rahul, esha, goa, direct, seattle = scenario
    page = await client.get("/friends/", cookies=_cookie(priya.id))
    assert page.status_code == 200
    html = page.text
    assert "Add expense" in _form(html, f"/friends/{rahul.id}/direct")
    assert f'href="/groups/{direct.id}"' in html and "Direct history" in html
    # Esha shares nothing yet: Add expense is there, Direct history is not
    assert f'action="/friends/{esha.id}/direct"' in html
    esha_card = html[html.index(f'id="friend-{esha.id}"'):]
    assert "Direct history" not in esha_card.split("Remove friend")[0]


@pytest.mark.asyncio
async def test_per_group_settle_buttons_post_to_their_own_group(client, db_session, scenario):
    priya, rahul, esha, goa, direct, seattle = scenario
    html = (await client.get("/friends/", cookies=_cookie(priya.id))).text

    goa_form = _form(html, f"/settlements/new/{goa.id}")
    assert "Record ₹1500.00 received" in goa_form
    assert f'name="from_user" value="{rahul.id}"' in goa_form
    assert f'name="to_user" value="{priya.id}"' in goa_form
    assert 'name="amount" value="1500.00"' in goa_form

    direct_form = _form(html, f"/settlements/new/{direct.id}")
    assert "Pay ₹15.00" in direct_form
    assert f'name="from_user" value="{priya.id}"' in direct_form
    assert f'name="to_user" value="{rahul.id}"' in direct_form
    assert 'name="amount" value="15.00"' in direct_form
    assert "Direct" in html and "just you two" in html

    seattle_form = _form(html, f"/settlements/new/{seattle.id}")
    assert "Pay $45.00" in seattle_form


@pytest.mark.asyncio
async def test_simplify_on_shows_net_per_currency_with_settle_all(client, db_session, scenario):
    priya, rahul, esha, goa, direct, seattle = scenario
    html = (await client.get("/friends/", cookies=_cookie(priya.id))).text
    assert "Simplify is on" in html
    assert "Rahul Verma owes you ₹1485.00" in html
    assert f'href="/friends/{rahul.id}/settle-all?currency=INR"' in html
    assert "You owe Rahul Verma $45.00" in html
    assert f'href="/friends/{rahul.id}/settle-all?currency=USD"' in html
    assert "1440" not in html  # ₹1485 − $45 must never be computed
    # Esha: nothing shared, no net line, no settle-all link
    assert f"/friends/{esha.id}/settle-all" not in html


@pytest.mark.asyncio
async def test_simplify_off_hides_net_line(client, db_session, scenario):
    priya, rahul, esha, goa, direct, seattle = scenario
    await set_pair_simplify(db_session, priya.id, rahul.id, False)
    await db_session.commit()
    html = (await client.get("/friends/", cookies=_cookie(priya.id))).text
    toggle = _form(html, f"/friends/{rahul.id}/simplify")
    assert "Simplify is off" in toggle
    assert f"/friends/{rahul.id}/settle-all" not in html
    assert "owes you ₹1485.00" not in html.split("Payment History")[0].split("By Group")[1]
    # Per-group controls are still the way to settle
    assert "Record ₹1500.00 received" in html and "Pay ₹15.00" in html


@pytest.mark.asyncio
async def test_settle_first_message(client, db_session, scenario):
    priya, rahul, *_ = scenario
    html = (await client.get(
        "/friends/", params={"error": "settle_first", "friend": rahul.id}, cookies=_cookie(priya.id)
    )).text
    assert "Settle up with Rahul Verma first" in html
    plain = (await client.get("/friends/", cookies=_cookie(priya.id))).text
    assert "Settle up with" not in plain


@pytest.mark.asyncio
async def test_settle_all_page_markup(client, db_session, scenario):
    priya, rahul, *_ = scenario
    html = (await client.get(
        f"/friends/{rahul.id}/settle-all", params={"currency": "INR"}, cookies=_cookie(priya.id)
    )).text
    assert "Settle all with Rahul Verma" in html
    assert 'class="btn btn-primary btn-block"' in html  # 44px primary, full width
    assert "Record 2 payments" in html
    assert "Rahul Verma pays you" in html and "₹1485.00" in html

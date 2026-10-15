"""The group page for a hidden pair group (requirements F3, mockup 'Pair group page')."""
import uuid

import pytest

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.direct import find_or_create_direct_group
from app.services.friendship import ensure_friendship


def _cookie(user_id: int) -> dict:
    from app.middleware.auth import session_serializer

    return {"frenmo_session": session_serializer.dumps({"user_id": user_id})}


@pytest.fixture
async def pages(db_session):
    """Priya ↔ Rahul pair group (INR) with one expense; Goa Trip as an ordinary group.
    Esha is Priya's friend and not in Goa Trip, so 'Add Friends' has someone to offer."""
    priya = User(
        name="Priya Nair", email=f"priya.{uuid.uuid4().hex[:6]}@example.com",
        password_hash="h", default_currency="INR",
    )
    rahul = User(
        name="Rahul Verma", email=f"rahul.{uuid.uuid4().hex[:6]}@example.com", password_hash="h"
    )
    esha = User(
        name="Esha Rao", email=f"esha.{uuid.uuid4().hex[:6]}@example.com", password_hash="h"
    )
    db_session.add_all([priya, rahul, esha])
    await db_session.flush()
    await ensure_friendship(db_session, priya.id, rahul.id)
    await ensure_friendship(db_session, priya.id, esha.id)

    direct = await find_or_create_direct_group(db_session, priya.id, rahul.id)
    chai = Expense(
        group_id=direct.id, description="Chai at the station", amount=3000, split_type="equal",
        paid_by=rahul.id, created_by=rahul.id, currency="INR",
    )
    db_session.add(chai)
    await db_session.flush()
    db_session.add_all([
        ExpenseSplit(expense_id=chai.id, user_id=rahul.id, paid_amount=3000, owed_amount=1500),
        ExpenseSplit(expense_id=chai.id, user_id=priya.id, paid_amount=0, owed_amount=1500),
    ])

    goa = Group(
        name="Goa Trip", created_by=priya.id, currency="INR", type="trip",
        invite_token=f"tok_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(goa)
    await db_session.flush()
    db_session.add_all([GroupMember(group_id=goa.id, user_id=u.id) for u in (priya, rahul)])
    await db_session.commit()
    return priya, rahul, esha, direct, goa


@pytest.mark.asyncio
async def test_pair_group_page_title_is_viewer_relative(client, db_session, pages):
    priya, rahul, esha, direct, goa = pages
    priya_view = (await client.get(f"/groups/{direct.id}", cookies=_cookie(priya.id))).text
    assert "You &amp; Rahul Verma" in priya_view
    assert "Priya Nair &amp; Rahul Verma" not in priya_view  # stored name is not shown
    assert ">Direct<" in priya_view
    assert "Just the two of you · INR" in priya_view

    rahul_view = (await client.get(f"/groups/{direct.id}", cookies=_cookie(rahul.id))).text
    assert "You &amp; Priya Nair" in rahul_view


@pytest.mark.asyncio
async def test_pair_group_page_hides_membership_and_shares_controls(client, db_session, pages):
    priya, rahul, esha, direct, goa = pages
    html = (await client.get(f"/groups/{direct.id}", cookies=_cookie(priya.id))).text
    assert f'href="/groups/{direct.id}/invite"' not in html
    assert "Add Friends" not in html and "/friends/add-to-group/" not in html
    for field in ('name="name"', 'name="shares_', 'name="kid_count_',
                  'name="kid_friendly"', 'name="default_split_ways"'):
        assert field not in html, field
    # Currency is the one setting left, posted to the same settings route
    assert f'action="/groups/{direct.id}/settings"' in html and 'name="currency"' in html
    assert "recalculate expenses" not in html  # no shares confirm dialog


@pytest.mark.asyncio
async def test_ordinary_group_page_unchanged(client, db_session, pages):
    priya, rahul, esha, direct, goa = pages
    html = (await client.get(f"/groups/{goa.id}", cookies=_cookie(priya.id))).text
    assert "Goa Trip" in html and ">Direct<" not in html
    assert f'href="/groups/{goa.id}/invite"' in html
    assert "Add Friends" in html and f"/friends/add-to-group/{goa.id}/{esha.id}" in html
    for field in ('name="name"', f'name="shares_{priya.id}"', 'name="kid_friendly"',
                  'name="default_split_ways"', 'name="currency"'):
        assert field in html, field


@pytest.mark.asyncio
async def test_pair_group_page_keeps_expenses_and_settle_up(client, db_session, pages):
    priya, rahul, esha, direct, goa = pages
    html = (await client.get(f"/groups/{direct.id}", cookies=_cookie(priya.id))).text
    assert "Chai at the station" in html
    assert f'href="/expenses/new/{direct.id}"' in html
    assert "Settle Up" in html and f'action="/settlements/new/{direct.id}"' in html
    assert "nobody else can be added" in html

"""A pair group never gains members and only its currency can change (AD-6)."""
import uuid

import pytest
from sqlalchemy import func, select

from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.direct import find_or_create_direct_group
from app.services.friendship import ensure_friendship


def _cookie(user_id: int) -> dict:
    from app.middleware.auth import session_serializer

    return {"frenmo_session": session_serializer.dumps({"user_id": user_id})}


@pytest.fixture
async def pair(db_session):
    priya = User(
        name="Priya Nair", email=f"priya.{uuid.uuid4().hex[:6]}@example.com",
        password_hash="h", default_currency="INR",
    )
    rahul = User(
        name="Rahul Verma", email=f"rahul.{uuid.uuid4().hex[:6]}@example.com", password_hash="h"
    )
    dev = User(name="Dev Patel", email=f"dev.{uuid.uuid4().hex[:6]}@example.com", password_hash="h")
    db_session.add_all([priya, rahul, dev])
    await db_session.flush()
    await ensure_friendship(db_session, priya.id, rahul.id)
    await ensure_friendship(db_session, priya.id, dev.id)
    group = await find_or_create_direct_group(db_session, priya.id, rahul.id)
    await db_session.commit()
    return priya, rahul, dev, group


async def _members(db, group_id):
    return (await db.execute(
        select(func.count()).select_from(GroupMember).where(GroupMember.group_id == group_id)
    )).scalar_one()


@pytest.mark.asyncio
async def test_pair_group_cannot_gain_members(client, db_session, pair):
    priya, rahul, dev, group = pair

    invite = await client.get(
        f"/groups/{group.id}/invite", cookies=_cookie(priya.id), follow_redirects=False
    )
    assert (invite.status_code, invite.headers["location"]) == (303, "/")

    confirm = await client.get(
        f"/groups/join/{group.invite_token}", cookies=_cookie(dev.id), follow_redirects=False
    )
    assert (confirm.status_code, confirm.headers["location"]) == (303, "/")

    join = await client.post(
        f"/groups/join/{group.invite_token}", cookies=_cookie(dev.id), follow_redirects=False
    )
    assert (join.status_code, join.headers["location"]) == (303, "/")

    add = await client.post(
        f"/friends/add-to-group/{group.id}/{dev.id}", cookies=_cookie(priya.id),
        follow_redirects=False,
    )
    assert add.status_code == 303
    assert await _members(db_session, group.id) == 2


@pytest.mark.asyncio
async def test_pair_group_settings_only_change_currency(client, db_session, pair):
    priya, rahul, dev, group = pair
    resp = await client.post(
        f"/groups/{group.id}/settings",
        data={
            "name": "Hijacked", "currency": "USD", "kid_friendly": "on",
            "default_split_ways": "5", f"shares_{priya.id}": "3", f"kid_count_{priya.id}": "2",
        },
        cookies=_cookie(priya.id), follow_redirects=False,
    )
    assert resp.status_code == 303
    fresh = (await db_session.execute(
        select(Group).where(Group.id == group.id).execution_options(populate_existing=True)
    )).scalar_one()
    assert fresh.currency == "USD"
    assert fresh.name == "Priya Nair & Rahul Verma"
    assert fresh.kid_friendly is False and fresh.default_split_ways is None
    member = (await db_session.execute(
        select(GroupMember)
        .where(GroupMember.group_id == group.id, GroupMember.user_id == priya.id)
        .execution_options(populate_existing=True)
    )).scalar_one()
    assert (member.default_shares, member.kid_count) == (1, 0)

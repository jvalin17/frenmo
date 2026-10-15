"""Hidden per-pair "direct" groups (requirements/direct-expenses.md F1, AD-1)."""
import uuid

import pytest
from sqlalchemy import func, select, text

from app.models.friendship import Friendship
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services import direct
from app.services.direct import (
    find_or_create_direct_group,
    is_direct,
    lookup_direct_group,
    pair_key_for,
)
from app.services.friendship import ensure_friendship, send_friend_request


@pytest.fixture
async def friends(db_session):
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
    await db_session.commit()
    return priya, rahul, dev


async def _count(db, model, **where):
    stmt = select(func.count()).select_from(model)
    for col, val in where.items():
        stmt = stmt.where(getattr(model, col) == val)
    return (await db.execute(stmt)).scalar_one()


def test_pair_key_for():
    assert pair_key_for(2, 9) == "2:9"
    assert pair_key_for(9, 2) == "2:9"
    assert pair_key_for(10, 10) == "10:10"


def test_is_direct():
    assert is_direct(Group(name="Priya Nair & Rahul Verma", type="direct", created_by=1))
    assert not is_direct(Group(name="Goa Trip", type="trip", created_by=1))
    assert not is_direct(None)


@pytest.mark.asyncio
async def test_lookup_direct_group(db_session, friends):
    priya, rahul, _ = friends
    assert await lookup_direct_group(db_session, pair_key_for(priya.id, rahul.id)) is None
    created = await find_or_create_direct_group(db_session, priya.id, rahul.id)
    await db_session.commit()
    found = await lookup_direct_group(db_session, pair_key_for(rahul.id, priya.id))
    assert found is not None and found.id == created.id


@pytest.mark.asyncio
async def test_find_or_create_direct_group(db_session, friends):
    priya, rahul, _ = friends
    group = await find_or_create_direct_group(db_session, rahul.id, priya.id)
    await db_session.commit()

    assert group.type == "direct"
    assert group.pair_key == f"{priya.id}:{rahul.id}"
    assert group.name == "Priya Nair & Rahul Verma"  # by id order, not by who clicked
    assert group.currency == "USD"  # Rahul created it: his default currency
    assert group.created_by == rahul.id
    members = (await db_session.execute(
        select(GroupMember.user_id).where(GroupMember.group_id == group.id)
    )).scalars().all()
    assert sorted(members) == [priya.id, rahul.id]

    # The other direction and a repeat call find the same group and create nothing
    again = await find_or_create_direct_group(db_session, priya.id, rahul.id)
    await db_session.commit()
    assert again.id == group.id
    assert await _count(db_session, Group, type="direct") == 1
    assert await _count(db_session, GroupMember, group_id=group.id) == 2


@pytest.mark.asyncio
async def test_non_friends_cannot_open_a_pair_group(db_session, friends):
    priya, rahul, dev = friends
    # No friendship row at all
    assert await find_or_create_direct_group(db_session, priya.id, dev.id) is None
    # Pending request is not a friendship
    await send_friend_request(db_session, dev.id, rahul.id)
    assert await find_or_create_direct_group(db_session, rahul.id, dev.id) is None
    # Self
    assert await find_or_create_direct_group(db_session, priya.id, priya.id) is None
    assert await _count(db_session, Group, type="direct") == 0


@pytest.mark.asyncio
async def test_concurrent_first_calls_create_one_pair_group(db_session, friends, monkeypatch):
    """Two requests both miss the lookup, both insert; the second insert hits the
    unique pair_key, does nothing, and re-selects the winner's group."""
    priya, rahul, _ = friends
    winner = await find_or_create_direct_group(db_session, priya.id, rahul.id)
    await db_session.commit()

    real_lookup = direct.lookup_direct_group
    calls = {"n": 0}

    async def stale_then_real(db, key):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # the loser's lookup ran before the winner committed
        return await real_lookup(db, key)

    monkeypatch.setattr(direct, "lookup_direct_group", stale_then_real)
    loser = await find_or_create_direct_group(db_session, rahul.id, priya.id)
    await db_session.commit()

    assert loser.id == winner.id
    assert await _count(db_session, Group, type="direct") == 1
    assert await _count(db_session, GroupMember, group_id=winner.id) == 2


@pytest.mark.asyncio
async def test_friendship_simplify_defaults_true(db_session, friends):
    priya, rahul, _ = friends
    row = (await db_session.execute(
        select(Friendship).where(Friendship.user_id == priya.id, Friendship.friend_id == rahul.id)
    )).scalar_one()
    assert row.simplify is True


class TestStartupMigration:
    @pytest.mark.asyncio
    async def test_startup_migration_adds_pair_key_index(self):
        """A database created before this feature has neither groups.pair_key nor
        friendships.simplify. migrate_schema must add the column, the unique index,
        and give existing friendship rows simplify = true."""
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.database import Base, migrate_schema

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            def seed(sync_conn):
                from sqlalchemy.orm import Session

                with Session(bind=sync_conn) as session:
                    maria = User(
                        name="Maria Garcia", email="maria.garcia@example.com", password_hash="h"
                    )
                    omar = User(
                        name="Omar Haddad", email="omar.haddad@example.com", password_hash="h"
                    )
                    session.add_all([maria, omar])
                    session.flush()
                    session.add(
                        Group(name="Old Flat", created_by=maria.id, invite_token="tok_legacy1")
                    )
                    session.add(
                        Friendship(user_id=maria.id, friend_id=omar.id, status="accepted")
                    )
                    session.commit()

            await conn.run_sync(seed)
            await conn.execute(text("DROP INDEX ux_groups_pair_key"))
            await conn.execute(text("ALTER TABLE groups DROP COLUMN pair_key"))
            await conn.execute(text("ALTER TABLE friendships DROP COLUMN simplify"))
            await conn.run_sync(migrate_schema)

            table_info = (await conn.execute(text("PRAGMA table_info(groups)"))).all()
            index_list = (await conn.execute(text("PRAGMA index_list(groups)"))).all()
            columns = {row[1] for row in table_info}
            indexes = {(row[1], row[2]) for row in index_list}
            simplify = (
                await conn.execute(text("SELECT simplify FROM friendships WHERE id = 1"))
            ).scalar()
            # Unique index must still allow many NULL pair_keys (every ordinary group)
            await conn.execute(text(
                "INSERT INTO groups "
                "(name, type, created_by, invite_token, currency, kid_friendly, created_at) "
                "VALUES ('Second Flat', 'home', 1, 'tok_legacy2', 'USD', 0, '2026-01-01')"
            ))
        await engine.dispose()
        assert "pair_key" in columns
        assert ("ux_groups_pair_key", 1) in indexes  # (name, unique)
        assert simplify == 1

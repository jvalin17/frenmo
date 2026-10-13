"""ensure_group_friendships must not issue one query per member pair.

The group detail page calls it on every load, so for M members it was
M*(M-1)/2 SELECTs plus INSERTs. It should load the existing pairs once and
insert only the missing ones.
"""
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import event, func, select

from app.models.friendship import Friendship
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.friendship import ensure_group_friendships, send_friend_request
from tests.conftest import test_engine


@contextmanager
def count_statements():
    """Count SQL statements executed on the test engine while the block runs."""
    counter = {"n": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(test_engine.sync_engine, "before_cursor_execute", _count)
    try:
        yield counter
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", _count)


async def _group_of(db, size: int, label: str) -> tuple[Group, list[User]]:
    users = [
        User(
            name=f"{label} member {i}",
            email=f"{label.lower()}.member{i}@example.com",
            password_hash="h",
        )
        for i in range(size)
    ]
    db.add_all(users)
    await db.flush()
    group = Group(
        name=f"{label} Flat", created_by=users[0].id, invite_token=f"tok_{uuid.uuid4().hex[:8]}"
    )
    db.add(group)
    await db.flush()
    db.add_all([GroupMember(group_id=group.id, user_id=u.id) for u in users])
    await db.commit()
    return group, users


async def _friendship_count(db, user_ids: list[int]) -> int:
    return await db.scalar(
        select(func.count()).select_from(Friendship).where(
            Friendship.user_id.in_(user_ids), Friendship.friend_id.in_(user_ids)
        )
    )


class TestEnsureGroupFriendshipsIsBulk:
    @pytest.mark.asyncio
    async def test_statement_count_does_not_grow_with_members(self, db_session):
        small, _ = await _group_of(db_session, 3, "Goa")
        large, large_users = await _group_of(db_session, 8, "Seattle")

        with count_statements() as small_count:
            created_small = await ensure_group_friendships(db_session, small.id)
        await db_session.commit()
        with count_statements() as large_count:
            created_large = await ensure_group_friendships(db_session, large.id)
        await db_session.commit()

        assert created_small == 3
        assert created_large == 28
        assert await _friendship_count(db_session, [u.id for u in large_users]) == 28
        assert large_count["n"] == small_count["n"], (
            f"3 members used {small_count['n']} statements, 8 members used {large_count['n']}; "
            "the repair must not scale with the number of member pairs"
        )
        assert large_count["n"] <= 4

    @pytest.mark.asyncio
    async def test_second_run_creates_nothing_and_stays_cheap(self, db_session):
        group, _ = await _group_of(db_session, 6, "Lisbon")
        await ensure_group_friendships(db_session, group.id)
        await db_session.commit()

        with count_statements() as counter:
            created = await ensure_group_friendships(db_session, group.id)
        assert created == 0
        assert counter["n"] <= 2  # members + existing pairs, no inserts

    @pytest.mark.asyncio
    async def test_pending_request_between_members_is_left_alone(self, db_session):
        group, users = await _group_of(db_session, 3, "Berlin")
        a, b, c = users
        await send_friend_request(db_session, from_user_id=b.id, to_user_id=a.id)

        created = await ensure_group_friendships(db_session, group.id)
        await db_session.commit()

        assert created == 2  # a-c and b-c; a-b already has a (pending) row
        rows = (await db_session.execute(
            select(Friendship.user_id, Friendship.friend_id, Friendship.status).where(
                Friendship.user_id.in_([a.id, b.id]), Friendship.friend_id.in_([a.id, b.id])
            )
        )).all()
        assert rows == [(b.id, a.id, "pending")]


class TestConcurrentRepairsDoNotCollide:
    """Two members loading the page at once can compute the same missing pairs.

    The batch INSERT must skip rows another request already inserted instead
    of failing the whole request on the unique constraint.
    """

    @pytest.mark.parametrize("dialect_name", ["sqlite", "postgresql"])
    def test_missing_friendships_insert(self, dialect_name):
        from sqlalchemy.dialects import postgresql, sqlite

        from app.services.friendship import missing_friendships_insert

        dialect = {"sqlite": sqlite.dialect(), "postgresql": postgresql.dialect()}[dialect_name]
        stmt = missing_friendships_insert(dialect_name)
        sql = str(stmt.compile(dialect=dialect))
        assert "ON CONFLICT" in sql and "DO NOTHING" in sql, sql

    @pytest.mark.asyncio
    async def test_pairs_are_stored_in_canonical_direction(self, db_session):
        """user_id < friend_id on every repaired row, so the unique constraint sees duplicates."""
        group, users = await _group_of(db_session, 5, "Oslo")
        await ensure_group_friendships(db_session, group.id)
        await db_session.commit()
        ids = [u.id for u in users]
        rows = (await db_session.execute(
            select(Friendship.user_id, Friendship.friend_id).where(
                Friendship.user_id.in_(ids), Friendship.friend_id.in_(ids)
            )
        )).all()
        assert len(rows) == 10
        assert all(user_id < friend_id for user_id, friend_id in rows), rows

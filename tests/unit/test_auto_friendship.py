"""Tests for auto-friendship on group join."""
import uuid

import pytest
from sqlalchemy import select

from app.models.friendship import Friendship
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.friendship import ensure_friendship, get_friend_list


@pytest.fixture
async def three_users(db_session):
    alice = User(name="Alice", email="alice@auto.com", password_hash="x")
    bob = User(name="Bob", email="bob@auto.com", password_hash="x")
    charlie = User(name="Charlie", email="charlie@auto.com", password_hash="x")
    db_session.add_all([alice, bob, charlie])
    await db_session.commit()
    return alice, bob, charlie


@pytest.fixture
async def group_with_two(db_session, three_users):
    """Group with Alice and Bob. Charlie will join later."""
    alice, bob, charlie = three_users
    group = Group(
        name="Trip", created_by=alice.id,
        invite_token=f"tok_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(group)
    await db_session.flush()
    db_session.add(GroupMember(group_id=group.id, user_id=alice.id))
    db_session.add(GroupMember(group_id=group.id, user_id=bob.id))
    await db_session.commit()
    return alice, bob, charlie, group


class TestEnsureFriendship:

    @pytest.mark.asyncio
    async def test_ensure_friendship_creates_accepted(self, db_session, three_users):
        """ensure_friendship creates an accepted friendship if none exists."""
        alice, bob, _ = three_users
        result = await ensure_friendship(db_session, alice.id, bob.id)
        assert result is True

        friends = await get_friend_list(db_session, alice.id)
        friend_ids = {f.id for f in friends}
        assert bob.id in friend_ids

    @pytest.mark.asyncio
    async def test_ensure_friendship_skips_existing(self, db_session, three_users):
        """ensure_friendship is idempotent — skips if friendship exists."""
        alice, bob, _ = three_users
        await ensure_friendship(db_session, alice.id, bob.id)
        # Call again — should not raise or create duplicate
        result = await ensure_friendship(db_session, alice.id, bob.id)
        assert result is False  # already exists

        # Should still be exactly one friendship
        friendships = (await db_session.execute(
            select(Friendship).where(
                Friendship.user_id == alice.id, Friendship.friend_id == bob.id
            )
        )).scalars().all()
        assert len(friendships) == 1

    @pytest.mark.asyncio
    async def test_ensure_friendship_skips_self(self, db_session, three_users):
        """ensure_friendship returns False for self-friendship."""
        alice, _, _ = three_users
        result = await ensure_friendship(db_session, alice.id, alice.id)
        assert result is False

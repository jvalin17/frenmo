"""Tests for security fixes: friendship verification and join_group POST."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.friendship import Friendship
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.friendship import is_friend


@pytest.fixture
async def users_and_group(db_session: AsyncSession):
    """Alice owns a group. Bob is a friend. Charlie is a stranger."""
    alice = User(email="alice@example.com", name="Alice", password_hash="h")
    bob = User(email="bob@example.com", name="Bob", password_hash="h")
    charlie = User(email="charlie@example.com", name="Charlie", password_hash="h")
    db_session.add_all([alice, bob, charlie])
    await db_session.flush()

    group = Group(name="Trip", created_by=alice.id, invite_token=f"tok_{uuid.uuid4().hex[:8]}")
    db_session.add(group)
    await db_session.flush()

    db_session.add(GroupMember(group_id=group.id, user_id=alice.id))

    # Alice and Bob are accepted friends
    db_session.add(Friendship(user_id=alice.id, friend_id=bob.id, status="accepted"))
    await db_session.commit()

    return group, alice, bob, charlie


class TestIsFriend:

    async def test_accepted_friendship_returns_true(self, db_session, users_and_group):
        """Accepted friends should return True."""
        _, alice, bob, _ = users_and_group
        assert await is_friend(db_session, alice.id, bob.id) is True

    async def test_accepted_friendship_bidirectional(self, db_session, users_and_group):
        """is_friend should work regardless of who sent the request."""
        _, alice, bob, _ = users_and_group
        # Bob checking if Alice is friend (reverse direction)
        assert await is_friend(db_session, bob.id, alice.id) is True

    async def test_stranger_returns_false(self, db_session, users_and_group):
        """Non-friends should return False."""
        _, alice, _, charlie = users_and_group
        assert await is_friend(db_session, alice.id, charlie.id) is False

    async def test_pending_friendship_returns_false(self, db_session, users_and_group):
        """Pending (not accepted) friendship should return False."""
        _, alice, _, charlie = users_and_group
        db_session.add(Friendship(user_id=alice.id, friend_id=charlie.id, status="pending"))
        await db_session.commit()
        assert await is_friend(db_session, alice.id, charlie.id) is False

    async def test_self_returns_false(self, db_session, users_and_group):
        """Checking friendship with self should return False."""
        _, alice, _, _ = users_and_group
        assert await is_friend(db_session, alice.id, alice.id) is False


class TestAddFriendToGroupSecurity:

    async def test_route_rejects_non_friend(self, client, db_session, users_and_group):
        """POST add-to-group with a non-friend should not add them."""
        group, alice, bob, charlie = users_and_group

        # Create a session cookie for alice
        from app.middleware.auth import session_serializer
        session_data = session_serializer.dumps({"user_id": alice.id})

        resp = await client.post(
            f"/friends/add-to-group/{group.id}/{charlie.id}",
            cookies={"frenmo_session": session_data},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Charlie should NOT be a group member
        result = await db_session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group.id,
                GroupMember.user_id == charlie.id,
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_route_accepts_real_friend(self, client, db_session, users_and_group):
        """POST add-to-group with an accepted friend should add them."""
        group, alice, bob, charlie = users_and_group

        from app.middleware.auth import session_serializer
        session_data = session_serializer.dumps({"user_id": alice.id})

        resp = await client.post(
            f"/friends/add-to-group/{group.id}/{bob.id}",
            cookies={"frenmo_session": session_data},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Bob SHOULD be a group member
        result = await db_session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group.id,
                GroupMember.user_id == bob.id,
            )
        )
        assert result.scalar_one_or_none() is not None


class TestJoinGroupSecurity:

    async def test_get_shows_confirmation_page(self, client, db_session, users_and_group):
        """GET /groups/join/{token} should show confirmation, not auto-join."""
        group, alice, bob, charlie = users_and_group

        from app.middleware.auth import session_serializer
        session_data = session_serializer.dumps({"user_id": bob.id})

        resp = await client.get(
            f"/groups/join/{group.invite_token}",
            cookies={"frenmo_session": session_data},
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "Join Group" in resp.text

        # Bob should NOT be a member yet (just viewing confirmation)
        result = await db_session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group.id,
                GroupMember.user_id == bob.id,
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_post_actually_joins(self, client, db_session, users_and_group):
        """POST /groups/join/{token} should add the user to the group."""
        group, alice, bob, charlie = users_and_group

        from app.middleware.auth import session_serializer
        session_data = session_serializer.dumps({"user_id": bob.id})

        resp = await client.post(
            f"/groups/join/{group.invite_token}",
            cookies={"frenmo_session": session_data},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Bob SHOULD be a member now
        result = await db_session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group.id,
                GroupMember.user_id == bob.id,
            )
        )
        assert result.scalar_one_or_none() is not None

    async def test_get_invalid_token_redirects(self, client, db_session, users_and_group):
        """Invalid invite token should redirect to home."""
        _, _, bob, _ = users_and_group

        from app.middleware.auth import session_serializer
        session_data = session_serializer.dumps({"user_id": bob.id})

        resp = await client.get(
            "/groups/join/invalid_token_xyz",
            cookies={"frenmo_session": session_data},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    async def test_get_already_member_redirects(self, client, db_session, users_and_group):
        """Already a member should redirect to group, not show confirmation."""
        group, alice, _, _ = users_and_group

        from app.middleware.auth import session_serializer
        session_data = session_serializer.dumps({"user_id": alice.id})

        resp = await client.get(
            f"/groups/join/{group.invite_token}",
            cookies={"frenmo_session": session_data},
            follow_redirects=False,
        )
        assert resp.status_code == 303

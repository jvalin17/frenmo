"""Tests for friendship service — search, request, accept, reject, remove."""
import pytest

from app.models.friendship import Friendship
from app.models.user import User
from app.services.friendship import (
    accept_friend_request,
    get_friend_list,
    get_pending_requests,
    reject_friend_request,
    remove_friend,
    search_users_by_email,
    send_friend_request,
)


@pytest.fixture
async def two_users(db_session):
    """Create two users for friendship tests."""
    user_alice = User(email="alice@example.com", name="Alice", password_hash="hashed1")
    user_bob = User(email="bob@example.com", name="Bob", password_hash="hashed2")
    db_session.add_all([user_alice, user_bob])
    await db_session.commit()
    await db_session.refresh(user_alice)
    await db_session.refresh(user_bob)
    return user_alice, user_bob


@pytest.fixture
async def three_users(db_session):
    """Create three users for friendship tests."""
    user_alice = User(email="alice@example.com", name="Alice", password_hash="hashed1")
    user_bob = User(email="bob@example.com", name="Bob", password_hash="hashed2")
    user_carol = User(email="carol@gmail.com", name="Carol", password_hash="hashed3")
    db_session.add_all([user_alice, user_bob, user_carol])
    await db_session.commit()
    await db_session.refresh(user_alice)
    await db_session.refresh(user_bob)
    await db_session.refresh(user_carol)
    return user_alice, user_bob, user_carol


class TestSearchUsers:
    async def test_search_by_partial_email(self, db_session, three_users):
        alice, bob, carol = three_users
        results = await search_users_by_email(db_session, "bob@", exclude_user_id=alice.id)
        assert len(results) == 1
        assert results[0].id == bob.id

    async def test_search_returns_multiple_matches(self, db_session, three_users):
        alice, bob, carol = three_users
        results = await search_users_by_email(db_session, "@", exclude_user_id=alice.id)
        assert len(results) == 2  # bob and carol, not alice

    async def test_search_excludes_self(self, db_session, three_users):
        alice, bob, carol = three_users
        results = await search_users_by_email(db_session, "alice@", exclude_user_id=alice.id)
        assert len(results) == 0

    async def test_search_no_match(self, db_session, three_users):
        alice, bob, carol = three_users
        results = await search_users_by_email(db_session, "nonexistent@", exclude_user_id=alice.id)
        assert len(results) == 0

    async def test_search_case_insensitive(self, db_session, three_users):
        alice, bob, carol = three_users
        results = await search_users_by_email(db_session, "BOB@", exclude_user_id=alice.id)
        assert len(results) == 1


class TestSendFriendRequest:
    async def test_send_creates_pending_request(self, db_session, two_users):
        alice, bob = two_users
        friendship = await send_friend_request(db_session, from_user_id=alice.id, to_user_id=bob.id)
        assert friendship.user_id == alice.id
        assert friendship.friend_id == bob.id
        assert friendship.status == "pending"

    async def test_cannot_send_duplicate_request(self, db_session, two_users):
        alice, bob = two_users
        await send_friend_request(db_session, from_user_id=alice.id, to_user_id=bob.id)
        result = await send_friend_request(db_session, from_user_id=alice.id, to_user_id=bob.id)
        assert result is None

    async def test_cannot_friend_yourself(self, db_session, two_users):
        alice, bob = two_users
        result = await send_friend_request(db_session, from_user_id=alice.id, to_user_id=alice.id)
        assert result is None


class TestAcceptReject:
    async def test_accept_sets_status_accepted(self, db_session, two_users):
        alice, bob = two_users
        friendship = await send_friend_request(db_session, from_user_id=alice.id, to_user_id=bob.id)
        accepted = await accept_friend_request(db_session, friendship_id=friendship.id, user_id=bob.id)
        assert accepted is True

        friends = await get_friend_list(db_session, alice.id)
        assert len(friends) == 1
        assert friends[0].id == bob.id

    async def test_reject_deletes_request(self, db_session, two_users):
        alice, bob = two_users
        friendship = await send_friend_request(db_session, from_user_id=alice.id, to_user_id=bob.id)
        rejected = await reject_friend_request(db_session, friendship_id=friendship.id, user_id=bob.id)
        assert rejected is True

        pending = await get_pending_requests(db_session, bob.id)
        assert len(pending) == 0

    async def test_only_recipient_can_accept(self, db_session, two_users):
        alice, bob = two_users
        friendship = await send_friend_request(db_session, from_user_id=alice.id, to_user_id=bob.id)
        accepted = await accept_friend_request(db_session, friendship_id=friendship.id, user_id=alice.id)
        assert accepted is False


class TestFriendList:
    async def test_friendship_is_bidirectional(self, db_session, two_users):
        alice, bob = two_users
        friendship = await send_friend_request(db_session, from_user_id=alice.id, to_user_id=bob.id)
        await accept_friend_request(db_session, friendship_id=friendship.id, user_id=bob.id)

        alice_friends = await get_friend_list(db_session, alice.id)
        bob_friends = await get_friend_list(db_session, bob.id)
        assert len(alice_friends) == 1
        assert len(bob_friends) == 1
        assert alice_friends[0].id == bob.id
        assert bob_friends[0].id == alice.id

    async def test_pending_not_in_friend_list(self, db_session, two_users):
        alice, bob = two_users
        await send_friend_request(db_session, from_user_id=alice.id, to_user_id=bob.id)
        friends = await get_friend_list(db_session, alice.id)
        assert len(friends) == 0

    async def test_get_pending_requests(self, db_session, two_users):
        alice, bob = two_users
        await send_friend_request(db_session, from_user_id=alice.id, to_user_id=bob.id)
        pending = await get_pending_requests(db_session, bob.id)
        assert len(pending) == 1
        assert pending[0].user_id == alice.id


class TestRemoveFriend:
    async def test_remove_deletes_friendship(self, db_session, two_users):
        alice, bob = two_users
        friendship = await send_friend_request(db_session, from_user_id=alice.id, to_user_id=bob.id)
        await accept_friend_request(db_session, friendship_id=friendship.id, user_id=bob.id)

        removed = await remove_friend(db_session, user_id=alice.id, friend_id=bob.id)
        assert removed is True

        alice_friends = await get_friend_list(db_session, alice.id)
        bob_friends = await get_friend_list(db_session, bob.id)
        assert len(alice_friends) == 0
        assert len(bob_friends) == 0

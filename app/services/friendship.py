from itertools import combinations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.friendship import Friendship
from app.models.user import User


async def search_users_by_email(
    db: AsyncSession, email_query: str, exclude_user_id: int
) -> list[User]:
    """Search users by partial email match, excluding the requesting user."""
    result = await db.execute(
        select(User)
        .where(
            func.lower(User.email).contains(email_query.lower()),
            User.id != exclude_user_id,
        )
        .limit(10)
    )
    return list(result.scalars().all())


async def send_friend_request(
    db: AsyncSession, from_user_id: int, to_user_id: int
) -> Friendship | None:
    """Send a friend request. Returns None if duplicate or self-request."""
    if from_user_id == to_user_id:
        return None

    # Check for existing friendship in either direction
    existing = await db.execute(
        select(Friendship).where(
            or_(
                and_(Friendship.user_id == from_user_id, Friendship.friend_id == to_user_id),
                and_(Friendship.user_id == to_user_id, Friendship.friend_id == from_user_id),
            )
        )
    )
    if existing.scalar_one_or_none() is not None:
        return None

    friendship = Friendship(
        user_id=from_user_id,
        friend_id=to_user_id,
        status="pending",
    )
    db.add(friendship)
    await db.commit()
    await db.refresh(friendship)
    return friendship


async def accept_friend_request(
    db: AsyncSession, friendship_id: int, user_id: int
) -> bool:
    """Accept a pending friend request. Only the recipient can accept."""
    result = await db.execute(
        select(Friendship).where(
            Friendship.id == friendship_id,
            Friendship.friend_id == user_id,
            Friendship.status == "pending",
        )
    )
    friendship = result.scalar_one_or_none()
    if friendship is None:
        return False

    friendship.status = "accepted"
    await db.commit()
    return True


async def reject_friend_request(
    db: AsyncSession, friendship_id: int, user_id: int
) -> bool:
    """Reject (delete) a pending friend request. Only the recipient can reject."""
    result = await db.execute(
        select(Friendship).where(
            Friendship.id == friendship_id,
            Friendship.friend_id == user_id,
            Friendship.status == "pending",
        )
    )
    friendship = result.scalar_one_or_none()
    if friendship is None:
        return False

    await db.delete(friendship)
    await db.commit()
    return True


async def get_friend_list(db: AsyncSession, user_id: int) -> list[User]:
    """Get all accepted friends for a user (bidirectional)."""
    # Friends where user is the requester
    sent = select(Friendship.friend_id.label("friend_id")).where(
        Friendship.user_id == user_id,
        Friendship.status == "accepted",
    )
    # Friends where user is the recipient
    received = select(Friendship.user_id.label("friend_id")).where(
        Friendship.friend_id == user_id,
        Friendship.status == "accepted",
    )
    # Union both directions
    friend_ids = sent.union(received).subquery()

    result = await db.execute(
        select(User).where(User.id.in_(select(friend_ids.c.friend_id)))
    )
    return list(result.scalars().all())


async def get_pending_requests(db: AsyncSession, user_id: int) -> list[Friendship]:
    """Get pending friend requests received by this user."""
    result = await db.execute(
        select(Friendship).where(
            Friendship.friend_id == user_id,
            Friendship.status == "pending",
        )
    )
    return list(result.scalars().all())


async def is_friend(db: AsyncSession, user_id: int, friend_id: int) -> bool:
    """Check if two users have an accepted friendship (either direction)."""
    result = await db.execute(
        select(Friendship).where(
            or_(
                and_(Friendship.user_id == user_id, Friendship.friend_id == friend_id),
                and_(Friendship.user_id == friend_id, Friendship.friend_id == user_id),
            ),
            Friendship.status == "accepted",
        )
    )
    return result.scalar_one_or_none() is not None


async def ensure_friendship(
    db: AsyncSession, user_id: int, friend_id: int
) -> bool:
    """Create an accepted friendship if none exists. Returns True if created, False if skipped."""
    if user_id == friend_id:
        return False

    existing = await db.execute(
        select(Friendship).where(
            or_(
                and_(Friendship.user_id == user_id, Friendship.friend_id == friend_id),
                and_(Friendship.user_id == friend_id, Friendship.friend_id == user_id),
            )
        )
    )
    if existing.scalar_one_or_none() is not None:
        return False

    friendship = Friendship(
        user_id=user_id,
        friend_id=friend_id,
        status="accepted",
    )
    db.add(friendship)
    await db.flush()
    return True


async def ensure_group_friendships(db: AsyncSession, group_id: int) -> int:
    """Ensure all members in a group are friends. Returns count of new friendships.

    Runs on every group page load, so it uses a fixed number of statements:
    one for the members, one for the friendship rows already present between
    them (either direction, any status), and one batched INSERT for the rest.
    The count is the number of pairs inserted by this call; pairs a concurrent
    repair inserted first are skipped by the database and still counted here.
    """
    from app.models.group import GroupMember

    members_result = await db.execute(
        select(GroupMember.user_id)
        .where(GroupMember.group_id == group_id)
        .order_by(GroupMember.user_id)  # canonical (lower, higher) pair direction
    )
    member_ids = [row[0] for row in members_result.all()]
    if len(member_ids) < 2:
        return 0

    existing_result = await db.execute(
        select(Friendship.user_id, Friendship.friend_id).where(
            Friendship.user_id.in_(member_ids),
            Friendship.friend_id.in_(member_ids),
        )
    )
    linked = {frozenset(pair) for pair in existing_result.all()}

    missing = [
        {"user_id": user_id, "friend_id": friend_id, "status": "accepted"}
        for user_id, friend_id in combinations(member_ids, 2)
        if frozenset((user_id, friend_id)) not in linked
    ]
    if missing:
        # One batched INSERT rather than one statement per pair. A concurrent
        # page load may have inserted the same pairs; ON CONFLICT DO NOTHING
        # skips those instead of failing the whole request.
        dialect_name = db.get_bind().dialect.name
        await db.execute(missing_friendships_insert(dialect_name), missing)
    return len(missing)


def missing_friendships_insert(dialect_name: str):
    """INSERT ... ON CONFLICT DO NOTHING for the friendships table on the given dialect."""
    insert_for = postgresql.insert if dialect_name == "postgresql" else sqlite.insert
    return insert_for(Friendship).on_conflict_do_nothing()


async def get_pair_simplify(db: AsyncSession, user_id: int, friend_id: int) -> bool:
    """Whether this pair folds balances across groups on the friends page.

    One accepted row exists per pair, so both users read the same value.
    Defaults to True when there is no accepted friendship.
    """
    result = await db.execute(
        select(Friendship.simplify).where(
            or_(
                and_(Friendship.user_id == user_id, Friendship.friend_id == friend_id),
                and_(Friendship.user_id == friend_id, Friendship.friend_id == user_id),
            ),
            Friendship.status == "accepted",
        )
    )
    value = result.scalar_one_or_none()
    return True if value is None else bool(value)


async def set_pair_simplify(
    db: AsyncSession, user_id: int, friend_id: int, value: bool
) -> bool:
    """Set the pair's simplify flag. Returns False when they are not accepted friends."""
    result = await db.execute(
        select(Friendship).where(
            or_(
                and_(Friendship.user_id == user_id, Friendship.friend_id == friend_id),
                and_(Friendship.user_id == friend_id, Friendship.friend_id == user_id),
            ),
            Friendship.status == "accepted",
        )
    )
    friendship = result.scalar_one_or_none()
    if friendship is None:
        return False
    friendship.simplify = value
    await db.flush()
    return True


async def remove_friend(db: AsyncSession, user_id: int, friend_id: int) -> bool:
    """Remove an accepted friendship (either direction)."""
    result = await db.execute(
        select(Friendship).where(
            or_(
                and_(Friendship.user_id == user_id, Friendship.friend_id == friend_id),
                and_(Friendship.user_id == friend_id, Friendship.friend_id == user_id),
            ),
            Friendship.status == "accepted",
        )
    )
    friendship = result.scalar_one_or_none()
    if friendship is None:
        return False

    await db.delete(friendship)
    await db.commit()
    return True

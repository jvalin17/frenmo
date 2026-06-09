from sqlalchemy import and_, func, or_, select
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

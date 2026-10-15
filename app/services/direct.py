"""Hidden per-pair "direct" groups: one-to-one balances without a visible group.

A pair group is an ordinary Group row with type="direct", exactly two members and
a unique pair_key "<lower id>:<higher id>". Every balance, expense and settlement
function treats it like any other group; only group lists hide it.
"""
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.friendship import is_friend

DIRECT_TYPE = "direct"


def pair_key_for(user_a: int, user_b: int) -> str:
    """Canonical key for an unordered pair of user ids."""
    low, high = sorted((user_a, user_b))
    return f"{low}:{high}"


def is_direct(group: Group | None) -> bool:
    return group is not None and group.type == DIRECT_TYPE


async def lookup_direct_group(db: AsyncSession, pair_key: str) -> Group | None:
    result = await db.execute(select(Group).where(Group.pair_key == pair_key))
    return result.scalar_one_or_none()


async def find_or_create_direct_group(
    db: AsyncSession, user_id: int, friend_id: int
) -> Group | None:
    """Return the pair group for two accepted friends, creating it on first use.

    Returns None for self or for users who are not accepted friends. Safe under
    concurrent first calls: the INSERT is ON CONFLICT DO NOTHING on pair_key and
    the group is re-read afterwards, so a lost race returns the winner's group
    and adds no duplicate members. Flushes; the caller commits.
    """
    if user_id == friend_id or not await is_friend(db, user_id, friend_id):
        return None

    key = pair_key_for(user_id, friend_id)
    group = await lookup_direct_group(db, key)
    if group is not None:
        return group

    low, high = sorted((user_id, friend_id))
    low_user, high_user, creator = (
        await db.get(User, low), await db.get(User, high), await db.get(User, user_id)
    )
    insert_for = postgresql.insert if db.get_bind().dialect.name == "postgresql" else sqlite.insert

    await db.execute(
        insert_for(Group)
        .values(
            name=f"{low_user.name} & {high_user.name}",
            type=DIRECT_TYPE,
            created_by=user_id,
            currency=creator.default_currency or "USD",
            pair_key=key,
        )
        .on_conflict_do_nothing(index_elements=["pair_key"])
    )
    group = await lookup_direct_group(db, key)
    await db.execute(
        insert_for(GroupMember)
        .values([{"group_id": group.id, "user_id": low}, {"group_id": group.id, "user_id": high}])
        .on_conflict_do_nothing(index_elements=["group_id", "user_id"])
    )
    await db.flush()
    return group

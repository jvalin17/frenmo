"""Settle all balances with one friend in one currency (requirements D2/D2a, AD-3).

The figure the user sees is the net across groups, but every record stays in
the group where the debt is: one settlement per group, all flushed in the
caller's transaction, so group pages, the friends page and the dashboard keep
agreeing. Only the net cash changes hands.
"""
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.services.balance import shared_group_balances
from app.services.expense import create_expense_with_splits
from app.services.friendship import is_friend


@dataclass(frozen=True)
class SettleEntry:
    """One settlement that settle_all would record: debtor pays creditor in this group."""

    group_id: int
    group_name: str
    currency: str
    debtor_id: int
    creditor_id: int
    amount: int  # minor units, always positive


def net_for(entries: list[SettleEntry], user_id: int) -> int:
    """Net cash for user_id across the entries: positive = they receive, negative = they pay."""
    return sum(e.amount if e.creditor_id == user_id else -e.amount for e in entries)


async def settle_all_plan(
    db: AsyncSession, user_id: int, friend_id: int, currency: str
) -> list[SettleEntry]:
    """What settle_all would write: one entry per shared group with a nonzero
    bilateral balance in `currency`, in group id order. Other currencies are
    never included or converted."""
    entries = []
    for row in await shared_group_balances(db, user_id, friend_id):
        if row["currency"] != currency or row["balance"] == 0:
            continue
        friend_owes = row["balance"] > 0
        entries.append(SettleEntry(
            group_id=row["group_id"],
            group_name=row["group_name"],
            currency=currency,
            debtor_id=friend_id if friend_owes else user_id,
            creditor_id=user_id if friend_owes else friend_id,
            amount=abs(row["balance"]),
        ))
    return entries


async def settle_all(
    db: AsyncSession, user_id: int, friend_id: int, currency: str, batch_id: str
) -> list[Expense] | None:
    """Record every entry of settle_all_plan as a settlement in its own group.

    Flushes only; the caller commits, so a failure on any entry leaves none of
    them behind. The idempotency key "settle-all:<batch>:<group>" makes a
    re-submit of the same batch a no-op. Returns None for self or non-friends.
    """
    if user_id == friend_id or not await is_friend(db, user_id, friend_id):
        return None

    written = []
    for entry in await settle_all_plan(db, user_id, friend_id, currency):
        written.append(await create_expense_with_splits(
            db=db,
            group_id=entry.group_id,
            description="Settle all",
            amount_paise=entry.amount,
            split_type="exact",
            paid_by=entry.debtor_id,
            created_by=user_id,
            member_ids=[entry.creditor_id],
            member_values={entry.creditor_id: entry.amount / 100},
            expense_type="settlement",
            currency=entry.currency,
            idempotency_key=f"settle-all:{batch_id}:{entry.group_id}",
            commit=False,
        ))
    await db.flush()
    return written

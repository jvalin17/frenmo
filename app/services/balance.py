from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense, ExpenseSplit


async def get_group_balances(
    db: AsyncSession, group_id: int
) -> dict[int, int]:
    """Compute net balance per user in a group.

    Positive = others owe you. Negative = you owe others.
    Derived from expense_splits (never cached).
    """
    result = await db.execute(
        select(
            ExpenseSplit.user_id,
            func.sum(ExpenseSplit.paid_amount).label("total_paid"),
            func.sum(ExpenseSplit.owed_amount).label("total_owed"),
        )
        .join(Expense, ExpenseSplit.expense_id == Expense.id)
        .where(Expense.group_id == group_id, Expense.deleted_at.is_(None))
        .group_by(ExpenseSplit.user_id)
    )

    balances = {}
    for row in result.all():
        net = (row.total_paid or 0) - (row.total_owed or 0)
        if net != 0:
            balances[row.user_id] = net
    return balances


def simplify_debts(balances: dict[int, int]) -> list[tuple[int, int, int]]:
    """Greedy debt simplification. O(n^2).

    Returns list of (debtor_id, creditor_id, amount_paise).
    Read-time optimization only — never rewrites history.
    """
    # Separate into creditors and debtors
    creditors = []  # (user_id, amount) — positive net
    debtors = []    # (user_id, amount) — negative net (stored as positive)

    for user_id, net in balances.items():
        if net > 0:
            creditors.append([user_id, net])
        elif net < 0:
            debtors.append([user_id, -net])

    # Sort by amount descending for greedy matching
    creditors.sort(key=lambda x: -x[1])
    debtors.sort(key=lambda x: -x[1])

    settlements = []
    creditor_index = 0
    debtor_index = 0

    while creditor_index < len(creditors) and debtor_index < len(debtors):
        creditor_id, credit_amount = creditors[creditor_index]
        debtor_id, debt_amount = debtors[debtor_index]

        settle_amount = min(credit_amount, debt_amount)
        settlements.append((debtor_id, creditor_id, settle_amount))

        creditors[creditor_index][1] -= settle_amount
        debtors[debtor_index][1] -= settle_amount

        if creditors[creditor_index][1] == 0:
            creditor_index += 1
        if debtors[debtor_index][1] == 0:
            debtor_index += 1

    return settlements


async def get_overall_balances(
    db: AsyncSession, user_id: int
) -> dict[int, dict[str, int]]:
    """Cross-group balances for a user, kept per currency.

    Amounts are never summed across currencies: each expense counts in its
    group's currency (one currency per group).

    Returns {other_user_id: {currency: net_amount}} where:
      positive = other person owes you
      negative = you owe the other person
    """
    from app.models.group import Group

    # Get all expenses involving this user (across all groups)
    result = await db.execute(
        select(
            ExpenseSplit.user_id,
            Group.currency,
            func.sum(ExpenseSplit.paid_amount).label("amount_paid"),
            func.sum(ExpenseSplit.owed_amount).label("amount_owed"),
        )
        .join(Expense, ExpenseSplit.expense_id == Expense.id)
        .join(Group, Expense.group_id == Group.id)
        .where(
            Expense.deleted_at.is_(None),
            Expense.id.in_(
                select(ExpenseSplit.expense_id).where(ExpenseSplit.user_id == user_id)
            ),
        )
        .group_by(ExpenseSplit.user_id, Group.currency)
    )

    all_balances: dict[int, dict[str, int]] = {}
    for row in result.all():
        # other_net: positive means they paid more than they owe (they're a creditor)
        # Negate to get current user's perspective:
        #   other is creditor → you owe them (negative)
        #   other is debtor → they owe you (positive)
        other_net = (row.amount_paid or 0) - (row.amount_owed or 0)
        from_user_perspective = -other_net
        if from_user_perspective != 0 and row.user_id != user_id:
            all_balances.setdefault(row.user_id, {})[row.currency] = from_user_perspective
    return all_balances


@dataclass(frozen=True)
class CurrencyTotal:
    """Dashboard hero totals for one currency, in integer minor units."""

    currency: str
    owed: int  # owed to you
    owe: int   # you owe

    @property
    def net(self) -> int:
        return self.owed - self.owe


def summarize_by_currency(overall: dict[int, dict[str, int]]) -> list[CurrencyTotal]:
    """Fold per-person, per-currency nets into one total per currency, sorted by code."""
    owed: dict[str, int] = {}
    owe: dict[str, int] = {}
    for per_currency in overall.values():
        for currency, net in per_currency.items():
            if net > 0:
                owed[currency] = owed.get(currency, 0) + net
            elif net < 0:
                owe[currency] = owe.get(currency, 0) - net
    return [
        CurrencyTotal(currency, owed.get(currency, 0), owe.get(currency, 0))
        for currency in sorted(owed.keys() | owe.keys())
    ]


def hero_state(totals: list[CurrencyTotal]) -> str:
    """positive | negative | mixed | settled, from the sign of each currency's net."""
    signs = {(t.net > 0) - (t.net < 0) for t in totals} - {0}
    if signs == {1}:
        return "positive"
    if signs == {-1}:
        return "negative"
    if signs:
        return "mixed"
    return "settled"


async def get_friend_balance_detail(
    db: AsyncSession, user_id: int, friend_id: int
) -> dict:
    """Per-friend balance with group breakdown and settlement history.

    Balances are never summed across currencies: each group's balance is
    kept in that group's currency and the net is reported per currency.

    Returns {
        net_balances: {currency: int} (positive = friend owes you),
        groups: [{group_id, group_name, balance, currency}],
        settlements: [{amount, currency, paid_by, created_at, group_name}],
    }
    """
    from app.models.group import Group, GroupMember

    # Find shared groups (both users are members)
    user_groups = select(GroupMember.group_id).where(GroupMember.user_id == user_id)
    friend_groups = select(GroupMember.group_id).where(GroupMember.user_id == friend_id)
    shared_group_ids = await db.execute(
        select(Group).where(Group.id.in_(user_groups.intersect(friend_groups)))
    )
    shared_groups = shared_group_ids.scalars().all()
    groups_by_id = {g.id: g for g in shared_groups}

    net_balances: dict[str, int] = {}
    group_details = []

    for group in shared_groups:
        balances = await get_group_balances(db, group.id)
        simplified = simplify_debts(balances)

        # Find bilateral balance from simplified debts
        group_balance = 0
        for debtor_id, creditor_id, amount in simplified:
            if debtor_id == friend_id and creditor_id == user_id:
                group_balance += amount  # friend owes me
            elif debtor_id == user_id and creditor_id == friend_id:
                group_balance -= amount  # I owe friend

        if group_balance != 0:
            group_details.append({
                "group_id": group.id,
                "group_name": group.name,
                "balance": group_balance,
                "currency": group.currency,
            })
            net_balances[group.currency] = net_balances.get(group.currency, 0) + group_balance

    # Settlement history between the two users across all shared groups
    settlement_result = await db.execute(
        select(Expense)
        .where(
            Expense.expense_type == "settlement",
            Expense.deleted_at.is_(None),
            Expense.group_id.in_([g.id for g in shared_groups]),
        )
        .order_by(Expense.created_at.desc())
    )
    settlements = []
    for expense in settlement_result.scalars().all():
        # Only include settlements between these two users
        if (expense.paid_by == user_id or expense.paid_by == friend_id):
            # Check if the other user is in the splits
            split_result = await db.execute(
                select(ExpenseSplit.user_id).where(
                    ExpenseSplit.expense_id == expense.id,
                    ExpenseSplit.user_id.in_([user_id, friend_id]),
                )
            )
            involved_users = {row[0] for row in split_result.all()}
            if user_id in involved_users and friend_id in involved_users:
                # Settlements are recorded in the group's currency; the query above
                # only returns rows from shared_groups, so the lookup always hits.
                group = groups_by_id[expense.group_id]
                settlements.append({
                    "amount": expense.amount,
                    "currency": group.currency,
                    "paid_by": expense.paid_by,
                    "created_at": expense.created_at,
                    "group_name": group.name,
                })

    return {
        "net_balances": net_balances,
        "groups": group_details,
        "settlements": settlements,
    }

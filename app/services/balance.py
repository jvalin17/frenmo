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

    # Sort by amount descending for greedy matching; ties break on user id so the
    # result does not depend on dict (= database row) order between page loads.
    creditors.sort(key=lambda x: (-x[1], x[0]))
    debtors.sort(key=lambda x: (-x[1], x[0]))

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


def bilateral_debts(
    simplified: list[tuple[int, int, int]], user_id: int
) -> dict[int, int]:
    """Net amount between user_id and each counterparty in a simplified debt list.

    Returns {other_user_id: net} with positive = they owe you, negative = you
    owe them. Transfers between two other people are ignored.
    """
    nets: dict[int, int] = {}
    for debtor_id, creditor_id, amount in simplified:
        if creditor_id == user_id:
            nets[debtor_id] = nets.get(debtor_id, 0) + amount
        elif debtor_id == user_id:
            nets[creditor_id] = nets.get(creditor_id, 0) - amount
    return {other_id: net for other_id, net in nets.items() if net != 0}


async def get_user_balances(
    db: AsyncSession, user_id: int, groups
) -> tuple[dict[int, dict[str, int]], dict[int, int]]:
    """Personal balances for user_id across the given groups, one pass per group.

    The canonical per-group calculation is get_group_balances + simplify_debts:
    it is what the group page's Settle Up list shows and what settlements are
    recorded against, so the dashboard and friends page derive their people
    balances from it too. Amounts are never summed across currencies.

    Returns (people, per_group):
      people:    {other_user_id: {currency: net}}, positive = they owe you
      per_group: {group_id: your net in that group}
    """
    people: dict[int, dict[str, int]] = {}
    per_group: dict[int, int] = {}
    for group in groups:
        balances = await get_group_balances(db, group.id)
        per_group[group.id] = balances.get(user_id, 0)
        for other_id, net in bilateral_debts(simplify_debts(balances), user_id).items():
            by_currency = people.setdefault(other_id, {})
            by_currency[group.currency] = by_currency.get(group.currency, 0) + net

    cleaned: dict[int, dict[str, int]] = {}
    for other_id, by_currency in people.items():
        nonzero = {currency: net for currency, net in by_currency.items() if net != 0}
        if nonzero:
            cleaned[other_id] = nonzero
    return cleaned, per_group


async def get_overall_balances(
    db: AsyncSession, user_id: int
) -> dict[int, dict[str, int]]:
    """Cross-group personal balances for a user, kept per currency.

    Returns {other_user_id: {currency: net_amount}} where:
      positive = other person owes you
      negative = you owe the other person
    """
    from app.models.group import Group, GroupMember

    result = await db.execute(
        select(Group)
        .join(GroupMember, Group.id == GroupMember.group_id)
        .where(GroupMember.user_id == user_id)
    )
    people, _ = await get_user_balances(db, user_id, result.scalars().all())
    return people


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


async def shared_group_balances(
    db: AsyncSession, user_id: int, friend_id: int
) -> list[dict]:
    """Bilateral balance with friend_id in every group both users belong to.

    One row per shared group, zero balances included:
    {group_id, group_name, currency, balance} with positive = friend owes you.
    The canonical per-group calculation (get_group_balances + simplify_debts +
    bilateral_debts) is the only arithmetic here; pair groups are ordinary rows.
    """
    from app.models.group import Group, GroupMember

    user_groups = select(GroupMember.group_id).where(GroupMember.user_id == user_id)
    friend_groups = select(GroupMember.group_id).where(GroupMember.user_id == friend_id)
    result = await db.execute(
        select(Group)
        .where(Group.id.in_(user_groups.intersect(friend_groups)))
        .order_by(Group.id)
    )
    rows = []
    for group in result.scalars().all():
        balances = await get_group_balances(db, group.id)
        rows.append({
            "group_id": group.id,
            "group_name": group.name,
            "type": group.type,  # "direct" marks the hidden pair group
            "currency": group.currency,
            "balance": bilateral_debts(simplify_debts(balances), user_id).get(friend_id, 0),
        })
    return rows


def fold_per_currency(rows: list[dict]) -> dict[str, int]:
    """Sum per-group bilateral rows into {currency: net}; zero nets are dropped.

    Never sums across currencies (requirements D2a).
    """
    nets: dict[str, int] = {}
    for row in rows:
        nets[row["currency"]] = nets.get(row["currency"], 0) + row["balance"]
    return {currency: net for currency, net in nets.items() if net != 0}


async def get_friend_balance_detail(
    db: AsyncSession, user_id: int, friend_id: int
) -> dict:
    """Per-friend balance with group breakdown and settlement history.

    Balances are never summed across currencies: each group's balance is
    kept in that group's currency and the net is reported per currency.

    Returns {
        net_balances: {currency: int} (positive = friend owes you),
        groups: [{group_id, group_name, type, balance, currency}] (nonzero only),
        settlements: [{amount, currency, paid_by, created_at, group_name}],
    }
    """
    rows = await shared_group_balances(db, user_id, friend_id)
    groups_by_id = {row["group_id"]: row for row in rows}
    group_details = [row for row in rows if row["balance"] != 0]
    net_balances = fold_per_currency(rows)

    # Settlement history between the two users across all shared groups
    settlement_result = await db.execute(
        select(Expense)
        .where(
            Expense.expense_type == "settlement",
            Expense.deleted_at.is_(None),
            Expense.group_id.in_(list(groups_by_id)),
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
                    "currency": group["currency"],
                    "paid_by": expense.paid_by,
                    "created_at": expense.created_at,
                    "group_name": group["group_name"],
                })

    return {
        "net_balances": net_balances,
        "groups": group_details,
        "settlements": settlements,
    }

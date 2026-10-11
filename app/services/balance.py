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
) -> dict[int, int]:
    """Cross-group balances for a user.

    Returns {other_user_id: net_amount} where:
      positive = other person owes you
      negative = you owe the other person
    """
    # Get all expenses involving this user (across all groups)
    result = await db.execute(
        select(
            ExpenseSplit.user_id,
            func.sum(ExpenseSplit.paid_amount).label("amount_paid"),
            func.sum(ExpenseSplit.owed_amount).label("amount_owed"),
        )
        .join(Expense, ExpenseSplit.expense_id == Expense.id)
        .where(
            Expense.deleted_at.is_(None),
            Expense.id.in_(
                select(ExpenseSplit.expense_id).where(ExpenseSplit.user_id == user_id)
            ),
        )
        .group_by(ExpenseSplit.user_id)
    )

    all_balances = {}
    for row in result.all():
        # other_net: positive means they paid more than they owe (they're a creditor)
        # Negate to get current user's perspective:
        #   other is creditor → you owe them (negative)
        #   other is debtor → they owe you (positive)
        other_net = (row.amount_paid or 0) - (row.amount_owed or 0)
        from_user_perspective = -other_net
        if from_user_perspective != 0 and row.user_id != user_id:
            all_balances[row.user_id] = from_user_perspective
    return all_balances


async def get_friend_balance_detail(
    db: AsyncSession, user_id: int, friend_id: int
) -> dict:
    """Per-friend balance with group breakdown and settlement history.

    Returns {
        net_balance: int (positive = friend owes you),
        groups: [{group_id, group_name, balance}],
        settlements: [{amount, paid_by, created_at, group_name}],
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

    net_balance = 0
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
            })
            net_balance += group_balance

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
                group_name = next(
                    (g.name for g in shared_groups if g.id == expense.group_id), "?"
                )
                settlements.append({
                    "amount": expense.amount,
                    "paid_by": expense.paid_by,
                    "created_at": expense.created_at,
                    "group_name": group_name,
                })

    return {
        "net_balance": net_balance,
        "groups": group_details,
        "settlements": settlements,
    }

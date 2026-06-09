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
    """Cross-group balances for a user. Returns {other_user_id: net_amount}."""
    # Get all expenses involving this user (across all groups)
    result = await db.execute(
        select(
            ExpenseSplit.user_id,
            func.sum(ExpenseSplit.paid_amount).label("total_paid"),
            func.sum(ExpenseSplit.owed_amount).label("total_owed"),
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
        net = (row.total_paid or 0) - (row.total_owed or 0)
        if net != 0 and row.user_id != user_id:
            all_balances[row.user_id] = net
    return all_balances

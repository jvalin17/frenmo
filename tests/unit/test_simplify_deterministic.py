"""simplify_debts must give the same answer regardless of input order (D4).

With tied amounts the greedy matcher used to fall back to dict insertion order,
which comes from database row order, so "who owes whom" could change between
page loads.
"""
from itertools import permutations

from app.services.balance import simplify_debts


def test_simplify_debts_is_deterministic_under_ties():
    # Two creditors tied at ₹300, three debtors tied at ₹200: many valid matchings.
    balances = {7: 30000, 3: 30000, 11: -20000, 5: -20000, 9: -20000}
    expected = simplify_debts(balances)
    for ordering in permutations(balances.items()):  # all 120 input orders
        assert simplify_debts(dict(ordering)) == expected
    # Ties break on user id: the lower-id creditor and debtor are matched first.
    assert expected[0] == (5, 3, 20000)


def test_simplify_debts_conserves_balances():
    balances = {1: 12500, 2: 7500, 3: -5000, 4: -5000, 5: -10000}
    paid: dict[int, int] = {}
    for debtor, creditor, amount in simplify_debts(balances):
        assert amount > 0
        paid[debtor] = paid.get(debtor, 0) - amount
        paid[creditor] = paid.get(creditor, 0) + amount
    assert paid == {1: 12500, 2: 7500, 3: -5000, 4: -5000, 5: -10000}

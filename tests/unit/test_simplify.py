"""Tests for debt simplification algorithm."""
from app.services.balance import simplify_debts


def test_simplify_two_people():
    # A paid ₹100, B owes ₹50
    balances = {1: 5000, 2: -5000}  # A gets 50, B owes 50
    result = simplify_debts(balances)
    assert len(result) == 1
    debtor, creditor, amount = result[0]
    assert debtor == 2
    assert creditor == 1
    assert amount == 5000


def test_simplify_chain():
    # A owes B, B owes C → simplify to A owes C
    balances = {1: -3000, 2: 0, 3: 3000}
    # Only non-zero balances matter; B drops out
    balances_filtered = {k: v for k, v in balances.items() if v != 0}
    result = simplify_debts(balances_filtered)
    assert len(result) == 1
    assert result[0] == (1, 3, 3000)  # A pays C directly


def test_simplify_triangle():
    # Classic: A(+50), B(-20), C(-30)
    balances = {1: 5000, 2: -2000, 3: -3000}
    result = simplify_debts(balances)
    total_settled = sum(amount for _, _, amount in result)
    assert total_settled == 5000  # total flow = total debt
    assert len(result) == 2  # two payments to settle


def test_simplify_already_settled():
    balances = {}
    result = simplify_debts(balances)
    assert result == []


def test_simplify_complex_group():
    # 4 people: A(+100), B(+50), C(-80), D(-70)
    balances = {1: 10000, 2: 5000, 3: -8000, 4: -7000}
    result = simplify_debts(balances)
    # Verify invariants
    credit_total = sum(v for v in balances.values() if v > 0)
    settled_total = sum(amount for _, _, amount in result)
    assert settled_total == credit_total  # all credit is settled
    assert len(result) <= 3  # at most n-1 transactions

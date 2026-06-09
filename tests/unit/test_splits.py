"""Tests for expense split calculations — the core financial logic."""
from app.services.expense import (
    compute_equal_splits,
    compute_exact_splits,
    compute_percent_splits,
)


def test_equal_split_divides_evenly():
    splits = compute_equal_splits(30000, [1, 2, 3])  # ₹300 / 3
    assert splits == {1: 10000, 2: 10000, 3: 10000}


def test_equal_split_distributes_remainder():
    splits = compute_equal_splits(10000, [1, 2, 3])  # ₹100 / 3 = 33.33...
    assert splits[1] == 3334  # first gets extra cent
    assert splits[2] == 3333
    assert splits[3] == 3333
    assert sum(splits.values()) == 10000  # invariant: sum = total


def test_equal_split_single_person():
    splits = compute_equal_splits(5000, [42])
    assert splits == {42: 5000}


def test_equal_split_empty():
    splits = compute_equal_splits(5000, [])
    assert splits == {}


def test_exact_split_sums_correctly():
    splits = compute_exact_splits(10000, {1: 60.00, 2: 40.00})
    assert splits[1] == 6000
    assert splits[2] == 4000
    assert sum(splits.values()) == 10000


def test_exact_split_adjusts_rounding():
    # ₹100 split as 33.33 + 33.33 + 33.34
    splits = compute_exact_splits(10000, {1: 33.33, 2: 33.33, 3: 33.34})
    assert sum(splits.values()) == 10000


def test_percent_split_basic():
    splits = compute_percent_splits(10000, {1: 50, 2: 30, 3: 20})
    assert splits[1] == 5000
    assert splits[2] == 3000
    assert splits[3] == 2000
    assert sum(splits.values()) == 10000


def test_percent_split_handles_rounding():
    # 33.33% + 33.33% + 33.34% of ₹100
    splits = compute_percent_splits(10000, {1: 33.33, 2: 33.33, 3: 33.34})
    assert sum(splits.values()) == 10000  # invariant must hold


# --- Shares split tests ---
from app.services.expense import compute_shares_splits, compute_full_split


def test_shares_split_parents_case():
    """jj has 3 shares (self + 2 parents), Alice and Bob have 1 each. $100 dinner."""
    splits = compute_shares_splits(10000, {1: 3, 2: 1, 3: 1})  # 5 total shares
    assert splits[1] == 6000  # 3/5 of $100
    assert splits[2] == 2000  # 1/5
    assert splits[3] == 2000  # 1/5
    assert sum(splits.values()) == 10000


def test_shares_split_equal_weights():
    splits = compute_shares_splits(10000, {1: 1, 2: 1, 3: 1})
    assert splits[1] == 3333
    assert splits[2] == 3333
    assert splits[3] == 3334  # remainder goes to last
    assert sum(splits.values()) == 10000


def test_shares_split_handles_rounding():
    """$100 split 2:1:1 = 50, 25, 25"""
    splits = compute_shares_splits(10000, {1: 2, 2: 1, 3: 1})
    assert splits[1] == 5000
    assert splits[2] == 2500
    assert splits[3] == 2500
    assert sum(splits.values()) == 10000


def test_shares_split_single_person():
    splits = compute_shares_splits(5000, {42: 3})
    assert splits == {42: 5000}


def test_shares_split_empty():
    splits = compute_shares_splits(5000, {})
    assert splits == {}


# --- Full split tests ---
def test_full_split_one_person_owes_all():
    """Alice paid, Bob owes the full amount."""
    splits = compute_full_split(10000, owes_user_id=2, member_ids=[1, 2])
    assert splits[2] == 10000
    assert splits[1] == 0


def test_full_split_payer_owes_themselves():
    splits = compute_full_split(10000, owes_user_id=1, member_ids=[1, 2])
    assert splits[1] == 10000
    assert splits[2] == 0

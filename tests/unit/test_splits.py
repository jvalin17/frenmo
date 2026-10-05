"""Tests for expense split calculations — the core financial logic."""
from app.services.splits import (
    compute_equal_splits,
    compute_exact_splits,
    compute_percent_splits,
)


def test_compute_equal_splits_divides_evenly():
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


def test_compute_exact_splits_sums_correctly():
    splits = compute_exact_splits(10000, {1: 60.00, 2: 40.00})
    assert splits[1] == 6000
    assert splits[2] == 4000
    assert sum(splits.values()) == 10000


def test_exact_split_adjusts_rounding():
    # ₹100 split as 33.33 + 33.33 + 33.34
    splits = compute_exact_splits(10000, {1: 33.33, 2: 33.33, 3: 33.34})
    assert sum(splits.values()) == 10000


def test_compute_percent_splits_basic():
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
from app.services.splits import compute_shares_splits, compute_full_split


def test_compute_shares_splits_parents_case():
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
def test_compute_full_split_one_person_owes_all():
    """Alice paid, Bob owes the full amount."""
    splits = compute_full_split(10000, owes_user_id=2, member_ids=[1, 2])
    assert splits[2] == 10000
    assert splits[1] == 0


def test_full_split_payer_owes_themselves():
    splits = compute_full_split(10000, owes_user_id=1, member_ids=[1, 2])
    assert splits[1] == 10000
    assert splits[2] == 0


def test_shares_split_group_default_trip():
    """Trip: jj=1 share, Bob=3 (parents), Alice=2 (partner). $60 expense."""
    splits = compute_shares_splits(6000, {1: 1, 2: 3, 3: 2})  # 6 total shares
    assert splits[1] == 1000   # jj: 1/6 = $10
    assert splits[2] == 3000   # Bob: 3/6 = $30
    assert splits[3] == 2000   # Alice: 2/6 = $20
    assert sum(splits.values()) == 6000


def test_shares_split_group_default_uneven():
    """$100 split 1:3:2 = 16.67, 50.00, 33.33"""
    splits = compute_shares_splits(10000, {1: 1, 2: 3, 3: 2})
    assert splits[1] == 1667   # 1/6
    assert splits[2] == 5000   # 3/6
    assert splits[3] == 3333   # remainder adjustment
    assert sum(splits.values()) == 10000


# --- compute_effective_shares tests ---
from app.services.splits import compute_effective_shares, compute_splits


def test_compute_effective_shares_non_kid():
    """Non-kid: kids count as full shares (additive)."""
    assert compute_effective_shares(2, 1, is_kid_friendly=False) == 3.0


def test_compute_effective_shares_kid_friendly():
    """Kid-friendly: kids count as 0.5."""
    assert compute_effective_shares(2, 1, is_kid_friendly=True) == 2.5


def test_compute_effective_shares_zero_adults():
    """0 adults + 1 kid, kid-friendly → 0.5."""
    assert compute_effective_shares(0, 1, is_kid_friendly=True) == 0.5


def test_compute_splits_dispatches_equal():
    """compute_splits with equal type uses equal logic."""
    result = compute_splits(10000, "equal", [1, 2])
    assert result == {1: 5000, 2: 5000}


def test_compute_splits_dispatches_shares():
    """compute_splits with shares type uses shares logic."""
    result = compute_splits(10000, "shares", [1, 2], member_values={1: 3.0, 2: 1.0})
    assert result[1] == 7500
    assert result[2] == 2500

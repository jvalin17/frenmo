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
    assert splits[1] == 3334  # first gets extra paise
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

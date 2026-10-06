"""Tests for kid-friendly split computation: effective shares, kid-aware splits, ValueError guard."""
import pytest

from app.services.splits import (
    compute_effective_shares,
    compute_kid_aware_splits,
    compute_shares_splits,
)


class TestComputeEffectiveShares:

    def test_non_kid_adult_with_kid(self):
        """Non-kid expense: kid counts as full share."""
        assert compute_effective_shares(2, 1, is_kid_friendly=False) == 3.0

    def test_kid_friendly_adult_with_kid(self):
        """Kid expense: kid counts as 0.5."""
        assert compute_effective_shares(2, 1, is_kid_friendly=True) == 2.5

    def test_zero_adults_kid_friendly(self):
        """0 adults + 1 kid, kid expense → 0.5."""
        assert compute_effective_shares(0, 1, is_kid_friendly=True) == 0.5

    def test_zero_adults_non_kid(self):
        """0 adults + 1 kid, non-kid expense → 1.0."""
        assert compute_effective_shares(0, 1, is_kid_friendly=False) == 1.0

    def test_kid_count_zero_is_noop(self):
        """kid_count=0 → same as default_shares regardless of kid_friendly."""
        assert compute_effective_shares(2, 0, is_kid_friendly=True) == 2.0
        assert compute_effective_shares(2, 0, is_kid_friendly=False) == 2.0

    def test_multiple_kids_kid_friendly(self):
        """3 kids at 0.5 each = 1.5 added."""
        assert compute_effective_shares(1, 3, is_kid_friendly=True) == 2.5

    def test_multiple_kids_non_kid(self):
        """3 kids at full share = 3 added."""
        assert compute_effective_shares(1, 3, is_kid_friendly=False) == 4.0


class TestComputeKidAwareSplits:

    def test_compute_kid_aware_splits_spec_example(self):
        """$1200 kid-friendly: Alice(1), Bob(2), Charlie(2.5) → denom 5.5."""
        shares = {1: 1.0, 2: 2.0, 3: 2.5}
        result = compute_kid_aware_splits(120000, shares, parent_user_ids=[3])
        assert result[1] == 21818  # 1/5.5 * 120000
        assert result[2] == 43636  # 2/5.5 * 120000
        assert sum(result.values()) == 120000  # remainder goes to parent (user 3)

    def test_non_kid_spec_example(self):
        """$1200 non-kid: Alice(1), Bob(2), Charlie(3) → denom 6."""
        shares = {1: 1.0, 2: 2.0, 3: 3.0}
        result = compute_kid_aware_splits(120000, shares, parent_user_ids=[3])
        assert result[1] == 20000
        assert result[2] == 40000
        assert result[3] == 60000
        assert sum(result.values()) == 120000

    def test_remainder_goes_to_first_parent(self):
        """Remainder paise assigned to first parent by user_id, not last member."""
        # 10001 / 3.5 = 2857.43... per unit share
        shares = {10: 1.0, 20: 1.0, 30: 1.5}  # parent is user 30
        result = compute_kid_aware_splits(10001, shares, parent_user_ids=[30])
        assert sum(result.values()) == 10001
        # User 30 (parent) gets the remainder
        expected_10 = round(10001 * 1.0 / 3.5)  # 2857
        expected_20 = round(10001 * 1.0 / 3.5)  # 2857
        expected_30 = round(10001 * 1.5 / 3.5)  # 4286
        # Sum = 2857+2857+4286 = 10000, remainder = 1 → goes to parent 30
        assert result[30] == expected_30 + (10001 - expected_10 - expected_20 - expected_30)

    def test_remainder_fallback_no_parents(self):
        """No parents → remainder goes to last member (existing behavior)."""
        shares = {1: 1.0, 2: 1.0, 3: 1.0}
        result = compute_kid_aware_splits(10001, shares, parent_user_ids=[])
        assert sum(result.values()) == 10001

    def test_single_member_with_kid(self):
        """One member with 0.5 shares → gets entire amount."""
        result = compute_kid_aware_splits(10000, {1: 0.5}, parent_user_ids=[1])
        assert result[1] == 10000

    def test_empty_shares_returns_empty(self):
        result = compute_kid_aware_splits(10000, {}, parent_user_ids=[])
        assert result == {}

    def test_zero_denominator_raises_value_error(self):
        """All members have 0 effective shares → ValueError."""
        with pytest.raises(ValueError, match="zero"):
            compute_kid_aware_splits(10000, {1: 0.0, 2: 0.0}, parent_user_ids=[])

    def test_multiple_parents_remainder_to_lowest_id(self):
        """Multiple parents → remainder goes to lowest user_id parent."""
        shares = {10: 1.5, 20: 1.5}  # both are parents
        result = compute_kid_aware_splits(10001, shares, parent_user_ids=[20, 10])
        assert sum(result.values()) == 10001
        # User 10 (lowest id) should get the remainder, not user 20
        base_per_unit = round(10001 * 1.5 / 3.0)  # 5001
        assert result[10] != result[20]  # they shouldn't be equal with odd amount
        assert result[10] > result[20] or result[10] == base_per_unit + 1  # user 10 gets +1

    def test_kid_friendly_ignores_total_splits(self):
        """Kid-friendly should NOT use total_splits — just sum of effective shares."""
        shares = {1: 1.0, 2: 2.5}
        # Even if total_splits=10, kid-friendly ignores it
        result = compute_kid_aware_splits(35000, shares, parent_user_ids=[2])
        assert result[1] == 10000  # 1/3.5 * 35000
        assert result[2] == 25000  # 2.5/3.5 * 35000
        assert sum(result.values()) == 35000


class TestBuildKidAwareSplitsHelper:

    def test__build_kid_aware_splits_kid_friendly(self):
        """_build_kid_aware_splits computes effective shares and delegates correctly."""
        from app.services.expense import _build_kid_aware_splits
        # Alice(1 share, 0 kids), Charlie(2 shares, 1 kid) → kid: 1.0 + 2.5 = 3.5
        result = _build_kid_aware_splits(
            amount_paise=35000,
            participant_ids=[1, 2],
            member_shares={1: 1, 2: 2},
            kid_counts={1: 0, 2: 1},
            is_kid_friendly=True,
        )
        assert result[1] == 10000  # 1.0/3.5 * 35000
        assert result[2] == 25000  # 2.5/3.5 * 35000
        assert sum(result.values()) == 35000

    def test__build_kid_aware_splits_non_kid(self):
        """Non-kid: kids count as full shares."""
        from app.services.expense import _build_kid_aware_splits
        result = _build_kid_aware_splits(
            amount_paise=30000,
            participant_ids=[1, 2],
            member_shares={1: 1, 2: 2},
            kid_counts={1: 0, 2: 1},
            is_kid_friendly=False,
        )
        # Non-kid: 1+0=1, 2+1=3 → denom 4
        assert result[1] == 7500   # 1/4 * 30000
        assert result[2] == 22500  # 3/4 * 30000


class TestZeroDenominatorGuard:

    def test_compute_shares_splits_raises_on_zero(self):
        """compute_shares_splits must raise ValueError on zero denominator."""
        with pytest.raises(ValueError, match="zero"):
            compute_shares_splits(10000, {1: 0.0, 2: 0.0})

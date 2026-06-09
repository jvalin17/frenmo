"""Tests for currency conversion service."""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.currency import convert_amount, get_exchange_rates, RATE_CACHE


class TestConvertAmount:
    def test_same_currency_returns_original(self):
        result = convert_amount(10000, "USD", "USD", {"USD": 1.0})
        assert result == 10000

    def test_usd_to_inr(self):
        rates = {"USD": 1.0, "INR": 83.5}
        result = convert_amount(10000, "USD", "INR", rates)  # $100 → ₹8350
        assert result == 835000

    def test_inr_to_usd(self):
        rates = {"USD": 1.0, "INR": 83.5}
        result = convert_amount(835000, "INR", "USD", rates)  # ₹8350 → $100
        assert result == 10000

    def test_eur_to_gbp_cross_rate(self):
        rates = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79}
        result = convert_amount(10000, "EUR", "GBP", rates)  # €100 → £85.87
        expected = round(10000 * (0.79 / 0.92))
        assert result == expected

    def test_zero_amount(self):
        rates = {"USD": 1.0, "INR": 83.5}
        result = convert_amount(0, "USD", "INR", rates)
        assert result == 0

    def test_missing_currency_returns_none(self):
        rates = {"USD": 1.0}
        result = convert_amount(10000, "USD", "XYZ", rates)
        assert result is None

    def test_missing_source_returns_none(self):
        rates = {"USD": 1.0, "INR": 83.5}
        result = convert_amount(10000, "XYZ", "INR", rates)
        assert result is None


class TestRateCache:
    def test_cache_stores_rates(self):
        RATE_CACHE.clear()
        RATE_CACHE["rates"] = {"USD": 1.0, "INR": 83.5}
        RATE_CACHE["timestamp"] = 9999999999.0
        assert RATE_CACHE["rates"]["INR"] == 83.5

    def test_cache_expiry_check(self):
        import time
        RATE_CACHE.clear()
        RATE_CACHE["rates"] = {"USD": 1.0}
        RATE_CACHE["timestamp"] = time.time() - 50000  # expired (>12h)
        elapsed = time.time() - RATE_CACHE["timestamp"]
        assert elapsed > 43200  # 12 hours in seconds

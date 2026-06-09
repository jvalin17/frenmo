import logging
import time

import httpx

logger = logging.getLogger(__name__)

# In-memory cache: {"rates": {...}, "timestamp": float}
RATE_CACHE: dict = {}

CACHE_TTL_SECONDS = 43200  # 12 hours

# Free API — no key needed
RATES_API_URL = "https://open.er-api.com/v6/latest/USD"


def convert_amount(
    amount_cents: int,
    from_currency: str,
    to_currency: str,
    rates: dict[str, float],
) -> int | None:
    """Convert amount in cents between currencies using provided rates.
    All rates are relative to USD. Returns None if currency not found."""
    if from_currency == to_currency:
        return amount_cents
    if from_currency not in rates or to_currency not in rates:
        return None
    if amount_cents == 0:
        return 0

    # Convert: from_currency → USD → to_currency
    usd_amount = amount_cents / rates[from_currency]
    target_amount = usd_amount * rates[to_currency]
    return round(target_amount)


async def get_exchange_rates() -> dict[str, float]:
    """Fetch exchange rates from API with 12-hour cache."""
    now = time.time()

    # Return cached if fresh
    if "rates" in RATE_CACHE and "timestamp" in RATE_CACHE:
        age = now - RATE_CACHE["timestamp"]
        if age < CACHE_TTL_SECONDS:
            return RATE_CACHE["rates"]

    # Fetch fresh rates
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(RATES_API_URL)
            if response.status_code == 200:
                data = response.json()
                rates = data.get("rates", {})
                if rates:
                    RATE_CACHE["rates"] = rates
                    RATE_CACHE["timestamp"] = now
                    logger.info("Exchange rates updated: %d currencies", len(rates))
                    return rates
    except Exception:
        logger.exception("Failed to fetch exchange rates")

    # Return stale cache if available, otherwise fallback
    if "rates" in RATE_CACHE:
        logger.warning("Using stale exchange rates")
        return RATE_CACHE["rates"]

    # Hardcoded fallback
    logger.warning("Using hardcoded fallback exchange rates")
    return {
        "USD": 1.0, "INR": 83.5, "EUR": 0.92, "GBP": 0.79,
        "AED": 3.67, "JPY": 155.0, "CAD": 1.36, "AUD": 1.53,
    }

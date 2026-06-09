"""Bank statement text parser — extracts transactions from raw text.

Shared between client-side (pdf.js extracts text, JS sends to this parser)
and server-side (pdfplumber extracts text, passed directly).
"""
import re
from datetime import datetime

# Bank detection patterns — first match wins
BANK_PATTERNS = {
    "discover": [r"(?i)discover\s*(bank|card|financial)", r"(?i)discover\b.*statement"],
    "chase": [r"(?i)jpmorgan\s*chase", r"(?i)chase\s*bank", r"(?i)chase\.com"],
    "bofa": [r"(?i)bank\s*of\s*america", r"(?i)bofa"],
    "amex": [r"(?i)american\s*express", r"(?i)amex"],
    "apple": [r"(?i)apple\s*card", r"(?i)goldman\s*sachs.*apple"],
    "hdfc": [r"(?i)hdfc\s*bank", r"(?i)hdfc\s*ltd"],
    "sbi": [r"(?i)state\s*bank\s*of\s*india", r"(?i)\bsbi\b"],
}

# Transaction line pattern: date + description + amount
# Matches: 01/15 AMAZON.COM PURCHASE 45.99
#          01/15 STARBUCKS $5.75
#          01/15 HOTEL BOOKING 1,245.00
#          01/15 PAYMENT RECEIVED -500.00
TRANSACTION_PATTERN = re.compile(
    r"^(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+"  # date: MM/DD or MM/DD/YYYY
    r"(.+?)\s+"                               # description (non-greedy)
    r"(-?\$?[\d,]+\.\d{2})\s*$",             # amount with optional $, commas, negative
    re.MULTILINE
)

# Lines to skip — subtotals, balances, headers
SKIP_PATTERNS = [
    r"(?i)previous\s*balance",
    r"(?i)new\s*balance",
    r"(?i)minimum\s*payment",
    r"(?i)opening\s*balance",
    r"(?i)closing\s*balance",
    r"(?i)total\s*(charges|payments|credits|debits)",
    r"(?i)account\s*(summary|number|ending)",
    r"(?i)statement\s*(period|date|closing)",
    r"(?i)^(date|transaction)\s+(date|description|amount)",
    r"(?i)interest\s*charge",
    r"(?i)annual\s*fee",
    r"(?i)reward|cashback|points",
]


def detect_bank(text: str) -> str | None:
    """Detect which bank issued the statement from raw text."""
    for bank_name, patterns in BANK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return bank_name
    return None


def validate_statement_text(text: str) -> bool:
    """Check if text looks like a bank statement (has transaction-like patterns)."""
    if not text or len(text.strip()) < 20:
        return False

    # Must have at least one line that looks like a transaction
    has_dates = bool(re.search(r"\d{1,2}/\d{1,2}", text))
    has_amounts = bool(re.search(r"\$?[\d,]+\.\d{2}", text))
    return has_dates and has_amounts


def _parse_date_for_comparison(date_str: str) -> tuple[int, int]:
    """Parse MM/DD or MM/DD/YYYY to (month, day) for range filtering."""
    parts = date_str.strip().split("/")
    return int(parts[0]), int(parts[1])


def _is_skip_line(line: str) -> bool:
    """Check if a line should be skipped (subtotals, headers, etc.)."""
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, line):
            return True
    return False


def parse_transactions(
    text: str,
    bank: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Extract transactions from bank statement text.

    Returns list of {"date": str, "description": str, "amount": int (cents)}.
    """
    if not text:
        return []

    transactions = []

    for match in TRANSACTION_PATTERN.finditer(text):
        full_line = match.group(0)

        # Skip non-transaction lines
        if _is_skip_line(full_line):
            continue

        date_str = match.group(1)
        description = match.group(2).strip()
        amount_str = match.group(3).strip()

        # Clean amount: remove $, commas, convert to cents
        amount_clean = amount_str.replace("$", "").replace(",", "")
        try:
            amount_cents = round(float(amount_clean) * 100)
        except ValueError:
            continue

        # Date range filtering
        if date_from or date_to:
            try:
                month, day = _parse_date_for_comparison(date_str)
                if date_from:
                    from_month, from_day = _parse_date_for_comparison(date_from)
                    if (month, day) < (from_month, from_day):
                        continue
                if date_to:
                    to_month, to_day = _parse_date_for_comparison(date_to)
                    if (month, day) > (to_month, to_day):
                        continue
            except (ValueError, IndexError):
                pass

        transactions.append({
            "date": date_str,
            "description": description,
            "amount": amount_cents,
        })

    return transactions

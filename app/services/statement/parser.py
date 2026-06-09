"""Bank statement text parser — extracts transactions from raw text.

Shared between client-side (pdf.js extracts text, JS sends to this parser)
and server-side (pdfplumber extracts text, passed directly).
"""
import re

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
# Matches: 01/15/2026 AMAZON.COM PURCHASE 45.99
#          01/15 STARBUCKS $5.75
#          01/15/26 HOTEL BOOKING 1,245.00
TRANSACTION_PATTERN = re.compile(
    r"^(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+"  # date: MM/DD or MM/DD/YY or MM/DD/YYYY
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

# Auto-categorize by keyword matching
CATEGORY_KEYWORDS = {
    "food": [
        "restaurant", "cafe", "coffee", "starbucks", "mcdonald", "chipotle",
        "subway", "pizza", "burger", "taco", "sushi", "grubhub", "doordash",
        "uber eats", "ubereats", "postmates", "whole foods", "trader joe",
        "grocery", "market", "deli", "bakery", "dunkin", "panera", "chick-fil",
        "wendy", "popeye", "panda express", "ihop", "denny", "applebee",
    ],
    "transport": [
        "uber", "lyft", "taxi", "gas", "shell", "chevron", "exxon", "bp ",
        "fuel", "parking", "toll", "metro", "transit", "airline", "flight",
        "delta", "united", "american air", "southwest", "jetblue", "spirit",
        "amtrak", "rental car", "hertz", "avis", "enterprise",
    ],
    "accommodation": [
        "hotel", "motel", "airbnb", "vrbo", "marriott", "hilton", "hyatt",
        "sheraton", "holiday inn", "best western", "hampton", "booking.com",
    ],
    "shopping": [
        "amazon", "walmart", "target", "costco", "best buy", "apple store",
        "nike", "adidas", "zara", "h&m", "nordstrom", "macy", "gap",
        "old navy", "ikea", "home depot", "lowes",
    ],
    "entertainment": [
        "netflix", "spotify", "hulu", "disney", "hbo", "cinema", "movie",
        "theater", "theatre", "concert", "ticket", "amc", "regal",
        "youtube", "apple music", "gaming", "steam", "playstation", "xbox",
    ],
    "utilities": [
        "electric", "water", "internet", "comcast", "verizon", "at&t",
        "t-mobile", "sprint", "phone", "utility", "power",
    ],
    "rent": [
        "rent", "lease", "mortgage", "property",
    ],
}


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
    has_dates = bool(re.search(r"\d{1,2}/\d{1,2}", text))
    has_amounts = bool(re.search(r"\$?[\d,]+\.\d{2}", text))
    return has_dates and has_amounts


def _parse_date_for_comparison(date_str: str) -> tuple[int, int, int | None]:
    """Parse MM/DD or MM/DD/YY or MM/DD/YYYY to (month, day, year)."""
    parts = date_str.strip().split("/")
    month = int(parts[0])
    day = int(parts[1])
    year = None
    if len(parts) == 3:
        year = int(parts[2])
        if year < 100:
            year += 2000
    return month, day, year


def _date_in_range(date_str: str, date_from: str | None, date_to: str | None) -> bool:
    """Check if a date is within the specified range. Compares (month, day) when no year."""
    try:
        month, day, year = _parse_date_for_comparison(date_str)

        if date_from:
            fm, fd, fy = _parse_date_for_comparison(date_from)
            if year and fy:
                if (year, month, day) < (fy, fm, fd):
                    return False
            else:
                if (month, day) < (fm, fd):
                    return False
        if date_to:
            tm, td, ty = _parse_date_for_comparison(date_to)
            if year and ty:
                if (year, month, day) > (ty, tm, td):
                    return False
            else:
                if (month, day) > (tm, td):
                    return False
    except (ValueError, IndexError):
        pass
    return True


def _auto_categorize(description: str) -> str | None:
    """Match description to a category using keyword matching."""
    description_lower = description.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in description_lower:
                return category
    return None


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

    Returns list of {"date": str, "description": str, "amount": int (cents), "category": str|None}.
    """
    if not text:
        return []

    transactions = []

    for match in TRANSACTION_PATTERN.finditer(text):
        full_line = match.group(0)

        if _is_skip_line(full_line):
            continue

        date_str = match.group(1)
        description = match.group(2).strip()
        amount_str = match.group(3).strip()

        # Clean amount
        amount_clean = amount_str.replace("$", "").replace(",", "")
        try:
            amount_cents = round(float(amount_clean) * 100)
        except ValueError:
            continue

        # Date range filtering
        if not _date_in_range(date_str, date_from, date_to):
            continue

        # Auto-categorize
        category = _auto_categorize(description)

        transactions.append({
            "date": date_str,
            "description": description,
            "amount": amount_cents,
            "category": category,
        })

    return transactions

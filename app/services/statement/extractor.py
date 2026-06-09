"""PDF statement extractor — server-side (mobile fallback).

Reads PDF bytes in memory, extracts text, passes to parser.
Never writes to disk. Bytes wiped after extraction.
"""
import io
import logging

import pdfplumber

from app.services.statement.parser import detect_bank, parse_transactions, validate_statement_text

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
PDF_MAGIC_BYTES = b"%PDF"


def validate_pdf_bytes(file_bytes: bytes) -> str | None:
    """Validate file is a real PDF. Returns error message or None if valid."""
    if not file_bytes:
        return "Empty file"
    if len(file_bytes) > MAX_FILE_SIZE:
        return "File too large (max 10MB)"
    if not file_bytes[:4] == PDF_MAGIC_BYTES:
        return "Not a valid PDF file"
    return None


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract all text from a PDF in memory. Never touches disk."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def process_statement(
    file_bytes: bytes,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Full pipeline: validate → extract text → detect bank → parse transactions.

    Returns {"bank": str|None, "transactions": list, "error": str|None}.
    File bytes are not retained after this function returns.
    """
    # Step 1: Validate PDF
    validation_error = validate_pdf_bytes(file_bytes)
    if validation_error:
        return {"bank": None, "transactions": [], "error": validation_error}

    # Step 2: Extract text
    try:
        text = extract_text_from_pdf(file_bytes)
    except Exception as exc:
        logger.exception("Failed to extract text from PDF")
        return {"bank": None, "transactions": [], "error": f"Could not read PDF: {exc}"}

    # Step 3: Validate it looks like a bank statement
    if not validate_statement_text(text):
        return {"bank": None, "transactions": [], "error": "This doesn't look like a bank statement. No transactions found."}

    # Step 4: Detect bank
    bank = detect_bank(text)

    # Step 5: Parse transactions
    transactions = parse_transactions(text, bank or "generic", date_from=date_from, date_to=date_to)

    if not transactions:
        return {"bank": bank, "transactions": [], "error": "No transactions found in the selected date range."}

    return {"bank": bank, "transactions": transactions, "error": None}

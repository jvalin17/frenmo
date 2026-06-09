"""Tests for bank statement text parsing — extract transactions from raw text."""
from app.services.statement.parser import parse_transactions, detect_bank, validate_statement_text


class TestDetectBank:
    def test_detect_discover(self):
        text = "Discover Bank\nAccount Number ending in 1234\nTransaction Date\nDescription\nAmount"
        assert detect_bank(text) == "discover"

    def test_detect_chase(self):
        text = "JPMorgan Chase Bank\nAccount Number: ****5678\nDate\nDescription\nAmount"
        assert detect_bank(text) == "chase"

    def test_detect_bofa(self):
        text = "Bank of America\nAccount # ending in 9012\nDate\nDescription\nAmount"
        assert detect_bank(text) == "bofa"

    def test_detect_amex(self):
        text = "American Express\nStatement Period\nDate\nDescription\nAmount"
        assert detect_bank(text) == "amex"

    def test_detect_unknown(self):
        text = "Hello world this is a random document"
        assert detect_bank(text) is None


class TestValidateStatement:
    def test_valid_statement(self):
        text = "Discover Bank\n01/15 AMAZON.COM 45.99\n01/16 UBER TRIP 23.50"
        assert validate_statement_text(text) is True

    def test_not_a_statement(self):
        text = "Dear sir, this is a letter about your application."
        assert validate_statement_text(text) is False

    def test_empty_text(self):
        assert validate_statement_text("") is False


class TestParseTransactions:
    def test_parse_basic_transactions(self):
        text = """Discover Bank
01/15 AMAZON.COM PURCHASE 45.99
01/16 UBER TRIP SF 23.50
01/17 WHOLE FOODS MKT 87.20
"""
        transactions = parse_transactions(text, "discover")
        assert len(transactions) == 3
        assert transactions[0]["date"] == "01/15"
        assert transactions[0]["description"] == "AMAZON.COM PURCHASE"
        assert transactions[0]["amount"] == 4599

    def test_parse_with_dollar_sign(self):
        text = "01/15 STARBUCKS $5.75"
        transactions = parse_transactions(text, "discover")
        assert len(transactions) == 1
        assert transactions[0]["amount"] == 575

    def test_parse_skips_non_transaction_lines(self):
        text = """Discover Bank
Account Summary
Previous Balance 1,234.56
01/15 AMAZON.COM 45.99
New Balance 1,280.55
Minimum Payment Due 25.00
"""
        transactions = parse_transactions(text, "discover")
        assert len(transactions) == 1
        assert transactions[0]["description"] == "AMAZON.COM"

    def test_parse_handles_commas_in_amount(self):
        text = "01/15 HOTEL BOOKING 1,245.00"
        transactions = parse_transactions(text, "discover")
        assert len(transactions) == 1
        assert transactions[0]["amount"] == 124500

    def test_parse_negative_amounts(self):
        text = "01/15 PAYMENT RECEIVED -500.00"
        transactions = parse_transactions(text, "discover")
        assert len(transactions) == 1
        assert transactions[0]["amount"] == -50000

    def test_parse_empty_returns_empty(self):
        transactions = parse_transactions("", "discover")
        assert transactions == []

    def test_parse_with_date_range(self):
        text = """01/10 UBER 15.00
01/15 AMAZON 45.99
01/20 WHOLE FOODS 87.20
01/25 TARGET 32.00
"""
        transactions = parse_transactions(text, "discover", date_from="01/14", date_to="01/21")
        assert len(transactions) == 2
        assert transactions[0]["description"] == "AMAZON"
        assert transactions[1]["description"] == "WHOLE FOODS"

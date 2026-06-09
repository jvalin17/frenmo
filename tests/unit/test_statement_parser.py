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
        assert transactions[0]["category"] == "shopping"  # AMAZON
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


class TestBankDetection:
    def test_detect_capital_one(self):
        text = "Capital One\nStatement Period\nDec 30 STARBUCKS $5.75"
        assert detect_bank(text) == "capital_one"

    def test_detect_citi(self):
        text = "Citibank\nAccount ending in 1234\n01/05 01/07 COSTCO 125.43"
        assert detect_bank(text) == "citi"

    def test_detect_wells_fargo(self):
        text = "Wells Fargo Bank\nChecking Summary\n01/15 DIRECT DEPOSIT 2500.00"
        assert detect_bank(text) == "wells_fargo"

    def test_detect_apple_card(self):
        text = "Apple Card\nGoldman Sachs\n10/03/2019 MERCHANT 2% $1.29 $64.31"
        assert detect_bank(text) == "apple"

    def test_detect_usbank(self):
        text = "U.S. Bank\nAccount Statement\n01/15 AMAZON 45.99"
        assert detect_bank(text) == "usbank"


class TestChaseParser:
    def test_chase_credit_card(self):
        text = """JPMorgan Chase Bank
01/23 AMAZON MKTPLACE PMTS AMZN.COM/BILL WA 12.34
01/04 CICEROS PIZZA SAN JOSE CA 28.18
01/01 AUTOMATIC PAYMENT - THANK YOU -10.99
"""
        transactions = parse_transactions(text, "chase")
        assert len(transactions) == 3  # includes payment as negative
        assert transactions[0]["amount"] == 1234
        assert transactions[0]["description"] == "AMAZON MKTPLACE PMTS AMZN.COM/BILL WA"


class TestAmexParser:
    def test_amex_with_year(self):
        text = """American Express
01/23/21 PHOTOGPHY PLAN NEW YORK NY 1.99
02/15/21 WHOLE FOODS MKT SAN FRANCISCO CA 87.45
"""
        transactions = parse_transactions(text, "amex")
        assert len(transactions) == 2
        assert transactions[0]["date"] == "01/23/21"
        assert transactions[0]["amount"] == 199

    def test_amex_asterisk_date(self):
        text = "01/23/21* PENDING CHARGE NYC NY 5.00"
        transactions = parse_transactions(text, "amex")
        assert len(transactions) == 1


class TestBofaParser:
    def test_bofa_two_dates(self):
        text = """Bank of America
12/05 12/07 WHOLE FOODS SF CA 8538 3456 251.49
01/15 01/17 AMAZON.COM AMZN.COM/BILLWA 1234 5678 15.99
"""
        transactions = parse_transactions(text, "bofa")
        assert len(transactions) == 2
        assert transactions[0]["date"] == "12/05"
        assert transactions[0]["amount"] == 25149


class TestCapitalOneParser:
    def test_capital_one_named_months(self):
        text = """Capital One
Dec 30 NYTIMES 800-698-4637NY $10.00
Jan 05 AMAZON.COM AMZN.COM/BILLWA $45.99
"""
        transactions = parse_transactions(text, "capital_one")
        assert len(transactions) == 2
        assert transactions[0]["date"] == "12/30"
        assert transactions[0]["amount"] == 1000
        assert transactions[1]["date"] == "01/05"


class TestAppleCardParser:
    def test_apple_card_with_cashback(self):
        text = """Apple Card
10/03/2024 FOO BAR MERCHANT CITY ST 2% $1.29 $64.31
11/15/2024 APPLE.COM/BILL CA 3% $0.30 $9.99
"""
        transactions = parse_transactions(text, "apple")
        assert len(transactions) == 2
        assert transactions[0]["date"] == "10/03/2024"
        assert transactions[0]["amount"] == 6431  # last $ amount
        assert transactions[1]["amount"] == 999


class TestWellsFargoParser:
    def test_wells_fargo_basic(self):
        text = """Wells Fargo
01/15 DIRECT DEPOSIT ACME CORP 2500.00
01/18 ONLINE PAYMENT CHASE CARD 500.00
"""
        transactions = parse_transactions(text, "wells_fargo")
        assert len(transactions) == 2
        assert transactions[0]["amount"] == 250000

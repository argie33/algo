#!/usr/bin/env python3
"""Tests for Form 4 plain-text parser."""

import unittest
from datetime import date

from utils.external.form4_plaintext_parser import Form4PlaintextParser


class TestForm4PlaintextParser(unittest.TestCase):
    """Test Form 4 plain-text parsing."""

    def test_extract_insider_name(self):
        """Test insider name extraction."""
        content = """
        FORM 4
        Reporting Owner Name: John Smith
        Officer Title: Chief Executive Officer
        """
        name = Form4PlaintextParser._extract_insider_name(content, "AAPL")
        self.assertEqual(name, "John Smith")

    def test_extract_insider_title(self):
        """Test insider title extraction."""
        content = """
        Officer Title: President and CEO
        """
        title = Form4PlaintextParser._extract_insider_title(content, "AAPL")
        self.assertIn("President", title)

    def test_extract_shares_owned(self):
        """Test shares owned extraction."""
        content = """
        Shares Owned Following Transaction: 1,234,567
        """
        shares = Form4PlaintextParser._extract_shares_owned(content, "AAPL")
        self.assertEqual(shares, 1234567)

    def test_extract_shares_owned_with_decimals(self):
        """Test shares owned extraction with decimals."""
        content = """
        Shares Following: 1,234,567.50
        """
        shares = Form4PlaintextParser._extract_shares_owned(content, "AAPL")
        self.assertEqual(shares, 1234567)

    def test_extract_ownership_pct(self):
        """Test ownership percentage extraction."""
        content = """
        % of Class: 2.5%
        """
        pct = Form4PlaintextParser._extract_ownership_pct(content, "AAPL")
        self.assertAlmostEqual(pct, 2.5)

    def test_extract_transactions(self):
        """Test transaction extraction."""
        content = """
        Non-Derivative Transactions

        2024-01-15 | A | 1,000
        2024-01-20 | D | 500
        2024-02-01 | A | 2,500
        """
        buys, sells, net, latest_date = Form4PlaintextParser._extract_transactions(content, "AAPL")
        self.assertEqual(buys, 2)  # Two acquisitions
        self.assertEqual(sells, 1)  # One disposition
        self.assertEqual(net, 3000)  # 1000 + 2500 - 500
        self.assertEqual(latest_date, date(2024, 2, 1))

    def test_parse_complete_form4(self):
        """Test parsing complete Form 4 document."""
        content = """
        FORM 4 - INSIDER TRADING FORM

        Reporting Owner Name: Jane Doe
        Officer Title: Vice President, Finance

        Non-Derivative Transactions

        2024-03-10 | A | 5,000
        2024-03-15 | A | 2,000
        2024-03-20 | D | 1,000

        Shares Owned Following Transaction: 50,000
        % of Class: 0.5%
        """
        result = Form4PlaintextParser.parse(content, "AAPL")

        self.assertIsNotNone(result)
        self.assertEqual(result["insider_name"], "Jane Doe")
        self.assertEqual(result["shares_owned"], 50000)
        self.assertAlmostEqual(result["ownership_pct"], 0.5)
        self.assertEqual(result["recent_buys"], 2)
        self.assertEqual(result["recent_sells"], 1)
        self.assertEqual(result["net_transactions"], 6000)

    def test_parse_invalid_content(self):
        """Test parsing invalid content returns None."""
        result = Form4PlaintextParser.parse("", "AAPL")
        self.assertIsNone(result)

        result = Form4PlaintextParser.parse(None, "AAPL")
        self.assertIsNone(result)

    def test_parse_missing_required_fields(self):
        """Test parsing with missing required fields."""
        # Missing insider name
        content = """
        Officer Title: CEO
        Shares Owned Following Transaction: 5,000
        % of Class: 0.1%
        """
        result = Form4PlaintextParser.parse(content, "AAPL")
        self.assertIsNone(result)

    def test_find_transaction_section(self):
        """Test transaction section discovery."""
        content = """
        Some header text

        Non-Derivative Transactions
        2024-03-10 | A | 5,000

        Derivative Transactions
        Some other content
        """
        section = Form4PlaintextParser._find_transaction_section(content)
        self.assertIn("2024-03-10", section)
        self.assertNotIn("Derivative", section)

    def test_extract_transactions_no_section(self):
        """Test extraction when no transaction section found."""
        content = "Just some text without transaction data"
        buys, sells, net, latest_date = Form4PlaintextParser._extract_transactions(content, "AAPL")
        self.assertEqual(buys, 0)
        self.assertEqual(sells, 0)
        self.assertEqual(net, 0)
        self.assertIsNone(latest_date)


if __name__ == "__main__":
    unittest.main()

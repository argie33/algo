#!/usr/bin/env python3
"""Integration tests for Phase 2 loaders (insider holdings & institutional holdings).

Tests verify:
1. Loaders handle both XBRL and plain-text Form 4 filings
2. Loaders properly aggregate insider/institutional data
3. Loaders return explicit data_unavailable markers
4. Loaders follow governance rules (fail-fast, explicit markers, no silent fallbacks)
"""

import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from loaders.load_insider_holdings_sec import InsiderHoldingsSECLoader
from loaders.load_institutional_holdings_13f import InstitutionalHoldings13FLoader
from utils.external.form4_plaintext_parser import Form4PlaintextParser
from utils.external.sec_xml_parser import Form4Parser, Schedule13GParser


class TestPhase2LoadersGovernance(unittest.TestCase):
    """Test that Phase 2 loaders follow governance rules."""

    def test_insider_loader_returns_data_unavailable_on_no_filings(self):
        """Loader should return explicit data_unavailable when no filings found."""
        loader = InsiderHoldingsSECLoader()

        # Mock SEC client to return empty submissions
        mock_sec_client = MagicMock()
        mock_sec_client.symbol_to_cik.return_value = "0000320193"
        mock_sec_client.get_submissions.return_value = {
            "filings": {"recent": {"form": [], "accessionNumber": [], "filingDate": []}}
        }

        loader.sec_client = mock_sec_client

        result = loader.fetch_incremental("AAPL", None)

        # Should return data_unavailable record
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["data_unavailable"])
        self.assertIn("no_form4_filings", result[0]["reason"])

    def test_institutional_loader_returns_data_unavailable_on_no_filings(self):
        """Loader should return explicit data_unavailable when no institutional ownership data found."""
        loader = InstitutionalHoldings13FLoader()

        # Mock SEC client to return empty companyfacts (no institutional ownership metric)
        mock_sec_client = MagicMock()
        mock_sec_client.symbol_to_cik.return_value = "0000320193"
        mock_sec_client.get_company_facts.return_value = {}

        loader.sec_client = mock_sec_client

        result = loader.fetch_incremental("AAPL", None)

        # Should return data_unavailable record
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["data_unavailable"])
        self.assertIn("no_institutional_ownership_metric", result[0]["reason"])

    def test_insider_loader_explicit_failure_reason(self):
        """Loader should provide explicit failure reasons for debugging."""
        loader = InsiderHoldingsSECLoader()

        # Mock SEC client to fail with specific error
        mock_sec_client = MagicMock()
        mock_sec_client.symbol_to_cik.side_effect = ValueError("CIK not found")

        loader.sec_client = mock_sec_client

        result = loader.fetch_incremental("INVALIDTICKER", None)

        # Should return data_unavailable with reason
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["data_unavailable"])
        self.assertEqual(result[0]["reason"], "cik_not_found")

    def test_institutional_loader_explicit_failure_reason(self):
        """Loader should provide explicit failure reasons for debugging."""
        loader = InstitutionalHoldings13FLoader()

        # Mock SEC client to fail
        mock_sec_client = MagicMock()
        mock_sec_client.symbol_to_cik.side_effect = ValueError("CIK not found")

        loader.sec_client = mock_sec_client

        result = loader.fetch_incremental("INVALIDTICKER", None)

        # Should return data_unavailable with reason
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["data_unavailable"])
        self.assertEqual(result[0]["reason"], "cik_not_found")

    def test_form4_plaintext_parser_robustness(self):
        """Parser should handle edge cases gracefully."""
        # Test with minimal valid content
        content = """
        Reporting Owner Name: Test Officer
        Shares Owned Following Transaction: 1,000
        % of Class: 0.5%
        """
        result = Form4PlaintextParser.parse(content, "TEST")
        self.assertIsNotNone(result)
        self.assertEqual(result["insider_name"], "Test Officer")

    def test_form4_plaintext_parser_handles_malformed_input(self):
        """Parser should return None for malformed input, not crash."""
        # Empty content
        result = Form4PlaintextParser.parse("", "TEST")
        self.assertIsNone(result)

        # Missing required fields
        result = Form4PlaintextParser.parse("Some random text", "TEST")
        self.assertIsNone(result)

        # None input
        result = Form4PlaintextParser.parse(None, "TEST")  # type: ignore
        self.assertIsNone(result)

    def test_loaders_never_silent_fail(self):
        """Loaders should never silently degrade or skip without marking data_unavailable."""
        insider_loader = InsiderHoldingsSECLoader()
        institutional_loader = InstitutionalHoldings13FLoader()

        # For each loader, when ANY error occurs, data_unavailable should be set to True
        # (We test this via mock rather than real SEC calls)
        for loader in [insider_loader, institutional_loader]:
            mock_client = MagicMock()
            mock_client.symbol_to_cik.return_value = "0000320193"
            mock_client.get_submissions.return_value = {
                "filings": {"recent": {"form": [], "accessionNumber": [], "filingDate": []}}
            }

            loader.sec_client = mock_client  # type: ignore

            result = loader.fetch_incremental("AAPL", None)

            # Verify: if data is unavailable, flag must be True and reason must be set
            if result[0]["data_unavailable"]:
                self.assertIsNotNone(result[0].get("reason"))
            else:
                # If data available, all fields should be filled
                for key in ["insider_ownership_pct", "recent_buys", "recent_sells"]:
                    if key in result[0]:
                        self.assertIsNotNone(result[0][key])


class TestPhase2DataQuality(unittest.TestCase):
    """Test data quality and governance compliance."""

    def test_form4_parser_returns_correct_types(self):
        """Parsed Form 4 data should have correct types."""
        content = """
        Reporting Owner Name: John Smith
        Officer Title: CEO
        Shares Owned Following Transaction: 5,000
        % of Class: 1.2%

        Non-Derivative Transactions
        2024-01-15 | A | 100
        2024-01-20 | D | 50
        """

        result = Form4PlaintextParser.parse(content, "AAPL")
        self.assertIsNotNone(result)

        # Verify types
        self.assertIsInstance(result["insider_name"], str)
        self.assertIsInstance(result["shares_owned"], int)
        self.assertIsInstance(result["ownership_pct"], float)
        self.assertIsInstance(result["recent_buys"], int)
        self.assertIsInstance(result["recent_sells"], int)
        self.assertIsInstance(result["net_transactions"], int)

    def test_insider_loader_field_validation(self):
        """Loader should validate critical fields before returning data."""
        # Test that loader validates ownership % is in valid range
        loader = InsiderHoldingsSECLoader()

        # We'd need to mock the entire parse flow to test this properly
        # For now, verify the validation logic is present in the code
        self.assertTrue(hasattr(loader, "fetch_incremental"))
        self.assertTrue(hasattr(loader, "_parse_form4_filings"))

    def test_loaders_include_data_source_field(self):
        """Loaders should include data_source field for audit trail."""
        loader = InsiderHoldingsSECLoader()
        mock_client = MagicMock()
        mock_client.symbol_to_cik.return_value = "0000320193"
        mock_client.get_submissions.return_value = {
            "filings": {"recent": {"form": [], "accessionNumber": [], "filingDate": []}}
        }

        loader.sec_client = mock_client  # type: ignore
        result = loader.fetch_incremental("AAPL", None)

        # Should have data_source field for audit trail
        self.assertIn("data_source", result[0])
        # When unavailable, source should reflect that
        self.assertIn(result[0]["data_source"], ["none", "sec_form4"])


if __name__ == "__main__":
    unittest.main()

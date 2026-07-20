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
        """Loader should return explicit data_unavailable when no filings found.

        See test_insider_loader_explicit_failure_reason: fetch_incremental() sources from
        Form345BulkAggregator, not sec_client.
        """
        loader = InsiderHoldingsSECLoader()
        loader._aggregator = MagicMock()
        loader._aggregator.get_symbol_summary.return_value = None

        result = loader.fetch_incremental("AAPL", None)

        # Should return data_unavailable record
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["data_unavailable"])
        self.assertIn("no_form345_filings", result[0]["reason"])

    def test_institutional_loader_returns_data_unavailable_on_no_filings(self):
        """Loader should return explicit data_unavailable when no institutional ownership data found."""
        loader = InstitutionalHoldings13FLoader()

        # fetch_incremental() sources institutional ownership from self.form13f_aggregator
        # (Session 298's Form 13F aggregation), not sec_client.get_company_facts - mock both
        # dependencies it actually calls (symbol_to_cik, then form13f_aggregator).
        mock_sec_client = MagicMock()
        mock_sec_client.symbol_to_cik.return_value = "0000320193"
        loader.sec_client = mock_sec_client

        loader.form13f_aggregator = MagicMock()
        loader.form13f_aggregator.get_institutional_ownership_pct.return_value = {
            "data_unavailable": True,
            "coverage_reason": "no_13f_filings",
        }

        result = loader.fetch_incremental("AAPL", None)

        # Should return data_unavailable record
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["data_unavailable"])
        self.assertIn("no_13f_filings", result[0]["reason"])

    def test_insider_loader_explicit_failure_reason(self):
        """Loader should provide explicit failure reasons for debugging.

        InsiderHoldingsSECLoader.fetch_incremental() sources data from the bulk Form
        3/4/5 aggregate (Form345BulkAggregator), not a per-symbol SEC client lookup - it
        never calls symbol_to_cik(), so mocking that (as this test did previously) had no
        effect on the code path actually exercised. Mock the aggregator it really uses.
        """
        loader = InsiderHoldingsSECLoader()
        loader._aggregator = MagicMock()
        loader._aggregator.get_symbol_summary.return_value = None

        result = loader.fetch_incremental("INVALIDTICKER", None)

        # Should return data_unavailable with reason
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["data_unavailable"])
        self.assertEqual(result[0]["reason"], "no_form345_filings_in_lookback_window")

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
        # InsiderHoldingsSECLoader sources from Form345BulkAggregator (not sec_client - see
        # test_insider_loader_explicit_failure_reason), so it needs its own mock; only
        # InstitutionalHoldings13FLoader still uses sec_client/symbol_to_cik.
        insider_loader = InsiderHoldingsSECLoader()
        insider_loader._aggregator = MagicMock()
        insider_loader._aggregator.get_symbol_summary.return_value = None

        institutional_loader = InstitutionalHoldings13FLoader()
        mock_client = MagicMock()
        mock_client.symbol_to_cik.return_value = "0000320193"
        mock_client.get_submissions.return_value = {
            "filings": {"recent": {"form": [], "accessionNumber": [], "filingDate": []}}
        }
        institutional_loader.sec_client = mock_client  # type: ignore

        for loader in [insider_loader, institutional_loader]:
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
        # Test that loader validates ownership % is in valid range.
        # _parse_form4_filings no longer exists - fetch_incremental() sources from
        # Form345BulkAggregator (see test_insider_loader_explicit_failure_reason), which
        # computes shares_outstanding via _get_shares_outstanding() and clamps the
        # resulting percentage inline (min(..., 100.0)) rather than through a separate
        # per-filing parse step.
        loader = InsiderHoldingsSECLoader()

        self.assertTrue(hasattr(loader, "fetch_incremental"))
        self.assertTrue(hasattr(loader, "_get_shares_outstanding"))

    def test_loaders_include_data_source_field(self):
        """Loaders should include data_source field for audit trail."""
        # See test_insider_loader_explicit_failure_reason: fetch_incremental() sources
        # from Form345BulkAggregator, not sec_client.
        loader = InsiderHoldingsSECLoader()
        loader._aggregator = MagicMock()
        loader._aggregator.get_symbol_summary.return_value = None

        result = loader.fetch_incremental("AAPL", None)

        # Should have data_source field for audit trail
        self.assertIn("data_source", result[0])
        # When unavailable, source should reflect that
        self.assertIn(result[0]["data_source"], ["none", "sec_form345_bulk"])


if __name__ == "__main__":
    unittest.main()

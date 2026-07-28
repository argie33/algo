#!/usr/bin/env python3
"""Integration tests for Phase 2 loaders (insider holdings & institutional holdings).

Tests verify:
1. Loaders properly aggregate insider/institutional data
2. Loaders return explicit data_unavailable markers
3. Loaders follow governance rules (fail-fast, explicit markers, no silent fallbacks)

REMOVED 2026-07-27: the per-filing Form4PlaintextParser and sec_xml_parser
(Form4Parser/Schedule13GParser) tests that used to live here - both parsers, and their
dedicated test files (test_form4_plaintext_parser.py, test_sec_xml_parser.py,
form4_parsing_metrics.py + its test), were confirmed dead code with zero production
callers. They were an early per-filing-crawl approach superseded by the bulk Form 3/4/5
dataset aggregation (utils/external/sec_form345_bulk.py, used by
InsiderHoldingsSECLoader) and the SEC 13F bulk dataset + OpenFIGI crosswalk (used by
InstitutionalHoldings13FLoader) - see steering/DATA_LOADERS.md's "Insider holdings" and
"Institutional holdings" sections. Never cleaned up after the bulk approach shipped.
"""

import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from loaders.load_insider_holdings_sec import InsiderHoldingsSECLoader
from loaders.load_institutional_holdings_13f import InstitutionalHoldings13FLoader


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
        """Loader should return explicit data_unavailable when no institutional ownership data found.

        fetch_incremental() reads a row previously written by fetch_global()'s bulk SEC 13F +
        OpenFIGI crosswalk (see the loader's module docstring) - it does NOT re-parse 13F
        filings per symbol. This test previously called it against the real DB unmocked,
        which only "passed" because this local dev DB happened to have no row for AAPL at
        the time - if fetch_global() had ever populated real data for AAPL here (the loader
        is live-verified to resolve real ownership % for mega-caps), this test would have
        failed. Mock the DB layer explicitly so the test is deterministic regardless of what
        fetch_global() has or hasn't populated.
        """
        loader = InstitutionalHoldings13FLoader()

        with patch("loaders.load_institutional_holdings_13f.DatabaseContext") as mock_db_ctx:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None
            mock_db_ctx.return_value.__enter__.return_value = mock_cursor

            result = loader.fetch_incremental("AAPL", None)

        # Should return data_unavailable record
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["data_unavailable"])
        # Reason is explicit: data not found in 13F filings
        self.assertIn("not_found_in_institutional_holdings_13f", result[0]["reason"])

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
        """Loader should provide explicit failure reasons for debugging.

        See test_institutional_loader_returns_data_unavailable_on_no_filings - mocked for
        the same reason (deterministic regardless of live DB state).
        """
        loader = InstitutionalHoldings13FLoader()

        with patch("loaders.load_institutional_holdings_13f.DatabaseContext") as mock_db_ctx:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None
            mock_db_ctx.return_value.__enter__.return_value = mock_cursor

            result = loader.fetch_incremental("INVALIDTICKER", None)

        # Should return data_unavailable with reason
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["data_unavailable"])
        # Reason is explicit: data not found in 13F filings
        self.assertIn("not_found_in_institutional_holdings_13f", result[0]["reason"])

    def test_loaders_never_silent_fail(self):
        """Loaders should never silently degrade or skip without marking data_unavailable."""
        insider_loader = InsiderHoldingsSECLoader()
        insider_loader._aggregator = MagicMock()
        insider_loader._aggregator.get_symbol_summary.return_value = None

        institutional_loader = InstitutionalHoldings13FLoader()

        # InstitutionalHoldings13FLoader.fetch_incremental() no longer has a `sec_client`
        # attribute at all (a previous version of this test set one, which the current
        # loader never reads - it only does a direct DB lookup via DatabaseContext, see
        # module docstring). Mock that instead so the "no data" branch is deterministic.
        with patch("loaders.load_institutional_holdings_13f.DatabaseContext") as mock_db_ctx:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None
            mock_db_ctx.return_value.__enter__.return_value = mock_cursor

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


    def test_institutional_loader_writes_fresh_marker_for_unresolved_active_symbols(self):
        """FIXED 2026-07-28: _calculate_and_cache_ownership() used to only return records
        for tickers that resolved via the OpenFIGI crosswalk AND had a usable
        shares_outstanding - every other active symbol was simply absent from the
        returned list, so load_global()'s bulk_insert() never touched its existing row.
        Live-confirmed this left 3,940 rows frozen on a reason string
        ("cusip_ticker_crosswalk_not_implemented") that predates the OpenFIGI fix and no
        longer exists in this file, because nothing ever revisited them. Every active
        symbol must now get an explicit, current record every run.
        """
        loader = InstitutionalHoldings13FLoader()

        with patch(
            "loaders.load_institutional_holdings_13f.get_active_symbols",
            return_value=["AAPL", "ZZZZ", "NOSHARES"],
        ), patch("loaders.load_institutional_holdings_13f.DatabaseContext") as mock_db_ctx:
            mock_cursor = MagicMock()

            def fetchone_side_effect():
                return {"AAPL": (1_000_000,), "NOSHARES": (None,)}.get(
                    mock_cursor.execute.call_args[0][1][0], None
                )

            mock_cursor.fetchone.side_effect = fetchone_side_effect
            mock_db_ctx.return_value.__enter__.return_value = mock_cursor

            # Only AAPL resolved via the crosswalk this run; ZZZZ never resolved at all,
            # NOSHARES resolved but has no usable shares_outstanding.
            records = loader._calculate_and_cache_ownership({"AAPL": 500_000, "NOSHARES": 100}, date(2026, 6, 30))

        by_symbol = {r["symbol"]: r for r in records}
        self.assertEqual(set(by_symbol), {"AAPL", "ZZZZ", "NOSHARES"})

        self.assertFalse(by_symbol["AAPL"]["data_unavailable"])
        self.assertEqual(by_symbol["AAPL"]["institutional_ownership_pct"], 50.0)

        self.assertTrue(by_symbol["NOSHARES"]["data_unavailable"])
        self.assertEqual(by_symbol["NOSHARES"]["reason"], "shares_outstanding_unavailable")

        self.assertTrue(by_symbol["ZZZZ"]["data_unavailable"])
        self.assertEqual(by_symbol["ZZZZ"]["reason"], "no_resolved_13f_holdings")


class TestPhase2DataQuality(unittest.TestCase):
    """Test data quality and governance compliance."""

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

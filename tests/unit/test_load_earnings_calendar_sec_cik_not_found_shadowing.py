"""Regression test for loaders/load_earnings_calendar_sec.py.

BUG FOUND 2026-08-21 (same bug class as load_sec_segment_info.py's/
load_current_reports_8k.py's/load_dividend_data.py's/the analyst loaders' pre-fix
marker retraction fixes): a transient SEC-ticker-cache miss on symbol_to_cik() wrote a
"cik_not_found" marker unconditionally, with no check for prior real coverage. Since
this marker's filing_date defaults to today() when no existing marker is on file (see
_unavailable_record's own docstring), it permanently outranks any real historical
earnings-date row in a "latest filing_date" read - live-confirmed 5 symbols (BNZI,
GRAF, GV, NUTR, QMMM) shadowed this way despite real coverage on record.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_earnings_calendar_sec import EarningsCalendarSECLoader


def _make_loader() -> EarningsCalendarSECLoader:
    loader = EarningsCalendarSECLoader.__new__(EarningsCalendarSECLoader)
    loader.sec_client = MagicMock()
    return loader


def _fake_db_context(delete_rowcount: int = 0):
    cur = MagicMock()
    cur.rowcount = delete_rowcount
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cur)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, cur


class TestCikNotFoundMarkerShadowing:
    def test_already_covered_symbol_skips_and_retracts_marker(self) -> None:
        loader = _make_loader()
        loader.sec_client.symbol_to_cik.side_effect = ValueError("not found")
        ctx, cur = _fake_db_context()

        with (
            patch.object(loader, "_has_prior_real_coverage", return_value=True),
            patch("loaders.load_earnings_calendar_sec.DatabaseContext", return_value=ctx),
        ):
            result = loader.fetch_incremental("BNZI", since=None)

        assert result == []
        query, params = cur.execute.call_args[0]
        assert "DELETE FROM earnings_calendar_sec" in query
        assert "data_unavailable = true" in query
        assert params == ("BNZI",)

    def test_never_covered_symbol_still_gets_the_marker(self) -> None:
        loader = _make_loader()
        loader.sec_client.symbol_to_cik.side_effect = ValueError("not found")
        # _unavailable_record() itself does a real-ish DatabaseContext("read") lookup
        # for an existing marker's filing_date - mock it out so this stays a real unit
        # test, not an implicit live-DB dependency.
        cur = MagicMock()
        cur.fetchone.return_value = None
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=cur)
        ctx.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(loader, "_has_prior_real_coverage", return_value=False),
            patch("loaders.load_earnings_calendar_sec.DatabaseContext", return_value=ctx),
        ):
            result = loader.fetch_incremental("ZZZZ", since=None)

        assert len(result) == 1
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "cik_not_found"

    def test_has_prior_real_coverage_checks_data_unavailable_false(self) -> None:
        cur = MagicMock()
        cur.fetchone.return_value = (1,)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=cur)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch("loaders.load_earnings_calendar_sec.DatabaseContext", return_value=ctx):
            assert EarningsCalendarSECLoader._has_prior_real_coverage("AAPL") is True

        query, params = cur.execute.call_args[0]
        assert "data_unavailable = false" in query
        assert params == ("AAPL",)

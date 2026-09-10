"""Regression test for a 2026-08-31 fix (goal: data-coverage sweep, GENI follow-up to
sec_valuations_frozen_yfinance_snapshot_live_recheck_fixed_20260831) to load_sec_valuations.py.

The `shares_outstanding_dei` cover-page fallback (`ORDER BY fiscal_year DESC LIMIT 1`) had no
staleness bound at all - unlike every sibling tier in this cascade. Live-confirmed via GENI
(Genius Sports): its ONLY shares_outstanding_dei entry across all fiscal years is FY2021's
18,500,000 (a SPAC-de-merger-year founder/sponsor-share figure) - real current shares are
~254.76M. Because GENI is a foreign private issuer, every earlier tier is gated off, so this
5-year-stale value became the entire resolved shares_out, producing market_cap=$148.37M (real:
~$2.04B) - a ~14x undercount.

Fix: the query now requires `fiscal_year >= (this year - 2)`, matching the 2-year recency
convention already used elsewhere in this codebase's staleness guards.

UPDATED 2026-08-31 (same-day follow-up, PHAR/IONR/JZXN/MI incident): this tier is now ALSO gated
on `not is_foreign_private_issuer` (a separate, second bug found the same session - see
load_sec_valuations.py's own comment on this tier) - it no longer fires for GENI-shaped fixtures
at all, since GENI is FPI. Test 1 below was re-targeted to a DOMESTIC-filer fixture (the tier
still matters there - e.g. GEF/DGICA/MC-shaped filers per this tier's own module comment) to keep
covering the recency-bound logic itself. Test 2 (the FPI end-to-end unavailable-marker case)
still applies as before, just with the now-dead company_info_sec/dei fetchone entries removed.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _RecordingCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self.executed: list[tuple[str, Any]] = []
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, params: Any = None) -> None:
        self.executed.append((query, params))

    def fetchall(self) -> list[tuple[Any, ...]]:
        result = self._fetchall_results[self._fetchall_idx]
        self._fetchall_idx += 1
        return result

    def fetchone(self) -> tuple[Any, ...] | None:
        # 2026-09-06: _sanity_check_shares_outstanding_vs_volume added one more fetchone() call
        # to the pipeline (see that method's own docstring) - same graceful-degradation
        # precedent as this class's own fetchall() (added 2026-09-05 for an identical reason):
        # return None (a real "no matching row") rather than IndexError once the scripted
        # sequence is exhausted, since these fixtures don't script that query's result.
        if self._fetchone_idx >= len(self._fetchone_results):
            return None
        result = self._fetchone_results[self._fetchone_idx]
        self._fetchone_idx += 1
        return result


def _run_fetch_incremental(
    symbol: str, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]
) -> tuple[list[dict[str, Any]], _RecordingCursor]:
    loader = _make_loader()
    fake_cursor = _RecordingCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        result = loader.fetch_incremental(symbol, None)
    return result, fake_cursor


# GENI-shaped: FPI, real net_income/EPS present (every domestic-only tier gated off).
_GENI_SHAPED_INCOME_ROWS = [
    (2025, 344_000_000.0, -21_000_000.0, -0.09, None, None, None, None, None, None, True),
]

# Domestic-filer-shaped (GEF/DGICA/MC-style: no us-gaap share-count concept tagged at all, only
# the dei cover-page fact) - is_foreign_private_issuer=False (last element). eps_basic (index 3)
# and reported_shares_outstanding (index 8) both None so neither the reported-shares nor the
# net_income/eps-derived tier can fire before reaching the dei fallback under test.
_DOMESTIC_NO_USGAAP_SHARES_INCOME_ROWS = [
    (2025, 500_000_000.0, 40_000_000.0, None, None, None, None, None, None, None, False),
]


class TestStaleDeiSharesOutstandingRecencyBound:
    def test_query_includes_fiscal_year_recency_bound(self) -> None:
        """The dei cover-page query must filter on fiscal_year, not just ORDER BY it -
        protects against this exact staleness bound being silently removed later. Domestic
        filer fixture: this tier is gated off entirely for FPI as of the same-day
        is_foreign_private_issuer fix (see module docstring), so it can only still fire here."""
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (30_000_000.0,),  # cash_and_equivalents
            (5_000_000.0, None, None, None),  # debt_row
            None,  # has_dual_class_sibling check - no matching row
            (None,),  # "older fiscal year" shares_outstanding_basic fallback (domestic-only tier)
            (None,),  # company_info_sec fallback
            (None,),  # shares_outstanding_diluted fallback
            (None,),  # shares_outstanding_dei fallback (the tier under test)
            (8.02,),  # price_daily.close
            (100_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check
            (None, None),  # yfinance_snapshot
        ]

        _, cursor = _run_fetch_incremental("DOMESTICCO", _DOMESTIC_NO_USGAAP_SHARES_INCOME_ROWS, fetchone_results)

        dei_queries = [(q, p) for q, p in cursor.executed if "shares_outstanding_dei" in q]
        assert len(dei_queries) == 1
        query, params = dei_queries[0]
        assert "fiscal_year >=" in query
        # Last bind param is the recency cutoff year.
        assert isinstance(params[-1], int)
        assert params[-1] >= 2024  # any reasonable "current year - 2" floor for this test to stay valid over time

    def test_stale_dei_value_excluded_falls_through_to_unavailable(self) -> None:
        """FPI case: shares_out can only come from the live yfinance fallback now (dei/
        company_info_sec are both gated off for FPI) - when that also fails, the result must
        be an honest unavailable marker, not a wrong market_cap built from a stale value."""
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (30_000_000.0,),
            (5_000_000.0, None, None, None),
        ]

        with patch.object(
            SecValuationsLoader, "_fetch_live_fpi_shares_outstanding_yfinance", return_value=None
        ) as mock_fpi_fetch:
            result, _ = _run_fetch_incremental("GENI", _GENI_SHAPED_INCOME_ROWS, fetchone_results)

        mock_fpi_fetch.assert_called_once_with("GENI")
        row = result[0]
        assert row.get("data_unavailable") is True
        assert row.get("market_cap") is None
        assert row.get("reason") == "foreign_private_issuer_shares_unavailable"

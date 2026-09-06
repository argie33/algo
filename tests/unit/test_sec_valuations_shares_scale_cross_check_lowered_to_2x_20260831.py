"""Regression test for the 2026-08-31 SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO lowering, 10x -> 2x
(goal session: continuation of UROY's ~2.6x discrepancy flagged open in
sec_valuations_pl_row_coupled_stale_shares_hbio_fixed_20260831).

Live-verified UROY: resolved shares_out 126.8M (FY2025 shares_outstanding_basic) vs
company_info_sec 381.1M (~3.0x) - a FRESH live yfinance fetch (not the 7-week-stale
yfinance_snapshot row that made an earlier same-day check look deceptively close) confirmed
sharesOutstanding=381,067,318, matching company_info_sec exactly. The 10x threshold (set
2026-08-25) missed this real ~3x mismatch entirely.

Verified this generalizes via a DB-wide scan + live yfinance cross-check on BOTH directions of
the 2x-10x band (the existing cross-check is direction-agnostic - it always prefers
company_info_sec once the ratio crosses the threshold, regardless of which side is larger):
- company_info_sec LARGER (235 symbols in this band DB-wide): 7/7 spot-checked correct via live
  yfinance, including COKE (Coca-Cola Consolidated, ~$13B real company, 7.9x) - not just
  distressed micro-caps. The low end of this band clusters tightly at ~2.00-2.04x across many
  unrelated tickers, consistent with an unadjusted 2-for-1 stock split.
- Resolved shares_out LARGER (86 symbols DB-wide): 4/4 spot-checked, ALSO company_info_sec
  correct - including HON (Honeywell) and FOX (Fox Corp). Counter to the intuition that "a big
  company's bigger number is probably right" - live data corrected that assumption both times.
11/11 live-verified correct in company_info_sec's favor, 0 counterexamples in either direction.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[Any]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        pass

    def fetchall(self) -> list[tuple[Any, ...]]:
        result = self._fetchall_results[self._fetchall_idx]
        self._fetchall_idx += 1
        return result

    def fetchone(self) -> Any:
        result = self._fetchone_results[self._fetchone_idx]
        self._fetchone_idx += 1
        return result


def _run_fetch_incremental(
    symbol: str, income_rows: list[tuple[Any, ...]], fetchone_results: list[Any]
) -> list[dict[str, Any]]:
    loader = _make_loader()
    fake_cursor = _FakeCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        return loader.fetch_incremental(symbol, None)


class TestSharesScaleCrossCheckLoweredTo2x:
    def test_uroy_shaped_3x_gap_now_corrected(self) -> None:
        # UROY-shaped: shares_outstanding_basic=126,795,491 (real, but a growing-fiscal-year
        # weighted-average figure), company_info_sec=381,067,318 (fresher point-in-time count,
        # live-confirmed matching yfinance exactly) - real values, ~3.0x apart.
        income_rows = [
            (2025, 500_000_000.0, 50_000_000.0, 0.39, None, None, None, None, 126_795_491.0, None, False),
        ]
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (10_000_000.0,),  # cash_and_equivalents
            (20_000_000.0, None, None, None),  # debt_row
            None,  # has_dual_class_sibling check - no match
            (None, None),  # freshest shares_outstanding_basic check - no fresher row
            (381_067_318.0,),  # company_info_sec cross-check - real, fresher value
            (4.2550,),  # price_daily.close
            (100_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check
            (None, None),  # yfinance_snapshot sanity check
        ]

        result = _run_fetch_incremental("UROY", income_rows, fetchone_results)

        row = result[0]
        assert row["shares_outstanding"] == 381_067_318.0
        assert row["market_cap"] == round(4.2550 * 381_067_318.0, 2)

    def test_1_5x_gap_still_not_overridden(self) -> None:
        """A modest, plausible real-world disagreement (1.5x - buybacks/timing, not a scale
        error or stale-source signature) must still NOT trigger an override at the new 2x
        threshold - confirms this isn't a blanket 'always trust company_info_sec' change."""
        income_rows = [
            (2025, 100_000_000.0, 10_000_000.0, 1.0, None, None, None, None, 10_000_000.0, None, False),
        ]
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (5_000_000.0,),  # cash_and_equivalents
            (1_000_000.0, None, None, None),  # debt_row
            None,  # has_dual_class_sibling check - no match
            (None, None),  # freshest shares_outstanding_basic check - no fresher row
            (15_000_000.0,),  # company_info_sec cross-check - 1.5x, under the new 2x bar
            (32.21,),  # price_daily.close
            (60_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check
            (None, None),  # yfinance_snapshot sanity check
        ]

        result = _run_fetch_incremental("MODEST15X", income_rows, fetchone_results)

        row = result[0]
        assert row["shares_outstanding"] == 10_000_000.0
        assert row["market_cap"] == round(32.21 * 10_000_000.0, 2)

    def test_resolved_value_larger_direction_also_corrected(self) -> None:
        """Direction-agnostic: when the RESOLVED (SEC-derived) value is the larger one by
        >=2x, company_info_sec (smaller here) must still win - the HON/FOX-shaped case, not
        just the company_info_sec-larger direction."""
        income_rows = [
            (2025, 100_000_000.0, 10_000_000.0, 0.05, None, None, None, None, 20_000_000.0, None, False),
        ]
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (5_000_000.0,),  # cash_and_equivalents
            (1_000_000.0, None, None, None),  # debt_row
            None,  # has_dual_class_sibling check - no match
            (None, None),  # freshest shares_outstanding_basic check - no fresher row
            (9_000_000.0,),  # company_info_sec cross-check - smaller, ~2.2x
            (32.21,),  # price_daily.close
            (60_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check
            (None, None),  # yfinance_snapshot sanity check
        ]

        result = _run_fetch_incremental("REVERSEDIR", income_rows, fetchone_results)

        row = result[0]
        assert row["shares_outstanding"] == 9_000_000.0
        assert row["market_cap"] == pytest.approx(32.21 * 9_000_000.0, rel=1e-9)

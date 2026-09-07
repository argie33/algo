"""Regression test for the 2026-08-25 SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO lowering
(goal: "fix all the things"/finance-accuracy follow-up audit).

test_sec_valuations_shares_outstanding_scale_cross_check.py's 20x threshold was tuned for
per-filing XBRL scale-tagging errors (LARK/RPAY, ~1000x). Live-verified against real SEC EDGAR
data (data.sec.gov/api/xbrl/companyconcept, dei:EntityCommonStockSharesOutstanding) that WHLR
(Wheeler REIT - a serial reverse-splitter/heavily-diluting distressed micro-cap) has a
GENUINE, correctly-reported ~18x swing in shares outstanding between its FY2025 10-K (106,902)
and its most recent 10-Q cover page (1,931,568, filed 2026-08-06) - not a tagging bug, just
annual-frequency SEC data going stale fast for a company whose float changes this much
quarter to quarter. 18x sat just under the old 20x bar, so the cross-check never corrected it,
leaving sec_valuations.market_cap at ~$39K (price $0.37 x the stale 106,902-share count)
instead of a real ~$700K-$1M for a company at this share count/price.

The underlying fix is the same mechanism regardless of root cause (tagging error vs genuine
share-count churn): prefer company_info_sec, the more current/independently-extracted source,
when the two disagree by an enormous multiple. Lowered SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO
from 20 to 10 - checked DB-wide first (44 symbols newly covered in the 10x-20x band out of
4,105 with both sources available, overwhelmingly distressed/micro-cap tickers of the same
character as WHLR, not stable large-caps that would be wrongly flipped).
"""

from typing import Any
from unittest.mock import MagicMock, patch

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
    symbol: str, income_rows: list[tuple[Any, ...]], fetchone_results: list[Any]
) -> list[dict[str, Any]]:
    loader = _make_loader()
    fake_cursor = _FakeCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        return loader.fetch_incremental(symbol, None)


class TestStaleAnnualSharesLoweredThreshold:
    def test_whlr_shaped_18x_gap_now_corrected(self) -> None:
        # WHLR-shaped: annual shares_outstanding_basic=106,902 (stale FY2025 10-K figure),
        # company_info_sec=1,931,568 (fresher 10-Q cover page) - real values, ~18x apart.
        income_rows = [
            (2025, 10_000_000.0, -5_000_000.0, -46.80, None, None, None, None, 106_902.0, None, False),
        ]
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (1_000_000.0,),  # cash_and_equivalents
            (5_000_000.0, None, None, None),  # debt_row
            None,  # has_dual_class_sibling check - no match (WHLR is single-class)
            (None, None),  # freshest shares_outstanding_basic check (2026-08-31) - no fresher row
            (1_931_568.0,),  # company_info_sec cross-check - real, fresher value
            (0.37,),  # price_daily.close
            (2_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX (economic_data VIXCLS)
            (20.0,),  # long-run avg VIX - equal to current so dynamic ERP == static 5% (not under test here)
            None,  # net borrowing check (2026-08-25) - no adjacent-year debt data, DCF falls back to OCF-CapEx-SBC unchanged
            (None, None),  # yfinance_snapshot sanity check
        ]

        result = _run_fetch_incremental("WHLR", income_rows, fetchone_results)

        row = result[0]
        assert row["shares_outstanding"] == 1_931_568.0
        assert row["market_cap"] == round(0.37 * 1_931_568.0, 2)
        assert row["market_cap"] > 500_000.0  # not the stale-data $39.5K

    def test_11x_gap_below_old_20x_bar_still_not_overridden_by_old_threshold_alone(self) -> None:
        """Sanity: an 11x gap is real (not a rounding artifact) - confirms the fix is the
        threshold itself, not some other side effect."""
        income_rows = [
            (2025, 10_000_000.0, 1_000_000.0, 1.0, None, None, None, None, 1_000_000.0, None, False),
        ]
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (1_000_000.0,),  # cash_and_equivalents
            (5_000_000.0, None, None, None),  # debt_row
            None,  # has_dual_class_sibling check - no match
            (None, None),  # freshest shares_outstanding_basic check (2026-08-31) - no fresher row
            (11_000_000.0,),  # company_info_sec cross-check - 11x higher
            (10.0,),  # price_daily.close
            (2_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX (economic_data VIXCLS)
            (20.0,),  # long-run avg VIX - equal to current so dynamic ERP == static 5% (not under test here)
            None,  # net borrowing check (2026-08-25) - no adjacent-year debt data, DCF falls back to OCF-CapEx-SBC unchanged
            (None, None),  # yfinance_snapshot sanity check
        ]

        result = _run_fetch_incremental("ELEVENX", income_rows, fetchone_results)

        row = result[0]
        assert row["shares_outstanding"] == 11_000_000.0  # corrected, not the stale 1M
        assert row["market_cap"] == round(10.0 * 11_000_000.0, 2)

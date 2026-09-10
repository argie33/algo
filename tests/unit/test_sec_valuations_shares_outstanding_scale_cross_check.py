"""Regression test for a 2026-08-20 fix (goal: finance-accuracy audit) to
load_sec_valuations.py's shares_outstanding resolution: MAX_PLAUSIBLE_SHARES_OUTSTANDING (100
billion) is calibrated to catch truly absurd derived values (see
test_sec_valuations_shares_outstanding_ceiling.py's NMR case, ~2.94e15 shares) but is far too
generous to catch a per-filing 1000x XBRL scale error for a small/mid-cap filer - a value like
6.07 billion or 82.5 billion passes the ceiling untouched even though it's still wrong by 3-4
orders of magnitude for that specific company.

Live-confirmed via the real DB: LARK (Landmark Bancorp)'s FY2025 shares_outstanding_basic=
6,070,662,000 (real count ~6.1M - LARK's own FY2026 row and its own shares_outstanding_dei both
independently agree on ~6.1M, proving the FY2025 tag itself is what's mis-scaled); RPAY (Repay
Holdings) mis-scaled the same way across every fiscal year on file (82.5B/85.6B/89.9B vs
company_info_sec's independently-extracted 6.47M). Both fed sec_valuations.market_cap in the
hundreds of billions (LARK $195.5B, RPAY $304.5B) for real small-caps, corrupting ps_ratio/
fcf_yield.

Fixed by cross-checking the resolved shares_out against company_info_sec.shares_outstanding (a
separately-extracted source) when both are available for a domestic filer: if they disagree by
more than 20x, prefer company_info_sec as the more independently-corroborated value.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _RecordingCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self.executed_sql: list[str] = []
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        self.executed_sql.append(query)

    def fetchall(self) -> list[tuple[Any, ...]]:
        # 2026-09-05: pe_ratio/pb_ratio's implausible-anchor cross-year fallback
        # (loaders/load_sec_valuations.py) can issue one additional fetchall() beyond this
        # fixture's originally-scripted sequence - return empty (no plausible fallback found)
        # rather than IndexError once the scripted list is exhausted, since these fixtures don't
        # care about that fallback's content.
        if self._fetchall_idx >= len(self._fetchall_results):
            return []
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


# LARK-shaped: reported shares_outstanding_basic mis-scaled 1000x (6.07B instead of ~6.07M),
# well within MAX_PLAUSIBLE_SHARES_OUTSTANDING (100B) so the bare ceiling never catches it.
_LARK_SHAPED_INCOME_ROWS = [
    (2025, 100_000_000.0, 10_000_000.0, 0.0016, None, None, None, None, 6_070_662_000.0, None),
]


class TestSharesOutstandingScaleCrossCheck:
    def test_thousandfold_mismatch_prefers_company_info_sec(self) -> None:
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (5_000_000.0,),  # cash_and_equivalents
            (1_000_000.0, None, None, None),  # debt_row
            None,  # has_dual_class_sibling check (2026-08-21) - no matching row
            (None, None),  # freshest shares_outstanding_basic check (2026-08-31) - no fresher row
            (6_100_534.0,),  # company_info_sec shares_outstanding cross-check - real ~6.1M
            (32.21,),  # price_daily.close
            (60_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX (economic_data VIXCLS)
            (20.0,),  # long-run avg VIX - equal to current so dynamic ERP == static 5% (not under test here)
            None,  # net borrowing check (2026-08-25) - no adjacent-year debt data, DCF falls back to OCF-CapEx-SBC unchanged
            (None, None),  # yfinance_snapshot market_cap/pe_ratio sanity check (2026-08-20)
        ]

        result, cursor = _run_fetch_incremental("LARK", _LARK_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        # market_cap must reflect the corrected ~6.1M share count, not the mis-scaled 6.07B
        # (which would put market_cap at ~$195.5 billion for a real small-cap bank).
        assert row["market_cap"] == pytest.approx(32.21 * 6_100_534.0, rel=1e-9)
        assert row["market_cap"] < 1_000_000_000.0  # sanity: nowhere near the fabricated $195.5B

        cross_check_queries = [
            sql for sql in cursor.executed_sql if "shares_outstanding" in sql and "FROM company_info_sec" in sql
        ]
        assert len(cross_check_queries) == 1

    def test_no_company_info_sec_row_keeps_original_value(self) -> None:
        """When company_info_sec has nothing to cross-check against, the originally-resolved
        value must be used as-is - the cross-check must never fabricate a rejection."""
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (5_000_000.0,),  # cash_and_equivalents
            (1_000_000.0, None, None, None),  # debt_row
            None,  # has_dual_class_sibling check (2026-08-21) - no matching row
            (None, None),  # freshest shares_outstanding_basic check (2026-08-31) - no fresher row
            (None,),  # company_info_sec cross-check - nothing available
            (32.21,),  # price_daily.close
            (60_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX (economic_data VIXCLS)
            (20.0,),  # long-run avg VIX - equal to current so dynamic ERP == static 5% (not under test here)
            None,  # net borrowing check (2026-08-25) - no adjacent-year debt data, DCF falls back to OCF-CapEx-SBC unchanged
            (None, None),  # yfinance_snapshot market_cap/pe_ratio sanity check (2026-08-20)
        ]

        result, _ = _run_fetch_incremental("LARK2", _LARK_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        assert row["market_cap"] == round(32.21 * 6_070_662_000.0, 2)

    def test_agreeing_values_within_20x_are_not_overridden(self) -> None:
        """A real, modest disagreement between sources (well under the 20x threshold) must not
        trigger an override - only a large-magnitude scale mismatch should."""
        income_rows = [
            (2025, 100_000_000.0, 10_000_000.0, 1.0, None, None, None, None, 10_000_000.0, None),
        ]
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (5_000_000.0,),  # cash_and_equivalents
            (1_000_000.0, None, None, None),  # debt_row
            None,  # has_dual_class_sibling check (2026-08-21) - no matching row
            (None, None),  # freshest shares_outstanding_basic check (2026-08-31) - no fresher row
            (11_000_000.0,),  # company_info_sec cross-check - close, 1.1x, not a scale error
            (32.21,),  # price_daily.close
            (60_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX (economic_data VIXCLS)
            (20.0,),  # long-run avg VIX - equal to current so dynamic ERP == static 5% (not under test here)
            None,  # net borrowing check (2026-08-25) - no adjacent-year debt data, DCF falls back to OCF-CapEx-SBC unchanged
            (None, None),  # yfinance_snapshot market_cap/pe_ratio sanity check (2026-08-20)
        ]

        result, _ = _run_fetch_incremental("NORMALCO2", income_rows, fetchone_results)

        row = result[0]
        assert row["market_cap"] == round(32.21 * 10_000_000.0, 2)

"""Regression test for a 2026-08-30 fix (goal: full-data audit, AKTX follow-up):
_sanity_check_market_cap's ONLY comparison source for a domestic (non-FPI) filer was the
frozen yfinance_snapshot table (no live writer since Session 275) - live-confirmed 645
active-universe symbols have market_cap computed with zero row in that table, leaving the
sanity check a complete no-op for every one of them.

Live-confirmed via AKTX (Akari Therapeutics): a genuinely-tagged-but-context-implausible
share count computed market_cap=$720.4B with no cross-check available at all (not an FPI, so
the existing FPI-only live-fetch override never fired either). An ABSOLUTE ceiling can't
distinguish this from a real value at similar magnitude - the same query that found AKTX also
surfaced SKHY ($1.14T, same shape) alongside BRK.B ($701.75B, a REAL value near-identical in
size to AKTX's wrong one).

Fixed: when yfinance_snapshot has nothing AND the symbol is not an FPI (which already gets
its own live-fetch override), fall back to a live yfinance fetch - but ONLY when the computed
market_cap exceeds $50B, to bound live-fetch volume on a full-universe run (live-confirmed
only 29 of the 645 clear that bar). Reuses the same live-fetch helper the FPI tier already
relies on.

Fixture shapes below are copied from the existing, verified
test_domestic_filer_never_calls_live_fpi_fetch fixture in
test_sec_valuations_fpi_live_yfinance_sanity_check.py (a domestic filer, price=$376.86,
shares_outstanding~1.418B -> market_cap~$534B, comfortably past the $50B gate) - only the
final yfinance_snapshot fetchone result and the live-fetch mock differ per test.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        pass

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
) -> list[dict[str, Any]]:
    loader = _make_loader()
    fake_cursor = _FakeCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        return loader.fetch_incremental(symbol, None)


# Domestic (FPI flag False, last element), shares_outstanding_basic=1,417,803,727 reported
# directly - same shape as the proven-working test_domestic_filer_never_calls_live_fpi_fetch.
_DOMESTIC_INCOME_ROWS = [
    (2024, 1_500_000_000.0, 227_000_000.0, 2.7, None, None, None, None, 1_417_803_727.0, None, False),
]

_BASE_FETCHONE_RESULTS = [
    None,  # entity_type exemption gate check (138006446) - not exempt
    (5_000_000.0,),  # cash_and_equivalents
    (1_000_000.0, None, None, None),  # debt_row
    None,  # has_dual_class_sibling check (2026-08-21) - no matching row
    (None, None),  # freshest shares_outstanding_basic check (2026-08-31) - no fresher row
    (1_417_000_000.0,),  # company_info_sec domestic cross-check tier (agrees, no mismatch)
    (376.86,),  # price_daily.close
    (60_000_000.0,),  # stockholders_equity
    (1.0,),  # beta
    (4.5,),  # risk_free_rate
    (20.0,),  # current VIX (economic_data VIXCLS)
    (20.0,),  # long-run avg VIX
    None,  # net borrowing check - no adjacent-year debt data
]


class TestDomesticLargeCapLiveYfinanceFallback:
    def test_no_snapshot_row_large_market_cap_triggers_live_fetch(self) -> None:
        # price $376.86 x shares ~1.418B = ~$534.4B computed market_cap - past the $50B gate.
        fetchone_results = [*_BASE_FETCHONE_RESULTS, (None, None)]  # yfinance_snapshot: no row

        with patch.object(
            SecValuationsLoader,
            "_fetch_live_fpi_yfinance_check_values",
            return_value=(5_000_000_000.0, None, None),  # live, real, ~100x-mismatched value
        ) as mock_live_fetch:
            result = _run_fetch_incremental("BIGCO", _DOMESTIC_INCOME_ROWS, fetchone_results)

        mock_live_fetch.assert_called_once_with("BIGCO")
        row = result[0]
        # The live fetch's result triggered the scale-mismatch guard - proves it was actually
        # used to null the field, not silently ignored.
        assert row["market_cap"] is None
        assert row["reason"] == "shares_outstanding_scale_mismatch"

    def test_no_snapshot_row_small_market_cap_does_not_trigger_live_fetch(self) -> None:
        """Below the $50B gate - must stay a no-op, not spend a live yfinance call on every
        one of the (much larger) small/mid-cap population with no snapshot coverage."""
        income_rows = [
            (2024, 15_000_000.0, 2_270_000.0, 0.27, None, None, None, None, 5_000_000.0, None, False),
        ]
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (5_000_000.0,),
            (1_000_000.0, None, None, None),
            None,
            (None, None),  # freshest shares_outstanding_basic check (2026-08-31) - no fresher row
            (5_000_000.0,),  # company_info_sec cross-check tier (agrees)
            (10.70,),  # price
            (60_000_000.0,),
            (1.0,),
            (4.5,),
            (20.0,),
            (20.0,),
            None,
            (None, None),  # yfinance_snapshot: no row
        ]

        with patch.object(SecValuationsLoader, "_fetch_live_fpi_yfinance_check_values") as mock_live_fetch:
            result = _run_fetch_incremental("SMALLCO", income_rows, fetchone_results)

        mock_live_fetch.assert_not_called()
        row = result[0]
        assert row["market_cap"] == pytest.approx(10.70 * 5_000_000.0, rel=1e-9)

    def test_stored_snapshot_present_still_never_calls_live_fetch(self) -> None:
        """A domestic filer WITH real yfinance_snapshot coverage must keep using the stored
        value, never spending an extra live call - same expectation as the pre-existing
        test_domestic_filer_never_calls_live_fpi_fetch, re-verified alongside this new gate."""
        fetchone_results = [*_BASE_FETCHONE_RESULTS, (534_400_000_000.0, None)]  # snapshot agrees

        with patch.object(SecValuationsLoader, "_fetch_live_fpi_yfinance_check_values") as mock_live_fetch:
            result = _run_fetch_incremental("BIGCO2", _DOMESTIC_INCOME_ROWS, fetchone_results)

        mock_live_fetch.assert_not_called()
        row = result[0]
        assert row["market_cap"] == pytest.approx(376.86 * 1_417_803_727.0, rel=1e-9)

"""Regression test for a 2026-08-31 fix (goal: data-coverage sweep, AMRN follow-up to
sec_valuations_fpi_shares_out_missing_gate_fixed_20260831) to load_sec_valuations.py.

AMRN (Amarin Corporation plc) files DOMESTIC forms (10-K/10-Q), so
is_foreign_private_issuer is correctly False per company_info_sec's form-type-based
classification - none of this file's FPI-specific ADS-unit-mismatch guards apply. But AMRN's
ADS ratio changed to 1 ADS = 20 ordinary shares (real corporate action, effective 2025-04-11).
SEC's own XBRL data is fresh and self-consistent on the ORDINARY share count (~420M, confirmed
via both us-gaap:CommonStockSharesOutstanding and WeightedAverageNumberOfSharesOutstandingBasic
agreeing) - there's no staleness or cross-check signal available to catch this automatically,
since the SEC data isn't wrong, just on a different basis than the traded ADS price.

Fix: a narrow, individually-verified DOMESTIC_FILER_ADS_RATIO_OVERRIDES allowlist (same
discipline as CIK_OVERRIDES/DUAL_CLASS_NO_SEPARATOR_ROOTS elsewhere in this file) divides the
resolved shares_out by the real ADS ratio right before market_cap computation.
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
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, params: Any = None) -> None:
        pass

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
) -> list[dict[str, Any]]:
    loader = _make_loader()
    fake_cursor = _RecordingCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        return loader.fetch_incremental(symbol, None)


# AMRN-shaped: domestic filer (is_foreign_private_issuer=False), real reported ordinary-share
# count (~420M) resolves via the first ("reported shares_outstanding_basic") tier.
_AMRN_SHAPED_INCOME_ROWS = [
    (2026, 344_000_000.0, -21_000_000.0, -1.02, None, None, None, None, 419_457_000.0, None, False),
]


class TestDomesticFilerAdsRatioOverride:
    def test_amrn_shares_out_divided_by_ads_ratio(self) -> None:
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (30_000_000.0,),  # cash_and_equivalents
            (5_000_000.0, None, None, None),  # debt_row
            None,  # has_dual_class_sibling check - no matching row
            (None, None),  # freshest shares_outstanding_basic check (2026-08-31) - no fresher row
            (None,),  # company_info_sec cross-check (reported shares already resolved)
            (14.0,),  # price_daily.close
            (100_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check
            (292_990_714.5, None),  # yfinance_snapshot - agrees with the ADS-adjusted market cap
        ]

        result = _run_fetch_incremental("AMRN", _AMRN_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        assert row["shares_outstanding"] == 419_457_000.0 / 20.0
        assert row["market_cap"] == 14.0 * (419_457_000.0 / 20.0)
        assert row["data_unavailable"] is False
        assert row["reason"] is None

    def test_other_domestic_symbol_unaffected(self) -> None:
        """The override must only apply to symbols explicitly in the allowlist - a
        similarly-shaped domestic filer with the same real share count must be untouched."""
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (30_000_000.0,),
            (5_000_000.0, None, None, None),
            None,
            (None, None),  # freshest shares_outstanding_basic check (2026-08-31) - no fresher row
            (None,),  # company_info_sec cross-check (reported shares already resolved)
            (14.0,),
            (100_000_000.0,),
            (1.0,),
            (4.5,),
            (20.0,),
            (20.0,),
            None,
            (14.0 * 419_457_000.0, None),  # yfinance_snapshot agrees with the UNadjusted value
        ]

        result = _run_fetch_incremental("NOTAMRN", _AMRN_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        assert row["shares_outstanding"] == 419_457_000.0
        assert row["market_cap"] == 14.0 * 419_457_000.0

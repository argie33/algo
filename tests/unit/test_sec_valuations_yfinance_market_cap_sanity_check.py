"""Regression test for a 2026-08-20 fix (goal: finance-accuracy audit) to
load_sec_valuations.py: shares_outstanding can be wrong by a factor neither the plausibility
ceiling (MAX_PLAUSIBLE_SHARES_OUTSTANDING) nor the company_info_sec cross-check catches, when
both independently derive from the SAME underlying mis-scaled SEC concept and agree with each
other while both being wrong.

Live-confirmed: ONC (BeOne Medicines) computed market_cap=$534.3B here, while
company_info_sec's shares_outstanding (1.478B) agreed with the SEC-derived value (1.418B)
within the existing 20x cross-check tolerance - both sourced from the same mis-scaled concept.
yfinance_snapshot.market_cap (a genuinely independent, differently-sourced figure) shows ONC's
real market cap is ~$31.0B - a 17x gap. A DB-wide scan found 92 symbols with a >10x mismatch
against yfinance_snapshot.market_cap (up to 792x for MTLS).

This file's own module docstring is explicit that yfinance must never be a VALUE source here
("No fallback to yfinance (SEC data only)"), so this only uses it as a validity check: a >10x
disagreement nulls every field that depends on shares_outstanding (market_cap, pb_ratio,
ps_ratio, fcf_yield, dividend_yield, enterprise_value, ev_ebitda, ev_revenue,
intrinsic_value_per_share, margin_of_safety_pct) rather than presenting a number now positively
known to likely be wrong. pe_ratio/peg_ratio are untouched since they don't depend on
shares_outstanding at all.
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
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        self.executed_sql.append(query)

    def fetchall(self) -> list[tuple[Any, ...]]:
        result = self._fetchall_results[self._fetchall_idx]
        self._fetchall_idx += 1
        return result

    def fetchone(self) -> tuple[Any, ...] | None:
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


# ONC-shaped: reported shares_outstanding_basic (1.418B) agrees with company_info_sec (so the
# earlier cross-check doesn't fire), but both are wrong relative to yfinance's independent
# market_cap figure.
_ONC_SHAPED_INCOME_ROWS = [
    (2026, 1_500_000_000.0, 227_000_000.0, 2.7, None, None, None, None, 1_417_803_727.0, None),
]


class TestYfinanceMarketCapSanityCheck:
    def test_large_mismatch_nulls_shares_dependent_fields_not_pe_ratio(self) -> None:
        fetchone_results = [
            (5_000_000.0,),  # cash_and_equivalents
            (1_000_000.0, None, None, None),  # debt_row
            None,  # has_dual_class_sibling check (2026-08-21) - no matching row
            (1_417_000_000.0,),  # company_info_sec cross-check - agrees with SEC value (no override)
            (376.86,),  # price_daily.close
            (60_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (30_990_489_600.0, None),  # yfinance_snapshot: market_cap (real ~$31.0B), pe_ratio unavailable
        ]

        result, cursor = _run_fetch_incremental("ONC", _ONC_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        # shares_outstanding-dependent fields must be nulled - the SEC-derived market_cap
        # ($534.3B) is now known to be implausible relative to an independent source.
        assert row["market_cap"] is None
        assert row["ps_ratio"] is None
        assert row["fcf_yield"] is None
        assert row["enterprise_value"] is None
        # pe_ratio does not depend on shares_outstanding - must survive untouched.
        assert row["pe_ratio"] == round(376.86 / 2.7, 2)
        assert row["reason"] == "shares_outstanding_scale_mismatch"

        sanity_check_queries = [sql for sql in cursor.executed_sql if "FROM yfinance_snapshot" in sql]
        assert len(sanity_check_queries) == 1

    def test_no_yfinance_row_leaves_result_untouched(self) -> None:
        """When yfinance_snapshot has nothing for this symbol, the sanity check must be a
        no-op - never treat missing comparison data as a reason to null anything."""
        fetchone_results = [
            (5_000_000.0,),
            (1_000_000.0, None, None, None),
            None,  # has_dual_class_sibling check (2026-08-21) - no matching row
            (1_417_000_000.0,),
            (376.86,),
            (60_000_000.0,),
            (1.0,),
            (4.5,),
            (None, None),  # yfinance_snapshot - nothing available
        ]

        result, _ = _run_fetch_incremental("ONC2", _ONC_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        assert row["market_cap"] == pytest.approx(376.86 * 1_417_803_727.0, rel=1e-9)

    def test_agreeing_market_caps_within_10x_not_touched(self) -> None:
        """A real, modest disagreement (well under the 10x threshold) must not trigger the
        override - only a large-magnitude scale mismatch should."""
        fetchone_results = [
            (5_000_000.0,),
            (1_000_000.0, None, None, None),
            None,  # has_dual_class_sibling check (2026-08-21) - no matching row
            (1_417_000_000.0,),
            (376.86,),
            (60_000_000.0,),
            (1.0,),
            (4.5,),
            (450_000_000_000.0, None),  # yfinance_snapshot.market_cap - within 10x of $534.3B
        ]

        result, _ = _run_fetch_incremental("ONC3", _ONC_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        assert row["market_cap"] == pytest.approx(376.86 * 1_417_803_727.0, rel=1e-9)

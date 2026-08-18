"""Regression test for the 2026-08-18 "no SEC data" audit finding: load_sec_valuations.py's
income-statement query ORDER BY ranks a fiscal year tier-0 if ANY of revenue/EPS/net_income is
present - not specifically revenue - so a filer whose latest fiscal year has a real net_income
but a not-yet-tagged revenue figure wins the tiebreak over an older row that has real, complete
revenue. ttm_revenue then comes back None even though a usable figure exists one row back,
silently killing ev_revenue/ps_ratio.

Live-confirmed on CRAI (CRA International, a real ~$750M/year consulting firm): FY2026's
annual_income_statement row has net_income=$54.8M but revenue=NULL (still tier 0 under the old
tiebreak, since net_income is present) and beat FY2025's real revenue=$751.58M. A universe-wide
scan found 723 symbols with this exact NULL-revenue-but-real-EPS-or-net-income anchor-row shape.

Fixed by falling back to income_rows[1] (already fetched via LIMIT 2, no extra query) whenever
the anchor row's revenue is None - same small-window "same-year-substitute" convention already
used elsewhere in this loader (see test_sec_valuations_debt_query_prefers_populated_fiscal_year.py).
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    """FIXED 2026-08-18 (missing factor inputs audit, continued): see
    test_sec_valuations_total_debt_not_total_liabilities.py's _FakeCursor docstring -
    fetchall() must be sequential (income_rows first, then the DCF 3-year-average-FCF
    fallback's cash_rows), not a single static response reused for both calls."""

    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        pass

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
) -> list[dict[str, Any]]:
    loader = _make_loader()
    fake_cursor = _FakeCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        return loader.fetch_incremental(symbol, None)


# Downstream fetchone() calls after the income_rows fetchall(), in order: price_daily.close,
# stockholders_equity, cash_and_equivalents, debt_row - same shape as
# test_sec_valuations_debt_query_prefers_populated_fiscal_year.py's fixture (cash_flow ocf/
# capex/dividends_paid is a fetchall(), not a fetchone() - see _FakeCursor above).
_DOWNSTREAM_FETCHONE = [
    (50.0,),
    (500_000_000.0,),
    (30_000_000.0,),
    (20_000_000.0, 5_000_000.0, None, None),
]


class TestRevenuePrefersPopulatedFiscalYear:
    def test_falls_back_to_prior_row_revenue_when_anchor_row_revenue_is_null(self) -> None:
        # CRAI-shaped: anchor row (FY2026) has net_income but NULL revenue; prior row (FY2025)
        # has real, complete revenue/net_income/EPS.
        income_rows = [
            (None, 54_800_000.0, None, None, None, None, None, 6_600_000.0, None),  # FY2026 anchor
            (
                751_583_000.0,
                54_782_000.0,
                8.23,
                83_124_000.0,
                76_573_000.0,
                None,
                None,
                6_600_000.0,
                None,
            ),  # FY2025
        ]

        result = _run_fetch_incremental("CRAI", income_rows, _DOWNSTREAM_FETCHONE)

        row = result[0]
        assert not row.get("data_unavailable")
        assert row["ps_ratio"] is not None, "PS ratio should compute using the fallback revenue"

    def test_no_fallback_available_leaves_revenue_null_not_a_crash(self) -> None:
        # Genuinely pre-revenue company (e.g. a clinical-stage biotech): neither row has
        # revenue. Must not crash and must not fabricate a value.
        income_rows = [
            (None, -10_000_000.0, -1.0, None, None, None, None, 10_000_000.0, None),
            (None, -8_000_000.0, -0.8, None, None, None, None, 10_000_000.0, None),
        ]

        result = _run_fetch_incremental("NOREV", income_rows, _DOWNSTREAM_FETCHONE)

        row = result[0]
        assert row.get("ps_ratio") is None

    def test_anchor_row_with_real_revenue_is_not_overridden_by_fallback(self) -> None:
        # A normal, complete anchor row must keep its own revenue - the fallback must only
        # fire when the anchor's revenue is actually NULL.
        income_rows = [
            (100_000_000.0, 10_000_000.0, 1.0, 15_000_000.0, 12_000_000.0, None, None, 10_000_000.0, None),
            (999_999_999.0, 9_000_000.0, 0.9, 14_000_000.0, 11_000_000.0, None, None, 10_000_000.0, None),
        ]

        result = _run_fetch_incremental("REALREV", income_rows, _DOWNSTREAM_FETCHONE)

        row = result[0]
        assert row["ps_ratio"] == round(50.0 / (100_000_000.0 / 10_000_000.0), 2)

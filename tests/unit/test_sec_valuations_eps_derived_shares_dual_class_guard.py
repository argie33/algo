"""Regression test for the 2026-08-21 fix (goal session - "is BRK.B handled the right
way" end-to-end re-check): load_sec_valuations.py's net_income/eps-derived
shares_outstanding proxy is vulnerable to the same dual-class ambiguity already fixed in
load_company_info_sec.py and load_financial_statements.py this session.

net_income is a single whole-company figure shared by every share class, but eps_basic is
class-specific (BRK.A's real EPS is ~1,500x BRK.B's). This proxy silently reconstructs
whichever class's EPS the extraction happened to expose, producing the SAME wrong
shares_out for every sibling class regardless of which ticker asked.

Live-confirmed: with company_info_sec/annual_income_statement.shares_outstanding_basic
already correctly NULL for BRK.A/BRK.B (both prior fixes), this proxy still derived an
identical 1,643,456 "shares" for both, producing BRK.A market_cap=$1.22T and BRK.B
market_cap=$815M off the SAME wrong share count.

Fix: skip the derivation entirely when the symbol has an actively-tracked dual-class
sibling in stock_symbols (checked via a cheap base-root query, covering both dot-suffixed
siblings like BRK.A/BRK.B and bare-ticker siblings like HEI/HEI.A).
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    """Sequential fetchone/fetchall stand-in - fetchone_results entries must exactly
    match what a real psycopg2 cursor would return: bare None for "no row found"
    (e.g. a "SELECT 1 FROM ... LIMIT 1" sibling check with no match), a tuple like
    (None,) only for "a row was found but its column value is NULL"."""

    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[Any]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None)]]
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


class TestEpsDerivedSharesDualClassGuard:
    def test_dot_suffixed_symbol_with_active_sibling_skips_derivation(self) -> None:
        """BRK.A-shaped: real net_income/eps that would derive a plausible-looking share
        count, but BRK.B is an actively-tracked sibling - must not trust the derivation."""
        income_rows = [
            (2025, 400_000_000_000.0, 90_000_000_000.0, 54.0, None, None, None, None, None, None, False),
        ]
        fetchone_results = [
            (5_000_000_000.0,),  # cash_and_equivalents
            (10_000_000_000.0, None, None, None),  # debt_row
            (1,),  # dual-class sibling check - BRK.B found (a real row, not None)
            None,  # older-fiscal-year shares_outstanding_basic fallback - no row
            None,  # company_info_sec fallback - no row
            None,  # shares_outstanding_diluted fallback - no row
            None,  # shares_outstanding_dei fallback - no row
        ]

        result = _run_fetch_incremental("BRK.A", income_rows, fetchone_results)

        row = result[0]
        assert row.get("data_unavailable") is True
        assert row.get("market_cap") is None

    def test_bare_ticker_with_dotted_sibling_also_skips_derivation(self) -> None:
        """HEI-shaped: bare ticker (no dot), but HEI.A is an actively-tracked sibling -
        the base-root sibling check must catch this direction too, not just dot-suffixed
        symbols querying for a bare sibling."""
        income_rows = [
            (2025, 4_000_000_000.0, 500_000_000.0, 9.0, None, None, None, None, None, None, False),
        ]
        fetchone_results = [
            (100_000_000.0,),  # cash_and_equivalents
            (200_000_000.0, None, None, None),  # debt_row
            (1,),  # dual-class sibling check - HEI.A found
            None,  # older-fiscal-year fallback - no row
            None,  # company_info_sec fallback - no row
            None,  # shares_outstanding_diluted fallback - no row
            None,  # shares_outstanding_dei fallback - no row
        ]

        result = _run_fetch_incremental("HEI", income_rows, fetchone_results)

        row = result[0]
        assert row.get("data_unavailable") is True
        assert row.get("market_cap") is None

    def test_no_sibling_still_uses_derivation_normally(self) -> None:
        """Regression guard: a real single-class company must be completely unaffected -
        the sibling check must not become a blanket rejection."""
        income_rows = [
            (2026, 1_000_000_000.0, 100_000_000.0, 2.0, None, None, None, None, None, None, False),
        ]
        fetchone_results = [
            (30_000_000.0,),  # cash_and_equivalents
            (20_000_000.0, 5_000_000.0, None, None),  # debt_row
            None,  # dual-class sibling check - no sibling found
            None,  # company_info_sec shares_outstanding cross-check - no row
            (35.26,),  # price_daily.close
            (500_000_000.0,),  # stockholders_equity
            (1.0,),  # beta (stability_metrics)
            (4.5,),  # risk_free_rate (economic_data DGS10)
            (None, None),  # yfinance_snapshot market_cap/pe_ratio sanity check
        ]

        result = _run_fetch_incremental("SOLOCO", income_rows, fetchone_results)

        row = result[0]
        assert not row.get("data_unavailable")
        assert row["market_cap"] == round(35.26 * 50_000_000.0, 2)

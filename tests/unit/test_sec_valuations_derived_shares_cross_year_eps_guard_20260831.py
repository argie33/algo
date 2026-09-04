"""Regression test for a 2026-08-31 fix (goal: data-coverage sweep, UROY follow-up to
sec_valuations_pl_row_coupled_stale_shares_hbio_fixed_20260831) to load_sec_valuations.py.

The "shares = net_income / eps" derived-shares tier only holds when both operands come from
the SAME fiscal year. `ttm_eps_basic` can be silently substituted from `income_rows[1]` (a
different, older fiscal year) by the `eps_substituted_from_row1` fallback (added 2026-08-18 to
recover pe_ratio/PEG when the anchor row's own EPS isn't tagged yet), while `_ttm_net_income`
stays the anchor row's own value - combining the two produces a mathematically meaningless
number, not a real share count.

Live-confirmed via UROY (Uranium Royalty Corp): anchor FY2026 has net_income=$40.249M but no
EPS tagged yet, so EPS was substituted from FY2025's -$0.04 - derived_shares_out =
40,249,000/0.04 = 1,006,225,000 (fabricated, not UROY's real share count) - producing
market_cap=$4.28B vs real ~$1.6-1.67B. The PEG calculation elsewhere in this method already
guards against this exact cross-year mismatch via `ttm_eps_fiscal_year` - this tier never had
the same guard.

Fix: skip the derived-shares tier when EPS was substituted from a different fiscal year than
net_income (`eps_substituted_from_row1`), same discipline as the existing dual-class-sibling
gate on this tier.

Every other shares_out tier is fed nothing here (all fetchone results None) so this test
isolates the derived-tier's own behavior in the cleanest possible way - the real live UROY case
falls through further to the "older fiscal year" tier, already covered end-to-end by this
session's live DB verification (see the memory file above), not re-derived here.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _RecordingCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[Any]) -> None:
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

    def fetchone(self) -> Any:
        result = self._fetchone_results[self._fetchone_idx]
        self._fetchone_idx += 1
        return result


def _run_fetch_incremental(
    symbol: str, income_rows: list[tuple[Any, ...]], fetchone_results: list[Any]
) -> list[dict[str, Any]]:
    loader = _make_loader()
    fake_cursor = _RecordingCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        return loader.fetch_incremental(symbol, None)


# UROY-shaped: anchor FY2026 has real net_income but no EPS/shares_outstanding_basic tagged yet
# (reported_shares_outstanding=None, index 8); FY2025 (income_rows[1]) has a real EPS but a
# DIFFERENT, older fiscal year's shares_outstanding_basic.
_UROY_SHAPED_INCOME_ROWS = [
    (2026, 186_952_000.0, 40_249_000.0, None, None, None, None, None, None, None, False),
    (2025, 11_276_000.0, -4_509_000.0, -0.04, None, None, None, None, 126_795_491.0, None, False),
]

# Verified query sequence (traced live against the real loader): prior-year-EPS-style lookup,
# cash, debt, dual-class-sibling check, older-fiscal-year shares_outstanding_basic,
# company_info_sec fallback, shares_outstanding_diluted fallback, shares_outstanding_dei
# fallback - every tier fed nothing so only the derived-tier's own behavior is under test.
_ALL_EMPTY_FETCHONE = [
    None,  # prior-year-EPS-style lookup
    (None,),  # cash_and_equivalents
    (None,),  # debt_row
    None,  # has_dual_class_sibling check - no matching row
    (None,),  # older-fiscal-year shares_outstanding_basic fallback
    (None,),  # company_info_sec fallback
    (None,),  # shares_outstanding_diluted fallback
    (None,),  # shares_outstanding_dei fallback
]


class TestDerivedSharesCrossYearEpsGuard:
    def test_cross_year_eps_does_not_produce_fabricated_shares(self) -> None:
        result = _run_fetch_incremental("UROY", _UROY_SHAPED_INCOME_ROWS, _ALL_EMPTY_FETCHONE)

        row = result[0]
        # If the derived tier incorrectly fired, this would be
        # 40,249,000/0.04=1,006,225,000 (a fabricated cross-year figure). With every other
        # tier empty, the honest outcome is "no shares available" - not a fabricated number.
        assert row["shares_outstanding"] is None
        assert row["data_unavailable"] is True
        assert row["reason"] == "shares_outstanding_unavailable"

    def test_same_year_eps_still_computes_normally(self) -> None:
        """Companion case: when the anchor row's OWN eps is used (not substituted from a
        different year), the derived tier must still fire exactly as before - this fix must
        not become a blanket rejection of the net_income/eps identity."""
        same_year_rows = [
            (2026, 186_952_000.0, 40_249_000.0, 0.40, None, None, None, None, None, None, False),
        ]
        # Single-row income_rows shape - no prior-year-EPS-style lookup fires (that only
        # happens when len(income_rows) > 1), so this fixture's sequence is shorter than the
        # 2-row UROY-shaped fixture above.
        fetchone_results = [
            (None,),  # cash_and_equivalents
            (None,),  # debt_row
            None,  # has_dual_class_sibling check - no matching row
            (None,),  # company_info_sec cross-check (shares_out already set by the derived tier)
            (10.0,),  # price_daily.close
            (None,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check
            (None, None),  # yfinance_snapshot
        ]

        result = _run_fetch_incremental("SAMEYEARCO", same_year_rows, fetchone_results)

        row = result[0]
        assert row["shares_outstanding"] == 40_249_000.0 / 0.40

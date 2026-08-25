"""Regression test for the 2026-08-22 fix (goal session - real-money-readiness audit):
load_sec_valuations.py's dual-class handling correctly refuses every SEC-derived
shares_outstanding tier for a symbol with an actively-tracked sibling class (see
test_sec_valuations_eps_derived_shares_dual_class_guard.py) - but until this fix, that meant
the symbol just stayed permanently data_unavailable, since SEC's companyfacts convenience API
structurally cannot carry per-share-class data at all (live-verified against real SEC EDGAR
data for BRK.A/BRK.B: no CommonStockSharesOutstanding concept exists for this filer at all,
and dei:EntityCommonStockSharesOutstanding hasn't had an entry since 2011 - see
dual_class_primary_ticker_shares_outstanding_structural_gap_found_20260822 in memory).

Fix: when every SEC-derived tier has failed AND has_dual_class_sibling=True, fall back to a
live yfinance shares_outstanding fetch (per-LISTING, not per-company, so it naturally resolves
the correct class-specific count) via _fetch_live_dual_class_shares_outstanding(). This is a
deliberate, narrow exception to this file's "SEC data only" policy - rows produced this way are
tagged data_source="sec_audited_except_dual_class_shares_yfinance" instead of "sec_audited" so
the exception stays visible/auditable rather than silently blended in.
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


# Same shape as test_sec_valuations_eps_derived_shares_dual_class_guard.py's BRK.A case: every
# SEC-derived tier fails (dual-class sibling found, then every fallback query returns no row).
_DUAL_CLASS_ALL_SEC_TIERS_FAIL_INCOME_ROWS = [
    (2025, 400_000_000_000.0, 90_000_000_000.0, 54.0, None, None, None, None, None, None, False),
]
_DUAL_CLASS_ALL_SEC_TIERS_FAIL_FETCHONE = [
    (5_000_000_000.0,),  # cash_and_equivalents
    (10_000_000_000.0, None, None, None),  # debt_row
    (1,),  # dual-class sibling check - found
    # tiers 1-3 (reported/eps-derived/older-fiscal-year) are gated off by
    # has_dual_class_sibling and make NO query at all. Tier 4 (company_info_sec fallback)
    # is deliberately ungated (company_info_sec is itself already class-safe) - one query,
    # no row. Tiers 5-6 (diluted/dei) are ALSO gated off by has_dual_class_sibling and make
    # no query either - do NOT add padding entries for them here: since _FakeCursor.fetchone()
    # just returns list entries in strict call order regardless of which SQL text was
    # "executed", an unconsumed extra entry here silently shifts every LATER real query
    # (the shares_out cross-check, then price_daily.close, ...) by one position instead of
    # being harmlessly ignored - this bit a first draft of this test (current_price silently
    # became None because price_daily.close's fetchone() consumed a leftover padding None).
    None,  # company_info_sec fallback (tier 4) - no row
]


class TestDualClassYfinanceSharesFallback:
    def test_dual_class_falls_back_to_live_yfinance_after_every_sec_tier_fails(self) -> None:
        # Real value live-verified 2026-08-22 against yf.Ticker("BRK-A").info.
        fetchone_results = [
            *_DUAL_CLASS_ALL_SEC_TIERS_FAIL_FETCHONE,
            # The company_info_sec cross-check (line ~689, `if shares_out and not
            # is_foreign_private_issuer`) sits BEFORE the dual-class yfinance tier in the
            # code and only fires if shares_out is ALREADY truthy at that point - it is
            # NOT re-evaluated after the dual-class tier resolves shares_out later, so it
            # makes no query at all in this scenario (every SEC tier failed). No padding
            # entry needed here - the very next real fetchone() call is price_daily.close.
            (743_500.0,),  # price_daily.close
            (700_000_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (None, None),  # yfinance_snapshot market_cap/pe_ratio sanity check
        ]

        with patch.object(
            SecValuationsLoader,
            "_fetch_live_dual_class_shares_outstanding",
            return_value=488_450.0,
        ) as mock_dual_class_fetch:
            result = _run_fetch_incremental("BRK.A", _DUAL_CLASS_ALL_SEC_TIERS_FAIL_INCOME_ROWS, fetchone_results)

        mock_dual_class_fetch.assert_called_once_with("BRK.A")
        row = result[0]
        assert row.get("data_unavailable") is False
        assert row["shares_outstanding"] == 488_450.0
        assert row["market_cap"] == round(743_500.0 * 488_450.0, 2)
        # The narrow exception must stay visible/auditable, not silently claim "sec_audited".
        assert row["data_source"] == "sec_audited_except_dual_class_shares_yfinance"

    def test_dual_class_yfinance_fetch_failure_stays_data_unavailable_not_crash(self) -> None:
        with patch.object(
            SecValuationsLoader,
            "_fetch_live_dual_class_shares_outstanding",
            return_value=None,
        ) as mock_dual_class_fetch:
            result = _run_fetch_incremental(
                "BRK.A", _DUAL_CLASS_ALL_SEC_TIERS_FAIL_INCOME_ROWS, _DUAL_CLASS_ALL_SEC_TIERS_FAIL_FETCHONE
            )

        mock_dual_class_fetch.assert_called_once_with("BRK.A")
        row = result[0]
        assert row.get("data_unavailable") is True
        assert row.get("reason") == "shares_outstanding_unavailable"

    def test_dual_class_yfinance_never_called_when_an_sec_tier_already_resolved(self) -> None:
        """Regression guard: the dual-class yfinance fallback must only fire once every
        SEC-derived tier has failed - never a substitute for a real SEC value that exists."""
        income_rows = [
            (2025, 400_000_000_000.0, 90_000_000_000.0, 54.0, None, None, None, None, None, None, False),
        ]
        fetchone_results = [
            (5_000_000_000.0,),  # cash_and_equivalents
            (10_000_000_000.0, None, None, None),  # debt_row
            (1,),  # dual-class sibling check - found
            # tiers 1-3 (reported_shares_outstanding/eps-derived/older-fiscal-year) are all
            # gated off by has_dual_class_sibling and make no query - the very next fetchone
            # is tier 4 (company_info_sec fallback, line ~594), which is deliberately
            # UNGATED since company_info_sec.shares_outstanding is itself already
            # class-safe (resolved by load_company_info_sec.py's own dual-class guard).
            (1_030_780.0,),  # company_info_sec fallback (tier 4) - REAL row
            None,  # company_info_sec cross-check (line ~689) - no data, no-op
            (376.86,),  # price_daily.close
            (700_000_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (None, None),  # yfinance_snapshot sanity check
        ]

        with patch.object(SecValuationsLoader, "_fetch_live_dual_class_shares_outstanding") as mock_dual_class_fetch:
            result = _run_fetch_incremental("AGM.A", income_rows, fetchone_results)

        mock_dual_class_fetch.assert_not_called()
        row = result[0]
        assert row["data_source"] == "sec_audited"

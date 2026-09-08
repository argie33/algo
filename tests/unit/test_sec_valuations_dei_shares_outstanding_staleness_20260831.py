"""Regression test for the 2026-08-31 fix (goal session: "VCIG tops the scores" follow-up
investigation into FPI shares_outstanding staleness) to load_sec_valuations.py's
`shares_outstanding_dei` cover-page fallback tier.

That tier had no recency bound - it picked whatever fiscal year had the MOST RECENT non-null
`shares_outstanding_dei`, with no check on how old that fiscal year actually was. For a foreign
private issuer, every fresher SEC tier (basic/diluted, current fiscal years) is deliberately
gated off, so this tier is the only SEC-sourced path reached - and for several real FPIs it
resolved to a value several YEARS stale because intervening fiscal years simply had a NULL dei
column. Live-confirmed on the real local DB: ENIC resolved to its FY2017 dei value (8 years
stale, 49.09B shares, FY2018-2024 all NULL); CEPU to FY2019 (6 years stale, 1.51B shares); AIFU
to FY2022 (1.07B shares) despite FY2023-2025 basic/diluted showing a real, much smaller, current
count (~2.6M-10.1M shares - AIFU genuinely restructured its share count since FY2022). All three
fed sec_valuations.shares_outstanding with data_source='sec_audited', silently implying
SEC-audited-and-current when it was neither.

Same bug class, same fix, as load_company_info_sec.py's `_latest_shares_value()` 2026-08-20 fix
(test_company_info_sec_shares_outstanding_stale_entry_rejected.py) - reject a candidate more
than 2 years (730 days, same bound) older than the symbol's most recent fiscal year, falling
through to the next tier (here: the FPI-yfinance live-fetch) instead of trusting a stale figure
just for being the newest thing this narrow column happened to have.

UPDATED 2026-08-31 (cherry-pick of the separately-landed 5e3f144f0 fix onto this same tier - see
that commit's own message): this tier is now ALSO gated on `not is_foreign_private_issuer`, so a
foreign private issuer never reaches it at all any more regardless of staleness (the PHAR/IONR/
JZXN evidence showed even a *recent* FPI dei value can be flat wrong - a home-market ordinary-
share count, not the ADS-equivalent count `current_price` is quoted in). `test_recent_dei_value_
still_accepted` therefore now uses a DOMESTIC filer (the only case that still reaches this tier at
all) instead of an FPI - the underlying claim being tested (a value inside the 2-year recency
window is still trusted) is unchanged, just the symbol shape needed updating to stay reachable.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...] | None]) -> None:
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
    symbol: str,
    income_rows: list[tuple[Any, ...]],
    fetchone_results: list[tuple[Any, ...] | None],
) -> list[dict[str, Any]]:
    loader = _make_loader()
    fake_cursor = _FakeCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        return loader.fetch_incremental(symbol, None)


class TestDeiSharesOutstandingStalenessRejected:
    def test_stale_dei_value_rejected_falls_through_to_fpi_yfinance(self) -> None:
        """ENIC/CEPU/AIFU-shaped: the only shares_outstanding_dei value on file is from a
        fiscal year more than 2 years before the symbol's most recent fiscal year - must be
        rejected, falling through to the FPI-yfinance live-fetch tier rather than trusted."""
        # is_foreign_private_issuer=True (index 10) - every tier before the dei one is gated
        # off entirely for an FPI (see fetch_incremental's own "shares_out = None" comment
        # block), so only cash/debt/[dei never reached: is_foreign_private_issuer now skips
        # it too]/price/... are actually queried. This symbol's specific staleness no longer
        # matters - ANY foreign private issuer falls straight through to FPI-yfinance now.
        income_rows = [
            (2024, 738_169_736_000.0, 61_254_079_000.0, 33.01, None, None, None, None, None, None, True, 6022),
        ]
        fetchone_results: list[tuple[Any, ...] | None] = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (30_000_000.0,),  # cash_and_equivalents
            (5_000_000.0, None, None, None),  # debt_row
            (2.23,),  # price_daily.close
            (100_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check
            (None, None),  # yfinance_snapshot market_cap/pe_ratio
        ]

        with (
            patch.object(
                SecValuationsLoader,
                "_fetch_live_fpi_shares_outstanding_yfinance",
                return_value=1_421_491_965.0,
            ) as mock_fpi_shares_fetch,
            patch.object(SecValuationsLoader, "_fetch_live_fpi_yfinance_check_values", return_value=(None, None, None)),
        ):
            result = _run_fetch_incremental("ENIC", income_rows, fetchone_results)

        mock_fpi_shares_fetch.assert_called_once_with("ENIC")
        row = result[0]
        # Resolved via the yfinance fallback (1.42B), NOT the stale FY2017 dei figure (49.09B).
        assert row.get("shares_outstanding") == pytest.approx(1_421_491_965.0)
        assert row.get("data_source") == "sec_audited_except_fpi_shares_yfinance"

    def test_recent_dei_value_still_accepted(self) -> None:
        """Companion case: a dei value from within the 2-year recency window must still be
        used exactly as before - this fix must not become a blanket rejection.

        Uses a DOMESTIC filer (is_foreign_private_issuer=False) - after the 5e3f144f0 cherry-
        pick added `not is_foreign_private_issuer` to this tier's gate, an FPI never reaches it
        at all any more (see the class docstring's UPDATED note), so this is now the only shape
        that still exercises the recency-bound logic itself. net_income/eps are left None so the
        earlier in-memory net_income/eps derivation tier can't short-circuit before reaching the
        dei tier; the scale-mismatch cross-check tier (fires once shares_out is set, domestic
        filers only) is included as an extra no-op fetchone()."""
        income_rows = [
            (2024, 10_000_000.0, None, None, None, None, None, None, None, None, False, 7372),
        ]
        fetchone_results: list[tuple[Any, ...] | None] = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (1_000_000.0,),  # cash_and_equivalents
            (500_000.0, None, None, None),  # debt_row
            None,  # dual-class sibling check -> not dual class
            (None,),  # older-fiscal-year shares_outstanding_basic fallback
            (None,),  # company_info_sec fallback
            (None,),  # diluted shares fallback
            (5_000_000.0, 2023),  # shares_outstanding_dei - recent (FY2023 vs most recent FY2024)
            (None,),  # scale-mismatch cross-check (company_info_sec) - no mismatch found
            (10.0,),  # price_daily.close
            (20_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check
            (None, None),  # yfinance_snapshot market_cap/pe_ratio
        ]

        with (
            patch.object(SecValuationsLoader, "_fetch_live_fpi_shares_outstanding_yfinance") as mock_fpi_shares_fetch,
            patch.object(SecValuationsLoader, "_fetch_live_fpi_yfinance_check_values", return_value=(None, None, None)),
        ):
            result = _run_fetch_incremental("RECENTDOM", income_rows, fetchone_results)

        mock_fpi_shares_fetch.assert_not_called()
        row = result[0]
        assert row.get("shares_outstanding") == pytest.approx(5_000_000.0)
        assert row.get("data_source") == "sec_audited"

    def test_stale_dei_value_rejected_for_domestic_filer_too(self) -> None:
        """The recency bound itself (not just the FPI gate) must still reject a stale value for
        a domestic filer - the dei query's own `fiscal_year >= this_year - 2` WHERE clause
        excludes a too-old row entirely, so fetchone() returns None and every subsequent tier
        (there is no yfinance fallback for a domestic filer) leaves shares_out unresolved."""
        income_rows = [
            (2024, 10_000_000.0, None, None, None, None, None, None, None, None, False, 7372),
        ]
        fetchone_results: list[tuple[Any, ...] | None] = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (1_000_000.0,),  # cash_and_equivalents
            (500_000.0, None, None, None),  # debt_row
            None,  # dual-class sibling check -> not dual class
            (None,),  # older-fiscal-year shares_outstanding_basic fallback
            (None,),  # company_info_sec fallback
            (None,),  # diluted shares fallback
            None,  # dei tier - stale row excluded by the query's own recency WHERE clause
            (10.0,),  # price_daily.close (no cross-check tier: shares_out never got set)
            (20_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check
            (None, None),  # yfinance_snapshot market_cap/pe_ratio
        ]

        with (
            patch.object(SecValuationsLoader, "_fetch_live_fpi_shares_outstanding_yfinance") as mock_fpi_shares_fetch,
            patch.object(SecValuationsLoader, "_fetch_live_fpi_yfinance_check_values", return_value=(None, None, None)),
        ):
            result = _run_fetch_incremental("STALEDOM", income_rows, fetchone_results)

        mock_fpi_shares_fetch.assert_not_called()
        row = result[0]
        assert row.get("shares_outstanding") is None
        assert row.get("data_unavailable") is True
        assert row.get("reason") == "shares_outstanding_unavailable"

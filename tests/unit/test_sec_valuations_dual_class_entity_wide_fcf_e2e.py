"""End-to-end regression test for the 2026-08-25 entity-wide-FCF-denominator fix (goal:
"margin of safety results look wrong" audit), exercised through the full fetch_incremental
path rather than _compute_valuations directly.

Live-confirmed root cause: TAP.A's shares_outstanding resolves via the UNGATED
company_info_sec fallback tier (same path as
test_sec_valuations_dual_class_yfinance_shares_fallback.py's
test_dual_class_yfinance_never_called_when_an_sec_tier_already_resolved / AGM.A case) - NOT
the yfinance dual-class tier - so data_source stays "sec_audited" and
shares_out_from_dual_class_yfinance is never set, even though shares_out is still
class-specific (2.56M, Molson Coors' Class A float, vs ~188M combined). Meanwhile
annual_cash_flow.operating_cash_flow/capex is entity-wide (SEC's companyfacts API collapses
every concept to one value per CIK+period, duplicated verbatim across sibling tickers) -
dividing that entity-wide FCF by the tiny class-specific share count inflated TAP.A's
fcf_yield to 936% and margin_of_safety_pct to 99.8% on a normally-priced stock.

This test locks in the fix at the has_dual_class_sibling level (not the narrower
shares_out_from_dual_class_yfinance flag it was first written against), confirming
fcf_yield/intrinsic_value_per_share use the entity-wide reported_shares_outstanding while
market_cap/pe_ratio stay pinned to the class-specific shares_out.
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
        # ocf=80M, capex=10M -> entity-wide fcf_base = 70M, same fixed shape every other
        # test file in this suite uses.
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


class TestDualClassEntityWideFcfEndToEnd:
    def test_company_info_sec_resolved_class_specific_shares_still_gets_entity_wide_fcf(self) -> None:
        # reported_shares_outstanding (index 8) = 700M: entity-wide collapsed SEC figure,
        # present even though has_dual_class_sibling gates it off as shares_out's own source.
        income_rows = [
            (2025, 400_000_000_000.0, 90_000_000_000.0, 54.0, None, None, None, None, 700_000_000.0, None, False),
        ]
        fetchone_results = [
            (5_000_000_000.0,),  # cash_and_equivalents
            (10_000_000_000.0, None, None, None),  # debt_row
            (1,),  # dual-class sibling check - found
            (2_000_000.0,),  # company_info_sec fallback (tier 4) - class-specific, REAL row
            None,  # company_info_sec cross-check (line ~689) - no data, no-op
            (50.0,),  # price_daily.close
            (700_000_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX (economic_data VIXCLS)
            (20.0,),  # long-run avg VIX - equal to current so dynamic ERP == static 5% (not under test here)
            None,  # net borrowing check (2026-08-25) - no adjacent-year debt data, DCF falls back to OCF-CapEx-SBC unchanged
            (None, None),  # yfinance_snapshot sanity check
        ]

        with patch.object(SecValuationsLoader, "_fetch_live_dual_class_shares_outstanding") as mock_dual_class_fetch:
            result = _run_fetch_incremental("TAP.A", income_rows, fetchone_results)

        mock_dual_class_fetch.assert_not_called()  # company_info_sec already resolved it
        row = result[0]
        assert row["data_source"] == "sec_audited"  # not the yfinance-flagged label
        assert row["shares_outstanding"] == 2_000_000.0  # class-specific, unchanged

        # market_cap/pe_ratio: still pinned to the class-specific share count.
        assert row["market_cap"] == round(50.0 * 2_000_000.0, 2)

        # fcf_yield: entity-wide fcf (70M) / entity-wide market cap (50 * 700M), NOT the
        # class-specific market cap (50 * 2M) - the bug would have produced 350.0% here.
        expected_entity_market_cap = 50.0 * 700_000_000.0
        expected_fcf_yield = round((70_000_000.0 / expected_entity_market_cap) * 100, 2)
        assert row["fcf_yield"] == expected_fcf_yield
        assert row["fcf_yield"] < 1.0  # sanity: nowhere near the pre-fix 350%/936%-class blowup

        # DCF: intrinsic value computed against the entity-wide share count, matching what
        # _compute_dcf_intrinsic_value itself produces for the same inputs directly.
        loader = _make_loader()
        expected_ivps, expected_mos = loader._compute_dcf_intrinsic_value(
            "TAP.A", fcf=70_000_000.0, eps_growth_pct=0.0, shares_out=700_000_000.0, current_price=50.0
        )
        assert row["intrinsic_value_per_share"] == expected_ivps
        assert row["margin_of_safety_pct"] == expected_mos

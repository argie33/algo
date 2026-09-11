"""Regression test (2026-09-11, goal: "under 300" push, total_debt_not_itemized
re-investigation): recategorize_balance_sheet_currency_fields() (loaders/helpers/vqg_shared.py)
already fixes roa/asset_turnover/debt_to_assets/gross_profitability (total-assets-derived) and
roe/debt_to_equity/sustainable_growth_rate (equity-derived) for a confirmed unsupported-
currency-balance-sheet symbol, but never covered the standalone total_debt field itself or
roce_pct (which fails the same way whenever its own total_debt lookup is what's missing) - both
stayed on the generic "total_debt_not_itemized" instead of the real "unsupported_currency_
no_fx_rate" cause every sibling field on the same row already carries.

Live-confirmed CEPU/CRESY/IRS/LOMA/BMA (Argentine 20-F/40-F filers, all already recognized by
_get_unsupported_currency_balance_sheet_symbols()): debt_to_equity correctly shows
"unsupported_currency_no_fx_rate" while total_debt/roce_pct still showed the generic reason.
"""

from typing import Any

from loaders.helpers.vqg_shared import recategorize_balance_sheet_currency_fields


class TestTotalDebtRocePctCurrencyRecategorize:
    def test_total_debt_gets_currency_reason(self) -> None:
        metrics: dict[str, Any] = {
            "total_debt": None,
            "total_debt_unavailable_reason": "total_debt_not_itemized",
        }

        recategorize_balance_sheet_currency_fields(metrics)

        assert metrics["total_debt_unavailable_reason"] == "unsupported_currency_no_fx_rate"

    def test_roce_pct_gets_currency_reason(self) -> None:
        metrics: dict[str, Any] = {
            "roce_pct": None,
            "roce_pct_unavailable_reason": "total_debt_not_itemized",
        }

        recategorize_balance_sheet_currency_fields(metrics)

        assert metrics["roce_pct_unavailable_reason"] == "unsupported_currency_no_fx_rate"

    def test_does_not_touch_a_real_computed_value(self) -> None:
        metrics: dict[str, Any] = {
            "total_debt": 500.0,
            "total_debt_unavailable_reason": "total_debt_not_itemized",
        }

        recategorize_balance_sheet_currency_fields(metrics)

        assert metrics["total_debt_unavailable_reason"] == "total_debt_not_itemized"

    def test_does_not_touch_a_different_already_specific_reason(self) -> None:
        metrics: dict[str, Any] = {
            "total_debt": None,
            "total_debt_unavailable_reason": "negative_free_cash_flow",
        }

        recategorize_balance_sheet_currency_fields(metrics)

        assert metrics["total_debt_unavailable_reason"] == "negative_free_cash_flow"

    def test_roce_pct_own_more_specific_reason_untouched(self) -> None:
        # roce_pct can independently fail for operating_income_not_itemized (a different
        # root cause than total_debt) - must not be swept into the currency reason.
        metrics: dict[str, Any] = {
            "roce_pct": None,
            "roce_pct_unavailable_reason": "operating_income_not_itemized",
        }

        recategorize_balance_sheet_currency_fields(metrics)

        assert metrics["roce_pct_unavailable_reason"] == "operating_income_not_itemized"

    def test_existing_equity_and_total_assets_fields_still_work(self) -> None:
        # Guard against regressing the two existing loops this fix sits alongside.
        metrics: dict[str, Any] = {
            "roa": None,
            "roa_unavailable_reason": "no_recent_total_assets_reported",
            "roe": None,
            "roe_unavailable_reason": "stockholders_equity_not_reported",
        }

        recategorize_balance_sheet_currency_fields(metrics)

        assert metrics["roa_unavailable_reason"] == "unsupported_currency_no_fx_rate"
        assert metrics["roe_unavailable_reason"] == "unsupported_currency_no_fx_rate"

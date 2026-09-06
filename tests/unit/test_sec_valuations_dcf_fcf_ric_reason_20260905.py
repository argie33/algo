"""Regression test (2026-09-05, goal: "SEC/XBRL missing data to zero" follow-up):
sec_valuations.dcf_fcf_unavailable_reason never distinguished a registered investment company
(closed-end fund/investment trust, which files a "Statement of Changes in Net Assets" with no
conventional cash-flow-statement concepts to tag at all) from a generic missing-cash-flow-data
gap - same root fact already fixed today for fcf_margin/fcf_yield/accruals_ratio/
ocf_to_net_income/roic_pct/debt_to_equity in loaders/helpers/vqg_quality.py and vqg_value.py,
just not recognized here since load_sec_valuations.py's SecValuationYieldDcfMixin has no access
to ValueQualityGrowthMetricsLoader's _get_registered_investment_company_symbols() gate
(different class hierarchy) - fixed via a small inline query in fetch_incremental instead.

Live-confirmed 7 universe symbols (EVN/BSTZ/CEV/BTX/BUI/JHI/PMO) hitting this exact shape.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    """Sequential fetchone/fetchall stand-in - see the sibling
    test_sec_valuations_ebitda_prefers_populated_fiscal_year.py file's _FakeCursor docstring for
    why fetchall() must be sequential. One extra fetchone() slot appended at the end for this
    fix's new RIC-check query, which runs after every other downstream lookup."""

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
        result = self._fetchone_results[self._fetchone_idx]
        self._fetchone_idx += 1
        return result


# Same downstream fetchone() sequence as
# test_sec_valuations_ebitda_pretax_fallback_interest_addback_20260905.py, plus one more slot at
# the end for this fix's new RIC-check query.
_BASE_DOWNSTREAM_FETCHONE = [
    None,  # entity_type exemption gate check (138006446) - not exempt
    (30_000_000.0,),
    (20_000_000.0, 5_000_000.0, None, None),
    None,
    (None, None),
    (None,),
    (35.26,),
    (500_000_000.0,),
    (1.0,),
    (4.5,),
    (20.0,),
    (20.0,),
    None,
    (None, None),
]

_INCOME_ROWS = [
    (
        2025,
        100_000_000.0,
        10_000_000.0,
        1.0,
        8_000_000.0,
        9_000_000.0,
        None,
        None,
        50_000_000.0,
        None,
        False,
        6726,
        None,
    ),
]


def _run(
    ric_query_result: tuple[Any, ...] | None,
    currency_query_result: tuple[Any, ...] | None = None,
    capex_query_result: tuple[Any, ...] | None = None,
    blank_check_query_result: tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    loader = _make_loader()
    # ADDED 2026-09-06 (sibling fix: _recategorize_unsupported_currency_dcf_fcf_reason): its
    # own fetchone() slot only gets consumed when the RIC check above did NOT already
    # override the reason - _recategorize_unsupported_currency_dcf_fcf_reason's own guard
    # returns early (no query at all) once dcf_fcf_unavailable_reason is no longer the
    # generic "missing_cash_flow_data", same short-circuit discipline as the RIC check has
    # for the reasons checked before it.
    extra_fetchone = [] if ric_query_result is not None else [currency_query_result]
    # ADDED 2026-09-06 (sibling fix: _recategorize_capex_never_tagged_dcf_fcf_reason, after
    # the royalty-trust check - pure membership, no query slot): its own fetchone() slot only
    # gets consumed when neither the RIC nor currency check already overrode the reason, same
    # short-circuit discipline.
    still_generic = ric_query_result is None and currency_query_result is None
    extra_fetchone2 = [] if not still_generic else [capex_query_result]
    # ADDED 2026-09-06 (sibling fix: _recategorize_blank_check_dcf_fcf_reason, after the capex
    # check): its own fetchone() slot only gets consumed when none of RIC/currency/capex above
    # already overrode the reason, same short-circuit discipline.
    still_generic = still_generic and capex_query_result is None
    extra_fetchone3 = [] if not still_generic else [blank_check_query_result]
    fake_cursor = _FakeCursor(
        _INCOME_ROWS,
        [*_BASE_DOWNSTREAM_FETCHONE, ric_query_result, *extra_fetchone, *extra_fetchone2, *extra_fetchone3],
    )
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    # Force dcf_fcf_base to None (ocf/capex both unusable) so
    # _compute_yield_and_dcf_fields's own fallback lands on "missing_cash_flow_data" -
    # this fix's new code only overrides that exact generic reason.
    forced_yield_dcf_result = {
        "fcf_yield": None,
        "fcf_yield_unavailable_reason": "missing_cash_flow_data",
        "dividend_yield": None,
        "net_payout_yield": None,
        "enterprise_value": 500_000_000.0,
        "ev_ebitda": None,
        "ev_revenue": None,
        "intrinsic_value_per_share": None,
        "margin_of_safety_pct": None,
        "dcf_fcf_unavailable_reason": "missing_cash_flow_data",
    }

    with (
        patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx),
        patch.object(SecValuationsLoader, "_compute_yield_and_dcf_fields", return_value=forced_yield_dcf_result),
    ):
        return loader.fetch_incremental("RICCO", None)


class TestSecValuationsDcfFcfRicReason:
    def test_ric_shaped_symbol_reports_registered_investment_company_reason(self) -> None:
        result = _run(ric_query_result=(1,))  # RIC-check query matches

        row = result[0]
        assert row["dcf_fcf_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_non_ric_symbol_keeps_generic_reason(self) -> None:
        result = _run(ric_query_result=None, currency_query_result=None)  # neither check matches

        row = result[0]
        assert row["dcf_fcf_unavailable_reason"] == "missing_cash_flow_data"

    def test_unsupported_currency_symbol_reports_specific_reason(self) -> None:
        """Companion to the RIC case above (2026-09-06 sibling fix): a foreign private issuer
        whose annual_cash_flow row was already tagged 'unsupported_currency_no_fx_rate' by
        load_financial_statements.py's own fix gets that same specific reason here too,
        instead of the generic fallback - checked only after the RIC case doesn't match."""
        result = _run(ric_query_result=None, currency_query_result=(1,))

        row = result[0]
        assert row["dcf_fcf_unavailable_reason"] == "unsupported_currency_no_fx_rate"

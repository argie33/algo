#!/usr/bin/env python3
"""Custom-XBRL-extension fallbacks for ConsolidatedFinancialStatementsLoader.fetch_incremental().

Extracted out of loaders/load_financial_statements.py (2026-09-10, file-size ratchet - that
file was pushing the 2000-line hard ceiling) - purely a relocation, no behavior change beyond
the fiscal_period gating fix described below.

Every fetch_custom_*() function here (from utils/external/sec_custom_xbrl_concepts.py) fetches
a value from the symbol's LATEST ANNUAL FILING ONLY (per each function's own docstring), for
filers whose real figure is tagged under a company-specific XBRL extension concept the normal
companyfacts-API-driven concept-list extraction structurally can't reach.

FIX 2026-09-10 (root-causing the quarterly_revenue_annual_duplicate DataPatrol finding, which
survived two prior one-off DB-patch "fixes" - commits 669b6797e and e4b0e9023 - neither of
which touched this code, so every reload reproduced it identically): every apply_custom_*()
function below used to write its annual-only fetched value onto EVERY row sharing a
fiscal_year, with no check for which period that row actually represents. When the loader runs
in quarterly mode, `rows` contains one row per quarter - all 4 got the identical annual figure
(e.g. APA's FY2025 revenue, $8.951B, injected into custom_extension_revenue for Q1-Q4 alike).
That field is fallback_only in the field mapping, so it only actually lands in the final column
when the normal quarterly SEC extraction found nothing - exactly APA's case (live-confirmed:
a direct get_income_statement(period='quarterly') call returns revenue=None for every quarter).
Fixed by gating every loop to annual rows only. Row shape at this point in the pipeline uses
"fiscal_period" (string: 'Q1'-'Q4' for quarterly rows, 'FY' for annual - live-confirmed via a
real fetch_incremental('APA') call), NOT the post-transform "fiscal_quarter" int column used
later in the pipeline - an easy mix-up (the first version of this fix used the wrong field name
and appeared to work only because its own test mocks made the same mistake consistently).
"""

from typing import Any

from utils.external.sec_custom_xbrl_concepts import (
    CUSTOM_CAPEX_CONCEPTS,
    CUSTOM_CAPEX_DIMENSIONED_CONCEPTS,
    CUSTOM_DEBT_CONCEPTS,
    CUSTOM_DEBT_LONGTERM_CONCEPTS,
    CUSTOM_DEBT_SHORTTERM_CONCEPTS,
    CUSTOM_DIVIDEND_CONCEPTS,
    CUSTOM_INCOME_DIMENSIONED_CONCEPTS,
    CUSTOM_REVENUE_CONCEPTS,
    fetch_custom_capex,
    fetch_custom_capex_dimensioned_sum,
    fetch_custom_debt,
    fetch_custom_debt_longterm,
    fetch_custom_debt_shortterm,
    fetch_custom_dividends,
    fetch_custom_income_dimensioned,
    fetch_custom_revenue,
)


def _annual_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("fiscal_period") == "FY"]


def apply_custom_income_extensions(
    symbol: str, rows: list[dict[str, Any]], statement_type: str, sec_client: Any
) -> None:
    """CUSTOM_REVENUE_CONCEPTS (APA/...) -> custom_extension_revenue (revenue), and
    CUSTOM_INCOME_DIMENSIONED_CONCEPTS (dei:LegalEntityAxis-dimensioned bank net_income/EPS) ->
    custom_extension_net_income/eps_basic/eps_diluted. Only called when statement_type=="income".
    """
    if statement_type != "income":
        return
    if symbol in CUSTOM_REVENUE_CONCEPTS:
        custom_revenue_by_year = fetch_custom_revenue(symbol, sec_client)
        for row in _annual_rows(rows):
            fiscal_year = row.get("fiscal_year")
            if fiscal_year in custom_revenue_by_year:
                row["custom_extension_revenue"] = custom_revenue_by_year[fiscal_year]

    if symbol in CUSTOM_INCOME_DIMENSIONED_CONCEPTS:
        custom_income_fields = fetch_custom_income_dimensioned(symbol, sec_client)
        for row in _annual_rows(rows):
            fiscal_year = row.get("fiscal_year")
            for field_key, values_by_year in custom_income_fields.items():
                if fiscal_year in values_by_year:
                    row[field_key] = values_by_year[fiscal_year]


def apply_custom_cashflow_extensions(symbol: str, rows: list[dict[str, Any]], sec_client: Any) -> None:
    """CUSTOM_CAPEX_CONCEPTS (DHT/CMRE/...) -> custom_extension_vessel_capex (capex);
    CUSTOM_CAPEX_DIMENSIONED_CONCEPTS (NJR/MUX) -> custom_extension_capex_dimensioned_sum
    (capex); CUSTOM_DIVIDEND_CONCEPTS (CMS/SPG/RS/HUBB) -> custom_extension_dividends_paid
    (dividends_paid). Only called when statement_type=="cashflow".
    """
    if symbol in CUSTOM_CAPEX_CONCEPTS:
        custom_capex_by_year = fetch_custom_capex(symbol, sec_client)
        for row in _annual_rows(rows):
            fiscal_year = row.get("fiscal_year")
            if fiscal_year in custom_capex_by_year:
                row["custom_extension_vessel_capex"] = custom_capex_by_year[fiscal_year]

    if symbol in CUSTOM_CAPEX_DIMENSIONED_CONCEPTS:
        dimensioned_capex_by_year = fetch_custom_capex_dimensioned_sum(symbol, sec_client)
        for row in _annual_rows(rows):
            fiscal_year = row.get("fiscal_year")
            if fiscal_year in dimensioned_capex_by_year:
                row["custom_extension_capex_dimensioned_sum"] = dimensioned_capex_by_year[fiscal_year]

    if symbol in CUSTOM_DIVIDEND_CONCEPTS:
        custom_dividends_by_year = fetch_custom_dividends(symbol, sec_client)
        for row in _annual_rows(rows):
            fiscal_year = row.get("fiscal_year")
            if fiscal_year in custom_dividends_by_year:
                row["custom_extension_dividends_paid"] = custom_dividends_by_year[fiscal_year]


def apply_custom_debt_extensions(symbol: str, rows: list[dict[str, Any]], sec_client: Any) -> None:
    """CUSTOM_DEBT_CONCEPTS (BRK.A/BRK.B, dimensioned-sum) -> custom_extension_total_debt
    (long_term_debt); CUSTOM_DEBT_LONGTERM_CONCEPTS/CUSTOM_DEBT_SHORTTERM_CONCEPTS (AES) ->
    custom_extension_total_debt (long_term_debt) / custom_extension_total_debt_current
    (short_term_debt). Only called when statement_type=="balance".
    """
    if symbol in CUSTOM_DEBT_CONCEPTS:
        custom_debt_by_year = fetch_custom_debt(symbol, sec_client)
        for row in _annual_rows(rows):
            fiscal_year = row.get("fiscal_year")
            if fiscal_year in custom_debt_by_year:
                row["custom_extension_total_debt"] = custom_debt_by_year[fiscal_year]
    if symbol in CUSTOM_DEBT_LONGTERM_CONCEPTS:
        custom_debt_lt_by_year = fetch_custom_debt_longterm(symbol, sec_client)
        for row in _annual_rows(rows):
            fiscal_year = row.get("fiscal_year")
            if fiscal_year in custom_debt_lt_by_year:
                row["custom_extension_total_debt"] = custom_debt_lt_by_year[fiscal_year]
    if symbol in CUSTOM_DEBT_SHORTTERM_CONCEPTS:
        custom_debt_st_by_year = fetch_custom_debt_shortterm(symbol, sec_client)
        for row in _annual_rows(rows):
            fiscal_year = row.get("fiscal_year")
            if fiscal_year in custom_debt_st_by_year:
                row["custom_extension_total_debt_current"] = custom_debt_st_by_year[fiscal_year]

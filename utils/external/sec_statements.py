#!/usr/bin/env python3
"""SEC EDGAR financial statement extractors.

High-level helpers for extracting balance sheet, income statement, and cash flow data.
These methods leverage the SecEdgarClient for company facts and aggregate multiple
GAAP concepts into structured financial statements.

Foreign private issuers (20-F/40-F filers - ADRs like ABEV, E, AEG, ACB, IBN) report
under the IFRS taxonomy (facts["ifrs-full"]) instead of, or in addition to, us-gaap.
Many report ZERO us-gaap concepts (e.g. ABEV: 0 us-gaap, 298 ifrs-full), so extracting
only us-gaap silently drops fundamental data SEC EDGAR actually has for these filers.
Each concept list below is followed by an IFRS_ALIASES list: (ifrs_concept, target_key)
pairs where target_key is the SAME snake_cased key the equivalent GAAP concept would
produce, so downstream field_mapping in load_financial_statements.py needs no changes -
an IFRS-sourced row looks identical to a GAAP-sourced one once aggregated.

REORGANIZED 2026-09-05 (file-size ratchet: this file was a Tier-2 bloater flagged for
decomposition, ~2070 lines). This module is now a thin re-export shim - all real logic
moved verbatim to sibling modules, split along the same three-statement boundary the
public API (get_balance_sheet/get_income_statement/get_cash_flow) already implies:
  - utils/external/sec_statements_shared.py: dependency-free constants/helpers
    (_extract_currency_code, _fx_rate_cache, _MIN_PLAUSIBLE_FISCAL_YEAR,
    _PRIMARY_STATEMENT_FORMS, _ANNUAL_REPORT_FORMS) shared by the aggregation engine.
  - utils/external/sec_statements_aggregate.py (+ _entry_resolution.py/_unit_context.py):
    the _aggregate_concepts engine, extracted earlier the same day.
  - utils/external/sec_balance_sheet.py: get_balance_sheet + its two long-term-debt
    fallback helpers + _BALANCE_IFRS_ALIASES.
  - utils/external/sec_income_statement.py: get_income_statement +
    _INCOME_IFRS_ALIASES/_INCOME_DEI_ALIASES.
  - utils/external/sec_income_statement_fallbacks.py: get_income_statement's five fallback
    post-processing helpers (further split out once sec_income_statement.py itself hit the
    800-line new-file cap).
  - utils/external/sec_cash_flow.py: get_cash_flow + _CASHFLOW_IFRS_ALIASES.
Every name below is re-exported unchanged so existing callers/tests importing from
`utils.external.sec_statements` (dozens of test files, sec_edgar_client.py, sec_edgar.py)
keep working with no import-line changes. Bodies are verbatim in their new homes - only
moved, no logic changed.
"""

from utils.external.sec_balance_sheet import (
    _BALANCE_IFRS_ALIASES,
    _fill_long_term_debt_from_noncurrent_current_split,
    _fill_long_term_debt_from_segment_dimensional_facts,
    get_balance_sheet,
)
from utils.external.sec_cash_flow import (
    _CASHFLOW_IFRS_ALIASES,
    get_cash_flow,
)
from utils.external.sec_income_statement import (
    _INCOME_DEI_ALIASES,
    _INCOME_IFRS_ALIASES,
    get_income_statement,
)
from utils.external.sec_income_statement_fallbacks import (
    _fill_earnings_per_share_from_continuing_discontinued_split,
    _fill_eps_shares_from_dual_class_dimensional_facts,
    _fill_income_tax_expense_from_current_deferred_split,
    _fill_operating_income_from_revenue_minus_costs_and_expenses,
    _fill_pretax_income_from_domestic_foreign_split,
    _fill_pretax_income_from_results_of_operations_when_validated,
)
from utils.external.sec_statements_aggregate import _aggregate_concepts, _to_snake
from utils.external.sec_statements_shared import (
    _ANNUAL_REPORT_FORMS,
    _MIN_PLAUSIBLE_FISCAL_YEAR,
    _PRIMARY_STATEMENT_FORMS,
    _extract_currency_code,
    _fx_rate_cache,
)

__all__ = [
    "_ANNUAL_REPORT_FORMS",
    "_BALANCE_IFRS_ALIASES",
    "_CASHFLOW_IFRS_ALIASES",
    "_INCOME_DEI_ALIASES",
    "_INCOME_IFRS_ALIASES",
    "_MIN_PLAUSIBLE_FISCAL_YEAR",
    "_PRIMARY_STATEMENT_FORMS",
    "_aggregate_concepts",
    "_extract_currency_code",
    "_fill_earnings_per_share_from_continuing_discontinued_split",
    "_fill_eps_shares_from_dual_class_dimensional_facts",
    "_fill_income_tax_expense_from_current_deferred_split",
    "_fill_long_term_debt_from_noncurrent_current_split",
    "_fill_long_term_debt_from_segment_dimensional_facts",
    "_fill_operating_income_from_revenue_minus_costs_and_expenses",
    "_fill_pretax_income_from_domestic_foreign_split",
    "_fill_pretax_income_from_results_of_operations_when_validated",
    "_fx_rate_cache",
    "_to_snake",
    "get_balance_sheet",
    "get_cash_flow",
    "get_income_statement",
]

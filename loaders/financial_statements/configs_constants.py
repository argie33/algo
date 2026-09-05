"""Shared constants for the financial-statements config zone.

Split out of load_financial_statements.py (see that module's top docstring). Consumed by
configs_income.py/configs_balance.py/configs_cashflow.py.
"""

# REQUIRED metric fields per statement type - a row with all of these NULL has no usable
# data regardless of what optional fields it carries. Shared between transform() (governs
# freshly-fetched rows) and post_run()'s force-null flag sync (governs rows whose values
# were wiped by _reject_stale_fpi_currency_data/_reject_implausible_* without going back
# through transform() - see post_run() for why that sync is necessary).
_REQUIRED_STATEMENT_FIELDS = {
    "income": {"revenue", "net_income"},
    "balance": {"total_assets", "stockholders_equity"},
    "cashflow": {"operating_cash_flow"},
}

# data_unavailable/reason must pass through so marker rows keep their flags.
_MARKER_FIELDS = {
    "data_unavailable": "data_unavailable",
    "reason": "reason",
    # FIXED 2026-08-16: added alongside the yfinance fallback (loaders/helpers/sec_base.py's
    # SecEdgarStatementLoader._try_yfinance_fallback) - every row now carries an explicit
    # 'sec_audited' or 'yfinance' tag (migration 1202) so a lower-fidelity fallback row is
    # never indistinguishable from a real SEC filing, per the same governance discipline
    # tests/unit/test_company_info_sec_no_yfinance_pollution.py enforces elsewhere.
    "data_source": "data_source",
}

# Quarterly rows carry fiscal_period ("Q1".."Q4"), which transform() converts to the
# integer fiscal_quarter column. Annual rows' fiscal_period ("FY") stays unmapped -
# annual tables have no fiscal_quarter column.
_QUARTERLY_EXTRA = {"fiscal_period": "fiscal_quarter"}

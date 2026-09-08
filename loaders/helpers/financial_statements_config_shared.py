"""Small constants shared across the income/balance/cashflow config modules
(extracted 2026-09-07 alongside those three modules from load_financial_statements.py -
see loaders/helpers/financial_statements_income_config.py's docstring for the full
extraction rationale). Kept separate from the three statement-specific modules purely
to avoid a circular import between them (balance and cashflow both need
_QUARTERLY_EXTRA; all three need _MARKER_FIELDS).
"""

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

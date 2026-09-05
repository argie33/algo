"""Shared constants/helpers for the SEC EDGAR financial-statement extractors, extracted
from sec_statements.py (2026-09-05, file-size ratchet: it's a Tier-2 bloater flagged for
decomposition). Bodies are verbatim, no logic changed - only moved file.

Deliberately dependency-free with respect to sec_statements.py itself (and the
sec_statements_aggregate/_entry_resolution/_unit_context modules it in turn depends on) -
those modules import _extract_currency_code/_fx_rate_cache/_MIN_PLAUSIBLE_FISCAL_YEAR/
_PRIMARY_STATEMENT_FORMS/_ANNUAL_REPORT_FORMS from HERE rather than from sec_statements.py,
so sec_statements.py can re-export get_balance_sheet/get_income_statement/get_cash_flow
(now defined in their own sibling modules, which themselves depend on
sec_statements_aggregate) without recreating the circular-import trap the original
single-file layout required a mid-file import to work around.
"""

from utils.external.fx_rates import FxRateCache

# FIXED 2026-08-17 (goal: "no SEC data" audit): module-level so the (currency, date)
# rate cache is shared and its persistent file cache reused across every symbol
# processed in a run, not just within one _aggregate_concepts call. See fx_rates.py's
# module docstring for the CAD/GBP/EUR/AUD/CHF/JPY-only fix this backs.
_fx_rate_cache = FxRateCache()

# See the "implausible fiscal_year" sanity-bound comment in _aggregate_concepts
# (BUG FOUND 2026-08-19).
_MIN_PLAUSIBLE_FISCAL_YEAR = 1990


def _extract_currency_code(unit: str) -> str:
    """Return the bare currency code from an XBRL unit string.

    Per-share concepts (BasicEarningsLossPerShare etc.) use compound units like
    "CAD/shares", not a bare "CAD" - the currency-rejection/conversion guard below
    only ever matched bare 3-letter units, so foreign filers' EPS silently passed
    through unconverted (and un-rejected) regardless of currency. Splitting on "/"
    first makes "CAD/shares" -> "CAD" (subject to the same reject-or-convert rule as
    a bare "CAD" monetary fact) while "shares"/"pure"/"USD/shares" -> "shares"/"pure"/
    "USD" still correctly fall outside the 3-letter-uppercase-code shape.
    """
    return unit.split("/", 1)[0]


# Forms that carry audited/reviewed primary financial statements. See the
# "FIXED 2026-08-17 (goal: 'no SEC data' audit)" comment in _aggregate_concepts for why
# these must outrank other forms (DEF 14A Pay vs Performance tables, 8-K, S-1, etc.)
# regardless of filing date - those forms retag figures like NetIncomeLoss without a
# reliable guarantee of the correct XBRL scale.
_PRIMARY_STATEMENT_FORMS = {
    "10-K",
    "10-K/A",
    "10-KT",
    "10-KT/A",
    "10-Q",
    "10-Q/A",
    "10-QT",
    "10-QT/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
    "6-K",
    "6-K/A",
}

# Forms that represent a genuine fiscal-year-end annual report (as opposed to a 10-Q/6-K
# interim filing). See the "FIXED 2026-08-18 (no-SEC-data audit continuation)" comment in
# _aggregate_concepts for why instant (point-in-time) balance-sheet facts need this
# narrower set: a 10-Q's balance sheet is a real, valid "as of" snapshot, but it's a
# mid-year snapshot, not the fiscal year's actual year-end position.
_ANNUAL_REPORT_FORMS = {
    "10-K",
    "10-K/A",
    "10-KT",
    "10-KT/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
}

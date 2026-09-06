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

from typing import Any

from utils.external.fx_rates import MAJOR_CURRENCIES, FxRateCache

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


def has_unsupported_currency_only_fact(
    client: Any, symbol: str, us_gaap_concepts: list[str], ifrs_concepts: list[str]
) -> bool:
    """True if the filer tagged a real value for one of these concepts, but ONLY under a
    non-USD, non-major currency (see fx_rates.MAJOR_CURRENCIES) - a genuine SEC data point
    that exists but can't be safely converted, distinct from a true absence.

    ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): live-confirmed GGAL/BBAR/
    BSAC/SUPV/TEO/TKC/TGS/TV (Argentine/regional FPI banks/telecoms/utilities filing
    ifrs-full "Assets" only under unit="ARS", never USD or any major currency).
    _aggregate_concepts already correctly skips a non-major-currency fact (no reliable FX
    rate to safely convert a hyperinflationary-currency filer - see
    _aggregate_concepts_currency_code's own docstring), but the resulting all-required-
    fields-NULL row then falls to the generic "incomplete_sec_filing_{type}" instead of the
    specific "unsupported_currency_no_fx_rate" reason (same "Missing SEC/XBRL data" category
    as its post_run()-path sibling fpi_currency_data_rejected - this doesn't change which
    category the row counts toward, just which real, specific cause it's attributed to) -
    same reason-string-doesn't-match-real-cause bug class as this sweep's other fixes, just
    undetectable from the DB alone since the currency a raw fact was tagged under isn't
    persisted anywhere once _aggregate_concepts discards it.

    Reuses client.get_company_facts()'s own per-CIK cache (already warmed by this same run's
    extraction call for this exact symbol), so this adds no extra HTTP cost on the only path
    that calls it (a required field this statement type already confirmed missing).
    """
    try:
        cik = client.symbol_to_cik(symbol)
        facts = client.get_company_facts(cik)
    except Exception:
        return False
    for taxonomy, concepts in (("us-gaap", us_gaap_concepts), ("ifrs-full", ifrs_concepts)):
        taxonomy_facts = facts.get("facts", {}).get(taxonomy, {})
        for concept in concepts:
            units = taxonomy_facts.get(concept, {}).get("units", {})
            has_allowed_currency_value = False
            has_rejected_currency_value = False
            for unit, entries in units.items():
                if not any(e.get("val") is not None for e in entries):
                    continue
                currency = _extract_currency_code(unit)
                if currency == "USD" or currency in MAJOR_CURRENCIES:
                    has_allowed_currency_value = True
                else:
                    has_rejected_currency_value = True
            if has_rejected_currency_value and not has_allowed_currency_value:
                return True
    return False

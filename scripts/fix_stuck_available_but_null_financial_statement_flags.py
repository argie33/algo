#!/usr/bin/env python3
"""One-time retroactive correction for financial-statement rows stuck
data_unavailable=FALSE/reason=NULL with every required field NULL.

BACKGROUND: load_financial_statements.py's post_run() (see its own 2026-09-02/09-03 fix
comments, ~line 1547) force-nulls a row's required field(s) when the run decides the
filer's value can't be trusted (FPI-currency rejection, an all-none annual row, a shared
ETF-trust CIK, ...), then syncs data_unavailable/reason to match. But that sync only
covers rows THIS run's own force-null loop actually touches - a row that got force-nulled
by an EARLIER run, before that 2026-09-02/09-03 fix existed, was left at whatever a prior
successful run had last written to data_unavailable/reason (almost always
FALSE/NULL, from when the row genuinely had real data) and never gets revisited unless
some LATER run happens to re-fetch and re-transform() that exact fiscal year. That's
strictly worse than being absent: `WHERE data_unavailable = FALSE` reads (the coverage
report, quality/growth/value metrics' reason-chain checks) silently treat the row as
real-but-null instead of correctly falling back to an "unavailable" classification.

Live-confirmed 2026-09-10 (goal: retroactive correction of this exact stuck population):
    annual_balance_sheet:       250 rows / 58 symbols
    annual_income_statement:     49 rows / 38 symbols
    annual_cash_flow:           133 rows / 47 symbols
    quarterly_balance_sheet:     35 rows / 26 symbols
    quarterly_income_statement:   5 rows /  3 symbols
    quarterly_cash_flow:          6 rows /  3 symbols

This script does NOT reimplement the loader's classification logic - it reuses the exact
same pieces load_financial_statements.py's own transform()/post_run() already use
(_UNSUPPORTED_CURRENCY_CHECK_CONCEPTS + has_unsupported_currency_only_fact,
SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS, _REQUIRED_STATEMENT_FIELDS), plus two additional
signals only available to a retroactive sweep looking across the whole DB rather than one
run's own fetch (company_info_sec.has_annual_report_filing, and a symbol_to_cik miss) -
see classify_stuck_symbol()'s docstring for the exact precedence and why each reason is
attributed the way it is. Every case defers to the SAME reason vocabulary the rest of the
codebase already uses (company_info_sec_reason_cleanup.py's "no_annual_report_filing"/
"registered_investment_company_no_annual_report", load_financial_statements.py's own
"cik_not_found"/"shared_issuer_or_trust_cik_not_attributable"/"unsupported_currency_no_fx_rate"/
"incomplete_sec_filing_{type}") - never a newly-invented string.

Classification only needs data already on disk (the on-disk SEC EDGAR companyfacts cache
under %TEMP%/algo-sec-edgar-cache/companyfacts, populated by normal loader runs, plus a
symbol_to_cik lookup that itself prefers the local ticker-cache file over any network
call) - it does not trigger a reload or any bulk SEC fetch. A per-symbol classification is
cached and reused across every row/table for that symbol, so the whole sweep costs at most
one companyfacts lookup per distinct stuck symbol (~95), not per row (~478).

Usage:
    python scripts/fix_stuck_available_but_null_financial_statement_flags.py --dry-run
    python scripts/fix_stuck_available_but_null_financial_statement_flags.py
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from loaders.load_financial_statements import (  # noqa: E402
    _REQUIRED_STATEMENT_FIELDS,
    _UNSUPPORTED_CURRENCY_CHECK_CONCEPTS,
    SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS,
)
from utils.db.context import DatabaseContext  # noqa: E402
from utils.external.sec_edgar_client import SecEdgarClient  # noqa: E402
from utils.external.sec_statements_shared import has_unsupported_currency_only_fact  # noqa: E402

# table -> statement_type (see _REQUIRED_STATEMENT_FIELDS/_UNSUPPORTED_CURRENCY_CHECK_CONCEPTS,
# both keyed by statement_type, not table/period - classification is the same for a symbol's
# annual and quarterly rows of the same statement type).
TABLE_STATEMENT_TYPES: dict[str, str] = {
    "annual_balance_sheet": "balance",
    "annual_income_statement": "income",
    "annual_cash_flow": "cashflow",
    "quarterly_balance_sheet": "balance",
    "quarterly_income_statement": "income",
    "quarterly_cash_flow": "cashflow",
}


def _stuck_where_clause(required_fields: set[str]) -> str:
    null_clause = " AND ".join(f"{f} IS NULL" for f in sorted(required_fields))
    return f"data_unavailable = FALSE AND reason IS NULL AND {null_clause}"


def find_stuck_symbols(table: str, statement_type: str, cur: Any) -> list[str]:
    required_fields = _REQUIRED_STATEMENT_FIELDS[statement_type]
    cur.execute(f"SELECT DISTINCT symbol FROM {table} WHERE {_stuck_where_clause(required_fields)}")
    return sorted(r[0] for r in cur.fetchall())


def load_company_info(symbols: list[str], cur: Any) -> dict[str, dict[str, Any]]:
    """Bulk-fetch the company_info_sec columns classify_stuck_symbol() needs, once for the
    whole sweep rather than per (symbol, table)."""
    if not symbols:
        return {}
    cur.execute(
        """
        SELECT symbol, is_foreign_private_issuer, entity_type, sic_code, has_annual_report_filing
        FROM company_info_sec WHERE symbol = ANY(%s)
        """,
        (symbols,),
    )
    out: dict[str, dict[str, Any]] = {}
    for symbol, is_fpi, entity_type, sic_code, has_annual in cur.fetchall():
        out[symbol] = {
            "is_foreign_private_issuer": bool(is_fpi),
            "entity_type": entity_type,
            "sic_code": sic_code,
            "has_annual_report_filing": has_annual,
        }
    return out


def classify_stuck_symbol(
    symbol: str,
    statement_type: str,
    client: SecEdgarClient,
    company_info: dict[str, dict[str, Any]],
) -> str:
    """Return the `reason` a current run's transform()/post_run() would have assigned this
    symbol's stuck row, had it revisited it - reusing the loader's own classification
    signals plus two DB-wide checks a single per-run fetch never had visibility into.

    Precedence (most specific/definitive first):
      1. SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS - same set load_financial_statements.py's own
         _reject_shared_etf_cik_data() uses; any data on file under this symbol's CIK is
         provably another ticker's financials, regardless of anything else.
      2. symbol_to_cik() fails - the same "cik_not_found" reason
         sec_base.py/load_company_info_sec.py/load_dividend_data.py/
         load_earnings_calendar_sec.py already use for an unresolvable ticker.
      3. company_info_sec.has_annual_report_filing is FALSE, or the CIK resolves but SEC
         has no companyfacts for it at all (a 404) - the entity is confirmed to have never
         filed a usable annual report. Reuses company_info_sec_reason_cleanup.py's own
         "no_annual_report_filing" convention (and its CEF-specific
         "registered_investment_company_no_annual_report" variant, same entity_type/sic_code
         signature that module already keys off) rather than inventing a new string for
         financial_statements tables.
      4. Foreign private issuer whose companyfacts show this statement's required
         concept(s) tagged ONLY under an unsupported (non-major, non-USD) currency -
         transform()'s own has_unsupported_currency_only_fact() check, verbatim.
      5. Otherwise: transform()'s own generic fallback, "incomplete_sec_filing_{type}".
    """
    if symbol in SHARED_ISSUER_OR_TRUST_CIK_SYMBOLS:
        return "shared_issuer_or_trust_cik_not_attributable"

    try:
        cik = client.symbol_to_cik(symbol)
    except Exception:
        return "cik_not_found"

    info = company_info.get(symbol)
    no_annual_report = False
    if info is not None and info["has_annual_report_filing"] is False:
        no_annual_report = True
    else:
        try:
            client.get_company_facts(cik)
        except FileNotFoundError:
            no_annual_report = True
        except Exception:
            pass  # transient/unknown - fall through to the generic reason, never mislabel
    if no_annual_report:
        if info is not None and info["entity_type"] in ("other", "investment") and info["sic_code"] is None:
            return "registered_investment_company_no_annual_report"
        return "no_annual_report_filing"

    if info is not None and info["is_foreign_private_issuer"]:
        us_gaap_concepts, ifrs_concepts = _UNSUPPORTED_CURRENCY_CHECK_CONCEPTS.get(statement_type, ([], []))
        if has_unsupported_currency_only_fact(client, symbol, us_gaap_concepts, ifrs_concepts):
            return "unsupported_currency_no_fx_rate"

    return f"incomplete_sec_filing_{statement_type}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run", action="store_true", help="Classify and print counts per (table, reason) without writing"
    )
    args = parser.parse_args()

    client = SecEdgarClient()
    classification_cache: dict[tuple[str, str], str] = {}
    total_updated = 0
    per_table_reason_counts: dict[str, Counter[str]] = {}

    for table, statement_type in TABLE_STATEMENT_TYPES.items():
        required_fields = _REQUIRED_STATEMENT_FIELDS[statement_type]
        with DatabaseContext("read") as cur:
            stuck_symbols = find_stuck_symbols(table, statement_type, cur)
            company_info = load_company_info(stuck_symbols, cur)

        reason_counts: Counter[str] = Counter()
        symbol_reasons: dict[str, str] = {}
        for symbol in stuck_symbols:
            cache_key = (symbol, statement_type)
            if cache_key not in classification_cache:
                classification_cache[cache_key] = classify_stuck_symbol(symbol, statement_type, client, company_info)
            reason = classification_cache[cache_key]
            symbol_reasons[symbol] = reason
            reason_counts[reason] += 1

        per_table_reason_counts[table] = reason_counts
        print(f"\n=== {table} ({len(stuck_symbols)} stuck symbols) ===")
        for reason, count in reason_counts.most_common():
            print(f"  {reason:<55} {count} symbol(s)")

        if args.dry_run or not stuck_symbols:
            continue

        with DatabaseContext("write") as cur:
            for symbol, reason in symbol_reasons.items():
                cur.execute(
                    f"""
                    UPDATE {table}
                       SET data_unavailable = TRUE,
                           reason = %s
                     WHERE symbol = %s
                       AND {_stuck_where_clause(required_fields)}
                    """,
                    (reason, symbol),
                )
                total_updated += cur.rowcount

    if args.dry_run:
        print("\n--dry-run: no rows were updated.")
    else:
        print(f"\nUpdated {total_updated} row(s) total across {len(TABLE_STATEMENT_TYPES)} tables.")


if __name__ == "__main__":
    main()

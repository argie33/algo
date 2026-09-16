#!/usr/bin/env python3
"""Plausibility gate for yfinance values before they are ever used to repair a divergence.

Added 2026-09-16 in direct response to the same-day corruption incident (see
scripts/DIVERGENCE_REPAIR_POSTMORTEM.md, Postmortem Rule 4): repair_*.py scripts blindly
copied xbrl_yfinance_line_item_report.yfinance_value into source tables, trusting yfinance
as ground truth. yfinance is a secondary, independently-parsed source used elsewhere in this
codebase purely as a divergence *detector* (scripts/xbrl_yfinance_crosscheck.py) - a WARN
means "two sources disagree," not "yfinance is right." This script is the missing plausibility
check that must run BEFORE any yfinance_value is proposed as a fix, so repair tooling can
never again apply an obviously-garbage number.

This does NOT decide which source is correct - that still requires root-causing each
divergence per Rule 2 of the postmortem. It only filters out yfinance values that are
implausible on their face and therefore must never be used as a repair candidate regardless
of root cause.

Checks applied per field family:
  - shares_outstanding (basic/diluted): flag if yfinance value <= 1,000 (no real filer has
    four-digit share counts; this was the exact pattern that produced GNLN=24, EDBL=25, CDT=24)
  - inherently-non-negative fields (revenue, total_assets, capex, depreciation_expense,
    shares_outstanding*): flag if yfinance value is negative or zero
  - any field: flag if yfinance value diverges from the symbol's own prior/next fiscal-year
    value (in OUR table, i.e. SEC-sourced) by more than 100x, UNLESS our own value also moves
    that much (a real business event, e.g. a split or divestiture, would show up on both sides)

Usage:
    python scripts/validate_yfinance_plausibility.py --audit-file /tmp/corruption_audit.json
    python scripts/validate_yfinance_plausibility.py --symbols GNLN,EDBL,CDT
    python scripts/validate_yfinance_plausibility.py --all-divergent --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.db import get_db_connection  # noqa: E402

NON_NEGATIVE_FIELD_SUBSTRINGS = (
    "shares_outstanding",
    "revenue",
    "total_assets",
    "capex",
    "capital_expenditures",
    "depreciation",
)

SHARES_MIN_PLAUSIBLE = 1000
CROSS_FIELD_RATIO_FLAG = 100


def _is_non_negative_field(field: str) -> bool:
    return any(s in field for s in NON_NEGATIVE_FIELD_SUBSTRINGS)


def _is_shares_field(field: str) -> bool:
    return "shares_outstanding" in field


def fetch_candidates(cursor, symbols=None):
    query = """
        SELECT symbol, our_table, our_field, fiscal_year, our_value, yfinance_value, ratio
        FROM xbrl_yfinance_line_item_report
        WHERE divergent = true
    """
    params = []
    if symbols:
        query += " AND symbol = ANY(%s)"
        params.append(symbols)
    query += " ORDER BY symbol, our_table, our_field, fiscal_year"
    cursor.execute(query, params)
    return cursor.fetchall()


def neighbor_years_our_value(cursor, table, field, symbol, fiscal_year):
    """Return this symbol's own (SEC-sourced) value in the adjacent fiscal years, for
    cross-field plausibility comparison."""
    query = f"""
        SELECT fiscal_year, {field}
        FROM {table}
        WHERE symbol = %s AND fiscal_year IN (%s, %s) AND {field} IS NOT NULL
    """
    cursor.execute(query, (symbol, fiscal_year - 1, fiscal_year + 1))
    return dict(cursor.fetchall())


def evaluate(cursor, symbol, table, field, fiscal_year, our_value, yfinance_value, ratio):
    """Return (verdict, reasons) where verdict is 'reject' or 'needs_review'."""
    reasons = []

    if yfinance_value is None:
        return "reject", ["yfinance_value is NULL"]

    yv = float(yfinance_value)

    if _is_shares_field(field) and yv <= SHARES_MIN_PLAUSIBLE:
        reasons.append(f"shares field with implausibly tiny yfinance value ({yv})")

    if _is_non_negative_field(field) and yv <= 0:
        reasons.append(f"inherently non-negative field with yfinance value <= 0 ({yv})")

    neighbors = neighbor_years_our_value(cursor, table, field, symbol, fiscal_year)
    for ny, nval in neighbors.items():
        if nval in (None, 0):
            continue
        cross_ratio = max(yv, float(nval)) / min(abs(yv), abs(float(nval))) if yv and nval else None
        if cross_ratio and cross_ratio > CROSS_FIELD_RATIO_FLAG:
            our_own_ratio = (
                max(float(our_value), float(nval)) / min(abs(float(our_value)), abs(float(nval)))
                if our_value and nval
                else None
            )
            if not our_own_ratio or our_own_ratio < CROSS_FIELD_RATIO_FLAG:
                reasons.append(
                    f"yfinance value diverges {cross_ratio:.0f}x from our own FY{ny} value "
                    f"({nval}) while our own FY{fiscal_year} value does not"
                )

    if reasons:
        return "reject", reasons
    return "needs_review", ["no automatic red flags - still requires root-cause review before use (Rule 2)"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", help="Comma-separated symbol list")
    parser.add_argument(
        "--audit-file", help="Path to a corruption-audit-style JSON file (list of {symbol,table,field,fiscal_year})"
    )
    parser.add_argument(
        "--all-divergent", action="store_true", help="Evaluate every divergent row in xbrl_yfinance_line_item_report"
    )
    parser.add_argument("--out", default=None, help="Write full results JSON to this path")
    args = parser.parse_args()

    if not (args.symbols or args.audit_file or args.all_divergent):
        parser.error("one of --symbols, --audit-file, --all-divergent is required")

    db = get_db_connection()
    cursor = db.cursor()

    if args.audit_file:
        with open(args.audit_file) as f:
            records = json.load(f)
        symbols = sorted({r["symbol"] for r in records})
        candidates = fetch_candidates(cursor, symbols=symbols)
        wanted = {(r["symbol"], r["table"], r["field"], r["fiscal_year"]) for r in records}
        candidates = [c for c in candidates if (c[0], c[1], c[2], c[3]) in wanted]
    else:
        symbols = args.symbols.split(",") if args.symbols else None
        candidates = fetch_candidates(cursor, symbols=symbols)

    results = []
    for symbol, table, field, fiscal_year, our_value, yfinance_value, ratio in candidates:
        verdict, reasons = evaluate(cursor, symbol, table, field, fiscal_year, our_value, yfinance_value, ratio)
        results.append(
            {
                "symbol": symbol,
                "table": table,
                "field": field,
                "fiscal_year": fiscal_year,
                "our_value": str(our_value),
                "yfinance_value": str(yfinance_value),
                "ratio": float(ratio) if ratio is not None else None,
                "verdict": verdict,
                "reasons": reasons,
            }
        )

    cursor.close()
    db.close()

    rejected = [r for r in results if r["verdict"] == "reject"]
    needs_review = [r for r in results if r["verdict"] == "needs_review"]

    print(f"Evaluated {len(results)} divergent candidates")
    print(f"  REJECT (never use yfinance value as-is): {len(rejected)}")
    print(f"  NEEDS_REVIEW (no auto red flag, still root-cause first): {len(needs_review)}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Full results written to {args.out}")


if __name__ == "__main__":
    main()

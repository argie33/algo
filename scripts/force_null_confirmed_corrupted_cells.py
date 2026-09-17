#!/usr/bin/env python3
"""Force-null a small, explicitly-curated list of confirmed-corrupted cells that a live
SEC XBRL reload could NOT refresh (closes the `preserve_on_missing_fields` gap documented
in scripts/DIVERGENCE_REPAIR_POSTMORTEM.md: a rejected/corrupted value for a historical
fiscal year that SEC's re-fetch doesn't return fresh data for stays stale forever, since
the normal loader path only ever COALESCEs a missing fresh value against whatever is
already stored).

This is deliberately NOT an automatic heuristic. There is no way for a loader run to
discover on its own that a stored value is corrupted rather than a legitimate, if
unusual, real figure - that determination requires independent verification against a
live source (SEC filing text, EDGAR full-text search, a cross-statement consistency
check, etc). Building an automatic "null anything not refreshed this run" sweep would
reintroduce exactly the blind-bulk-write failure mode that caused the original 2026-09-16
incident, just in the null direction instead of the copy-yfinance direction.

Input is a JSON list of objects, each requiring every one of:
    {"table": "annual_balance_sheet", "field": "long_term_debt",
     "symbol": "GNLN", "fiscal_year": 2022,
     "reason": "confirmed_corrupted_no_fresh_sec_data",
     "verified_by": "WebSearch of GNLN's actual 10-K, 2026-09-16 session"}

`reason` and `verified_by` are both required and must be non-empty - this script refuses
to silently accept a bare "trust me" JSON the way apply_verified_sec_fixes.py's design
flaw allowed (see [[divergence-repair-critical-incident]] memory: "still accepts a
hand-typed JSON of verified values on faith"). This script only ever writes NULL, never a
hand-typed replacement number, so there is no equivalent risk of writing a wrong figure -
but an unverified reason string is still worth refusing so this never becomes a rubber
stamp for an unreviewed bulk change.

Usage:
    python scripts/force_null_confirmed_corrupted_cells.py --input cells.json          # dry-run
    python scripts/force_null_confirmed_corrupted_cells.py --input cells.json --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.db import get_db_connection  # noqa: E402

ALLOWED_TABLES = {"annual_income_statement", "annual_balance_sheet", "annual_cash_flow"}


def _validate(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for i, e in enumerate(entries):
        missing = [k for k in ("table", "field", "symbol", "fiscal_year", "reason", "verified_by") if not e.get(k)]
        if missing:
            raise ValueError(f"entry {i} missing required field(s) {missing}: {e}")
        if e["table"] not in ALLOWED_TABLES:
            raise ValueError(f"entry {i}: table {e['table']!r} not in {ALLOWED_TABLES}")
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, help="JSON file of confirmed-corrupted cells to null")
    parser.add_argument("--apply", action="store_true", help="Actually write. Without this, only prints a preview.")
    args = parser.parse_args()

    entries = _validate(json.load(open(args.input, encoding="utf-8")))
    print(f"Loaded {len(entries)} confirmed-corrupted cell(s) from {args.input}")

    db = get_db_connection()
    cur = db.cursor()
    nulled = 0
    for e in entries:
        table, field, symbol, fy = e["table"], e["field"], e["symbol"], e["fiscal_year"]
        cur.execute(f"SELECT {field} FROM {table} WHERE symbol = %s AND fiscal_year = %s", (symbol, fy))
        row = cur.fetchone()
        current = row[0] if row else None
        print(
            f"  {table}.{field} {symbol} FY{fy}: current={current!r} -> NULL  ({e['reason']}, verified_by={e['verified_by']!r})"
        )
        if args.apply and row is not None and current is not None:
            cur.execute(
                f"UPDATE {table} SET {field} = NULL WHERE symbol = %s AND fiscal_year = %s AND {field} IS NOT NULL",
                (symbol, fy),
            )
            nulled += cur.rowcount

    if args.apply:
        db.commit()
        print(f"\nAPPLIED: force-nulled {nulled} cell(s).")
    else:
        print(f"\nDRY RUN: {len(entries)} cell(s) would be nulled. Re-run with --apply to write.")

    cur.close()
    db.close()


if __name__ == "__main__":
    main()

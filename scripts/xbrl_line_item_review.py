#!/usr/bin/env python3
"""Mark the human-review verdict on a specific xbrl_yfinance_line_item_report row (migration
1301). This is the ONLY sanctioned way to set review_status - scripts/xbrl_yfinance_crosscheck.py
never touches it itself, and there is deliberately no bulk/pattern-matching mode here: the
2026-09-16 corruption incident (scripts/DIVERGENCE_REPAIR_POSTMORTEM.md) happened precisely
because a script treated a whole class of rows (divergent=true) as "confirmed wrong" without
checking each one. Mark rows one at a time, after actually looking at that specific
(symbol, table, field, fiscal_year).

Usage:
    python scripts/xbrl_line_item_review.py AAPL annual_income_statement revenue 2024 \\
        --status reviewed_not_error --note "Restatement, both sides correct for their filing vintage"

    python scripts/xbrl_line_item_review.py RETO annual_balance_sheet long_term_debt 2025 \\
        --status reviewed_fixed --note "Was 189758 (matched yfinance's garbage value), corrected to SEC's 3165000"

    # Quarterly row (migration 1303 added fiscal_quarter/period_type - default 0 means annual):
    python scripts/xbrl_line_item_review.py AAPL quarterly_income_statement revenue 2025 \\
        --fiscal-quarter 2 --status reviewed_not_error --note "Fiscal-vs-calendar-quarter mismatch, not a bug"
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

_STATUSES = ("unreviewed", "reviewed_not_error", "reviewed_needs_fix", "reviewed_fixed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("symbol")
    parser.add_argument("table", help="our_table value, e.g. annual_income_statement")
    parser.add_argument("field", help="our_field value, e.g. revenue")
    parser.add_argument("fiscal_year", type=int)
    parser.add_argument(
        "--fiscal-quarter",
        type=int,
        default=0,
        choices=(0, 1, 2, 3, 4),
        help="0 (default) = annual row. 1-4 = quarterly row (migration 1303).",
    )
    parser.add_argument("--status", required=True, choices=_STATUSES)
    parser.add_argument("--note", default=None, help="Why - what you actually checked and found")
    parser.add_argument("--by", default=None, help="Reviewer identity (default: local username)")
    args = parser.parse_args()

    symbol = args.symbol.strip().upper()

    from utils.db.connection import get_db_connection

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT our_value, yfinance_value, ratio, divergent, review_status
        FROM xbrl_yfinance_line_item_report
        WHERE symbol = %s AND our_table = %s AND our_field = %s AND fiscal_year = %s AND fiscal_quarter = %s
        """,
        (symbol, args.table, args.field, args.fiscal_year, args.fiscal_quarter),
    )
    row = cur.fetchone()
    period = f"FY{args.fiscal_year}" if args.fiscal_quarter == 0 else f"FY{args.fiscal_year}Q{args.fiscal_quarter}"
    if row is None:
        checker = "xbrl_yfinance_crosscheck.py" if args.fiscal_quarter == 0 else "xbrl_yfinance_quarterly_crosscheck.py"
        print(
            f"No recorded comparison for {symbol} {args.table}.{args.field} {period} - "
            f"has scripts/{checker} ever checked this symbol? "
            f"(python scripts/xbrl_line_item_report.py --symbol {symbol})"
        )
        cur.close()
        conn.close()
        sys.exit(1)

    ours, yf, ratio, divergent, prior_status = row
    print(
        f"{symbol} {args.table}.{args.field} {period}: "
        f"ours={ours} yfinance={yf} ratio={ratio} divergent={divergent} "
        f"(currently review_status={prior_status})"
    )

    cur.execute(
        """
        UPDATE xbrl_yfinance_line_item_report
        SET review_status = %s, review_note = %s, reviewed_at = CURRENT_TIMESTAMP, reviewed_by = %s
        WHERE symbol = %s AND our_table = %s AND our_field = %s AND fiscal_year = %s AND fiscal_quarter = %s
        """,
        (
            args.status,
            args.note,
            args.by or getpass.getuser(),
            symbol,
            args.table,
            args.field,
            args.fiscal_year,
            args.fiscal_quarter,
        ),
    )
    conn.commit()
    print(f"-> review_status set to {args.status}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

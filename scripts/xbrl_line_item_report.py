#!/usr/bin/env python3
"""Read-side report for xbrl_yfinance_line_item_report (migration 1300): the accumulated,
per-symbol/per-field/per-fiscal-year matrix scripts/xbrl_yfinance_crosscheck.py builds up over
many runs. Answers "where exactly do we still have a data issue" directly from the DB instead
of digging through data_patrol_log's capped JSONB examples.

Usage:
    python scripts/xbrl_line_item_report.py                 # coverage + per-field divergence summary
    python scripts/xbrl_line_item_report.py --symbol AAPL   # full line-item breakdown for one symbol
    python scripts/xbrl_line_item_report.py --divergent-only --limit 50   # worst offenders across all fields
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _universe_size(cur: Any) -> int:
    cur.execute(
        """
        SELECT COUNT(DISTINCT ais.symbol)
        FROM annual_income_statement ais
        JOIN stock_symbols s ON s.symbol = ais.symbol AND s.active = true
        WHERE ais.data_source = 'sec_audited' AND ais.data_unavailable = FALSE
        """
    )
    return int(cur.fetchone()[0])


def _print_coverage(cur: Any) -> None:
    universe = _universe_size(cur)
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM xbrl_yfinance_line_item_report")
    checked = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM xbrl_yfinance_line_item_report")
    total_rows = cur.fetchone()[0]
    print("=== Coverage ===")
    pct = (checked / universe * 100.0) if universe else 0.0
    print(f"Symbols with at least one recorded comparison: {checked}/{universe} ({pct:.1f}%)")
    print(f"Total (symbol, field, fiscal_year/quarter) comparisons on record: {total_rows}")
    # id=1 is the annual sweep cursor, id=2 the quarterly one (migration 1303/1304 -
    # scripts/xbrl_yfinance_quarterly_crosscheck.py) - print both rather than assuming id=1.
    cur.execute(
        "SELECT id, last_symbol, updated_at FROM xbrl_yfinance_crosscheck_progress WHERE id IN (1, 2) ORDER BY id"
    )
    cursor_rows = {r[0]: r for r in cur.fetchall()}
    for cid, label in ((1, "annual"), (2, "quarterly")):
        row = cursor_rows.get(cid)
        if row and row[1]:
            print(f"Sweep cursor ({label}): last symbol checked = {row[1]} (updated {row[2]})")
        else:
            print(f"Sweep cursor ({label}): not yet initialized (no --sweep run yet)")
    print()

    # review_status (migration 1302): divergent alone doesn't say whether anyone has confirmed
    # which side is actually wrong - see scripts/DIVERGENCE_REPAIR_POSTMORTEM.md for why that
    # distinction matters. This is the honest three-way split: confident (not divergent),
    # flagged-but-unreviewed, and the review outcomes for whatever HAS been looked at.
    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE NOT divergent) AS confident,
            COUNT(*) FILTER (WHERE divergent AND review_status = 'unreviewed') AS unreviewed,
            COUNT(*) FILTER (WHERE divergent AND review_status = 'reviewed_not_error') AS not_error,
            COUNT(*) FILTER (WHERE divergent AND review_status = 'reviewed_needs_fix') AS needs_fix,
            COUNT(*) FILTER (WHERE divergent AND review_status = 'reviewed_fixed') AS fixed
        FROM xbrl_yfinance_line_item_report
        """
    )
    confident, unreviewed, not_error, needs_fix, fixed = cur.fetchone()
    print("=== Confidence breakdown ===")
    print(f"Confident (matches yfinance):        {confident}")
    print(f"Flagged, not yet reviewed:            {unreviewed}")
    print(f"Reviewed - legitimate difference:     {not_error}")
    print(f"Reviewed - confirmed wrong, open:     {needs_fix}")
    print(f"Reviewed - confirmed wrong, fixed:    {fixed}")
    print()


def _print_field_summary(cur: Any) -> None:
    cur.execute(
        """
        SELECT our_table, our_field,
               COUNT(*) AS n,
               COUNT(*) FILTER (WHERE divergent) AS n_divergent
        FROM xbrl_yfinance_line_item_report
        GROUP BY our_table, our_field
        ORDER BY n_divergent DESC, our_table, our_field
        """
    )
    rows = cur.fetchall()
    if not rows:
        print("No comparisons recorded yet - run scripts/xbrl_yfinance_crosscheck.py first.")
        return
    print("=== Per-field divergence rate ===")
    print(f"{'table':<28} {'field':<45} {'n':>6} {'divergent':>10} {'rate':>7}")
    for table, field, n, n_div in rows:
        rate = (n_div / n * 100.0) if n else 0.0
        print(f"{table:<28} {field:<45} {n:>6} {n_div:>10} {rate:>6.1f}%")
    print()


def _print_symbol_detail(cur: Any, symbol: str) -> None:
    cur.execute(
        """
        SELECT our_table, our_field, fiscal_year, fiscal_quarter, our_value, yfinance_value, ratio, divergent,
               review_status, checked_at
        FROM xbrl_yfinance_line_item_report
        WHERE symbol = %s
        ORDER BY divergent DESC, our_table, our_field, fiscal_year DESC, fiscal_quarter DESC
        """,
        (symbol,),
    )
    rows = cur.fetchall()
    if not rows:
        print(f"No recorded comparisons for {symbol} yet.")
        return
    print(f"=== Line-item detail for {symbol} ===")
    for table, field, fy, fq, ours, yf, ratio, divergent, review_status, checked_at in rows:
        flag = "DIVERGENT" if divergent else "ok"
        review = f" [{review_status}]" if divergent else ""
        period = f"FY{fy}" if fq == 0 else f"FY{fy}Q{fq}"
        print(
            f"[{flag:>9}] {table}.{field} {period}: ours={ours} yfinance={yf} ratio={ratio:.3f}"
            f"{review} (checked {checked_at})"
        )
    print()


def _print_worst_offenders(cur: Any, limit: int, unreviewed_only: bool) -> None:
    cur.execute(
        f"""
        SELECT symbol, our_table, our_field, fiscal_year, fiscal_quarter, our_value, yfinance_value, ratio,
               review_status, checked_at
        FROM xbrl_yfinance_line_item_report
        WHERE divergent {"AND review_status = 'unreviewed'" if unreviewed_only else ""}
        ORDER BY GREATEST(ratio, 1.0 / NULLIF(ratio, 0)) DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cur.fetchall()
    if not rows:
        print("No divergent line items recorded.")
        return
    label = "unreviewed divergent" if unreviewed_only else "divergent"
    print(f"=== Top {len(rows)} {label} line items (by ratio distance from 1.0) ===")
    for symbol, table, field, fy, fq, ours, yf, ratio, review_status, checked_at in rows:
        period = f"FY{fy}" if fq == 0 else f"FY{fy}Q{fq}"
        print(
            f"{symbol:<8} {table}.{field} {period}: ours={ours} yfinance={yf} ratio={ratio:.3f} "
            f"[{review_status}] (checked {checked_at})"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", help="Show full line-item detail for one symbol instead of the summary")
    parser.add_argument(
        "--divergent-only", action="store_true", help="Show the worst divergent line items across the whole universe"
    )
    parser.add_argument("--limit", type=int, default=50, help="Row limit for --divergent-only (default 50)")
    parser.add_argument(
        "--unreviewed-only",
        action="store_true",
        help="With --divergent-only, exclude rows someone has already reviewed (any review_status)",
    )
    args = parser.parse_args()

    from utils.db.connection import get_db_connection

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor()

    if args.symbol:
        _print_symbol_detail(cur, args.symbol.strip().upper())
    elif args.divergent_only:
        _print_worst_offenders(cur, args.limit, args.unreviewed_only)
    else:
        _print_coverage(cur)
        _print_field_summary(cur)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

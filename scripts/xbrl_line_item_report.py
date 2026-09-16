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
    cur.execute("SELECT last_symbol, updated_at FROM xbrl_yfinance_crosscheck_progress WHERE id = 1")
    row = cur.fetchone()
    print("=== Coverage ===")
    pct = (checked / universe * 100.0) if universe else 0.0
    print(f"Symbols with at least one recorded comparison: {checked}/{universe} ({pct:.1f}%)")
    print(f"Total (symbol, field, fiscal_year) comparisons on record: {total_rows}")
    if row and row[0]:
        print(f"Sweep cursor: last symbol checked = {row[0]} (updated {row[1]})")
    else:
        print("Sweep cursor: not yet initialized (no --sweep run yet)")
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
        SELECT our_table, our_field, fiscal_year, our_value, yfinance_value, ratio, divergent, checked_at
        FROM xbrl_yfinance_line_item_report
        WHERE symbol = %s
        ORDER BY divergent DESC, our_table, our_field, fiscal_year DESC
        """,
        (symbol,),
    )
    rows = cur.fetchall()
    if not rows:
        print(f"No recorded comparisons for {symbol} yet.")
        return
    print(f"=== Line-item detail for {symbol} ===")
    for table, field, fy, ours, yf, ratio, divergent, checked_at in rows:
        flag = "DIVERGENT" if divergent else "ok"
        print(f"[{flag:>9}] {table}.{field} FY{fy}: ours={ours} yfinance={yf} ratio={ratio:.3f} (checked {checked_at})")
    print()


def _print_worst_offenders(cur: Any, limit: int) -> None:
    cur.execute(
        """
        SELECT symbol, our_table, our_field, fiscal_year, our_value, yfinance_value, ratio, checked_at
        FROM xbrl_yfinance_line_item_report
        WHERE divergent
        ORDER BY GREATEST(ratio, 1.0 / NULLIF(ratio, 0)) DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cur.fetchall()
    if not rows:
        print("No divergent line items recorded.")
        return
    print(f"=== Top {len(rows)} divergent line items (by ratio distance from 1.0) ===")
    for symbol, table, field, fy, ours, yf, ratio, checked_at in rows:
        print(f"{symbol:<8} {table}.{field} FY{fy}: ours={ours} yfinance={yf} ratio={ratio:.3f} (checked {checked_at})")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", help="Show full line-item detail for one symbol instead of the summary")
    parser.add_argument(
        "--divergent-only", action="store_true", help="Show the worst divergent line items across the whole universe"
    )
    parser.add_argument("--limit", type=int, default=50, help="Row limit for --divergent-only (default 50)")
    args = parser.parse_args()

    from utils.db.connection import get_db_connection

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor()

    if args.symbol:
        _print_symbol_detail(cur, args.symbol.strip().upper())
    elif args.divergent_only:
        _print_worst_offenders(cur, args.limit)
    else:
        _print_coverage(cur)
        _print_field_summary(cur)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

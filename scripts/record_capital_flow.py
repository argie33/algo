#!/usr/bin/env python3
"""Record an external capital flow (deposit or withdrawal) into algo_capital_flows.

Any real money moved into or out of the trading account MUST be recorded here.
The drawdown circuit breaker (algo/risk/circuit_breaker.py::_check_drawdown) compares
cash-flow-adjusted equity against its adjusted peak so that deposits/withdrawals are not
misread as trading gains/losses. An unrecorded flow will show up as a false swing in
that metric exactly like the incident documented in migrations/versions/1134_add_capital_flow_adjusted_drawdown.sql.

Usage:
    python scripts/record_capital_flow.py --date 2026-07-20 --amount -5000 --type withdrawal --notes "Personal withdrawal"
    python scripts/record_capital_flow.py --date 2026-07-20 --amount 10000 --type deposit --notes "Added capital"
"""

import argparse
import sys
from datetime import date

from utils.db import DatabaseContext


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", required=True, help="Flow date, YYYY-MM-DD")
    parser.add_argument(
        "--amount",
        required=True,
        type=float,
        help="Signed dollar amount: positive = deposit, negative = withdrawal. Must match --type's sign.",
    )
    parser.add_argument("--type", required=True, choices=["deposit", "withdrawal"], dest="flow_type")
    parser.add_argument("--notes", default="", help="Free-text context for the audit trail")
    args = parser.parse_args()

    try:
        flow_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"ERROR: --date must be YYYY-MM-DD, got {args.date!r}", file=sys.stderr)
        return 1

    if args.flow_type == "deposit" and args.amount <= 0:
        print("ERROR: deposits must have a positive --amount", file=sys.stderr)
        return 1
    if args.flow_type == "withdrawal" and args.amount >= 0:
        print("ERROR: withdrawals must have a negative --amount", file=sys.stderr)
        return 1

    with DatabaseContext("write") as cur:
        cur.execute(
            """
            INSERT INTO algo_capital_flows (flow_date, amount, flow_type, source, notes)
            VALUES (%s, %s, %s, 'manual', %s)
            """,
            (flow_date, args.amount, args.flow_type, args.notes),
        )
        # Recompute adjusted_equity/adjusted_running_peak/adjusted_drawdown_pct for every
        # snapshot from this flow's date onward - the same formula as migration 1134's backfill.
        cur.execute(
            """
            WITH flow_cum AS (
                SELECT
                    s.id, s.snapshot_date, s.total_portfolio_value,
                    COALESCE((SELECT SUM(f.amount) FROM algo_capital_flows f WHERE f.flow_date <= s.snapshot_date), 0) AS cum_flow
                FROM algo_portfolio_snapshots s
                WHERE s.total_portfolio_value > 0
            ),
            adj AS (
                SELECT
                    id, snapshot_date, cum_flow,
                    (total_portfolio_value - cum_flow) AS adjusted_equity,
                    MAX(total_portfolio_value - cum_flow) OVER (
                        ORDER BY snapshot_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS adjusted_peak
                FROM flow_cum
            )
            UPDATE algo_portfolio_snapshots s
            SET
                net_capital_flow_cum = a.cum_flow,
                adjusted_equity = a.adjusted_equity,
                adjusted_running_peak = a.adjusted_peak,
                adjusted_drawdown_pct = CASE
                    WHEN a.adjusted_peak > 0 THEN ((a.adjusted_peak - a.adjusted_equity) / a.adjusted_peak * 100)::DECIMAL(8, 4)
                    ELSE 0
                END
            FROM adj a
            WHERE s.id = a.id AND s.snapshot_date >= %s
            """,
            (flow_date,),
        )
        print(f"Recorded {args.flow_type} of ${args.amount:,.2f} on {flow_date}, recomputed adjusted drawdown series.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

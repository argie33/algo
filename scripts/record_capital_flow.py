#!/usr/bin/env python3
"""Record an external capital flow (deposit or withdrawal) and recompute the
cash-flow-adjusted drawdown series the circuit breaker depends on.

BUILT 2026-08-10: this script was referenced by name in comments across
algo/risk/circuit_breaker.py, algo/infrastructure/reconciliation.py, and
algo/trading/position_sizer.py ("record every capital flow in algo_capital_flows via
scripts/record_capital_flow.py or it will misreport here") but was never actually built -
migration 1134 created the algo_capital_flows table and the adjusted_equity/
adjusted_running_peak/adjusted_drawdown_pct columns it feeds, and backfilled 3 historical
withdrawals with a one-off SQL UPDATE, but left no supported tool for recording the NEXT
one. Without this, the first real deposit/withdrawal after that backfill has no correct way
to be recorded - a raw INSERT into algo_capital_flows alone is not enough, since
adjusted_equity/adjusted_running_peak/adjusted_drawdown_pct on algo_portfolio_snapshots are
a cumulative-sum-based derived series that must be recomputed for every affected snapshot,
not just appended to.

Per migration 1134's own root-cause story: an unrecorded capital flow makes the drawdown
circuit breaker misinterpret account-size changes as trading performance - a withdrawal can
trigger a false halt (real incident: 8+ months of permanent halt deadlock from exactly this),
and a deposit can equally mask a genuine drawdown by inflating current equity. This script
closes that gap before real money makes the omission consequential.

Usage:
    python scripts/record_capital_flow.py --amount -5000 --date 2026-08-10 --notes "Withdrawal to bank account"
    python scripts/record_capital_flow.py --amount 10000 --date 2026-08-10 --notes "Initial funding"
    python scripts/record_capital_flow.py --list

Sign convention (single source of truth - avoids the redundant amount/flow_type
inconsistency the underlying table's own CHECK constraint allows but doesn't prevent):
    positive --amount = deposit (inflow)
    negative --amount = withdrawal (outflow)
flow_type is derived from the sign, never taken as separate operator input.
"""

import argparse
import sys
from datetime import date as _date
from datetime import datetime
from decimal import Decimal, InvalidOperation

from utils.db import DatabaseContext


def _parse_date(value: str) -> _date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date {value!r}, expected YYYY-MM-DD") from None


def record_flow(flow_date: _date, amount: Decimal, source: str, notes: str | None) -> int:
    """Insert the flow and recompute the adjusted equity series. Returns the new row's id.

    Recompute logic mirrors migration 1134's own backfill UPDATE exactly (cumulative SUM of
    algo_capital_flows.amount up to each snapshot_date, then MAX() as a running peak) so this
    script's output is guaranteed consistent with how the original 3 historical flows were
    applied - not a reimplementation that could silently drift from that logic over time.
    """
    if amount == 0:
        raise ValueError("amount must be non-zero (a zero-dollar flow is not a real capital movement)")

    flow_type = "deposit" if amount > 0 else "withdrawal"

    with DatabaseContext("write") as cur:
        cur.execute(
            """
            INSERT INTO algo_capital_flows (flow_date, amount, flow_type, source, notes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (flow_date, amount, flow_type, source, notes),
        )
        new_id = cur.fetchone()[0]

        # Recompute the full adjusted series - same query shape as migration 1134's backfill.
        # Table is one row per trading day; a full recompute is cheap and guarantees
        # correctness (no risk of an incremental-update path drifting from this source of
        # truth over repeated runs).
        cur.execute(
            """
            WITH flow_cum AS (
                SELECT
                    s.id,
                    s.snapshot_date,
                    s.total_portfolio_value,
                    COALESCE((
                        SELECT SUM(f.amount) FROM algo_capital_flows f WHERE f.flow_date <= s.snapshot_date
                    ), 0) AS cum_flow
                FROM algo_portfolio_snapshots s
                WHERE s.total_portfolio_value > 0
            ),
            adj AS (
                SELECT
                    id,
                    snapshot_date,
                    cum_flow,
                    (total_portfolio_value - cum_flow) AS adjusted_equity,
                    MAX(total_portfolio_value - cum_flow) OVER (
                        ORDER BY snapshot_date
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
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
            WHERE s.id = a.id
            """
        )
        affected = cur.rowcount

    print(f"Recorded {flow_type} of ${abs(amount):,.2f} on {flow_date} (id={new_id}, source={source!r}).")
    print(
        f"Recomputed adjusted_equity/adjusted_running_peak/adjusted_drawdown_pct for {affected} portfolio snapshot(s)."
    )
    return int(new_id)


def list_flows() -> None:
    with DatabaseContext("read") as cur:
        cur.execute(
            "SELECT id, flow_date, amount, flow_type, source, notes, created_at "
            "FROM algo_capital_flows ORDER BY flow_date, id"
        )
        rows = cur.fetchall()
    if not rows:
        print("No capital flows recorded.")
        return
    print(f"{'id':>4}  {'date':<10}  {'amount':>14}  {'type':<10}  {'source':<28}  notes")
    for row_id, flow_date, amount, flow_type, source, notes, _created_at in rows:
        print(f"{row_id:>4}  {flow_date}  {amount:>14,.2f}  {flow_type:<10}  {source:<28}  {notes or ''}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record a capital flow (deposit/withdrawal) and recompute adjusted drawdown series",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--amount",
        type=str,
        help="Signed dollar amount: positive = deposit, negative = withdrawal (e.g. -5000 or 10000)",
    )
    group.add_argument("--list", action="store_true", help="List all recorded capital flows")
    parser.add_argument(
        "--date", type=_parse_date, default=_date.today(), help="Flow date, YYYY-MM-DD (default: today)"
    )
    parser.add_argument("--source", type=str, default="manual", help="Source tag (default: manual)")
    parser.add_argument("--notes", type=str, default=None, help="Free-text description (recommended)")
    args = parser.parse_args()

    if args.list:
        list_flows()
        return 0

    try:
        amount = Decimal(args.amount)
    except InvalidOperation:
        print(f"ERROR: --amount {args.amount!r} is not a valid number.", file=sys.stderr)
        return 1

    if args.date > _date.today():
        print(
            f"ERROR: --date {args.date} is in the future. Capital flows must be dated on or before today.",
            file=sys.stderr,
        )
        return 1

    try:
        record_flow(args.date, amount, args.source, args.notes)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: Failed to record capital flow: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

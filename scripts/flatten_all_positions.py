#!/usr/bin/env python3
"""Emergency flatten-all: close every open position immediately.

BUILT 2026-08-24 (real-money-readiness /goal session, operational-readiness audit
follow-up - see memory/pre_live_money_operational_audit_20260824.md, finding #4).
scripts/manage_halt_flag.py can stop NEW entries (Phase 7/8 gates check the halt flag),
but nothing in this codebase could close EXISTING open positions on operator demand - a
halt alone leaves every open position's broker-side bracket running untouched. That's the
right default for a routine halt (those bracket legs are the position's own protection),
but it is NOT what an operator needs in a "something is badly wrong, get me flat right
now" scenario, which has no dedicated tool until this script.

Deliberately reuses the exact same exit path every other real exit in this system goes
through - TradeExecutor.exit_trade() -> ExitHandler.execute_exit() - rather than a
bespoke Alpaca bulk-close call, so a flatten gets the identical transaction safety,
bracket cancellation, and audit logging as any other exit (target hit, stop hit, time
exit, health-flag exit). No new order-submission logic was written for this - the exit
path itself already went through many sessions of adversarial fuzz-testing
(NaN/Infinity/magnitude-ceiling bugs, partial-exit bracket-resize bugs, trailing-stop
broker-sync gaps) and duplicating it here would just reopen all of that surface.

This is a genuinely destructive, hard-to-reverse operator action (real market/limit sell
orders against every open position) - it requires --confirm and a --reason, and always
sets the halt flag first so nothing tries to re-enter while positions are being closed.

Usage:
    python scripts/flatten_all_positions.py --status
    python scripts/flatten_all_positions.py --confirm --reason "runaway bug in signal generation"
"""

import argparse
import logging
import sys

from algo.infrastructure.config import AlgoConfig
from algo.orchestration.halt_flag_manager import HaltFlagManager
from algo.reporting import AlertManager
from algo.trading.executor import TradeExecutor
from algo.trading.quote_fetcher import fetch_live_quote
from utils.db import DatabaseContext
from utils.trading import TradeStatus

logger = logging.getLogger(__name__)


def _noop_log_phase_result(*args: object, **kwargs: object) -> None:
    pass


def _fetch_open_trades() -> list[tuple[int, str]]:
    """(trade_id, symbol) for every non-terminal trade - same status set exit_engine.py's
    own core exit-candidate query uses (TradeStatus.all_open()), so this sees exactly the
    same positions the normal automated exit path would eventually act on.
    """
    open_statuses = TradeStatus.all_open()
    placeholders = ", ".join(["%s"] * len(open_statuses))
    with DatabaseContext("read") as cur:
        cur.execute(
            f"SELECT trade_id, symbol FROM algo_trades WHERE status IN ({placeholders}) ORDER BY trade_date ASC",
            open_statuses,
        )
        return [(row[0], row[1]) for row in cur.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Emergency: close every open position immediately")
    parser.add_argument("--status", action="store_true", help="List open positions without closing anything")
    parser.add_argument("--confirm", action="store_true", help="Actually close every open position (destructive)")
    parser.add_argument("--reason", metavar="REASON", help="Required with --confirm - why this flatten is happening")
    args = parser.parse_args()

    if not args.status and not args.confirm:
        parser.error('Specify --status (safe, read-only) or --confirm --reason "..." (closes every position)')
    if args.confirm and not args.reason:
        parser.error("--confirm requires --reason - this is a destructive action, always record why")

    open_trades = _fetch_open_trades()

    if args.status:
        print(f"Open positions: {len(open_trades)}")
        for trade_id, symbol in open_trades:
            print(f"  trade_id={trade_id} symbol={symbol}")
        return 0

    if not open_trades:
        print("No open positions - nothing to flatten.")
        return 0

    print(f"FLATTENING {len(open_trades)} open position(s). Reason: {args.reason}")

    halt_manager = HaltFlagManager(AlertManager(), _noop_log_phase_result)
    halt_result = halt_manager.set_halt_flag(
        f"EMERGENCY FLATTEN: {args.reason}", triggered_by="manual_operator", force=True
    )
    if not halt_result:
        print(
            "ERROR: Failed to set halt flag before flattening (both DynamoDB and RDS unavailable). "
            "Refusing to flatten without the halt in place - new entries could race with these exits.",
            file=sys.stderr,
        )
        return 1
    print("Halt flag set - no new entries will be opened while flattening.")

    config = AlgoConfig()
    executor = TradeExecutor(config)
    execution_mode = str(config["execution_mode"]).lower()

    closed: list[str] = []
    failed: list[tuple[str, str]] = []

    for trade_id, symbol in open_trades:
        try:
            quote = fetch_live_quote(symbol, execution_mode, log_prefix="FLATTEN_ALL")
        except Exception as e:
            failed.append((symbol, f"quote fetch failed: {type(e).__name__}: {e}"))
            continue
        if isinstance(quote, dict):
            failed.append((symbol, f"quote unavailable: {quote.get('reason', quote)}"))
            continue

        result = executor.exit_trade(
            trade_id=trade_id,
            exit_price=quote,
            exit_reason=f"MANUAL_EMERGENCY_FLATTEN: {args.reason}",
            exit_fraction=1.0,
        )
        if result.get("success"):
            closed.append(symbol)
            print(f"  CLOSED {symbol} (trade_id={trade_id}) @ ${quote:.2f}")
        else:
            failed.append((symbol, str(result.get("message"))))
            print(f"  FAILED {symbol} (trade_id={trade_id}): {result.get('message')}")

    print(f"\nFlatten complete: {len(closed)} closed, {len(failed)} failed.")
    if failed:
        print("STILL OPEN - needs manual attention:", file=sys.stderr)
        for symbol, message in failed:
            print(f"  {symbol}: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

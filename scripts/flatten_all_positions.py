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
from typing import Any

import requests

from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter
from algo.infrastructure.config import AlgoConfig
from algo.orchestration.halt_flag_manager import HaltFlagManager
from algo.reporting import AlertManager, notify
from algo.trading.exceptions import NotificationError
from algo.trading.executor import TradeExecutor
from algo.trading.quote_fetcher import fetch_live_quote
from utils.db import DatabaseContext
from utils.trading import TradeStatus

logger = logging.getLogger(__name__)


def _noop_log_phase_result(*args: object, **kwargs: object) -> None:
    pass


def _fetch_open_trades() -> list[tuple[int, str, str, str]]:
    """(trade_id, symbol, status, alpaca_order_id) for every non-terminal trade - same
    status set exit_engine.py's own core exit-candidate query uses (TradeStatus.all_open()),
    so this sees exactly the same positions the normal automated exit path would eventually
    act on. alpaca_order_id is needed to cancel a still-unfilled entry order by its own order
    id rather than by symbol - see the unfilled_trades loop in main() for why.
    """
    open_statuses = TradeStatus.all_open()
    placeholders = ", ".join(["%s"] * len(open_statuses))
    with DatabaseContext("read") as cur:
        cur.execute(
            f"SELECT trade_id, symbol, status, alpaca_order_id FROM algo_trades "
            f"WHERE status IN ({placeholders}) ORDER BY trade_date ASC",
            open_statuses,
        )
        return [(row[0], row[1], row[2], row[3]) for row in cur.fetchall()]


def _fetch_broker_positions(config: AlgoConfig) -> list[dict[str, Any]]:
    """Every open position Alpaca reports right now - the one ground-truth seam both the
    start-of-run divergence check and the end-of-run post-flatten verification call through,
    so both get the same real /v2/positions data and both are equally easy to mock in tests.
    """
    return AlpacaBrokerAdapter(config).fetch_positions()


def _fetch_broker_only_symbols(config: AlgoConfig, db_tracked_symbols: set[str]) -> list[tuple[str, float]]:
    """(symbol, qty) for every broker position NOT covered by open_trades.

    REAL-MONEY-READINESS FIX (2026-09-07 audit): this script used to decide "nothing to
    flatten" purely from algo_trades - exactly the wrong source of truth for an emergency
    flatten, whose whole reason for existing is "something is badly wrong" (which very much
    includes "the DB and the broker have diverged"). circuit_breaker.py's own orphan-cleanup
    path can delete an algo_positions row for an open/null-stop/no-trade_ids position before
    this script ever sees it, and any other DB/broker desync (crash mid-entry before the
    trade row commits, a manual broker-side action, a sync bug) has the same effect: a real
    broker position that this script would otherwise report as "0 positions, nothing to
    flatten" while it sits fully exposed. Always cross-check against Alpaca's own
    /v2/positions directly - the actual ground truth - not just internal bookkeeping.
    """
    positions = _fetch_broker_positions(config)
    return [(p["symbol"], p["qty"]) for p in positions if p["symbol"] not in db_tracked_symbols and p["qty"] != 0]


def _close_untracked_broker_position(executor: TradeExecutor, symbol: str, reason: str) -> dict[str, object]:
    """Full close via Alpaca's DELETE /v2/positions/{symbol} (no qty = close entirely).

    Used only for positions the DB has no record of at all - there is no trade_id to route
    through the normal exit_trade() path, so this goes straight to the broker's own
    close-position endpoint (the same one order_manager.py's _try_close_position_fallback
    already uses elsewhere in this codebase for the qty-restricted partial case).
    """
    om = executor.order_manager
    try:
        resp = requests.delete(
            f"{om.alpaca_base_url}/v2/positions/{symbol}",
            headers={"APCA-API-KEY-ID": om.alpaca_key, "APCA-API-SECRET-KEY": om.alpaca_secret},
            timeout=30,
        )
    except requests.RequestException as e:
        return {"success": False, "message": f"close-position request failed: {type(e).__name__}: {e}"}
    if resp.status_code not in (200, 201):
        return {"success": False, "message": f"close-position endpoint returned {resp.status_code}: {resp.text[:500]}"}
    logger.info(f"[FLATTEN_ALL] {symbol}: untracked broker position closed ({reason})")
    return {"success": True, "message": f"Closed via broker close-position endpoint (order {resp.json().get('id')})"}


def _flatten_untracked_broker_positions(
    executor: TradeExecutor, broker_only: list[tuple[str, float]], reason: str
) -> tuple[list[str], list[tuple[str, str]]]:
    closed: list[str] = []
    failed: list[tuple[str, str]] = []
    for symbol, qty in broker_only:
        result = _close_untracked_broker_position(
            executor, symbol, reason=f"MANUAL_EMERGENCY_FLATTEN_UNTRACKED: {reason}"
        )
        if result.get("success"):
            closed.append(symbol)
            print(f"  CLOSED untracked broker position {symbol} (qty={qty}): {result.get('message')}")
        else:
            failed.append((symbol, str(result.get("message"))))
            print(f"  FAILED to close untracked broker position {symbol} (qty={qty}): {result.get('message')}")
    return closed, failed


def _cancel_unfilled_trades(
    executor: TradeExecutor, unfilled_trades: list[tuple[int, str, str]], reason: str
) -> tuple[list[str], list[tuple[str, str]]]:
    """Cancel each still-unfilled entry by its own alpaca_order_id.

    REAL-MONEY-READINESS FIX (2026-09-10 /goal pre-live-money audit): this used to call
    cancel_all_open_orders_for_symbol(symbol), which - per its own docstring - is only
    safe when the position is confirmed CLOSED. Pyramiding means an already-FILLED
    position's live protective stop-loss/take-profit can rest at the broker for the same
    symbol as this still-unfilled entry; cancelling by symbol here would strip that
    already-filled leg's stop during an emergency flatten, exactly when the system is
    trying to get safer, not less safe (order_manager_stop_repair.py's
    cancel_pending_entry_order fixed this same bug class on the halt path 2026-09-07 -
    this script never got the equivalent fix). Cancel by this trade's own alpaca_order_id
    instead, and handle the fill-vs-cancel race explicitly: cancel_bracket_orders reports
    filled_qty/filled_avg_price whenever the entry actually filled before the cancel
    landed, and executor_entry_handler.py's own race-recovery logic proves that value must
    never be silently discarded (a real, unrecorded, unprotected fill left in the account
    while the operator believes the flatten cancelled it away).
    """
    closed: list[str] = []
    failed: list[tuple[str, str]] = []
    for trade_id, symbol, alpaca_order_id in unfilled_trades:
        if not alpaca_order_id:
            failed.append((symbol, f"trade_id={trade_id} has no alpaca_order_id on file - cannot cancel safely"))
            print(f"  FAILED to cancel unfilled order for {symbol} (trade_id={trade_id}): no alpaca_order_id on file")
            continue

        cancel_result = executor.order_manager.cancel_bracket_orders(alpaca_order_id)
        raced_filled_qty = cancel_result.get("filled_qty")
        if raced_filled_qty:
            logger.critical(
                f"[FLATTEN_ALL] {symbol} {alpaca_order_id}: fill-vs-cancel race - "
                f"{raced_filled_qty} shares filled despite attempting to cancel this unfilled "
                f"entry. Closing the resulting position immediately via the broker's own "
                f"close-position endpoint rather than leaving it live."
            )
            close_result = _close_untracked_broker_position(
                executor, symbol, reason=f"MANUAL_EMERGENCY_FLATTEN_RACE_FILL: {reason}"
            )
            try:
                notify(
                    "critical",
                    title=f"Flatten-all fill-vs-cancel race: {symbol}",
                    message=(
                        f"trade_id={trade_id} order {alpaca_order_id}: {raced_filled_qty} shares filled "
                        f"during flatten's cancel attempt. Immediate broker-side close "
                        f"{'succeeded' if close_result.get('success') else 'FAILED: ' + str(close_result.get('message'))}."
                    ),
                )
            except NotificationError as e:
                logger.warning(f"Failed to send flatten-all race-fill alert for {symbol}: {e}")
            if close_result.get("success"):
                closed.append(symbol)
                print(f"  RACE-FILLED then CLOSED {symbol} (trade_id={trade_id}): {close_result.get('message')}")
            else:
                failed.append((symbol, f"race-filled but close failed: {close_result.get('message')}"))
                print(f"  RACE-FILLED and FAILED to close {symbol} (trade_id={trade_id}) - NEEDS MANUAL ATTENTION")
            continue

        # Paper/local mode never has a real Alpaca order to cancel - cancel_bracket_orders
        # reports success=False with this specific message for that case (see its own
        # docstring / executor_exit_handler.py's identical handling of the same message),
        # which is not a real failure here.
        if cancel_result.get("success") or "Paper mode" in str(cancel_result.get("message", "")):
            closed.append(symbol)
            print(f"  CANCELLED unfilled order for {symbol} (trade_id={trade_id}, order={alpaca_order_id})")
        else:
            failed.append((symbol, str(cancel_result.get("message"))))
            print(
                f"  FAILED to cancel unfilled order for {symbol} (trade_id={trade_id}, order={alpaca_order_id}): "
                f"{cancel_result.get('message')}"
            )
    return closed, failed


def _verify_flat_at_broker(config: AlgoConfig) -> list[tuple[str, str]]:
    """Re-query Alpaca's own /v2/positions and return a failed-style list for anything
    still open there.

    REAL-MONEY-READINESS FIX (2026-09-10 /goal pre-live-money audit): every step in main()
    trusts its OWN success signal (exit_trade()'s return dict, a cancel result, a
    close-position response) - none of that proves the account is actually flat at the
    broker afterward. A step can report success while a race, a partial fill, or a
    broker-side quirk this script didn't anticipate leaves real shares behind. Re-query
    the same ground-truth cross-check _fetch_broker_only_symbols already uses at the START
    of this script - one more time at the END, and treat ANY remaining broker position as
    a failure regardless of what every step above believed it accomplished.
    """
    try:
        remaining_positions = _fetch_broker_positions(config)
    except Exception as e:
        print(
            f"WARNING: Could not verify the account is actually flat after flattening "
            f"({type(e).__name__}: {e}) - the steps above reported success/failure, but this "
            f"could not be independently confirmed against the broker. Check /v2/positions "
            f"manually.",
            file=sys.stderr,
        )
        return []

    still_open = [p for p in remaining_positions if p.get("qty") not in (0, 0.0, None)]
    if not still_open:
        return []
    print(
        f"POST-FLATTEN VERIFICATION FAILED: {len(still_open)} position(s) still live at "
        f"the broker despite this run's own success reporting:",
        file=sys.stderr,
    )
    verification_failed = []
    for p in still_open:
        print(f"  {p.get('symbol')}: qty={p.get('qty')}", file=sys.stderr)
        verification_failed.append(
            (str(p.get("symbol")), "still open at broker after flatten (post-flatten verification)")
        )
    return verification_failed


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
    config = AlgoConfig()

    # Always cross-check against the broker directly - see _fetch_broker_only_symbols'
    # docstring for why algo_trades alone is not trustworthy for an emergency flatten.
    # Fails closed: if we can't reach the broker to verify, we refuse to report "nothing to
    # flatten" on DB state alone.
    try:
        broker_only = _fetch_broker_only_symbols(config, {symbol for _, symbol, _, _ in open_trades})
    except Exception as e:
        print(
            f"ERROR: Could not verify against broker's actual positions ({type(e).__name__}: {e}). "
            "Refusing to report position status from DB alone - the DB and broker can diverge, "
            "which is exactly the scenario this tool exists for.",
            file=sys.stderr,
        )
        return 1

    if args.status:
        print(f"Open positions (DB-tracked): {len(open_trades)}")
        for trade_id, symbol, status, _alpaca_order_id in open_trades:
            print(f"  trade_id={trade_id} symbol={symbol} status={status}")
        if broker_only:
            print(f"UNTRACKED broker-only positions (no DB record): {len(broker_only)}")
            for symbol, qty in broker_only:
                print(f"  symbol={symbol} qty={qty} <-- broker has this, DB does not")
        return 0

    if not open_trades and not broker_only:
        print("No open positions (DB or broker) - nothing to flatten.")
        return 0

    if broker_only:
        print(f"WARNING: {len(broker_only)} broker position(s) have NO DB record: {[s for s, _ in broker_only]}")

    print(
        f"FLATTENING {len(open_trades)} DB-tracked position(s) + {len(broker_only)} untracked broker "
        f"position(s). Reason: {args.reason}"
    )

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

    executor = TradeExecutor(config)
    execution_mode = str(config["execution_mode"]).lower()

    closed, failed = _flatten_untracked_broker_positions(executor, broker_only, args.reason)

    # REAL-MONEY-READINESS FIX (2026-09-06 audit): trades in PENDING/OPEN status have been
    # submitted to Alpaca (or queued to be) but have NOT filled yet - there is no position
    # for exit_trade() to close, so routing them through the fill-based exit path always
    # failed with "Position quantity unavailable" and the resting entry order at the broker
    # was left completely untouched. Minutes later that order could fill, creating a brand
    # new, unprotected position (no bracket attached, since Phase 8 already ran) after the
    # operator believed the account was flat. These must be cancelled at the broker instead.
    unfilled_statuses = {TradeStatus.PENDING.value, TradeStatus.OPEN.value}
    unfilled_trades = [
        (tid, sym, order_id) for tid, sym, status, order_id in open_trades if status in unfilled_statuses
    ]
    filled_trades = [(tid, sym) for tid, sym, status, _order_id in open_trades if status not in unfilled_statuses]

    cancel_closed, cancel_failed = _cancel_unfilled_trades(executor, unfilled_trades, args.reason)
    closed.extend(cancel_closed)
    failed.extend(cancel_failed)

    for trade_id, symbol in filled_trades:
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

    verification_failed = _verify_flat_at_broker(config)
    failed.extend(verification_failed)
    if not verification_failed and not failed:
        print("Post-flatten verification: broker confirms zero open positions.")

    if failed:
        print("STILL OPEN - needs manual attention:", file=sys.stderr)
        for symbol, message in failed:
            print(f"  {symbol}: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

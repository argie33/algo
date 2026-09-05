#!/usr/bin/env python3
"""
Per-position stop-loss check-and-repair - split out of phase9_reconciliation.py
(file-size ratchet, see .file-size-baseline.json) to keep the auto-remediation logic
added 2026-09-05 out of an already-oversized legacy file.

See _verify_open_position_stop_loss_protection_step in phase9_reconciliation.py for
the full real-money-readiness context (why this check exists, and why it now
auto-repairs a missing stop-loss leg instead of only alerting a human).
"""

import logging
from typing import Any, Literal

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

Outcome = Literal["skipped", "protected", "repaired", "unrepairable"]


def check_and_repair_one_position(
    order_mgr: Any,
    pos_id: Any,
    symbol: str,
    trade_ids_arr: list[Any] | None,
    quantity: float | None,
    current_stop_price: float | None,
    standalone_stop_order_id: str | None,
) -> Outcome:
    """Verify (and, if needed, auto-repair) one open position's stop-loss protection.

    Returns "skipped" for cases that don't count toward the cycle's checked total at
    all (no resolvable trade/order, or a paper/local-mode order - nothing to verify
    against a real broker either way).
    """
    # A prior cycle may have already repaired this position with a standalone stop
    # that's still resting live - skip re-checking the (now-irrelevant) original
    # bracket for it, otherwise this would resubmit a duplicate protective stop every
    # single cycle forever.
    if standalone_stop_order_id:
        try:
            still_live = order_mgr.is_order_still_live(standalone_stop_order_id)
        except Exception as e:
            logger.warning(
                f"[PHASE 9] {symbol} (position {pos_id}): could not verify prior repair "
                f"order {standalone_stop_order_id}: {e}"
            )
            return "skipped"
        if still_live:
            return "protected"
        # Repair order is no longer live (filled/cancelled/expired) - fall through and
        # treat this position like any other unverified one below.

    # Same convention position_monitor.py uses to resolve "the" trade for a position's
    # stop management (trade_ids_arr[0]) - see its own CRITICAL FIX comment for why
    # this is the correct, established column to read.
    trade_id = trade_ids_arr[0] if trade_ids_arr else None
    if trade_id is None:
        return "skipped"

    with DatabaseContext("read") as cur:
        cur.execute("SELECT alpaca_order_id FROM algo_trades WHERE trade_id = %s", (trade_id,))
        row = cur.fetchone()
    alpaca_order_id = row[0] if row else None

    try:
        result = order_mgr.check_stop_loss_leg_live(alpaca_order_id)
    except Exception as e:
        logger.warning(
            f"[PHASE 9] {symbol} (position {pos_id}): could not verify stop-loss leg for order {alpaca_order_id}: {e}"
        )
        return "skipped"

    if not result.get("checked"):
        return "skipped"  # paper/local mode or order no longer resolvable - nothing to verify
    if result.get("has_live_stop_loss"):
        return "protected"

    logger.critical(
        f"[PHASE 9] {symbol} (position {pos_id}, order {alpaca_order_id}): {result.get('message')} "
        "- attempting auto-repair"
    )

    if not current_stop_price or not quantity:
        logger.critical(
            f"[PHASE 9 CRITICAL] {symbol} (position {pos_id}): cannot auto-repair - "
            f"missing quantity/current_stop_price in algo_positions (qty={quantity}, stop={current_stop_price})"
        )
        return "unrepairable"

    try:
        repair = order_mgr.submit_standalone_protective_stop(symbol, float(quantity), float(current_stop_price))
    except Exception as e:
        repair = {"success": False, "message": f"Exception during repair submission: {e}"}

    if not repair.get("success"):
        logger.critical(
            f"[PHASE 9 CRITICAL] {symbol} (position {pos_id}): auto-repair FAILED - {repair.get('message')}"
        )
        return "unrepairable"

    with DatabaseContext("write") as write_cur:
        write_cur.execute(
            "UPDATE algo_positions SET standalone_stop_order_id = %s WHERE id = %s",
            (repair.get("order_id"), pos_id),
        )
    logger.warning(f"[PHASE 9] {symbol} (position {pos_id}): auto-repaired - {repair.get('message')}")

    # TAKE-PROFIT-LEG FIX (2026-09-05): the standalone stop just submitted above is not
    # part of the original bracket's OCO group. If the take-profit leg is still live (the
    # stop-loss leg alone went missing - e.g. only it hit a day-TIF expiry), the position
    # now has two unlinked live sell orders: the still-live take-profit leg and this new
    # standalone stop. If the take-profit leg fills first, nothing cancels the standalone
    # stop (it's not a sibling order Alpaca knows to cancel), leaving it resting
    # indefinitely and able to later fire against a completely unrelated future position
    # in this symbol. Cancel the original bracket's remaining leg(s) now that the
    # standalone stop is confirmed live, collapsing to stop-only protection - done AFTER
    # the repair succeeds so a cancel failure here never leaves the position with zero
    # protection.
    try:
        cancel_result = order_mgr.cancel_bracket_orders(alpaca_order_id)
        if not cancel_result.get("success"):
            logger.warning(
                f"[PHASE 9] {symbol} (position {pos_id}): repaired with standalone stop, but "
                f"failed to cancel original bracket's remaining leg(s) - {cancel_result.get('message')}"
            )
    except Exception as e:
        logger.warning(
            f"[PHASE 9] {symbol} (position {pos_id}): repaired with standalone stop, but "
            f"could not cancel original bracket's remaining leg(s): {e}"
        )

    return "repaired"

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
import uuid
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
            # REAL-MONEY-READINESS FIX (2026-09-05 audit): a "skipped" return here is
            # indistinguishable at the caller from the benign no-trade-id/paper-mode
            # skips (phase9_reconciliation.py just `continue`s with no alert) - a
            # persistently-failing verification call for one symbol would silently
            # never surface to a human, cycle after cycle, for the exact position this
            # whole check exists to protect. "unrepairable" is the same outcome the
            # caller already alerts loudly on for a confirmed-missing stop; a
            # false-positive alert here (transient blip, actually still protected) is
            # far safer than a silent miss that never gets looked at.
            logger.critical(
                f"[PHASE 9] {symbol} (position {pos_id}): could not verify prior repair "
                f"order {standalone_stop_order_id}, cannot confirm protection: {e}"
            )
            return "unrepairable"
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
        # See the identical rationale on the standalone_stop_order_id check above -
        # "unrepairable" routes this into the caller's existing loud alert path instead
        # of a silent, unalerted "skipped" that could recur forever for one symbol.
        logger.critical(
            f"[PHASE 9] {symbol} (position {pos_id}): could not verify stop-loss leg for order "
            f"{alpaca_order_id}, cannot confirm protection: {e}"
        )
        return "unrepairable"

    if not result.get("checked"):
        return "skipped"  # paper/local mode or order no longer resolvable - nothing to verify
    if result.get("has_live_stop_loss"):
        leg_qty = result.get("leg_qty")
        # Leg presence alone isn't proof of protection: a partial-exit resize
        # (executor_exit_handler.py's _sync_bracket_stop_loss) can fail and only log,
        # leaving a live stop leg sized for the PRE-partial-exit share count. A stop
        # sized larger than the current position would try to sell shares the account
        # no longer holds if it ever fires; resize it in place here rather than
        # reporting "protected" on presence alone.
        if leg_qty is not None and quantity is not None and abs(leg_qty - float(quantity)) > 1e-6:
            if not current_stop_price:
                logger.critical(
                    f"[PHASE 9 CRITICAL] {symbol} (position {pos_id}): stop leg qty mismatch "
                    f"(leg={leg_qty}, position={quantity}) but no current_stop_price to resize with"
                )
                return "unrepairable"
            resize = order_mgr.sync_bracket_stop_loss(
                alpaca_order_id, float(current_stop_price), new_qty=float(quantity)
            )
            if not resize.get("success"):
                logger.critical(
                    f"[PHASE 9 CRITICAL] {symbol} (position {pos_id}): stop leg qty mismatch "
                    f"(leg={leg_qty}, position={quantity}) - resize FAILED: {resize.get('message')}"
                )
                return "unrepairable"
            logger.warning(
                f"[PHASE 9] {symbol} (position {pos_id}): resized stop leg from {leg_qty} to "
                f"{quantity} shares after a stale partial-exit mismatch"
            )
            return "repaired"
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

    # REAL-MONEY-READINESS FIX (2026-09-05 audit): `quantity`/`current_stop_price` are
    # whatever the caller's batch SELECT read at the START of this whole reconciliation
    # cycle - by this point, several live Alpaca round-trips (each with its own
    # retry/backoff, up to a few seconds) have already happened in
    # check_stop_loss_leg_live above. A concurrent execute_exit (full or partial) closing
    # or resizing this exact position in that window would otherwise submit a brand-new
    # standalone GTC sell-stop sized off STALE data - for a full exit, a naked resting
    # sell order on a symbol the account no longer holds, able to fire later against a
    # completely unrelated future position in the same symbol (the same failure class the
    # take-profit-leg-cancel fix below this function already guards against, from a
    # different direction). Re-read immediately before submission - the narrowest window
    # achievable without holding a lock across the entire check-and-repair call.
    with DatabaseContext("read") as fresh_cur:
        fresh_cur.execute(
            "SELECT status, quantity, current_stop_price FROM algo_positions WHERE id = %s",
            (pos_id,),
        )
        fresh_row = fresh_cur.fetchone()
    if fresh_row is None or fresh_row[0] != "open" or not fresh_row[1] or fresh_row[1] <= 0:
        logger.warning(
            f"[PHASE 9] {symbol} (position {pos_id}): position closed or emptied since this "
            f"cycle's batch read - skipping stale-data repair, nothing to protect."
        )
        return "skipped"
    if fresh_row[1] != quantity or fresh_row[2] != current_stop_price:
        logger.warning(
            f"[PHASE 9] {symbol} (position {pos_id}): quantity/stop changed since this cycle's "
            f"batch read (qty {quantity}->{fresh_row[1]}, stop {current_stop_price}->{fresh_row[2]}) "
            f"- using the fresh values for repair."
        )
    quantity, current_stop_price = fresh_row[1], fresh_row[2]
    if not current_stop_price:
        logger.critical(
            f"[PHASE 9 CRITICAL] {symbol} (position {pos_id}): cannot auto-repair - "
            f"fresh re-read has no current_stop_price (qty={quantity})"
        )
        return "unrepairable"

    # Unique per call (not a bare f"stoprepair-{pos_id}") - this position can legitimately
    # need a SECOND standalone repair later in its lifetime (e.g. this repair order itself
    # later expires/fills and a future cycle repairs again), and Alpaca does not release a
    # client_order_id for reuse once assigned, even after that order closes. A permanently
    # fixed id would make that later legitimate resubmission collide with the first one
    # forever, and submit_standalone_protective_stop's ground-truth lookup would then
    # wrongly report success by pointing at the OLD, no-longer-live order - silently
    # leaving the position unprotected. Uniqueness here only needs to survive THIS call's
    # own internal retry loop (crash mid-attempt reusing the same id) - see
    # submit_standalone_protective_stop's own broker-side open-order preflight check for
    # the cross-cycle (this whole call never returning at all) duplicate-prevention layer.
    client_order_id = f"stoprepair-{pos_id}-{uuid.uuid4().hex[:12]}"
    try:
        repair = order_mgr.submit_standalone_protective_stop(
            symbol, float(quantity), float(current_stop_price), client_order_id=client_order_id, pos_id=pos_id
        )
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

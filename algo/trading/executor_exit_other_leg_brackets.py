#!/usr/bin/env python3
"""Cancel every OTHER pyramid leg's bracket order on full exit - split out of
executor_exit_handler.py (file-size ratchet, see .file-size-baseline.json), mirroring
executor_exit_standalone_stop.py's own split for the identical reason.

REAL-MONEY-READINESS FINDING (found via a real-money-readiness audit fork): a pyramided
(2+ leg) position's algo_positions.trade_ids_arr holds one algo_trades row per pyramid add
(executor_entry_handler.py appends a new trade_id onto trade_ids_arr on each add,
max_reentries_per_name=2 by default - a live, reachable config, not hypothetical). Every
exit call site (phase6_exit_execution.py, this module's own caller) resolves
trade_id = trade_ids_arr[0] - the first/original leg only - and the bracket-cancel block in
executor_exit_handler.py cancelled ONLY that leg's own alpaca_order_id. A full exit submits
ONE new sell order sized for the position's ENTIRE remaining quantity across every leg
(algo_positions.quantity), but left every OTHER leg's own stop-loss/take-profit bracket
order still resting live at the broker - the position is now fully sold to zero, so if
either later fires, it's a naked short against a position the account no longer holds.

Mirrors the exact fill-vs-cancel race handling executor_exit_handler.py already applies to
the primary bracket and executor_exit_standalone_stop.py already applies to a
Phase-9-repaired standalone stop: returns the same {success, message, filled_qty,
filled_avg_price} shape those two already produce (aggregated across every other leg, with
a quantity-weighted average fill price) so the caller can apply IDENTICAL race-handling
code to this path with no new branching.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from psycopg2.extensions import cursor as PsycopgCursor

logger = logging.getLogger(__name__)


def fetch_other_leg_order_ids(
    cur: PsycopgCursor[Any], position_id: int | None, primary_trade_id: int
) -> list[tuple[int, str]]:
    """Return (trade_id, alpaca_order_id) for every OTHER leg of this position.

    Excludes primary_trade_id (already handled by the caller's own bracket-cancel path)
    and any leg with no alpaca_order_id (paper/local-mode legs, or a leg whose bracket was
    already cancelled/never submitted - nothing to cancel there).
    """
    if position_id is None:
        # No position row means no other legs could possibly exist - nothing to process,
        # not a data-availability failure worth a marker/exception.
        return []
    cur.execute(
        """SELECT t.trade_id, t.alpaca_order_id
           FROM algo_positions p
           JOIN algo_trades t ON t.trade_id::text = ANY(p.trade_ids_arr::text[])
           WHERE p.position_id = %s AND t.trade_id != %s AND t.alpaca_order_id IS NOT NULL""",
        (position_id, primary_trade_id),
    )
    return [(int(row[0]), row[1]) for row in cur.fetchall()]


def cancel_other_leg_brackets_on_full_exit(
    cancel_order_fn: Callable[[str], dict[str, Any]],
    other_legs: list[tuple[int, str]],
) -> dict[str, Any]:
    """Cancel every other leg's bracket order, aggregating fill-vs-cancel race info.

    No-op (returns filled_qty=None, success=True) when there are no other legs - the
    overwhelmingly common single-leg case. Reuses OrderManager.cancel_bracket_orders as
    `cancel_order_fn` (same reuse executor_exit_standalone_stop.py already relies on) -
    it already performs a post-cancel fill check and returns filled_qty/filled_avg_price.

    A cancel failure on one leg that reports no fill either (unconfirmed - network error,
    rotated credentials, retries exhausted) is treated as success=False on the AGGREGATE
    result, exactly like a primary-bracket cancel failure - the caller's existing
    execution_mode=="auto" abort-the-exit logic applies unchanged. A leg that fills during
    its own cancel race is recorded regardless of whether OTHER legs' cancels succeeded,
    since that fill is real and must not be double-sold either way.
    """
    if not other_legs:
        return {"success": True, "message": "No other legs", "filled_qty": None, "filled_avg_price": None}

    total_filled_qty = 0.0
    filled_notional = 0.0
    unconfirmed_failures: list[str] = []

    for trade_id, order_id in other_legs:
        result = cancel_order_fn(order_id)
        filled_qty = result.get("filled_qty")
        if filled_qty:
            filled_avg_price = result.get("filled_avg_price")
            if filled_avg_price is None:
                raise RuntimeError(
                    f"[EXIT_HANDLER CRITICAL] other-leg trade {trade_id} order {order_id}: "
                    f"{filled_qty} shares filled during its own bracket-cancel race but no fill "
                    f"price was available - cannot safely determine the remaining exit quantity."
                )
            total_filled_qty += float(filled_qty)
            filled_notional += float(filled_qty) * float(filled_avg_price)
            continue
        if not result.get("success"):
            message = result.get("message") or "Bracket cancellation failed (no error message provided)"
            logger.warning(f"Failed to cancel other-leg bracket {order_id} (trade {trade_id}): {message}")
            unconfirmed_failures.append(f"trade {trade_id} order {order_id}: {message}")

    if unconfirmed_failures:
        return {
            "success": False,
            "message": "; ".join(unconfirmed_failures),
            "filled_qty": total_filled_qty or None,
            "filled_avg_price": (filled_notional / total_filled_qty) if total_filled_qty else None,
        }

    return {
        "success": True,
        "message": f"Cancelled {len(other_legs)} other leg(s)' bracket order(s)",
        "filled_qty": total_filled_qty or None,
        "filled_avg_price": (filled_notional / total_filled_qty) if total_filled_qty else None,
    }

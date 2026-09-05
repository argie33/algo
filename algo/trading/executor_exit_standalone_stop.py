#!/usr/bin/env python3
"""Cancel a standalone protective stop on full exit - split out of
executor_exit_handler.py (file-size ratchet, see .file-size-baseline.json) to keep this
2026-09-05 real-money-readiness fix out of an already-oversized legacy file.

REAL-MONEY-READINESS FINDING (2026-09-05): Phase 9's stop-loss auto-repair (776988c4e)
submits a standalone GTC protective stop and records its id in
algo_positions.standalone_stop_order_id when a bracket's stop-loss leg goes missing.
Nothing then cancelled that order when the position closed through the normal exit path
(target/time/trailing-stop) - the full-exit cancellation in executor_exit_handler.py only
ever cancelled the ORIGINAL bracket by alpaca_order_id, with zero awareness of this
separately-tracked standalone stop. Left resting at the broker indefinitely, it could
later fire against a completely unrelated future position opened in the same symbol at a
stale price.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from psycopg2.extensions import cursor as PsycopgCursor

logger = logging.getLogger(__name__)


def fetch_standalone_stop_order_id(cur: PsycopgCursor[Any], position_id: int | None) -> str | None:
    """Read algo_positions.standalone_stop_order_id, re-acquiring the row's FOR UPDATE.

    Piggybacks on the same row _fetch_and_lock_trade_data's caller already locked via its
    own `SELECT 1 ... FOR UPDATE` earlier in the same transaction - re-acquiring FOR UPDATE
    on an already-locked row is a safe no-op in Postgres, so this just adds one more read,
    not a second lock.
    """
    if position_id is None:
        return None
    cur.execute(
        "SELECT standalone_stop_order_id FROM algo_positions WHERE position_id = %s FOR UPDATE",
        (position_id,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def cancel_standalone_stop_on_full_exit(
    cancel_order_fn: Callable[[str], dict[str, Any]],
    cur: PsycopgCursor[Any],
    trade_id: int,
    position_id: int | None,
    standalone_stop_order_id: str | None,
) -> None:
    """Cancel a previously auto-repaired standalone protective stop and clear its id.

    No-op when there was never a standalone stop for this position. Reuses
    OrderManager.cancel_bracket_orders as `cancel_order_fn` - despite the name it just
    DELETEs an order by id, no bracket-specific assumptions, so it works fine here too.

    Clears algo_positions.standalone_stop_order_id regardless of cancel outcome: a 422
    (already terminal/filled) means the order is gone from the broker's perspective
    either way, and leaving a dead id behind would make is_order_still_live() misreport
    this position as unprotected forever on a future auto-repair pass.
    """
    if not standalone_stop_order_id:
        return

    result = cancel_order_fn(standalone_stop_order_id)
    if not result.get("success"):
        logger.warning(
            f"Failed to cancel standalone protective stop {standalone_stop_order_id} "
            f"for trade {trade_id}: {result.get('message')}"
        )

    cur.execute(
        "UPDATE algo_positions SET standalone_stop_order_id = NULL WHERE position_id = %s",
        (position_id,),
    )

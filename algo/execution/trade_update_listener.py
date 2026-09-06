#!/usr/bin/env python3
"""Always-on Alpaca `trade_updates` websocket consumer (real-money-readiness architecture
rebuild, 2026-09-06 - see memory/intraday_monitoring_architecture_gap_20260906.md for the
audit that found order/fill state was 100% REST polling, invoked only when the
orchestrator runs).

DESIGN CONSTRAINT (do not violate): this process is a LATENCY ACCELERANT ONLY, never a
second source of fill truth. On every trade_updates event it does not write any DB row
itself - it triggers the exact same reconciliation methods
(DailyReconciliation.check_partial_fills / .reconcile_exit_fills, from
algo/infrastructure/reconciliation_fill_and_account.py and reconciliation_exit_fills.py)
that already run once per orchestrator cycle (~5x/day), just immediately instead of
waiting for the next cycle. Both methods independently re-derive truth from Alpaca's REST
`fetch_closed_orders()` each time they run - they do not trust the websocket event's own
payload for anything beyond "something changed, go look now." This means:
  - A missed/dropped/duplicate websocket event can never produce an untracked or
    double-recorded position - REST reconciliation converges to the same truth on its own
    schedule regardless of whether this process saw the event at all.
  - If this process is down entirely, the only effect is LATENCY (fills recorded a few
    minutes late via the next scheduled reconciliation instead of instantly) - never lost
    or incorrect state. See tests/unit/test_trade_update_listener_20260906.py's explicit
    "listener never fires, REST reconciliation still converges" test for this.
  - The fill-vs-cancel race fix (order_manager.py's cancel_bracket_orders, commits
    bc9b68268/b9c350ee2) is preserved automatically, since this never calls any order
    API itself - it only ever reads (via the reconciliation methods' own broker calls).

Runs as an always-on ECS Fargate service (desired_count=1,
terraform/modules/loaders/trade-update-listener.tf) - the first long-lived process in this
repo's infrastructure (everything else is Lambda or scheduled/triggered batch ECS tasks).
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import date as _date
from datetime import datetime, timezone
from typing import Any

from algo.config.api_endpoints import get_alpaca_base_url
from algo.config.credential_manager import get_alpaca_credentials
from algo.infrastructure import get_config
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)

# Alpaca drops trade_updates connections routinely (idle timeouts, server-side restarts) -
# this is expected, not exceptional. Reconnect promptly but back off on repeated failures
# so a genuine outage doesn't spin-loop against Alpaca's API.
RECONNECT_BASE_DELAY_SECONDS = 2
RECONNECT_MAX_DELAY_SECONDS = 60


def _run_reconciliation_now(config: Any, trigger_event_type: str, trigger_symbol: str | None) -> None:
    """Re-run the same entry-fill-drift and exit-fill-price reconciliation the orchestrator
    already runs once per cycle - NOW, instead of waiting for the next cycle. Deliberately
    reuses DailyReconciliation's own methods rather than writing anything here directly -
    see this module's docstring for why that's the entire safety argument.
    """
    # BUG FOUND (adversarial review, 2026-09-06): the try/except below used to start AFTER
    # DailyReconciliation(config) construction and the recon.broker check - but __init__
    # itself can raise (e.g. ValueError if config["execution_mode"] is missing), which
    # would then propagate uncaught, contradicting this function's own "never let a
    # reconciliation hiccup kill the listener process" contract. The whole thing (build +
    # check + reconcile) is now inside one try/except.
    try:
        from algo.infrastructure.reconciliation import DailyReconciliation

        recon = DailyReconciliation(config)
        if recon.broker is None:
            logger.info(
                f"[TRADE_UPDATE_LISTENER] {trigger_event_type} event for {trigger_symbol} - "
                "no broker configured (paper/local mode), nothing to reconcile."
            )
            return

        with DatabaseContext("write") as cur:
            fill_result = recon.check_partial_fills(cur)
            exit_result = recon.reconcile_exit_fills(cur, _date.today())
        logger.info(
            f"[TRADE_UPDATE_LISTENER] Reconciled after {trigger_event_type} event "
            f"({trigger_symbol}): entry_fills={fill_result}, exit_fills={exit_result}"
        )
    except Exception as e:
        # Never let a reconciliation hiccup kill the listener process itself - the next
        # trade_updates event (or the next scheduled orchestrator/unified-risk-monitor
        # cycle, which calls these same reconciliation paths independently) will retry.
        logger.error(
            f"[TRADE_UPDATE_LISTENER] Reconciliation trigger failed for {trigger_event_type} "
            f"event ({trigger_symbol}): {e}. Will retry on the next event/scheduled cycle.",
            exc_info=True,
        )


async def _handle_trade_update(config: Any, data: Any) -> None:
    """Alpaca trade_updates event handler. `data` is the SDK's TradeUpdate object -
    only `data.event` and `data.order['symbol']` are used, both purely for logging/routing
    to the reconciliation trigger above; nothing here is trusted as ground truth (see
    module docstring)."""
    event_type = getattr(data, "event", "unknown")
    order = getattr(data, "order", {}) or {}
    symbol = order.get("symbol") if isinstance(order, dict) else None

    if event_type not in ("fill", "partial_fill", "canceled", "rejected", "expired"):
        return

    logger.info(f"[TRADE_UPDATE_LISTENER] Received {event_type} for {symbol}")
    _run_reconciliation_now(config, event_type, symbol)


def _build_stream(config: Any) -> Any:
    # Imported lazily so this module can be imported (and its handler logic unit-tested)
    # without the alpaca_trade_api package needing to be importable in every environment
    # that imports this module.
    from alpaca_trade_api.stream import Stream

    creds = get_alpaca_credentials()
    key = creds.get("key")
    secret = creds.get("secret")
    if not key or not secret:
        raise RuntimeError("[TRADE_UPDATE_LISTENER] Alpaca credentials unavailable - cannot start websocket listener.")

    base_url = get_alpaca_base_url(config.get("execution_mode"))
    stream = Stream(key, secret, base_url=base_url)

    async def _handler(data: Any) -> None:
        await _handle_trade_update(config, data)

    stream.subscribe_trade_updates(_handler)
    return stream


def run_forever() -> None:
    """Reconnect/backoff loop around the Stream client. Alpaca's websocket disconnects
    routinely (idle timeouts, server restarts) - `stream.run()` blocking calls are expected
    to eventually return/raise, and this loop is what makes the process actually always-on
    rather than exiting on the first disconnect.
    """
    config = get_config()
    delay = RECONNECT_BASE_DELAY_SECONDS
    consecutive_failures = 0

    while True:
        try:
            logger.info("[TRADE_UPDATE_LISTENER] Connecting to Alpaca trade_updates stream...")
            stream = _build_stream(config)
            stream.run()  # blocks until disconnected/error
            logger.warning("[TRADE_UPDATE_LISTENER] Stream.run() returned - reconnecting.")
            consecutive_failures = 0
            delay = RECONNECT_BASE_DELAY_SECONDS
        except Exception as e:
            consecutive_failures += 1
            logger.critical(
                f"[TRADE_UPDATE_LISTENER] Stream connection failed (attempt {consecutive_failures}): {e}. "
                f"Reconnecting in {delay}s. REST reconciliation continues independently on its own "
                "schedule while this listener is down - fills are delayed, never lost.",
                exc_info=True,
            )
            time.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    logger.info(f"[TRADE_UPDATE_LISTENER] Starting at {datetime.now(timezone.utc).isoformat()}")
    run_forever()

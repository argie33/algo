#!/usr/bin/env python3
"""Always-on Alpaca `trade_updates` websocket consumer (real-money-readiness architecture
rebuild, 2026-09-06 - see memory/intraday_monitoring_architecture_gap_20260906.md for the
audit that found order/fill state was 100% REST polling, invoked only when the
orchestrator runs).

Talks Alpaca's trading-stream protocol directly over a raw websocket (the `websockets`
package - already a transitive dependency of yfinance>=1.4.1's own websockets>=13.0
requirement, now declared directly in requirements.txt since this module relies on it
explicitly) rather than via the `alpaca-trade-api` SDK's `Stream` class originally used
here: that SDK hard-pins `websockets<11`, which made requirements.txt's `alpaca-trade-api`
+ `yfinance` combination literally uninstallable (pip ResolutionImpossible, caught by CI
right after this module was first added). Every other Alpaca call in this codebase already
uses raw `requests` against the REST API rather than an SDK, for the same reason - one
fewer dependency surface to keep in sync across the whole requirements.txt.

Protocol (Alpaca's account/trading update stream, distinct from the market-data stream):
connect to `{base_url with https->wss}/stream`, send `{"action": "auth", "key": ...,
"secret": ...}`, wait for `{"stream": "authorization", "data": {"status": "authorized"}}`,
then send `{"action": "listen", "data": {"streams": ["trade_updates"]}}` and read
`{"stream": "trade_updates", "data": {...}}` messages going forward. This is intentionally
narrow - just enough to know "something changed, go look now" (see DESIGN CONSTRAINT below,
unchanged by this rewrite: this process still never trusts the message payload as truth).

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

import asyncio
import json
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

# Only the account/trading update stream, deliberately not the separate market-data stream
# (unrelated to this listener's purpose - order/fill events only).
_STREAM_PATH = "/stream"
_RELEVANT_EVENTS = frozenset({"fill", "partial_fill", "canceled", "rejected", "expired"})
# Alpaca's own idle-connection timeout is well under this; a missed ping means the
# connection is already dead, so failing fast here just gets to reconnect sooner.
_WEBSOCKET_PING_TIMEOUT_SECONDS = 30


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
        # trade_updates event (or the next scheduled orchestrator cycle, which calls these
        # same reconciliation paths independently) will retry.
        logger.error(
            f"[TRADE_UPDATE_LISTENER] Reconciliation trigger failed for {trigger_event_type} "
            f"event ({trigger_symbol}): {e}. Will retry on the next event/scheduled cycle.",
            exc_info=True,
        )


async def _handle_trade_update(config: Any, message: dict[str, Any]) -> None:
    """Handle one `{"stream": "trade_updates", "data": {...}}` message. Only `data.event`
    and `data.order.symbol` are used, both purely for logging/routing to the reconciliation
    trigger above; nothing here is trusted as ground truth (see module docstring)."""
    data = message.get("data") or {}
    event_type = data.get("event") if "event" in data else "unknown"
    order = data.get("order") or {}
    symbol = order.get("symbol") if isinstance(order, dict) else None

    if event_type not in _RELEVANT_EVENTS:
        return

    logger.info(f"[TRADE_UPDATE_LISTENER] Received {event_type} for {symbol}")
    _run_reconciliation_now(config, event_type, symbol)


def _get_stream_url(config: Any) -> str:
    base_url = get_alpaca_base_url(config.get("execution_mode"))
    ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://")
    return f"{ws_base}{_STREAM_PATH}"


async def _run_stream_once(config: Any) -> None:
    """Connect, authenticate, subscribe, and consume trade_updates messages until the
    connection drops or errors - one full connection lifecycle. Imports `websockets`
    lazily so this module can be imported (and its handler logic unit-tested) without that
    package needing to be importable in every environment that imports this module."""
    import websockets

    creds = get_alpaca_credentials()
    key = creds.get("key")
    secret = creds.get("secret")
    if not key or not secret:
        raise RuntimeError("[TRADE_UPDATE_LISTENER] Alpaca credentials unavailable - cannot start websocket listener.")

    url = _get_stream_url(config)
    async with websockets.connect(url, ping_timeout=_WEBSOCKET_PING_TIMEOUT_SECONDS) as ws:
        await ws.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
        auth_reply = json.loads(await ws.recv())
        auth_status = (auth_reply.get("data") or {}).get("status") if isinstance(auth_reply, dict) else None
        if auth_status != "authorized":
            raise RuntimeError(f"[TRADE_UPDATE_LISTENER] Alpaca stream auth failed: {auth_reply}")

        await ws.send(json.dumps({"action": "listen", "data": {"streams": ["trade_updates"]}}))
        logger.info("[TRADE_UPDATE_LISTENER] Authenticated and subscribed to trade_updates.")

        async for raw_message in ws:
            try:
                message = json.loads(raw_message)
            except (TypeError, ValueError) as e:
                logger.warning(f"[TRADE_UPDATE_LISTENER] Dropping unparseable message: {e}")
                continue
            if isinstance(message, dict) and message.get("stream") == "trade_updates":
                await _handle_trade_update(config, message)


def run_forever() -> None:
    """Reconnect/backoff loop around the websocket connection. Alpaca's websocket disconnects
    routinely (idle timeouts, server restarts) - `_run_stream_once` returning/raising is
    expected, and this loop is what makes the process actually always-on rather than exiting
    on the first disconnect.
    """
    config = get_config()
    delay = RECONNECT_BASE_DELAY_SECONDS
    consecutive_failures = 0

    while True:
        try:
            logger.info("[TRADE_UPDATE_LISTENER] Connecting to Alpaca trade_updates stream...")
            asyncio.run(_run_stream_once(config))
            logger.warning("[TRADE_UPDATE_LISTENER] Stream connection closed - reconnecting.")
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

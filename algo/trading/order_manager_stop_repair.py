#!/usr/bin/env python3
"""
Standalone protective-stop repair - split out of order_manager.py (file-size ratchet,
see .file-size-baseline.json) to keep the auto-remediation logic added 2026-09-05 out
of an already-oversized legacy file.

REAL-MONEY-READINESS FINDING (2026-09-05): phase9_reconciliation.py's proactive
stop-loss protection check used to only alert a human when a bracket's stop-loss leg
went missing - not an acceptable real-money control when nobody reliably watches
alerts in real time. This module provides the auto-repair primitives: checking whether
a previously-placed repair order is still live, and submitting a fresh standalone
protective stop when one isn't.

Mixed into OrderManager (see order_manager.py's class declaration) rather than kept as
free functions so both methods keep using self.alpaca_key/secret/base_url and
self.get_order exactly like every other OrderManager method - callers
(phase9_reconciliation.py) don't need to know this is a separate file.
"""

import json
import logging
import time
from typing import Any

import requests

from algo.infrastructure import get_api_timeout

logger = logging.getLogger(__name__)


class StopLossRepairMixin:
    """OrderManager methods for auto-repairing a missing stop-loss leg."""

    def is_order_still_live(self, alpaca_order_id: str | None) -> bool | None:
        """Is this order (bracket leg or standalone) still resting/working at the broker?

        Used by phase9_reconciliation.py to check a previously-placed standalone
        protective stop (algo_positions.standalone_stop_order_id) before deciding whether
        another auto-remediation attempt is needed - without this, a stop that's still
        perfectly live would look "missing" (since it's not a leg of the ORIGINAL bracket)
        and the reconciliation step would resubmit a duplicate protective stop every cycle.

        Returns:
            True/False: order fetched successfully, status checked against the same
                "live" status set order_manager.py's _find_live_stop_loss_leg uses for
                bracket legs.
            None: paper/local mode or order no longer resolvable - not evidence either way.
        """
        from algo.trading.order_manager import _LIVE_LEG_STATUSES

        if not alpaca_order_id or alpaca_order_id.startswith(("LOCAL-", "PENDING-")):
            return None
        order = self.get_order(alpaca_order_id)  # type: ignore[attr-defined]
        if order is None:
            return None
        return order.get("status") in _LIVE_LEG_STATUSES

    def submit_standalone_protective_stop(
        self, symbol: str, qty: float, stop_price: float, client_order_id: str | None = None
    ) -> dict[str, Any]:
        """Auto-remediation for check_stop_loss_leg_live finding a position with no live
        stop-loss protection: submit a plain (non-bracket) sell stop order directly.

        This is NOT a leg of the original bracket order and Alpaca will not associate it
        with that parent - callers (phase9_reconciliation.py) must persist the returned
        order id themselves (algo_positions.standalone_stop_order_id) so a future cycle
        recognizes protection already exists instead of submitting a duplicate stop every
        cycle forever.

        Uses time_in_force=gtc, deliberately different from the bracket entry's day TIF -
        this repair exists specifically because a day-TIF leg may have already expired
        unprotected once; resubmitting another day order would just recreate the same
        expiry risk every single day until someone notices. A resting GTC sell-stop is
        the correct fix for a position already known to be held multi-day.

        Side is hardcoded "sell" - this codebase is long-only (see order_manager.py's
        _build_bracket_order_payload hardcoded "side": "buy" for entries); there is no
        short-position case to protect.
        """
        from algo.trading.order_manager import _quantize_price

        if not self.alpaca_key or not self.alpaca_secret:  # type: ignore[attr-defined]
            return {"success": False, "message": "Cannot submit protective stop - Alpaca credentials missing"}

        order_data: dict[str, Any] = {
            "symbol": symbol,
            "qty": str(qty),
            "side": "sell",
            "type": "stop",
            "time_in_force": "gtc",
            "stop_price": _quantize_price(stop_price),
            "extended_hours": False,
        }
        if client_order_id:
            order_data["client_order_id"] = client_order_id

        max_attempts = 3
        last_error = "No attempts made"
        for attempt in range(max_attempts):
            try:
                resp = requests.post(
                    f"{self.alpaca_base_url}/v2/orders",  # type: ignore[attr-defined]
                    headers={
                        "APCA-API-KEY-ID": self.alpaca_key,  # type: ignore[attr-defined]
                        "APCA-API-SECRET-KEY": self.alpaca_secret,  # type: ignore[attr-defined]
                        "Content-Type": "application/json",
                    },
                    data=json.dumps(order_data),
                    timeout=get_api_timeout(),
                )
                if resp.status_code in (200, 201):
                    try:
                        data = resp.json()
                    except (requests.RequestException, requests.Timeout, ValueError) as e:
                        return {"success": False, "message": f"Protective stop response is invalid JSON: {e}"}
                    new_id = data.get("id")
                    return {
                        "success": True,
                        "order_id": new_id,
                        "message": (
                            f"Standalone protective stop submitted for {symbol}: {qty} shares "
                            f"@ stop {stop_price:.4f} (order id {new_id})"
                        ),
                    }

                # A 422/40310000-class rejection for "insufficient qty available" almost
                # always means Alpaca already has a resting sell order (or another repair
                # attempt landed first) covering these shares - not a transient failure,
                # and retrying would either loop forever or oversell on a partial match.
                last_error = f"Failed to submit protective stop: {resp.status_code} {resp.text[:300]}"
                if resp.status_code in (429, 503) and attempt < max_attempts - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"[PROTECTIVE_STOP] {symbol}: {last_error} - transient, "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/{max_attempts})"
                    )
                    time.sleep(wait_time)
                    continue
                return {"success": False, "message": last_error}
            except (requests.RequestException, requests.Timeout) as e:
                last_error = f"Error submitting protective stop: {e!s}"
                logger.warning(f"[PROTECTIVE_STOP] {symbol}: {last_error} (attempt {attempt + 1}/{max_attempts})")
                if attempt < max_attempts - 1:
                    time.sleep(1)

        return {
            "success": False,
            "message": f"Failed to submit protective stop for {symbol} after {max_attempts} attempts: {last_error}",
        }

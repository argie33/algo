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

    def _find_open_sell_stop_order(self, symbol: str, pos_id: int | None = None) -> dict[str, Any] | None:
        """Does a resting (non-bracket) sell-stop order already exist for this symbol?

        Ground-truth check used by submit_standalone_protective_stop before submitting a
        new standalone repair stop - catches the case where an EARLIER repair call fully
        succeeded at the broker but crashed before its caller could persist
        standalone_stop_order_id, so this cycle has no record of it and would otherwise
        submit a genuine second live stop for the same shares.

        REAL-MONEY-READINESS FIX (2026-09-06): this used to match the FIRST open sell-stop
        order for the symbol, full stop - a broker-level query has no concept of this
        codebase's own position_id, so a leftover resting stop from a DIFFERENT, unrelated
        position in the same symbol (e.g. an earlier position that closed without its stop
        being cancelled - see alpaca_sync_manager.py's own orphaned-leg cleanup for that
        exact gap) would be misidentified as "this position is already protected," reusing
        its order_id/qty/stop_price for a position it has nothing to do with and skipping
        the real repair this position actually needs.
        phase9_stop_loss_repair.py's own client_order_id for a repair order is always
        f"stoprepair-{pos_id}-{uuid}" (unique per call, but always prefixed with the exact
        position_id it was submitted for) - when the caller passes pos_id, only an order
        whose client_order_id carries THAT position's prefix counts as "already resting for
        this position." Falls back to the old symbol-only match only when no pos_id is
        given (there is currently no such caller, but this keeps the broker-state-check
        semantics from before pos_id-awareness for any future direct caller).

        Returns: the matching order dict, or None if none exists / the lookup itself fails
        (fails open - see caller).
        """
        if not self.alpaca_key or not self.alpaca_secret:  # type: ignore[attr-defined]
            return None
        resp = requests.get(
            f"{self.alpaca_base_url}/v2/orders",  # type: ignore[attr-defined]
            params={"status": "open", "symbols": symbol},
            headers={
                "APCA-API-KEY-ID": self.alpaca_key,  # type: ignore[attr-defined]
                "APCA-API-SECRET-KEY": self.alpaca_secret,  # type: ignore[attr-defined]
            },
            timeout=get_api_timeout(),
        )
        resp.raise_for_status()
        orders = resp.json()
        if not isinstance(orders, list):
            return None
        sell_stop_orders = [o for o in orders if o.get("side") == "sell" and o.get("type") == "stop"]
        if pos_id is not None:
            prefix = f"stoprepair-{pos_id}-"
            for order in sell_stop_orders:
                client_order_id = order.get("client_order_id") or ""
                if client_order_id.startswith(prefix):
                    return order  # type: ignore[no-any-return]
            return None
        return sell_stop_orders[0] if sell_stop_orders else None

    def cancel_all_open_orders_for_symbol(self, symbol: str) -> dict[str, Any]:
        """Cancel every open order resting at the broker for a symbol - used when a
        position has been confirmed CLOSED at the broker (Alpaca's own /v2/positions no
        longer lists it) but local reconciliation has no record of why (manual close via
        the Alpaca dashboard/API, or any other out-of-band exit) and so never ran the
        normal exit path that would have cancelled the bracket's sibling legs.

        REAL-MONEY-READINESS FINDING (2026-09-06 dig): a bracket's stop-loss/take-profit
        legs are only ever cancelled by this codebase's own exit path (executor_exit_
        handler.py) or by check_and_repair_one_position's take-profit-leg-cancel step
        (phase9_stop_loss_repair.py) after a standalone repair. Neither runs for a
        position closed entirely outside the algo. The stale leg then rests indefinitely
        - for a long-only account it can't fill against zero shares today, but if the
        algo re-enters this exact symbol later, that leftover sell order (sized/priced
        from the OLD position, never linked in DB to the new one) can fire against the
        new position without the algo's knowledge. Cancelling here is a pure risk-
        reduction action (removes a stale resting order) and deliberately does NOT touch
        algo_positions/algo_trades - it must never be used as a substitute for the
        alert-and-manually-review path callers already have for the DB-side question of
        whether to mark the position closed.

        Returns: {"success": bool, "cancelled_order_ids": list[str], "message": str}.
        Best-effort per order - one order's cancel failing does not stop the others.
        """
        if not self.alpaca_key or not self.alpaca_secret:  # type: ignore[attr-defined]
            return {"success": False, "cancelled_order_ids": [], "message": "Alpaca credentials missing"}

        try:
            resp = requests.get(
                f"{self.alpaca_base_url}/v2/orders",  # type: ignore[attr-defined]
                params={"status": "open", "symbols": symbol},
                headers={
                    "APCA-API-KEY-ID": self.alpaca_key,  # type: ignore[attr-defined]
                    "APCA-API-SECRET-KEY": self.alpaca_secret,  # type: ignore[attr-defined]
                },
                timeout=get_api_timeout(),
            )
            resp.raise_for_status()
            open_orders = resp.json()
        except (requests.RequestException, requests.Timeout, ValueError) as e:
            return {
                "success": False,
                "cancelled_order_ids": [],
                "message": f"Could not list open orders for {symbol}: {e}",
            }
        if not isinstance(open_orders, list) or not open_orders:
            return {"success": True, "cancelled_order_ids": [], "message": f"No open orders for {symbol}"}

        cancelled: list[str] = []
        failures: list[str] = []
        for order in open_orders:
            order_id = order.get("id")
            if not order_id:
                continue
            try:
                result = self.cancel_bracket_orders(order_id)  # type: ignore[attr-defined]
            except Exception as e:
                failures.append(f"{order_id}: {e}")
                continue
            if result.get("success"):
                cancelled.append(order_id)
            else:
                failures.append(f"{order_id}: {result.get('message')}")

        return {
            "success": not failures,
            "cancelled_order_ids": cancelled,
            "message": (
                f"Cancelled {len(cancelled)} stale order(s) for {symbol}"
                + (f"; {len(failures)} failed: {'; '.join(failures)}" if failures else "")
            ),
        }

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
        self,
        symbol: str,
        qty: float,
        stop_price: float,
        client_order_id: str | None = None,
        pos_id: int | None = None,
    ) -> dict[str, Any]:
        """Auto-remediation for check_stop_loss_leg_live finding a position with no live
        stop-loss protection: submit a plain (non-bracket) sell stop order directly.

        This is NOT a leg of the original bracket order and Alpaca will not associate it
        with that parent - callers (phase9_reconciliation.py) must persist the returned
        order id themselves (algo_positions.standalone_stop_order_id) so a future cycle
        recognizes protection already exists instead of submitting a duplicate stop every
        cycle forever.

        `pos_id`: threaded through to _find_open_sell_stop_order's own pre-submission
        ground-truth check (2026-09-06 real-money-readiness fix - see that method's
        docstring) so the "already resting" check can never reuse a stale order that
        actually belongs to a different, unrelated position in the same symbol. Optional
        only for backward compatibility with any caller that doesn't yet track pos_id;
        phase9_stop_loss_repair.py (the only current caller) always has it.

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

        try:
            existing_stop = self._find_open_sell_stop_order(symbol, pos_id=pos_id)
        except Exception as e:
            existing_stop = None
            logger.warning(f"[PROTECTIVE_STOP] {symbol}: pre-submission existing-order check failed: {e}")
        if existing_stop:
            return {
                "success": True,
                "order_id": existing_stop.get("id"),
                "message": (
                    f"Standalone protective stop for {symbol} already resting at the broker "
                    f"(id={existing_stop.get('id')}) from an earlier repair whose DB write was "
                    "never confirmed - reusing it instead of submitting a duplicate."
                ),
            }

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
                if client_order_id and resp.status_code not in (429, 503):
                    existing = self._lookup_order_by_client_order_id(client_order_id)  # type: ignore[attr-defined]
                    if existing:
                        return {
                            "success": True,
                            "order_id": existing.get("id"),
                            "message": (
                                f"Standalone protective stop for {symbol} already existed at the broker "
                                f"(client_order_id={client_order_id}, id={existing.get('id')}) - an earlier "
                                "attempt's response was lost, not a new submission."
                            ),
                        }
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

        if client_order_id:
            existing = self._lookup_order_by_client_order_id(client_order_id)  # type: ignore[attr-defined]
            if existing:
                return {
                    "success": True,
                    "order_id": existing.get("id"),
                    "message": (
                        f"Standalone protective stop for {symbol} already existed at the broker "
                        f"(client_order_id={client_order_id}, id={existing.get('id')}) - an earlier "
                        "attempt's response was lost, not a new submission."
                    ),
                }
        return {
            "success": False,
            "message": f"Failed to submit protective stop for {symbol} after {max_attempts} attempts: {last_error}",
        }

#!/usr/bin/env python3
"""
Order Manager - Send and verify orders via Alpaca API

Responsibilities:
- Bracket orders (entry with stop loss + take profit)
- Market exit orders
- Order verification and status queries
- Fill price and quantity retrieval
"""

import json
import logging
import math
import time
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

import requests

from algo.infrastructure import get_api_timeout
from algo.trading.exceptions import OrderExecutionError
from algo.trading.order_manager_stop_repair import StopLossRepairMixin
from utils.validation import AlpacaResponseValidator

logger = logging.getLogger(__name__)
validator = AlpacaResponseValidator()


_LIVE_LEG_STATUSES = {"new", "accepted", "held", "pending_new", "accepted_for_bidding"}


def _find_live_stop_loss_leg(legs: list[Any]) -> dict[str, Any] | None:
    """Find the resting stop-loss leg (if any) in a bracket order's `legs` array.

    Shared by sync_bracket_stop_loss (which needs the leg's id to replace it) and
    check_stop_loss_leg_live (which only needs to know whether one exists) so the two
    can never disagree about what counts as "live".
    """
    return next(
        (
            leg
            for leg in legs
            if isinstance(leg, dict) and leg.get("order_type") == "stop" and leg.get("status") in _LIVE_LEG_STATUSES
        ),
        None,
    )


def _quantize_price(v: float) -> str:
    """Quantize a price for broker submission - SEC Rule 612 sub-penny rule.

    Securities priced under $1.00 must be quoted in $0.0001 increments, not $0.01 - Alpaca
    enforces this. Uses Decimal.quantize(ROUND_HALF_UP), not Python's round() (binary-float
    round-half-to-even can silently submit an order 1 cent off, e.g. round(2.675, 2) == 2.67).
    Shared by every order-submission path (bracket entries, exit limit orders) so this logic
    exists exactly once - see _build_bracket_order_payload's history for why that mattered.
    """
    v_dec = Decimal(str(v))
    places = Decimal("0.0001") if v_dec < 1 else Decimal("0.01")
    return str(v_dec.quantize(places, rounding=ROUND_HALF_UP))


class OrderManager(StopLossRepairMixin):
    """Manage order lifecycle via Alpaca API.

    is_order_still_live/submit_standalone_protective_stop live in
    order_manager_stop_repair.py's StopLossRepairMixin (split out to respect the
    file-size ratchet on this already-oversized file, see .file-size-baseline.json).
    """

    def __init__(self, alpaca_key: str | None, alpaca_secret: str | None, alpaca_base_url: str) -> None:
        self.alpaca_key = alpaca_key
        self.alpaca_secret = alpaca_secret
        self.alpaca_base_url = alpaca_base_url

    def _entry_result_from_order_data(self, symbol: str, data: dict[str, Any]) -> dict[str, Any]:
        """Interpret an Alpaca order object into send_bracket_order's result shape.

        Shared by the normal 200/201 submission response and by the duplicate-
        client_order_id recovery path (_lookup_order_by_client_order_id) - both hand this
        method the same Alpaca order object schema, just fetched via different requests.
        """
        validation = validator.validate_order_response(data)
        if not validation["valid"]:
            error_msg = f"Invalid response: {', '.join(validation['errors'])}"
            logger.error(f"[SEND_ORDER] {symbol}: {error_msg}. Response data: {data}")
            return {"success": False, "message": error_msg}

        order_status = validation["status"]
        executed_price = validation["filled_avg_price"]

        logger.info(
            f"[SEND_ORDER] {symbol}: Order {validation['order_id']} created - status={order_status}, fill=${executed_price}"
        )
        return {
            "success": True,
            "order_id": validation["order_id"],
            "order_class": validation["order_class"],
            "status": order_status,
            "executed_price": executed_price,
            "legs": validation["legs"],
            "rejection_reason": validation.get("rejection_reason"),
        }

    def _build_bracket_order_payload(
        self,
        symbol: str,
        shares: float,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float | None,
        client_order_id: str | None,
    ) -> dict[str, Any]:
        """Build the Alpaca bracket-order request body for send_bracket_order."""

        # CRITICAL: use Decimal.quantize(ROUND_HALF_UP), not Python's built-in round(), for every
        # price submitted to the broker. round() operates on binary float representation and uses
        # round-half-to-even - the classic round(2.675, 2) == 2.67 trap (2.675 isn't exactly
        # representable in binary float) can silently submit an order 1 cent off the intended
        # price. The take_profit fallback below already used Decimal correctly; the entry
        # limit_price/stop_price literally two lines above it did not. Fixed 2026-07-21 for
        # consistency with position_sizer.py/executor_entry_handler.py, which are Decimal-only.
        #
        # BUG FOUND 2026-08-11: this unconditionally quantized to 2 decimal places for every
        # price, but SEC Rule 612 (the "sub-penny rule") requires securities priced under
        # $1.00 to be quoted in $0.0001 increments, not $0.01 - Alpaca enforces this and can
        # reject (or silently mis-price) an order for a sub-$1 symbol submitted with only 2
        # decimals of precision. This codebase already treats sub-$1/low-priced symbols as a
        # real, expected case elsewhere (buy_signal_generator.py computes buy/stop/target
        # levels at 4-decimal precision throughout; executor_entry_handler.py normalizes
        # entry_price/stop_loss_price to 4 decimals "for consistent duplicate detection";
        # phase8_entry_execution.py explicitly lists "penny stocks" alongside ETFs as an
        # anticipated high-volatility case) - this was the one place in the actual
        # broker-submission path that silently threw that precision away right before hitting
        # the API. No existing test/code path in this repo compensated for it.
        # (_quantize_price is now a module-level function shared with send_market_exit's
        # marketable-limit path - see its docstring.)

        # CRITICAL: Always build a bracket order - stop loss protection is mandatory
        order_data: dict[str, Any] = {
            "symbol": symbol,
            "qty": shares,
            "side": "buy",
            "type": "limit",
            "time_in_force": "day",
            "limit_price": _quantize_price(entry_price),
            "extended_hours": False,
            "order_class": "bracket",
            "stop_loss": {
                "stop_price": _quantize_price(stop_loss_price),
            },
        }
        if client_order_id:
            order_data["client_order_id"] = client_order_id

        # Add take-profit target (either explicit or computed from 1.5R)
        if take_profit_price is not None and take_profit_price > entry_price:
            order_data["take_profit"] = {
                "limit_price": _quantize_price(take_profit_price),
            }
        else:
            risk_dec = Decimal(str(entry_price)) - Decimal(str(stop_loss_price))
            if risk_dec > 0:
                tp_dec = Decimal(str(entry_price)) + (Decimal("1.5") * risk_dec)
                order_data["take_profit"] = {
                    "limit_price": _quantize_price(float(tp_dec)),
                }

        return order_data

    def send_bracket_order(
        self,
        symbol: str,
        shares: float,
        entry_price: float,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a BRACKET order to Alpaca - entry + stop loss + take profit.

        This is the institutional best practice: even if our system goes down,
        Alpaca enforces the stop loss and take profit. No naked positions.

        Bracket order: parent buy fills, then OCO (one-cancels-other) of:
          - Stop loss order (executes if price drops to stop)
          - Take profit limit order (executes if price hits target)

        CRITICAL: Bracket orders REQUIRE a valid stop_loss_price. This is non-negotiable.
        Sending naked positions without stop-loss protection violates risk management.
        Fail-fast if stop loss is missing - do not send a simple limit order fallback.

        client_order_id: Passed through to Alpaca as broker-side idempotency protection.
        Caller passes a deterministic idempotency_key (hash of symbol/entry_price/signal_date only -
        see executor_entry_handler.py's key_source; stop_loss_price is deliberately NOT part of the
        hash since it's derived from the same signal and shouldn't vary between retries), NOT the
        random per-attempt trade_id - the value must be the same across separate attempts at the
        same underlying trade intent for this to work.
        If a submission's HTTP response is lost to a timeout/connection error (ambiguous:
        the order may have actually reached Alpaca and been accepted), our own duplicate-
        position check only queries algo_trades/algo_positions - it can't see an order that
        never got recorded because we never received a response. Without client_order_id,
        retrying (e.g. Phase 8 reprocessing the same still-valid signal after a crash/restart)
        would submit a genuinely separate order at the broker. Alpaca rejects a resubmission
        that reuses a client_order_id already tied to an existing order for the account, so
        this makes such a retry safe even though our system has no record of the first
        attempt's outcome. algo_untracked_positions (see GOVERNANCE.md) is a different
        mechanism - it exists for manual/external trades placed outside the algo, not as a
        duplicate-order gate for algo-originated entries.
        """
        if not self.alpaca_key or not self.alpaca_secret:
            logger.error(f"[SEND_ORDER] {symbol}: Alpaca credentials not configured")
            return {"success": False, "message": "Alpaca credentials not configured"}

        # BUG FOUND 2026-08-10 (via fuzzing with pathological inputs): this function - the
        # ACTUAL real-order-to-the-broker submission path - had zero validation on
        # entry_price/shares, and the stop_loss_price check below didn't catch NaN (NaN
        # comparisons are always False in Python, so `stop_loss_price <= 0` silently passes
        # for NaN). A NaN/Infinite price would then flow into `_quantize_price()` below, which formats
        # via Decimal.quantize() - Decimal NaN doesn't raise, it silently produces the
        # literal string "NaN" - and that string would be sent to Alpaca as
        # order_data["stop_loss"]["stop_price"]/["limit_price"], a real order submission
        # with a garbage price field. Same bug class already found and fixed this session in
        # position_sizer.py, financial.py, phase8_entry_execution.py, and exit_engine.py -
        # this is the most consequential instance since it's the actual broker submission
        # call, not an internal calculation upstream of it.
        #
        # BUG FOUND 2026-08-11 (via a broader fuzz pass, same class): the isnan/isinf checks
        # above catch NaN/Infinity but not merely-huge finite values (e.g. 1e300, the kind of
        # number a unit-conversion or corrupted-upstream-data bug could plausibly produce).
        # `_q2()`'s `Decimal.quantize(Decimal("0.01"))` raises decimal.InvalidOperation (an
        # ArithmeticError, uncaught by this function's own try/except below) once the value
        # needs more significant digits than Decimal's default context precision (28) allows -
        # live-reproduced via fuzzing (28,561 combinations, 745 uncaught crashes, all at
        # magnitude >= 1e300). Added an explicit magnitude ceiling alongside the existing
        # finite check - no real equity price or share count is within many orders of
        # magnitude of $1M/share or 10M shares, so this only ever catches corrupted data,
        # never a real trade.
        max_abs_price = 1_000_000.0
        max_abs_shares = 10_000_000.0
        for label, value, ceiling in (
            ("entry_price", entry_price, max_abs_price),
            ("shares", shares, max_abs_shares),
        ):
            if (
                value is None
                or (isinstance(value, float) and (math.isnan(value) or math.isinf(value)))
                or value <= 0
                or abs(value) > ceiling
            ):
                error_msg = (
                    f"[SEND_ORDER CRITICAL] {symbol}: Cannot send bracket order with invalid {label}={value!r}. "
                    f"Must be a finite positive number no larger than {ceiling:,.0f}. "
                    f"Refusing to submit a real order with corrupted data."
                )
                logger.critical(error_msg)
                return {"success": False, "message": error_msg}

        # CRITICAL: Fail-fast if stop loss is missing or invalid - no fallback to naked positions
        if (
            stop_loss_price is None
            or (isinstance(stop_loss_price, float) and (math.isnan(stop_loss_price) or math.isinf(stop_loss_price)))
            or stop_loss_price <= 0
            or abs(stop_loss_price) > max_abs_price
        ):
            error_msg = (
                f"[SEND_ORDER CRITICAL] {symbol}: Cannot send bracket order without valid stop_loss_price. "
                f"Stop loss protection is non-negotiable for risk management. "
                f"Received: {stop_loss_price}. Entry price: {entry_price}. "
                f"Fail-fast to prevent naked positions (no stop-loss protection). "
                f"Check Phase 8 entry validation - stop price calculation must succeed before order submission."
            )
            logger.critical(error_msg)
            return {"success": False, "message": error_msg}

        # BUG FOUND 2026-08-11: take_profit_price was never validated at all. A NaN
        # take_profit_price doesn't crash (float NaN comparisons are always False, so
        # `take_profit_price > entry_price` below silently evaluates False) - but it's
        # silently DISCARDED and replaced with an internally-computed 1.5R fallback instead
        # of either using the caller's real intent or telling the caller their explicit
        # take_profit_price was invalid. A too-large finite value hits the same
        # decimal.InvalidOperation crash in `_q2()` as entry_price/stop_loss_price above.
        if take_profit_price is not None and (
            (isinstance(take_profit_price, float) and (math.isnan(take_profit_price) or math.isinf(take_profit_price)))
            or take_profit_price <= 0
            or abs(take_profit_price) > max_abs_price
        ):
            error_msg = (
                f"[SEND_ORDER CRITICAL] {symbol}: Cannot send bracket order with invalid "
                f"take_profit_price={take_profit_price!r}. Must be a finite positive number no larger "
                f"than {max_abs_price:,.0f}, or None to auto-calculate from the 1.5R fallback."
            )
            logger.critical(error_msg)
            return {"success": False, "message": error_msg}

        stop_desc = f"${stop_loss_price:.2f}"
        logger.info(
            f"[SEND_ORDER] {symbol}: Sending order - {shares}sh @ ${entry_price:.2f}, stop {stop_desc} to {self.alpaca_base_url}"
        )

        order_data = self._build_bracket_order_payload(
            symbol, shares, entry_price, stop_loss_price, take_profit_price, client_order_id
        )
        logger.debug(f"[SEND_ORDER] {symbol}: Payload = {order_data}")

        # RETRY (found 2026-07-28): this used to make exactly one attempt, unlike
        # _send_exit's 3-attempt loop for the same broker/endpoint - a transient Alpaca
        # 429 (rate limited) or 503 (unavailable) during entry submission was treated as a
        # permanent rejection, silently losing a real trading opportunity that a retry would
        # likely have recovered (audited via _log_signal_rejection downstream, but not
        # actually retried). 422 (unprocessable) is NOT retried - a validation error would
        # fail identically again - matching _send_exit's own distinction.
        max_attempts = 3
        last_error = "No attempts made"
        for attempt in range(max_attempts):
            try:
                response = requests.post(
                    f"{self.alpaca_base_url}/v2/orders",
                    json=order_data,
                    headers={
                        "APCA-API-KEY-ID": self.alpaca_key,
                        "APCA-API-SECRET-KEY": self.alpaca_secret,
                    },
                    timeout=get_api_timeout(),
                )
                logger.info(
                    f"[SEND_ORDER] {symbol}: Alpaca responded with HTTP {response.status_code} "
                    f"(attempt {attempt + 1}/{max_attempts})"
                )

                if response.status_code in (200, 201):
                    try:
                        data = response.json()
                    except (
                        requests.RequestException,
                        requests.Timeout,
                        json.JSONDecodeError,
                    ) as e:
                        logger.error(
                            f"[SEND_ORDER] {symbol}: Failed to parse response JSON: {e}. Response: {response.text}"
                        )
                        return {
                            "success": False,
                            "message": f"Invalid response format: {e}",
                        }

                    logger.debug(f"[SEND_ORDER] {symbol}: Response = {data}")
                    return self._entry_result_from_order_data(symbol, data)

                error_text = response.text[:500]
                logger.error(f"[SEND_ORDER] {symbol}: Alpaca {response.status_code} error")
                logger.error(f"[SEND_ORDER] {symbol}: Request payload: {json.dumps(order_data, indent=2)}")
                logger.error(f"[SEND_ORDER] {symbol}: Response: {error_text}")
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        logger.error(f"[SEND_ORDER] {symbol}: Error message: {error_data['message']}")
                except (json.JSONDecodeError, ValueError) as json_err:
                    logger.debug(f"[SEND_ORDER] {symbol}: Could not parse error response as JSON: {json_err}")

                last_error = f"Alpaca {response.status_code}: {error_text[:200]}"

                if response.status_code in (429, 503) and attempt < max_attempts - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"[SEND_ORDER] {symbol}: {last_error} - transient, retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{max_attempts})"
                    )
                    time.sleep(wait_time)
                    continue

                # Non-retryable status (or retries exhausted): before reporting failure, this
                # client_order_id may have been rejected because an EARLIER attempt already
                # succeeded at the broker (response lost to a timeout/crash, this call is a
                # crash-recovery retry - e.g. Phase 8 reprocessing the same still-valid signal -
                # see _lookup_order_by_client_order_id's docstring). Ground-truth check, not
                # error-text guessing: falls through to the original failure unchanged if no
                # such order actually exists.
                if client_order_id:
                    existing = self._lookup_order_by_client_order_id(client_order_id)
                    if existing:
                        return self._entry_result_from_order_data(symbol, existing)
                return {
                    "success": False,
                    "message": last_error,
                }
            except (requests.RequestException, requests.Timeout, json.JSONDecodeError) as e:
                last_error = f"Request failed: {e}"
                logger.warning(f"[SEND_ORDER] {symbol}: {last_error} (attempt {attempt + 1}/{max_attempts})")
                if attempt < max_attempts - 1:
                    time.sleep(1)

        # Every attempt failed with a network-level exception (no HTTP response ever
        # received) rather than a rejection Alpaca actually responded to - the case the
        # 422-rejection branch above already ground-truth-checks via client_order_id, but
        # this exhausted-retries path fell through without ever checking it. If attempt 1
        # actually reached Alpaca and created the order but the response itself was lost,
        # this is exactly the scenario client_order_id exists to make recoverable (see this
        # method's docstring) - check ground truth before reporting a false failure.
        if client_order_id:
            existing = self._lookup_order_by_client_order_id(client_order_id)
            if existing:
                return self._entry_result_from_order_data(symbol, existing)
        logger.error(f"[SEND_ORDER] {symbol}: Failed after {max_attempts} attempts: {last_error}")
        return {"success": False, "message": last_error}

    def cancel_bracket_orders(self, alpaca_order_id: str) -> dict[str, Any]:
        """Cancel bracket order and its children (stop loss + take profit).

        Returns: { success: bool, message: str, filled_qty: float | None,
                   filled_avg_price: float | None }

        filled_qty/filled_avg_price are populated whenever a post-cancel status check finds
        the order had ALREADY filled (fully or partially) by the time the cancel request
        reached the broker - see the FILL-VS-CANCEL RACE note below. None when the order
        genuinely had zero fill, or when the post-cancel check itself couldn't be completed
        (never block/crash cancellation cleanup on this best-effort check failing).
        """
        if not alpaca_order_id:
            return {"success": False, "message": "No order ID provided", "filled_qty": None, "filled_avg_price": None}

        if alpaca_order_id.startswith(("LOCAL-", "PENDING-")):
            return {
                "success": False,
                "message": "Paper mode, no Alpaca order to cancel (not a failure)",
                "filled_qty": None,
                "filled_avg_price": None,
            }

        if not self.alpaca_key or not self.alpaca_secret:
            return {
                "success": False,
                "message": "Cannot cancel order - Alpaca credentials missing",
                "filled_qty": None,
                "filled_avg_price": None,
            }

        # RETRY (found 2026-07-28, same class as send_bracket_order's fix): a single-attempt
        # transient 429/503 here used to be reported as a permanent cancel failure. Callers
        # only log a warning on failure (this is cleanup for an order we've already decided
        # not to treat as a real position, e.g. missing stop-loss leg or fill-wait timeout) -
        # a failed cancel leaves a real resting bracket order at the broker with no matching
        # DB record, exactly the orphaned-position class AlpacaSyncManager._sync_untracked_
        # positions exists to catch later, but retrying here means it usually never gets that far.
        max_attempts = 3
        last_error = "No attempts made"
        for attempt in range(max_attempts):
            try:
                resp = requests.delete(
                    f"{self.alpaca_base_url}/v2/orders/{alpaca_order_id}",
                    headers={
                        "APCA-API-KEY-ID": self.alpaca_key,
                        "APCA-API-SECRET-KEY": self.alpaca_secret,
                    },
                    timeout=get_api_timeout(),
                )
                if resp.status_code in (200, 204):
                    # FILL-VS-CANCEL RACE (found 2026-09-01, real-money-readiness sweep,
                    # order-retry fringe-case review): a 200/204 here only means the DELETE
                    # request was accepted - it does NOT guarantee zero shares filled. Alpaca
                    # cancels only the still-open remainder of a partially-filled order and
                    # still returns 200/204; the already-filled portion is real and stays
                    # filled. The prior version of this method returned bare success/failure
                    # with no fill info at all, so every caller (executor_entry_handler.py's
                    # timeout-cancel path) discarded that fill entirely - the exact same
                    # "invisible live position" bug class already fixed for wait_for_order_
                    # fill's own partially_filled/cancelled-with-fill branches, just reached
                    # via THIS cancel path instead of the polling loop. Check the order's real
                    # final state before declaring success - best-effort, never let a check
                    # failure here mask that the cancel itself DID succeed.
                    filled_qty, filled_avg_price = self._post_cancel_fill_check(alpaca_order_id)
                    return {
                        "success": True,
                        "message": f"Cancelled bracket order {alpaca_order_id}",
                        "filled_qty": filled_qty,
                        "filled_avg_price": filled_avg_price,
                    }

                if resp.status_code == 422:
                    # Alpaca returns 422 when the order is already in a terminal state (e.g.
                    # fully filled) and thus can no longer be cancelled - the FILL-VS-CANCEL
                    # RACE note above applies here even more directly: this is the exact
                    # signature of "the order finished filling before our cancel reached the
                    # broker." Check for a real fill before treating this as a bare failure.
                    filled_qty, filled_avg_price = self._post_cancel_fill_check(alpaca_order_id)
                    if filled_qty:
                        return {
                            "success": False,
                            "message": (
                                f"Order {alpaca_order_id} could not be cancelled (422 - already terminal) "
                                f"but filled {filled_qty} shares before the cancel raced past it"
                            ),
                            "filled_qty": filled_qty,
                            "filled_avg_price": filled_avg_price,
                        }

                last_error = f"Failed to cancel: {resp.status_code}"
                if resp.status_code in (429, 503) and attempt < max_attempts - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"[CANCEL_BRACKET] {alpaca_order_id}: {last_error} - transient, "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/{max_attempts})"
                    )
                    time.sleep(wait_time)
                    continue
                raise RuntimeError(f"[CANCEL_BRACKET] Failed to cancel order {alpaca_order_id}: {last_error}")
            except (requests.RequestException, requests.Timeout) as e:
                last_error = f"Error cancelling order: {e!s}"
                logger.warning(
                    f"[CANCEL_BRACKET] {alpaca_order_id}: {last_error} (attempt {attempt + 1}/{max_attempts})"
                )
                if attempt < max_attempts - 1:
                    time.sleep(1)

        raise RuntimeError(
            f"[CANCEL_BRACKET] Failed to cancel order {alpaca_order_id} after {max_attempts} attempts: {last_error}"
        )

    def _post_cancel_fill_check(self, alpaca_order_id: str) -> tuple[float | None, float | None]:
        """Best-effort check of an order's real filled_qty/filled_avg_price right after a
        cancel attempt - see cancel_bracket_orders' FILL-VS-CANCEL RACE note for why this
        exists. Never raises: a failure here must not mask whether the cancel itself
        succeeded, so any error just means "couldn't confirm, treat as no fill" - the
        existing AlpacaSyncManager._sync_untracked_positions safety net (Phase 9) still
        catches a genuinely-missed fill later, this is a best-effort earlier catch only.
        """
        try:
            order = self.get_order(alpaca_order_id)
        except (OrderExecutionError, RuntimeError, requests.RequestException, requests.Timeout) as e:
            logger.warning(
                f"[CANCEL_BRACKET] {alpaca_order_id}: post-cancel fill check failed ({e}) - "
                f"cannot confirm whether shares filled before the cancel. Relying on Phase 9's "
                f"untracked-position sync to catch this if a real fill was missed here."
            )
            return None, None
        if not order:
            return None, None
        try:
            filled_qty = float(order["filled_qty"]) if order.get("filled_qty") is not None else 0.0
        except (TypeError, ValueError):
            filled_qty = 0.0
        if filled_qty <= 0:
            return None, None
        filled_avg_price_raw = order.get("filled_avg_price")
        filled_avg_price = None
        if filled_avg_price_raw is not None:
            try:
                filled_avg_price = float(filled_avg_price_raw)
            except (TypeError, ValueError):
                filled_avg_price = None
        logger.warning(
            f"[CANCEL_BRACKET] {alpaca_order_id}: {filled_qty} shares filled @ "
            f"{filled_avg_price} before/during cancellation - NOT discarding this fill."
        )
        return filled_qty, filled_avg_price

    def get_order(self, alpaca_order_id: str) -> dict[str, Any] | None:
        """Fetch the full order object (including nested `legs`) from Alpaca.

        Used to discover the live child order id of a bracket's stop-loss leg -
        Alpaca's GET /v2/orders/{id} on the PARENT bracket order returns the
        current state of its `legs`, including whichever id is presently live
        (the leg's original submission-time id, or a later replacement's id if
        sync_bracket_stop_loss has already moved it once - see that method's
        docstring for why we never cache a leg id ourselves).

        Returns:
            dict: the order object as returned by Alpaca
            None: for paper mode orders (LOCAL-*/PENDING-* prefixes, no Alpaca record exists)

        Raises OrderExecutionError if unable to fetch after retries (live mode only).
        """
        if not self.alpaca_key or not self.alpaca_secret or not alpaca_order_id:
            raise RuntimeError("Cannot fetch order without credentials and order_id")

        if alpaca_order_id.startswith(("LOCAL-", "PENDING-")):
            logger.debug(f"[ORDER_MANAGER] Order {alpaca_order_id} is paper mode (no live Alpaca record)")
            return None

        max_attempts = 3
        last_error = "No attempts made"
        for attempt in range(max_attempts):
            try:
                resp = requests.get(
                    f"{self.alpaca_base_url}/v2/orders/{alpaca_order_id}",
                    headers={
                        "APCA-API-KEY-ID": self.alpaca_key,
                        "APCA-API-SECRET-KEY": self.alpaca_secret,
                    },
                    timeout=get_api_timeout(),
                )
                if resp.status_code == 200:
                    try:
                        data: dict[str, Any] = resp.json()
                    except (requests.RequestException, requests.Timeout, ValueError) as e:
                        raise RuntimeError(f"[GET_ORDER] Invalid JSON for order {alpaca_order_id}: {e}") from e
                    return data

                last_error = f"Failed to fetch order: {resp.status_code}"
                if resp.status_code in (429, 503) and attempt < max_attempts - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"[GET_ORDER] {alpaca_order_id}: {last_error} - transient, "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/{max_attempts})"
                    )
                    time.sleep(wait_time)
                    continue
                raise RuntimeError(f"[GET_ORDER] Failed to fetch order {alpaca_order_id}: {last_error}")
            except (requests.RequestException, requests.Timeout) as e:
                last_error = f"Error fetching order: {e!s}"
                logger.warning(f"[GET_ORDER] {alpaca_order_id}: {last_error} (attempt {attempt + 1}/{max_attempts})")
                if attempt < max_attempts - 1:
                    time.sleep(1)

        raise OrderExecutionError(
            f"[GET_ORDER] Unable to fetch order {alpaca_order_id} after {max_attempts} attempts: {last_error}"
        )

    def replace_order_stop_price(
        self, order_id: str, new_stop_price: float, new_qty: float | None = None
    ) -> dict[str, Any]:
        """PATCH /v2/orders/{order_id} to move a resting stop order's trigger price,
        optionally also resizing its quantity.

        new_qty matters because a PARTIAL exit (T1/T2/T3 profit-taking, or any other
        fraction<1 exit) sells shares via a SEPARATE order from the bracket's resting
        legs - it does not touch them. Left alone, a bracket's stop-loss/take-profit
        legs stay sized for the ORIGINAL full entry quantity forever, even after we
        hold far fewer shares. If the stale, oversized stop-loss leg ever fires, it
        would attempt to sell more shares than the account actually holds.

        Alpaca implements order replacement as cancel-and-recreate under the hood:
        a successful response is a NEW order object with a new id (the original is
        marked 'replaced'). Callers must not cache the returned id for reuse across
        future updates - always re-resolve the live leg via sync_bracket_stop_loss()
        on the next trail, which re-fetches the parent order fresh each time.
        """
        if not self.alpaca_key or not self.alpaca_secret:
            return {"success": False, "synced": False, "message": "Cannot replace order - Alpaca credentials missing"}

        body: dict[str, Any] = {"stop_price": _quantize_price(new_stop_price)}
        if new_qty is not None:
            body["qty"] = str(new_qty)

        max_attempts = 3
        last_error = "No attempts made"
        for attempt in range(max_attempts):
            try:
                resp = requests.patch(
                    f"{self.alpaca_base_url}/v2/orders/{order_id}",
                    headers={
                        "APCA-API-KEY-ID": self.alpaca_key,
                        "APCA-API-SECRET-KEY": self.alpaca_secret,
                        "Content-Type": "application/json",
                    },
                    data=json.dumps(body),
                    timeout=get_api_timeout(),
                )
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except (requests.RequestException, requests.Timeout, ValueError) as e:
                        return {
                            "success": False,
                            "synced": False,
                            "message": f"Replace order response is invalid JSON: {e}",
                        }
                    new_id = data.get("id")
                    return {
                        "success": True,
                        "synced": True,
                        "new_order_id": new_id,
                        "message": f"Stop-loss order {order_id} replaced, new stop_price={new_stop_price:.4f} (new order id {new_id})",
                    }

                last_error = f"Failed to replace order: {resp.status_code} {resp.text[:200]}"
                if resp.status_code in (429, 503) and attempt < max_attempts - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"[REPLACE_ORDER] {order_id}: {last_error} - transient, "
                        f"retrying in {wait_time}s (attempt {attempt + 1}/{max_attempts})"
                    )
                    time.sleep(wait_time)
                    continue
                return {"success": False, "synced": False, "message": last_error}
            except (requests.RequestException, requests.Timeout) as e:
                last_error = f"Error replacing order: {e!s}"
                logger.warning(f"[REPLACE_ORDER] {order_id}: {last_error} (attempt {attempt + 1}/{max_attempts})")
                if attempt < max_attempts - 1:
                    time.sleep(1)

        return {
            "success": False,
            "synced": False,
            "message": f"Failed to replace order {order_id} after {max_attempts} attempts: {last_error}",
        }

    def sync_bracket_stop_loss(
        self, parent_alpaca_order_id: str | None, new_stop_price: float, new_qty: float | None = None
    ) -> dict[str, Any]:
        """Push a trailed/raised stop-loss (and, on a partial exit, a corrected
        quantity) to the live resting broker order.

        This is the fix for a real gap: exit_engine.py computes an improved stop
        (breakeven move at T1, chandelier ATR trail, etc.) and persists it to
        algo_positions.current_stop_price - but the bracket order's stop-loss leg,
        submitted once at entry (send_bracket_order), otherwise keeps resting at the
        broker at its ORIGINAL price forever. Nothing previously pushed a trailed
        stop back to Alpaca, so the "trail" was purely a belief in our own database:
        the position was only really protected at the wider, stale entry-time level
        between orchestrator runs, not at the level we thought we'd raised it to.

        new_qty (optional) keeps the leg's size correct after a partial exit -
        executor_exit_handler.py._execute_exit() sells partial shares via a SEPARATE
        order and never touched the bracket's legs before this fix, so a stop-loss
        leg left at the original full quantity could try to sell more shares than
        the account actually holds if it ever fires. Pass the current remaining
        share count any time you call this after a fill may have changed it -
        _raise_stop_only also passes it now so a partial exit's stale qty gets
        corrected the next time a stop is simply raised, not just at the moment of
        the partial exit itself.

        Deliberately not implemented as an Alpaca-native `trailing_stop` order type:
        our stop logic isn't a fixed trail percent/dollar amount - it jumps to
        breakeven at T1, trails 3xATR (chandelier) or 21-EMA after that, per
        exit_engine.py's documented exit hierarchy. A native trailing_stop order
        can't express that, so we keep our own computation and push it to a plain
        stop order via replace instead.

        Returns success=True, synced=False (not an error) when there's no live
        broker order to sync - paper-mode LOCAL-/PENDING- orders, or a position
        with no alpaca_order_id at all (e.g. manually imported) - callers should
        still proceed with their own DB update in that case, same as every other
        broker-optional path in this class.
        """
        if not parent_alpaca_order_id or parent_alpaca_order_id.startswith(("LOCAL-", "PENDING-")):
            return {"success": True, "synced": False, "message": "No live Alpaca order to sync (paper/local mode)"}

        order = self.get_order(parent_alpaca_order_id)
        if order is None:
            return {"success": True, "synced": False, "message": "No live Alpaca order to sync (paper/local mode)"}

        legs = order.get("legs") or []
        stop_leg = _find_live_stop_loss_leg(legs)
        if stop_leg is None:
            return {
                "success": False,
                "synced": False,
                "message": (
                    f"No live stop-loss leg found on order {parent_alpaca_order_id} - "
                    f"leg statuses: {[(leg.get('order_type'), leg.get('status')) for leg in legs if isinstance(leg, dict)]}. "
                    "Position may already be closing at the broker."
                ),
            }

        stop_leg_id = stop_leg.get("id")
        if not stop_leg_id:
            return {"success": False, "synced": False, "message": "Stop-loss leg missing order id"}

        return self.replace_order_stop_price(stop_leg_id, new_stop_price, new_qty=new_qty)

    def check_stop_loss_leg_live(self, parent_alpaca_order_id: str | None) -> dict[str, Any]:
        """Read-only check: does this bracket order currently have a live stop-loss leg
        resting at the broker?

        Unlike sync_bracket_stop_loss, this NEVER writes/replaces anything - it exists so
        a periodic reconciliation pass (see phase9_reconciliation.py's stop-loss protection
        check) can verify protection still exists WITHOUT the side effect of an
        unconditional cancel-and-recreate replace on every cycle (Alpaca implements order
        replacement that way - calling sync_bracket_stop_loss just to "check" would briefly
        leave the position naked between the cancel and the recreate, every single check).

        Returns:
            {"checked": False, "has_live_stop_loss": None, ...} - nothing to verify against
                a broker: paper/local mode order, or the order can no longer be found. Not
                itself evidence of a protection gap.
            {"checked": True, "has_live_stop_loss": bool, "message": str} - a real bracket
                order was fetched and its legs inspected.
        """
        if not parent_alpaca_order_id or parent_alpaca_order_id.startswith(("LOCAL-", "PENDING-")):
            return {
                "checked": False,
                "has_live_stop_loss": None,
                "message": "No live Alpaca order to check (paper/local mode)",
            }

        order = self.get_order(parent_alpaca_order_id)
        if order is None:
            return {
                "checked": False,
                "has_live_stop_loss": None,
                "message": "No live Alpaca order to check (paper/local mode)",
            }

        legs = order.get("legs") or []
        stop_leg = _find_live_stop_loss_leg(legs)
        if stop_leg is None:
            return {
                "checked": True,
                "has_live_stop_loss": False,
                "message": (
                    f"No live stop-loss leg on order {parent_alpaca_order_id} - "
                    f"leg statuses: {[(leg.get('order_type'), leg.get('status')) for leg in legs if isinstance(leg, dict)]}"
                ),
            }
        return {"checked": True, "has_live_stop_loss": True, "message": "stop-loss leg live"}

    def get_order_fill_price(self, alpaca_order_id: str) -> float | None:
        """Query Alpaca for actual fill price of an order.

        Returns:
            float: Actual fill price if order status is 'filled'
            None: ONLY for paper mode orders (LOCAL-*/PENDING-* prefixes)

        Raises RuntimeError if:
            - Alpaca API unavailable or returns error
            - Response validation fails
            - Order status cannot be determined
            - Order has terminal status (cancelled, rejected, expired)

        Note: For in-flight orders (status: pending/accepted), returns None only
        for paper mode. Live broker orders that are pending will raise RuntimeError
        if they lack proper status - they must have a valid status or this is an error.
        """
        if not self.alpaca_key or not self.alpaca_secret:
            raise RuntimeError("Alpaca credentials not configured")
        if not alpaca_order_id:
            raise ValueError("alpaca_order_id required")

        if alpaca_order_id.startswith(("LOCAL-", "PENDING-")):
            logger.debug(f"[ORDER_MANAGER] Order {alpaca_order_id} is paper mode (no live Alpaca record)")
            return None

        try:
            resp = requests.get(
                f"{self.alpaca_base_url}/v2/orders/{alpaca_order_id}",
                headers={
                    "APCA-API-KEY-ID": self.alpaca_key,
                    "APCA-API-SECRET-KEY": self.alpaca_secret,
                },
                timeout=get_api_timeout(),
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except (requests.RequestException, requests.Timeout) as parse_err:
                    raise RuntimeError(f"Operation failed: {parse_err}") from parse_err

                validation = validator.validate_order_status_response(data)
                if not validation["valid"]:
                    error_msg = (
                        f"[GET_ORDER_PRICE] {alpaca_order_id}: Invalid response from Alpaca: {validation['errors']}"
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

                status = validation["status"]
                if status == "filled":
                    return cast(float, validation["filled_avg_price"])
                elif status in ("pending", "pending_new", "accepted"):
                    logger.debug(
                        f"Order {alpaca_order_id} still in flight (status={status}). "
                        f"Fill price unavailable until order fills."
                    )
                    raise RuntimeError(
                        f"Order {alpaca_order_id} has pending status '{status}' - "
                        f"not yet filled. Caller must wait/retry or track via order event stream."
                    )
                else:
                    raise RuntimeError(
                        f"Order {alpaca_order_id} has terminal status '{status}' (likely cancelled/rejected/expired) - "
                        f"fill price unavailable (order will not fill)."
                    )
            else:
                raise RuntimeError(f"Alpaca API returned {resp.status_code} for order {alpaca_order_id}")
        except (requests.RequestException, requests.Timeout) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def get_order_filled_quantity(self, alpaca_order_id: str) -> float | None:
        """Query Alpaca for actual filled quantity of an order.

        Includes retry logic with exponential backoff for transient failures.

        Returns:
            int: filled_qty from Alpaca for live orders
            None: for paper mode orders (LOCAL-*/PENDING-* prefixes, no Alpaca record exists)

        Raises OrderExecutionError if Alpaca API unreachable after retries (live mode only).
        """
        if not self.alpaca_key or not self.alpaca_secret:
            raise RuntimeError("Alpaca credentials not configured")
        if not alpaca_order_id:
            raise ValueError("alpaca_order_id required")

        if alpaca_order_id.startswith(("LOCAL-", "PENDING-")):
            logger.debug(f"[ORDER_MANAGER] Order {alpaca_order_id} is paper mode (no live Alpaca record)")
            return None

        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = requests.get(
                    f"{self.alpaca_base_url}/v2/orders/{alpaca_order_id}",
                    headers={
                        "APCA-API-KEY-ID": self.alpaca_key,
                        "APCA-API-SECRET-KEY": self.alpaca_secret,
                    },
                    timeout=get_api_timeout(),
                )
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except (requests.RequestException, requests.Timeout) as e:
                        raise RuntimeError(f"Operation failed: {e}") from e
                    filled_qty = data["filled_qty"] if "filled_qty" in data else None
                    if filled_qty is None:
                        logger.error(
                            f"[ORDER_MANAGER] Alpaca response missing 'filled_qty' for order {alpaca_order_id}"
                        )
                        raise ValueError(f"Order {alpaca_order_id}: Alpaca response missing filled_qty (required)")
                    # Alpaca returns filled_qty as a STRING to preserve precision (e.g. "4.87"
                    # for a fractional-share fill - this system actively trades fractional
                    # shares, confirmed via real open positions). int("4.87") raises
                    # ValueError uncaught by this function's retry loop (which only catches
                    # requests exceptions), crashing entry/exit fill verification for any
                    # fractionally-filled order. The function's own declared return type is
                    # `float | None`, not int.
                    return float(filled_qty)
                else:
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        time.sleep(wait_time)
            except (requests.RequestException, requests.Timeout) as e:
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"Failed to get filled quantity for {alpaca_order_id} after {max_retries} attempts: {e}"
                    )
        raise OrderExecutionError(
            f"Unable to verify filled quantity for order {alpaca_order_id} after {max_retries} retries. "
            "Alpaca API unreachable. Cannot proceed without order fill confirmation."
        )

    def verify_order_status(self, alpaca_order_id: str) -> str | None:
        """Re-query order status from Alpaca with retry logic.

        Returns:
            str: order status string ('filled', 'partially_filled', 'pending', 'cancelled', etc.)
            None: for paper mode orders (LOCAL-*/PENDING-* prefixes, no Alpaca record exists)

        Raises OrderExecutionError if unable to verify status after retries (live mode only).
        """
        if not self.alpaca_key or not self.alpaca_secret or not alpaca_order_id:
            raise RuntimeError("Cannot verify order status without credentials and order_id")

        if alpaca_order_id.startswith(("LOCAL-", "PENDING-")):
            logger.debug(f"[ORDER_MANAGER] Order {alpaca_order_id} is paper mode (no live Alpaca record)")
            return None

        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = requests.get(
                    f"{self.alpaca_base_url}/v2/orders/{alpaca_order_id}",
                    headers={
                        "APCA-API-KEY-ID": self.alpaca_key,
                        "APCA-API-SECRET-KEY": self.alpaca_secret,
                    },
                    timeout=get_api_timeout(),
                )
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except (requests.RequestException, requests.Timeout) as e:
                        error_msg = f"Order status response is invalid JSON for {alpaca_order_id}: {e}. Response text: {resp.text[:200]}"
                        logger.error(error_msg)
                        raise ValueError(error_msg) from e
                    status = data.get("status")
                    if status is None:
                        logger.error(f"[ORDER_MANAGER] Alpaca response missing 'status' for order {alpaca_order_id}")
                        raise ValueError(f"Order {alpaca_order_id}: Alpaca response missing status field (required)")
                    return cast(str, status)
                else:
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.debug(f"Retrying order status query ({attempt + 1}/{max_retries}) after {wait_time}s...")
                        time.sleep(wait_time)
            except (requests.RequestException, requests.Timeout) as e:
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.debug(f"Retrying order status query ({attempt + 1}/{max_retries}) after {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"Failed to verify order status for {alpaca_order_id} after {max_retries} attempts: {e}"
                    )
        raise OrderExecutionError(
            f"Unable to verify order status for {alpaca_order_id} after {max_retries} retries. "
            "Alpaca API unreachable. Cannot proceed without status confirmation."
        )

    def _lookup_order_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        """Look up an order by the client_order_id we submitted it with.

        Used after a non-200/201 submission response to distinguish two cases that both
        surface as "the POST failed": (1) the order never reached Alpaca at all (genuine
        validation failure - bad qty, invalid symbol, etc.), vs (2) client_order_id was
        rejected as a duplicate of an order Alpaca already has on file - which happens
        specifically when a crash/timeout lost the response to an EARLIER submission that
        actually succeeded, and this call is a crash-recovery retry reusing the same id
        (see send_bracket_order/send_market_exit docstrings). Rather than pattern-matching
        Alpaca's rejection error text/code for "duplicate", this checks ground truth: does
        an order with this client_order_id actually exist at the broker? If yes, that
        order's real status is authoritative - the original attempt succeeded. If no (404),
        the rejection was genuine and the caller's existing failure handling is correct.

        VERIFIED 2026-08-10 against Alpaca's official API reference (docs.alpaca.markets):
        POST /v2/orders only documents 200/403/422 responses and does not document a
        specific status for a duplicate client_order_id - but that's a non-issue here by
        design, since the caller (send_bracket_order/send_market_exit) falls through to
        this ground-truth check on ANY non-429/503 response, not a specific code. What
        actually matters is THIS lookup being correct, and it is: GET
        /v2/orders:by_client_order_id (URL/method/query-param below) and its 200 response's
        Order-object schema (confirmed fields include id/status/filled_qty/filled_avg_price)
        both match Alpaca's official reference docs exactly.

        Returns: the order dict if found, None if not found.

        Raises:
            RuntimeError: On authentication or infrastructure failures that prevent lookup
            (Recoverable/inconclusive errors still return None to allow caller's fallback)
        """
        if not self.alpaca_key or not self.alpaca_secret or not client_order_id:
            return None
        try:
            resp = requests.get(
                f"{self.alpaca_base_url}/v2/orders:by_client_order_id",
                params={"client_order_id": client_order_id},
                headers={
                    "APCA-API-KEY-ID": self.alpaca_key,
                    "APCA-API-SECRET-KEY": self.alpaca_secret,
                },
                timeout=get_api_timeout(),
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and data.get("id"):
                    logger.warning(
                        f"[ORDER_LOOKUP] client_order_id={client_order_id}: rejected on resubmission "
                        f"but an order already exists at the broker (id={data['id']}, "
                        f"status={data.get('status')}) - treating the earlier attempt as the real "
                        f"outcome instead of reporting this resubmission as a failure."
                    )
                    return data
                return None
            if resp.status_code == 404:
                # Order not found - this is expected for genuine rejections
                return None
            if resp.status_code == 401:
                # Authentication failure - this is a critical infrastructure issue
                raise RuntimeError(
                    f"[ORDER_LOOKUP] Authentication failed for {client_order_id}: HTTP 401. "
                    f"Alpaca API credentials invalid or expired."
                )
            if resp.status_code >= 500:
                # Server errors - infrastructure problems
                raise RuntimeError(
                    f"[ORDER_LOOKUP] Alpaca API server error for {client_order_id}: HTTP {resp.status_code}"
                )
            # Other HTTP errors - inconclusive, let caller fall back
            logger.debug(
                f"[ORDER_LOOKUP] client_order_id={client_order_id}: lookup returned "
                f"HTTP {resp.status_code}, treating as inconclusive"
            )
            return None
        except (requests.Timeout, requests.ConnectionError) as e:
            # Network problems - could be transient, let caller fall back
            logger.debug(f"[ORDER_LOOKUP] client_order_id={client_order_id}: network error during lookup: {e}")
            return None
        except ValueError as e:
            # JSON parsing error - inconclusive
            logger.debug(f"[ORDER_LOOKUP] client_order_id={client_order_id}: response parse error: {e}")
            return None

    def wait_for_order_fill(
        self, symbol: str, alpaca_order_id: str, max_wait_seconds: int = 30
    ) -> tuple[bool, float | None, str]:
        """Wait for Alpaca order to fill.

        CRITICAL: Do not write trade to DB until this confirms the order is filled.

        Args:
            symbol: Stock symbol
            alpaca_order_id: Order ID returned from send_bracket_order
            max_wait_seconds: Max time to wait for fill (paper mode is instant)

        Returns:
            (success: bool, filled_price: float | None, error_message: str)
            - success=True, filled_price=<price>: Order filled, record to DB
            - success=False, filled_price=None, error_message=<reason>: Order failed/timeout

        For paper mode (LOCAL-/PENDING- prefixes), returns immediately with success.
        """
        if alpaca_order_id.startswith(("LOCAL-", "PENDING-")):
            logger.info(f"[ORDER_FILL_WAIT] {symbol} {alpaca_order_id}: Paper mode - instant fill")
            return (True, None, "")

        if not self.alpaca_key or not self.alpaca_secret:
            return (False, None, "Alpaca credentials not configured")

        start_time = time.time()
        poll_interval = 0.5  # 500ms between polls
        attempt = 0

        while time.time() - start_time < max_wait_seconds:
            attempt += 1
            try:
                resp = requests.get(
                    f"{self.alpaca_base_url}/v2/orders/{alpaca_order_id}",
                    headers={
                        "APCA-API-KEY-ID": self.alpaca_key,
                        "APCA-API-SECRET-KEY": self.alpaca_secret,
                    },
                    timeout=get_api_timeout(),
                )

                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status")

                    if status in ("filled", "partially_filled"):
                        # BUG FOUND 2026-08-11 (via adversarial fuzzing of order state
                        # transitions): "partially_filled" used to fall through to the
                        # `else: "Unknown order status"` branch below, returning
                        # (False, None, ...) - the exact same "order did not fill, do NOT
                        # write to DB" contract as a genuine rejection. But a partial fill
                        # means REAL shares were already bought at the broker - the caller
                        # (executor_entry_handler.py's _submit_entry_phase) would then cancel
                        # the remaining bracket and never write a trade/position record for
                        # the shares that DID fill, the same "invisible live position" bug
                        # class as the accepted-but-unfilled bug fixed earlier today
                        # (9ab154003) and the dead notify() bug (263137d81) - just reached via
                        # a different order state. _record_entry_phase downstream already
                        # correctly handles order_status="partially_filled" via
                        # _get_order_filled_quantity() to get the real filled qty - treating
                        # it as a success here (like "filled") lets that existing, correct
                        # downstream reconciliation actually run instead of never being
                        # reached.
                        #
                        # CRITICAL: filled/partially_filled status MUST include filled_avg_price
                        if "filled_avg_price" not in data or data["filled_avg_price"] is None:
                            error_msg = (
                                f"[ORDER_FILL_WAIT] {symbol} {alpaca_order_id}: Order status={status} but "
                                f"filled_avg_price missing or NULL in Alpaca response. Cannot record fill price. "
                                f"Response keys: {list(data.keys())}"
                            )
                            logger.error(error_msg)
                            raise RuntimeError(error_msg)
                        # BUG FOUND 2026-08-11 (via the same fuzzing pass): Alpaca's real API
                        # returns filled_avg_price as a JSON string (confirmed by
                        # utils/validation/alpaca.py's AlpacaResponseValidator, which already
                        # explicitly float()-converts this exact field with its own
                        # try/except) - but this f-string used the raw, still-string value
                        # directly with `:.2f` formatting, which raises an unhandled
                        # `ValueError: Unknown format code 'f' for object of type 'str'`
                        # immediately on every real fill confirmation. Not caught by this
                        # loop's own except clause (only catches requests exceptions), so it
                        # would propagate all the way out of wait_for_order_fill() uncaught -
                        # a successful order fill would crash the entry pipeline instead of
                        # being recorded. Cast to float BEFORE first use, not just in the
                        # return statement below.
                        filled_price = float(data["filled_avg_price"])
                        elapsed = time.time() - start_time
                        logger.info(
                            f"[ORDER_FILL_WAIT] {symbol} {alpaca_order_id}: {status.upper()} @ ${filled_price:.2f} "
                            f"after {elapsed:.1f}s ({attempt} polls)"
                        )
                        return (True, filled_price, "")

                    elif status in ("cancelled", "rejected", "expired"):
                        # BUG FOUND 2026-09-01 (real-money-readiness sweep, partial-fill
                        # lifecycle audit): a terminal cancel/expire status can still carry a
                        # nonzero filled_qty - Alpaca moves a partially-filled day order
                        # straight to "canceled"/"expired" (not "partially_filled", which is a
                        # still-open state) once no further fill is possible, e.g. a TIF expiry
                        # or a manual cancel-remaining after a partial fill. filled_qty still
                        # reflects what DID fill at the broker. This branch used to report
                        # unconditional failure for ANY terminal status, discarding that
                        # filled_qty entirely - the exact same "invisible live position" bug
                        # class as the partially_filled-fell-through-to-unknown-status bug
                        # fixed above (2026-08-11), just reached via a cancel/expire status
                        # instead of a stuck "unknown status". Real shares bought before the
                        # cancellation would never get an algo_trades/algo_positions row.
                        filled_qty_raw = data.get("filled_qty")
                        try:
                            filled_qty_on_terminal = float(filled_qty_raw) if filled_qty_raw is not None else 0.0
                        except (TypeError, ValueError):
                            filled_qty_on_terminal = 0.0
                        if filled_qty_on_terminal > 0:
                            if "filled_avg_price" not in data or data["filled_avg_price"] is None:
                                error_msg = (
                                    f"[ORDER_FILL_WAIT] {symbol} {alpaca_order_id}: status={status} with "
                                    f"filled_qty={filled_qty_on_terminal} but filled_avg_price missing or "
                                    f"NULL. Cannot record partial fill price."
                                )
                                logger.error(error_msg)
                                raise RuntimeError(error_msg)
                            filled_price = float(data["filled_avg_price"])
                            logger.warning(
                                f"[ORDER_FILL_WAIT] {symbol} {alpaca_order_id}: status={status} but "
                                f"filled_qty={filled_qty_on_terminal} > 0 - broker filled part of the "
                                f"order before cancelling/expiring the remainder. Treating as a partial "
                                f"fill, not a total failure, so the shares that DID fill get recorded."
                            )
                            return (True, filled_price, "")
                        # Alpaca doesn't guarantee 'cancel_reason' is present for every terminal
                        # status (utils/validation/alpaca.py's own validator already falls back
                        # through cancel_reason -> failed_reason -> reason for this exact reason).
                        # A bare data["cancel_reason"] subscript would raise an uncaught KeyError
                        # here instead of returning the documented (False, None, error_message)
                        # tuple, turning a normal order rejection into an unhandled crash.
                        reason = (
                            data.get("cancel_reason")
                            or data.get("failed_reason")
                            or data.get("reason")
                            or "no reason provided"
                        )
                        error_msg = f"Order {status}: {reason}"
                        logger.error(f"[ORDER_FILL_WAIT] {symbol} {alpaca_order_id}: {error_msg}")
                        return (False, None, error_msg)

                    elif status in ("pending", "pending_new", "accepted", "new"):
                        # Still waiting
                        logger.debug(
                            f"[ORDER_FILL_WAIT] {symbol} {alpaca_order_id}: status={status} (attempt {attempt})"
                        )
                        time.sleep(poll_interval)
                        continue

                    else:
                        error_msg = f"Unknown order status: {status}"
                        logger.error(f"[ORDER_FILL_WAIT] {symbol} {alpaca_order_id}: {error_msg}")
                        return (False, None, error_msg)

                else:
                    logger.warning(
                        f"[ORDER_FILL_WAIT] {symbol} {alpaca_order_id}: HTTP {resp.status_code} "
                        f"(attempt {attempt}), retrying..."
                    )
                    time.sleep(poll_interval)
                    continue

            except (requests.RequestException, requests.Timeout) as e:
                logger.warning(f"[ORDER_FILL_WAIT] {symbol} {alpaca_order_id}: API error (attempt {attempt}): {e}")
                time.sleep(poll_interval)
                continue

        elapsed = time.time() - start_time
        error_msg = f"Order fill timeout after {elapsed:.1f}s ({attempt} polls). Order may still fill asynchronously."
        logger.error(f"[ORDER_FILL_WAIT] {symbol} {alpaca_order_id}: {error_msg}")
        return (False, None, error_msg)

    def _exit_result_from_order_data(self, symbol: str, data: dict[str, Any]) -> dict[str, Any]:
        """Interpret an Alpaca order object into send_market_exit's result shape.

        Shared by the normal 200/201 submission response and by the duplicate-
        client_order_id recovery path (_lookup_order_by_client_order_id) - both hand this
        method the same Alpaca order object schema, just fetched via different requests.
        """
        order_id = data.get("id")
        if not order_id:
            logger.error(f"[SEND_EXIT] {symbol}: Alpaca response missing order id")
            return {
                "success": False,
                "message": "Alpaca response missing order id",
            }
        if "status" not in data:
            logger.error("[ORDER_MANAGER] Alpaca order response missing 'status' field")
            raise ValueError("Order status missing from Alpaca response")
        order_status = data["status"]

        if "filled_avg_price" not in data:
            logger.error(
                f"[SEND_EXIT] {symbol}: Alpaca order response missing 'filled_avg_price' field. "
                f"This field should always be present (even if NULL for pending orders). "
                f"Response keys present: {list(data.keys())}. "
                f"Cannot proceed without knowing if fill price was returned."
            )
            raise ValueError("Alpaca order response missing 'filled_avg_price' field - API contract violation")

        filled_price_raw = data["filled_avg_price"]
        if filled_price_raw is None:
            logger.info(
                f"[SEND_EXIT] {symbol}: Exit order {order_id} submitted (status={order_status}), "
                f"fill price pending (will be reconciled)"
            )
            return {
                "success": True,
                "order_id": order_id,
                "filled_price": None,
                "message": f"Order submitted, fill pending: {order_id}",
            }
        try:
            filled_price = float(filled_price_raw)
        except (ValueError, TypeError) as e:
            logger.error(f"[SEND_EXIT] {symbol}: filled_avg_price not numeric: {e}")
            return {
                "success": False,
                "message": f"filled_avg_price not numeric: {e}",
            }
        logger.info(f"[SEND_EXIT] {symbol}: Exit order {order_id} filled at ${filled_price}")
        return {
            "success": True,
            "order_id": order_id,
            "filled_price": filled_price,
            "message": f"Order filled: {order_id}",
        }

    def _try_close_position_fallback(self, symbol: str) -> dict[str, Any] | None:
        """Close a position via Alpaca's /v2/positions/{symbol} DELETE endpoint.

        Used by send_market_exit's 403 "insufficient qty" handling when all shares are held
        by open orders (e.g. an existing bracket) - the close-position endpoint bypasses that
        hold. Returns a result dict on any definitive outcome (filled, pending-fill, or a
        response missing a required field), or None if the endpoint itself returned a non-2xx
        status - the caller falls through to its normal retry/last_error handling in that case.
        """
        close_resp = requests.delete(
            f"{self.alpaca_base_url}/v2/positions/{symbol}",
            headers={
                "APCA-API-KEY-ID": self.alpaca_key,
                "APCA-API-SECRET-KEY": self.alpaca_secret,
            },
            timeout=get_api_timeout(),
        )
        if close_resp.status_code not in (200, 201):
            logger.warning(
                f"[SEND_EXIT] {symbol}: Close-position endpoint returned "
                f"{close_resp.status_code}: {close_resp.text[:500]}"
            )
            return None

        close_data = close_resp.json()
        # CRITICAL: close-position response MUST include 'filled_avg_price' field
        if "filled_avg_price" not in close_data:
            logger.error(
                f"[SEND_EXIT] {symbol}: Alpaca close-position response missing 'filled_avg_price' field. "
                f"Cannot determine if position was filled. "
                f"Response keys: {list(close_data.keys())}"
            )
            raise ValueError("Close-position response missing filled_avg_price field")
        filled_price_raw = close_data["filled_avg_price"]
        if filled_price_raw is not None:
            try:
                filled_price = float(filled_price_raw)
                order_id = close_data.get("id")
                if not order_id:
                    logger.error(
                        f"[SEND_EXIT] {symbol}: Alpaca close-position response missing required 'id' field. "
                        f"Cannot track order without ID. Response: {close_data}"
                    )
                    return {
                        "success": False,
                        "order_id": None,
                        "filled_price": None,
                        "message": "Alpaca close-position missing order id",
                    }
                logger.info(f"[SEND_EXIT] {symbol}: Close-position succeeded, fill=${filled_price} (order {order_id})")
                return {
                    "success": True,
                    "order_id": order_id,
                    "filled_price": filled_price,
                    "message": f"Closed via position endpoint: {order_id}",
                }
            except (ValueError, TypeError) as e:
                logger.error(
                    f"[SEND_EXIT] {symbol}: Failed to parse filled_price ({filled_price_raw}). "
                    f"Error: {type(e).__name__}: {e}. Retrying..."
                )
        # Order placed but price not yet filled (market order in flight)
        order_id = close_data.get("id")
        if not order_id:
            logger.error(
                f"[SEND_EXIT] {symbol}: Alpaca close-position response missing required 'id' field. "
                f"Cannot track order without ID. Response: {close_data}"
            )
            return {
                "success": False,
                "order_id": None,
                "filled_price": None,
                "message": "Alpaca close-position missing order id",
            }
        logger.info(
            f"[SEND_EXIT] {symbol}: Close-position order {order_id} submitted, fill price pending (market order)"
        )
        return {
            "success": True,
            "order_id": order_id,
            "filled_price": None,
            "message": f"Close-position order submitted: {order_id}",
        }

    def _handle_insufficient_qty(
        self, symbol: str, resp: requests.Response, shares: float, attempt: int, max_attempts: int
    ) -> tuple[str, Any]:
        """Handle Alpaca's 403 "insufficient qty available" response for send_market_exit.

        Two cases:
          1. DB qty != Alpaca qty (e.g. fractional fill not reconciled): retry with actual qty
          2. Shares locked by open bracket order: use close-position endpoint to bypass

        Returns ("retry", new_shares) to retry the same attempt with a corrected share count,
        ("return", result_dict) to return that dict immediately from send_market_exit, or
        ("fallthrough", None) when neither case applies - the caller falls through to its
        normal last_error/retry handling.
        """
        try:
            err_data = resp.json()
            available_str = err_data.get("available")
            if available_str is not None and attempt == 0:
                available_qty = float(available_str)
                if 0 < available_qty < shares:
                    # Case 1: partial availability - retry with actual qty
                    logger.warning(
                        f"[SEND_EXIT] {symbol}: DB qty={shares} but Alpaca available={available_qty}. "
                        f"Retrying with actual available qty (position out-of-sync)."
                    )
                    return ("retry", available_qty)
                if "held_for_orders" not in err_data:
                    raise RuntimeError(
                        f"[SEND_EXIT] {symbol}: Alpaca reported insufficient shares "
                        f"but error response missing 'held_for_orders' field. "
                        f"Cannot determine how many shares are held by open orders. "
                        f"Response: {err_data}"
                    )
                held = float(err_data["held_for_orders"])
                if available_qty == 0 and held > 0 and attempt < max_attempts - 1:
                    # Case 2: all shares locked by open orders - use close-position endpoint
                    logger.warning(
                        f"[SEND_EXIT] {symbol}: All {held} shares locked by open orders. "
                        f"Using close-position endpoint to override existing bracket."
                    )
                    fallback_result = self._try_close_position_fallback(symbol)
                    if fallback_result is not None:
                        return ("return", fallback_result)
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error(f"[SEND_EXIT] {symbol}: Failed to parse response. Error: {type(e).__name__}: {e}. Retrying...")
        return ("fallthrough", None)

    def send_market_exit(
        self,
        symbol: str,
        shares: float,
        execution_mode: str,
        client_order_id: str | None = None,
        limit_price: float | None = None,
    ) -> dict[str, Any]:
        """Send an exit (sell) order to Alpaca - market, or marketable limit when limit_price is given.

        Returns { success, order_id, filled_price }.
        Never returns None - always returns dict with success/error fields.

        client_order_id: Passed through to Alpaca on every retry attempt within this call, as
        broker-side idempotency protection - same reasoning as send_bracket_order's
        client_order_id (see its docstring). Without this, a timeout/connection error on
        attempt 1 whose response never arrived (order may have actually reached Alpaca) would
        let attempt 2 submit a genuinely separate market sell order for the same intent - a
        real double-sell, not just a duplicate no-op. Caller must generate ONE id per call to
        this method (stable across this call's own retry loop) - NOT a single id reused across
        separate calls/days, since unlike entries, one trade can have multiple legitimate
        partial exits over its lifetime; a key stable forever per trade_id would cause Alpaca
        to reject a later, genuinely different partial exit as a duplicate of an earlier one.

        limit_price: When provided (non-urgent exits - see executor.py's _send_alpaca_exit),
        submits a single "day" limit order at this price instead of a market order. The caller
        is responsible for computing an aggressive/marketable price (a small buffer through the
        current bid) - this method does not adjust the price further. Deliberately a single
        order at a fixed price, not a limit-then-market-fallback sequence: that would need a
        second client_order_id for the fallback leg, which the crash-recovery machinery above
        (keyed on exactly one id per exit attempt, persisted before submission) isn't designed
        for. If the limit doesn't fill (rare - only when price gaps past the buffer), the
        position stays open and gets re-evaluated on the next exit-engine pass; the existing
        403/"held_for_orders" handling below already treats a still-resting order on this
        symbol as normal (falls back to the close-position endpoint), so this doesn't introduce
        a new stuck-order failure mode. None (the default) preserves the original unconditional
        market-order behavior exactly - hard stop-loss exits always call this with limit_price
        omitted, since certainty of exit outweighs price control for capital preservation.
        """
        if execution_mode in ("paper", "dry", "review"):
            logger.info(f"[SEND_EXIT] {symbol}: Paper mode exit - {shares}sh")
            return {
                "success": True,
                "order_id": f"PAPER-{uuid.uuid4().hex[:10].upper()}",
                "filled_price": None,
                "message": f"Paper mode: {shares}sh sell order",
            }

        if not self.alpaca_key or not self.alpaca_secret:
            logger.error(f"[SEND_EXIT] {symbol}: Alpaca credentials not configured")
            return {
                "success": False,
                "order_id": None,
                "filled_price": None,
                "message": "Alpaca credentials not configured",
            }

        # BUG FOUND 2026-09-01 (/goal session, real-money-readiness sweep): unlike
        # send_bracket_order() above - the entry path, hardened via a 28,561-combination
        # fuzz pass that found 745 uncaught crashes at magnitude >= 1e300 - this exit path
        # had zero validation on `shares` itself before it goes straight into
        # order_data["qty"] and gets POSTed to Alpaca as a real sell order. shares_to_exit
        # is computed upstream in executor_exit_handler.py's _calculate_exit_shares() via
        # Decimal(str(current_qty)) * Decimal(str(exit_fraction)) - if either input were
        # ever NaN/Infinite/corrupted, that arithmetic's behavior isn't the kind of thing to
        # reason about by hand (Decimal NaN propagation/InvalidOperation semantics differ
        # from float's), and "probably fine" was exactly the wrong call on the entry side
        # until it was actually fuzzed. Cheap, same-shape guard at the literal broker-
        # submission boundary regardless of what upstream corruption might look like.
        max_abs_shares = 10_000_000.0
        if (
            shares is None
            or (isinstance(shares, float) and (math.isnan(shares) or math.isinf(shares)))
            or shares <= 0
            or abs(shares) > max_abs_shares
        ):
            error_msg = (
                f"[SEND_EXIT CRITICAL] {symbol}: Cannot send exit order with invalid shares={shares!r}. "
                f"Must be a finite positive number no larger than {max_abs_shares:,.0f}. "
                f"Refusing to submit a real order with corrupted data."
            )
            logger.critical(error_msg)
            return {
                "success": False,
                "order_id": None,
                "filled_price": None,
                "message": error_msg,
            }

        # Same NaN/Infinity/non-positive guard discipline as _build_bracket_order_payload's
        # caller (position_sizer.py etc.) - a corrupted limit_price must fall back to a plain
        # market order, not flow into _quantize_price() and produce a garbage order field.
        use_limit = limit_price is not None and math.isfinite(limit_price) and limit_price > 0
        if limit_price is not None and not use_limit:
            logger.error(
                f"[SEND_EXIT] {symbol}: limit_price={limit_price!r} is not a valid finite positive "
                "price - falling back to a market order for this exit."
            )

        logger.info(
            f"[SEND_EXIT] {symbol}: Sending exit order - {shares}sh "
            + (f"limit sell @ ${limit_price:.4f}" if use_limit else "market sell")
        )

        max_attempts = 3
        last_error = None
        for attempt in range(max_attempts):
            try:
                order_data: dict[str, Any] = {
                    "symbol": symbol,
                    "qty": shares,
                    "side": "sell",
                    "type": "limit" if use_limit else "market",
                    "time_in_force": "day",
                }
                if use_limit:
                    order_data["limit_price"] = _quantize_price(cast(float, limit_price))
                if client_order_id:
                    order_data["client_order_id"] = client_order_id
                resp = requests.post(
                    f"{self.alpaca_base_url}/v2/orders",
                    json=order_data,
                    headers={
                        "APCA-API-KEY-ID": self.alpaca_key,
                        "APCA-API-SECRET-KEY": self.alpaca_secret,
                    },
                    timeout=get_api_timeout(),
                )
                logger.info(
                    f"[SEND_EXIT] {symbol}: Alpaca responded with status {resp.status_code} (attempt {attempt + 1})"
                )
                if resp.status_code in (200, 201):
                    try:
                        data = resp.json()
                    except (requests.RequestException, requests.Timeout) as e:
                        logger.error(f"[SEND_EXIT] {symbol}: Failed to parse exit response JSON: {e}")
                        return {
                            "success": False,
                            "message": f"Invalid response format: {e}",
                        }
                    return self._exit_result_from_order_data(symbol, data)
                elif resp.status_code == 422:
                    logger.error(f"[SEND_EXIT] {symbol}: Alpaca 422 (unprocessable) - {resp.text[:200]}")
                    # Before reporting failure: this client_order_id may have been rejected
                    # because an EARLIER attempt already succeeded at the broker (the response
                    # was lost to a timeout/crash, and this call is the crash-recovery retry -
                    # see _lookup_order_by_client_order_id's docstring). Ground-truth check,
                    # not error-text guessing: falls through to the original failure unchanged
                    # if no such order actually exists.
                    if client_order_id:
                        existing = self._lookup_order_by_client_order_id(client_order_id)
                        if existing:
                            return self._exit_result_from_order_data(symbol, existing)
                    return {
                        "success": False,
                        "order_id": None,
                        "filled_price": None,
                        "message": f"Alpaca 422 unprocessable: {resp.text[:200]}",
                    }
                elif resp.status_code == 403:
                    action, payload = self._handle_insufficient_qty(symbol, resp, shares, attempt, max_attempts)
                    if action == "retry":
                        shares = cast(float, payload)
                        continue
                    if action == "return":
                        return cast(dict[str, Any], payload)
                    last_error = f"Alpaca {resp.status_code}: {resp.text[:200]}"
                    logger.warning(f"[SEND_EXIT] {symbol}: {last_error} (attempt {attempt + 1}/{max_attempts})")
                else:
                    last_error = f"Alpaca {resp.status_code}: {resp.text[:200]}"
                    logger.warning(f"[SEND_EXIT] {symbol}: {last_error} (attempt {attempt + 1}/{max_attempts})")
            except (
                requests.RequestException,
                requests.Timeout,
                json.JSONDecodeError,
            ) as e:
                last_error = f"Error: {e!s}"
                logger.warning(f"[SEND_EXIT] {symbol}: {last_error} (attempt {attempt + 1}/{max_attempts})")
                if attempt < max_attempts - 1:
                    time.sleep(1)

        # Same gap as send_bracket_order's identical fix: every attempt failed with a
        # network-level exception (no HTTP response ever received), so the 422-rejection
        # branch's ground-truth client_order_id lookup above never ran. Check it here too -
        # if attempt 1 actually reached Alpaca and sold the position but the response was
        # lost, this is exactly the double-sell this method's docstring says client_order_id
        # exists to prevent; reporting a false failure risks a caller retrying the sell fresh.
        if client_order_id:
            existing = self._lookup_order_by_client_order_id(client_order_id)
            if existing:
                return self._exit_result_from_order_data(symbol, existing)
        logger.error(f"[SEND_EXIT] {symbol}: Failed after {max_attempts} attempts: {last_error}")
        return {
            "success": False,
            "order_id": None,
            "filled_price": None,
            "message": last_error,
        }

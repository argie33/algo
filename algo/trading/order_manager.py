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
import time
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

import requests

from algo.infrastructure import get_api_timeout
from algo.trading.exceptions import OrderExecutionError
from utils.validation import AlpacaResponseValidator

logger = logging.getLogger(__name__)
validator = AlpacaResponseValidator()


class OrderManager:
    """Manage order lifecycle via Alpaca API."""

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
        Caller passes a deterministic idempotency_key (hash of symbol/signal_date/entry_price/
        stop_loss_price), NOT the random per-attempt trade_id - the value must be the same
        across separate attempts at the same underlying trade intent for this to work.
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

        # CRITICAL: Fail-fast if stop loss is missing or invalid - no fallback to naked positions
        if stop_loss_price is None or stop_loss_price <= 0:
            error_msg = (
                f"[SEND_ORDER CRITICAL] {symbol}: Cannot send bracket order without valid stop_loss_price. "
                f"Stop loss protection is non-negotiable for risk management. "
                f"Received: {stop_loss_price}. Entry price: {entry_price}. "
                f"Fail-fast to prevent naked positions (no stop-loss protection). "
                f"Check Phase 8 entry validation - stop price calculation must succeed before order submission."
            )
            logger.critical(error_msg)
            return {"success": False, "message": error_msg}

        stop_desc = f"${stop_loss_price:.2f}"
        logger.info(
            f"[SEND_ORDER] {symbol}: Sending order - {shares}sh @ ${entry_price:.2f}, stop {stop_desc} to {self.alpaca_base_url}"
        )

        # CRITICAL: use Decimal.quantize(ROUND_HALF_UP), not Python's built-in round(), for every
        # price submitted to the broker. round() operates on binary float representation and uses
        # round-half-to-even - the classic round(2.675, 2) == 2.67 trap (2.675 isn't exactly
        # representable in binary float) can silently submit an order 1 cent off the intended
        # price. The take_profit fallback two blocks below already used Decimal correctly; the
        # entry limit_price/stop_price literally two lines above it did not. Fixed 2026-07-21 for
        # consistency with position_sizer.py/executor_entry_handler.py, which are Decimal-only.
        def _q2(v: float) -> str:
            return str(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        # CRITICAL: Always build a bracket order - stop loss protection is mandatory
        order_data = {
            "symbol": symbol,
            "qty": shares,
            "side": "buy",
            "type": "limit",
            "time_in_force": "day",
            "limit_price": _q2(entry_price),
            "extended_hours": False,
            "order_class": "bracket",
            "stop_loss": {
                "stop_price": _q2(stop_loss_price),
            },
        }
        if client_order_id:
            order_data["client_order_id"] = client_order_id

        # Add take-profit target (either explicit or computed from 1.5R)
        if take_profit_price is not None and take_profit_price > entry_price:
            order_data["take_profit"] = {
                "limit_price": _q2(take_profit_price),
            }
        else:
            risk_dec = Decimal(str(entry_price)) - Decimal(str(stop_loss_price))
            if risk_dec > 0:
                tp_dec = Decimal(str(entry_price)) + (Decimal("1.5") * risk_dec)
                order_data["take_profit"] = {
                    "limit_price": str(tp_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                }

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

        logger.error(f"[SEND_ORDER] {symbol}: Failed after {max_attempts} attempts: {last_error}")
        return {"success": False, "message": last_error}

    def cancel_bracket_orders(self, alpaca_order_id: str) -> dict[str, Any]:
        """Cancel bracket order and its children (stop loss + take profit).

        Returns: { success: bool, message: str }
        """
        if not alpaca_order_id:
            return {"success": False, "message": "No order ID provided"}

        if alpaca_order_id.startswith(("LOCAL-", "PENDING-")):
            return {"success": False, "message": "Paper mode, no Alpaca order to cancel (not a failure)"}

        if not self.alpaca_key or not self.alpaca_secret:
            return {"success": False, "message": "Cannot cancel order - Alpaca credentials missing"}

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
                    return {
                        "success": True,
                        "message": f"Cancelled bracket order {alpaca_order_id}",
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

        raise RuntimeError(f"[CANCEL_BRACKET] Failed to cancel order {alpaca_order_id} after {max_attempts} attempts: {last_error}")

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
            logger.debug(
                f"[ORDER_LOOKUP] client_order_id={client_order_id}: network error during lookup: {e}"
            )
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

                    if status == "filled":
                        # CRITICAL: filled status MUST include filled_avg_price - this is the fill price
                        if "filled_avg_price" not in data or data["filled_avg_price"] is None:
                            error_msg = (
                                f"[ORDER_FILL_WAIT] {symbol} {alpaca_order_id}: Order status=filled but "
                                f"filled_avg_price missing or NULL in Alpaca response. Cannot record fill price. "
                                f"Response keys: {list(data.keys())}"
                            )
                            logger.error(error_msg)
                            raise RuntimeError(error_msg)
                        filled_price = data["filled_avg_price"]
                        elapsed = time.time() - start_time
                        logger.info(
                            f"[ORDER_FILL_WAIT] {symbol} {alpaca_order_id}: FILLED @ ${filled_price:.2f} "
                            f"after {elapsed:.1f}s ({attempt} polls)"
                        )
                        return (True, float(filled_price), "")

                    elif status in ("cancelled", "rejected", "expired"):
                        # Alpaca doesn't guarantee 'cancel_reason' is present for every terminal
                        # status (utils/validation/alpaca.py's own validator already falls back
                        # through cancel_reason -> failed_reason -> reason for this exact reason).
                        # A bare data["cancel_reason"] subscript would raise an uncaught KeyError
                        # here instead of returning the documented (False, None, error_message)
                        # tuple, turning a normal order rejection into an unhandled crash.
                        reason = data.get("cancel_reason") or data.get("failed_reason") or data.get("reason") or "no reason provided"
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

    def send_market_exit(
        self, symbol: str, shares: float, execution_mode: str, client_order_id: str | None = None
    ) -> dict[str, Any]:  # noqa: C901
        """Send a market sell order to Alpaca.

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

        logger.info(f"[SEND_EXIT] {symbol}: Sending exit order - {shares}sh market sell")

        max_attempts = 3
        last_error = None
        for attempt in range(max_attempts):
            try:
                order_data: dict[str, Any] = {
                    "symbol": symbol,
                    "qty": shares,
                    "side": "sell",
                    "type": "market",
                    "time_in_force": "day",
                }
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
                    # Alpaca 403 "insufficient qty available" - two cases:
                    # 1. DB qty != Alpaca qty (e.g. fractional fill not reconciled): retry with actual qty
                    # 2. Shares locked by open bracket order: use close-position endpoint to bypass
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
                                shares = available_qty
                                continue
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
                                close_resp = requests.delete(
                                    f"{self.alpaca_base_url}/v2/positions/{symbol}",
                                    headers={
                                        "APCA-API-KEY-ID": self.alpaca_key,
                                        "APCA-API-SECRET-KEY": self.alpaca_secret,
                                    },
                                    timeout=get_api_timeout(),
                                )
                                if close_resp.status_code in (200, 201):
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
                                            logger.info(
                                                f"[SEND_EXIT] {symbol}: Close-position succeeded, "
                                                f"fill=${filled_price} (order {order_id})"
                                            )
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
                                        f"[SEND_EXIT] {symbol}: Close-position order {order_id} submitted, "
                                        f"fill price pending (market order)"
                                    )
                                    return {
                                        "success": True,
                                        "order_id": order_id,
                                        "filled_price": None,
                                        "message": f"Close-position order submitted: {order_id}",
                                    }
                                else:
                                    logger.warning(
                                        f"[SEND_EXIT] {symbol}: Close-position endpoint returned "
                                        f"{close_resp.status_code}: {close_resp.text[:500]}"
                                    )
                    except (ValueError, TypeError, json.JSONDecodeError) as e:
                        logger.error(
                            f"[SEND_EXIT] {symbol}: Failed to parse response. "
                            f"Error: {type(e).__name__}: {e}. Retrying..."
                        )
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

        logger.error(f"[SEND_EXIT] {symbol}: Failed after {max_attempts} attempts: {last_error}")
        return {
            "success": False,
            "order_id": None,
            "filled_price": None,
            "message": last_error,
        }

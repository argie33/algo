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

    def __init__(self, alpaca_key: str, alpaca_secret: str, alpaca_base_url: str) -> None:
        self.alpaca_key = alpaca_key
        self.alpaca_secret = alpaca_secret
        self.alpaca_base_url = alpaca_base_url

    def send_bracket_order(
        self,
        symbol: str,
        shares: float,
        entry_price: float,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
    ) -> dict[str, Any]:
        """Send a BRACKET order to Alpaca — entry + stop loss + take profit.

        This is the institutional best practice: even if our system goes down,
        Alpaca enforces the stop loss and take profit. No naked positions.

        Bracket order: parent buy fills, then OCO (one-cancels-other) of:
          - Stop loss order (executes if price drops to stop)
          - Take profit limit order (executes if price hits target)

        Falls back to simple limit order if bracket can't be sent (no stop).
        Never returns None — always returns dict with success/error fields.
        """
        if not self.alpaca_key or not self.alpaca_secret:
            logger.error(f"[SEND_ORDER] {symbol}: Alpaca credentials not configured")
            return {"success": False, "message": "Alpaca credentials not configured"}

        logger.info(
            f"[SEND_ORDER] {symbol}: Sending order - {shares}sh @ ${entry_price:.2f}, stop ${stop_loss_price:.2f} to {self.alpaca_base_url}"
        )
        try:
            order_data = {
                "symbol": symbol,
                "qty": shares,
                "side": "buy",
                "type": "limit",
                "time_in_force": "day",
                "limit_price": str(round(entry_price, 2)),
                "extended_hours": False,
            }

            if stop_loss_price is not None and stop_loss_price > 0:
                order_data["order_class"] = "bracket"
                order_data["stop_loss"] = {
                    "stop_price": str(round(stop_loss_price, 2)),
                }
                if take_profit_price is not None and take_profit_price > entry_price:
                    order_data["take_profit"] = {
                        "limit_price": str(round(take_profit_price, 2)),
                    }
                else:
                    risk_dec = Decimal(str(entry_price)) - Decimal(str(stop_loss_price))
                    if risk_dec > 0:
                        tp_dec = Decimal(str(entry_price)) + (Decimal("1.5") * risk_dec)
                        tp = float(tp_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                        order_data["take_profit"] = {
                            "limit_price": str(round(tp, 2)),
                        }

            logger.debug(f"[SEND_ORDER] {symbol}: Payload = {order_data}")

            response = requests.post(
                f"{self.alpaca_base_url}/v2/orders",
                json=order_data,
                headers={
                    "APCA-API-KEY-ID": self.alpaca_key,
                    "APCA-API-SECRET-KEY": self.alpaca_secret,
                },
                timeout=get_api_timeout(),
            )
            logger.info(f"[SEND_ORDER] {symbol}: Alpaca responded with HTTP {response.status_code}")

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
            else:
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
                return {
                    "success": False,
                    "message": f"Alpaca {response.status_code}: {error_text[:200]}",
                }
        except (requests.RequestException, requests.Timeout, json.JSONDecodeError) as e:
            logger.exception(f"[SEND_ORDER] {symbol}: Exception during request: {e}")
            return {"success": False, "message": f"Request failed: {e}"}

    def cancel_bracket_orders(self, alpaca_order_id: str) -> dict[str, Any]:
        """Cancel bracket order and its children (stop loss + take profit).

        Returns: { success: bool, message: str }
        """
        if not self.alpaca_key or not self.alpaca_secret or not alpaca_order_id:
            return {"success": True, "message": "No order to cancel"}

        if alpaca_order_id.startswith(("LOCAL-", "PENDING-")):
            return {"success": True, "message": "Paper mode, no Alpaca order to cancel"}

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
            else:
                return {
                    "success": False,
                    "message": f"Failed to cancel: {resp.status_code}",
                }
        except (requests.RequestException, requests.Timeout) as e:
            return {"success": False, "message": f"Error cancelling order: {e!s}"}

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
        if they lack proper status — they must have a valid status or this is an error.
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
                        f"Order {alpaca_order_id} has pending status '{status}' — "
                        f"not yet filled. Caller must wait/retry or track via order event stream."
                    )
                else:
                    raise RuntimeError(
                        f"Order {alpaca_order_id} has terminal status '{status}' (likely cancelled/rejected/expired) — "
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
                    filled_qty = data.get("filled_qty")
                    if filled_qty is None:
                        logger.error(
                            f"[ORDER_MANAGER] Alpaca response missing 'filled_qty' for order {alpaca_order_id}"
                        )
                        raise ValueError(f"Order {alpaca_order_id}: Alpaca response missing filled_qty (required)")
                    return int(filled_qty)
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

    def send_market_exit(self, symbol: str, shares: float, execution_mode: str) -> dict[str, Any]:
        """Send a market sell order to Alpaca.

        Returns { success, order_id, filled_price }.
        Never returns None — always returns dict with success/error fields.
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
                resp = requests.post(
                    f"{self.alpaca_base_url}/v2/orders",
                    json={
                        "symbol": symbol,
                        "qty": shares,
                        "side": "sell",
                        "type": "market",
                        "time_in_force": "day",
                    },
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
                    order_id = data.get("id")
                    # Issue #13: filled_avg_price is required — no silent None
                    if not order_id:
                        logger.error(f"[SEND_EXIT] {symbol}: Alpaca response missing order id")
                        return {
                            "success": False,
                            "message": "Alpaca response missing order id",
                        }
                    filled_price_raw = data.get("filled_avg_price")
                    order_status = data.get("status", "")
                    if not filled_price_raw:
                        # Market orders return null filled_avg_price when status is "new" or "pending_new"
                        # — the fill comes asynchronously. Treat as success with pending fill price;
                        # Phase 9 reconciliation will poll for the actual fill price.
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
                elif resp.status_code == 422:
                    logger.error(f"[SEND_EXIT] {symbol}: Alpaca 422 (unprocessable) - {resp.text[:200]}")
                    return {
                        "success": False,
                        "order_id": None,
                        "filled_price": None,
                        "message": f"Alpaca 422 unprocessable: {resp.text[:200]}",
                    }
                elif resp.status_code == 403:
                    # Alpaca 403 "insufficient qty available" — two cases:
                    # 1. DB qty != Alpaca qty (e.g. fractional fill not reconciled): retry with actual qty
                    # 2. Shares locked by open bracket order: use close-position endpoint to bypass
                    try:
                        err_data = resp.json()
                        available_str = err_data.get("available")
                        if available_str is not None and attempt == 0:
                            available_qty = float(available_str)
                            if 0 < available_qty < shares:
                                # Case 1: partial availability — retry with actual qty
                                logger.warning(
                                    f"[SEND_EXIT] {symbol}: DB qty={shares} but Alpaca available={available_qty}. "
                                    f"Retrying with actual available qty (position out-of-sync)."
                                )
                                shares = available_qty
                                continue
                            held = float(err_data.get("held_for_orders", 0) or 0)
                            if available_qty == 0 and held > 0 and attempt < max_attempts - 1:
                                # Case 2: all shares locked by open orders — use close-position endpoint
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
                                    filled_price_raw = close_data.get("filled_avg_price")
                                    if filled_price_raw:
                                        try:
                                            filled_price = float(filled_price_raw)
                                            order_id = close_data.get("id", "close-position")
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
                                        except (ValueError, TypeError):
                                            pass
                                    # Order placed but price not yet filled (market order in flight)
                                    order_id = close_data.get("id", "close-position")
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
                                        f"{close_resp.status_code}: {close_resp.text[:100]}"
                                    )
                    except (ValueError, TypeError, json.JSONDecodeError):
                        pass
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

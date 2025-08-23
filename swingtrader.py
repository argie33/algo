#!/usr/bin/env python3
"""
Alpaca paper-trading order placer.
Reads PAPER API credentials and order parameters from environment,
submits a single order, logs response, then exits.
"""

import logging
import os
import sys

from alpaca_trade_api.rest import REST, APIError

# ─── Configuration via ENV ──────────────────────────────────────────────────
ALPACA_PAPER_API_KEY = os.getenv("ALPACA_PAPER_API_KEY")
ALPACA_PAPER_SECRET_KEY = os.getenv("ALPACA_PAPER_SECRET_KEY")
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"  # fixed to paper

SYMBOL = os.getenv("ALPACA_SYMBOL", "AAPL")
ACTION = os.getenv("ALPACA_ACTION", "buy").lower()  # "buy" or "sell"
QUANTITY = int(os.getenv("ALPACA_QUANTITY", "1"))
ORDER_TYPE = os.getenv("ALPACA_ORDER_TYPE", "market").lower()  # "market" or "limit"
LIMIT_PRICE = os.getenv("ALPACA_LIMIT_PRICE")  # required if limit order
TIME_IN_FORCE = os.getenv("ALPACA_TIME_IN_FORCE", "day")  # "day", "gtc", etc.

# ─── Logging setup ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def validate_env():
    missing = []
    if not ALPACA_PAPER_API_KEY:
        missing.append("ALPACA_PAPER_API_KEY")
    if not ALPACA_PAPER_SECRET_KEY:
        missing.append("ALPACA_PAPER_SECRET_KEY")
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)


def build_order_params():
    params = dict(
        symbol=SYMBOL,
        qty=QUANTITY,
        side=ACTION,
        type=ORDER_TYPE,
        time_in_force=TIME_IN_FORCE,
    )
    if ORDER_TYPE == "limit":
        if not LIMIT_PRICE:
            logger.error("LIMIT_PRICE must be set for limit orders")
            sys.exit(1)
        params["limit_price"] = float(LIMIT_PRICE)
    return params


def main():
    validate_env()
    logger.info(f"Connecting to Alpaca PAPER at {ALPACA_BASE_URL!r}…")

    api = REST(
        key_id=ALPACA_PAPER_API_KEY,
        secret_key=ALPACA_PAPER_SECRET_KEY,
        base_url=ALPACA_BASE_URL,
        api_version="v2",
    )

    order_params = build_order_params()
    logger.info(f"Placing order: {order_params}")
    try:
        order = api.submit_order(**order_params)
    except APIError as e:
        logger.error(f"APIError placing order: {e}")
        sys.exit(1)

    logger.info(f"[ORDER SUBMITTED] id={order.id} status={order.status}")
    logger.info(
        f"Filled qty: {order.filled_qty}, remaining: {float(order.qty) - float(order.filled_qty)}"
    )
    logger.info(f"Submitted at: {order.submitted_at}")

    # Fetch and print full order details
    full = api.get_order(order.id)
    logger.info(f"[ORDER DETAILS] {full}")


if __name__ == "__main__":
    main()

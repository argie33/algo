#!/usr/bin/env python3
"""
Alpaca paper-trading (mock) order placer.
Reads API credentials and order parameters from environment,
submits a single order, logs response, then exits.
"""

import os
import sys
import logging
from alpaca_trade_api.rest import REST, TimeFrame, APIError

# ─── Configuration via ENV ──────────────────────────────────────────────────
ALPACA_API_KEY     = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY  = os.getenv("ALPACA_SECRET_KEY")
# default to Alpaca paper trading URL
ALPACA_BASE_URL    = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

SYMBOL             = os.getenv("ALPACA_SYMBOL", "AAPL")
ACTION             = os.getenv("ALPACA_ACTION", "buy").lower()   # "buy" or "sell"
QUANTITY           = int(os.getenv("ALPACA_QUANTITY", "1"))
ORDER_TYPE         = os.getenv("ALPACA_ORDER_TYPE", "market").lower()  # "market" or "limit"
LIMIT_PRICE        = os.getenv("ALPACA_LIMIT_PRICE")  # required if limit order
TIME_IN_FORCE      = os.getenv("ALPACA_TIME_IN_FORCE", "day")  # "day", "gtc", etc.

# ─── Logging setup ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def validate_env():
    missing = []
    for var in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
        if not globals().get(var):
            missing.append(var)
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
    logger.info(f"Connecting to Alpaca at {ALPACA_BASE_URL!r} using key {ALPACA_API_KEY[:4]}...")

    api = REST(
        key_id=ALPACA_API_KEY,
        secret_key=ALPACA_SECRET_KEY,
        base_url=ALPACA_BASE_URL,
        api_version='v2'
    )

    order_params = build_order_params()
    logger.info(f"Placing order: {order_params}")
    try:
        order = api.submit_order(**order_params)
    except APIError as e:
        logger.error(f"APIError placing order: {e}")
        sys.exit(1)

    logger.info(f"[ORDER SUBMITTED] id={order.id} status={order.status}")
    logger.info(f"Filled qty: {order.filled_qty}, remaining: {order.qty - float(order.filled_qty)}")
    logger.info(f"Submitted at: {order.submitted_at}")

    # Optionally, fetch and print full order details
    full = api.get_order(order.id)
    logger.info(f"[ORDER DETAILS] {full}")

if __name__ == "__main__":
    main()

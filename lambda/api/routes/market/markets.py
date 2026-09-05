"""Handler for /api/market/indices (market index quotes and history).

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import db_route_handler, json_response, raise_api_error

from algo.infrastructure.config.sql_intervals import get_interval_sql
from utils.market_symbols_config import MarketSymbolsConfig

logger = logging.getLogger(__name__)


def _get_index_symbols() -> list[str]:
    symbols: list[str] = MarketSymbolsConfig.get_index_symbols()
    return symbols


def _get_index_names() -> dict[str, str]:
    names: dict[str, str] = MarketSymbolsConfig.get_index_names()
    return names


@db_route_handler("get market indices")
def _get_markets(cur: cursor) -> Any:
    index_symbols = _get_index_symbols()
    cur.execute(
        """
        WITH latest_date AS (
            SELECT date AS d FROM price_daily WHERE symbol = ANY(%s) ORDER BY date DESC LIMIT 1
        ),
        prev_date AS (
            SELECT date AS d FROM price_daily
            WHERE symbol = ANY(%s)
                  AND date < (SELECT d FROM latest_date)
            ORDER BY date DESC LIMIT 1
        ),
        today AS (
            SELECT symbol, date, close
            FROM price_daily
            WHERE symbol = ANY(%s)
                  AND date = (SELECT d FROM latest_date)
        ),
        yesterday AS (
            SELECT symbol, close AS prev_close
            FROM price_daily
            WHERE symbol = ANY(%s)
                  AND date = (SELECT d FROM prev_date)
        )
        SELECT t.symbol, t.date, t.close,
                   COALESCE(y.prev_close, t.close) AS prev_close,
                   (y.prev_close IS NULL) AS _is_fallback
        FROM today t
        LEFT JOIN yesterday y ON t.symbol = y.symbol
        ORDER BY t.symbol
    """,
        (index_symbols, index_symbols, index_symbols, index_symbols),
    )
    latest = cur.fetchall()

    interval_90d = get_interval_sql("90d")
    cur.execute(
        f"""
        SELECT symbol, date, close
        FROM price_daily
        WHERE symbol = ANY(%s)
              AND date >= CURRENT_DATE - {interval_90d}
        ORDER BY symbol, date DESC
    """,
        (index_symbols,),
    )
    history_rows = cur.fetchall()

    history: dict[str, list[Any]] = {}
    for row in history_rows:
        sym = row["symbol"]
        if sym not in history:
            history[sym] = []
        # Validate price data exists before adding to history
        if row["close"] is None or row["close"] <= 0:
            logger.warning(f"[MARKET_INDICES] Skipping {sym} on {row['date']}: invalid close price {row['close']}")
            continue
        if row["date"] is None:
            logger.error(f"[MARKET_INDICES] Missing date for {sym}: cannot add to history without date")
            raise ValueError(f"[MARKET_INDICES] {sym} history record missing required date field")
        history[sym].append(
            {
                "date": str(row["date"]),
                "close": float(row["close"]),
            }
        )

    indices = []
    stale_alerts = []

    for row in latest:
        if "symbol" not in row or row["symbol"] is None:
            raise ValueError(
                "[MARKET_API_INDICES_INCOMPLETE] Index row missing required 'symbol' field. "
                f"Cannot process index data without symbol. Row keys: {list(row.keys())}"
            )
        symbol = row["symbol"]

        if row["close"] is None or row["close"] <= 0:
            logger.warning(f"Market API indices: Invalid close price for {symbol}: {row['close']}; skipping")
            continue
        price = float(row["close"])
        if row["prev_close"] is None or row["prev_close"] <= 0:
            logger.warning(
                f"Market API indices: Invalid prev_close for {symbol}: {row['prev_close']}; cannot calculate change"
            )
            continue
        prev_price = float(row["prev_close"])
        change = price - prev_price
        change_pct = change / prev_price * 100

        # Fail-fast on fallback prices: if today's quote is missing during market hours, raise 503
        if "_is_fallback" not in row:
            raise ValueError(
                f"[MARKET_API_FALLBACK_MISSING] Index {symbol} row missing '_is_fallback' indicator. "
                f"Cannot determine if price is fresh or fallback. Check data source. "
                f"Row keys: {list(row.keys())}"
            )
        is_fallback = bool(row["_is_fallback"])
        if is_fallback:
            raise_api_error(503, "stale_data", f"Index {symbol} price unavailable (today's quote missing)")

        # Check data age and add to stale alerts
        if row.get("date"):
            row_date = row["date"]
            if isinstance(row_date, str):
                from datetime import datetime

                row_date = datetime.fromisoformat(row_date).date()
            data_age = (date.today() - row_date).days
            if data_age > 1:
                stale_alerts.append(f"{row['symbol']} {data_age}d old")

        index_names = _get_index_names()
        indices.append(
            {
                "symbol": row["symbol"],
                "name": index_names.get(row["symbol"], row["symbol"]),
                "date": str(row["date"]),
                "price": round(price, 2),
                "change": round(change, 2),
                "changePercent": round(change_pct, 2),
                "pe": None,
            }
        )

    if not indices:
        raise_api_error(503, "no_data", "No valid index price data available for latest market indices")

    result = {
        "indices": indices,
        "history": history,
        "stale_alerts": stale_alerts,
    }
    return json_response(200, result)

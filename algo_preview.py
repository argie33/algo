#!/usr/bin/env python3
"""
Algo Trade Preview — Returns a JSON trade preview for a given symbol, entry, and stop.

Usage:
    python3 algo_preview.py SYMBOL ENTRY_PRICE STOP_LOSS_PRICE

Output (stdout):
    {"symbol": "AAPL", "entry_price": 195.0, "stop_loss": 187.0, ...}
"""

import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = Path(__file__).parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass

from credential_helper import get_db_password


def get_db_conn():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=get_db_password(),
        database=os.getenv("DB_NAME", "stocks"),
    )


def preview(symbol: str, entry_price: float, stop_loss: float) -> dict:
    risk_pct = round((entry_price - stop_loss) / entry_price * 100, 2)
    r1_target = round(entry_price + (entry_price - stop_loss), 2)
    r2_target = round(entry_price + 2 * (entry_price - stop_loss), 2)
    position_size_pct = round(min(1.0 / max(risk_pct, 0.5) * 100, 25), 1)

    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    ss.composite_score,
                    ss.momentum_score,
                    ss.quality_score,
                    ss.value_score,
                    cp.sector,
                    cp.industry,
                    COALESCE(cp.short_name, cp.display_name, cp.long_name) AS company_name
                FROM stock_scores ss
                LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
                WHERE ss.symbol = %s
                LIMIT 1
            """, (symbol,))
            row = cur.fetchone()

            cur.execute("""
                SELECT close
                FROM price_daily
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 1
            """, (symbol,))
            price_row = cur.fetchone()
    finally:
        conn.close()

    composite_score = float(row[0]) if row and row[0] is not None else None
    momentum_score  = float(row[1]) if row and row[1] is not None else None
    quality_score   = float(row[2]) if row and row[2] is not None else None
    value_score     = float(row[3]) if row and row[3] is not None else None
    sector          = row[4] if row else None
    industry        = row[5] if row else None
    company_name    = row[6] if row else symbol
    current_price   = float(price_row[0]) if price_row else None

    return {
        "symbol": symbol,
        "company_name": company_name,
        "sector": sector,
        "industry": industry,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "current_price": current_price,
        "risk_pct": risk_pct,
        "r1_target": r1_target,
        "r2_target": r2_target,
        "position_size_pct": position_size_pct,
        "composite_score": composite_score,
        "momentum_score": momentum_score,
        "quality_score": quality_score,
        "value_score": value_score,
    }


def main():
    if len(sys.argv) != 4:
        print(json.dumps({"error": "Usage: algo_preview.py SYMBOL ENTRY_PRICE STOP_LOSS"}))
        sys.exit(1)

    symbol = sys.argv[1].upper()
    try:
        entry_price = float(sys.argv[2])
        stop_loss   = float(sys.argv[3])
    except ValueError:
        print(json.dumps({"error": "entry_price and stop_loss must be numbers"}))
        sys.exit(1)

    if stop_loss >= entry_price:
        print(json.dumps({"error": "stop_loss must be less than entry_price"}))
        sys.exit(1)

    try:
        result = preview(symbol, entry_price, stop_loss)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()

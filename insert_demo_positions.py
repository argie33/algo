#!/usr/bin/env python3
"""Insert demo positions for local development testing."""

from datetime import datetime

from utils.db import DatabaseContext

demo_positions: list[dict[str, str | float]] = [
    {"symbol": "AAPL", "quantity": 100, "avg_entry_price": 150.0, "current_price": 185.0},
    {"symbol": "MSFT", "quantity": 50, "avg_entry_price": 380.0, "current_price": 420.0},
    {"symbol": "TSLA", "quantity": 25, "avg_entry_price": 250.0, "current_price": 280.0},
    {"symbol": "NVDA", "quantity": 30, "avg_entry_price": 800.0, "current_price": 920.0},
    {"symbol": "AMZN", "quantity": 15, "avg_entry_price": 170.0, "current_price": 195.0},
]

try:
    with DatabaseContext("write") as cur:
        # Clear existing demo positions
        cur.execute("DELETE FROM algo_positions WHERE symbol IN ('AAPL', 'MSFT', 'TSLA', 'NVDA', 'AMZN')")
        print("Cleared existing demo positions")

        # Insert new demo positions
        for i, pos in enumerate(demo_positions, 1):
            quantity = float(pos["quantity"])
            avg_entry_price = float(pos["avg_entry_price"])
            current_price = float(pos["current_price"])
            position_id = f"DEMO_{i}_{pos['symbol']}"
            position_value = quantity * current_price
            unrealized_pnl = position_value - (quantity * avg_entry_price)
            unrealized_pnl_pct = (unrealized_pnl / (quantity * avg_entry_price)) * 100

            cur.execute(
                """INSERT INTO algo_positions
                   (position_id, symbol, quantity, avg_entry_price, current_price,
                    position_value, unrealized_pnl, unrealized_pnl_pct, status,
                    entry_date, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (position_id, pos["symbol"], quantity, avg_entry_price,
                 current_price, position_value, unrealized_pnl, unrealized_pnl_pct,
                 "open", datetime.now().date(), datetime.now(), datetime.now()),
            )
        print(f"Created {len(demo_positions)} demo positions")

        # Verify
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
        result = cur.fetchone()
        if not result:
            print("ERROR: Failed to query position count")
        else:
            count = result[0]
            print(f"Total open positions in database: {count}")

except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()

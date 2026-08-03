from utils.db import DatabaseContext

with DatabaseContext() as cur:
    print("=== POSITIONS WITH NULL cognito_sub ===")
    cur.execute("""
    SELECT position_id, symbol, quantity, entry_price, entry_date, created_at
    FROM algo_positions
    WHERE status = 'open' AND cognito_sub IS NULL
    ORDER BY entry_date DESC
    """)

    rows = cur.fetchall()
    for pos_id, symbol, qty, entry_price, entry_date, created_at in rows:
        print(f"{symbol:10} | Qty={qty:6.2f} | Entry=${entry_price:8.2f} | Created={created_at}")

    print("\n=== CHECKING CORRESPONDING TRADES ===")
    cur.execute("""
    SELECT t.trade_id, t.symbol, t.quantity, t.status, t.cognito_sub
    FROM algo_trades t
    WHERE t.status IN ('open', 'filled')
    AND t.cognito_sub IS NOT NULL
    LIMIT 5
    """)

    trades = cur.fetchall()
    if trades:
        print(f"Found {len(trades)} trades WITH cognito_sub")
        for trade_id, symbol, qty, status, cognito_sub in trades[:3]:
            print(f"  {trade_id}: {symbol} cognito_sub={cognito_sub}")

    cur.execute("""
    SELECT COUNT(*)  FROM algo_trades
    WHERE status IN ('open', 'filled')
    AND cognito_sub IS NULL
    """)
    null_trades = cur.fetchone()[0]
    print(f"\nTrades WITH NULL cognito_sub: {null_trades}")

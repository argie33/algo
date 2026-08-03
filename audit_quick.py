from utils.db import DatabaseContext

with DatabaseContext() as cur:
    print("=== POSITION DATA INTEGRITY CHECKS ===")

    cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open' AND stop_loss_price IS NULL")
    print(f"Open positions with NULL stop_loss_price: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open' AND entry_price IS NULL")
    print(f"Open positions with NULL entry_price: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open' AND cognito_sub IS NULL")
    print(f"Open positions with NULL cognito_sub: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM algo_positions WHERE quantity = 0 AND status = 'open'")
    print(f"Orphaned positions (qty=0, status=open): {cur.fetchone()[0]}")

    print("\n=== TRADE DATA INTEGRITY CHECKS ===")
    cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status = 'open' AND entry_price IS NULL")
    print(f"Open trades with NULL entry_price: {cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status = 'closed' AND (profit_loss_pct IS NULL OR profit_loss_dollars IS NULL)")
    print(f"Closed trades with NULL profit/loss: {cur.fetchone()[0]}")

    print("\n=== PORTFOLIO STATE ===")
    cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
    print(f"Total open positions: {cur.fetchone()[0]}")

    cur.execute("SELECT COALESCE(SUM(profit_loss_dollars), 0) FROM algo_positions WHERE status = 'open'")
    unrealized = cur.fetchone()[0]
    print(f"Total unrealized P&L: {unrealized:.2f}")

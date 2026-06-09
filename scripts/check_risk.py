#!/usr/bin/env python3
import psycopg2
import os
import json
import sys

# Get credentials from environment - should be set by PowerShell profile
host = os.getenv('DB_HOST') or os.getenv('ALGO_DB_HOST')
user = os.getenv('DB_USER') or os.getenv('ALGO_DB_USER')
password = os.getenv('DB_PASSWORD') or os.getenv('ALGO_DB_PASSWORD')
database = os.getenv('DB_NAME') or os.getenv('ALGO_DB_NAME')

if not host:
    print("ERROR: Database credentials not set in environment variables")
    print("Please run this from PowerShell with the profile loaded, or set:")
    print("  ALGO_DB_HOST, ALGO_DB_USER, ALGO_DB_PASSWORD, ALGO_DB_NAME")
    sys.exit(1)

try:
    conn = psycopg2.connect(host=host, user=user, password=password, database=database)
    cur = conn.cursor()

    print('='*60)
    print('PORTFOLIO VALUE')
    print('='*60)
    cur.execute('SELECT total_portfolio_value, snapshot_date FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1')
    row = cur.fetchone()
    if row:
        print(f'Portfolio Value: ${row[0]:,.2f}')
        print(f'As of: {row[1]}')
    else:
        print('No portfolio data found')

    print('\n' + '='*60)
    print('OPEN POSITIONS')
    print('='*60)
    cur.execute("""
        SELECT
          p.symbol,
          p.quantity,
          ROUND(t.entry_price::numeric, 2),
          ROUND(COALESCE(p.current_stop_price, t.stop_loss_price)::numeric, 2),
          ROUND(((t.entry_price - COALESCE(p.current_stop_price, t.stop_loss_price)) * p.quantity)::numeric, 2)
        FROM algo_positions p
        JOIN algo_trades t ON t.trade_id = ANY(p.trade_ids_arr)
        WHERE p.status = 'open'
        ORDER BY p.symbol
    """)
    positions = cur.fetchall()
    if positions:
        print(f"{'SYMBOL':<8} {'QTY':<10} {'ENTRY':<10} {'STOP':<10} {'RISK':<12}")
        print('-'*60)
        for sym, qty, entry, stop, risk in positions:
            print(f"{sym:<8} {qty:<10.0f} ${entry:<9.2f} ${stop:<9.2f} ${risk:<11,.2f}")
    else:
        print('No open positions')

    print('\n' + '='*60)
    print('TOTAL RISK CALCULATION')
    print('='*60)
    cur.execute("""
        WITH risk_calc AS (
          SELECT
            SUM(GREATEST(0, (t.entry_price - COALESCE(p.current_stop_price, t.stop_loss_price)) * p.quantity)) as total_risk_dollars,
            (SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1) as portfolio_value
          FROM algo_positions p
          JOIN algo_trades t ON t.trade_id = ANY(p.trade_ids_arr)
          WHERE p.status = 'open'
        )
        SELECT total_risk_dollars, portfolio_value FROM risk_calc
    """)
    row = cur.fetchone()
    if row and row[1]:
        risk_dollars = float(row[0]) if row[0] else 0
        portfolio = float(row[1])
        risk_pct = (risk_dollars / portfolio * 100) if portfolio > 0 else 0
        threshold = 4.0
        status = 'TRIGGERED' if risk_pct >= threshold else 'OK'
        print(f'Total Risk:     ${risk_dollars:,.2f}')
        print(f'Portfolio:      ${portfolio:,.2f}')
        print(f'Risk %:         {risk_pct:.2f}%')
        print(f'Threshold:      {threshold:.1f}%')
        print(f'Status:         [{status}]')

    cur.close()
    conn.close()
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

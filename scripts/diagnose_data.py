#!/usr/bin/env python3
"""Diagnostic script to check database state for VIX and concentration data.

Run: python scripts/diagnose_data.py
"""

import logging

logging.basicConfig(level=logging.INFO)

print("\n" + "=" * 80)
print("DATABASE DIAGNOSTICS: VIX and Concentration Data")
print("=" * 80 + "\n")

try:
    from utils.db.context import DatabaseContext
except ImportError as e:
    print(f"ERROR: Cannot import DatabaseContext: {e}")
    print("Make sure you're running from the algo root directory")
    exit(1)

# 1. Check market_health_daily for VIX data
print("1. MARKET_HEALTH_DAILY TABLE (VIX source)")
print("-" * 80)
try:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT COUNT(*) FROM market_health_daily")
        count = cur.fetchone()[0]
        print(f"Total rows: {count}")

        if count > 0:
            cur.execute("SELECT date, vix_level FROM market_health_daily ORDER BY date DESC LIMIT 10")
            rows = cur.fetchall()
            print("\nLast 10 rows (date, vix_level):")
            for date_val, vix in rows:
                print(f"  {date_val}: {vix}")

            # Count NULL vix_level
            cur.execute("SELECT COUNT(*) FROM market_health_daily WHERE vix_level IS NULL")
            null_count = cur.fetchone()[0]
            print(f"\nRows with NULL vix_level: {null_count}/{count}")

            cur.execute("SELECT COUNT(*) FROM market_health_daily WHERE vix_level < 5")
            low_count = cur.fetchone()[0]
            print(f"Rows with vix_level < 5: {low_count}/{count}")

            if null_count == count:
                print("\n[ERROR] ALL vix_level values are NULL!")
                print("  -> load_market_health_daily may not have run")
                print("  -> OR yfinance fetch is failing")
        else:
            print("[ERROR] Table is EMPTY!")
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")

# 2. Check algo_risk_daily for concentration data
print("\n2. ALGO_RISK_DAILY TABLE (concentration source)")
print("-" * 80)
try:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT COUNT(*) FROM algo_risk_daily")
        count = cur.fetchone()[0]
        print(f"Total rows: {count}")

        if count > 0:
            cur.execute(
                "SELECT report_date, top_5_concentration, var_pct_95, cvar_pct_95, portfolio_beta FROM algo_risk_daily ORDER BY report_date DESC LIMIT 10"
            )
            rows = cur.fetchall()
            print("\nLast 10 rows:")
            for report_date, conc5, var95, cvar95, beta in rows:
                print(f"  {report_date}: conc5={conc5}, var95={var95}, cvar95={cvar95}, beta={beta}")

            # Check NULL values
            cur.execute("SELECT COUNT(*) FROM algo_risk_daily WHERE top_5_concentration IS NULL")
            null_count = cur.fetchone()[0]
            print(f"\nRows with NULL top_5_concentration: {null_count}/{count}")

            cur.execute("SELECT COUNT(*) FROM algo_risk_daily WHERE top_5_concentration = 0")
            zero_count = cur.fetchone()[0]
            print(f"Rows with top_5_concentration = 0: {zero_count}/{count}")

            if null_count == count:
                print("\n[ERROR] ALL top_5_concentration values are NULL!")
                print("  -> concentration_report() in var.py may not have run")
                print("  -> OR all positions are being excluded (missing prices)")
        else:
            print("[ERROR] Table is EMPTY!")
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")

# 3. Check algo_positions for position data
print("\n3. ALGO_POSITIONS TABLE (position source for concentration)")
print("-" * 80)
try:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
        count = cur.fetchone()[0]
        print(f"Total open positions: {count}")

        if count > 0:
            cur.execute(
                "SELECT symbol, quantity, current_price, avg_entry_price, position_value FROM algo_positions WHERE status = 'open' LIMIT 10"
            )
            rows = cur.fetchall()
            print("\nFirst 10 positions:")
            for symbol, qty, cur_price, entry_price, pos_val in rows:
                print(f"  {symbol}: qty={qty}, cur_price={cur_price}, entry_price={entry_price}, pos_val={pos_val}")

            # Check missing current_price
            cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open' AND current_price IS NULL")
            null_price = cur.fetchone()[0]
            print(f"\nPositions with NULL current_price: {null_price}/{count}")

            if null_price == count:
                print("\n[ERROR] ALL positions have NULL current_price!")
                print("  -> This is why concentration is 0%")
                print("  -> Check how position prices are populated")
            elif null_price > 0:
                print(f"\n[WARN] {null_price} positions excluded from concentration due to missing price")
        else:
            print("[ERROR] No open positions!")
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")

# 4. Check algo_portfolio_snapshots for portfolio value
print("\n4. ALGO_PORTFOLIO_SNAPSHOTS TABLE")
print("-" * 80)
try:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT COUNT(*) FROM algo_portfolio_snapshots")
        count = cur.fetchone()[0]
        print(f"Total rows: {count}")

        if count > 0:
            cur.execute(
                "SELECT snapshot_date, total_portfolio_value, total_cash FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 5"
            )
            rows = cur.fetchall()
            print("\nLast 5 snapshots:")
            for date_val, port_val, cash in rows:
                print(f"  {date_val}: portfolio=${port_val}, cash=${cash}")
        else:
            print("[ERROR] Table is EMPTY!")
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")

print("\n" + "=" * 80)
print("END DIAGNOSTICS")
print("=" * 80 + "\n")

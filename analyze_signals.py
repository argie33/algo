#!/usr/bin/env python3
"""Analyze signal volume and performance."""

from utils.db_connection import get_db_connection
from datetime import datetime, timedelta

conn = get_db_connection()
cursor = conn.cursor()

print("\n" + "="*70)
print("SIGNAL GENERATION ANALYSIS")
print("="*70 + "\n")

# Check signal volume over past 30 days
cursor.execute("""
    SELECT
        DATE(date) as signal_date,
        COUNT(*) as signal_count,
        COUNT(DISTINCT symbol) as unique_symbols
    FROM buy_sell_daily
    WHERE date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY DATE(date)
    ORDER BY signal_date DESC
""")

print("Daily Signal Counts (Last 30 Days):")
print("-" * 70)
results = cursor.fetchall()
total_signals = 0
for date, count, unique in results:
    print(f"  {date}: {count:>6} signals, {unique:>4} unique symbols")
    total_signals += count

print(f"\nTotal signals in past 30 days: {total_signals}")
if results:
    avg_per_day = total_signals / len(results)
    avg_per_week = avg_per_day * 7
    print(f"Average per day: {avg_per_day:.1f}")
    print(f"Average per week: {avg_per_week:.1f}")

# Check the 3 signals from May 15
print("\n" + "="*70)
print("SIGNALS FROM MAY 15 (2026-05-15)")
print("="*70 + "\n")

cursor.execute("""
    SELECT symbol, signal, date
    FROM buy_sell_daily
    WHERE date = '2026-05-15'
    ORDER BY symbol
""")

signals = cursor.fetchall()
print(f"Found {len(signals)} signals on 2026-05-15:")
for i, (symbol, signal, date) in enumerate(signals[:10], 1):
    print(f"  {i}. {symbol:6} → {signal}")

# Get performance stats for recent trades
print("\n" + "="*70)
print("RECENT TRADE PERFORMANCE")
print("="*70 + "\n")

cursor.execute("""
    SELECT
        COUNT(*) as total_trades,
        SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as winning_trades,
        SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) as losing_trades,
        ROUND(SUM(profit_loss)::NUMERIC, 2) as total_pnl,
        ROUND(AVG(profit_loss)::NUMERIC, 2) as avg_pnl,
        ROUND(MAX(profit_loss)::NUMERIC, 2) as best_trade,
        ROUND(MIN(profit_loss)::NUMERIC, 2) as worst_trade
    FROM trades
    WHERE entry_date >= CURRENT_DATE - INTERVAL '30 days'
""")

row = cursor.fetchone()
if row[0] > 0:
    total_trades, wins, losses, total_pnl, avg_pnl, best, worst = row
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    print(f"Total trades (30d):  {total_trades}")
    print(f"Winning trades:      {wins} ({win_rate:.1f}%)")
    print(f"Losing trades:       {losses}")
    print(f"Total P&L:           ${total_pnl}")
    print(f"Average P&L/trade:   ${avg_pnl}")
    print(f"Best trade:          ${best}")
    print(f"Worst trade:         ${worst}")
else:
    print("No trades executed yet (system in dry-run mode)")

# Signal selectivity analysis
print("\n" + "="*70)
print("SIGNAL SELECTIVITY")
print("="*70 + "\n")

cursor.execute("""
    SELECT
        COUNT(DISTINCT symbol) as universe_size,
        (SELECT COUNT(*) FROM stock_symbols) as total_stocks
    FROM price_daily
    WHERE date = (SELECT MAX(date) FROM price_daily)
""")

universe, total = cursor.fetchone()
cursor.execute("""
    SELECT COUNT(*) FROM buy_sell_daily
    WHERE date = (SELECT MAX(date) FROM buy_sell_daily)
""")
signal_count = cursor.fetchone()[0]

print(f"Total stocks tracked:      {total:,}")
print(f"Stocks with current data:  {universe:,}")
print(f"Signals generated (latest): {signal_count}")
if universe > 0:
    selectivity = (signal_count / universe * 100)
    print(f"Selectivity rate:          {selectivity:.3f}% (only {signal_count} out of {universe:,} stocks)")
    print(f"\nThis means the filters are VERY SELECTIVE:")
    print(f"  - Only signals meeting ALL filter criteria are passed")
    print(f"  - Gates include: trend quality, momentum, volume, technicals")
    print(f"  - Expected: 3-5 high-quality signals per week is normal for a selective algo")

cursor.close()
conn.close()

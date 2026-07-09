#!/usr/bin/env python3
"""Complete system diagnostic - verify what's ACTUALLY working"""
import json
from utils.db.context import DatabaseContext

print("=" * 80)
print("FULL SYSTEM DIAGNOSTIC")
print("=" * 80)

db = DatabaseContext('read')
with db as cur:
    # 1. Test if growth scores are actually queryable by the API
    print("\n1. GROWTH SCORES API TEST:")
    try:
        cur.execute('''
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN growth_score IS NOT NULL THEN 1 END) as with_score,
                   COUNT(CASE WHEN growth_score IS NOT NULL AND composite_score > 0 THEN 1 END) as tradeable
            FROM stock_scores
            WHERE composite_score > 0
        ''')
        row = cur.fetchone()
        print(f"   Total scores with composite_score > 0: {row['total']}")
        print(f"   With growth_score: {row['with_score']}")
        print(f"   Tradeable (growth + composite): {row['tradeable']}")

        # Get sample growth score
        cur.execute('''
            SELECT symbol, growth_score, composite_score, quality_score, value_score
            FROM stock_scores
            WHERE growth_score IS NOT NULL
            LIMIT 3
        ''')
        samples = cur.fetchall()
        if samples:
            print(f"   Sample data available:")
            for s in samples:
                print(f"      {s['symbol']}: growth={s['growth_score']}, composite={s['composite_score']}")
    except Exception as e:
        print(f"   ERROR: {e}")

    # 2. Check what the positions endpoint would return
    print("\n2. POSITIONS DATA STRUCTURE:")
    try:
        cur.execute('''
            SELECT symbol, status, position_value, avg_entry_price, current_price,
                   unrealized_pnl_pct, stop_loss_price, entry_date
            FROM algo_positions
            WHERE status = 'open'
            ORDER BY entry_date DESC
            LIMIT 3
        ''')
        positions = cur.fetchall()
        if positions:
            print(f"   Open positions: {len([p for p in cur.fetchall() if p['status'] == 'open'])} + {len(positions)} displayed")
            for p in positions:
                print(f"   {p['symbol']}: value={p['position_value']}, entry={p['avg_entry_price']}, current={p['current_price']}, pnl_pct={p['unrealized_pnl_pct']}")
        else:
            print(f"   No positions returned from query")
    except Exception as e:
        print(f"   ERROR: {e}")

    # 3. Check if any signals were generated TODAY
    print("\n3. SIGNAL GENERATION TODAY:")
    try:
        cur.execute('''
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN signal_type = 'BUY' THEN 1 END) as buys,
                   COUNT(CASE WHEN signal_type = 'SELL' THEN 1 END) as sells
            FROM algo_signals
            WHERE DATE(created_at) = CURRENT_DATE
        ''')
        row = cur.fetchone()
        print(f"   Signals generated today: {row['total']}")
        print(f"   Buy signals: {row['buys']}")
        print(f"   Sell signals: {row['sells']}")

        if row['total'] > 0:
            # If signals exist, get sample
            cur.execute('''
                SELECT symbol, signal_type, signal_strength, created_at
                FROM algo_signals
                WHERE DATE(created_at) = CURRENT_DATE
                ORDER BY created_at DESC
                LIMIT 3
            ''')
            samples = cur.fetchall()
            for s in samples:
                print(f"      {s['symbol']}: {s['signal_type']} (strength={s['signal_strength']})")
    except Exception as e:
        print(f"   ERROR: {e}")

    # 4. Check trade execution
    print("\n4. TRADES EXECUTION:")
    try:
        cur.execute('''
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN DATE(entry_date) = CURRENT_DATE THEN 1 END) as today,
                   MAX(entry_date) as latest
            FROM algo_trades
        ''')
        row = cur.fetchone()
        print(f"   Total trades all time: {row['total']}")
        print(f"   Trades today: {row['today']}")
        print(f"   Latest trade: {row['latest']}")

        # Check last 7 days
        cur.execute('''
            SELECT DATE(entry_date) as date, COUNT(*) as count
            FROM algo_trades
            WHERE entry_date >= CURRENT_DATE - get_interval_sql('7d')
            GROUP BY DATE(entry_date)
            ORDER BY date DESC
        ''')
        recent = cur.fetchall()
        if recent:
            print(f"   Last 7 days:")
            for r in recent:
                print(f"      {r['date']}: {r['count']} trades")
    except Exception as e:
        print(f"   ERROR: {e}")

    # 5. Check if orchestrator is generating ANY phase 7 outputs
    print("\n5. ORCHESTRATOR PHASE 7 OUTPUTS:")
    try:
        cur.execute('''
            SELECT run_id, overall_status, started_at,
                   phase_results -> '7' ->> 'signal_count' as signal_count,
                   phase_results -> '7' ->> 'status' as phase_7_status
            FROM orchestrator_execution_log
            WHERE overall_status = 'success'
            ORDER BY started_at DESC
            LIMIT 3
        ''')
        rows = cur.fetchall()
        if rows:
            print(f"   Recent successful orchestrator runs:")
            for row in rows:
                phase7_status = row.get('phase_7_status', 'N/A')
                signal_count = row.get('signal_count', '0')
                print(f"      {row['run_id']}: phase_7={phase7_status}, signals={signal_count}")
    except Exception as e:
        print(f"   ERROR: {e}")

    # 6. Check data quality
    print("\n6. DATA QUALITY METRICS:")
    try:
        cur.execute('''
            SELECT
                (SELECT COUNT(*) FROM stock_scores WHERE data_unavailable = FALSE) as scores_available,
                (SELECT COUNT(*) FROM stock_scores WHERE growth_score IS NOT NULL) as growth_available,
                (SELECT COUNT(*) FROM stock_scores WHERE composite_score > 0) as tradeable_stocks,
                (SELECT COUNT(*) FROM price_daily WHERE DATE(date) = CURRENT_DATE) as prices_today
        ''')
        row = cur.fetchone()
        print(f"   Stock scores available: {row['scores_available']}")
        print(f"   With growth_score: {row['growth_available']}")
        print(f"   Tradeable (composite > 0): {row['tradeable_stocks']}")
        print(f"   Price updates today: {row['prices_today']}")
    except Exception as e:
        print(f"   ERROR: {e}")

print("\n" + "=" * 80)
print("END DIAGNOSTIC")
print("=" * 80)

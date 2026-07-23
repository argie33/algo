#!/usr/bin/env python3
"""Test Phase 7 signal quality score fix."""

import sys
sys.path.insert(0, "/root" if "/" in sys.path[0] else "C:\\Users\\arger\\code\\algo")

from utils.db.context import DatabaseContext
from datetime import datetime

print("\n" + "=" * 70)
print("TEST: Phase 7 Signal Quality Score Fix")
print("=" * 70)

with DatabaseContext("read") as cur:
    # Check if signal quality scores were computed for recent trades
    print("\n1. Signal Quality Scores in Database:")
    print("-" * 70)

    cur.execute("""
        SELECT MAX(created_at) as latest_computed
        FROM signal_quality_scores
    """)
    result = cur.fetchone()
    if result and result[0]:
        print(f"   Latest scores computed: {result[0]}")
    else:
        print("   No scores found")

    # Check new trades - do they have signal quality scores?
    print("\n2. Recent Trades - Signal Quality Scores:")
    print("-" * 70)

    cur.execute("""
        SELECT
            symbol,
            entry_date,
            signal_quality_score,
            trend_template_score,
            profit_loss_pct
        FROM algo_trades
        WHERE status = 'closed'
          AND trade_id NOT LIKE 'EXT-%%'
          AND entry_date >= CURRENT_DATE - INTERVAL '1 day'
        ORDER BY entry_date DESC
        LIMIT 10
    """)

    rows = cur.fetchall()
    if rows:
        has_sqs = sum(1 for r in rows if r[2] is not None)
        print(f"   Total trades in last 24h: {len(rows)}")
        print(f"   With signal_quality_score: {has_sqs}")

        for sym, entry_d, sqs, tts, pnl in rows:
            pnl_str = f"{pnl:+.2f}%" if pnl else "NULL"
            sqs_str = f"{sqs:.0f}" if sqs else "NULL"
            print(f"   {sym:6} {entry_d} SQS:{sqs_str:>3} TTS:{str(tts)[:2]:>2} PnL:{pnl_str:>8}")
    else:
        print("   No trades in last 24 hours")

    # Check win rate with new trades
    print("\n3. Updated Win Rate:")
    print("-" * 70)

    cur.execute("""
        WITH all_trades AS (
            SELECT profit_loss_pct as pnl_pct
            FROM (
                SELECT profit_loss_pct
                FROM algo_trades
                WHERE status = 'closed'
                  AND trade_id NOT LIKE 'EXT-%%'
                  AND profit_loss_pct IS NOT NULL
                ORDER BY exit_date DESC
                LIMIT 30
            ) recent_closed
            UNION ALL
            SELECT unrealized_pnl_pct as pnl_pct
            FROM algo_positions
            WHERE status = 'open' AND quantity > 0
        )
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
            COUNT(*) FILTER (WHERE pnl_pct < 0) as losses,
            ROUND(100.0 * COUNT(*) FILTER (WHERE pnl_pct > 0) / (COUNT(*) FILTER (WHERE pnl_pct > 0) + COUNT(*) FILTER (WHERE pnl_pct < 0)), 1) as win_rate
        FROM all_trades
    """)

    total, wins, losses, wr = cur.fetchone()
    print(f"   Total in sample: {total}")
    print(f"   Wins: {wins}")
    print(f"   Losses: {losses}")
    print(f"   Win rate: {wr}%")
    print(f"   Threshold: 40%")
    print(f"   Status: {'CLEAR TO TRADE' if wr and wr >= 40 else 'HALTED'}")

print("\n" + "=" * 70 + "\n")

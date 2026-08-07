#!/usr/bin/env python3
"""
Comprehensive audit to find ALL real issues preventing production readiness.
Not just the first halt - find everything broken.
"""

import sys
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from utils.db.context import DatabaseContext
from utils.trading import TradeStatus, PositionStatus

def audit_database_integrity():
    """Check database state for real issues."""
    print("\n" + "="*80)
    print("DATABASE INTEGRITY AUDIT")
    print("="*80)

    with DatabaseContext("read") as cur:
        # 1. Check for positions without trades
        cur.execute("""
            SELECT id, symbol, quantity, trade_ids_arr
            FROM algo_positions
            WHERE (trade_ids_arr IS NULL OR array_length(trade_ids_arr, 1) = 0)
            AND status = 'open'
        """)
        orphaned = cur.fetchall()
        if orphaned:
            print(f"\n❌ CRITICAL: {len(orphaned)} OPEN positions without trade_ids")
            for row in orphaned[:3]:
                print(f"   Pos {row[0]}: {row[1]} qty={row[2]}, trades={row[3]}")
        else:
            print(f"\n✅ No orphaned open positions")

        # 2. Simple check: open positions with negative unrealized PNL
        cur.execute("""
            SELECT id, symbol, quantity, unrealized_pnl_pct, current_price, stop_loss_price
            FROM algo_positions
            WHERE status = 'open' AND unrealized_pnl_pct < -10
        """)
        underwater = cur.fetchall()
        if underwater:
            print(f"\n⚠️ {len(underwater)} open positions underwater > 10%")
            for row in underwater[:5]:
                print(f"   Pos {row[0]}: {row[1]} qty={row[2]}, PNL={row[3]:.1f}%, Current=${row[4]:.2f}, Stop=${row[5]:.2f}")
        else:
            print(f"✅ No severely underwater positions")

        # 3. Check for positions with NULL critical fields
        cur.execute("""
            SELECT id, symbol, stop_loss_price, target_1_price, entry_price
            FROM algo_positions
            WHERE status = 'open'
            AND (stop_loss_price IS NULL OR entry_price IS NULL OR target_1_price IS NULL)
        """)
        null_fields = cur.fetchall()
        if null_fields:
            print(f"\n❌ {len(null_fields)} open positions with NULL critical fields")
            for row in null_fields[:3]:
                print(f"   Pos {row[0]}: {row[1]} stop={row[2]}, tgt={row[3]}, entry={row[4]}")
        else:
            print(f"✅ No NULL critical fields in open positions")

def audit_circuit_breaker():
    """Check circuit breaker state and recent halts."""
    print("\n" + "="*80)
    print("CIRCUIT BREAKER STATUS")
    print("="*80)

    with DatabaseContext("read") as cur:
        # Check recent orchestrator halts
        cur.execute("""
            SELECT run_id, overall_status, halt_reason, started_at
            FROM algo_orchestrator_runs
            WHERE overall_status = 'halted'
            ORDER BY started_at DESC
            LIMIT 3
        """)

        halts = cur.fetchall()
        for run_id, status, reason, start_time in halts:
            print(f"\n❌ Halted run: {run_id}")
            print(f"   Time: {start_time}")
            print(f"   Reason: {reason[:100]}")

def audit_recent_trades():
    """Check if the 5 consecutive losses are real or false positives."""
    print("\n" + "="*80)
    print("RECENT TRADE AUDIT - LOSS STREAK ANALYSIS")
    print("="*80)

    with DatabaseContext("read") as cur:
        # Get the 10 most recent closed trades
        cur.execute("""
            SELECT id, trade_id, symbol, entry_price, entry_date, exit_date,
                   profit_loss_pct, exit_reason, status
            FROM algo_trades
            WHERE status = 'closed' AND exit_date IS NOT NULL
            AND trade_id NOT ILIKE 'EXT-%%'
            AND exit_reason NOT ILIKE '%%reconciliation%%'
            AND exit_reason NOT ILIKE '%%force%%close%%'
            AND exit_reason NOT ILIKE '%%delisted%%'
            AND exit_reason NOT ILIKE '%%DATA-QC%%'
            AND exit_reason NOT ILIKE '%%CONCENTRATION%%'
            ORDER BY exit_date DESC, id DESC
            LIMIT 10
        """)

        trades = cur.fetchall()
        consecutive_losses = 0
        print(f"\nRecent closed trades (most recent first):")
        for idx, (id, tid, sym, ep, ed_date, ex_date, pnl, reason, status) in enumerate(trades):
            marker = "❌" if pnl and pnl < 0 else ("✅" if pnl and pnl > 0 else "⚪")
            print(f"{marker} {idx+1}. {sym:6} | PNL: {pnl:+7.2f}% | {ex_date} | {reason[:60]}")

            # Count consecutive losses from most recent
            if idx == 0 and pnl and pnl < 0:
                consecutive_losses = 1
            elif idx > 0 and consecutive_losses > 0 and pnl and pnl < 0:
                consecutive_losses += 1
            elif idx > 0 and consecutive_losses > 0:
                break

        print(f"\nConsecutive losses from most recent: {consecutive_losses}")
        print(f"Circuit breaker threshold (paper mode): 5")
        if consecutive_losses >= 5:
            print(f"⚠️ CIRCUIT BREAKER ACTIVE - system is HALTED")

def audit_open_positions():
    """Check current open positions for issues."""
    print("\n" + "="*80)
    print("OPEN POSITIONS AUDIT")
    print("="*80)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT id, symbol, quantity, entry_price, current_price, stop_loss_price,
                   unrealized_pnl_pct, days_since_entry
            FROM algo_positions
            WHERE status = 'open' AND is_open = true
            ORDER BY created_at DESC
            LIMIT 15
        """)

        positions = cur.fetchall()
        print(f"\nTotal open positions: {len(positions)}\n")

        stopped_out_count = 0
        for id, sym, qty, entry, current, stop, pnl, days in positions[:10]:
            # Check if below stop
            is_below_stop = current and stop and current <= stop
            marker = "🛑" if is_below_stop else "✅"

            if is_below_stop:
                stopped_out_count += 1

            print(f"{marker} {sym:6} | Qty: {qty:8.2f} | Entry: ${entry:8.2f} | " +
                  f"Current: ${current:8.2f} | Stop: ${stop:8.2f} | PNL: {pnl:+6.2f}% | Age: {days}d")

        if stopped_out_count > 0:
            print(f"\n❌ {stopped_out_count} positions are BELOW their stop loss prices")
            print("   These should trigger exit engine immediately")
        else:
            print(f"\n✅ No positions below stop loss (safe)")

def audit_loader_freshness():
    """Check if loaders are running and data is fresh."""
    print("\n" + "="*80)
    print("DATA LOADER STATUS")
    print("="*80)

    with DatabaseContext("read") as cur:
        # Check latest prices loader
        cur.execute("""
            SELECT MAX(created_at) as last_run
            FROM price_daily
            WHERE created_at IS NOT NULL
        """)
        row = cur.fetchone()
        if row and row[0]:
            # Handle timezone-aware comparison
            now = datetime.now() if row[0].tzinfo is None else datetime.now(timezone.utc)
            last_run = row[0] if row[0].tzinfo else row[0].replace(tzinfo=timezone.utc)
            if row[0].tzinfo is None:
                last_run = row[0].replace(tzinfo=None)
                now = datetime.now()
            else:
                now = datetime.now(timezone.utc)
            age = now - last_run
            age_hours = age.total_seconds() / 3600
            marker = "✅" if age_hours < 24 else "⚠️" if age_hours < 72 else "❌"
            print(f"\n{marker} Prices loader: {age_hours:.1f} hours old")
        else:
            print("\n❌ No price data found")

def main():
    print("\n" + "="*80)
    print("COMPREHENSIVE AUDIT - FINDING ALL REAL ISSUES")
    print("="*80)

    try:
        audit_database_integrity()
        audit_circuit_breaker()
        audit_recent_trades()
        audit_open_positions()
        audit_loader_freshness()

        print("\n" + "="*80)
        print("AUDIT COMPLETE")
        print("="*80)
    except Exception as e:
        print(f"\nAUDIT ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

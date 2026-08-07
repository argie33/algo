#!/usr/bin/env python3
from utils.db import DatabaseContext

def check_data_integrity():
    """Comprehensive database consistency checks"""
    issues = []

    with DatabaseContext('read') as cur:
        print("=" * 70)
        print("DATA INTEGRITY CHECK")
        print("=" * 70)

        # 1. Check for NULL values in critical fields
        print("\n1. CRITICAL NULLS CHECK:")
        cur.execute("""
            SELECT COUNT(*) FROM algo_trades WHERE status='open' AND (
                entry_price IS NULL OR stop_loss_price IS NULL OR
                entry_date IS NULL OR symbol IS NULL
            )
        """)
        null_trades = cur.fetchone()[0]
        if null_trades > 0:
            issues.append(f"❌ {null_trades} open trades have NULL critical fields")
            print(f"   ❌ {null_trades} trades with NULL critical fields")
        else:
            print(f"   ✅ All open trades have valid critical fields")

        # 2. Check for orphaned/duplicate positions
        print("\n2. POSITION INTEGRITY CHECK:")
        cur.execute("""
            SELECT symbol, COUNT(*) as cnt FROM algo_positions
            WHERE status='open' GROUP BY symbol HAVING COUNT(*) > 1
        """)
        dups = cur.fetchall()
        if dups:
            issues.append(f"❌ {len(dups)} symbols have duplicate open positions")
            print(f"   ❌ {len(dups)} symbols with >1 open position:")
            for sym, cnt in dups:
                print(f"      {sym}: {cnt} positions")
        else:
            print(f"   ✅ No duplicate positions")

        # 3. Check for trades without positions
        print("\n3. TRADE-POSITION LINKAGE CHECK:")
        cur.execute("""
            SELECT COUNT(*) FROM algo_trades t
            LEFT JOIN algo_positions p ON t.trade_id::text = ANY(p.trade_ids_arr::text[])
            WHERE t.status='open' AND p.position_id IS NULL
        """)
        orphaned = cur.fetchone()[0]
        if orphaned > 0:
            issues.append(f"❌ {orphaned} open trades orphaned (no position)")
            print(f"   ❌ {orphaned} orphaned open trades")
        else:
            print(f"   ✅ All open trades linked to positions")

        # 4. Check portfolio value consistency
        print("\n4. PORTFOLIO VALUE CHECK:")
        cur.execute("""
            SELECT total_portfolio_value FROM algo_portfolio_snapshots
            ORDER BY created_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row and row[0] is not None:
            print(f"   ✅ Latest portfolio snapshot: ${row[0]:,.2f}")
        else:
            issues.append("⚠️ No portfolio snapshot available")
            print(f"   ⚠️ No portfolio snapshot available")

        # 5. Check concentration limits
        print("\n5. CONCENTRATION CHECK:")
        cur.execute("""
            SELECT symbol, position_value
            FROM algo_positions p
            WHERE status='open'
            ORDER BY position_value DESC LIMIT 5
        """)
        positions = cur.fetchall()
        if positions:
            print(f"   ✅ Top 5 positions by value:")
            for sym, val in positions:
                print(f"      {sym}: ${val:,.2f}")
        else:
            print(f"   ✅ No open positions")

        # 6. Check for quantity mismatches
        print("\n6. QUANTITY CONSISTENCY CHECK:")
        cur.execute("""
            SELECT t.symbol, t.entry_quantity, p.quantity
            FROM algo_trades t
            JOIN algo_positions p ON t.trade_id::text = ANY(p.trade_ids_arr::text[])
            WHERE t.status='open' AND p.status='open'
            AND ABS(CAST(t.entry_quantity AS numeric) - CAST(p.quantity AS numeric)) > 0.01
        """)
        mismatches = cur.fetchall()
        if mismatches:
            issues.append(f"❌ {len(mismatches)} trades with quantity mismatches")
            print(f"   ❌ {len(mismatches)} quantity mismatches:")
            for sym, trade_qty, pos_qty in mismatches[:5]:
                print(f"      {sym}: trade={trade_qty}, position={pos_qty}")
        else:
            print(f"   ✅ All quantities consistent")

        # 7. Summary
        print("\n7. OPEN POSITIONS SUMMARY:")
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status='open'")
        open_count = cur.fetchone()[0]
        print(f"   ✅ Total open positions: {open_count}")

    print("\n" + "=" * 70)
    print(f"SUMMARY: {len(issues)} issues found")
    for issue in issues:
        print(f"  {issue}")

    return len(issues) == 0

if __name__ == "__main__":
    success = check_data_integrity()
    exit(0 if success else 1)


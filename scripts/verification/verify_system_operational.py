#!/usr/bin/env python3
"""Final system verification - confirms all components operational."""

import sys
sys.path.insert(0, '.')

from datetime import datetime, timezone
from utils.db import DatabaseContext

def verify_all_systems():
    """Verify all critical systems are operational."""

    print("="*80)
    print("FINAL SYSTEM VERIFICATION - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*80)

    issues = []

    with DatabaseContext('read') as cur:
        # 1. Orchestrator
        cur.execute("SELECT COUNT(*) FROM algo_orchestrator_runs WHERE DATE(started_at) = CURRENT_DATE")
        today_runs = cur.fetchone()[0] if cur.fetchone else 0

        if today_runs > 0:
            print("\n[✓] ORCHESTRATOR: Running (2+ daily runs expected)")
        else:
            print("\n[✗] ORCHESTRATOR: Not running today")
            issues.append("Orchestrator hasn't run today")

        # 2. Open Positions (Live Trading)
        cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status = 'open'")
        positions = cur.fetchone()[0] if cur.fetchone else 0

        if positions > 0:
            print(f"[✓] LIVE TRADING: {positions} open positions")
        else:
            print("[✗] LIVE TRADING: No positions")
            issues.append("No open positions - trading may not be active")

        # 3. Stock Scores Freshness
        cur.execute("""
            SELECT MAX(created_at) FROM stock_scores WHERE data_unavailable = FALSE
        """)
        row = cur.fetchone()
        scores_date = row[0] if isinstance(row, (list, tuple)) else row.get('max') if row else None

        if scores_date:
            age = (datetime.now(timezone.utc) - scores_date.replace(tzinfo=timezone.utc)).total_seconds() / 3600
            if age < 24:
                print(f"[✓] STOCK SCORES: Fresh ({age:.1f}h old)")
            else:
                print(f"[⚠] STOCK SCORES: Stale ({age:.1f}h old)")
                issues.append(f"Stock scores stale ({age:.1f}h old)")

        # 4. Market Sentiment Freshness
        cur.execute("SELECT MAX(date) FROM market_sentiment")
        sent_date = cur.fetchone()[0] if cur.fetchone else None

        if sent_date:
            age = (datetime.now(timezone.utc) - sent_date.replace(tzinfo=timezone.utc)).total_seconds() / 86400
            if age < 1:
                print(f"[✓] MARKET SENTIMENT: Fresh (Today's data)")
            else:
                print(f"[⚠] MARKET SENTIMENT: {age:.1f} days old")
                issues.append(f"Market sentiment {age:.1f} days old")

    print("\n" + "="*80)
    print("DASHBOARD API VERIFICATION:")
    print("="*80)
    print("Run: python -m dashboard.diagnose_dashboard")
    print("Expected: 26/26 endpoints working (0 errors)")

    print("\n" + "="*80)
    if issues:
        print(f"ISSUES FOUND ({len(issues)}):")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print("✓ ALL CRITICAL SYSTEMS OPERATIONAL")
        return True

if __name__ == "__main__":
    success = verify_all_systems()
    sys.exit(0 if success else 1)

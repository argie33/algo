#!/usr/bin/env python3
"""Comprehensive system audit - identifies all issues preventing end-to-end operation."""

import os
import sys
import socket
import json
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows console encoding for unicode output
if sys.platform.startswith('win'):
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except:
        pass

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent))


def audit_database():
    """Check database connectivity and critical table status."""
    print("\n" + "="*70)
    print("DATABASE AUDIT")
    print("="*70)

    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            user=os.getenv('DB_USER', 'stocks'),
            password=os.getenv('DB_PASSWORD', 'stocks'),
            database=os.getenv('DB_NAME', 'stocks'),
            connect_timeout=5,
        )
        cur = conn.cursor()
        print("✓ Database connection successful")

        # Check critical tables
        critical_tables = {
            'price_daily': 'OHLCV prices (required for signals)',
            'stock_scores': 'Stock rankings (dashboard display)',
            'algo_orchestrator_runs': 'Orchestrator execution history',
            'circuit_breaker_status': 'Trading safety metrics',
            'algo_signals': 'Buy/sell signals for trading',
        }

        issues = []
        for table, description in critical_tables.items():
            try:
                cur.execute(f"SELECT COUNT(*) as cnt FROM {table}")
                count = cur.fetchone()[0]
                if count == 0:
                    issues.append(f"⚠ {table}: EMPTY TABLE - {description}")
                else:
                    print(f"✓ {table}: {count} rows")
            except Exception as e:
                issues.append(f"✗ {table}: {str(e)[:80]}")

        # Check loader status
        cur.execute("SELECT COUNT(*) FROM data_loader_status WHERE age_days = 0")
        fresh_loaders = cur.fetchone()[0]
        print(f"✓ Loaders: {fresh_loaders} tables updated today")

        conn.close()
        return issues

    except Exception as e:
        return [f"✗ Database connection failed: {e}"]


def audit_dev_server():
    """Check if dev_server is running."""
    print("\n" + "="*70)
    print("DEV SERVER AUDIT")
    print("="*70)

    issues = []

    # Check port
    is_open = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', 3001))
        sock.close()
        is_open = (result == 0)
    except:
        pass

    if is_open:
        print("✓ Dev server running on localhost:3001")
        # Check health
        try:
            import requests
            resp = requests.get("http://localhost:3001/api/health", timeout=5)
            if resp.status_code == 200:
                print("✓ Dev server /api/health OK")
            else:
                issues.append(f"⚠ Dev server health check returned {resp.status_code}")
        except:
            issues.append("⚠ Dev server not responding to health check")
    else:
        issues.append("✗ Dev server NOT running on port 3001 (required for dashboard)")
        issues.append("  FIX: Run: python start_dashboard_dev.py")

    return issues


def audit_orchestrator():
    """Check orchestrator execution."""
    print("\n" + "="*70)
    print("ORCHESTRATOR AUDIT")
    print("="*70)

    issues = []

    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            user=os.getenv('DB_USER', 'stocks'),
            password=os.getenv('DB_PASSWORD', 'stocks'),
            database=os.getenv('DB_NAME', 'stocks'),
            connect_timeout=5,
        )
        cur = conn.cursor()

        # Check last run
        cur.execute("""
        SELECT started_at, phase_results, summary
        FROM algo_orchestrator_runs
        ORDER BY started_at DESC LIMIT 1
        """)
        row = cur.fetchone()

        if not row:
            issues.append("✗ No orchestrator runs found in database")
        else:
            started_at, status, summary = row
            age_hours = (datetime.now(timezone.utc) - started_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600

            if status == 'success':
                print(f"✓ Last run: {age_hours:.1f} hours ago - {status}")
            else:
                issues.append(f"✗ Last run failed: {status}")
                if summary:
                    issues.append(f"  Summary: {summary[:100]}")

            # Check if running too fast (indicates dry-run or error)
            if age_hours < 1:
                cur.execute("""
                SELECT COUNT(*) FROM algo_orchestrator_runs
                WHERE started_at > NOW() - INTERVAL '1 hour'
                AND status = 'success'
                """)
                recent_count = cur.fetchone()[0]
                if recent_count > 5:
                    issues.append(f"⚠ {recent_count} runs in last hour (very frequent - check if DRY_RUN is enabled)")

        # Check Phase 8 & 9 (trading & reconciliation)
        cur.execute("""
        SELECT phases FROM algo_orchestrator_runs
        ORDER BY started_at DESC LIMIT 1
        """)
        phases_row = cur.fetchone()
        if phases_row:
            phases_json = phases_row[0]
            if isinstance(phases_json, str):
                import json
                phases = json.loads(phases_json)
            else:
                phases = phases_json

            phase_8 = next((p for p in phases if p.get('action_type') == 'Phase 8'), None)
            phase_9 = next((p for p in phases if p.get('action_type') == 'Phase 9'), None)

            if phase_8:
                if phase_8.get('status') == 'success':
                    print(f"✓ Phase 8 (Trading): {phase_8.get('status')}")
                else:
                    issues.append(f"⚠ Phase 8 (Trading) status: {phase_8.get('status')}")

            if phase_9:
                if phase_9.get('status') == 'success':
                    print(f"✓ Phase 9 (Reconciliation): {phase_9.get('status')}")
                else:
                    issues.append(f"⚠ Phase 9 (Reconciliation) status: {phase_9.get('status')}")

        conn.close()

    except Exception as e:
        issues.append(f"✗ Orchestrator check failed: {str(e)[:80]}")

    return issues


def audit_alpaca():
    """Check Alpaca configuration and trading setup."""
    print("\n" + "="*70)
    print("ALPACA TRADING AUDIT")
    print("="*70)

    issues = []

    # Check if Alpaca credentials exist in AWS Secrets Manager
    alpaca_key = os.getenv('ALPACA_API_KEY')
    alpaca_secret = os.getenv('ALPACA_SECRET_KEY')
    alpaca_paper = os.getenv('ALPACA_PAPER_TRADING', 'true').lower() == 'true'

    if alpaca_key:
        print(f"✓ Alpaca API Key configured (last 4: ...{alpaca_key[-4:]})")
    else:
        issues.append("✗ ALPACA_API_KEY not configured (required for paper trading)")

    if alpaca_secret:
        print("✓ Alpaca Secret Key configured")
    else:
        issues.append("✗ ALPACA_SECRET_KEY not configured (required for paper trading)")

    if alpaca_paper:
        print("✓ Paper trading mode: ENABLED")
    else:
        issues.append("⚠ Paper trading mode: DISABLED (currently in live/simulation mode)")

    if not alpaca_key or not alpaca_secret:
        issues.append("  FIX: Configure Alpaca credentials in AWS Secrets Manager")
        issues.append("  See: steering/SECRETS_MANAGEMENT_PLAYBOOK.md")

    return issues


def audit_dashboard():
    """Check dashboard module."""
    print("\n" + "="*70)
    print("DASHBOARD AUDIT")
    print("="*70)

    issues = []

    try:
        import dashboard
        print("✓ Dashboard module imports successfully")

        # Check if we can import fetchers
        from dashboard import fetchers
        print("✓ Dashboard fetchers module available")

    except Exception as e:
        issues.append(f"✗ Dashboard import failed: {str(e)[:80]}")

    return issues


def audit_data_freshness():
    """Check if data is fresh enough for trading."""
    print("\n" + "="*70)
    print("DATA FRESHNESS AUDIT")
    print("="*70)

    issues = []

    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            user=os.getenv('DB_USER', 'stocks'),
            password=os.getenv('DB_PASSWORD', 'stocks'),
            database=os.getenv('DB_NAME', 'stocks'),
            connect_timeout=5,
        )
        cur = conn.cursor()

        # Critical for trading: stock_scores (used to select positions)
        cur.execute("SELECT MAX(created_at) FROM stock_scores")
        row = cur.fetchone()
        if row and row[0]:
            age = (datetime.now(timezone.utc) - row[0].replace(tzinfo=timezone.utc)).total_seconds() / 3600
            if age < 24:
                print(f"✓ Stock scores: {age:.1f} hours old")
            else:
                issues.append(f"✗ Stock scores STALE: {age:.1f} hours old (>24h critical)")
        else:
            issues.append("✗ Stock scores: No data available")

        # Critical for trading: algo_signals (trade signals)
        cur.execute("SELECT MAX(signal_date) FROM algo_signals WHERE signal_active = true")
        row = cur.fetchone()
        if row and row[0]:
            from datetime import date as date_type
            if isinstance(row[0], date_type):
                age = (datetime.now(timezone.utc).date() - row[0]).days
                if age == 0:
                    print(f"✓ Active signals: Generated today")
                else:
                    issues.append(f"⚠ Active signals: {age} days old (from {row[0]})")
            else:
                age = (datetime.now(timezone.utc) - row[0].replace(tzinfo=timezone.utc)).total_seconds() / 3600
                if age < 24:
                    print(f"✓ Active signals: {age:.1f} hours old")
                else:
                    issues.append(f"⚠ Active signals: {age:.1f} hours old")
        else:
            issues.append("⚠ Active signals: None available (may be normal after hours)")

        conn.close()

    except Exception as e:
        issues.append(f"✗ Data freshness check failed: {str(e)[:80]}")

    return issues


def main():
    """Run all audits."""
    print("\n" + "="*70)
    print("COMPREHENSIVE SYSTEM AUDIT")
    print("="*70)

    all_issues = []

    # Run all audits
    all_issues.extend(audit_database())
    all_issues.extend(audit_dev_server())
    all_issues.extend(audit_orchestrator())
    all_issues.extend(audit_data_freshness())
    all_issues.extend(audit_dashboard())
    all_issues.extend(audit_alpaca())

    # Summary
    print("\n" + "="*70)
    print("AUDIT SUMMARY")
    print("="*70)

    if not all_issues:
        print("\n✓ ALL SYSTEMS OPERATIONAL")
        print("\nYou can now:")
        print("  1. Start dashboard: python start_dashboard_dev.py -w 30")
        print("  2. Monitor trading: Dashboard will show positions and trades")
        print("  3. Verify Alpaca: Check if trades are being executed")
        return 0
    else:
        print(f"\n✗ {len(all_issues)} ISSUE(S) FOUND:\n")
        for i, issue in enumerate(all_issues, 1):
            print(f"{i}. {issue}")

        print("\n" + "="*70)
        print("NEXT STEPS:")
        print("="*70)
        print("1. Address critical issues (✗) first")
        print("2. Run: python start_dashboard_dev.py (to start dev_server + dashboard)")
        print("3. Monitor health panel for remaining issues")
        return 1


if __name__ == "__main__":
    sys.exit(main())

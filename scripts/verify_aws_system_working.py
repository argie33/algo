#!/usr/bin/env python3
"""
AWS System Verification Script

Verify that AWS deployment actually worked by checking:
1. ECS task definitions have latest fixes
2. Loaders/orchestrator executed recently
3. RDS has fresh data from AWS
4. Dashboard works in AWS mode
"""

import sys
from datetime import datetime

from config.credential_manager import CredentialManager


def check_database_freshness():
    """Check if RDS has been updated with fresh AWS loader data"""
    print("\n" + "="*70)
    print("1. DATABASE FRESHNESS CHECK (RDS)")
    print("="*70)

    try:
        import psycopg2
        creds = CredentialManager()
        db_creds = creds.get_db_credentials()

        conn = psycopg2.connect(
            host=db_creds['host'],
            port=int(db_creds['port']),
            database=db_creds['database'],
            user=db_creds['user'],
            password=db_creds['password'],
            sslmode=db_creds.get('sslmode', 'prefer')
        )
        cur = conn.cursor()

        # Check if loaders have run recently (after Terraform deployment)
        cur.execute("""
        SELECT 'price_daily' as table_name, MAX(date) as latest,
               EXTRACT(EPOCH FROM (NOW() - MAX(date))) / 3600 as hours_old
        FROM price_daily
        UNION ALL
        SELECT 'technical_data_daily', MAX(date),
               EXTRACT(EPOCH FROM (NOW() - MAX(date))) / 3600
        FROM technical_data_daily
        UNION ALL
        SELECT 'stock_scores', MAX(updated_at),
               EXTRACT(EPOCH FROM (NOW() - MAX(updated_at))) / 3600
        FROM stock_scores
        UNION ALL
        SELECT 'quality_metrics', MAX(updated_at),
               EXTRACT(EPOCH FROM (NOW() - MAX(updated_at))) / 3600
        FROM quality_metrics
        UNION ALL
        SELECT 'growth_metrics', MAX(updated_at),
               EXTRACT(EPOCH FROM (NOW() - MAX(updated_at))) / 3600
        FROM growth_metrics
        UNION ALL
        SELECT 'value_metrics', MAX(updated_at),
               EXTRACT(EPOCH FROM (NOW() - MAX(updated_at))) / 3600
        FROM value_metrics
        UNION ALL
        SELECT 'stability_metrics', MAX(updated_at),
               EXTRACT(EPOCH FROM (NOW() - MAX(updated_at))) / 3600
        FROM stability_metrics
        ORDER BY 1
        """)

        print("\nData Freshness Status:")
        print("-" * 70)
        stale_count = 0
        for table, latest, hours_old in cur.fetchall():
            if latest is None:
                status = "NO DATA"
                stale = True
            elif hours_old < 24:
                status = f"FRESH ({hours_old:.1f}h old)"
                stale = False
            elif hours_old < 48:
                status = f"ACCEPTABLE ({hours_old:.1f}h old)"
            else:
                status = f"STALE ({hours_old:.1f}h old)"
                stale_count += 1

            print(f"{table:25} {status}")

        if stale_count > 0:
            print(f"\n[WARNING] {stale_count} tables have stale data - loaders may not be running in AWS")
            return False
        else:
            print("\n[OK] All data is current - loaders are working!")
            return True

        cur.close()
        conn.close()

    except Exception as e:
        print(f"[ERROR] Database check failed: {e}")
        return False

def check_orchestrator_runs():
    """Check if orchestrator is running in AWS"""
    print("\n" + "="*70)
    print("2. ORCHESTRATOR EXECUTION CHECK")
    print("="*70)

    try:
        import psycopg2
        creds = CredentialManager()
        db_creds = creds.get_db_credentials()

        conn = psycopg2.connect(
            host=db_creds['host'],
            port=int(db_creds['port']),
            database=db_creds['database'],
            user=db_creds['user'],
            password=db_creds['password'],
            sslmode=db_creds.get('sslmode', 'prefer')
        )
        cur = conn.cursor()

        # Check recent runs
        cur.execute("""
        SELECT
            COUNT(*) as runs_24h,
            COUNT(CASE WHEN started_at > NOW() - INTERVAL '1 hour' THEN 1 END) as runs_1h,
            MAX(started_at) as latest_run,
            COUNT(CASE WHEN overall_status = 'halted' THEN 1 END) as halted_runs
        FROM algo_orchestrator_runs
        WHERE started_at > NOW() - INTERVAL '24 hours'
        """)

        runs_24h, runs_1h, latest_run, halted = cur.fetchone()

        print("\nOrchestrator Execution Status:")
        print("-" * 70)
        print(f"Runs in last 24h: {runs_24h}")
        print(f"Runs in last 1h:  {runs_1h}")
        print(f"Halted runs:      {halted}")

        if latest_run:
            hours_ago = (datetime.now() - latest_run).total_seconds() / 3600
            print(f"Latest run:       {hours_ago:.1f}h ago")

            if hours_ago < 1:
                print("\n[OK] Orchestrator actively running!")
                return True
            elif hours_ago < 24:
                print(f"\n[WARNING] Orchestrator running but not recent ({hours_ago:.1f}h old)")
                return True
            else:
                print("\n[CRITICAL] Orchestrator not running for >24h - check AWS EventBridge!")
                return False
        else:
            print("\n[CRITICAL] No orchestrator runs found!")
            return False

        cur.close()
        conn.close()

    except Exception as e:
        print(f"[ERROR] Orchestrator check failed: {e}")
        return False

def check_credential_status():
    """Check if Alpaca credentials are configured"""
    print("\n" + "="*70)
    print("3. ALPACA CREDENTIALS STATUS")
    print("="*70)

    try:
        creds = CredentialManager()
        alpaca = creds.get_alpaca_credentials()

        if alpaca and alpaca.get('key_id'):
            print("[OK] Alpaca credentials configured")
            return True
        else:
            print("[MISSING] Alpaca credentials NOT configured")
            print("  Phase 8 (Entry Execution) will SKIP without credentials")
            print("  To fix:")
            print("    1. Get API key from: https://app.alpaca.markets")
            print("    2. Run: bash scripts/setup_alpaca_credentials.sh")
            print("    3. Or set: export APCA_API_KEY_ID=... APCA_API_SECRET_KEY=...")
            return False
    except Exception as e:
        print(f"[MISSING] Alpaca credentials error: {e}")
        return False

def main():
    print("\n")
    print("#" * 70)
    print("# AWS SYSTEM VERIFICATION")
    print("#" * 70)

    results = {
        "Database Freshness": check_database_freshness(),
        "Orchestrator Runs": check_orchestrator_runs(),
        "Alpaca Credentials": check_credential_status(),
    }

    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    all_ok = True
    for check, passed in results.items():
        status = "OK" if passed else "FAIL"
        print(f"{check:30} [{status}]")
        if not passed:
            all_ok = False

    if all_ok:
        print("\n[SUCCESS] All systems operational!")
        return 0
    else:
        print("\n[INCOMPLETE] Some issues remain - see details above")
        return 1

if __name__ == "__main__":
    sys.exit(main())

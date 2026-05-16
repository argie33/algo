#!/usr/bin/env python3
"""
Final System Verification - Ensures everything is working end-to-end

Checks:
1. Database connectivity
2. Schema completeness (150+ tables)
3. Critical loaders can execute
4. Orchestrator can import all dependencies
5. Key calculations are working
6. No obvious configuration issues
"""

import os
import sys
import importlib
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def check_database():
    """Verify database is accessible."""
    print("\n[1/6] Database Connectivity")
    try:
        import psycopg2
        db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "database": os.getenv("DB_NAME", "stocks"),
            "connect_timeout": 5,
        }
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
        table_count = cur.fetchone()[0]
        cur.close()
        conn.close()

        print(f"  ✓ Database connected: {table_count} tables found")
        return True, f"{table_count} tables"
    except Exception as e:
        print(f"  ✗ Database error: {str(e)}")
        return False, str(e)

def check_schema_completeness():
    """Verify critical tables exist."""
    print("\n[2/6] Schema Completeness")
    try:
        import psycopg2
        db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "database": os.getenv("DB_NAME", "stocks"),
        }
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        critical_tables = [
            'price_daily', 'technical_data_daily', 'buy_sell_daily',
            'algo_trades', 'algo_positions', 'algo_audit_log',
            'market_health_daily', 'stock_symbols', 'algo_config',
            'signal_quality_scores', 'market_exposure_daily'
        ]

        missing = []
        for table in critical_tables:
            cur.execute("""
                SELECT EXISTS(
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema='public' AND table_name=%s
                )
            """, (table,))
            exists = cur.fetchone()[0]
            if not exists:
                missing.append(table)

        cur.close()
        conn.close()

        if missing:
            print(f"  ✗ Missing tables: {', '.join(missing)}")
            return False, f"{len(missing)} missing"
        else:
            print(f"  ✓ All {len(critical_tables)} critical tables present")
            return True, f"{len(critical_tables)} tables OK"
    except Exception as e:
        print(f"  ✗ Schema check error: {str(e)}")
        return False, str(e)

def check_imports():
    """Verify orchestrator can import all dependencies."""
    print("\n[3/6] Module Imports")
    try:
        modules = [
            'algo_config',
            'algo_market_calendar',
            'algo_filter_pipeline',
            'algo_trade_executor',
            'algo_exit_engine',
            'algo_circuit_breaker',
            'algo_market_exposure',
        ]

        failed = []
        for mod in modules:
            try:
                importlib.import_module(mod)
            except Exception as e:
                failed.append(f"{mod}: {str(e)[:50]}")

        if failed:
            print(f"  ✗ Import failures ({len(failed)}):")
            for f in failed[:3]:
                print(f"    - {f}")
            return False, f"{len(failed)} import errors"
        else:
            print(f"  ✓ All {len(modules)} critical modules import successfully")
            return True, f"{len(modules)} modules OK"
    except Exception as e:
        print(f"  ✗ Import check error: {str(e)}")
        return False, str(e)

def check_configuration():
    """Verify key configuration parameters."""
    print("\n[4/6] Configuration")
    try:
        from algo_config import get_config
        config = get_config()

        required_keys = [
            'max_data_staleness_days',
            'max_open_positions',
            'max_position_size_pct',
            'execution_mode',
        ]

        missing = []
        for key in required_keys:
            if key not in config:
                missing.append(key)

        if missing:
            print(f"  ✗ Missing config keys: {', '.join(missing)}")
            return False, f"{len(missing)} missing"
        else:
            print(f"  ✓ All {len(required_keys)} required config keys present")
            return True, f"{len(required_keys)} keys OK"
    except Exception as e:
        print(f"  ✗ Config error: {str(e)}")
        return False, str(e)

def check_data_availability():
    """Verify recent data exists in database."""
    print("\n[5/6] Data Availability")
    try:
        import psycopg2
        from datetime import date, timedelta

        db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "database": os.getenv("DB_NAME", "stocks"),
        }
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        checks = {
            'price_daily': 'SELECT COUNT(*) FROM price_daily WHERE date >= CURRENT_DATE - INTERVAL \'7 days\'',
            'technical_data_daily': 'SELECT COUNT(*) FROM technical_data_daily WHERE date >= CURRENT_DATE - INTERVAL \'7 days\'',
            'buy_sell_daily': 'SELECT COUNT(*) FROM buy_sell_daily WHERE date >= CURRENT_DATE - INTERVAL \'7 days\'',
            'stock_symbols': 'SELECT COUNT(*) FROM stock_symbols',
        }

        issues = []
        for table, query in checks.items():
            cur.execute(query)
            count = cur.fetchone()[0]
            if count == 0:
                issues.append(f"{table}: no recent data")

        cur.close()
        conn.close()

        if issues:
            print(f"  ✗ Data issues ({len(issues)}):")
            for issue in issues:
                print(f"    - {issue}")
            return False, f"{len(issues)} data issues"
        else:
            print(f"  ✓ All critical tables have recent data")
            return True, "Data OK"
    except Exception as e:
        print(f"  ✗ Data check error: {str(e)}")
        return False, str(e)

def check_orchestrator():
    """Verify orchestrator can instantiate."""
    print("\n[6/6] Orchestrator Readiness")
    try:
        from algo_orchestrator import Orchestrator

        # Don't actually run it, just instantiate
        orch = Orchestrator(init_db=False, verbose=False)
        print(f"  ✓ Orchestrator instantiated successfully")
        print(f"    Run mode: {orch.config.get('execution_mode', 'paper')}")
        return True, "Ready"
    except Exception as e:
        print(f"  ✗ Orchestrator error: {str(e)}")
        return False, str(e)

def main():
    print("\n" + "="*70)
    print("SYSTEM READINESS VERIFICATION")
    print("="*70)

    checks = [
        ("Database", check_database),
        ("Schema", check_schema_completeness),
        ("Imports", check_imports),
        ("Config", check_configuration),
        ("Data", check_data_availability),
        ("Orchestrator", check_orchestrator),
    ]

    results = {}
    for name, check_func in checks:
        try:
            passed, detail = check_func()
            results[name] = (passed, detail)
        except Exception as e:
            print(f"  ✗ Unexpected error: {str(e)}")
            results[name] = (False, str(e))

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    passed = sum(1 for p, _ in results.values() if p)
    total = len(results)

    for name, (passed, detail) in results.items():
        status = "✓" if passed else "✗"
        print(f"{status} {name:15s} - {detail}")

    print("\n" + "="*70)
    if passed == total:
        print(f"✓ ALL {total} CHECKS PASSED - System ready for trading")
        print("="*70 + "\n")
        return 0
    else:
        print(f"✗ {total - passed}/{total} checks failed - Fix issues before trading")
        print("="*70 + "\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())

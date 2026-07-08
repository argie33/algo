#!/usr/bin/env python3
"""Comprehensive orchestrator and database state diagnostic."""

import sys
from pathlib import Path
from datetime import datetime
import json

sys.path.insert(0, str(Path.cwd()))

from utils.db.context import DatabaseContext

def run_diagnostics():
    """Run all diagnostic queries and return structured output."""

    diagnostics = {
        "timestamp": datetime.now().isoformat(),
        "orchestrator_status": None,
        "data_freshness": {},
        "loader_status": {},
        "missing_config_keys": [],
        "coverage": {},
        "errors": []
    }

    # 1. Portfolio snapshots - last successful run
    print("[1/7] Checking portfolio snapshots...")
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    id,
                    created_at,
                    snapshot_date,
                    total_portfolio_value
                FROM algo_portfolio_snapshots
                ORDER BY created_at DESC
                LIMIT 5
            """)
            snapshots = cur.fetchall()
            if snapshots:
                latest = snapshots[0]
                age_seconds = (datetime.now() - latest[1]).total_seconds() if latest[1] else None
                diagnostics["data_freshness"]["portfolio_snapshots"] = {
                    "latest_timestamp": latest[1].isoformat() if latest[1] else None,
                    "age_seconds": age_seconds,
                    "snapshot_date": latest[2].isoformat() if latest[2] else None,
                    "last_5_runs": [
                        {
                            "created_at": s[1].isoformat() if s[1] else None,
                            "snapshot_date": s[2].isoformat() if s[2] else None,
                            "total_value": float(s[3]) if s[3] else None
                        }
                        for s in snapshots
                    ]
                }
                print(f"  OK: Latest snapshot: {latest[1]}")
    except Exception as e:
        diagnostics["errors"].append(f"portfolio_snapshots: {str(e)[:100]}")
        print(f"  ERROR: {e}")

    # 2. Orchestrator execution history
    print("[2/7] Checking orchestrator execution history...")
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    run_id,
                    run_date,
                    started_at,
                    completed_at,
                    overall_status,
                    halt_reason
                FROM algo_orchestrator_runs
                ORDER BY run_date DESC
                LIMIT 10
            """)
            runs = cur.fetchall()
            orchestrator_runs = []
            for run in runs:
                orchestrator_runs.append({
                    "run_id": run[0],
                    "run_date": run[1].isoformat() if run[1] else None,
                    "started_at": run[2].isoformat() if run[2] else None,
                    "completed_at": run[3].isoformat() if run[3] else None,
                    "overall_status": run[4],
                    "halt_reason": run[5]
                })

            diagnostics["orchestrator_status"] = {
                "last_10_runs": orchestrator_runs
            }

            if orchestrator_runs:
                latest_run = orchestrator_runs[0]
                print(f"  OK: Latest run: {latest_run['run_date']} - Status: {latest_run['overall_status']}")
                if latest_run.get('halt_reason'):
                    print(f"      Halt reason: {latest_run['halt_reason'][:80]}")
    except Exception as e:
        diagnostics["errors"].append(f"orchestrator_runs: {str(e)[:100]}")
        print(f"  ERROR: {e}")

    # 3. Data loader status
    print("[3/7] Checking data loader status...")
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    table_name,
                    frequency,
                    latest_date,
                    age_days,
                    row_count,
                    status,
                    error_message,
                    last_updated,
                    symbol_count,
                    symbols_loaded
                FROM data_loader_status
                ORDER BY last_updated DESC
            """)
            loaders = cur.fetchall()
            for loader in loaders:
                diagnostics["loader_status"][loader[0]] = {
                    "frequency": loader[1],
                    "latest_date": loader[2].isoformat() if loader[2] else None,
                    "age_days": loader[3],
                    "row_count": loader[4],
                    "status": loader[5],
                    "error_message": loader[6][:100] if loader[6] else None,
                    "last_updated": loader[7].isoformat() if loader[7] else None,
                    "symbol_count": loader[8],
                    "symbols_loaded": loader[9]
                }

            failed_loaders = [name for name, status in diagnostics["loader_status"].items()
                              if status.get("status", "").lower() in ["error", "failed"]]
            stale_loaders = [name for name, status in diagnostics["loader_status"].items()
                             if status.get("status", "").lower() == "stale"]

            if failed_loaders:
                print(f"  ERROR: Failed loaders: {', '.join(failed_loaders)}")
            if stale_loaders:
                print(f"  WARNING: Stale loaders: {', '.join(stale_loaders)}")
            if not (failed_loaders or stale_loaders):
                print(f"  OK: All {len(loaders)} loaders in good status")
    except Exception as e:
        diagnostics["errors"].append(f"data_loader_status: {str(e)[:100]}")
        print(f"  ERROR: {e}")

    # 4. Config keys check
    print("[4/7] Checking critical config keys...")
    critical_keys = [
        'yfinance_market_close_timeout_eod_sec',
        'yfinance_market_close_timeout_morning_sec',
        'price_daily_coverage_threshold_pct',
        'technical_daily_coverage_threshold_pct',
        'buy_sell_daily_coverage_threshold_pct'
    ]

    try:
        config_found = []
        for key in critical_keys:
            with DatabaseContext("read") as cur:
                cur.execute("""
                    SELECT key, value, updated_at
                    FROM algo_config
                    WHERE key = %s
                """, (key,))
                result = cur.fetchone()
                if result:
                    config_found.append(key)
                    print(f"  OK: {key}: {result[1]}")
                else:
                    diagnostics["missing_config_keys"].append(key)
                    print(f"  ERROR: {key}: MISSING")
    except Exception as e:
        diagnostics["errors"].append(f"algo_config: {str(e)[:100]}")
        print(f"  ERROR: {e}")

    # 5. Price daily coverage
    print("[5/7] Checking price_daily coverage...")
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as count,
                    MAX(date) as latest_date,
                    COUNT(DISTINCT symbol) as symbols
                FROM price_daily
            """)
            result = cur.fetchone()
            if result:
                price_count, latest_date, symbols = result[0], result[1], result[2]

                # Get total symbols in universe
                cur.execute("SELECT COUNT(DISTINCT symbol) FROM stock_scores")
                total_symbols_result = cur.fetchone()
                total_symbols = total_symbols_result[0] if total_symbols_result else 0

                coverage_pct = (symbols / total_symbols * 100) if total_symbols > 0 else 0

                diagnostics["coverage"]["price_daily"] = {
                    "total_rows": price_count,
                    "symbols_with_data": symbols,
                    "total_symbols": total_symbols,
                    "coverage_percentage": round(coverage_pct, 2),
                    "latest_date": latest_date.isoformat() if latest_date else None
                }
                print(f"  OK: Coverage: {coverage_pct:.1f}% ({symbols}/{total_symbols} symbols)")
                print(f"      Latest date: {latest_date}")
    except Exception as e:
        diagnostics["errors"].append(f"price_daily: {str(e)[:100]}")
        print(f"  ERROR: {e}")

    # 6. Technical data daily coverage
    print("[6/7] Checking technical_data_daily coverage...")
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as count,
                    MAX(date) as latest_date,
                    COUNT(DISTINCT symbol) as symbols
                FROM technical_data_daily
            """)
            result = cur.fetchone()
            if result:
                tech_count, latest_date, symbols = result[0], result[1], result[2]

                # Get total symbols in universe
                cur.execute("SELECT COUNT(DISTINCT symbol) FROM stock_scores")
                total_symbols_result = cur.fetchone()
                total_symbols = total_symbols_result[0] if total_symbols_result else 0

                coverage_pct = (symbols / total_symbols * 100) if total_symbols > 0 else 0

                diagnostics["coverage"]["technical_data_daily"] = {
                    "total_rows": tech_count,
                    "symbols_with_data": symbols,
                    "total_symbols": total_symbols,
                    "coverage_percentage": round(coverage_pct, 2),
                    "latest_date": latest_date.isoformat() if latest_date else None
                }
                print(f"  OK: Coverage: {coverage_pct:.1f}% ({symbols}/{total_symbols} symbols)")
                print(f"      Latest date: {latest_date}")
    except Exception as e:
        diagnostics["errors"].append(f"technical_data_daily: {str(e)[:100]}")
        print(f"  ERROR: {e}")

    # 7. Buy-sell signals
    print("[7/7] Checking buy_sell_daily signals...")
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as count,
                    MAX(date) as latest_date,
                    COUNT(DISTINCT symbol) as symbols
                FROM buy_sell_daily
            """)
            result = cur.fetchone()
            if result:
                signal_count, latest_date, symbols = result[0], result[1], result[2]

                diagnostics["coverage"]["buy_sell_daily"] = {
                    "total_signals": signal_count,
                    "symbols_with_signals": symbols,
                    "latest_date": latest_date.isoformat() if latest_date else None
                }
                print(f"  OK: Signals: {signal_count} ({symbols} symbols)")
                print(f"      Latest date: {latest_date}")

                # Get latest signal breakdown
                if latest_date:
                    cur.execute("""
                        SELECT signal_type, COUNT(*) as count
                        FROM buy_sell_daily
                        WHERE date = %s
                        GROUP BY signal_type
                    """, (latest_date,))
                    signal_breakdown = cur.fetchall()
                    diagnostics["coverage"]["buy_sell_daily"]["latest_breakdown"] = {
                        row[0]: row[1] for row in signal_breakdown
                    }
    except Exception as e:
        diagnostics["errors"].append(f"buy_sell_daily: {str(e)[:100]}")
        print(f"  ERROR: {e}")

    return diagnostics

if __name__ == "__main__":
    print("\n" + "="*60)
    print("ORCHESTRATOR AND DATABASE DIAGNOSTIC CHECK")
    print("="*60 + "\n")

    results = run_diagnostics()

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    if results.get("missing_config_keys"):
        print(f"\nMISSING CONFIG KEYS: {results['missing_config_keys']}")

    if results.get("errors"):
        print(f"\nERRORS ENCOUNTERED:")
        for err in results["errors"]:
            print(f"  - {err}")

    print("\n" + json.dumps(results, indent=2, default=str))

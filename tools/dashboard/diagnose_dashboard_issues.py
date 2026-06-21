#!/usr/bin/env python3
"""Diagnostic tool to identify data loading and display issues in the dashboard."""

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from tools.dashboard.error_boundary import has_error
from tools.dashboard.fetchers import load_all


ET = ZoneInfo("America/New_York")


def diagnose_data_issues():
    """Load all dashboard data and report what's broken vs working."""
    print("\n" + "=" * 80)
    print("DASHBOARD DATA DIAGNOSTIC")
    print(f"Time: {datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S ET')}")
    print("=" * 80 + "\n")

    try:
        print("[*] Loading all dashboard data...")
        data = load_all()

        # Check which datasets have errors
        error_count = 0
        ok_count = 0
        endpoints = {
            "run": "Last algo run",
            "cfg": "Algo config",
            "mkt": "Market data",
            "port": "Portfolio",
            "perf": "Performance",
            "pos": "Positions",
            "sig": "Signals",
            "trades": "Trades",
            "health": "Data health",
            "cb": "Circuit breakers",
            "srank": "Sector rankings",
            "activity": "Activity log",
            "eco": "Economic indicators",
            "notifs": "Notifications",
            "sentiment": "Market sentiment",
            "econ_cal": "Economic calendar",
            "risk": "Risk metrics",
            "perf_anl": "Performance analytics",
            "sig_eval": "Signal evaluation",
            "sec_rot": "Sector rotation",
            "algo_metrics": "Algo metrics",
            "irank": "Industry rankings",
            "audit": "Audit log",
            "exec_hist": "Execution history",
            "exp_factors": "Exposure factors",
            "scores": "Stock scores",
        }

        print("\n" + "-" * 80)
        print("DATA STATUS REPORT")
        print("-" * 80)

        for key, label in endpoints.items():
            value = data.get(key)

            if has_error(value):
                error_msg = value.get("_error", "Unknown error")
                print(f"[X] {label:30} - ERROR")
                print(f"     {error_msg}")
                error_count += 1
            elif value is None:
                print(f"[?] {label:30} - MISSING (None)")
                error_count += 1
            elif isinstance(value, dict) and "_error" not in value:
                print(f"[OK] {label:30} - OK")
                ok_count += 1
            elif isinstance(value, list):
                print(f"[OK] {label:30} - OK (list with {len(value)} items)")
                ok_count += 1
            else:
                print(f"[?] {label:30} - UNKNOWN TYPE: {type(value).__name__}")

        print("\n" + "-" * 80)
        print(f"SUMMARY: {ok_count} OK, {error_count} BROKEN/MISSING")
        print("-" * 80)

        # Show critical data that must be present
        print("\n" + "-" * 80)
        print("CRITICAL FIELDS CHECK")
        print("-" * 80)

        mkt = data.get("mkt")
        if not has_error(mkt):
            spy = mkt.get("spy")
            vix = mkt.get("vix")
            print(f"Market - SPY: {spy}, VIX: {vix}")
        else:
            print(f"Market [ERROR]: {mkt.get('_error', 'Unknown')}")

        port = data.get("port")
        if not has_error(port):
            total_value = port.get("total_portfolio_value")
            cash = port.get("total_cash")
            print(f"Portfolio - Total Value: {total_value}, Cash: {cash}")
        else:
            print(f"Portfolio [ERROR]: {port.get('_error', 'Unknown')}")

        pos = data.get("pos")
        if not has_error(pos):
            items = pos.get("items") if isinstance(pos, dict) else pos
            item_count = len(items) if isinstance(items, list) else "?"
            print(f"Positions - Count: {item_count}")
        else:
            print(f"Positions [ERROR]: {pos.get('_error', 'Unknown')}")

        print("\n" + "=" * 80)
        print("END DIAGNOSTIC")
        print("=" * 80 + "\n")

        return error_count == 0

    except Exception as e:
        print(f"\n[FATAL] Diagnostic failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = diagnose_data_issues()
    sys.exit(0 if success else 1)

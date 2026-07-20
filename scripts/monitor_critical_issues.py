#!/usr/bin/env python3
"""Monitor for critical issues that caused 9-day outage.

Session 288 audit found:
1. AWS credentials expiry (blocks all loaders)
2. Data staleness (25+ tables from July 10)
3. Loader failures (28/30 loaders not running)

This script checks for these issues and alerts operators.

Usage:
  python3 scripts/monitor_critical_issues.py              # One-time check
  python3 scripts/monitor_critical_issues.py --watch 60   # Poll every 60 seconds
"""

import argparse
import sys
import time
from datetime import datetime, timezone

from utils.db.context import DatabaseContext


def check_aws_credentials() -> dict[str, bool | str]:
    """Check if AWS credentials are valid."""
    try:
        import boto3
        from botocore.exceptions import ClientError

        sts = boto3.client("sts", region_name="us-east-1")
        response = sts.get_caller_identity()
        return {
            "ok": True,
            "account_id": response.get("Account"),
            "user": response.get("Arn"),
        }
    except ClientError as e:
        return {
            "ok": False,
            "error": str(e),
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Could not check AWS credentials: {e}",
        }


def check_loaders_running() -> dict:
    """Check if loaders have run in the last 24 hours."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
            SELECT
              loader_name,
              COUNT(*) as runs_24h,
              MAX(run_date) as last_run
            FROM data_loader_runs
            WHERE started_at > NOW() - INTERVAL '24 hours'
            GROUP BY loader_name
            ORDER BY last_run DESC
            """)

            recent_loaders = {}
            for row in cur.fetchall():
                recent_loaders[row[0]] = {
                    "runs_24h": row[1],
                    "last_run": row[2],
                }

            # Critical loaders that must run daily
            critical = [
                "loadpricedaily",
                "load_financial_statements",
                "load_stock_scores",
                "load_buy_sell_daily",
                "load_market_exposure_daily",
            ]

            missing = [loader for loader in critical if loader not in recent_loaders]

            return {
                "recent_loaders": len(recent_loaders),
                "missing_critical": missing,
                "details": recent_loaders,
            }
    except Exception as e:
        return {"error": str(e)}


def check_data_staleness() -> dict:
    """Check if critical tables are stale."""
    try:
        with DatabaseContext("read") as cur:
            # Critical tables that must be fresh daily
            critical_tables = [
                "price_daily",
                "market_health_daily",
                "market_exposure_daily",
                "stock_scores",
                "buy_sell_daily",
                "technical_data_daily",
            ]

            cur.execute("""
            SELECT
              table_name,
              status,
              age_days,
              last_updated,
              row_count
            FROM data_loader_status
            WHERE table_name = ANY(%s)
            ORDER BY age_days DESC NULLS LAST
            """, (critical_tables,))

            stale = []
            for row in cur.fetchall():
                table, _status, age, updated, count = row
                if age is not None and age > 0:
                    stale.append({
                        "table": table,
                        "age_days": age,
                        "last_updated": updated,
                        "rows": count,
                    })

            return {
                "stale_tables": len(stale),
                "details": stale,
            }
    except Exception as e:
        return {"error": str(e)}


def check_loader_errors() -> dict:
    """Check for recent loader failures."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
            SELECT
              loader_name,
              COUNT(*) as failures_24h,
              MAX(started_at) as latest_failure
            FROM data_loader_runs
            WHERE status = 'failed'
              AND started_at > NOW() - INTERVAL '24 hours'
            GROUP BY loader_name
            ORDER BY failures_24h DESC
            """)

            failures = {}
            for row in cur.fetchall():
                failures[row[0]] = {
                    "failures": row[1],
                    "latest": row[2],
                }

            return {
                "failed_loaders": len(failures),
                "details": failures,
            }
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Monitor for critical system issues")
    parser.add_argument("--watch", type=int, help="Poll every N seconds (default: run once)")
    args = parser.parse_args()

    while True:
        print("\n" + "=" * 70)
        print(f"[CRITICAL ISSUES MONITOR] {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 70)

        # AWS Credentials
        print("\n[AWS CREDENTIALS]")
        creds = check_aws_credentials()
        if creds["ok"]:
            print(f"  OK: Account {creds['account_id']}")
        else:
            print(f"  CRITICAL: {creds['error']}")
            print("  ACTION: Run 'aws configure' to refresh credentials")

        # Loaders
        print("\n[LOADER HEALTH]")
        loaders = check_loaders_running()
        if "error" not in loaders:
            print(f"  Recent loaders (24h): {loaders['recent_loaders']}")
            if loaders["missing_critical"]:
                print(f"  CRITICAL: Missing critical loaders: {loaders['missing_critical']}")
                print("  ACTION: Check loader logs, EventBridge Scheduler status, AWS credentials")
            for name, info in list(loaders["details"].items())[:5]:
                print(f"    - {name}: last run {info['last_run']}")
        else:
            print(f"  ERROR: {loaders['error']}")

        # Data Staleness
        print("\n[DATA STALENESS]")
        stale = check_data_staleness()
        if "error" not in stale:
            if stale["stale_tables"] > 0:
                print(f"  CRITICAL: {stale['stale_tables']} tables stale")
                for t in stale["details"][:5]:
                    print(f"    - {t['table']:35s} | {t['age_days']} days old | updated {t['last_updated']}")
                print("  ACTION: Refresh AWS credentials, run loaders manually")
            else:
                print("  OK: All critical tables fresh")
        else:
            print(f"  ERROR: {stale['error']}")

        # Loader Errors
        print("\n[LOADER FAILURES (24H)]")
        errors = check_loader_errors()
        if "error" not in errors:
            if errors["failed_loaders"] > 0:
                print(f"  WARNING: {errors['failed_loaders']} loaders failing")
                for name, info in list(errors["details"].items())[:5]:
                    print(f"    - {name}: {info['failures']} failures, latest {info['latest']}")
            else:
                print("  OK: No recent loader failures")
        else:
            print(f"  ERROR: {errors['error']}")

        print("\n" + "=" * 70)

        if not args.watch:
            break

        print(f"Next check in {args.watch}s (Ctrl+C to stop)")
        time.sleep(args.watch)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMonitoring stopped")
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

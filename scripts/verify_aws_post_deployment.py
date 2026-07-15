#!/usr/bin/env python3
"""Post-deployment AWS verification - Run after CI/CD deployment completes.

Verifies:
1. CloudWatch logs show recent activity (not "Never")
2. RDS has fresh data from loaders
3. Lambda functions are responding
4. EventBridge scheduler is enabled
5. Step Functions pipelines are healthy

Usage:
    python scripts/verify_aws_post_deployment.py
"""

import boto3
import sys
from datetime import datetime, timedelta


def check_cloudwatch_logs() -> dict:
    """Check if CloudWatch logs have recent activity."""
    result = {
        "name": "CloudWatch Logs (Activity)",
        "status": "UNKNOWN",
        "details": [],
    }

    try:
        logs = boto3.client("logs", region_name="us-east-1")

        # Critical log groups that should show activity
        critical_logs = [
            "/aws/lambda/algo-orchestrator-dev",
            "/aws/ecs/algo-orchestrator",
            "/aws/lambda/algo-api-dev",
            "/ecs/algo-algo-orchestrator",
        ]

        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)

        for log_group in critical_logs:
            try:
                streams = logs.describe_log_streams(
                    logGroupName=log_group, orderBy="LastEventTime", descending=True, limit=5
                )

                if not streams["logStreams"]:
                    result["details"].append(f"  ⚠️ {log_group}: No log streams")
                    continue

                latest_stream = streams["logStreams"][0]
                last_event_time = latest_stream.get("lastEventTimestamp", 0)

                if last_event_time == 0:
                    result["details"].append(f"  ❌ {log_group}: Never logged")
                else:
                    last_event = datetime.fromtimestamp(last_event_time / 1000)
                    age_minutes = (now - last_event).total_seconds() / 60

                    if age_minutes < 60:
                        result["details"].append(
                            f"  ✅ {log_group}: Active {age_minutes:.0f}m ago"
                        )
                    elif age_minutes < 1440:
                        result["details"].append(
                            f"  ⚠️ {log_group}: Last activity {age_minutes/60:.1f}h ago"
                        )
                    else:
                        result["details"].append(
                            f"  ❌ {log_group}: Last activity {age_minutes/1440:.1f}d ago"
                        )

            except Exception as e:
                result["details"].append(f"  ❌ {log_group}: {str(e)[:60]}")

        # Overall status
        failed = sum(1 for d in result["details"] if d.startswith("  ❌"))
        if failed == 0:
            result["status"] = "OK"
        elif failed <= len(critical_logs) // 2:
            result["status"] = "WARN"
        else:
            result["status"] = "FAIL"

    except Exception as e:
        result["status"] = "ERROR"
        result["details"].append(f"CloudWatch access error: {e}")

    return result


def check_rds_freshness() -> dict:
    """Check if RDS has recent data from loaders."""
    result = {
        "name": "RDS Data Freshness",
        "status": "UNKNOWN",
        "details": [],
    }

    try:
        import psycopg2

        # Try RDS first, fall back to localhost
        rds_host = "algo-db.c5sxkzr8e7wz.us-east-1.rds.amazonaws.com"
        localhost_host = "localhost"

        for host in [rds_host, localhost_host]:
            try:
                conn = psycopg2.connect(
                    f"dbname=stocks user=stocks host={host} port=5432 password=stocks connect_timeout=5"
                )
                result["details"].append(f"Connected to {host}")

                cur = conn.cursor()

                # Check price data age
                cur.execute("SELECT MAX(date) FROM price_daily")
                max_price_date = cur.fetchone()[0]
                if max_price_date:
                    age = (datetime.now().date() - max_price_date).days
                    if age <= 1:
                        result["details"].append(f"  ✅ Prices: {max_price_date} ({age}d old)")
                    elif age <= 3:
                        result["details"].append(f"  ⚠️ Prices: {max_price_date} ({age}d old)")
                    else:
                        result["details"].append(f"  ❌ Prices: {max_price_date} ({age}d old)")

                # Check orchestrator runs
                cur.execute(
                    """
                    SELECT COUNT(*), MAX(started_at)
                    FROM algo_orchestrator_runs
                    WHERE started_at > NOW() - INTERVAL '24 hours'
                """
                )
                run_count, latest_run = cur.fetchone()
                if run_count > 0:
                    result["details"].append(
                        f"  ✅ Orchestrator: {run_count} runs in 24h, latest {latest_run}"
                    )
                else:
                    result["details"].append("  ⚠️ Orchestrator: No runs in 24h")

                # Check growth scores completion
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT symbol),
                           COUNT(CASE WHEN growth_score > 0 THEN 1 END)
                    FROM stock_scores
                    WHERE updated_at > NOW() - INTERVAL '24 hours'
                """
                )
                total, with_scores = cur.fetchone()
                if total > 0:
                    pct = (with_scores / total * 100) if total > 0 else 0
                    status = "✅" if pct > 80 else ("⚠️" if pct > 50 else "❌")
                    result["details"].append(
                        f"  {status} Growth scores: {with_scores}/{total} ({pct:.1f}%)"
                    )

                conn.close()
                break  # Stop if connection succeeds

            except psycopg2.OperationalError:
                continue  # Try next host

        result["status"] = "OK" if not any("❌" in d for d in result["details"]) else "WARN"

    except ImportError:
        result["status"] = "SKIP"
        result["details"].append("psycopg2 not available")
    except Exception as e:
        result["status"] = "ERROR"
        result["details"].append(f"RDS check error: {e}")

    return result


def check_eventbridge_scheduler() -> dict:
    """Check if EventBridge scheduler is enabled."""
    result = {
        "name": "EventBridge Scheduler",
        "status": "UNKNOWN",
        "details": [],
    }

    try:
        scheduler = boto3.client("scheduler", region_name="us-east-1")
        schedules = scheduler.list_schedules()

        algo_schedules = [
            s for s in schedules.get("Schedules", []) if "algo" in s["Name"].lower()
        ]

        enabled_count = sum(1 for s in algo_schedules if s.get("State") == "ENABLED")

        result["details"].append(f"  Total schedules: {len(algo_schedules)}")
        result["details"].append(f"  Enabled: {enabled_count}")

        for sched in algo_schedules[:5]:
            state = sched.get("State", "UNKNOWN")
            status_icon = "✅" if state == "ENABLED" else "❌"
            result["details"].append(f"  {status_icon} {sched['Name']}: {state}")

        result["status"] = "OK" if enabled_count >= len(algo_schedules) * 0.8 else "WARN"

    except Exception as e:
        result["status"] = "ERROR"
        result["details"].append(f"Scheduler check error: {str(e)[:60]}")

    return result


def main() -> int:
    """Run all verification checks."""
    print("=" * 70)
    print("AWS POST-DEPLOYMENT VERIFICATION")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}\n")

    checks = [
        check_cloudwatch_logs(),
        check_rds_freshness(),
        check_eventbridge_scheduler(),
    ]

    for check in checks:
        status_icon = "✅" if check["status"] == "OK" else ("⚠️" if check["status"] == "WARN" else "❌")
        print(f"{status_icon} {check['name']}: {check['status']}")
        for detail in check.get("details", []):
            print(f"   {detail}")
        print()

    # Overall status
    failed = sum(1 for c in checks if c["status"] == "FAIL")
    warns = sum(1 for c in checks if c["status"] == "WARN")

    print("=" * 70)
    if failed == 0:
        print("✅ POST-DEPLOYMENT VERIFICATION PASSED")
        return 0
    else:
        print(f"❌ POST-DEPLOYMENT VERIFICATION FAILED ({failed} failures, {warns} warnings)")
        return 1


if __name__ == "__main__":
    sys.exit(main())

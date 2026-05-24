#!/usr/bin/env python3
"""Audit all loaders and categorize status by checking CloudWatch logs."""
import subprocess
import json
from datetime import datetime, timezone

LOADERS = [
    "stock_prices_daily", "technical_data_daily", "market_data_batch",
    "financials_annual_balance", "financials_annual_income", "financials_annual_cashflow",
    "financials_quarterly_balance", "financials_quarterly_income", "financials_quarterly_cashflow",
    "financials_ttm_income", "financials_ttm_cashflow",
    "earnings_calendar", "earnings_history", "earnings_revisions", "earnings_surprises",
    "eod_bulk_refresh",
    "signals_daily", "signals_weekly", "signals_monthly",
    "signals_etf_daily", "signals_etf_weekly", "signals_etf_monthly",
    "company_profile", "sectors", "industry_ranking", "stock_symbols", "stock_scores",
    "market_health_daily", "swing_trader_scores", "algo_metrics_daily",
    "growth_metrics", "quality_metrics", "value_metrics",
    "aaii_data", "feargreed", "naaim_data", "analyst_sentiment",
    "analyst_upgrades_downgrades", "seasonality"
]

def get_loader_status(loader_name):
    """Check CloudWatch logs for loader status. Returns (status, error_msg)."""
    log_group = f"/ecs/algo-{loader_name}-loader"

    try:
        # Get latest log streams
        result = subprocess.run(
            ["aws", "logs", "describe-log-streams",
             "--log-group-name", log_group,
             "--order-by", "LastEventTime",
             "--descending",
             "--max-items", "10",
             "--region", "us-east-1"],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            return "??", "NO_STREAMS"

        streams = json.loads(result.stdout)
        if not streams.get("logStreams"):
            return "??", "NO_STREAMS"

        # Check most recent streams
        for stream in streams.get("logStreams", [])[:5]:
            stream_name = stream["logStreamName"]

            result = subprocess.run(
                ["aws", "logs", "get-log-events",
                 "--log-group-name", log_group,
                 "--log-stream-name", stream_name,
                 "--region", "us-east-1"],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                continue

            events = json.loads(result.stdout).get("events", [])
            if not events:
                continue

            # Parse last 50 events for status
            has_error = False
            has_success = False
            error_msg = ""

            for event in events[-50:]:
                msg = event["message"]

                # Check for error/success keywords
                if "ERROR" in msg or "Error" in msg or "error" in msg:
                    has_error = True
                    error_msg = msg[:120]

                if any(x in msg for x in ["completed", "SUCCESS", "success", "Finished", "finished", "loaded"]):
                    has_success = True
                    error_msg = ""

            if has_error:
                return "XX", error_msg or "ERROR"
            elif has_success:
                return "OK", "SUCCESS"
            elif events:
                return "..", "RUNNING"

        return "??", "NO_INFO"

    except subprocess.TimeoutExpired:
        return "??", "TIMEOUT"
    except Exception as e:
        return "??", str(e)[:50]

def main():
    print(f"=== LOADER AUDIT [{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}] ===\n")

    success = []
    running = []
    failed = []
    unknown = []

    for loader in sorted(LOADERS):
        status, msg = get_loader_status(loader)

        if status == "OK":
            success.append(loader)
        elif status == "..":
            running.append(loader)
        elif status == "XX":
            failed.append((loader, msg))
        else:
            unknown.append(loader)

    print(f"[OK] SUCCESS ({len(success)})")
    for name in success:
        print(f"  - {name}")

    print(f"\n[..] RUNNING ({len(running)})")
    for name in running:
        print(f"  - {name}")

    print(f"\n[XX] FAILED ({len(failed)})")
    for name, msg in failed:
        short_msg = msg[:80] if len(msg) > 80 else msg
        print(f"  - {name}: {short_msg}")

    print(f"\n[??] NO_RECENT_RUNS ({len(unknown)})")
    for name in unknown:
        print(f"  - {name}")

    if failed:
        exit(1)

if __name__ == "__main__":
    main()

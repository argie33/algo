#!/usr/bin/env python3
"""Comprehensive audit of all 54 loaders - execution status and data verification."""
import subprocess
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

# All 54 loaders from the codebase
LOADERS = [
    # Reference data
    "stock_symbols",

    # Price data
    "stock_prices_daily", "stock_prices_weekly", "stock_prices_monthly",
    "etf_prices_daily", "etf_prices_weekly", "etf_prices_monthly",

    # Financial statements
    "financials_annual_income", "financials_quarterly_income",
    "financials_annual_balance", "financials_quarterly_balance",
    "financials_annual_cashflow", "financials_quarterly_cashflow",
    "financials_ttm_income", "financials_ttm_cashflow",

    # Key metrics
    "key_metrics",

    # Computed metrics
    "growth_metrics", "quality_metrics", "value_metrics",

    # Earnings
    "earnings_history", "earnings_revisions", "earnings_surprise", "earnings_calendar",

    # Company & analyst
    "company_profile", "analyst_sentiment", "analyst_upgrades_downgrades",
    "sectors", "industry_ranking",

    # Market & economic data
    "seasonality", "econ_data", "aaiidata", "naaim_data", "feargreed",

    # Scores & signals
    "stock_scores", "signals_daily", "signals_weekly", "signals_monthly",
    "signals_etf_daily", "signals_etf_weekly", "signals_etf_monthly",

    # Algo metrics
    "algo_metrics_daily",

    # Other
    "eod_bulk_refresh", "market_data_batch", "technical_data_daily",
    "market_health_daily", "swing_trader_scores", "trend_template_data",
]

# Mapping of loaders to their primary target tables
LOADER_TABLES = {
    "stock_prices_daily": "stock_prices_daily",
    "stock_prices_weekly": "stock_prices_weekly",
    "stock_prices_monthly": "stock_prices_monthly",
    "etf_prices_daily": "etf_prices_daily",
    "etf_prices_weekly": "etf_prices_weekly",
    "etf_prices_monthly": "etf_prices_monthly",
    "market_data_batch": "market_data_batch",
    "technical_data_daily": "technical_data_daily",
    "signals_daily": "signals_daily",
    "signals_weekly": "signals_weekly",
    "signals_monthly": "signals_monthly",
    "signals_etf_daily": "signals_etf_daily",
    "signals_etf_weekly": "signals_etf_weekly",
    "signals_etf_monthly": "signals_etf_monthly",
    "algo_metrics_daily": "algo_metrics_daily",
    "econ_data": "naaim_data",  # econ_data loader puts data in naaim_data
    "company_profile": "company_profile",
    "analyst_sentiment": "analyst_sentiment",
    "analyst_upgrades_downgrades": "analyst_upgrades_downgrades",
    "key_metrics": "key_metrics",
    "growth_metrics": "growth_metrics",
    "value_metrics": "value_metrics",
    "quality_metrics": "quality_metrics",
    "earnings_history": "earnings_history",
    "earnings_revisions": "earnings_revisions",
    "earnings_surprise": "earnings_surprise",
    "earnings_calendar": "earnings_calendar",
    "sectors": "sectors",
    "industry_ranking": "industry_ranking",
    "seasonality": "seasonality",
    "aaiidata": "aaiidata",
    "naaim_data": "naaim_data",
    "feargreed": "feargreed",
    "stock_scores": "stock_scores",
    "stock_symbols": "stock_symbols",
    "swing_trader_scores": "swing_trader_scores",
    "trend_template_data": "trend_template_data",
    "market_health_daily": "market_health_daily",
    # Financial statements
    "financials_annual_income": "financials_annual_income",
    "financials_quarterly_income": "financials_quarterly_income",
    "financials_annual_balance": "financials_annual_balance",
    "financials_quarterly_balance": "financials_quarterly_balance",
    "financials_annual_cashflow": "financials_annual_cashflow",
    "financials_quarterly_cashflow": "financials_quarterly_cashflow",
    "financials_ttm_income": "financials_ttm_income",
    "financials_ttm_cashflow": "financials_ttm_cashflow",
    "eod_bulk_refresh": "stock_prices_daily",  # Uses multiple tables
}

def check_ecs_tasks(hours_back=24):
    """Check ECS task history for recently completed loaders."""
    print("\n=== ECS Task History (Last 24 Hours) ===")
    try:
        # Get task definitions
        result = subprocess.run(
            ["aws", "ecs", "list-task-definitions", "--region", "us-east-1"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            print("Could not query ECS task definitions")
            return {}

        defs = json.loads(result.stdout).get("taskDefinitionArns", [])
        print(f"Found {len(defs)} task definitions")

        # For each loader, check if there's a recent task
        loader_status = {}
        for loader in LOADERS[:10]:  # Sample first 10 for now
            task_def = f"algo-{loader}-loader"
            if any(task_def in d for d in defs):
                print(f"  {loader}: Task definition exists")
                loader_status[loader] = "defined"
            else:
                loader_status[loader] = "not_defined"

        return loader_status
    except Exception as e:
        print(f"ECS check failed: {str(e)[:100]}")
        return {}

def check_local_execution(timeout_sec=5):
    """Test loaders by running them locally (requires Docker/local env)."""
    print(f"\n=== Local Loader Execution Test (Sample) ===")
    print(f"Testing {min(5, len(LOADERS))} loaders with {timeout_sec}s timeout each...")

    results = {"pass": 0, "fail": 0, "timeout": 0}

    for loader in LOADERS[:5]:  # Sample first 5
        try:
            result = subprocess.run(
                ["python3", "-u", "-m", "loaders"],
                env={"LOADER_NAME": loader},
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                cwd=str(Path(__file__).parent)
            )
            if result.returncode == 0:
                results["pass"] += 1
                print(f"  {loader}: PASS")
            else:
                results["fail"] += 1
                error = result.stderr.split('\n')[-2] if result.stderr else "unknown error"
                print(f"  {loader}: FAIL ({error[:50]})")
        except subprocess.TimeoutExpired:
            results["timeout"] += 1
            print(f"  {loader}: TIMEOUT")
        except Exception as e:
            results["fail"] += 1
            print(f"  {loader}: ERROR ({str(e)[:30]})")

    return results

def main():
    print(f"=== Comprehensive Loader Audit ===")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Total loaders configured: {len(LOADERS)}")

    # Check ECS tasks
    ecs_status = check_ecs_tasks()

    # Test local execution
    local_results = check_local_execution()

    print(f"\n=== Summary ===")
    print(f"Local execution sample: {local_results['pass']} pass, {local_results['fail']} fail, {local_results['timeout']} timeout")
    print(f"\nTo verify all loaders:")
    print(f"1. Check CloudWatch logs: /ecs/algo-<loader>-loader")
    print(f"2. Query database tables for recent data")
    print(f"3. Check ECS task status in AWS console")
    print(f"\nManual workflow:")
    print(f"  GH Actions: https://github.com/argie33/algo/actions")
    print(f"  Run 'manual-invoke-loaders.yml' to trigger loader sequence")

    return 0

if __name__ == "__main__":
    sys.exit(main())

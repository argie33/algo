#!/usr/bin/env python3
"""Local data loader scheduler - runs loaders on a schedule for local development.

For local dev environments where AWS EventBridge isn't available.
Runs key loaders at scheduled times to keep data fresh (mirrors AWS's real multi-pipeline
EventBridge schedule in terraform/modules/pipeline/main.tf, plus a local-only reference pipeline):
- 2:00 AM ET: Morning pipeline (prices, technicals, market health - pre-market prep)
- 9:15 AM ET: Reference pipeline (SEC company info, earnings calendar; local-only, not in AWS)
- 3:30 PM ET: Metrics pipeline (CRITICAL: runs BEFORE signals to ensure stock_scores uses fresh
  fundamentals). Slow SEC/EDGAR fundamentals refresh: financials, 13F, insider, positioning,
  value/quality/growth. Must complete before signals pipeline so stock_scores can compute
  composite scores from today's fundamentals (2026-07-25 fix: was 7 PM, creating 3+ hour lag).
- 4:05 PM ET: Signals pipeline (re-fetches that day's CLOSING prices/technicals, then recomputes
  stock_scores/buy_sell_daily/signal_quality_scores/risk_metrics/algo_metrics/sector_industry -
  all DB-only/price-driven, no external API calls, so this must run every day regardless of
  whether "metrics" ran that day). Matches AWS's eod_pipeline timing/content exactly. CRITICAL:
  Runs AFTER metrics pipeline (3:30 PM) so stock_scores has fresh fundamentals. Also, nothing
  previously re-fetched closing prices after the 2 AM pre-market run at all in the daemon/
  Windows-Task-Scheduler paths. Both fixed 2026-07-21; see run_complete_loader_pipeline() in
  start_dashboard_dev.py, which now always runs this pipeline.

Usage:
  python3 scripts/local_loader_scheduler.py                # Run scheduler daemon
  python3 scripts/local_loader_scheduler.py --now morning  # Run morning pipeline now
  python3 scripts/local_loader_scheduler.py --now signals  # Run signals pipeline now
"""

import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# Configure logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

EASTERN_TZ = ZoneInfo("America/New_York")
LOADER_TIMEOUT_SECONDS = 3600  # 1 hour - allow loaders to fetch/transform data

# Loader definitions for each pipeline
# Note: Phase 2-4 consolidations mean multiple old loaders are now single consolidated loaders:
# - Phase 2: market_health_daily + market_exposure_daily + market_sentiment → market_status_daily
# - Phase 3: quality_growth_metrics + yfinance_derived_metrics → value_quality_growth_metrics
# - Phase 4: sector_rankings + industry_ranking + sector_performance → sector_industry_daily
# - Phase 5 (Session 211): load_sec_valuations replaces yfinance quoteSummary calls (PE/PB/PS/PEG/FCF)
LOADERS = {
    "morning": {
        "description": "Morning pipeline (2:00 AM ET): sentiment + prices + technicals + market status + FINRA short interest (Phase 1 optimization)",
        "loaders": [
            "load_naaim.py",  # Restored Session 301 - NAAIM factor (Core-12 market exposure input) was silently reading stale data after its loader was deleted Session ~283
            "load_aaii_sentiment.py",  # Restored Session 301 - AAII factor (Core-12 market exposure input), same bug as NAAIM. Requires Playwright (bot-protection bypass); run before load_market_status_daily.py which reads both.
            "load_prices.py",
            "load_technical_indicators.py",
            "load_trend_analysis.py",  # CRITICAL: Phase 1 freshness check requires trend_template_data
            "load_market_status_daily.py",
            "load_short_interest_finra.py",  # Phase 1: FINRA short interest (authoritative, replaces yfinance)
        ],
        "interval_hours": 24,
        "target_hour": 2,
        "target_minute": 0,
    },
    "reference": {
        "description": "Reference data (9:15 AM ET): SEC company info, earnings calendar",
        "loaders": [
            "load_company_info_sec.py",  # Phase 3: Replaces ~15% yfinance (company info)
            "load_earnings_calendar_sec.py",  # Phase 3: Replaces ~10% yfinance (earnings dates)
        ],
        "interval_hours": 24,
        "target_hour": 9,
        "target_minute": 15,
    },
    "metrics": {
        "description": "Metrics pipeline (3:30 PM ET, before signals): slow SEC/EDGAR fundamentals refresh - stock universe, financial statements, valuations, positioning, value/quality/growth. CRITICAL: Must run BEFORE signals pipeline so stock_scores uses fresh fundamentals. In start_dashboard_dev.py, skips only if growth_metrics/quality_metrics tables are <24h old (staleness gate, not completeness gate).",
        "loaders": [
            # Found+fixed 2026-07-20 (data-loading audit): market_constituents and economic_data
            # are wired into the AWS EOD Step Functions pipeline (terraform/modules/pipeline/main.tf)
            # but were missing from this local scheduler and from scripts/setup_windows_schedule.ps1's
            # --now metrics call - so local dev silently never auto-refreshed the stock/ETF universe
            # or FRED/DXY economic data unless someone ran the loader by hand. Re-added to match
            # prod's actual loader set.
            "load_market_constituents.py",  # Universe (stock_symbols/etf_symbols) - must run first; see algo/orchestrator/phase1_data_freshness.py
            "load_financial_statements.py",
            "load_sec_valuations.py",
            "load_sec_cash_flow_metrics.py",  # Working capital/CapEx/FCF computed from Phase 2 SEC statement tables (needs load_financial_statements.py first)
            "load_institutional_holdings_13f.py",  # Phase 2: SEC 13F institutional ownership (replaces ~20% yfinance)
            "load_insider_holdings_sec.py",  # Phase 2: SEC Form 4/5 insider holdings (replaces ~15% yfinance)
            "load_current_reports_8k.py",  # NEW: SEC Form 8-K material events (catalysts, M&A, leadership changes)
            "load_sec_segment_info.py",  # XBRL: Business segment disclosures (ASC 280) - NOTE: SEC companyfacts API incomplete for major companies (no segment revenue), returns data_unavailable markers
            "load_dividend_data.py",  # NEW: Dividend ex-dates and amounts (position management)
            "load_positioning_metrics.py",  # Reads from Phase 2 SEC tables + FINRA short interest
            "load_value_quality_growth_metrics.py",
            "load_economic_data.py",  # FRED (T10Y2Y/FEDFUNDS/BAMLH0A0HYM2/ICSA) + DXY
        ],
        "interval_hours": 24,
        "target_hour": 15,
        "target_minute": 30,
    },
    "signals": {
        "description": "Signals pipeline (4:05 PM ET, 5 min after market close - matches AWS eod_pipeline's real schedule): re-fetches that day's closing prices/technicals, then recomputes scores/signals from them. CRITICAL: Runs AFTER metrics pipeline completes so stock_scores can use fresh fundamentals. Must run every day regardless of whether 'metrics' ran, since these are price-driven (not fundamentals-driven).",
        "loaders": [
            # Local dev's only other price fetch is 'morning' at 2 AM ET (pre-market, i.e. still
            # showing the PREVIOUS close). Without re-fetching here, everything below would compute
            # off a full trading day of stale price/technical data whenever this pipeline is run on
            # its own schedule (daemon or Windows Task Scheduler) rather than chained after 'morning'
            # in the same invocation (as start_dashboard_dev.py does). Mirrors AWS's eod_pipeline
            # (terraform/modules/pipeline/main.tf), which re-runs stock_prices_daily/trend_template_data/
            # technical_data_daily immediately before buy_sell_daily for exactly this reason.
            "load_prices.py",
            "load_technical_indicators.py",
            "load_trend_analysis.py",
            "load_risk_metrics_daily.py",
            "load_stock_scores.py",
            "load_buy_sell_daily.py",  # EOD signals: depends on stock_scores (must be after load_stock_scores.py)
            "load_signal_quality_scores.py",  # Depends on buy_sell_daily (Session 307 restoration)
            "load_algo_metrics_daily.py",  # Portfolio stats/execution summary from algo_audit_log
            "load_sector_industry_daily.py",
            "load_insider_transaction_velocity.py",  # NEW: Insider buying/selling velocity patterns (confidence signals)
        ],
        "interval_hours": 24,
        "target_hour": 16,
        "target_minute": 5,
    },
}


def run_loader_now(loader_name):
    """Run a single loader immediately."""
    logger.info(f"Running loader: {loader_name}")

    loader_path = f"loaders/{loader_name}"
    if not os.path.exists(loader_path):
        logger.error(f"Loader not found: {loader_path}")
        return False

    try:
        env = os.environ.copy()
        env["LOCAL_MODE"] = "1"
        if loader_name == "load_financial_statements.py":
            # Matches terraform/modules/loaders/main.tf's "financials_all" ECS task
            # (LOADER_STATEMENT_TYPE=all): without this, the loader's own main() defaults
            # LOADER_STATEMENT_TYPE to "income" and only ever runs the income/annual combo
            # (see load_financial_statements.py's main()/load_all_statements() split).
            # Confirmed live 2026-07-20: a local `--now metrics` run refreshed
            # annual_income_statement but left annual_balance_sheet/annual_cash_flow/
            # quarterly_* untouched - a real AWS-vs-local parity gap, not by design (AWS's
            # ECS task sets this same env var explicitly for exactly this reason).
            env["LOADER_STATEMENT_TYPE"] = "all"
        result = subprocess.run(
            ["python3", loader_path],
            timeout=LOADER_TIMEOUT_SECONDS,
            check=False,
            env=env,
        )
        if result.returncode == 0:
            logger.info(f"✓ Loader succeeded: {loader_name}")
            return True
        else:
            logger.error(f"✗ Loader failed: {loader_name} (exit code {result.returncode})")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"✗ Loader timeout: {loader_name}")
        return False
    except Exception as e:
        logger.error(f"✗ Loader error: {loader_name} - {e}")
        return False


def run_pipeline(pipeline_name):
    """Run all loaders in a pipeline."""
    if pipeline_name not in LOADERS:
        logger.error(f"Unknown pipeline: {pipeline_name}")
        return False

    pipeline = LOADERS[pipeline_name]
    logger.info(f"\n{'=' * 70}")
    logger.info(f"Starting pipeline: {pipeline['description']}")
    logger.info(f"{'=' * 70}\n")

    success_count = 0
    for loader in pipeline["loaders"]:
        if run_loader_now(loader):
            success_count += 1
        time.sleep(2)  # Brief pause between loaders

    logger.info(f"\nPipeline {pipeline_name} completed: {success_count}/{len(pipeline['loaders'])} loaders succeeded\n")
    return success_count == len(pipeline["loaders"])


def time_until_next_run(target_hour, target_minute):
    now = datetime.now(EASTERN_TZ)
    next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

    # If the time has already passed today, schedule for tomorrow
    if next_run <= now:
        from datetime import timedelta

        next_run += timedelta(days=1)

    seconds_until = (next_run - now).total_seconds()
    return int(seconds_until), next_run


def is_trading_day(date_obj):
    """Check if date is a trading day (accounting for market holidays).

    Uses MarketCalendar.is_trading_day() to properly handle market holidays
    (Presidents Day, Thanksgiving, etc.) which would be incorrectly classified
    as trading days by simple weekday() checks.
    """
    from algo.infrastructure import MarketCalendar
    return MarketCalendar.is_trading_day(date_obj)


def scheduler_daemon():
    """Run as a daemon, checking every minute for scheduled runs."""
    logger.info("Local data loader scheduler started")
    logger.info(f"Timezone: {EASTERN_TZ}")
    logger.info("\nScheduled pipelines:")
    for name, config in LOADERS.items():
        logger.info(f"  {name}: {config['description']}")

    last_run = {}

    while True:
        try:
            now = datetime.now(EASTERN_TZ)

            # Check each pipeline
            for pipeline_name, pipeline in LOADERS.items():
                target_hour = pipeline["target_hour"]
                target_minute = pipeline["target_minute"]

                # Check if it's time to run
                if now.hour == target_hour and now.minute == target_minute:
                    # Make sure we only run once per day
                    last_key = f"{pipeline_name}_{now.date()}"
                    if last_key not in last_run:
                        # Check if today is a trading day
                        if is_trading_day(now):
                            logger.info(f"Running scheduled pipeline: {pipeline_name}")
                            run_pipeline(pipeline_name)
                            last_run[last_key] = True
                        else:
                            logger.info(f"Skipping {pipeline_name} - non-trading day")
                            last_run[last_key] = True

            # Clean up old entries (keep last 7 days)
            cutoff_date = (now - __import__("datetime").timedelta(days=7)).date()
            for key in list(last_run.keys()):
                if key.split("_")[1] < str(cutoff_date):
                    del last_run[key]

            # Sleep for 30 seconds before checking again
            time.sleep(30)

        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            time.sleep(60)


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        if sys.argv[1] == "--now":
            if len(sys.argv) < 3:
                logger.error("Usage: --now <pipeline_name>")
                sys.exit(1)
            pipeline_name = sys.argv[2]
            if run_pipeline(pipeline_name):
                sys.exit(0)
            else:
                sys.exit(1)
        else:
            logger.error(f"Unknown option: {sys.argv[1]}")
            sys.exit(1)
    else:
        # Run scheduler daemon
        scheduler_daemon()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Loader dispatcher - routes LOADER_NAME env var to correct loader script.

Usage (in ECS):
  python3 -m loaders (reads LOADER_NAME env var)

Example Terraform:
  {
    name  = "LOADER_NAME"
    value = "stock_prices_daily"
  }
"""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mapping of Terraform loader key → Python module to run
LOADER_MAP = {
    # Reference data
    "stock_symbols": "loaders.loadstocksymbols",

    # Price data (consolidated)
    "stock_prices_daily": "loaders.loadpricedaily",
    "stock_prices_weekly": "loaders.loadpricedaily",
    "stock_prices_monthly": "loaders.loadpricedaily",
    "etf_prices_daily": "loaders.loadpricedaily",
    "etf_prices_weekly": "loaders.loadpricedaily",
    "etf_prices_monthly": "loaders.loadpricedaily",

    # Financial statements (consolidated into 3 files: income_statement, balance_sheet, cash_flow)
    "financials_annual_income": "loaders.load_income_statement",
    "financials_quarterly_income": "loaders.load_income_statement",
    "financials_annual_balance": "loaders.load_balance_sheet",
    "financials_quarterly_balance": "loaders.load_balance_sheet",
    "financials_annual_cashflow": "loaders.load_cash_flow",
    "financials_quarterly_cashflow": "loaders.load_cash_flow",
    "financials_ttm_income": "loaders.load_income_statement",
    "financials_ttm_cashflow": "loaders.load_cash_flow",

    # Key metrics
    "key_metrics": "loaders.load_growth_metrics",

    # Computed metrics
    "growth_metrics": "loaders.load_growth_metrics",
    "quality_metrics": "loaders.load_quality_metrics",
    "value_metrics": "loaders.load_value_metrics",

    # Earnings data
    "earnings_history": "loaders.loadearningshistory",
    "earnings_revisions": "loaders.loadearningsrevisions",
    "earnings_surprise": "loaders.loadearningsrevisions",
    "earnings_calendar": "loaders.load_earnings_calendar",

    # Company & analyst data
    "company_profile": "loaders.load_company_profile",
    "analyst_sentiment": "loaders.load_analyst_sentiment_analysis",
    "analyst_upgrades_downgrades": "loaders.load_analyst_upgrade_downgrade",
    "sectors": "loaders.loadsectors",
    "industry_ranking": "loaders.load_industry_ranking",

    # Market & economic data
    "market_indices": "loaders.loadstocksymbols",  # Placeholder
    "seasonality": "loaders.loadseasonality",
    "econ_data": "loaders.loadstocksymbols",  # Placeholder - uses FRED
    "aaiidata": "loaders.load_aaii_sentiment",
    "naaim_data": "loaders.load_naaim",
    "feargreed": "loaders.load_fear_greed_index",

    # Stock scores & signals (consolidated)
    "stock_scores": "loaders.load_quality_metrics",
    "signals_daily": "loaders.load_signal_quality_scores",
    "signals_weekly": "loaders.load_signal_quality_scores",
    "signals_monthly": "loaders.load_signal_quality_scores",
    "signals_etf_daily": "loaders.load_signal_quality_scores",
    "signals_etf_weekly": "loaders.load_signal_quality_scores",
    "signals_etf_monthly": "loaders.load_signal_quality_scores",

    # Algo metrics
    "algo_metrics_daily": "loaders.load_algo_metrics_daily",

    # EOD bulk refresh
    "eod_bulk_refresh": "loaders.loadpricedaily",  # Runs price loader

    # Market data batch
    "market_data_batch": "loaders.load_market_health_daily",

    # Technical indicators
    "technical_data_daily": "loaders.load_technical_data_daily",

    # Market health
    "market_health_daily": "loaders.load_market_health_daily",

    # Swing trader scores
    "swing_trader_scores": "loaders.load_swing_trader_scores",

    # Trend template
    "trend_template_data": "loaders.load_trend_criteria_data",

    # Weight optimization
    "weight_optimization": "loaders.load_weight_optimization",
}

def main():
    loader_name = os.getenv("LOADER_NAME")

    if not loader_name:
        print("ERROR: LOADER_NAME environment variable not set", file=sys.stderr)
        print(f"Available loaders: {', '.join(sorted(LOADER_MAP.keys()))}", file=sys.stderr)
        return 1

    if loader_name not in LOADER_MAP:
        print(f"ERROR: Unknown loader: {loader_name}", file=sys.stderr)
        print(f"Available loaders: {', '.join(sorted(LOADER_MAP.keys()))}", file=sys.stderr)
        return 1

    module_path = LOADER_MAP[loader_name]

    # Import and run the loader module
    try:
        module = __import__(module_path, fromlist=["main"])
        if hasattr(module, "main"):
            return module.main()
        else:
            print(f"ERROR: Module {module_path} has no main() function", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"ERROR: Failed to load module {module_path}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())

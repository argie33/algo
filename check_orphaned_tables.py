#!/usr/bin/env python3
import re
import os
import sys

# Tables from init.sql
all_tables = {
    'aaii_sentiment', 'algo_audit_log', 'algo_champion_challenger', 'algo_config',
    'algo_config_audit', 'algo_information_coefficient', 'algo_model_registry',
    'algo_notifications', 'algo_performance_daily', 'algo_portfolio_snapshots',
    'algo_positions', 'algo_risk_daily', 'algo_signals_evaluated', 'algo_tca',
    'algo_trade_adds', 'algo_trades', 'analyst_upgrade_downgrade',
    'annual_balance_sheet', 'annual_cash_flow', 'annual_income_statement',
    'backtest_results', 'backtest_runs', 'backtest_trades', 'beta_validation',
    'buy_sell_daily', 'buy_sell_daily_etf', 'buy_sell_monthly',
    'buy_sell_monthly_etf', 'buy_sell_weekly', 'buy_sell_weekly_etf',
    'calendar_events', 'can_slim_metrics', 'commodity_categories',
    'commodity_correlations', 'commodity_events', 'commodity_macro_drivers',
    'commodity_price_history', 'commodity_prices', 'commodity_seasonality',
    'commodity_technicals', 'community_signups', 'company_profile',
    'contact_submissions', 'cot_data', 'covered_call_opportunities',
    'data_completeness_scores', 'data_loader_runs', 'data_loader_status',
    'data_patrol_log', 'data_remediation_log', 'distribution_days',
    'earnings_estimate_revisions', 'earnings_estimate_trends', 'earnings_estimates',
    'earnings_history', 'economic_calendar', 'economic_data', 'etf_price_daily',
    'etf_price_monthly', 'etf_price_weekly', 'etf_symbols', 'factor_metrics',
    'fear_greed_index', 'filter_rejection_log', 'growth_metrics', 'index_metrics',
    'industry_performance', 'industry_ranking', 'insider_transactions',
    'institutional_positioning', 'iv_history', 'key_metrics', 'last_updated',
    'loader_execution_history', 'loader_execution_metrics', 'loader_sla_status',
    'manual_positions', 'market_data', 'market_exposure_daily',
    'market_health_daily', 'market_overview', 'market_sentiment',
    'momentum_metrics', 'naaim', 'options_chains', 'options_greeks',
    'order_execution_log', 'portfolio_holdings', 'portfolio_performance',
    'positioning_metrics', 'price_daily', 'price_monthly', 'price_weekly',
    'quality_metrics', 'quarterly_balance_sheet', 'quarterly_cash_flow',
    'quarterly_income_statement', 'relative_performance', 'safeguard_audit_log',
    'seasonality_day_of_week', 'seasonality_monthly_stats', 'sector_performance',
    'sector_ranking', 'sector_rotation_signal', 'sectors', 'sentiment',
    'sentiment_social', 'signal_quality_scores', 'signal_themes',
    'signal_trade_performance', 'stability_metrics', 'stock_scores',
    'stock_symbols', 'swing_trader_scores', 'technical_data_daily',
    'technical_data_monthly', 'technical_data_weekly', 'trades',
    'trend_template_data', 'ttm_cash_flow', 'ttm_income_statement',
    'user_alerts', 'user_api_keys', 'user_dashboard_settings', 'users',
    'value_metrics', 'vcp_patterns',
    # Special tables for auth/admin
    'api_keys', 'api_requests_log'
}

# Search code for table references
referenced = set()

patterns = [
    r'FROM\s+([a-z_]+)',
    r'INSERT\s+INTO\s+([a-z_]+)',
    r'UPDATE\s+([a-z_]+)',
    r'DELETE\s+FROM\s+([a-z_]+)',
    r'\.execute\(["\'].*?([a-z_]+)',
    r'query\(["\'].*?([a-z_]+)',
]

for root, dirs, files in os.walk('.'):
    # Skip node_modules and .git
    if 'node_modules' in root or '.git' in root:
        continue
    
    for file in files:
        if file.endswith(('.py', '.js')):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    for pattern in patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        for match in matches:
                            table = match.lower().strip()
                            if table in all_tables:
                                referenced.add(table)
            except:
                pass

orphaned = sorted(all_tables - referenced)

print(f"Total tables in schema: {len(all_tables)}")
print(f"Tables referenced in code: {len(referenced)}")
print(f"Potentially orphaned tables: {len(orphaned)}")
print()

if orphaned:
    print("Potentially orphaned tables (not referenced in code):")
    for table in orphaned:
        print(f"  - {table}")
else:
    print("No orphaned tables found!")

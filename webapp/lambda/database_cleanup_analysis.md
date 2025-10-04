# Database Cleanup Analysis

## Tables to KEEP (Core Site Functionality)

### Market Data
- `company_profile` - Company information
- `market_data` - Current market data
- `price_daily` - Daily price data
- `stock_prices` - Historical prices
- `stock_symbols` - Symbol definitions
- `market_indices` - Index data
- `market_quotes` - Real-time quotes
- `daily_volume_history` - Volume data

### Technical Analysis
- `technical_data_daily` - Daily technical indicators
- `technical_data_weekly` - Weekly technical indicators
- `technical_data_monthly` - Monthly technical indicators
- `latest_technicals_daily` - Latest technical snapshots

### Earnings & Fundamentals
- `earnings` - Earnings data
- `earnings_estimates` - EPS estimates
- `earnings_history` - Historical earnings
- `earnings_metrics` - Earnings quality metrics
- `earnings_reports` - Earnings reports
- `financial_metrics` - Financial metrics
- `fundamental_metrics` - Fundamental data
- `key_metrics` - Key financial metrics

### Financial Statements
- `annual_balance_sheet`
- `annual_cash_flow`
- `annual_income_statement`
- `quarterly_balance_sheet`
- `quarterly_cash_flow`
- `quarterly_income_statement`
- `ttm_cash_flow`
- `ttm_income_statement`

### Analyst Data
- `analyst_coverage` - Analyst coverage
- `analyst_estimates` - Analyst estimates
- `analyst_price_targets` - Price targets
- `analyst_recommendations` - Analyst ratings
- `analyst_sentiment_analysis` - Analyst sentiment
- `analyst_upgrade_downgrade` - Upgrades/downgrades

### Sentiment & News
- `aaii_sentiment` - AAII sentiment data
- `sentiment` - Stock sentiment data
- `social_sentiment_analysis` - Social sentiment
- `news` - News articles
- `news_articles` - News articles
- `stock_news` - Stock-specific news

### Dividends & Corporate Actions
- `dividend_history` - Dividend history
- `dividend_calendar` - Dividend events
- `stock_splits` - Stock split history

### Economic Data
- `economic_data` - Economic indicators
- `economic_events` - Economic calendar
- `fear_greed_index` - Fear & Greed index
- `naaim` - NAAIM sentiment

### Calendar & Events
- `calendar_events` - Earnings/dividend calendar

### ETF Data
- `etfs` - ETF information
- `etf_symbols` - ETF symbols
- `etf_holdings` - ETF holdings
- `etf_price_daily` - ETF prices

### Metrics & Scoring
- `stock_scores` - Stock scoring
- `comprehensive_scores` - Comprehensive scores
- `momentum_metrics` - Momentum metrics
- `quality_metrics` - Quality metrics
- `value_metrics` - Value metrics
- `profitability_metrics` - Profitability metrics

## Tables to REMOVE (Duplicates, Unused, or Testing)

### Duplicate Tables
- `stocks` (duplicate of company_profile/stock_symbols)
- `market_sentiment` (covered by aaii_sentiment)
- `sentiment_analysis` (duplicate of sentiment)
- `sentiment_data` (duplicate of sentiment)
- `sentiment_indicators` (covered by sentiment)
- `retail_sentiment` (covered by social_sentiment_analysis)
- `technical_indicators` (duplicate of technical_data_*)
- `technical_signals` (covered by swing_trading_signals)
- `economic_series` (duplicate of economic_data)
- `dividend_events` (duplicate of dividend_calendar)
- `dividends` (duplicate of dividend_history)
- `earnings_reports` (duplicate of earnings)
- `revenue_estimates` (covered by earnings_estimates)
- `trade_insights` (duplicate of trade_analytics)
- `sectors_performance` (duplicate of sector_performance)
- `watchlist` (duplicate of watchlists)
- `watchlist_performance` (calculated, not stored)
- `user_portfolios` (duplicate of portfolio_metadata)
- `user_watchlists` (duplicate of watchlists)

### Portfolio/Trading Tables (Not Used in Current Site)
- `portfolio_holdings`
- `portfolio_holdings_paper`
- `portfolio_transactions`
- `portfolio_performance`
- `portfolio_performance_paper`
- `portfolio_metadata`
- `portfolio_summary`
- `portfolio_analytics`
- `portfolio_returns`
- `portfolio_risk`
- `portfolio_risk_metrics`
- `portfolio_symbol_performance`
- `portfolio_alerts`
- `user_portfolio`
- `user_portfolio_metadata`
- `position_history`
- `positions`

### Trading/Execution Tables (Not Used)
- `trades`
- `trade_executions`
- `trade_history`
- `trade_analytics`
- `trading_sessions`
- `trading_strategies`
- `order_activities`
- `orders`
- `orders_paper`
- `buy_sell_daily`
- `buy_sell_daily_paper`
- `buy_sell_monthly`
- `buy_sell_weekly`
- `swing_trading_signals`
- `custom_signals`
- `signal_history`
- `backtest_results`

### Alert Tables (Can Be Consolidated)
- `alerts` - Keep
- `alert_rules` - Keep
- `alert_settings` - Keep
- `technical_alerts` - Remove (merge into alerts)
- `price_alerts` - Remove (merge into alerts)
- `volume_alerts` - Remove (merge into alerts)
- `risk_alerts` - Remove (merge into alerts)
- `signal_alerts` - Remove (merge into alerts)
- `trading_alerts` - Remove (merge into alerts)
- `news_alerts` - Remove (merge into alerts)
- `user_alerts` - Remove (duplicate)

### Attribution/Performance Analysis (Not Used)
- `attribution_analysis`
- `attribution_components`
- `brinson_attribution`
- `performance_attribution`
- `performance_benchmarks`
- `performance_metrics`

### Research/Reports (Not Used)
- `research_reports`

### Broker Integration (Not Used)
- `broker_api_configs`

### Governance (Not Used)
- `governance_scores`
- `leadership_team`

### User Management (Can Be Simplified)
- Keep: `user_profiles`, `user_settings`
- Remove: `user_2fa_secrets`, `user_activity_log`, `user_api_keys`, `user_dashboard_settings`, `user_risk_limits`

### API Management (Not Used in Current Site)
- `api_keys`
- `api_key_audit_log`

### Watchlist Tables (Can Be Simplified)
- Keep: `watchlists`, `watchlist_items`
- Remove: `watchlist`, `watchlist_performance`

### Screener Tables
- Keep: `saved_screens`

### Options Data (Not Used)
- `options_positioning`

### Risk Assessment (Not Used)
- `risk_assessments`

### Institutional Data
- Keep: `insider_transactions`, `institutional_positioning`

### Financial Ratios
- Keep: `financial_ratios`

### Sector Data
- Keep: `sector_performance`, `sectors`
- Remove: `sectors_performance` (duplicate)

### Volume Analysis
- Keep: `daily_volume_history`
- Remove: `volume_analysis` (duplicate/calculated)

### Utility Tables
- Keep: `last_updated`

## Summary

**Original**: 158 total tables
**Kept**: 78 core tables for site functionality
**Removed**: 80 duplicate, unused, or consolidatable tables

## Cleanup Status

✅ **COMPLETED** - Database cleanup executed on 2025-10-03

### Remaining Tables (78)
Core functionality tables retained:
- Market & pricing data (12 tables)
- Technical analysis (4 tables)
- Earnings & fundamentals (17 tables)
- Financial statements (7 tables)
- Analyst data (7 tables)
- Sentiment & news (6 tables)
- Dividends & events (3 tables)
- Economic data (4 tables)
- ETF data (4 tables)
- Metrics & scoring (6 tables)
- User & settings (4 tables)
- Watchlists & alerts (4 tables)

## Cleanup Script

```sql
-- Drop duplicate tables
DROP TABLE IF EXISTS stocks, market_sentiment, sentiment_analysis, sentiment_data CASCADE;
DROP TABLE IF EXISTS sentiment_indicators, retail_sentiment, technical_indicators CASCADE;
DROP TABLE IF EXISTS technical_signals, economic_series, dividend_events, dividends CASCADE;

-- Drop portfolio/trading tables
DROP TABLE IF EXISTS portfolio_holdings, portfolio_holdings_paper, portfolio_transactions CASCADE;
DROP TABLE IF EXISTS portfolio_performance, portfolio_performance_paper CASCADE;
DROP TABLE IF EXISTS portfolio_metadata, portfolio_summary, portfolio_analytics CASCADE;
DROP TABLE IF EXISTS portfolio_returns, portfolio_risk, portfolio_risk_metrics CASCADE;
DROP TABLE IF EXISTS portfolio_symbol_performance, portfolio_alerts CASCADE;
DROP TABLE IF EXISTS user_portfolio, user_portfolio_metadata CASCADE;
DROP TABLE IF EXISTS position_history, positions CASCADE;

-- Drop trading/execution tables
DROP TABLE IF EXISTS trades, trade_executions, trade_history, trade_analytics CASCADE;
DROP TABLE IF EXISTS trading_sessions, trading_strategies CASCADE;
DROP TABLE IF EXISTS order_activities, orders, orders_paper CASCADE;
DROP TABLE IF EXISTS buy_sell_daily, buy_sell_daily_paper CASCADE;
DROP TABLE IF EXISTS buy_sell_monthly, buy_sell_weekly CASCADE;
DROP TABLE IF EXISTS swing_trading_signals, custom_signals, signal_history CASCADE;
DROP TABLE IF EXISTS backtest_results CASCADE;

-- Drop duplicate alert tables
DROP TABLE IF EXISTS technical_alerts, price_alerts, volume_alerts CASCADE;
DROP TABLE IF EXISTS risk_alerts, signal_alerts, trading_alerts CASCADE;
DROP TABLE IF EXISTS news_alerts, user_alerts CASCADE;

-- Drop attribution/performance tables
DROP TABLE IF EXISTS attribution_analysis, attribution_components CASCADE;
DROP TABLE IF EXISTS brinson_attribution, performance_attribution CASCADE;
DROP TABLE IF EXISTS performance_benchmarks, performance_metrics CASCADE;

-- Drop unused feature tables
DROP TABLE IF EXISTS research_reports, broker_api_configs CASCADE;
DROP TABLE IF EXISTS governance_scores, leadership_team CASCADE;
DROP TABLE IF EXISTS api_keys, api_key_audit_log CASCADE;
DROP TABLE IF EXISTS options_positioning, risk_assessments CASCADE;
DROP TABLE IF EXISTS user_2fa_secrets, user_activity_log CASCADE;
DROP TABLE IF EXISTS user_api_keys, user_dashboard_settings, user_risk_limits CASCADE;

-- Drop duplicate watchlist/sector tables
DROP TABLE IF EXISTS watchlist, watchlist_performance CASCADE;
DROP TABLE IF EXISTS sectors_performance, volume_analysis CASCADE;
```

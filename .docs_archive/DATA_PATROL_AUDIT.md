# Data Patrol Audit Report
**Date:** 2026-05-04  
**Database:** PostgreSQL (139 total tables)  
**Current Patrol:** algo_data_patrol.py with 11 checks (P1-P11)

---

## EXECUTIVE SUMMARY

✅ **Core data integrity:** Well-covered for critical trading tables  
⚠️ **Fundamental data:** Partially monitored  
❌ **Derived metrics:** Limited monitoring  
❌ **ETF data:** Only signals covered, not price data  
❌ **Market-wide metrics:** No dedicated patrol  
❌ **User/config data:** Not monitored

---

## CURRENT PATROLS (In algo_data_patrol.py)

### P1: STALENESS ✅
**What it checks:**
- 14 tables monitored for data freshness
- Thresholds: daily (7 days), weekly (14 days), quarterly (120 days)

**Tables covered:**
- price_daily (CRITICAL)
- technical_data_daily (CRITICAL)
- buy_sell_daily (CRITICAL)
- trend_template_data (CRITICAL)
- signal_quality_scores
- market_health_daily
- sector_ranking
- industry_ranking
- insider_transactions
- analyst_upgrade_downgrade
- stock_scores
- aaii_sentiment
- growth_metrics
- earnings_history

**Missing critical tables (no staleness check):**
- buy_sell_weekly ❌
- buy_sell_monthly ❌
- buy_sell_daily_etf ❌
- buy_sell_weekly_etf ❌
- buy_sell_monthly_etf ❌
- etf_price_daily ❌
- etf_price_weekly ❌
- etf_price_monthly ❌
- earnings_estimates ❌
- earnings_estimate_revisions ❌
- key_metrics ❌
- quality_metrics ❌
- momentum_metrics ❌
- value_metrics ❌
- stability_metrics ❌
- annual_income_statement ❌
- annual_balance_sheet ❌
- annual_cash_flow ❌
- quarterly_income_statement ❌
- quarterly_balance_sheet ❌
- quarterly_cash_flow ❌

### P2: NULL ANOMALIES ✅
**What it checks:**
- Sudden spike in NULL values vs 30-day historical average
- Currently only checks: price_daily.close

**Missing coverage:**
- Doesn't check other critical columns (high, low, open, volume)
- Doesn't check technical_data_daily indicators
- Doesn't check signal quality in buy_sell_daily

### P3: ZERO/IDENTICAL DATA ✅
**What it checks:**
- Zero values in OHLC/volume (API limit hit)
- Identical OHLC (high=low=open=close)
- Currently only checks: price_daily

**Missing coverage:**
- etf_price_daily
- technical_data_daily

### P4: PRICE SANITY ✅
**What it checks:**
- >50% day-over-day moves (flags suspicious changes)
- Currently only checks: price_daily

**Missing coverage:**
- Sector ranking sudden changes
- Industry ranking volatility
- Fundamental metric shifts (earnings revisions, analyst changes)

### P5: VOLUME SANITY ✅
**Status:** Mentioned in P3 but not explicitly implemented as separate check
- Should validate volume > 0 for liquid stocks
- Should flag volume spikes / drops

### P6: CROSS-SOURCE VALIDATION ✅
**What it checks:**
- Compares price_daily.close vs Alpaca API
- Compares price_daily.close vs Yahoo Finance
- Flags >5% mismatches

**Missing coverage:**
- No validation for earnings data
- No validation for fundamental metrics
- No cross-check for technical indicators
- No secondary source for ETF data

### P7: UNIVERSE COVERAGE ✅
**What it checks:**
- % of symbols updated on latest date in price_daily
- Thresholds: <90% ERROR, <98% WARN

**Missing coverage:**
- Doesn't check buy_sell_daily coverage vs price_daily
- Doesn't check technical_data_daily coverage
- Doesn't check if all symbols in price_daily have technical data
- No cross-table coverage validation

### P8: SEQUENCE CONTINUITY ✅
**What it checks:**
- No gaps in trading days for SPY (canary)
- Max gap: 4 days (weekend = 3 days)

**Missing coverage:**
- Doesn't validate for individual symbols (trading halts, delistings)
- Doesn't check weekly/monthly tables
- Doesn't check for missing trading days when market should be open

### P9: CONSTRAINT VALIDATION ✅
**What it checks:**
- NULL primary key fields in:
  - algo_trades (symbol, trade_id)
  - algo_positions (symbol, position_id)
  - price_daily (symbol, date)
  - buy_sell_daily (symbol, date, signal)

**Missing coverage:**
- Foreign key violations
- Unique constraint violations
- Check constraint violations
- Other 135+ tables not validated

### P10: SCORE FRESHNESS ✅
**What it checks:**
- Computed scores updated AFTER raw data
- Checks: trend_template_data, signal_quality_scores vs price_daily

**Missing coverage:**
- stock_scores (not included in check)
- data_completeness_scores (not included)
- Technical indicators (technical_data_daily) fresher than price_daily?
- Buy/sell signals fresh relative to price/technical?

### P11: LOADER CONTRACTS ✅
**What it checks:**
- Min row count thresholds per table
- Buy/sell signal quality (% clean BUY/SELL vs NULL)

**Contracts configured:**
- price_daily: 50K rows in 14 days
- technical_data_daily: 50K rows
- buy_sell_daily: 1K rows
- trend_template_data: 20K rows
- signal_quality_scores: 20K rows
- sector_ranking: 10 rows
- industry_ranking: 100 rows
- market_health_daily: 10 rows
- market_exposure_daily: 5 rows
- stock_scores: 4.5K rows
- data_completeness_scores: 4.5K rows

**Missing contracts:**
- buy_sell_weekly (no threshold)
- buy_sell_monthly (no threshold)
- buy_sell_daily_etf (no threshold)
- earnings_estimates (critical, no check)
- earnings_estimate_revisions (critical, no check)
- Technical indicator components (atr, sma_50, ema_12, etc.)
- Annual/quarterly financial data
- All 60+ other loaders with no contract validation

---

## TABLES NOT MONITORED AT ALL ❌

### Category: ETF Data (8 tables)
- buy_sell_daily_etf
- buy_sell_weekly_etf
- buy_sell_monthly_etf
- etf_price_daily
- etf_price_weekly
- etf_price_monthly
- etf_symbols

### Category: Financial Statements (6 tables)
- annual_income_statement
- annual_balance_sheet
- annual_cash_flow
- quarterly_income_statement
- quarterly_balance_sheet
- quarterly_cash_flow

### Category: Advanced Metrics (12 tables)
- key_metrics
- quality_metrics
- momentum_metrics
- value_metrics
- stability_metrics
- growth_metrics (partial - only staleness)
- can_slim_metrics
- beta_validation
- market_breadth
- positioning_metrics
- institutional_positioning
- vcp_patterns

### Category: Earnings Data (4 tables)
- earnings_estimates (CRITICAL - only has staleness, no contract)
- earnings_estimate_revisions (CRITICAL - no patrol)
- earnings_estimate_trends
- earnings_metrics

### Category: Market/Sector Data (9 tables)
- sector_rotation_signal
- industry_technical_data
- sector_technical_data
- sector_performance (vs sector_ranking)
- industry_performance (vs industry_ranking)
- market_overview
- market_data
- market_indices
- market_exposure_daily (has contract but no other checks)

### Category: Sentiment/Sentiment Analysis (5 tables)
- sentiment (raw sentiment scores)
- social_sentiment_analysis
- analyst_sentiment_analysis
- fear_greed_index
- naaim / naaim_exposure

### Category: Technical Signals (9 tables)
- range_signals_daily
- mean_reversion_signals_daily
- momentum_metrics (also in advanced)
- seasonality_day_of_week
- seasonality_monthly
- seasonality_quarterly
- distribution_days
- market_health_daily (partial - only staleness)
- sector_rotation_signal

### Category: Options Data (4 tables)
- options_chains
- options_greeks
- covered_call_opportunities
- iv_history

### Category: Commodities (9 tables)
- commodity_prices
- commodity_price_history
- commodity_technicals
- commodity_correlations
- commodity_events
- commodity_inventory
- commodity_macro_drivers
- commodity_seasonality
- commodity_supply_demand

### Category: Macro/Economic (5 tables)
- economic_data
- economic_calendar
- cot_data
- commodities / related

### Category: News/Sentiment (2 tables)
- news (if exists)
- signal_themes

### Category: Portfolio/Algo Execution (9 tables)
- algo_trades (P9 only)
- algo_positions (P9 only)
- algo_audit_log
- algo_portfolio_snapshots
- algo_signals_evaluated
- algo_trade_adds
- algo_notifications
- algo_config
- backtest_runs / backtest_trades

### Category: User/Config (8 tables)
- users
- user_api_keys
- user_alerts
- user_dashboard_settings
- contact_submissions
- community_signups
- algo_config
- manual_positions

### Category: Metadata/Operational (15+ tables)
- data_loader_status
- data_remediation_log
- loader_execution_metrics
- loader_performance_summary
- loader_run_progress
- loader_watermarks
- last_updated
- stock_symbols
- pricing tables (weekly, monthly variants)
- stage tables (_stage_buy_sell_daily_*, _stage_price_daily_*)

---

## AWS MONITORING GAPS ❌

### CloudWatch Dashboard Gaps
Current dashboard has:
- Lambda metrics (generic)
- ECS metrics (if used)
- RDS metrics (generic)
- S3 storage
- API Gateway
- CloudFront

**Missing:**
- Data loader success/failure rates by loader
- Data freshness per table (custom metric)
- Data quality metrics (P1-P11 results)
- Loader execution time trends
- Data patrol alarm integration
- SNS alerts for critical data issues
- DynamoDB metrics (Phase E caching)
- EventBridge schedule execution status

### CloudWatch Alarms
**Currently missing entirely:**
- No alarms for stale data
- No alarms for loader failures
- No alarms for data quality issues
- No alarms for patrol CRITICAL findings
- No auto-remediation triggers

### EventBridge Integration
**Missing:**
- Automatic patrol scheduling
- Loader failure notifications
- Data quality alerts to ops team
- SNS topic integration

### Lambda Monitoring
**Missing:**
- Custom metrics for data quality
- Patrol execution metrics
- Failure triggers for Phase 1 orchestrator

---

## CRITICAL GAPS - PRIORITIZED BY RISK

### 🔴 TIER 1 (Must-Have) - Trading-Critical Data

1. **Earnings Data Validation** ❌
   - earnings_estimates (no staleness contract)
   - earnings_estimate_revisions (not monitored)
   - earnings_estimate_trends (not monitored)
   - **Why:** Affects position monitoring, earnings alerts, stop decisions
   - **Impact:** Could hold position through earnings without knowing
   - **Fix:** Add P12 check for earnings data freshness + contracts

2. **ETF Signal Coverage** ❌
   - buy_sell_daily_etf (no monitoring)
   - buy_sell_weekly_etf (no monitoring)
   - buy_sell_monthly_etf (no monitoring)
   - **Why:** Portfolio may have ETF positions
   - **Impact:** Missing signals for ETF holdings
   - **Fix:** Add P13 check for ETF signal freshness + contracts

3. **ETF Price Data** ❌
   - etf_price_daily (no monitoring)
   - etf_price_weekly (no monitoring)
   - etf_price_monthly (no monitoring)
   - **Why:** Need ETF prices for position valuation
   - **Impact:** Incorrect portfolio value calculations
   - **Fix:** Extend P1 staleness + P3 zero check to ETF tables

4. **Buy/Sell Signal Quality** ⚠️ (Partial)
   - P11 checks only % clean signals, not signal accuracy
   - Doesn't validate signal_quality_scores values (0-100 range?)
   - Doesn't check if signal confidence scores make sense
   - **Fix:** Add validation for signal_quality_scores range + distribution

5. **Cross-Table Data Alignment** ❌
   - No check that buy_sell_daily has 100% of symbols from price_daily
   - No check that technical_data_daily covers all price_daily symbols
   - No check that scores match symbol universe
   - **Fix:** Add P14 alignment check (universal coverage validation)

### 🟠 TIER 2 (Should-Have) - Fundamental & Analysis Data

6. **Financial Statement Freshness** ❌
   - annual_income_statement, balance_sheet, cash_flow
   - quarterly_income_statement, balance_sheet, cash_flow
   - earnings_metrics
   - **Why:** Used for valuation, scoring, screening
   - **Impact:** Stale fundamentals in stock scores
   - **Fix:** Add P15 check for financial data freshness (quarterly cadence)

7. **Key Metrics Completeness** ❌
   - key_metrics, quality_metrics, momentum_metrics, value_metrics
   - **Why:** Used in stock scoring, screening
   - **Impact:** Incomplete scores if metrics missing
   - **Fix:** Add P16 check for metric coverage vs symbol universe

8. **Market/Sector Data Freshness** ⚠️
   - sector_ranking (P1 covers)
   - industry_ranking (P1 covers)
   - sector_rotation_signal (NOT covered)
   - sector_performance vs sector_ranking (inconsistency risk)
   - **Fix:** Add check for sector data consistency

9. **Analyst Data Freshness** ❌
   - analyst_upgrade_downgrade (P1 covers)
   - analyst_sentiment_analysis (NOT covered)
   - earnings_estimate_revisions (NOT covered)
   - **Fix:** Extend P1 to analyst_sentiment_analysis + estimate revisions

### 🟡 TIER 3 (Nice-to-Have) - Operational Monitoring

10. **Loader Execution Health** ❌
    - data_loader_status table exists but not monitored
    - loader_execution_metrics not in patrol
    - loader_performance_summary not in patrol
    - **Fix:** Add P17 check to validate all loaders executed today

11. **Algo Execution Audit** ⚠️
    - algo_audit_log not monitored
    - Positions tracked but audit trail not validated
    - **Fix:** Add audit log consistency check

12. **Data Remediation Tracking** ❌
    - data_remediation_log exists but not monitored
    - Can't detect if remediation is working
    - **Fix:** Add P18 to track remediation effectiveness

---

## MISSING AWS INTEGRATIONS

### CloudWatch Integration Gaps
```
Current:  Local Python script → data_patrol_log table
Needed:   Local Python script → CloudWatch Metrics → Alarms → SNS → Ops
```

**Missing:**
1. CloudWatch Metrics Namespace: `StockAlgo/DataQuality`
   - MetricName: `PatrolFinding` (dimension: check_type, severity)
   - MetricName: `DataStaleness` (dimension: table_name, days_old)
   - MetricName: `LoaderSuccess` (dimension: loader_name)

2. CloudWatch Alarms:
   - **CRITICAL alarm:** Any P1 CRITICAL finding
   - **ERROR alarm:** >3 P1 ERROR findings in 1 hour
   - **WARNING alarm:** >5 WARN findings in 1 hour

3. SNS Integration:
   - Topic: `algo-data-quality-alerts`
   - Trigger on: CRITICAL, ERROR findings
   - Subscribers: Ops team email, Slack webhook

4. EventBridge Integration:
   - Schedule: Daily patrol at 8am ET (before market open)
   - Trigger Lambda: `run-data-patrol`
   - Action on FAIL: Halt Phase 1 orchestrator

---

## RECOMMENDED MONITORING STRATEGY

### Tier 1 Patrols (Add These Immediately)

**P12: Earnings Data Validation** 
- Check staleness: earnings_estimates, earnings_estimate_revisions
- Validate min row counts per table
- Flag if earnings data is stale for upcoming earnings dates

**P13: ETF Data Validation**
- Extend P1 staleness to all etf_price_* tables
- Extend P3 zero check to etf_price_daily
- Extend P7 coverage to buy_sell_daily_etf
- Validate ETF signal freshness

**P14: Cross-Table Alignment**
- Verify buy_sell_daily symbols ⊆ price_daily symbols (>=95%)
- Verify technical_data_daily symbols ⊆ price_daily symbols (>=95%)
- Verify stock_scores symbols ⊆ universe symbols (>=95%)

**P15: Financial Data Freshness**
- quarterly_income_statement, balance_sheet, cash_flow (max age: 45 days)
- annual_* (max age: 120 days)
- earnings_metrics (max age: 7 days)

### Tier 2 Patrols (Add These in Next Sprint)

**P16: Metric Coverage Validation**
- Verify key_metrics covers >=98% of symbols
- Verify quality_metrics, momentum_metrics, value_metrics coverage
- Flag symbols missing metrics that affect scoring

**P17: Loader Execution Audit**
- Query data_loader_status: all 59 loaders executed in last 24h
- Flag missing loaders
- Validate no loader stuck in "running" state >2h

**P18: Signal Quality Distribution**
- Validate signal_quality_scores range (0-100)
- Flag if <50% of signals have confidence >80
- Detect signal generation regression

### AWS Infrastructure (Parallel Track)

1. **CloudWatch Metrics Export** (Week 1)
   - Lambda function: `export-patrol-results-to-cloudwatch`
   - Runs after patrol completes
   - Publishes custom metrics per check

2. **SNS Alerts** (Week 1)
   - Topic: `algo-data-quality-alerts`
   - Subscription: ops-team@example.com, Slack webhook
   - Triggers on CRITICAL, ERROR findings

3. **EventBridge Schedule** (Week 2)
   - Rule: `daily-data-patrol`
   - Schedule: `cron(0 8 * * ? *)` (8am ET daily)
   - Target: Lambda function `run-data-patrol`

4. **CloudWatch Dashboard** (Week 2)
   - Widget: Patrol results (CRITICAL, ERROR, WARN counts)
   - Widget: Data staleness per table (heatmap)
   - Widget: Loader execution status (grid)
   - Widget: Patrol alert history (log insights)

5. **Auto-Remediation** (Week 3 - Optional)
   - If P1 CRITICAL: automatically halt Phase 1 orchestrator
   - Alert ops team for investigation
   - Block new trades until manual remediation

---

## IMPLEMENTATION ROADMAP

### Week 1 (Immediate)
- [ ] Add P12, P13, P14 patrols to algo_data_patrol.py
- [ ] Create CloudWatch metrics export Lambda
- [ ] Set up SNS topic + subscriptions
- [ ] Test patrol with new checks

### Week 2
- [ ] Add P15, P16, P17 patrols
- [ ] Set up EventBridge daily schedule
- [ ] Create CloudWatch dashboard
- [ ] Run 5 consecutive days of successful patrols

### Week 3
- [ ] Add P18 signal quality check
- [ ] Integrate patrol results → CloudWatch → Alarms
- [ ] Configure critical alarm escalation
- [ ] Documentation & runbook

### Week 4
- [ ] Load testing: patrol performance with all 139 tables
- [ ] Auto-remediation: halt orchestrator on critical findings
- [ ] Monitoring dashboard refinement
- [ ] Deploy to production

---

## SUCCESS CRITERIA

✅ All 18 patrols (P1-P18) running daily  
✅ Zero data quality issues reach trading system  
✅ <5min patrol execution time  
✅ <1hr E2E from patrol complete → ops alert  
✅ All 139 tables monitored (directly or via aggregate checks)  
✅ CloudWatch dashboard shows real-time data health  
✅ Ops team can respond to data issues within 1 hour  
✅ Audit trail of all patrol findings (2-year retention)  

---

## APPENDIX: All Loaders & Their Monitor Status

### High-Frequency (Daily) - CRITICAL
- [x] loadpricedaily.py → price_daily (P1-P11)
- [x] loadtechnicalsdaily.py → technical_data_daily (P1, P11)
- [x] loadbuyselldaily.py → buy_sell_daily (P1-P11)
- [ ] loadbuyselldaily_etf.py → buy_sell_daily_etf (MISSING)
- [ ] loadetfpricedaily.py → etf_price_daily (MISSING)
- [x] load_trend_template_data.py → trend_template_data (P1, P11)
- [x] load_market_health_daily.py → market_health_daily (P1, P11)
- [ ] load_algo_metrics_daily.py → ??? (MISSING CHECKS)

### Weekly - MEDIUM
- [ ] loadpriceweekly.py → price_weekly (NO CHECKS)
- [ ] loadtechnicalsdaily.py weekly variant (NO CHECKS)
- [ ] loadbuysellweekly.py → buy_sell_weekly (NO CHECKS)
- [ ] loadbuysell_etf_weekly.py → buy_sell_weekly_etf (NO CHECKS)
- [ ] loadetfpriceweekly.py → etf_price_weekly (NO CHECKS)

### Monthly - MEDIUM
- [ ] loadpricemonthly.py → price_monthly (NO CHECKS)
- [ ] loadbuysellmonthly.py → buy_sell_monthly (NO CHECKS)
- [ ] loadbuysell_etf_monthly.py → buy_sell_monthly_etf (NO CHECKS)
- [ ] loadetfpricemonthly.py → etf_price_monthly (NO CHECKS)

### Earnings - CRITICAL
- [ ] loadearningshistory.py → earnings_history (P1 only, no contract)
- [ ] loadearningsestimates.py → earnings_estimates (NO CHECKS)
- [ ] loadearningsrevisions.py → earnings_estimate_revisions (NO CHECKS)

### Fundamentals - MEDIUM
- [ ] loadannualincomestatement.py → annual_income_statement (NO CHECKS)
- [ ] loadannualbalancesheet.py → annual_balance_sheet (NO CHECKS)
- [ ] loadannualcashflow.py → annual_cash_flow (NO CHECKS)
- [ ] loadquarterlyincomestatement.py → quarterly_income_statement (NO CHECKS)
- [ ] loadquarterlybalancesheet.py → quarterly_balance_sheet (NO CHECKS)
- [ ] loadquarterlycashflow.py → quarterly_cash_flow (NO CHECKS)

### Market Data - MEDIUM
- [x] loadsectorranking.py → sector_ranking (P1, P11)
- [x] loadindustryranking.py → industry_ranking (P1, P11)
- [ ] loadmarket.py → market_data (NO CHECKS)
- [ ] loadmarketindices.py → market_indices (NO CHECKS)

### Sentiment - LOW
- [x] loadaaiidata.py → aaii_sentiment (P1)
- [ ] loadsentiment.py → sentiment (NO CHECKS)
- [ ] loadanalystsentiment.py → analyst_sentiment_analysis (NO CHECKS)
- [x] loadanalystupgradedowngrade.py → analyst_upgrade_downgrade (P1)

### Signals - MEDIUM
- [ ] loadswingscores.py → swing_trader_scores (NO CHECKS)
- [ ] loadstockscores.py → stock_scores (P1, P11)
- [ ] loadmeanreversionsignals.py → mean_reversion_signals_daily (NO CHECKS)
- [ ] loadrangesignals.py → range_signals_daily (NO CHECKS)

### Other Loaders (30+) - LOW PRIORITY
- loadcommodities.py, loadecondata.py, loadfeargreed.py, etc.
- Most have NO CHECKS in patrol

---

**Report Generated:** 2026-05-04  
**Next Review:** After P12-P15 implementation (Week 2)  
**Maintained By:** Data Platform Team

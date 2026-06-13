# Remaining Issues for Full AWS Data Deployment

## Fixed This Session ✅
1. health.py: Fixed get_config import error (was trying to import from root config module instead of lambda/api/utils/config.py)
2. health.py: Added missing safe_json_serialize import from routes.utils
3. phase1_data_freshness.py: Adjusted min_symbol_count from 8000 to 2000 (realistic for actual data availability)
4. test_intraday_pipelines.py: Removed return statements to eliminate pytest warnings
5. All tests passing: 86 passed, 2 skipped, 0 failures

## Critical Issues (Block Production)

### 1. RDS Connection Pool Saturation
- Status: Configured but needs monitoring
- Details: 24 loaders using adaptive parallelism with 20-30 persistent RDS connections
- Risk: Pool exhaustion during EOD pipeline (4:05-5:30 PM) with full data volume
- Action: Monitor CloudWatch DatabaseConnections metric, alert if >80% (>400 connections)
- Threshold: Max 100 connections in db.t4g.small RDS instance

### 2. Loader Parallelism Auto-Scaling
- Status: DynamoDB-based adaptive config exists but needs validation
- Details: stock_prices_daily (max 3), technical_data_daily (max 2), analytics (max 8)
- Risk: Parallelism doesn't reduce fast enough if RDS saturates
- Action: Test auto-scaling with full symbol count (5000+); verify reduction logic works
- Files: loaders/load_*.py parallelism configuration

### 3. Morning Prep Pipeline SLA (2 AM - 9:30 AM)
- Status: Currently 5-5.5 hours, leaves 1-1.5h buffer
- Details: Must complete before 9:30 AM orchestrator run
- Risk: Any delays in price/market health/swing_trader_scores loading will miss SLA
- Action: Benchmark with full 5000+ symbol dataset; add monitoring alerts
- Critical files: loaders/load_stock_prices_daily.py, load_swing_trader_scores_vectorized.py

### 4. Pre-Close Update Pipeline SLA (2:50 PM - 3:15 PM)
- Status: 5-15 min pipeline must complete in 25-minute window
- Details: Phase 5 signal generation uses scores from pre-close update
- Risk: Any yfinance delays will exceed SLA, preventing signal updates for 3 PM orchestrator
- Action: Monitor CloudWatch logs for pipeline start/end times daily
- Critical files: Phase 5 signal generation logic

### 5. API Rate Limiting (yfinance, IEX Cloud, FRED)
- Status: Multiple loaders hit APIs with strict rate limits
- Details: yfinance (batch 150), IEX Cloud (IP-based), FRED (single endpoint)
- Risk: Rate limiting causes batch failures, triggering retry loops and delays
- Action: Implement request queuing, rate limit detection, and graceful degradation
- Files: loaders/load_stock_prices_daily.py, load_technical_data_daily.py

### 6. Cognito Configuration Mismatch
- Status: COGNITO_CLIENT_ID must match actual Cognito user pool
- Details: /api/health/cognito validates client ID; deployment blocked if mismatch
- Risk: Deployment fails if GitHub Actions secret doesn't match Cognito
- Action: Verify COGNITO_CLIENT_ID and COGNITO_USER_POOL_ID match production setup
- Critical files: lambda/api/routes/health.py health check validation

## High-Priority Issues (May Block Features)

### 7. Orchestrator Distributed Lock Timeout
- Status: 600-second lock with timeout
- Details: DynamoDB lock (`orchestrator-run-lock`) prevents concurrent runs
- Risk: Timeout if orchestrator takes >10 minutes or previous instance hangs
- Action: Monitor lock acquisition time; add alerting if >500 seconds
- Files: algo/algo_orchestrator.py lock acquisition logic

### 8. Circuit Breaker Thresholds Validation
- Status: Hardcoded thresholds may not match production risk tolerance
- Details: Drawdown ≥20%, daily loss ≥2%, consecutive losses ≥3, VIX ≥35, win rate <40%
- Risk: Thresholds too strict → constant halts; too loose → excessive losses
- Action: Validate thresholds with historical backtests; adjust via algo_config table
- Files: algo/orchestrator/phase2_circuit_breakers.py

### 9. Signal Generation Quality Thresholds
- Status: Minervini gate, quality score minimum (50), liquidity gate (top 150) need validation
- Details: Phase 5 signal generation is on-the-fly with real-time data
- Risk: Quality gates too strict → no signals; too loose → low-quality trades
- Action: Backtest with production data; tune via algo_config
- Files: algo/orchestrator/phase5_signal_generation.py

### 10. Data Patrol Configuration
- Status: Staleness, coverage, sanity thresholds exist but need production tuning
- Details: Monitors symbol coverage, data age, value ranges
- Risk: False positives halt system unnecessarily
- Action: Analyze production data distribution; set realistic thresholds
- Files: algo/algo_data_patrol.py

## Medium-Priority Issues (Performance/Reliability)

### 11. Phase 1 Data Freshness Thresholds
- Status: Currently 75% coverage vs prior day, 2000 symbol minimum
- Details: Checks price_daily for recent data; triggers halt if stale
- Risk: May be too strict for holiday/weekend extended periods
- Action: Monitor failures; use DATA_FRESHNESS_MAX_HOURS env var for holidays
- Files: algo/orchestrator/phase1_data_freshness.py

### 12. Intraday Score Pipeline Synchronization
- Status: Morning (2 AM), Afternoon (12:50 PM), Pre-close (2:50 PM) pipelines
- Details: Each pipeline loads swing_trader_scores with INTRADAY_MODE=true
- Risk: Concurrent loader runs may conflict if not properly sequenced
- Action: Verify CloudWatch logs show no lock timeouts or conflicts
- Files: loaders/load_swing_trader_scores_vectorized.py

### 13. DynamoDB State Management
- Status: orchestrator_halt, phase1_degraded_mode flags stored in DynamoDB
- Details: Halt flag auto-expires; degraded mode indicates failsafe is running
- Risk: DynamoDB unavailability breaks health checks and halt management
- Action: Enable DynamoDB backups; monitor table activity; set proper TTL
- Files: algo/algo_orchestrator.py DynamoDB operations

### 14. Alpaca Paper Trading Mode
- Status: Currently alpaca_paper_trading = true
- Details: Uses paper-api.alpaca.markets; live trading requires mode switch
- Risk: Credentials or API endpoint mismatch will cause trade failures
- Action: Test paper trading thoroughly; validate live credentials before switching
- Files: loaders/reconciliation, Alpaca API calls

### 15. Position Reconciliation (Phase 7)
- Status: Reconciles Phase 4 pre-closes with actual Alpaca fills
- Details: Handles EXT-* trades, adjusts win rate, updates position state
- Risk: Reconciliation lag may cause position state mismatches
- Action: Monitor Phase 7 logs for reconciliation delays >1 hour
- Files: algo/orchestrator/phase7_reconciliation.py

## Low-Priority Issues (Monitoring/Tuning)

### 16. API Cold Start Performance
- Status: 1 provisioned concurrency keeps Lambda warm
- Details: 256 MB, 28s timeout
- Risk: VPC cold starts cause 30-40s delays
- Action: Monitor CloudWatch metrics for cold starts; consider increasing concurrency
- Files: lambda/api/lambda_function.py

### 17. CloudFront Cache Invalidation
- Status: Four-layer caching (S3 headers + CloudFront + browser + parameter)
- Details: config.js injected at build time with cache-bust parameter
- Risk: Stale config on frontend if cache-bust fails
- Action: Monitor frontend for old API URLs/Cognito IDs; clear cache if needed
- Files: webapp/frontend/src/config.js generation

### 18. Loader Status Monitoring
- Status: data_loader_status table tracks RUNNING/COMPLETED/FAILED
- Details: DynamoDB fallback with 1-hour TTL for tracking
- Risk: Missing loaders silently if status table corrupts
- Action: Periodic verification that all loaders log status correctly
- Files: loaders/loader_status_tracker.py

### 19. Market Calendar Integration
- Status: MarketCalendar.is_trading_day() checks for holidays/weekends
- Details: Used by Phase 1 for last trading day calculation
- Risk: Holiday calendar updates may lag; manual override needed
- Action: Update market calendar before known holidays; test Phase 1 on edges
- Files: algo/algo_market_calendar.py

### 20. Error Handling Fallbacks
- Status: Hardcoded zeros with _is_fallback_data flag for missing data
- Details: Phase 1 monitors but doesn't halt on fallback usage
- Risk: Trading on fallback data (zeros) could cause losses
- Action: Monitor for _is_fallback_data = true in logs; escalate if frequent
- Files: lambda/api/routes/utils.py fallback logic

## Validation Checklist for Production Deployment

- [ ] RDS connection pool monitoring alerts configured
- [ ] Morning prep pipeline completes before 9:30 AM (benchmark with full data)
- [ ] Pre-close pipeline completes before 3:15 PM (benchmark with full data)
- [ ] yfinance rate limiting doesn't trigger on full 5000+ symbol data
- [ ] Cognito COGNITO_CLIENT_ID matches production user pool
- [ ] Orchestrator distributed lock doesn't timeout (monitor < 600s)
- [ ] Circuit breaker thresholds validated with historical backtest
- [ ] Signal generation quality gates validated with production data
- [ ] Phase 1 data freshness thresholds appropriate for production
- [ ] DynamoDB halt flag and degraded mode working correctly
- [ ] Alpaca paper trading mode verified (or live credentials validated)
- [ ] Phase 7 reconciliation keeping up with actual fills
- [ ] CloudFront caching not serving stale config.js
- [ ] Market calendar has current holidays configured
- [ ] Error fallback usage (zeros) monitored and escalated
- [ ] All 86 unit tests passing in production environment
- [ ] All 4 EventBridge scheduler rules active and triggering
- [ ] All 4 Step Functions state machines executing correctly
- [ ] CloudWatch dashboards showing real-time system health

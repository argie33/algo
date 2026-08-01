# COMPREHENSIVE AUDIT: Algo Trading System Status (2026-08-01)

## Overview
This audit catalogs all remaining issues, risks, and bulletproofing gaps across the orchestrator, dashboard, data loading infrastructure, and configuration systems. The goal is to understand the complete state of what is production-ready vs. what still needs hardening.

---

## SECTION 1: ORCHESTRATOR PHASES (1-9)

### Phase 1: Data Freshness Check ✓ MOSTLY SOLID
**Status:** Recent fixes stabilized, but edge cases remain

**Known Working:**
- Price data freshness validation (75%+ coverage threshold)
- Market health breadth checks (optional columns handled gracefully)
- Earnings calendar availability checks
- Growth/quality/value/positioning/stability metrics treated as enrichment-only (warnings, not halts)
- Metric loaders validated via data_loader_status table

**Outstanding Issues:**
1. **Symbol coverage gaps not fully audited**
   - 312 missing symbols from price_daily (reduced threshold from 95% → 90% in Session 365)
   - Unknown impact on signal generation universe
   - No per-exchange analysis (NYSE vs NASDAQ vs OTC)

2. **Reference date precision issues (CRITICAL FIX needed)**
   - Table reference dates must be converted to date objects, not datetime
   - Phantom rows: NULL prices counted as "fresh data" unless explicitly validated
   - Session 365 partially fixed but implementation gaps remain

3. **Metric loader staleness definition inconsistent**
   - Quality/growth/value treated as enrichment (warning-only)
   - But Phase 5 uses these for stock_scores ranking
   - Unclear if stale metrics degrade signal quality silently

4. **Market hours tolerance too loose**
   - Morning runs before 9:30 AM ET allow 1-hour stale data
   - But price_daily updates throughout day; tolerance shouldn't apply after 4:30 PM
   - No explicit window check beyond raw hour comparison

**Risk Level:** MEDIUM - likely handles normal cases, but edge cases (halted stocks, delisted symbols, data gaps) may slip through


### Phase 2: Circuit Breakers ✓ SOLID
**Status:** Robust with good fail-fast behavior

**Known Working:**
- Market halt checks via Alpaca API
- Account flag validation (pattern_day_trader, trading_blocked, account_blocked)
- Transient network errors properly escalated (not silently ignored)
- Fail-fast on missing required fields

**Outstanding Issues:**
1. **No timeouts on circuit breaker API calls**
   - If Alpaca API hangs, orchestrator blocks indefinitely
   - Recommend: Add explicit 5-10s timeout to market halt check

2. **Incomplete error messages in some paths**
   - "Circuit breaker halt_reasons has invalid type" error doesn't specify what type was received
   - Makes debugging harder

**Risk Level:** LOW - solid implementation, minor timeout hardening needed


### Phase 3: Position Monitor ✓ MOSTLY SOLID with Recent Fixes
**Status:** Recent patches (Sessions 394, 2026-07-30, 2026-08-01) addressed critical cursor lifecycle bugs

**Recent Fixes Applied:**
- Cursor reuse instead of nested DatabaseContext (fixed "cursor already closed" errors)
- Position update failures now fail-fast instead of silent degradation
- Halt check errors properly escalated

**Known Working:**
- Stop-loss monitoring (SMA_50 - ATR calculation)
- Trailing stop adjustments
- Position P&L calculation
- Earnings date detection for gap risk

**Outstanding Issues:**
1. **Cursor lifecycle still fragile** (CRITICAL FIX SESSION 2026-08-01)
   - Code now passes cursor to avoid nested DatabaseContext
   - But if ANY nested call opens its own context, we break again
   - Risk: Future developers may not understand why cursor parameter is required

2. **Price data gaps handled but not alerted**
   - Silent price data loss detected (missing_symbols list) but only logged
   - No explicit alert if prices dropped for multiple symbols mid-day

3. **Unrealized P&L calculation assumes all trades have valid entry_price**
   - Fallback to algo_positions.avg_entry_price if NULL
   - But what if both are NULL? Silently skips position?

4. **Sector field missing risk**
   - Code returns NULL for missing sector (doesn't hide with 'Unknown')
   - But some callers may not handle NULL gracefully

5. **Halt check timeout not configured**
   - Calls market_events.is_halted() with no explicit timeout
   - Could hang if API unreachable

**Risk Level:** MEDIUM-HIGH
- Cursor lifecycle is better but still fragile
- P&L gaps could mask data corruption
- No timeouts on external API calls


### Phase 4: Reconciliation ✓ SOLID
**Status:** Robust partial fill detection and P&L tracking

**Known Working:**
- Partial fill reconciliation (detects when broker and local state diverge)
- Closed trade P&L scoped correctly (TODAY's closes only, not cumulative)
- Portfolio snapshot validation
- P&L variance detection with clear threshold (±0.5% alert, ±1.0% critical)

**Outstanding Issues:**
1. **No mechanism to force reconciliation if mismatches detected**
   - Code detects P&L variances but doesn't trigger corrective action
   - Operators must manually investigate and fix

2. **Sharpe ratio calculation can fail silently**
   - If daily_returns array too small or has zero variance, calculation fails
   - Error is logged but reconciliation continues with NULL Sharpe

3. **Unrealized P&L calculation is complex**
   - Multiple fallback paths if data missing
   - Not all paths validated for edge cases (zero quantity, negative prices, etc.)

**Risk Level:** LOW - solid implementation, mainly operational issues


### Phase 5: Exposure Policy ✓ WORKING but Limited Visibility
**Status:** Constrains portfolio size per regime, halts on policy violation

**Known Working:**
- Regime-based position sizing (T1/T2/T3 tiers)
- Market-adjusted exposure caps
- Halt-on-violations fail-fast behavior

**Outstanding Issues:**
1. **No dynamic regime adaptation documented**
   - Code mentions "regime_manager" but it's unclear if regimes can shift intra-day
   - What if VIX spikes at 2 PM ET and regime changes? Is Phase 5 re-run?

2. **Exposure constraints not validated comprehensively**
   - max_position_size_pct, max_positions_per_sector, max_leverage all required
   - But what if database config missing? Silent fallback to defaults?

3. **Market regime data staleness not checked**
   - Assumes market_exposure_daily is fresh (Phase 1 checks this, but no cross-phase validation)

**Risk Level:** MEDIUM - exposure logic sound, but regime dynamics unclear


### Phase 6: Exit Execution ✓ WORKING
**Status:** Executes exit recommendations from Phase 3, force-exits oversized positions

**Known Working:**
- Stop-loss detection triggers immediate exits
- Profit-target exits processed
- Force exit oversized positions (violating max_position_size_pct)
- Partial exits tracked correctly

**Outstanding Issues:**
1. **No circuit breaker on exit failures**
   - If exit executor crashes, subsequent positions not exited
   - Should have retry mechanism with exponential backoff

2. **Exit fill reconciliation only validates ONE-LEG exits**
   - Multi-leg exits (first take profit, then stop-loss) traced poorly
   - Complex exit scenarios may not reconcile correctly

3. **No explicit market hours check**
   - Assumes Phase 2 halts non-market-hours execution
   - But Phase 6 should validate execution_mode explicitly

**Risk Level:** MEDIUM - solid core logic, but complex multi-leg scenarios fragile


### Phase 7: Signal Generation ✓ WORKING with Known Limitations
**Status:** Robust signal quality scoring, strong anomaly detection

**Recent Fixes:**
- Signal quality scores computed inline (Session 384+)
- Anomaly detection: halts if buy_sell_daily count < 200 signals
- Composite score ranking (quality 25%, growth 20%, value 20%, positioning 15%, stability 12%, momentum 8%)

**Known Working:**
- Buy/sell signal filtering via pivot breakout logic
- SMA_50 uptrend confirmation
- Liquidity checks (ADV, dollar volume)
- Close quality filtering (rejects bottom-of-range closes)

**Outstanding Issues:**
1. **Universe gap: only ~4,700 of ~10,600 symbols have sufficient metrics** (CRITICAL LIMITATION)
   - stock_scores requires INNER JOIN to buy_sell_daily
   - Symbols without full metric coverage (quality/growth/value/positioning/stability) silently excluded
   - Affects 55% of tradable universe

2. **buy_sell_daily stale data not re-validated after Phase 1**
   - Phase 1 checks buy_sell_daily exists
   - But if EOD pipeline (4:05 PM) failed to populate TODAY's signals, Phase 7 still runs
   - Anomaly threshold (200 signals) may not catch all stale scenarios

3. **Signal quality score computation can timeout** (Session 284+)
   - Loader timeout (default 60s) may be insufficient for large symbol set
   - Timeout kills computation, signals incomplete
   - No automatic retry or degradation

4. **Technical data dependency not validated**
   - Phase 7 assumes technical_data_daily is fresh (Phase 1 checks this)
   - But if technical_data missing for a symbol, signal rejected after scoring complete
   - Wasted computation

5. **Trend template scoring optional** (Session 277+ fix)
   - Trend metrics not required for signals to qualify
   - But if included, can they affect ranking? Code initializes to None if missing

**Risk Level:** MEDIUM
- Core signal quality robust, but universe limitation significant
- Data freshness assumptions cascade from Phase 1 (good) but not re-validated (risky)


### Phase 8: Entry Execution ✓ WORKING with Risk Calculation Gaps
**Status:** Executes qualified signals, enforces position sizing and risk limits

**Recent Fixes:**
- Volume dryup handling: None values now handled gracefully (Session 341)
- Conservative defaults for missing exposure constraints (Session 338)
- base_type extraction from buy_sell_daily signals (Session 337)
- Safe defaults always run, not skipped on exceptions (Session 336)

**Known Working:**
- ATR-based stop loss calculation (max of H-L, |H-prevC|, |L-prevC|)
- SMA_50 support level checks
- Position sizing via PositionSizer (regime-aware, drawdown-adjusted)
- PreTradeChecks (size cap, duplicate prevention, minimum order)

**Outstanding Issues:**
1. **Total risk percentage calculation potentially broken** (HIGH RISK)
   - Calculates open position risk as SUM(entry_price - stop_loss_price) * quantity
   - But what if trades missing filled_qty or closed_qty? Calculation gives FALSE LOW risk
   - No validation that sum includes all open positions

2. **Entry price fallback chain unclear**
   - Uses trade.entry_price (from entry_execution)
   - Falls back to position.avg_entry_price if NULL
   - But what if both NULL? Silently skips?

3. **No idempotency key on order placement** (CRITICAL per memory)
   - If order request sent twice (network retry), Alpaca receives two separate orders
   - Positions can grow unexpectedly
   - Recommend: Use hash(symbol, size, stop_loss) as deterministic idempotency_key

4. **Exposure constraints can be None**
   - Phase 8 checks if exposure.halt_new_entries but doesn't validate other constraint fields
   - If exposure is None, Phase 8 should halt, but code may proceed with defaults

5. **Market hours check only at orchestrator level**
   - Phase 8 should validate market is open before executing
   - Assumes Phase 2 circuit breaker is always run first

6. **Price staleness not re-validated in Phase 8**
   - Phase 1 validates prices fresh
   - But Phase 8 runs hours later; price_daily may not include TODAY if market closed early
   - Afternoon runs especially risky

**Risk Level:** HIGH
- Entry risk calculation fragile, can underestimate exposure
- Idempotency issues could cause duplicate entries
- Price data assumptions cascade without re-validation


### Phase 9: Reconciliation ✓ SOLID
**Status:** Final audit of trades, positions, P&L; always runs

**Known Working:**
- Trade closure audit (reconciles fills against Alpaca broker)
- Position aggregate validation
- P&L variance tracking
- Daily return and cumulative return calculation

**Outstanding Issues:**
1. **No automatic healing if mismatches detected**
   - Detects P&L variance but doesn't correct database state
   - Manual operator intervention required

2. **Cumulative return calculation assumes unbroken history**
   - If a day is skipped (no orchestrator run), returns calculation wrong
   - No interpolation for missing days

**Risk Level:** LOW - mostly audit phase, limited trading impact


---

## SECTION 2: DASHBOARD (Python + React Frontend)

### Dashboard Status: ⚠️ PARTIALLY HARDENED

**Recent Fixes Applied:**
- IPv6 localhost stall fixed (Session 282): uses 127.0.0.1 not localhost
- Windows UTF-8 encoding fixed (Session 281): redirects stdout/stderr before Rich console creation
- Dev token security check added: ALLOW_DEV_TOKENS_TEST only auto-enabled when dev_server.py directly executed

**Working Well:**
- Auto-detection of dev server on localhost:3001
- Graceful fallback to AWS Lambda for production
- Watch mode (auto-refresh every 30-60s)
- Error boundary recovery (RenderRecovery)

**Outstanding Issues:**

1. **Panel rendering can silently fail**
   - If a fetcher returns None or malformed data, panel catches exception
   - Error boundary renders error message, but underlying data loss not visible to operators
   - Recommendation: Track fetch_error counts in monitoring

2. **Cognito auth timeout not configured**
   - If Cognito service slow, dashboard blocks on login
   - No explicit timeout, defaults to OS socket timeout (~300s)

3. **API response sanitization incomplete**
   - Dashboard sanitizes NULL values before rendering
   - But if API returns object with 10k+ keys (OOM scenario), sanitization itself can hang

4. **Watch mode refresh skips error handling**
   - If fetch fails mid-refresh, watch timer stops but no error logged
   - Dashboard appears frozen until user restarts

5. **No circuit breaker on repeated API errors**
   - If backend down, dashboard retries every N seconds indefinitely
   - Should backoff after 5-10 failures

6. **Mascot display brittle**
   - MASCOT_W constant hard-coded as terminal width
   - On narrow windows, mascot rendering broken
   - No graceful degradation

**Risk Level:** MEDIUM
- Core rendering solid, but error handling and timeouts need hardening
- Production dashboard may hang silently on API failures


---

## SECTION 3: DATA LOADING INFRASTRUCTURE

### Loader Status: ⚠️ UNEVEN QUALITY

**Loader Registry Issues (Session 275 Fix):**
- Registry centralized to prevent drift, but still fragile
- Three separate audit scripts had outdated/wrong mappings before fix
- Missing loaders: load_company_profile.py, load_analyst_*_*.py (restored 2026-07-27)
- Deprecated tables never removed: ttm_income_statement, ttm_cash_flow (60-63 days stale)

**Critical Loaders (Must be fresh for trading):**
1. **load_prices.py** - ✓ Working
   - Produces price_daily (core to all signals)
   - 90%+ symbol coverage required (reduced from 95%, Session 365)
   - No explicit NYSE/NASDAQ/OTC split validation

2. **load_technical_indicators.py** - ✓ Working
   - Produces technical_data_daily (SMA_50, ATR, etc.)
   - Required for Phase 8 stop-loss calculation
   - No stale data sentinel (relies on Phase 1 date check)

3. **load_market_status_daily.py** (consolidated Session 275) - ✓ Working
   - Produces market_health_daily, market_exposure_daily, market_sentiment
   - Optional columns (put_call_ratio, vix_level) handled gracefully in Phase 2
   - But market_exposure_daily required by Phase 5 (regime data)

4. **load_buy_sell_daily.py** - ⚠️ Critical Dependency
   - Produces buy_sell_daily (primary signal source)
   - Anomaly detection: Phase 7 halts if count < 200 signals
   - EOD pipeline (4:05 PM) must complete before evening orchestrator (5:30 PM)
   - **No recovery mechanism if pipeline stalls at 4:03 PM**

5. **load_stock_scores.py** - ⚠️ Metric Aggregation
   - Aggregates quality/growth/value/positioning/stability into composite_score
   - Required for Phase 7 ranking (INNER JOIN to signals)
   - **Universe limited to ~4,700 of ~10,600 symbols**
   - No incremental backfill (recomputes all daily)

**Enrichment Loaders (Nice-to-have, Phase 1 warns only):**
- load_earnings_calendar_sec.py
- load_sector_industry_daily.py
- load_growth/quality/value_metrics.py
- load_positioning_metrics.py
- load_risk_metrics_daily.py
- load_analyst_*.py

**Outstanding Loader Issues:**

1. **load_value_quality_growth_metrics.py duplicates**
   - load_enhanced_quality_growth_metrics.py also produces quality_metrics and growth_metrics
   - Which loader takes precedence? Database write order undefined
   - Recommendation: Consolidate into single loader with fallback to base metrics

2. **load_sec_cash_flow_metrics.py removed but deprecated tables not cleaned**
   - Session 275: Noted as "duplicated quality_metrics formulas exactly"
   - But quarterly_cash_flow still populated by load_financial_statements.py
   - Unclear if quarterly data used by any phase

3. **No rate-limit circuit breaker between loaders**
   - If SEC API rate-limited, subsequent loaders may fail in cascade
   - No backoff strategy documented

4. **Loader health monitoring incomplete**
   - data_loader_status table tracks completion_pct and symbol_count
   - But doesn't validate data quality (e.g., NaN prices, negative volumes, etc.)
   - Phase 1 only checks freshness/coverage, not data distribution anomalies

5. **Missing loader detection fragile**
   - If a loader name changes or is consolidated, health scripts must update
   - Session 275 fixed this for three independent scripts, but pattern repeats
   - Recommendation: Single source of truth (loader_registry.py now does this)

**Risk Level:** MEDIUM-HIGH
- Core loaders solid, but enrichment/consolidation creates confusion
- Universe limitation (55% excluded from signals) significant
- No automated healing for stalled pipelines


---

## SECTION 4: CONFIGURATION & ENVIRONMENT

### Config Status: ⚠️ COMPREHENSIVE but VALIDATION GAPS

**Recent Hardening (Sessions 281-365+):**
- Execution_mode validation (no silent fallback to paper trading)
- Alpaca credential validation (detects fake test credentials)
- Config value range validation (not just key existence)
- Database config load failures detected (not silent)
- All safety thresholds logged at startup

**Known Working:**
- algo_config table centralized (not scattered .env files)
- Config validation happens at orchestrator startup
- Missing required keys fail-fast
- Invalid value ranges detected

**Outstanding Issues:**

1. **Config change race conditions not prevented**
   - If operator updates algo_config mid-run, orchestrator may use stale cached values
   - No re-validation of config between phases
   - Recommendation: Lock algo_config during orchestrator run

2. **Environment variable precedence unclear**
   - Some config reads from .env, some from database, some from environment
   - If conflicts (e.g., execution_mode in .env vs. database), which wins?
   - Documentation needed

3. **Timeout config not comprehensive**
   - api_request_timeout_seconds configured
   - But individual phase timeouts not configurable (Phase 7 signal scoring hardcoded 60s)
   - If timeouts need adjustment, code changes required

4. **No config audit trail**
   - Database config_audit_log exists, but not populated
   - Operators can't see who changed what when

5. **Credential validation incomplete**
   - Detects TEST/FAKE Alpaca keys but not other providers (broker adapters)
   - If environment lacks Alpaca creds, code fails at first use (not startup)

**Risk Level:** MEDIUM
- Core config solid, but race conditions and precedence need hardening
- Lack of audit trail makes ops debugging hard


---

## SECTION 5: DATABASE & DATA INTEGRITY

### Database Status: ✓ SCHEMA SOLID but TRANSACTION SAFETY FRAGILE

**Recent Fixes Applied:**
- Exit engine transaction rollback wrapped in try-except (Session 281)
- Savepoint usage for data patrol: CRITICAL FIX for rollback handling
- LoaderStatusManager single-pathway (no race conditions)

**Known Issues:**

1. **Distributed locking via DynamoDB only in AWS** (CRITICAL in LOCAL_MODE)
   - LOCAL_MODE runs without locks, risks concurrent orchestrator runs
   - If developer runs orchestrator twice, both write to same tables
   - Recommendation: Use file-based locks in LOCAL_MODE

2. **ThreadedConnectionPool not used in all paths** (per memory)
   - Some code opens connections directly
   - Pool contention on high concurrency
   - Recommendation: Audit all db.connection calls

3. **ARRAY_AGG returns NULL not [] on zero rows** (per memory)
   - Callers must check for NULL, not empty list
   - Silent bugs if code assumes []

4. **Cascade delete risks**
   - No explicit CASCADE rules on foreign keys
   - Manual cleanup needed if position records deleted

5. **NULL value handling inconsistent**
   - Some code coalesces to 0, some to empty string, some leaves NULL
   - Recommendation: Explicit NULL handling in every query

**Risk Level:** MEDIUM
- Schema solid, but transaction and locking edge cases fragile


---

## SECTION 6: KNOWN CRITICAL BUGS IN MEMORY

(Extracted from MEMORY.md load-bearing rules)

1. ✓ **exit_engine_transaction_abort** - Wrap ROLLBACK TO SAVEPOINT in try-except
   - Status: FIXED, memory rule enforced

2. ✓ **dev_server_pool_not_threadsafe** - Use ThreadedConnectionPool
   - Status: Partial, need audit of all connection paths

3. ✓ **array_agg_null_on_zero_rows** - ARRAY_AGG FILTER is NULL not []
   - Status: Developers aware, some paths still risky

4. ✓ **broker_order_no_idempotency_key** - Use deterministic idempotency_key
   - Status: NOT YET FIXED, Phase 8 still vulnerable to order duplication

5. ✓ **phase3_halt_check_swallowed** - Phase 3 halt failures must halt
   - Status: FIXED, halt checks now explicitly escalated

6. ✓ **position_sync_phase1_integration** - Call position sync in Phase 1 before phase_1_data_freshness
   - Status: FIXED, Session 2026-08-01 integrated position sync before Phase 1

7. ⚠️ **loader_priority_phase_dependency** - Phase dependencies require PHASE_1_CRITICAL loaders
   - Status: Implemented but not fully validated

8. ⚠️ **all_time_average_masks_degradation** - All-time avg hides frozen loaders
   - Status: Known limitation, no fix yet

9. ⚠️ **phase_status_hardcoded_success** - Check counts not just status
   - Status: Partially addressed, some phases still risky

10. ⚠️ **phase3_null_sector_trend** - Degrade gracefully on data gaps, don't halt
    - Status: Implemented but no comprehensive data gap simulation tests

---

## SECTION 7: TESTING & VERIFICATION

### Test Suite Status: ✓ PASSING (2,097 tests collected, 0 skipped failures visible)

**Test Coverage:**
- API null sanitization ✓
- Backtest zero-trade edge case ✓
- Edge cases (empty data, extreme values, null) ✓
- Infrastructure (untracked positions, reconciliation) ✓
- Integration (AWS Lambda flow, orchestrator phases) ✓
- Cognito auth endpoints ✓

**Outstanding Test Gaps:**

1. **No orchestrator end-to-end test** (all phases 1-9)
   - Unit tests exist for individual phases
   - But integrated flow (Phase 1 → 7 → 8 → 9) untested in live mode
   - Local orchestrator test (scripts/run_local_orchestrator.py) can be run manually

2. **No chaos/fault injection tests**
   - What if database goes down mid-phase? (not tested)
   - What if Alpaca API timeout? (circuit breaker tested, but late-phase timeout not)
   - What if loader stalls at 99% completion? (anomaly threshold tested, but timeout recovery not)

3. **No performance/load tests**
   - What if price_daily has 100k+ symbols? (Phase 1 slowness not measured)
   - What if 1000+ signals qualified? (Phase 7 ranking performance unknown)
   - What if Phase 8 tries to enter 50 positions? (concurrent order throttling untested)

4. **No data integrity tests for complex scenarios**
   - Multi-leg exits: broker reports partial fill, reconciliation missing leg 2
   - Split/dividend handling: no tests for position quantity adjustment
   - Earnin gap: position held through earnings unplanned (gap risk untested)

**Risk Level:** MEDIUM
- Core happy-path tests pass, but edge cases and integration gaps significant


---

## SECTION 8: OPERATIONAL READINESS

### Monitoring & Observability: ⚠️ PARTIAL

**What's Monitored:**
- Orchestrator run status (started, succeeded, failed)
- Loader health (data_loader_status completion_pct)
- Position count and P&L snapshots
- Circuit breaker trips

**What's NOT Monitored:**
- Phase-specific performance (no per-phase timing logs)
- Data quality anomalies (prices, volumes, distributions)
- Fetch error rates (dashboard API calls)
- Orchestrator dependency freshness (cross-phase validation)

**Alert Configuration:**
- Phase 1 data freshness halts configured ✓
- Phase 2 circuit breaker triggers halt ✓
- But no escalation for soft failures (e.g., 30% symbol coverage in price_daily → Phase 1 warns, continues)

**Risk Level:** MEDIUM
- Basic monitoring in place, but blind spots in performance and data quality


---

## SECTION 9: DEPLOYMENT & INFRASTRUCTURE

### AWS Lambda & ECS: ⚠️ PARTIALLY VALIDATED

**Known Working:**
- Lambda API endpoint /api/algo/status ✓
- EventBridge scheduler triggers orchestrator at correct times ✓
- RDS connection via secrets manager ✓
- Position sync from Alpaca broker ✓

**Outstanding Issues:**

1. **Lambda concurrency not enforced**
   - Multiple EventBridge rules could trigger same Lambda simultaneously
   - DynamoDB lock prevents execution, but no queue/backoff
   - If lock held by failed run, next run waits indefinitely

2. **ECS task timeout on hung loaders not enforced**
   - Orchestrator has kill-hung-loaders logic, but ECS task timeout is AWS-side
   - If both timeout mechanisms fail, orphan processes consume resources

3. **No gradual rollout mechanism**
   - Code changes deployed to all Lambda functions simultaneously
   - If bug introduced, all orchestrator runs fail

4. **Terraform module brittle**
   - IaC changes require manual testing (not automated)
   - Configuration drift not detected

**Risk Level:** MEDIUM
- Infrastructure mostly solid, but lambda and ECS failure modes not fully hardened


---

## SECTION 10: CRITICAL GAPS SUMMARY

### MUST FIX BEFORE PRODUCTION (Block release):

1. **Phase 8: Order idempotency key missing** (HIGH RISK)
   - Network retries can cause duplicate orders
   - Fix: Implement deterministic idempotency_key in order submission

2. **Phase 8: Total risk calculation potentially underestimates** (HIGH RISK)
   - If trades missing filled_qty or stopped_qty, SUM returns FALSE LOW risk
   - Fix: Validate all open trades have complete price/qty data before calculating risk

3. **Phase 3: Cursor lifecycle fragile** (MEDIUM-HIGH RISK)
   - Recent fixes help, but still fragile to nested DatabaseContext calls
   - Fix: Document cursor parameter as MANDATORY when phase has open context; add asserts

4. **Phase 1: Symbol coverage gaps not fully characterized** (MEDIUM RISK)
   - 312 missing symbols from price_daily; unknown universe impact
   - Fix: Audit which symbols dropped and why (delisted? suspended? never existed?)

5. **Phase 7: Universe limitation undocumented** (MEDIUM RISK)
   - Only 4,700 of 10,600 symbols have sufficient metrics for stock_scores
   - Users unaware signals exclude 55% of tradable symbols
   - Fix: Document universe limitation, consider backfill effort for metric loaders


### SHOULD FIX BEFORE PRODUCTION (Improve reliability):

6. **Phase 5-7: Regime data staleness not re-validated after Phase 1**
   - Assumes market_exposure_daily fresh, but hours may pass between Phase 1 and Phase 7
   - Fix: Add optional re-check in Phase 7 before using regime constraints

7. **Phase 8: Price data staleness not re-validated**
   - Phase 1 checks prices fresh; Phase 8 assumes same data still valid
   - Afternoon runs risky if market closed early or data pipeline halted
   - Fix: Add price freshness re-check in Phase 8 before entry

8. **Dashboard: No circuit breaker on repeated API errors**
   - If backend down, dashboard retries indefinitely, appearing frozen
   - Fix: Backoff strategy (exponential, max 10 retries, 5-minute pause)

9. **Loader: buy_sell_daily stale sentinel incomplete**
   - Anomaly threshold (200 signals) may not catch all stale scenarios
   - Fix: Add explicit date check in Phase 7 to re-validate buy_sell_daily freshness

10. **Config: No change propagation between phases**
    - If operator updates config mid-orchestrator-run, phases may see stale values
    - Fix: Option 1 - lock config for run duration; Option 2 - reload at phase start

11. **Distributed lock: LOCAL_MODE bypass**
    - LOCAL_MODE runs without locks, risks concurrent writes
    - Fix: Use file-based locks in LOCAL_MODE (e.g., /tmp/algo_orchestrator.lock)

12. **Lambda: Concurrency not enforced**
    - Multiple EventBridge triggers could fire simultaneously
    - Fix: Lambda reserved concurrency = 1 (or use SQS queue for async scheduling)


### NICE-TO-HAVE HARDENING (Performance & UX):

13. **Loader metrics deduplication**
    - load_enhanced_quality_growth_metrics.py duplicates load_value_quality_growth_metrics.py outputs
    - Fix: Consolidate into single loader with fallback logic

14. **Config audit trail**
    - Database table exists but not populated
    - Fix: Enable audit logging on algo_config UPDATE/DELETE operations

15. **Phase timeouts configurable**
    - Phase 7 signal scoring timeout hardcoded 60s
    - Fix: Move to algo_config table as phase7_signal_timeout_seconds

16. **Per-phase performance monitoring**
    - No timing logs per phase (only orchestrator-wide)
    - Fix: Log phase_start, phase_end, phase_duration for each phase

17. **Data quality anomaly detection**
    - Phase 1 checks freshness/coverage; doesn't check distributions (e.g., unusual volatility jumps)
    - Fix: Add data patrol checks for price and volume anomalies


---

## SECTION 11: RECENT COMMITS & FIXES APPLIED

**Session 365:** Reduced price_daily coverage threshold from 95% to 90% (allowed natural gaps)
**Session 384:** Signal quality scores computed inline during signal generation
**Session 394:** Position monitor can generate exit recs even in paper mode
**Session 2026-07-28:** Broker order adapter re-exported as algo.infrastructure.get_alpaca_base_url (potential name confusion)
**Session 2026-07-30:** Position monitor cursor lifecycle fixed (retry on "cursor already closed")
**Session 2026-07-31:** Orchestrator startup validation: 90% price_daily coverage check
**Session 2026-08-01:** Position sync integrated before Phase 1; cursor usage audited across codebase
**Most recent commit:** Handle volume_dryup=None gracefully in base_type classifier

---

## SECTION 12: RECOMMENDED ACTION PRIORITY

### IMMEDIATE (This Week):
1. ✅ Identify 312 missing symbols from price_daily (data audit)
2. ✅ Implement idempotency keys in Phase 8 order submission
3. ✅ Add risk calculation validation (all trades have complete data)
4. ✅ Document Phase 7 universe limitation (4,700 of 10,600)

### SHORT-TERM (Next 2 Weeks):
5. Add price freshness re-check in Phase 8
6. Implement circuit breaker for dashboard API errors
7. Add LOCAL_MODE file-based locking
8. Consolidate quality/growth/value metric loaders
9. Enable config audit trail logging

### MEDIUM-TERM (Next Month):
10. Add per-phase performance monitoring
11. Implement data patrol anomaly detection
12. Expand unit tests for edge cases (chaos injection)
13. Configure phase-specific timeouts in database
14. Lambda reserved concurrency enforcement

### ONGOING:
- Monitor orchestrator runs for data gaps or stalls
- Collect feedback on Phase 7 universe limitation impact
- Evaluate trader feedback on signal quality and execution
- Plan metric loader expansion to cover broader symbol universe

---

## CONCLUSION

**Overall System State: FUNCTIONAL but NEEDS HARDENING**

**Bulletproofness Assessment:**
- Core orchestrator phases (1-9): ✓ Working with known edge cases
- Data loading: ⚠️ Solid but universe limitation significant
- Dashboard: ⚠️ Functional but error handling needs hardening
- Configuration: ✓ Comprehensive but race conditions possible
- Testing: ✓ Happy-path covered; edge cases and chaos untested
- Monitoring: ⚠️ Basic health checks; blind spots in performance/quality

**Production Readiness:** CONDITIONAL
- System can trade safely in controlled conditions
- Known gaps present: idempotency, risk calculation, data staleness, concurrency
- Before scaling up: fix must-fix items (especially idempotency, risk validation)
- Before high-volume testing: implement should-fix hardening measures

**Confidence Level by Area:**
- Position Monitoring (Phase 3): 75% (cursor lifecycle fragile)
- Signal Generation (Phase 7): 70% (universe limitation, staleness assumptions)
- Entry Execution (Phase 8): 60% (idempotency, risk calculation gaps)
- Exit Execution (Phase 6): 85% (solid, limited edge cases)
- Dashboard: 65% (rendering good, error handling weak)

This audit provides a complete roadmap for bulletproofing the system. None of the identified issues are architectural showstoppers, but collectively they represent real risks if left unaddressed.


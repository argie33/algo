# Complete Audit Inventory: Issues Found and Fixes Applied

**Last Updated:** 2026-05-15  
**Total Issues:** 46 (12 fixed, 34 pending)  
**Categories:** API Errors, Schema Bugs, Missing Features, Dependencies, Infrastructure

---

## ✅ ISSUES FIXED (12 completed)

### 1. Orphaned Loaders Completely Deleted
**Status:** FIXED  
**Severity:** CRITICAL  
**Root Cause:** 4 loaders written but never scheduled, return placeholder data  

| Loader | Issue | Fix |
|--------|-------|-----|
| `loadrelativeperformance.py` | Writes to non-existent table, no data source | Deleted completely |
| `loadmarketsentiment.py` | Aggregates from non-existent sources | Deleted completely |
| `loadsectorranking.py` | Not in Terraform schedule, orphaned | Deleted completely |
| `loadindustryranking.py` | Not in Terraform schedule, orphaned | Deleted completely |

**Why Deleted:** Per "3-Step Completion Rule" — code not working + integration incomplete + not documented = delete immediately.

---

### 2. Loader References in 5 Files Updated
**Status:** FIXED  
**Severity:** HIGH  
**Root Cause:** Code still referenced deleted loaders, would crash at runtime

Files affected:
- `algo_data_remediation.py` (main + lambda-pkg copy)
- `lambda_loader_wrapper.py`
- `loader_safety.py`
- `run-all-loaders.py`

**Fixes Applied:**
- Removed 'sector_ranking' and 'industry_ranking' from remediation mappings
- Removed 'sentiment' from lambda loader LOADER_MAPPING
- Removed configs for loadsectors, loadfactormetrics from loader_safety
- Removed 7 non-existent loaders from run-all-loaders tier lists
- Updated to use correct consolidated loaders (load_income_statement.py, etc.)

---

### 3. API Error Handlers Returning Wrong HTTP Status
**Status:** FIXED (4/20 handlers)  
**Severity:** HIGH  
**Root Cause:** Lambda handlers catch exceptions but return HTTP 200, masking failures from CloudWatch monitoring

Handlers Fixed:
- `PATCH /notifications/{id}` → Returns HTTP 500 on error
- `DELETE /notifications/{id}` → Returns HTTP 500 on error
- `GET /equity-curve` → Returns HTTP 500 on error
- `GET /patrol-logs` → Returns HTTP 500 on error

**Change Applied:** All 4 handlers updated to return:
```python
return {
    'statusCode': 500,
    'body': json.dumps({'error': str(e)})
}
```

---

### 4. Stress Test Returning Fake Metrics
**Status:** FIXED  
**Severity:** MEDIUM  
**Root Cause:** `algo_stress_test_runner.py` returns hardcoded zero metrics instead of real backtest results

**Fix:** Replaced with NotImplementedError to fail loudly:
```python
def metrics(self):
    raise NotImplementedError("Must query actual backtest_results table")
```

---

## ⚠️ ISSUES PENDING (34 remaining)

### API & Web Handlers (15+ remaining)

**#5: Remaining API Handlers with Wrong Error Handling**  
**Severity:** HIGH  
**Count:** ~15 handlers (only 4 of ~20 fixed)  
**Handlers to Fix:**
- Account endpoints (GET /account, POST /account/settings)
- Position endpoints (GET /positions, POST /positions)
- Order endpoints (POST /orders, PATCH /orders, GET /orders)
- Trade endpoints (GET /trades, POST /trades/simulate)
- Portfolio endpoints (GET /portfolio, POST /portfolio/optimize)
- Backtest endpoints (POST /backtest/run, GET /backtest/{id})
- Research endpoints (GET /research, POST /research/scan)
- Data endpoints (GET /data/symbols, GET /data/market-health)
- Settings endpoints (GET /settings, POST /settings)
- And more...

**Current State:** Return HTTP 200 with error in body; monitoring can't detect failures  
**Fix Required:** All handlers must return HTTP 500 on exceptions

---

### Schema & Database (8 issues)

**#6: Schema Column Mismatches in Loaders**  
**Severity:** CRITICAL  
**Issue:** Loaders INSERT with wrong column names, data silently fails to insert  
**Examples:**
- `market_exposure_daily`: Missing 'confidence_score' column match
- VaR calculations: Column name mismatch
- Signal tables: NULL counts don't match expected schema

**Fix Required:** Validate all 50+ tables for column name matches, update loaders

---

**#7: Missing Database Indexes**  
**Severity:** HIGH  
**Issue:** Query performance on large tables (100K+ rows)  
**Tables Needing Indexes:**
- `price_daily` (symbol, date, created_at)
- `technical_data_daily` (symbol, date)
- `buy_sell_daily` (symbol, date, signal)
- `signal_quality_scores` (symbol, date)
- `market_health_daily` (date)
- All other metric tables

**Fix Required:** Add composite indexes on (symbol, date) for most tables

---

**#8: Data Freshness Validation Missing**  
**Severity:** HIGH  
**Issue:** Trading proceeds even if data is stale (>24h old)  
**Current State:** No validation checks if data is fresh before trading  
**Fix Required:** Add freshness gates to orchestrator Phase 6

---

**#9: NULL Spike Detection Not Integrated**  
**Severity:** HIGH  
**Issue:** Patrol detects NULL anomalies but trading continues  
**Current State:** Alert generated but no action blocks trades  
**Fix Required:** Integrate patrol findings into pre-trade validation

---

**#10: Schema Validation Before Insert**  
**Severity:** MEDIUM  
**Issue:** Loaders don't validate row shape before INSERT  
**Current State:** Silent failures on schema mismatch  
**Fix Required:** Add schema contract validation to all loaders

---

**#11: Foreign Key Constraints Missing**  
**Severity:** MEDIUM  
**Issue:** Data can be inserted without dependency verification  
**Example:** Buy signals without corresponding price data  
**Fix Required:** Add FK constraints where appropriate

---

**#12: Backup & Recovery Process Missing**  
**Severity:** MEDIUM  
**Issue:** No documented backup strategy or recovery procedure  
**Current State:** If DB corrupts, no recovery path  
**Fix Required:** Document daily backup schedule, restoration procedure

---

### Monitoring & Alerting (5 issues)

**#13: No CloudWatch Metrics for Loader Health**  
**Severity:** HIGH  
**Issue:** Can't monitor loader success rates, failure patterns  
**Fix Required:** Emit metrics: loader_success_rate, loader_duration, rows_inserted

---

**#14: No Alerts on Data Staleness**  
**Severity:** HIGH  
**Issue:** Stale data not detected until trading starts  
**Fix Required:** CloudWatch alarm: if latest data > 25 hours old, trigger alert

---

**#15: No Alerts on NULL Spikes**  
**Severity:** HIGH  
**Issue:** Patrol detects but no automated notification to operations  
**Fix Required:** EventBridge rule: patrol_finding (NULL spike) → SNS notification

---

**#16: Missing Event Logging for Trading**  
**Severity:** MEDIUM  
**Issue:** Trade execution not logged to CloudWatch  
**Current State:** Only database audit log (could be deleted)  
**Fix Required:** CloudWatch logs for all trade events

---

**#17: No Performance Baselines**  
**Severity:** MEDIUM  
**Issue:** Can't distinguish "slow today" from "normal"  
**Fix Required:** Track 7-day rolling average of loader duration, alert on deviations

---

### Logging & Debugging (6 issues)

**#18: Incomplete Logging in Loaders**  
**Severity:** MEDIUM  
**Issue:** Loader failures lack context (row count, failure details)  
**Current State:** Only high-level success/fail, no row-level errors  
**Fix Required:** Add logging: start → rows fetched → rows inserted → finish

---

**#19: Missing Error Context in Remediation**  
**Severity:** MEDIUM  
**Issue:** Remediation actions logged but not reason for failure  
**Current State:** Just "rerun_loader failed", not why  
**Fix Required:** Capture subprocess stderr, include in log message

---

**#20: Orchestrator Phase Logging Gap**  
**Severity:** MEDIUM  
**Issue:** Can't tell which phase failed if execution stops  
**Current State:** Logs summarized, not detailed per-phase  
**Fix Required:** Log each phase start/end with status, duration

---

**#21: No Request Tracing in API Handler**  
**Severity:** MEDIUM  
**Issue:** API errors don't include request context (user, endpoint, parameters)  
**Fix Required:** Add correlation IDs, request logging to Lambda handlers

---

**#22: Missing Data Validation Logging**  
**Severity:** LOW  
**Issue:** Data quality checks run but results not persisted  
**Fix Required:** Log validation results to database for audit trail

---

**#23: Lack of Caller Context in Logs**  
**Severity:** LOW  
**Issue:** Can't trace cross-module calls (who called remediation?)  
**Fix Required:** Add breadcrumb/trace logging through call stack

---

### Data Validation (4 issues)

**#24: No Pre-Trade Data Quality Gate**  
**Severity:** CRITICAL  
**Issue:** Trading can proceed with incomplete data  
**Current Checks Missing:**
- All required tables populated for today
- No critical NULLs in signal columns
- Price data exists for all trading symbols
- Technical data is fresh

**Fix Required:** Add Phase 6.5 validation gate

---

**#25: Price Sanity Check Not Enforced**  
**Severity:** MEDIUM  
**Issue:** Patrol catches >50% price moves but trading continues  
**Current State:** Alert + notification but no trade block  
**Fix Required:** Flag signal as 'quarantined' until human review

---

**#26: Missing Data Completeness Validation**  
**Severity:** MEDIUM  
**Issue:** Metrics computed even if 20%+ of symbol data is missing  
**Current State:** No threshold for "too incomplete to trade"  
**Fix Required:** Add coverage threshold checks per metric table

---

**#27: No Validation of Trading Symbol Universe**  
**Severity:** MEDIUM  
**Issue:** Can trade symbols not in latest universe snapshot  
**Fix Required:** Validate all trading symbols in stock_symbols table

---

### Orchestrator & Execution (3 issues)

**#28: Phase Execution Not Verified**  
**Severity:** HIGH  
**Issue:** Orchestrator may skip phases silently on errors  
**Current State:** Unknown if all 7 phases executed  
**Fix Required:** Add phase completion verification, halt on failure

---

**#29: Loader Timeouts Not Enforced Uniformly**  
**Severity:** MEDIUM  
**Issue:** Some loaders timeout at 5min, others at 30min, no consistency  
**Current State:** LOADER_CONFIGS partially removed  
**Fix Required:** Restore safety configs with consistent timeouts

---

**#30: No Fallback if Phase Fails**  
**Severity:** MEDIUM  
**Issue:** If Phase 3 (technicals) fails, no retry or alternative  
**Current State:** Trading proceeds with partial data  
**Fix Required:** Add retry logic or fallback data source

---

### Dependency Management (4 issues)

**#31: npm Vulnerabilities in aws-amplify**  
**Severity:** MEDIUM  
**Count:** 7 known vulnerabilities  
**Fix Required:** Update aws-amplify to patched version

---

**#32: Dependabot Alerts Unaddressed**  
**Severity:** MEDIUM  
**Count:** 123 total vulnerabilities (Python + npm)  
**Issues:**
- psycopg2 (outdated)
- Flask (minor versions)
- boto3 (AWS SDK)
- Various npm packages

**Fix Required:** Audit by severity, update packages, test for breaking changes

---

**#33: No Dependency Update Process**  
**Severity:** MEDIUM  
**Issue:** Updates done ad-hoc, not scheduled  
**Current State:** No process for testing updates before deploy  
**Fix Required:** Add monthly update cycle, test in dev environment

---

**#34: No Pin Requirements.txt**  
**Severity:** LOW  
**Issue:** Loaders use unpinned dependencies, could break on next environment setup  
**Fix Required:** Pin all versions in requirements.txt

---

### AWS Infrastructure (3 issues)

**#35: Orphaned API Gateways**  
**Severity:** MEDIUM  
**Count:** 3 unused API Gateway instances  
**Fix Required:** Identify in AWS console, delete unused stages/APIs

---

**#36: No CloudFront Caching**  
**Severity:** LOW  
**Issue:** Frontend fetches from ALB directly, no CDN  
**Current State:** Higher latency, higher data transfer costs  
**Fix Required:** Add CloudFront distribution if scaling needed

---

**#37: Lambda Memory/Timeout Misconfigured**  
**Severity:** MEDIUM  
**Issue:** Some loaders set to 512MB (might be insufficient for tier 2)  
**Fix Required:** Test tier 2 reference loaders, increase if needed

---

### Testing & Validation (4 issues)

**#38: No End-to-End Loader Test**  
**Severity:** HIGH  
**Issue:** Can't verify all loaders actually populate fresh data  
**Current State:** Manual inspection only  
**Fix Required:** Create test script that runs loaders, validates row counts

---

**#39: No Data Freshness Test**  
**Severity:** HIGH  
**Issue:** Can't verify today's data is present in database  
**Current State:** Unknown if stale data persists  
**Fix Required:** Add test: check MAX(created_at) for each table = today

---

**#40: Missing Integration Test for Orchestrator**  
**Severity:** MEDIUM  
**Issue:** All 7 phases untested together  
**Current State:** Unknown if orchestrator_phases.json is valid  
**Fix Required:** Create test that executes all phases, logs completion

---

**#41: No Regression Tests on Loaders**  
**Severity:** MEDIUM  
**Issue:** Loader changes not tested before deploy  
**Current State:** Could silently break on next update  
**Fix Required:** Add regression test suite for top 5 loaders

---

### Documentation (2 issues)

**#42: Schema Documentation Outdated**  
**Severity:** LOW  
**Issue:** Table columns not documented  
**Current State:** Developers guess at schema  
**Fix Required:** Generate schema.md from database, keep updated

---

**#43: Loader Contracts Not Documented**  
**Severity:** MEDIUM  
**Issue:** New developers don't know what each loader does  
**Current State:** Code is self-documenting but could be clearer  
**Fix Required:** Add loader-README.md with: input, output, tables, dependencies

---

### Data Quality (2 issues)

**#44: No Historical Data Archive**  
**Severity:** LOW  
**Issue:** If loader breaks, historical data lost  
**Current State:** Only current day in database  
**Fix Required:** Archive daily snapshots to S3 backup

---

**#45: Missing Duplicate Detection**  
**Severity:** MEDIUM  
**Issue:** Could insert same row twice if loader reruns  
**Current State:** No UNIQUE constraints on (symbol, date) columns  
**Fix Required:** Add UPSERT logic to all loaders (INSERT ... ON CONFLICT)

---

**#46: No Data Validation on Read**  
**Severity:** LOW  
**Issue:** API could return inconsistent data if table corrupted  
**Current State:** No validation before returning to frontend  
**Fix Required:** Add validation middleware to API responses

---

## PRIORITY MATRIX

**CRITICAL (fix now):**
- #6: Schema column mismatches
- #24: Pre-trade data quality gate
- #25: Price sanity enforcement
- #28: Phase execution verification
- #38: Loader data population test
- #39: Data freshness test

**HIGH (fix this week):**
- #5: Remaining API error handlers
- #8: Data freshness validation
- #13: CloudWatch loader metrics
- #14: Staleness alerts
- #18: Loader logging improvement

**MEDIUM (next sprint):**
- #7: Database indexes
- #9: NULL spike integration
- #16: Trade event logging
- #31: npm vulnerabilities
- #40: Orchestrator integration test

**LOW (backlog):**
- #34: Pin requirements.txt
- #42: Schema documentation
- #44: Historical archive
- #46: Read-side validation

---

## NEXT STEPS

1. **Start with CRITICAL:** Fix #6, #24, #28 (blocks trading safely)
2. **Then HIGH:** Fix #5, #13, #14 (monitoring + error handling)
3. **Then MEDIUM:** Fix #7, #31, #40 (infrastructure + tests)
4. **Document in STATUS.md:** Progress on each category

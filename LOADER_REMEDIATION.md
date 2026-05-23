# Loader System Remediation Plan

**Date:** 2026-05-23  
**Status:** In Progress  
**Total Issues Found:** 28 (13 critical, 15 warnings)

---

## CRITICAL ISSUES (Fix Now)

### 1. Database Connection Pool Exhaustion
**Affected Loaders:**
- `financials_ttm_cashflow` (current parallelism: 4)
- `financials_ttm_income` (current parallelism: 4)
- `swing_trader_scores` (current parallelism: 8)

**Error:** `psycopg2.errors.ConnectionException: Timed-out waiting to acquire database connection`

**Root Cause:** Multiple loaders running simultaneously with high parallelism exhaust RDS connection pool

**Fix:**
```bash
# Reduce LOADER_PARALLELISM to 2 for each loader
# Register new task definitions with:
LOADER_PARALLELISM=2

# Then re-run loaders sequentially (not in parallel)
```

**Priority:** CRITICAL - This blocks multiple loaders

---

### 2. SEC EDGAR API Rate Limiting
**Affected Loaders (7):**
- financials_annual_balance
- financials_annual_cashflow
- financials_annual_income
- financials_quarterly_balance
- financials_quarterly_cashflow
- financials_quarterly_income
- financials_ttm_income

**Error:** `ERROR: SEC ticker cache failed after 5 retries (total 62s): 429 Too Many Requests`

**Root Cause:** SEC EDGAR API rate limits to ~10 requests/sec; loaders exceed this

**Fix:**
```python
# In utils/sec_edgar_client.py, implement:
# 1. Exponential backoff: 1s, 2s, 4s, 8s, 16s between retries
# 2. Request batching: Bundle ticker lookups
# 3. Cache TTL: Keep ticker cache for 24 hours min
# 4. Rate limiting: Max 8 concurrent requests to SEC

# Current retries: 5 attempts with linear backoff
# New: 5 attempts with exponential backoff + jitter
```

**Priority:** HIGH - Affects 7 loaders, but data eventually loads

---

## HIGH PRIORITY ISSUES

### 3. yfinance Authentication Error
**Affected Loaders:**
- earnings_history

**Error:** `WARNING: Auth error for CHR (attempt 1): 401 Client Error: Unauthorized`

**Root Cause:** Some symbols fail auth with yfinance API (CHR specifically)

**Fix:**
- Validate yfinance API credentials
- Skip symbols with consistent 401 errors
- Log failed symbols separately for manual review

---

### 4. signals_daily / naaim_data Errors
**Affected Loaders (2):**
- signals_daily
- naaim_data

**Error:** JSON log entries without clear error messages

**Fix:**
- Pull full error logs from CloudWatch
- Add better error context in loader output
- Fix root cause based on actual error

---

## MEDIUM PRIORITY ISSUES

### 5. stock_scores Configuration Mismatch
**Issue:** Task definition `algo-stock_scores-loader` points to `load_quality_metrics.py`

**Current State:**
- LOADER_FILE: `load_quality_metrics.py`
- LOADER_NAME: `stock_scores`
- Table EXISTS with 10,157 rows (being populated)

**Fix Option A (Simplest):**
- Rename task definition to `algo-quality_metrics-loader`
- Verify quality_metrics table is populated

**Fix Option B (If stock_scores needs separate loader):**
- Create `load_stock_scores.py` if not present
- Update task definition to point to it

---

## LOW PRIORITY ISSUES

### 6. Warning Logs (15 non-critical warnings)
- Rate limit warnings (expected during throttling)
- JSON format issues (cosmetic)
- Symbol-level failures (logged, data still loads)

**Action:** Monitor but do not block

---

## IMPLEMENTATION ROADMAP

### Phase 1: Connection Pool (Today)
1. [ ] Reduce parallelism for 3 timeouts loaders to 2
2. [ ] Register new task definitions
3. [ ] Test individual loaders
4. [ ] Run sequentially, not parallel

### Phase 2: SEC EDGAR (This week)
1. [ ] Update SEC client with exponential backoff
2. [ ] Implement request batching
3. [ ] Add cache TTL management
4. [ ] Test with finance loaders

### Phase 3: Signals & NAAIM (This week)
1. [ ] Pull detailed error logs
2. [ ] Fix root causes
3. [ ] Test end-to-end

### Phase 4: Config Cleanup (Next week)
1. [ ] Resolve stock_scores definition
2. [ ] Audit all task definitions
3. [ ] Document loader mappings

---

## VALIDATION CHECKLIST

After each fix, verify:
- [ ] Loader completes with exit code 0
- [ ] Data written to expected table
- [ ] Row counts match previous runs (allow ±5%)
- [ ] CloudWatch logs show no errors
- [ ] Database connection pool stays <80% utilization

---

## TESTING SEQUENCE

1. **Unit Test:** Run individual loader locally
   ```bash
   python3 loaders/load_financials_ttm_cashflow.py --parallelism 2
   ```

2. **Integration Test:** Run via ECS with fixed config
   ```bash
   aws ecs run-task --cluster algo-cluster --task-definition algo-financials_ttm_cashflow-loader
   ```

3. **Load Test:** Run multiple loaders sequentially
   ```bash
   for loader in financials_ttm_cashflow financials_ttm_income swing_trader_scores; do
     aws ecs run-task --cluster algo-cluster --task-definition algo-${loader}-loader
     sleep 60  # Wait for one to finish
   done
   ```

4. **Full Validation:** Run all loaders, check data integrity

---

## ROLLBACK PLAN

If fixes break anything:
1. Stop failing tasks immediately
2. Revert task definition to previous version
3. Check CloudWatch for root cause
4. Re-test fix before re-deploying

---

## DOCS & REFERENCES

- DB Connection limits: `terraform/modules/database/main.tf`
- SEC EDGAR client: `utils/sec_edgar_client.py`
- Loader configs: Each loader's `LOADER_PARALLELISM` setting
- Terraform task definitions: `terraform/modules/loaders/main.tf`


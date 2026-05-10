# Prioritized Action Plan - Stock Analytics Platform

**Date**: 2026-05-10  
**Status**: Ready for implementation  
**Total Effort**: ~40 hours  
**Estimated Timeline**: 5-7 days working

---

## Phase 0: Quick Wins (2-3 hours) - START HERE

### 0.1 Test All Frontend Pages (30 mins)
```bash
cd webapp/frontend
npm run dev
```
Then navigate to each page in browser and document:
- Which pages load without errors
- Which pages have missing data (show "—")
- Which pages have console errors
- Which API calls fail

**Pages to test** (28 total):
1. MarketOverview
2. SectorAnalysis  
3. EconomicDashboard
4. CommoditiesAnalysis
5. SentimentAnalysis
6. ScoresDashboard
7. TradingSignals
8. DeepValuePicks
9. SwingCandidates
10. PortfolioDashboard
11. TradeTracker
12. Optimizer
13. HedgeHelper
14. AlgoDashboard
15. SignalIntelligence
16. BacktestResults
17. ServiceHealth
18. NotificationsPage
19. AuditTrail
20. Settings
21. MarketsHealth
... (8 more)

**Expected Result**: Document which pages are broken and why

### 0.2 Verify Phase 3 Endpoints Exist (30 mins)
Test these endpoints:
```bash
curl http://localhost:3001/api/earnings/calendar
curl http://localhost:3001/api/financials/AAPL/balance-sheet
curl http://localhost:3001/api/stocks/companies
```

**Expected**: All return valid data, not 404

### 0.3 Check Loader Status (30 mins)
Find recent logs:
```bash
aws logs tail /aws/lambda/stocks-loader --follow
# Or locally:
ls -lt load*.py | head -10
```

**Check**:
- When did each loader last run?
- Did it succeed or fail?
- How much data loaded?

**Expected**: All major loaders ran in last 24 hours

### 0.4 Check Data Freshness (30 mins)
Query database (via local docker or AWS):
```sql
SELECT table_name, MAX(date) as latest_date, COUNT(*) as row_count
FROM (
  SELECT 'price_daily' as table_name, date, 1 FROM price_daily
  UNION ALL SELECT 'momentum_metrics', date, 1 FROM momentum_metrics
  UNION ALL SELECT 'earnings_history', quarter, 1 FROM earnings_history
) grouped
GROUP BY table_name
ORDER BY latest_date DESC;
```

**Expected**: All tables have data from 2026-05-09 or later

---

## Phase 1: Critical Issues (6-8 hours)

### 1.1 Fix Null Scores & Missing Metrics (3-4 hours)
**Problem**: Frontend shows null values for momentum_score, quality_score, etc.
**Root Cause**: Loaders haven't run recently or Phase 1 validators are rejecting data

**Action**:
1. Check if loadstockscores.py ran recently
   ```bash
   grep "loadstockscores" /var/log/syslog | tail -20  # Or AWS logs
   ```
2. If not, run manually:
   ```bash
   python3 loadstockscores.py --symbols AAPL,MSFT,GOOGL
   ```
3. Check for errors in output
4. If validation errors, review data_tick_validator.py logic
5. Run full load:
   ```bash
   python3 loadstockscores.py --parallelism 8
   ```
6. Verify scores populated in database
7. Test /api/scores/stockscores again

**Expected Result**: All scores have values, no more nulls

### 1.2 Implement Complete Phase 3 Endpoints (2-3 hours)
**Problem**: 26 endpoints missing or incomplete
**Focus**: Top 3 blocked pages

**Action**:
1. **Verify Earnings Endpoints**
   - Check `webapp/lambda/routes/earnings.js` - endpoints exist
   - Test `/api/earnings/calendar` - returns data?
   - Test `/api/earnings/sector-trend` - returns data?
   - If working, move to next

2. **Verify Financials Endpoints**
   - Check `webapp/lambda/routes/financials.js`
   - Test `/api/financials/AAPL/balance-sheet`
   - Test `/api/financials/AAPL/income-statement`
   - Test `/api/stocks/companies`

3. **If any missing**: Implement based on Phase 3 guide (see PHASE_3_MISSING_ENDPOINTS.md)

**Expected Result**: EarningsCalendar page loads and displays data

### 1.3 Commit Current Work (30 mins)
```bash
git add -A
git commit -m "fix: Fix null scores, complete Phase 3 endpoints"
git push
```

---

## Phase 2: Data Integrity (8-10 hours)

### 2.1 Consolidate Database Schema (3-4 hours)
**Problem**: 5 different initialization patterns
**Action**:
1. Compare schemas:
   - Local: `init_db.sql` (1080 lines)
   - AWS: `terraform/modules/database/init.sql` (112 lines)
   - Python: `init_database.py` (1926 lines)

2. Choose authoritative source:
   - **Recommendation**: Use `init_db.sql` (most comprehensive)
   - It's already proven locally

3. Update others:
   - Update Terraform to use same schema
   - Make `init_database.py` optional (for testing)

4. Test:
   - Deploy to AWS test environment
   - Verify tables exist
   - Verify local docker and AWS schemas match

**Expected Result**: One schema, consistent everywhere

### 2.2 Integrate Phase 1 into Top 10 Loaders (4-5 hours)
**Current State**: Only 4 loaders have Phase 1 (loadpricedaily, loadfeargreed, loadaaiidata, loadnaaim)
**Action**: Add to 10 most important loaders

**Top 10 Loaders by Criticality**:
1. loadstockscores.py - **HIGHEST PRIORITY**
2. loadtechnicalsdaily.py
3. loadearningshistory.py
4. loadfactormetrics.py
5. loadsectors.py
6. loadsentiment.py
7. loadmarket.py
8. loadbuysellweekly.py
9. loadquarterlyincomestatement.py
10. loadetfpricedaily.py

**For Each Loader**:
```python
# Add these 3 lines at top:
from data_tick_validator import validate_[type]_tick
from data_provenance_tracker import DataProvenanceTracker
from data_watermark_manager import WatermarkManager

# In __init__:
self.tracker = DataProvenanceTracker(...)
self.watermark_mgr = WatermarkManager(...)

# In transform():
# Call validate_[type]_tick() for each row
# Track valid rows with self.tracker.record_tick()
# Record errors with self.tracker.record_error()
```

**Expected Result**: All 10 loaders have data validation + provenance tracking

### 2.3 Test Data Integrity End-to-End (1-2 hours)
```bash
# Run one Phase 1 loader
python3 loadstockscores.py --symbols AAPL

# Check provenance tracker recorded data
python3 -c "
from data_provenance_tracker import DataProvenanceTracker
tracker = DataProvenanceTracker(...)
tracker.get_run_status(run_id)  # Should show success
"

# Verify watermark prevents re-loading
python3 loadstockscores.py --symbols AAPL
# Should skip already-loaded dates
```

**Expected Result**: Phase 1 features working end-to-end

---

## Phase 3: Codebase Cleanup (4-6 hours)

### 3.1 Delete Obsolete Files (2-3 hours)
**Remove**:
- 75+ `Dockerfile.*` files (superseded by Terraform)
  ```bash
  rm Dockerfile.aaiidata Dockerfile.alpacaportfolio ... # All except Dockerfile
  git rm Dockerfile.*.
  ```
- Duplicate backtest files:
  - Delete `algo_backtest.py` (keep `backtest.py`)
  - Delete `algo_phase2_backtest_comparison.py` (keep `backtest_compare.py`)
- Old test output files:
  - Delete `api-test.json`, `api-test.log`, `comprehensive-test-report.json`, etc.

**Commit**:
```bash
git add -A
git commit -m "chore: Remove obsolete Dockerfiles and test artifacts"
```

### 3.2 Archive Documentation Files (1-2 hours)
**Move to `memory/` folder**:
- CODEBASE_AUDIT_2026_05_09.md
- DATA_INTEGRITY_AUDIT_FINAL_2026_05_10.md
- PHASE_1_COMPLETE.txt
- PHASE_1_COMPLETION_SUMMARY.md
- PHASE_1_DATA_INTEGRITY_SUMMARY.md
- PHASE_1_DEPLOYMENT_ACTION_PLAN.md
- PHASE_1_DEPLOYMENT_STATUS.md
- PHASE_1_LOADER_UPDATE_CHECKLIST.md
- PHASE_2_COMPLETION_SUMMARY.md
- PHASE_3_MISSING_ENDPOINTS.md
- SCHEMA_SYNC_ISSUE_AND_FIX.md
- SESSION_COMPLETION_SUMMARY.md
- README_PHASE_1_NEXT_STEPS.txt
- Plus 10+ other documentation files

**Consolidate**:
```bash
mkdir -p docs/archive/2026-05-10
mv PHASE_*.md docs/archive/2026-05-10/
mv CODEBASE_AUDIT*.md docs/archive/2026-05-10/
# Keep only: COMPREHENSIVE_ISSUES_AUDIT_2026_05_10.md and ACTION_PLAN_PRIORITIZED_2026_05_10.md in root
```

**Commit**:
```bash
git add -A
git commit -m "chore: Archive Phase 1-3 completion documentation"
```

### 3.3 Verify Git Status (30 mins)
```bash
git status
# Should show:
# - All modified files clean
# - No untracked files
# - Ready for deployment
```

---

## Phase 4: Testing & Verification (8-10 hours)

### 4.1 End-to-End Frontend Testing (4-5 hours)
**Manual Testing Checklist**:
```
[ ] ScoresDashboard: Loads all stocks, scores visible, no "—"
[ ] TradingSignals: Shows signals with all fields populated
[ ] PortfolioDashboard: Shows holdings, P&L, all metrics
[ ] MarketOverview: Shows indices, breadth, sentiment data
[ ] EarningsCalendar: Shows earnings with dates
[ ] FinancialData: Shows balance sheets, income statements
[ ] AlgoDashboard: Shows trades, positions, P&L
[ ] BacktestResults: Shows equity curves, trade details
[ ] All 28 pages: Load without console errors
[ ] All charts: Render with data
[ ] All tables: Paginate correctly
```

**Automation**:
- Create Playwright test for critical paths
- Run: `npm run test:integration`

### 4.2 API Contract Testing (2-3 hours)
**Create test suite** for all endpoints:
```bash
# Test endpoint response format
for endpoint in /api/scores/stockscores /api/market/indices /api/signals/stocks; do
  curl -s http://localhost:3001$endpoint | validate_json_schema.py
done
```

**Verify**:
- All responses have `{success, items/data, pagination}`
- No wrapped objects where arrays expected
- All required fields present

### 4.3 Data Integrity Verification (2-3 hours)
```bash
# Check Phase 1 loaders working
python3 test_phase_1_4_integration.py

# Check data freshness
python3 check_data.py --table price_daily --warn-if-stale 1day

# Check watermark system
python3 test_watermark_incremental.py

# Check provenance tracking
python3 -c "from data_provenance_tracker import DataProvenanceTracker; ..."
```

### 4.4 Performance Check (1-2 hours)
```bash
# Test critical queries
time curl -s http://localhost:3001/api/scores/stockscores?limit=5000

# Check database query times
# Should be <1s for all common queries
```

---

## Phase 5: Deployment (2-3 hours)

### 5.1 Local Verification
```bash
# Run full test suite
npm run test
python3 -m pytest tests/

# Deploy locally
docker-compose down
docker-compose up -d
```

### 5.2 AWS Staging
```bash
# Deploy to staging
gh workflow run deploy-all-infrastructure.yml --ref main

# Monitor logs
aws logs tail /aws/lambda/stocks-api --follow
aws logs tail /aws/lambda/stocks-loader --follow

# Test endpoints
curl -s https://[staging-api]/api/scores/stockscores
```

### 5.3 Production Deployment
```bash
# After verification
gh workflow run deploy-all-infrastructure.yml --ref main

# Monitor
aws logs tail /aws/lambda/algo-orchestrator --follow

# Verify
curl -s https://[prod-api]/api/algo/positions
```

---

## Summary of Changes

### Files Modified
- `webapp/lambda/routes/*.js` - Complete Phase 3 endpoints
- `load[X].py` - Add Phase 1 to 10 loaders
- `terraform/modules/database/init.sql` - Consolidate schema
- `docker-compose.yml` - Update to use single schema
- `init_database.py` - Reference consolidated schema

### Files Deleted
- 75+ `Dockerfile.*` files
- `algo_backtest.py`, `algo_phase2_backtest_comparison.py`
- Old test output files
- Moved 20+ audit files to archives

### Files Created
- `COMPREHENSIVE_ISSUES_AUDIT_2026_05_10.md`
- `ACTION_PLAN_PRIORITIZED_2026_05_10.md`
- Playwright test suite for frontend
- API contract test suite
- Data integrity test suite

### Commits Required
1. "fix: Complete Phase 3 endpoints and fix null scores"
2. "fix: Integrate Phase 1 data integrity into top 10 loaders"
3. "fix: Consolidate database schema for dev/prod parity"
4. "chore: Remove obsolete files and archive documentation"
5. "test: Add integration and contract tests"

---

## Success Criteria

✅ All 28 frontend pages load without errors
✅ No more null values in critical metrics
✅ All Phase 3 endpoints implemented and tested
✅ Top 10 loaders have Phase 1 validation
✅ Database schema unified locally and in AWS
✅ All tests passing (unit + integration + E2E)
✅ No console errors on any page
✅ Data freshness <1 day old for all tables
✅ Loader health monitoring working
✅ Codebase cleaned up (no obsolete files)

---

## Timeline

| Phase | Tasks | Effort | Days |
|-------|-------|--------|------|
| **0** | Quick Wins | 2-3h | 0.5 |
| **1** | Critical Fixes | 6-8h | 1 |
| **2** | Data Integrity | 8-10h | 1.5 |
| **3** | Cleanup | 4-6h | 0.5 |
| **4** | Testing | 8-10h | 1.5 |
| **5** | Deployment | 2-3h | 0.5 |
| **TOTAL** | | ~30-40h | 5-7 days |

---

## Current Status

✅ All APIs deployed and responding
✅ Most frontend pages built
✅ Phase 1 pattern exists (4 loaders have it)
✅ Phase 2 API standardization complete
✅ Phase 3 endpoints partially complete

❌ Phase 3 endpoints not fully verified
❌ Data metrics showing null values
❌ Loaders not all enhanced with Phase 1
❌ Database schema not consolidated
❌ Codebase not cleaned up

---

## Risk Assessment

**Risk Level**: LOW ✅

- All changes are non-breaking
- Phase 1 is backward compatible
- Cleanup doesn't affect deployed code
- Can rollback easily with git

**Mitigations**:
- Test locally before deploying
- Use feature flags for Phase 1 rollout
- Keep backups of database schema
- Gradual loader upgrade (one at a time)

---

## Questions to Resolve Before Starting

1. **Earnings/Financials Data**: Does database have this data loaded?
   - If not, need to run those loaders first

2. **Momentum/Technical Metrics**: Why are they null?
   - Are loadtechnicalsdaily, loadfactormetrics running?

3. **Schema Priority**: Which should be source of truth?
   - Recommend: Keep init_db.sql (most comprehensive)

4. **Loader Upgrade Order**: Should we do all 54 at once or gradually?
   - Recommend: Top 10 first, then rest

5. **Cleanup Safety**: Delete Dockerfiles and test files?
   - Confirm these are truly obsolete

---

**Next Action**: Start with Phase 0 (30 mins) to identify actual blockers, then work through phases in order.


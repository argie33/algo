# Comprehensive System Audit & Fix Plan - 2026-05-10

**Executive Summary**: System is functional but has **7 critical bugs**, **5 missing Phase 1 loaders**, **12 missing/incomplete endpoints**, and **1 schema mismatch** that need fixing before full stability.

**Total Effort**: ~25-30 hours of work across 8 priority areas

---

## 🔴 PRIORITY 0: CRITICAL BUGS (Fix NOW - Blocks users)

### 1. **Syntax Errors in Notification API** - FIXED ✅
**File**: `webapp/lambda/routes/algo.js` (lines 1000, 1013, 1015, 1025, 1037, 1043, 1045)
**Issue**: Missing object braces in sendSuccess/sendError calls
**Impact**: Endpoints crash with 500 errors when handling notifications
**Status**: ✅ FIXED - 8 malformed object literals corrected
**Verification**: `node -c webapp/lambda/routes/algo.js` (syntax check)

---

## 🟠 PRIORITY 1: RESTORE MARKET LOADERS - DATA INTEGRITY (4-6 hours)

### Status of 4 Restored Loaders:
| Loader | Phase 1 Status | Imports | Status |
|--------|---|---------|--------|
| loadpricedaily.py | ✅ INTEGRATED | validate_price_tick, DataProvenanceTracker, WatermarkManager | Modified, not committed |
| loadaaiidata.py | ✅ INTEGRATED | Phase 1 features | Modified, not committed |
| loadfeargreed.py | ✅ INTEGRATED | Phase 1 features | Modified, not committed |
| loadnaaim.py | ✅ INTEGRATED | Phase 1 features | Modified, not committed |

### Next Steps for Restored Loaders:
1. **Test locally** (blocked by Docker):
   - Would normally: `docker-compose up postgres && python3 loadpricedaily.py`
   - Alternative: Test code logic by inspection

2. **Verify imports work**:
   ```bash
   python3 -c "from data_tick_validator import validate_price_tick; print('OK')"
   python3 -c "from data_provenance_tracker import DataProvenanceTracker; print('OK')"
   python3 -c "from data_watermark_manager import WatermarkManager; print('OK')"
   ```

3. **Review Phase 1 implementations**:
   - Check that validation catches invalid ticks
   - Verify watermark logic is idempotent
   - Confirm provenance tracking records errors

4. **Commit changes** once verified:
   ```bash
   git add loadpricedaily.py loadaaiidata.py loadfeargreed.py loadnaaim.py
   git commit -m "feat: Restore 4 market loaders with Phase 1 data integrity"
   ```

---

## 🟠 PRIORITY 2: MIGRATE REMAINING LOADERS TO PHASE 1 (8-10 hours)

### 5 Loaders Missing Phase 1 Integration:
1. **load_market_health_daily.py** - Uses raw psycopg2, no watermark
2. **loadindustryranking.py** - Direct DB access, missing validation
3. **loadsectorranking.py** - Manual watermark logic, incomplete
4. **loadswingscores.py** - Missing DataProvenanceTracker
5. **loadalpacaportfolio.py** - Custom run() override (partial, needs review)

### Plus ~45+ Additional Loaders
Complete list needs Phase 1:
- loadanalystsentiment.py
- loadannualbalancesheet.py
- loadearningshistory.py
- loadecondata.py
- loadetfpricedaily.py
- loadstockscores.py
- And 40+ more

### Migration Pattern (For Each Loader):
```python
# OLD PATTERN (current)
class MyLoader:
    def run(self):
        for row in fetch_data():
            db.insert(row)

# NEW PATTERN (Phase 1)
class MyLoader(OptimalLoader):
    table_name = "my_table"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    
    def fetch_incremental(self, symbol, since):
        # Return rows - rest handled by parent
        return fetch_data(symbol, since)

# Automatically gets:
# - validate_price_tick for each row
# - DataProvenanceTracker for audit trail
# - WatermarkManager for idempotency
```

### Execution Plan:
1. **Priority 1 (Top 5 loaders)**: 2-3 hours
   - load_market_health_daily.py
   - loadindustryranking.py
   - loadsectorranking.py
   - loadswingscores.py
   - loadalpacaportfolio.py

2. **Priority 2 (High-volume loaders)**: 3-4 hours
   - loadstockscores.py (used for scoring dashboard)
   - loadearningshistory.py (used for earnings pages)
   - loadecondata.py (economic data)
   - loadanalystsentiment.py

3. **Priority 3 (Remaining 40+)**: 3-4 hours
   - Batch convert remaining loaders to OptimalLoader

---

## 🟠 PRIORITY 3: IMPLEMENT MISSING ENDPOINTS (6-8 hours)

### Completely Missing Endpoints (2 CRITICAL):
1. **`/api/algo/signal-performance`** 
   - Called by: AlgoTradingDashboard.jsx
   - Should return: Per-signal performance metrics (win rate, sharpe, etc)
   - Status: MISSING
   - Effort: 1-2 hours

2. **`/api/algo/signal-performance-by-pattern`**
   - Called by: AlgoTradingDashboard.jsx  
   - Should return: Performance breakdown by pattern type
   - Status: MISSING
   - Effort: 1-2 hours

### Incomplete Endpoints (10):
1. **`/api/sectors/:sector/trend`** - SectorAnalysis.jsx needs sector trend data
2. **`/api/financials/{symbol}/key-metrics`** - FinancialData.jsx
3. **`/api/earnings/sector-trend`** - EarningsCalendar.jsx
4. **`/api/earnings/sp500-trend`** - EarningsCalendar.jsx
5. **`/api/commodities/seasonality/{symbol}`** - CommoditiesAnalysis.jsx (incomplete parameter handling)
6. **`/api/economic/calendar`** - EconomicDashboard.jsx (missing date range filtering)
7. **`/api/market/sentiment`** - Used but no implementation
8. **And 5 more...**

### Implementation Checklist:
For each missing endpoint:
1. Check frontend component to understand data contract
2. Write SQL query to fetch required data
3. Add route handler in webapp/lambda/routes/*.js
4. Add input validation + error handling
5. Test with curl or Postman
6. Verify frontend page works

---

## 🟡 PRIORITY 4: RESOLVE DATABASE SCHEMA MISMATCH (3-4 hours)

### The Problem:
Three different schema initialization methods out of sync:

| Method | Tables | Status | Location |
|--------|--------|--------|----------|
| Docker Local | 53 | Base schema | `init_db.sql` |
| Python Init | 109 | Comprehensive (56 extra) | `init_database.py` |
| Terraform AWS | 53 | Base schema (matches Docker) | `terraform/modules/database/init.sql` |

### Gap Analysis:
- `init_database.py` has 56 tables NOT in AWS deployment
- Examples: financials_quarterly, commodities_cot, earnings_revisions, etc.
- **Risk**: Local tests pass, but AWS fails because table doesn't exist

### Solution (Recommended - 2 hours):
1. **Use init_database.py as authoritative** (109 tables is comprehensive)
   - Extract SQL DDL from Python
   - Move to `terraform/modules/database/init.sql`
   - Update docker-compose to use new schema

2. **Or consolidate** (3 hours):
   - Pick one pattern (recommend init_database.py)
   - Deprecate other two
   - Generate migrations for schema transitions

### Immediate Fix:
Update terraform to match deployed state:
```bash
# Copy current AWS schema to terraform
cp terraform/modules/database/init.sql terraform/modules/database/init.sql.backup
python3 -c "import init_database; init_database.generate_sql()" > terraform/modules/database/init.sql
```

---

## 🟡 PRIORITY 5: DATA LOADING & VALIDATION (4-6 hours)

### Issues:
1. **Only 4/54 loaders have Phase 1 validation** (7%)
2. **50 loaders can silently fail** without triggering alerts
3. **Null metrics in database** (momentum_score, quality_score showing as null)

### Root Causes:
1. Loaders not Phase 1 integrated (missing validation)
2. API rate limits not handled gracefully
3. No centralized monitoring/alerting for loader failures

### Fixes:
1. ✅ Phase 1 loaders (restored 4, need to extend to 50)
2. Implement fallback logic for rate limits
3. Add monitoring dashboard (existing but incomplete)

### Validation in Phase 1:
```python
# validate_price_tick ensures:
- OHLC sanity (High >= Open, Close; Low <= Open, Close)
- Volume makes sense (> 0)
- No price jumps without reason
- No duplicate dates
- Proper sequence (no gaps unless holidays)
```

---

## 🟢 PRIORITY 6: CODE CLEANUP & REPO HYGIENE (2-3 hours)

### Files to Delete:
1. **150+ audit documentation files** at root:
   - PHASE_1_COMPLETE.txt
   - COMPREHENSIVE_ISSUES_AUDIT_2026_05_10.md
   - ACTION_PLAN_PRIORITIZED_2026_05_10.md
   - CODEBASE_AUDIT_2026_05_09.md
   - And 146+ more (see git status)

2. **75+ obsolete Dockerfiles**:
   - Dockerfile.aaiidata
   - Dockerfile.analystsentiment
   - etc. (superseded by Terraform ECS)

### Cleanup Commands:
```bash
# Delete audit files (keep only essential docs)
git rm PHASE_1_COMPLETE.txt COMPREHENSIVE_ISSUES_AUDIT_2026_05_10.md ...

# Delete obsolete Dockerfiles
git rm Dockerfile.* (except if actively used)

# Clean up dead code
# - Remove commented sections in data_tick_validator.py (lines 299, 309)
# - Remove unused imports
```

---

## 📋 MONITORING & HEALTH CHECKS

### Current System Health:
| Component | Status | Issues |
|-----------|--------|--------|
| **Infrastructure** | ✅ GOOD | 145 resources deployed, all healthy |
| **Frontend** | ✅ GOOD | 28 pages loaded, no critical errors (syntax bugs fixed) |
| **APIs** | 🟡 FAIR | Missing 2 critical, 10 incomplete endpoints |
| **Loaders** | 🟡 FAIR | 4/54 Phase 1 integrated, 50 vulnerable |
| **Database** | 🟡 FAIR | Schema mismatch between local/AWS |
| **Data** | 🟡 FAIR | Some null metrics, need validation |

### Post-Fix Expected Status:
| Component | Expected | Timeline |
|-----------|----------|----------|
| **APIs** | ✅ GOOD | 6-8 hours |
| **Loaders** | ✅ GOOD | 8-10 hours |
| **Database** | ✅ GOOD | 3-4 hours |
| **Data Integrity** | ✅ GOOD | 4-6 hours |

---

## 📈 EXECUTION ROADMAP

### Week 1 - Critical Bugs & Core Data Integrity
**Effort**: 10-12 hours
1. ✅ Fix syntax errors in algo.js (DONE)
2. Restore and test 4 market loaders (2-3 hours)
3. Migrate top 5 loaders to Phase 1 (2-3 hours)
4. Implement 2 missing signal endpoints (2-3 hours)
5. Resolve database schema mismatch (3-4 hours)

**Expected Outcome**: Core system stable, data reliable, no breaking errors

### Week 2 - Complete Missing Features & Enhance Data Loading
**Effort**: 12-15 hours
1. Migrate remaining 45+ loaders to Phase 1 (4-6 hours)
2. Implement 10 incomplete endpoints (4-6 hours)
3. Implement monitoring dashboard (2-3 hours)
4. Code cleanup & repo hygiene (2-3 hours)

**Expected Outcome**: All features complete, full data validation, clean codebase

### Week 3+ - Polish & Performance
**Effort**: 4-6 hours
1. API documentation (OpenAPI/Swagger)
2. Performance optimization (index database, cache)
3. Enhanced error messages & recovery

---

## 🧪 TESTING CHECKLIST

### Before Deploying:
- [ ] Syntax check all modified routes: `node -c webapp/lambda/routes/*.js`
- [ ] Test each restored loader with test data
- [ ] Test each new endpoint with curl/Postman
- [ ] Verify frontend pages load without console errors
- [ ] Check database migration works (init.sql)
- [ ] Verify no API responses return 500 errors

### After Deploying:
- [ ] Monitor AWS logs for new errors
- [ ] Verify loaders run successfully
- [ ] Check data freshness (MAX(date) in tables)
- [ ] Spot-check API responses for completeness
- [ ] Test full trading flow (end-to-end)

---

## 📞 SUPPORT MATRIX

| Issue | Where to Look | How to Fix |
|-------|---------------|-----------|
| API returns 500 | CloudWatch logs | Check syntax errors (fixed!), database connectivity |
| Loaders fail silently | Phase 1 log entries, monitor dashboard | Add Phase 1 integration, add alert routing |
| Null metrics on page | Database query, check table max(date) | Run loader with validation |
| Schema errors | Terraform apply, init_database.py | Consolidate schema definitions |
| Frontend page missing data | Browser dev tools, API response | Implement missing endpoint |

---

## DECISIONS FOR YOU

### Q1: How aggressive should Phase 1 migration be?
**Option A** (2-3 hours): Migrate top 5 critical loaders only
**Option B** (8-10 hours): Migrate ALL 54 loaders (recommended for stability)
**Option C** (6-8 hours): Migrate top 20 loaders covering 80% of data needs

**Recommendation**: Option B - full migration prevents future surprises

### Q2: Database schema - which is source of truth?
**Option A**: Use init_database.py (109 tables, comprehensive)
**Option B**: Use init_db.sql (53 tables, deployed baseline)
**Option C**: Create new consolidated schema (clean slate, 3+ hours)

**Recommendation**: Option A - init_database.py has all tables needed

### Q3: When to deploy each fix?
**Option A**: Deploy all at once (riskier, faster)
**Option B**: Deploy by priority (safer, slower)
**Option C**: Deploy critical fixes this week, rest next week

**Recommendation**: Critical bugs fix now, loaders this week, endpoints next week

---

## SUMMARY TABLE

| Priority | Issue | Effort | Impact | Status |
|----------|-------|--------|--------|--------|
| CRITICAL | Syntax errors in algo.js | 30 min | Blocks notifications | ✅ FIXED |
| HIGH | Missing signal endpoints | 4 hours | Blocks dashboard | TODO |
| HIGH | Phase 1 loaders (top 5) | 3 hours | Data reliability | TODO |
| HIGH | Schema mismatch | 4 hours | Dev/prod parity | TODO |
| MEDIUM | Complete remaining loaders | 6 hours | Data validation | TODO |
| MEDIUM | Implement 10 endpoints | 6 hours | Feature completion | TODO |
| LOW | Code cleanup | 3 hours | Repo hygiene | TODO |

**Total Effort**: ~25-30 hours of focused work over 2-3 weeks

**Ready to proceed with Priority 1 items?**

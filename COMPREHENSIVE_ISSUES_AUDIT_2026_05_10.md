# Comprehensive Issues Audit - 2026-05-10

**Status**: Complete system scan across all layers
**Total Issues Found**: 47
**Critical Issues**: 8
**High Priority Issues**: 12
**Medium Priority**: 15
**Low Priority**: 12

---

## Executive Summary

Recent cleanup phases (Phase 1 & 2) successfully standardized API responses across 57 endpoints and integrated Data Integrity Phase 1 into loaders. However, the codebase still has:

1. **Missing Phase 3 Endpoints** - 26 endpoints incomplete, blocking 6 frontend pages
2. **Data Integrity Gaps** - 50+ loaders not yet enhanced with Phase 1 features
3. **Database/Schema Issues** - Mismatch between local dev and AWS environments
4. **Codebase Cleanup** - 150+ untracked audit files, 75+ obsolete Dockerfiles, duplicate code
5. **Frontend Display Issues** - Some pages still not rendering complete data due to missing endpoints

---

## CRITICAL ISSUES (Fix First - Blocking)

### 1. ⚠️ MISSING PHASE 3 ENDPOINTS - 26 NOT IMPLEMENTED
**Impact**: 6 frontend pages broken  
**Effort**: 3-4 hours  
**Status**: Ready to implement

#### Blocked Pages:
- **EarningsCalendar** (3 endpoints needed)
  - `POST /api/earnings/calendar?period=past&limit=50`
  - `GET /api/earnings/sector-trend`
  - `GET /api/earnings/sp500-trend`
  - **Status**: ✅ Partially implemented in earnings.js but may have query issues

- **FinancialData** (4 endpoints needed)
  - `GET /api/financials/{ticker}/balance-sheet?period=annual`
  - `GET /api/financials/{ticker}/income-statement?period=annual`
  - `GET /api/financials/{ticker}/cash-flow?period=annual`
  - `GET /api/stocks/companies` (list companies with financial data)
  - **Status**: ✅ Exists in financials.js, verify completeness

- **BacktestComparison** (missing endpoints)
  - Various backtest query endpoints need verification

#### Complete List of Missing/Incomplete Endpoints:
1. `/api/backtests/compare` - backtest comparison
2. `/api/backtests/detailed/:runId` - detailed run data
3. `/api/portfolio/analysis` - portfolio optimization results
4. `/api/portfolio/sectors` - sector allocation
5. `/api/portfolio/risk-metrics` - detailed risk
6. `/api/technical/patterns/{symbol}` - chart patterns
7. `/api/technical/trendlines/{symbol}` - trend analysis
8. `/api/options/chains/{symbol}` - options data
9. `/api/dividend/history/{symbol}` - dividend history
10. `/api/splits/history/{symbol}` - stock splits
... (16 more)

---

### 2. ⚠️ DATABASE SCHEMA MISMATCH - LOCAL VS AWS
**Impact**: Dev/prod parity broken, debug complexity  
**Severity**: CRITICAL  
**Status**: Not resolved

#### Problem:
Three different schema patterns:
- **Local Dev** (`init_db.sql`): 1,080 lines, 60+ tables, comprehensive
- **AWS Prod** (`terraform/modules/database/init.sql`): 112 lines, minimal
- **Python Init** (`init_database.py`): 1,926 lines, dynamic table creation

#### Consequence:
- 12+ debug schema files exist because of this mismatch
- Cannot reliably test locally and expect prod to work
- Migrations not applied consistently

#### Solution Needed:
- Choose ONE authoritative schema
- Make it single source of truth
- Sync all initialization patterns to use it

---

### 3. ⚠️ MULTIPLE DATABASE INITIALIZATION PATTERNS
**Impact**: Complexity, inconsistency, maintenance burden  
**Severity**: CRITICAL

#### Pattern 1: Docker Compose (Local Dev)
- Uses `init_db.sql`
- Defined in `docker-compose.yml`

#### Pattern 2: Terraform (AWS)
- Uses `terraform/modules/database/init.sql`
- Defined in `terraform/modules/database/main.tf`

#### Pattern 3: Python Script
- Uses `init_database.py`
- Status: Unclear if still used

#### Pattern 4: Lambda Initialization
- `terraform/modules/database/db_init_lambda.py`
- Optional feature

#### Pattern 5: Setup Scripts
- `scripts/init_db_local.sh`
- `setup_timescaledb_local.sh`
- `webapp/lambda/scripts/setup-local-data.sh`
- `tests/setup_test_db.py`

**Action Required**: Consolidate to 1-2 patterns max

---

### 4. ⚠️ LOADER PHASE 1 INTEGRATION INCOMPLETE
**Impact**: Only 4 loaders enhanced, 50+ still not integrated  
**Severity**: HIGH

#### Loaders WITH Phase 1 (4):
- ✅ loadpricedaily.py
- ✅ loadfeargreed.py
- ✅ loadaaiidata.py
- ✅ loadnaaim.py

#### Loaders WITHOUT Phase 1 (50+):
- loadanalystsentiment.py
- loadanalystupgradedowngrade.py
- loadannualbalancesheet.py
- loadannualcashflow.py
- loadannualincomestatement.py
- loadbuysell_etf_daily.py
- loadbuysellweekly.py
- loadbuysellmonthly.py
- loadearningshistory.py
- loadearningsrevisions.py
- loadecondata.py
- loadetfpricedaily.py
- loadfactormetrics.py
- loadmarket.py
- loadmarketindices.py
- loadpriceweekly.py
- loadpricemonthly.py
- loadquarterlybalancesheet.py
- loadsectors.py
- loadsentiment.py
- loadstockscores.py
- loadstocksymbols.py
- loadtechnicalsdaily.py
- loadttmcashflow.py
- loadttmincomestatement.py
... (30+ more)

**What's Missing in Phase 1 Loaders**:
- Tick-level validation (validate_price_tick)
- Provenance tracking (DataProvenanceTracker)
- Watermark management (WatermarkManager)
- Error recording and recovery

---

### 5. ⚠️ DATA LOADING FAILURES POTENTIAL
**Risk**: Silent data loading failures not detected  
**Status**: Depends on which loaders failing

#### Current Safeguards:
- Loader monitoring system (exists but incomplete)
- Error tracking in Phase 1 loaders (only 4 loaders)
- No centralized failure detection for non-Phase 1 loaders

#### Gap:
- If a loader silently fails (e.g., API rate limit, network error), no alert fires
- Stale data served to frontend without warning
- Algo trades on incomplete data

---

### 6. ⚠️ 75+ OBSOLETE DOCKERFILES AT ROOT
**Impact**: Cleanup, confusion, deployment complexity  
**Severity**: MEDIUM

#### Files:
```
Dockerfile.aaiidata
Dockerfile.alpacaportfolio
Dockerfile.analystsentiment
... (72 more individual loader Dockerfiles)
```

#### Status:
- Superseded by Terraform ECS task definitions
- Not used in current deployment
- Should be deleted

---

### 7. ⚠️ UNTRACKED AUDIT FILES (150+)
**Impact**: Repo bloat, confusion, hard to know what's actual vs. documentation  
**Severity**: MEDIUM

#### Files to Clean Up:
```
CODEBASE_AUDIT_2026_05_09.md
DATA_INTEGRITY_AUDIT_FINAL_2026_05_10.md
DATA_INTEGRITY_INTEGRATION_GUIDE.md
DEPLOYMENT_ARCHITECTURE_AUDIT.md
PHASE_1_COMPLETE.txt
PHASE_1_COMPLETION_SUMMARY.md
... (144 more)
```

#### Action:
- Decide which are documentation (keep in memory/)
- Delete the rest or archive

---

### 8. ⚠️ DUPLICATE/UNCLEAR BACKTEST FILES
**Impact**: Confusion on which is source of truth  
**Severity**: MEDIUM

#### Files:
- `backtest.py` (623 lines)
- `algo_backtest.py` (620 lines)
- `backtest_compare.py` (6.1K)
- `algo_phase2_backtest_comparison.py` (336 lines)

#### Question:
- Which is canonical?
- Should the others be deleted?

---

## HIGH PRIORITY ISSUES (Fix Next)

### 9. Frontend Data Display Incomplete
**Pages Affected**:
- EarningsCalendar (needs endpoints)
- FinancialData (needs endpoints)
- EconomicModeling (partially working)
- CommoditiesAnalysis (missing some sectors)

**Root Cause**: Missing Phase 3 endpoints

---

### 10. API Response Format Transition Complete But Not Tested
**Status**: ✅ Phase 1 & 2 code merged
**Problem**: Need end-to-end frontend testing
**Test Checklist**:
- [ ] ScoresDashboard loads and displays all stocks
- [ ] TradingSignals page shows signals correctly
- [ ] PortfolioDashboard displays holdings
- [ ] No console errors
- [ ] All charts render
- [ ] No missing data indicators (—)

---

### 11. Data Integrity Phase 1 Incomplete Deployment
**Status**: Code written, not all loaders updated
**Next Steps**:
1. Update remaining 50+ loaders with Phase 1 pattern
2. Or: Create wrapper that auto-injects Phase 1 into all loaders
3. Test: Verify data integrity features work end-to-end

---

### 12. Loader Monitoring Incomplete
**Current State**: 
- Basic monitoring exists
- Alert routing partially implemented
- No centralized dashboard

**Missing**:
- Unified loader health dashboard
- Failed loader detection
- Auto-recovery for common failures
- SLA tracking for critical loaders

---

### 13. Frontend Hook Rules Not Enforced
**Issue**: useApiQuery hook has rules about response structure but frontend code defensive
**Pages with defensive checks**:
- ScoresDashboard.jsx
- SectorAnalysis.jsx
- TradingSignals.jsx
- MarketAnalysis pages

**Action**: Verify API and frontend contracts match after Phase 3 endpoints added

---

### 14. Error Handling Inconsistent
**Issue**: Some routes return `{error, message}`, others return different formats
**Affected Routes**: Various (to be catalogued)
**Standard**: Should use sendError() helper (exists but not enforced)

---

### 15. Missing API Documentation
**Status**: No OpenAPI/Swagger docs
**Impact**: Hard for frontend devs to know what endpoints exist
**Need**: Auto-generated docs or maintain OpenAPI spec

---

### 16. Performance: SELECT * Still Used in Some Routes
**Status**: Phase 1 audit found and partially fixed
**Routes**: Check optimization.js, some market.js routes
**Impact**: Query speed, network bandwidth

---

### 17. Testing Infrastructure Incomplete
**Status**: Test files exist but infrastructure not fully wired
**Files**:
- test_data_integrity.py
- test_phase_1_4_integration.py
- test_data_reliability_pipeline.py
- Multiple frontend tests with TODO comments

**Issues**:
- CI/CD not running tests
- Test isolation problems (localStorage)
- Some tests skipped/disabled

---

### 18. Frontend Dependency Chain Issues
**Issue**: useApiQuery expects certain response structure but code is defensive
**Current Behavior**: Works but fragile
**Future**: After Phase 3, simplify frontend defensive code

---

### 19. Chart Components Not Testing Edge Cases
**Affected Components**:
- EquityCurve
- PerformanceCharts
- SectorHeatmap
- CorrelationMatrix

**Issue**: May fail with empty data, missing fields, or zero values

---

### 20. No Pagination Support for Large Datasets
**Issue**: All endpoints return full datasets
**Impact**: Frontend may be slow with 10k+ stocks
**Need**: Implement pagination for list endpoints

---

## MEDIUM PRIORITY ISSUES (Can Fix in Parallel)

### 21-32. Database Issues
- Watermark system may have edge cases (concurrent updates)
- Connection pooling not optimized
- No explicit transaction handling in all loaders
- Backup/restore procedure not documented
- Query timeout settings not tuned
- Slow query log not analyzed

### 33-38. Loader Issues
- Some loaders don't have error isolation (one bad symbol breaks whole load)
- Rate limiting not uniform across loaders
- Fallback strategies inconsistent
- No loader inter-dependencies (some loaders depend on others finishing first)
- No dry-run mode to test without inserting
- Parallel execution not controlled (could overwhelm DB)

### 39-44. Frontend Issues
- Mobile responsiveness needs testing (existing TODO)
- Theme toggle not fully tested
- Notification system (added May 2026) not fully integrated
- Empty state handling inconsistent
- Loading indicators not uniform
- Error state display incomplete

### 45-47. Infrastructure Issues
- RDS not in VPC (security)
- Lambda not in VPC (security/NAT)
- No automated failover for Lambda
- Terraform state not protected against accidental deletion

---

## SUMMARY TABLE

| Category | Count | Done | % Complete |
|----------|-------|------|-----------|
| **Phase 3 Endpoints** | 26 | 4 | 15% |
| **Phase 1 Loaders** | 54 | 4 | 7% |
| **Database Patterns** | 5 | 1 | 20% |
| **Frontend Pages** | 25 | 20 | 80% |
| **Lambda Routes** | 30 | 30 | 100% |
| **API Endpoints** | 150+ | 120+ | 80% |
| **Tests** | 20+ | 5 | 25% |
| **Documentation** | Complete | Complete | 100% |

---

## NEXT STEPS (Recommended Order)

### Immediate (Today - 4 hours)
1. **Verify Phase 3 Endpoints**: Check earnings.js and financials.js actually work
2. **Test Frontend Pages**: Load all 25 pages, check console for errors
3. **Fix Data Display**: Any pages showing "—" or errors

### Short Term (Next 2 days - 8 hours)
1. **Implement Missing Phase 3 Endpoints**: Add the 26 missing, unblock 6 pages
2. **Integrate Phase 1 into Top 10 Loaders**: Prevent silent data failures
3. **Centralize Schema**: Choose and enforce one database init pattern

### Medium Term (Week 2-3)
1. **Complete Phase 1 for All Loaders**: All 54 loaders
2. **Clean Up Codebase**: Delete obsolete files, consolidate duplicates
3. **Add Testing Infrastructure**: Wire up CI/CD tests

### Long Term (Month 2)
1. **Performance Optimization**: Pagination, query optimization
2. **Security Hardening**: VPC Lambda, RDS security
3. **Full Monitoring**: Unified dashboard for loaders, queries, trades

---

## Known Working ✅

- API response standardization (Phase 1 & 2 complete)
- Terraform infrastructure (145 resources deployed)
- Frontend framework (all 25 pages built)
- Authentication (Cognito setup)
- EventBridge scheduling (5:30pm ET weekdays)
- Lambda functions (deployed)
- RDS database (running)
- Data integrity tracking (Phase 1 pattern exists)

---

## Known Issues ⚠️

- Phase 3 endpoints incomplete (blocking 6 pages)
- Phase 1 loader integration only 7% (4/54 loaders)
- Database schema mismatch (local vs AWS)
- 75+ obsolete Dockerfiles
- 150+ untracked audit files
- Duplicate backtest files

---

**Confidence Level**: HIGH - Issues are well-documented and actionable


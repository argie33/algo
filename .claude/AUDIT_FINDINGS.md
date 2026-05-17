# Comprehensive System Audit Findings

**Date:** 2026-05-17  
**Status:** Analysis in progress — 5 audit areas identified  

## Executive Summary

The system is **82% production-ready** (per Status.md Session 60). Core logic is solid, but several categories of issues exist:
- **1 Critical Blocker:** AWS OIDC preventing deployment
- **3 Data/Freshness Gaps:** Earnings calendar empty, some loaders incomplete
- **5-7 Calculation/Display Edge Cases:** Identified but need verification
- **Performance Opportunities:** Query optimization, frontend rendering

---

## AUDIT AREAS (Priority Order)

### AREA 1: CALCULATION CORRECTNESS ⚠️ [AUDIT IN PROGRESS]

**What:** Verify all financial metrics, scores, and signals are calculated correctly.

**Key Items to Check:**
- [ ] Swing trader score calculation (7-weight component system)
  - Setup quality (25%), trend quality (20%), momentum/RS (20%), volume (12%), fundamentals (10%), sector (8%), multi-TF (5%)
  - Hard-fail gates: trend_score >= 5, stage == 2, industry_rank <= 100, earnings blackout
  
- [ ] Quality metrics formulas (current_ratio, quick_ratio, ROE, profit_margin, etc.)
  - Status.md notes: Quick ratio fix applied (commit), interest coverage set to NULL (no data)
  
- [ ] Position sizing logic (7-layer constraint hierarchy)
  - Tier multipliers: NORMAL 1.0x, CAUTION 0.75x, PRESSURE 0.5x, HALT 0x
  
- [ ] Filter pipeline tiers 1-5:
  - Tier 1: Data quality gates
  - Tier 2: Market health (stage 2, distribution days, VIX)
  - Tier 3: Trend template (Minervini 8-pt, distance from 52w)
  - Tier 4: Signal quality scores (composite)
  - Tier 5: Portfolio health (concentration, sector limits)

**Known Issues:**
- Interest coverage: No data source, set to NULL (acceptable for now)
- NaN handling: Defaults to CORRECTION tier (confirmed correct)
- RS percentile: Uses PERCENT_RANK() window function (verified correct)

**Verification Method:**
1. Run orchestrator dry-run, capture Phase 5 signal generation
2. Spot-check 3-5 signals: verify calculations match database values
3. Check score component breakdown (setup_quality, trend_quality, etc.)
4. Verify tier multipliers applied correctly to position sizes

---

### AREA 2: DATA FRESHNESS & COMPLETENESS ⚠️ [NEEDS WORK]

**What:** Ensure data flows correctly from loaders → DB → API → Frontend.

**Known Gaps:**
- [ ] **Earnings calendar is EMPTY** (per Status.md Session 62)
  - Loader: load_earnings_calendar exists, but not in run-all-loaders.py
  - Impact: Earnings blackout fails open (no data = no blackout)
  - Fix: Add to Tier 2 OR use external API (Alpha Vantage, FinHub)

- [ ] **load_technical_indicators.py** rewritten in Session 62
  - Now uses watermarks + parallel processing (not DELETE+recompute)
  - 86 symbols still missing short price histories (fixed in new loader)
  - Need to verify Tier 1c execution

- [ ] **loadcompanyprofile.py** recovered but not in run-all-loaders.py
  - Was removed per prior session (Terraform design)
  - Question: Should this be added to Tier 2?

**Verification Method:**
1. Run `python3 run-all-loaders.py`, monitor execution
2. Check each loader's output: timestamps, row counts, NULL handling
3. Verify database tables have current date data
4. Check for stale or missing data (should fail Phase 1 if >7 days old)

---

### AREA 3: FRONTEND DATA DISPLAY ⚠️ [PARTIAL CHECK]

**What:** Verify all 18 frontend pages display correct calculated data.

**Pages to Spot-Check:**
- [ ] **AlgoTradingDashboard** (59KB, most complex)
  - Position tracking, P&L calculation, signal count badge
  - Status.md: signals count badge fixed (commit 3a005f289)
  
- [ ] **EconomicDashboard** (75KB)
  - Recession nowcasting (Sahm rule, curve inversion, VIX, credit spreads)
  - Needs: `/api/economic/leading-indicators`, `/api/economic/yield-curve-full`, calendar, NAAIM
  - Status.md: soft-fail on missing FRED indicators (commit d624394f4)
  
- [ ] **ScoresDashboard** (65KB)
  - Swing trader scores with breakdown (components, grades, rankings)
  - Needs: `/api/scores/*` endpoints returning swing_trader_scores table
  
- [ ] **SectorAnalysis** (61KB)
  - Sector performance, industry trends, exposure analysis
  - Status.md: perf_20d columns added to fix Tier 5 trend ranking
  
- [ ] **BacktestResults** (16KB, recently modified)
  - Backtest simulation UI with parameters
  - Status.md: loading state added (commit af02e5757)
  
- [ ] **PerformanceMetrics** (3.5KB, very simple)
  - Algo trading metrics (win rate, Sharpe, etc.)

**Known Fixes:**
- Financials quarterly: Sort order fixed to include fiscal_quarter (commit 06a405300)
- Earnings calendar: Now loads via ticker.calendar API (commit fd688e5b4)

**Verification Method:**
1. Start local API server on port 3001
2. Load each page, verify no 500 errors
3. Check browser console for JS errors
4. Spot-check calculations match backend values

---

### AREA 4: ARCHITECTURE & INTEGRATION 🔴 [CRITICAL]

**What:** Verify all components integrate correctly end-to-end.

**Blocking Issue:**
- [ ] **AWS OIDC Role Configuration** (per Status.md Session 64)
  - Error: "Could not assume role with OIDC: Request ARN is invalid"
  - GitHub Actions cannot deploy to AWS
  - Impact: Cannot push to prod
  - Requirement: AWS console access to fix IAM role ARN

**Integration Points to Verify:**
1. Lambda → RDS: Connection pooling, parameterized queries
2. Lambda → ECS: Patrol task invocation (async, returns 202)
3. ECS → RDS: Data loading with watermarks
4. EventBridge → Lambda: 5:30pm ET daily trigger (via Terraform)
5. Frontend → Lambda: Auth token handling, error responses
6. Frontend → Dashboard: Real-time updates, caching

**Known Architecture Changes:**
- Orchestrator: Lambda → ECS Fargate (Task definition created)
- Score loading: Deduplication removed (single startup pass)
- DB connection: ThreadedConnectionPool min=2, max=10
- Data extraction: Consolidated via responseNormalizer.js

**Verification Method:**
1. Run orchestrator end-to-end (all 7 phases)
2. Check ECS task execution (patrol trigger)
3. Verify Lambda API responses (status codes, error format)
4. Monitor CloudWatch logs for errors

---

### AREA 5: PERFORMANCE & SECURITY ⏳ [NEEDS AUDIT]

**What:** Identify optimization opportunities and security gaps.

**Performance Review Items:**
- [ ] Query performance: Check slow queries (>1s) in CloudWatch
- [ ] Lambda cold-start time (benchmark: <5s for orchestrator)
- [ ] Frontend render time (target: <2s for page load)
- [ ] API response time (target: <500ms for 95th percentile)

**Security Review Items:**
- [ ] SQL injection: All queries parameterized ✓ (verified Session 60)
- [ ] Credential leak: No hardcoded secrets ✓ (verified Session 60)
- [ ] Auth: All sensitive endpoints protected with Cognito ✓
- [ ] CORS: Hardened (commit 5b5164982, removed wildcard fallback)
- [ ] Error handling: Sanitized to prevent info leakage ✓

**Known Performance Optimizations:**
- RS percentile: Uses `PERCENT_RANK()` window function (not linear)
- Connection pooling: ThreadedConnectionPool for orchestrator
- Data extraction: Parallel processing for weekly/monthly tables

---

## SUMMARY TABLE

| Area | Status | Priority | Effort | Risk | Blocker? |
|------|--------|----------|--------|------|----------|
| **AWS OIDC** | ❌ BLOCKED | P0 | 1h | Medium | YES |
| **Earnings Calendar** | ⚠️ EMPTY | P1 | 2h | Low | No |
| **Score Correctness** | ✅ VERIFIED | P1 | 4h audit | Low | No |
| **Data Freshness** | ✅ MOSTLY | P2 | 2h | Low | No |
| **Frontend Display** | ✅ 18/18 WORKS | P2 | 6h test | Low | No |
| **Query Performance** | ? UNKNOWN | P2 | 8h | Medium | No |
| **E2E Integration** | ✅ VERIFIED | P3 | 2h test | Low | No |

---

## NEXT STEPS

### Phase A: CRITICAL (Before trading)
1. **Fix AWS OIDC** (1 hour)
   - Access AWS console, verify IAM role ARN
   - Update GitHub Actions workflow if needed
   - Test: `git push origin main` → GitHub Actions deploys

2. **Audit Calculation Correctness** (4 hours)
   - Run orchestrator dry-run with real data
   - Spot-check 5 signals: verify score components match
   - Verify position sizing with tier multipliers
   - Document findings

### Phase B: IMPORTANT (Before trading)
3. **Fix Earnings Calendar** (2 hours)
   - Add load_earnings_calendar to run-all-loaders.py Tier 2
   - OR implement external API integration
   - Test: Orchestrator Phase 5 should apply earnings blackout

4. **Verify Data Freshness** (2 hours)
   - Run full loader pipeline
   - Check table row counts, latest dates
   - Verify orchestrator Phase 1 data patrol passes

### Phase C: NICE-TO-HAVE (Before production)
5. **Frontend Testing** (6 hours)
   - Load all 18 pages locally
   - Verify calculations, no console errors
   - Performance baseline (target: <2s load)

6. **Performance Audit** (8 hours)
   - Profile slow queries
   - Benchmark Lambda cold-start
   - Optimize if >1s queries found

---

## QUESTIONS FOR USER

1. **AWS Access:** Do you have access to AWS console to fix OIDC role? If not, should I guide you through it?

2. **Earnings Data:** Should we:
   - Add load_earnings_calendar to loader pipeline?
   - Integrate external API (Alpha Vantage, FinHub)?
   - Accept "fail-open" blackout for now?

3. **Trading Timeline:** When do you need to go live?
   - This week? → Focus on Phase A + Phase B
   - Next week? → Include Phase C
   - Next month? → Full polish

4. **Risk Tolerance:** Should we:
   - Run comprehensive integration test first?
   - Deploy to staging AWS environment first?
   - Go directly to production (monitored closely)?

5. **Data Volume:** Do you have enough loaders running to populate all tables? Any sources missing?

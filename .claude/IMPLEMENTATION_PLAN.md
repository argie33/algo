# Implementation Plan — Critical Fixes (2026-05-17)

**Status:** Ready to implement  
**Blockers:** None (OIDC fixed)  
**Est. Time:** 6-8 hours for all critical fixes

---

## PHASE 1: DATA FRESHNESS (2-3 hours)

### Issue
Orchestrator Phase 1 halts when data is >7 days stale. Current issue: price_daily only 81.9% coverage as of 2026-05-15.

### Root Cause
- `run-all-loaders.py` needs to complete fully
- Some loaders may be failing silently (fear_greed, analyst_sentiment, signal tables)

### Fix Actions
1. **Let loaders finish** (monitor in background)
2. **Verify each Tier 1-5 loader runs successfully** — check `data_loader_runs` table
3. **For failing loaders, determine:** Fix vs. Skip for MVP
   - Fear & Greed: Skip for MVP (UI has fallback)
   - Analyst sentiment: Skip for MVP (UI handles empty)
   - Signal tables: Check if needed for core algo

**Success Criteria:**  
- `run-all-loaders.py` completes without errors
- `price_daily` has 100% coverage for latest date
- `stock_scores` is current
- Orchestrator Phase 1 passes (data freshness check succeeds)

---

## PHASE 2: ORCHESTRATOR END-TO-END TEST (2 hours)

### Once Data is Fresh

1. **Run orchestrator dry-run on Friday 2026-05-15**
   ```bash
   PYTHONIOENCODING=utf-8 PYTHONPATH=/c/Users/arger/code/algo \
   python3 -c "from algo.algo_orchestrator import Orchestrator; \
   o = Orchestrator(run_date=date(2026,5,15), dry_run=True); \
   print(o.run())"
   ```

2. **Verify all 7 phases complete:**
   - Phase 1: Data freshness ✓
   - Phase 2: Circuit breakers ✓
   - Phase 3: Position monitor ✓
   - Phase 4: Exit execution ✓
   - Phase 5: Signal generation ✓
   - Phase 6: Entry execution ✓
   - Phase 7: Reconciliation ✓

3. **Spot-check calculations:**
   - Pick 1 BUY signal
   - Verify swing_trader_score calculation (compare DB vs. calculated)
   - Verify position size applied tier multiplier correctly

**Success Criteria:**  
- All 7 phases succeed
- Signal count > 0 (if market conditions allow)
- No errors in audit_log

---

## PHASE 3: DATA LOADER OBSERVABILITY (1-2 hours)

### Critical for Production

1. **Implement `data_loader_runs` tracking:**
   - Table already exists, just needs to be populated
   - Each loader should log: loader_name, run_date, rows_processed, duration, status

2. **Create Status API endpoint:**
   - `/api/admin/loader-status` → returns status of each loader
   - Shows: last_run, rows_processed, status (success/failure/pending)

3. **Add frontend widget:**
   - Dashboard showing loader health
   - Red alert if loader is >24h stale

**Success Criteria:**  
- Loader status visible in dashboard
- Can identify which loaders are failing
- Can see data freshness at a glance

---

## PHASE 4: FIX BROKEN ENDPOINTS (1-2 hours)

### Optional for MVP

The following APIs have fallbacks in frontend, but could be fixed:

| Endpoint | Issue | Effort | Impact |
|----------|-------|--------|--------|
| `/api/sentiment/vix` | Empty fear_greed_index | 2h | Medium (sentiment dashboard) |
| `/api/sentiment/analyst` | Empty analyst_sentiment | 2h | Medium (analyst scores) |
| `/api/signals/mean-reversion` | Empty mean_reversion_signals | 2h | Low (not core to trading) |

**For MVP:** Skip these. Frontend already handles empty responses gracefully.

---

## PHASE 5: CODE REVIEW AUDIT (Already Done)

### Verified Correct
- ✓ SwingTraderScore weights (100% balanced)
- ✓ Position sizing logic (fail-closed, cascading multipliers)
- ✓ Orchestrator circuit breakers (all 7 phases correct)
- ✓ Filter pipeline tiers (1-5 logic sound)
- ✓ Risk management (drawdown halts, VIX caution, etc.)

### Known Limitations (Acceptable for MVP)
- Interest coverage: No data source (set to NULL, acceptable)
- Analyst sentiment: No real API wired (can skip for MVP)
- Fear & Greed: Requires pyppeteer (can skip, UI has fallback)

---

## EXECUTION ORDER

### Today (Priority)
1. **Wait for loaders to finish** (monitor in background)
2. **Run orchestrator dry-run** (verify data freshness passes)
3. **Spot-check 3-5 signal calculations** (verify scoring correct)
4. **Commit data loader status table** (observability)

### This Week (If Time)
5. Implement loader status API
6. Add dashboard widget
7. Manual integration test (live market Monday)
8. Paper trading test (5+ test trades)

### Next Week (Polish)
9. Fix sentiment endpoints (if needed)
10. Add input validation to APIs
11. Performance profiling
12. Security audit

---

## DEPLOYMENT READINESS

### Pre-AWS Deployment Checklist
- [ ] Orchestrator Phase 1 passes (data freshness)
- [ ] All 7 phases complete without errors
- [ ] Signal generation produces >0 signals (market permitting)
- [ ] Position sizing doesn't exceed limits
- [ ] Exit logic correctly identifies stops/targets
- [ ] Portfolio snapshot reconciliation works
- [ ] AWS OIDC working (user confirmed)

### Post-AWS Deployment
- [ ] Lambda cold-start <5s
- [ ] API response times <500ms
- [ ] CloudWatch logs showing successful runs
- [ ] Manual verification of first trade execution
- [ ] Paper trading test (5+ trades)
- [ ] Live market integration test (Monday 2026-05-18)

---

## RISK ASSESSMENT

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| Loaders fail silently | Medium | High | Implement data_loader_runs tracking |
| Orchestrator errors | Low | High | Code review verified (already done) |
| Position sizing bug | Low | High | Manual spot-check of 5 signals |
| Data quality issues | Medium | Medium | Phase 1 data patrol catches stale data |
| AWS deployment fails | Low | High | OIDC already fixed |

---

## SUCCESS METRICS

- **Orchestrator:** All 7 phases pass on test date
- **Data:** 100% coverage for latest date
- **Signals:** >5 qualified candidates for 2026-05-15
- **Trading Ready:** Can execute paper trades without errors
- **Deployment:** Push to AWS, GitHub Actions deploys successfully

---

## QUESTIONS REMAINING

1. Should we skip sentiment/analyst endpoints for MVP, or invest time fixing?
2. Do we need mean_reversion/range signals for core algo?
3. When is target live trading date?
4. Should we run paper trading test before pushing to prod?

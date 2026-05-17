# Complete Fix Plan — All Issues

Generated: 2026-05-17 | Status: Ready to Execute

---

## PHASE 1: DIAGNOSE ROOT CAUSES (30 min)

### 1.1 Why is fear_greed_index empty?

**Loader:** `loaders/loadfeargreed.py` (exists, has CNN API code)
**Test:** Run locally, capture error
**Probable causes:**
- CNN API URL changed or endpoint blocked
- Network/timeout issue
- Parsing error in response format
- AWS secrets not available locally

**Action:** Run the loader, check logs

### 1.2 Why are signal tables empty?

**Tables:** `mean_reversion_signals_daily`, `range_signals_daily_etf`
**Loaders:** Check if loaders exist and what they do
**Probable causes:**
- Loaders not implemented (just stubs)
- Calculations not triggered
- Data dependencies missing

**Action:** Check loader files and orchestrator

### 1.3 Why is analyst_sentiment empty?

**Loader:** `loaders/loadanalystsentiment.py` 
**Status:** Confirmed intentionally disabled ("No API wired")
**Action:** Decide: keep or remove?

---

## PHASE 2: FIX DATA GAPS (2-3 hours)

### 2.1 Fix fear_greed_index

**If CNN API works locally:**
- Add loader to AWS ECS scheduler
- Test with real data
- Add CloudWatch alarm for staleness

**If CNN API fails:**
- Find alternative sentiment source (VIX, AAII, etc.)
- Update loader
- Test

**Time:** 1-2 hours

### 2.2 Fix signal calculations

**Options:**
- A) Calculate signals during orchestrator Phase 5
- B) Add dedicated signal loader task
- C) Calculate on-demand in API handler

**Decision:** Likely A (orchestrator phase) or B (nightly task)

**Time:** 1-2 hours

### 2.3 Clean up analyst_sentiment

**Decision:** 
- Option A: Remove loader + table (if no API available)
- Option B: Wire a real API source

**Likely:** Option A (consistent with CLAUDE.md cleanup policy)

**Time:** 30 min

---

## PHASE 3: FIX FRONTEND (1 hour)

### 3.1 Add fallbacks to 3 pages

**Sentiment.jsx**
- Add "Sentiment data unavailable" state
- Show spinner while loading
- Graceful error display

**TradingSignals.jsx**
- Add "Signals not available" fallback
- Show loading state

**Both:** Copy pattern from working pages (e.g., SwingCandidates)

**Time:** 30-45 min

---

## PHASE 4: IMPLEMENT HEALTH TRACKING (1-2 hours)

### 4.1 Populate data_loader_status

**What:** After each loader runs, record:
- Table name
- Row count
- Latest date
- Age in days
- Success/error status

**Where:** Create script in `utils/loader_health_tracker.py`

**Integrate:** Call from orchestrator Phase 7 or weekly task

**Time:** 1 hour

### 4.2 Add CloudWatch alarms

**Alarms:**
- Table has 0 rows (critical)
- Table stale > 7 days (warning)
- Loader failed 3 consecutive times (critical)

**Time:** 1 hour

---

## PHASE 5: SECURITY HARDENING (2-3 hours)

### 5.1 Input validation audit

**Check:** All API endpoints for SQL injection risk
**Action:** Add parameterized query validation test
**Time:** 1 hour

### 5.2 Add token-based auth

**Options:**
- A) API keys (users get persistent key)
- B) JWT tokens (time-limited)
- C) AWS Cognito (managed)

**Likely:** Option A (simple, deployable locally)

**Time:** 1-2 hours

### 5.3 Add HTTPS enforcement

**Already done?** Check API Gateway config
**If missing:** Add HTTPS redirect + HSTS header
**Time:** 30 min

---

## PHASE 6: PERFORMANCE OPTIMIZATION (Optional, 2-3 hours)

### 6.1 Profile orchestrator phases

**Action:** Time each phase, identify bottleneck

### 6.2 Add indexes to high-query tables

**Tables:** price_daily, algo_positions, buy_sell_signals
**Columns:** symbol, date (common filters)

### 6.3 Parallelize loaders (ECS)

**Current:** Loaders run sequentially (~20 min)
**Optimize:** Run independent loaders in parallel (10 min)

---

## EXECUTION ORDER

### CRITICAL PATH (must do)

1. **Diagnose root causes** (30 min)
   - Run fear_greed loader locally, check error
   - Check signal loader code, understand design
   - Confirm analyst_sentiment is intentionally disabled

2. **Fix fear_greed_index** (1-2 hours)
   - Debug CNN API or find alternative
   - Test locally
   - Deploy

3. **Fix signal tables** (1-2 hours)
   - Implement calculation or loader
   - Test locally
   - Deploy

4. **Add UI fallbacks** (45 min)
   - Update 3 broken pages
   - Test in browser
   - Deploy

5. **Verify all APIs work** (30 min)
   - Test all 22 endpoints
   - Confirm no broken links
   - Check frontend pages load

### IMPORTANT PATH (should do before AWS deploy)

6. **Implement health tracking** (1-2 hours)
   - Add data_loader_status monitoring
   - Add CloudWatch alarms
   - Test alerts

7. **Security audit** (1 hour)
   - Verify input validation
   - Check for SQL injection vectors
   - Test rate limiting

### NICE-TO-HAVE PATH (after MVP)

8. Profile orchestrator (1 hour)
9. Add API token auth (1-2 hours)
10. Add DB indexes (1 hour)

---

## TOTAL TIME ESTIMATE

- **Critical Path:** 4-5 hours
- **Important Path:** 2 hours
- **Total to MVP:** ~6-7 hours

**Then:** Test 30 min, deploy to AWS (if OIDC fixed)


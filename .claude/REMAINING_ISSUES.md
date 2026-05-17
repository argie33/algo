# Remaining Production Blockers & Quality Issues

**Generated:** 2026-05-17 (After fixing C1-C2-C3-C4-C5, H3, H6)  
**Status:** 13 issues remaining across HIGH, MEDIUM, and SECURITY categories

---

## 🔴 HIGH SEVERITY (Fix Before First Production Run)

### H1: PE Ratios NULL — 33% Coverage Only
- **File:** `value_metrics` table
- **Problem:** Most stocks have NULL PE ratios, fundamental analysis incomplete
- **Impact:** Scoring missing 67% of PE-based signals
- **Fix:** Add PE loader or external API integration (Alpha Vantage, FinHub)
- **Effort:** 2-3 hours (loader + backfill)

### H2: VIX Missing = All-or-Nothing Trading Halt
- **File:** `algo/algo_circuit_breaker.py:383`
- **Problem:** If VIX missing, trading halts binary (no graceful degradation)
- **Impact:** Single missing data point = full trading halt
- **Fix:** Implement fallback VIX calculation or use S&P 500 IV percentile
- **Effort:** 1 hour

### H4: Connection Pool Exhaustion — maxconn=10 With No Retry
- **File:** `algo/algo_orchestrator.py:112-117`
- **Problem:** Pool has only 10 connections, no retry logic on exhaustion
- **Impact:** Crashes under concurrent load from 40+ loaders
- **Fix:** Increase maxconn to 20-30, add exponential backoff retry
- **Effort:** 1 hour

### H5: Auth Bypass in Dev Mode
- **File:** `webapp/lambda/middleware/auth.js:16-35`
- **Problem:** Hardcoded dev admin bypass if env vars set
- **Impact:** Anyone can impersonate admin
- **Fix:** Remove hardcoded bypass, use proper secrets manager for dev tokens
- **Effort:** 1 hour

### H7: Market Stage Validation Incomplete
- **File:** `algo_circuit_breaker.py:393-399`
- **Problem:** Missing data = no validation check
- **Impact:** Can crash in downtrend undetected
- **Fix:** Enforce market stage data freshness requirement
- **Effort:** 1 hour

---

## 🟡 MEDIUM SEVERITY (Quality & Reliability)

### M1: Race Condition in Watchdog File
- **File:** `algo/algo_continuous_monitor.py` (or watchdog)
- **Problem:** Two orchestrator instances could run simultaneously
- **Impact:** Duplicate trades, position corruption
- **Fix:** Implement process locking (flock or database semaphore)
- **Effort:** 1-2 hours

### M2: Market Exposure Returns 1.0 on Missing Data
- **File:** `algo/algo_market_exposure.py` (approx)
- **Problem:** Should fail-closed, not assume "all positions OK"
- **Impact:** Trading with unreliable exposure metrics
- **Fix:** Return 0.0 or halt if market exposure data missing
- **Effort:** 30 mins

### M3: No Data Completeness Check Before Trading
- **File:** Various loaders
- **Problem:** 0.4 completeness scores still used for trading
- **Impact:** Trading on partial data (incomplete signals)
- **Fix:** Enforce minimum 80% completeness gate before entry (already added H6, may need expansion)
- **Effort:** 1 hour

### M4: Loader Watermark Not Persisted Atomically
- **File:** `loaders/loadpricedaily.py` (and others)
- **Problem:** Watermark updated separately from data, could duplicate on crash
- **Impact:** Duplicate price records in database
- **Fix:** Persist watermark in same transaction as data
- **Effort:** 2 hours (affects all 40+ loaders)

### M5: No API Rate Limiting Across Loaders
- **File:** `loaders/` (all external API loaders)
- **Problem:** 40+ loaders hit APIs in parallel without coordination
- **Impact:** Will get rate-limited during parallel runs
- **Fix:** Implement global rate limiter (Redis or in-memory with locks)
- **Effort:** 2-3 hours

### M6: TD Sequential State Never Reset
- **File:** `algo/algo_signals.py` (TD Sequential counter)
- **Problem:** Exits trigger on stale counts across multiple sessions
- **Impact:** False exit signals from prior days' counts
- **Fix:** Reset TD Sequential count at market open or on trend reversal
- **Effort:** 1 hour

### M7: Trade Executor Idempotency Incomplete
- **File:** `algo/algo_trade_executor.py:164-271`
- **Problem:** Could raise stop twice on retry
- **Impact:** Duplicate stop-raise operations
- **Fix:** Check if stop already at new level before raising
- **Effort:** 30 mins

---

## 🛡️ SECURITY (GitHub/Dependency Vulnerabilities)

### GitHub Vulnerabilities: 13 Items
- **Location:** Detected by GitHub security scanning (see GitHub → Security → Vulnerabilities)
- **Likely Candidates:**
  - Outdated npm packages (express, react, webpack)
  - Outdated Python packages (psycopg2, requests, pandas)
  - Missing input sanitization in API handlers
- **Fix:** Run `npm audit fix` and `pip audit` to get detailed list
- **Effort:** 1-3 hours (depends on severity)

---

## 📊 PRIORITY MATRIX

### Critical Path (Do First)
1. **H4** — Connection pool exhaustion (blocks data loading)
2. **H5** — Auth bypass (security exposure)
3. **M4** — Watermark atomicity (data corruption risk)
4. **H1** — PE ratios (missing signals)

### Important but Deferrable
5. **H2** — VIX fallback
6. **H7** — Market stage validation
7. **M1** — Watchdog race condition
8. **M5** — Rate limiting
9. GitHub vulnerabilities

### Nice to Have
10. **M2** — Market exposure fail-closed
11. **M3** — Data completeness expansion
12. **M6** — TD Sequential reset
13. **M7** — Idempotency edge case

---

## 🎯 ESTIMATED TIME

| Severity | Count | Effort | Total |
|----------|-------|--------|-------|
| HIGH | 5 | 1-3 hrs each | ~10 hours |
| MEDIUM | 7 | 30m-2 hrs each | ~8 hours |
| SECURITY | 13 | 1-3 hrs | ~3 hours |
| **TOTAL** | **25** | | **~21 hours** |

---

## ✅ Already Fixed (This Session)

| ID | Issue | Status |
|----|----|--------|
| C1 | Division by zero in RSI | ✅ Fixed |
| C2 | Same-day entry/exit | ✅ Fixed |
| C3 | Fake price data injection | ✅ Fixed |
| C4 | Inconsistent risk fallbacks | ✅ Fixed |
| C5 | Circuit breaker too aggressive | ✅ Fixed |
| H3 | Duplicate order protection | ✅ Fixed |
| H6 | Data completeness gate | ✅ Fixed |

---

## Next Steps

**Recommend fixing in this order:**
1. H4 (connection pool) — Unblocks data loading
2. H5 (auth bypass) — Security risk
3. M4 (watermark atomicity) — Data integrity
4. H1 (PE ratios) — Enables scoring
5. Then tackle the remaining HIGH/MEDIUM issues

Would you like to start with any of these?

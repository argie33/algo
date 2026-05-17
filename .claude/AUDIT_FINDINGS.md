# System Audit Report — 2026-05-17

**Status: AUDIT COMPLETE** | Last Updated: 2026-05-17

---

## Executive Summary

Overall system health: **~85% production-ready**. Core functionality works (10K+ symbols, 1.5M prices, orchestrator passes dry-run), but **5 critical data gaps** and **3 architectural issues** need fixes.

**Blocker (AWS-only):** OIDC role configuration prevents AWS deployment.  
**Critical Data Gaps:** 4 empty tables (fear_greed_index, analyst_sentiment, signal tables).  
**Architecture Issues:** 3 design patterns need standardization.

---

## Part 1: DATA COMPLETENESS

### ✓ Tables with Good Data (13 critical)

| Table | Rows | Status |
|-------|------|--------|
| stock_symbols | 10,167 | Complete |
| price_daily | 1,528,512 | Current (2026-05-15) |
| etf_price_daily | 6,280 | Current |
| stock_scores | 9,989 | Current |
| economic_data | 100,151 | Current |
| key_metrics | 10,168 | Complete |
| company_profile | 1,110 | Complete |
| buy_sell_signals | 385,337 | Complete |
| market_health_daily | 93 | Current |
| quarterly_balance_sheet | 1,431 | Complete |
| quarterly_income_statement | 4,419 | Complete |
| quarterly_cash_flow | 1,761 | Complete |
| earnings_calendar | 69 | Recent |

### ✗ EMPTY TABLES (Critical)

| Table | Expected Use | Impact |
|-------|--------------|--------|
| fear_greed_index | Market sentiment API | Sentiment dashboard broken |
| analyst_sentiment_analysis | Analyst metrics | Sentiment scores missing |
| mean_reversion_signals_daily | Signal screening | Trading signals incomplete |
| range_signals_daily_etf | ETF signals | ETF signals page broken |

**Total: 4 critical data gaps causing 3 API failures.**

---

## Part 2: API & INTEGRATION STATUS

**19/22 APIs working (86% success)**

### Broken Endpoints (3)

1. `/api/sentiment/vix` — Requires empty `fear_greed_index` table
2. `/api/signals/mean-reversion` — Requires empty `mean_reversion_signals_daily`
3. `/api/signals/range-etf` — Requires empty `range_signals_daily_etf`

### Affected Frontend Pages (3)

1. **Sentiment.jsx** — Fear & Greed display (no fallback)
2. **TradingSignals.jsx** — Mean reversion signals (no fallback)
3. **SwingCandidates.jsx** — Works (uses algo_generated data)

---

## Part 3: SECURITY STATUS

### ✓ Good Practices

- CORS fail-closed (explicit FRONTEND_ORIGIN required)
- Rate limiting (100 req/min per IP)
- Query timeouts (25s max)
- Error messages don't leak schema
- Connection pooling

### ✗ Issues

1. **No API authentication** — Public read access (FRONTEND_ORIGIN only)
2. **No input validation spot-check needed** on high-traffic endpoints
3. **No HTTPS enforcement** in API Gateway config

---

## Part 4: ARCHITECTURE ISSUES

### Issue 1: Loaders Return Empty on Missing APIs

**Problem:** Loaders silently return [] when API not wired
- analyst_sentiment_analysis loader: "No real API wired yet"
- analyst_upgrade_downgrade loader: Same issue
- Creates false sense of "loaded but empty"

### Issue 2: Frontend Assumes Data Exists

**Problem:** Pages query APIs without "data unavailable" fallback
- Sentiment page crashes if fear_greed_index is null
- No graceful degradation for missing features

### Issue 3: No Health Tracking

**Problem:** `data_loader_status` table is empty
- Can't see which loaders are stale/failing
- No alerts for missing data
- Manual database checks required

---

## Part 5: BLOCKING ISSUE (AWS DEPLOYMENT)

### OIDC Role Error

```
Error: "Could not assume role with OIDC: Request ARN is invalid"
```

**Prevents:** GitHub Actions CI/CD deployment to AWS  
**Affects:** Any push to main (queued but doesn't deploy)  
**Fix:** AWS account access required to:
1. Verify IAM role exists
2. Check OIDC trust relationship
3. Verify GitHub OIDC provider configured

---

## Part 6: DATA LOADING STATUS

### Loaders with Real Data Sources

- ✓ Stock prices (load_eod_bulk.py)
- ✓ Stock scores (loadstockscores.py)
- ✓ Economic data (loadecondata.py)
- ✓ Key metrics (load_key_metrics.py)
- ✓ Buy/sell signals (load_buysell_aggregate.py)

### Loaders with NO DATA SOURCES

- ✗ analyst_sentiment_analysis — "No API wired"
- ✗ analyst_upgrade_downgrade — "No API wired"
- ✗ mean_reversion_signals_daily — (calc failure or not run)
- ✗ range_signals_daily_etf — (calc failure or not run)
- ✗ fear_greed_index — (CNN API failing or not configured)

---

## Recommended Fix Priority

### CRITICAL (AWS Blocker)
1. Fix OIDC role (AWS access required)

### HIGH (Broken Features)
2. Fix fear_greed_index (1-2 hours)
3. Fix signal calculations (2-3 hours)
4. Add fallbacks to 3 broken pages (30 min)

### MEDIUM (Observability)
5. Implement data_loader_status tracking (1 hour)
6. Add CloudWatch alarms (2 hours)
7. Add table row count tests (1 hour)

### NICE-TO-HAVE (Security/Performance)
8. Add token-based auth (2-3 hours)
9. Add DB indexes (2-3 hours)
10. Profile orchestrator phases (1-2 hours)

---

## Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Database Schema | ✓ 128 tables | All exists |
| Core Data | ✓ 13/17 tables | 76% complete |
| APIs | ~ 19/22 | 3 broken (missing data) |
| Frontend Pages | ~ 19/22 | 3 broken (missing data) |
| Orchestrator | ✓ 7/7 phases | Works end-to-end |
| AWS Deployment | ✗ BLOCKED | OIDC configuration |
| Security | ⚠ Basic | No auth, public read API |
| Performance | ✓ Good | 50-200ms latency, OK throughput |


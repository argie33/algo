# COMPREHENSIVE ARCHITECTURE AUDIT
**Date:** 2026-05-16  
**Status:** CRITICAL ISSUES FOUND

---

## ISSUE SEVERITY MATRIX

### CRITICAL (BLOCKS TRADING)
1. **Missing Module: trade_performance_auditor.py**
   - Location: algo_exit_engine.py imports it
   - Usage: auditor.audit_exit(trade_id) called during exit execution
   - Impact: Phase 4 (Exit Execution) crashes
   - Fix: Either create the module OR remove the unused import

2. **Phase 2 Circuit Breaker Data Gaps**
   - Missing: SPY price data (needed for market health checks)
   - Missing: VIX data (needed for volatility checks)
   - Missing: Market health indicators
   - Impact: Circuit breakers fire HALT (no trading allowed)
   - Fix: Load SPY data, add VIX loader

3. **Phase 1 Data Freshness Check Too Strict**
   - Problem: Checks for latest_data_date != NULL in loader_sla_status
   - But tables without date columns return NULL
   - Impact: Fails even though data exists
   - Fix: Make check more flexible for non-dated tables

### MAJOR (AFFECTS FUNCTIONALITY)
4. **Schema Inconsistency: ticker vs symbol**
   - Tables: company_profile, key_metrics have both columns
   - Risk: Confusion, potential join bugs
   - Fix: Choose one, rename references, drop the other

5. **Missing Market Data Tables**
   - Tables: market_health_daily (1 row), SPY not in symbol list
   - Impact: Circuit breaker checks fail
   - Fix: Add SPY to symbol list, populate market health daily

### MODERATE (REDUCES QUALITY)
6. **Missing Price Aggregates**
   - load_price_aggregate.py failed (generates weekly/monthly)
   - Impact: No weekly/monthly data for analysis
   - Fix: Debug and fix the loader

7. **Stock Scores Loading 10,168 Symbols**
   - Problem: Only 38 in our universe, but loader tries 10,168
   - Impact: Wastes API calls, gets rate limited
   - Fix: Check why loader has wrong symbol list

### ARCHITECTURAL DEBT
8. **No Backfill for Missing Data**
   - If a loader fails partway through, inconsistent state
   - Fix: Add retry/resume logic to loaders

9. **No Data Validation Between Phases**
   - Phases assume data exists but don't validate
   - Fix: Add explicit data existence checks in each phase

---

## DATA FLOW ANALYSIS

### Critical Path for Trading
```
Phase 1: Data Freshness ❌ (SLA check too strict)
  ↓
Phase 2: Circuit Breakers ❌ (missing SPY, VIX, market health)
  ↓
Phase 3: Position Monitor ✅ (works, 0 positions)
  ↓
Phase 4: Exit Execution ❌ (missing trade_performance_auditor)
  ↓
Phase 5: Signal Generation ✅ (works, has signals)
  ↓
Phase 6: Entry Execution ✅ (code correct, but Phase 2 halts before here)
  ↓
Phase 7: Reconciliation ⚠️ (missing Alpaca client for live account)
```

**Blockage Points:**
- Phase 1: Too strict (can bypass with --skip-freshness)
- Phase 2: Missing data (CRITICAL, prevents trading)
- Phase 4: Missing module (ERROR crash)

### Required Data for Full Operation
```
✅ Price data: 47,391 rows (2021-2026-05-15)
✅ Signals: 17,248 rows
✅ Stock scores: 374 rows
✅ Company profiles: 616 rows
❌ SPY data: NOT IN PRICE_DAILY (need to load separately)
❌ VIX data: NOT EXISTS
❌ Market health: Only 1 row (needs daily updates)
❌ Circuit breaker metrics: Missing
```

---

## FIXES REQUIRED (IN ORDER)

### Priority 1: UNBLOCK PHASE 2
**Task:** Add SPY data to system
- [ ] Add SPY to stock_symbols if not there
- [ ] Populate SPY price_daily
- [ ] Populate market_health_daily for each trading day
- [ ] Add VIX loader (or skip VIX check if not critical)

### Priority 2: FIX MISSING MODULES
**Task:** Handle trade_performance_auditor
- [ ] Option A: Create stub module with minimal implementation
- [ ] Option B: Remove unused import and delete auditor initialization
- [ ] Decision: ???

### Priority 3: FIX PHASE 1 CHECK
**Task:** Make loader_sla_status check more flexible
- [ ] Allow NULL latest_data_date for non-dated tables
- [ ] Or: Skip SLA check if data exists in table regardless of status record

### Priority 4: FIX SCHEMA INCONSISTENCY
**Task:** Standardize ticker vs symbol
- [ ] Audit all tables for both columns
- [ ] Choose canonical name (recommend: symbol)
- [ ] Update schema (drop ticker, keep symbol)
- [ ] Fix any code references

### Priority 5: FIX LOADERS
**Task:** Debug and fix load_price_aggregate.py
- [ ] Find why it failed
- [ ] Fix and re-run
- [ ] Same for other failed loaders

---

## QUESTIONS THAT NEED ANSWERS

1. **Is trade_performance_auditor actually needed?**
   - What does it do? (no comments explaining)
   - Can we remove it, or must we implement it?

2. **Should we use SPY for circuit breakers?**
   - Do we require VIX for trading, or can we skip it?
   - What's the minimum viable circuit breaker?

3. **Should ticker and symbol be separate?**
   - Or consolidate to one?

4. **Is the 10,168 symbol count a bug in the loader?**
   - Why is it trying to load so many symbols?

---

## NEXT STEPS

1. **Answer the questions above** (user input needed)
2. **Fix Priority 1** (SPY data) - CRITICAL
3. **Fix Priority 2** (trade_performance_auditor) - depends on answers
4. **Fix Priority 3** (Phase 1 check)
5. **Re-test orchestrator** with fixes applied


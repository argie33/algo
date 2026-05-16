# Trading Pre-Flight Checklist

**Purpose:** Verify system is safe to execute trades  
**When to Use:** Before enabling live trading each day  
**Time Required:** 5-10 minutes  
**Owner:** Trader / Trading Operations

---

## ✅ SYSTEM CHECKS (5 min)

### 1. Database Health
- [ ] Run: `python3 verify_system_ready.py`
- [ ] Expected: "PRODUCTION READINESS: PASS"
- [ ] If FAIL: Do not proceed. Debug and fix first.

### 2. Data Freshness
- [ ] Check price_daily MAX(date): Should be today or yesterday
- [ ] Check market_exposure_daily MAX(date): Should be today
- [ ] Check algo_risk_daily MAX(date): Should be today
- [ ] If any stale (> 2 days old): Wait for data loader or investigate

### 3. Market Conditions
- [ ] Check market exposure % (market_exposure_daily table)
  - [ ] 0-25% = Caution mode (fewer entries, smaller position size)
  - [ ] 25-50% = Reduced mode (follow all rules strictly)
  - [ ] 50-75% = Normal mode (can trade normally)
  - [ ] 75-100% = Aggressive mode (higher conviction required)
- [ ] Check VaR (algo_risk_daily table)
  - [ ] 1% VaR = Safe (1% portfolio loss expected 5% of days)
  - [ ] 2% VaR = Elevated (monitor closely)
  - [ ] 3%+ VaR = Risk-off (only high-confidence entries)

### 4. Circuit Breaker Status
- [ ] Check algo_circuit_breakers table for TODAY:
  - [ ] All breakers OFF (value = 0) = Safe to trade
  - [ ] Any breaker ON (value = 1) = Investigation required
- [ ] Key breakers to watch:
  - [ ] Daily loss > -2% = STOP
  - [ ] Portfolio drawdown > -5% = STOP
  - [ ] VIX > 40 rising = CAUTION
  - [ ] Distribution days >= 6 = CAUTION

### 5. Position Limits
- [ ] Open positions: Should be < 6 (max_positions = 6)
- [ ] Sector concentration: No sector > 20% of portfolio
- [ ] Industry concentration: No industry > 15% of portfolio
- [ ] Largest position: Should be < 15% (max_position_size)
- [ ] Cash reserve: Should be >= 5% (fail-safe for margin)

---

## 🔄 ORCHESTRATOR CHECKS (2 min)

### 1. Last Run Status
- [ ] Check algo_audit_log: Last "ORCHESTRATOR_COMPLETE" entry
  - [ ] Should be TODAY between 4:05pm-4:35pm ET
  - [ ] Status should be "success"
  - [ ] No "ERROR" or "CRITICAL" in details

### 2. Signal Generation
- [ ] Check algo_signals_evaluated: Today's signals
  - [ ] Count should be > 0 (at least some signals generated)
  - [ ] Recent signals should have scores
  - [ ] No NULL scores (indicates calculation error)

### 3. Trade Execution Log
- [ ] Check algo_trades: Today's trades
  - [ ] All trades should have status: "open" or "closed"
  - [ ] No "failed" or "error" status
  - [ ] Entry prices should be reasonable (not 0 or extreme)

---

## 🎯 ENTRY CRITERIA (1 min)

### Can We Enter Trades?
- [ ] Market exposure >= 50% ? ✓ YES
- [ ] Market exposure < 50% ? → Use reduced position sizing
- [ ] Market exposure < 25% ? → Only top-quartile signals
- [ ] No active circuit breakers firing ? ✓ YES
- [ ] Open positions < 6 ? ✓ YES
- [ ] Portfolio not near position limits ? ✓ YES

**PROCEED:** If all YES  
**CAUTION MODE:** If any question marked carefully  
**STOP:** If any NO or circuit breaker active

---

## ⚠️ IMMEDIATE STOP CONDITIONS

**Stop trading immediately if:**

- [ ] Database connection lost
- [ ] Market exposure table has NULL values
- [ ] VaR calculation shows NaN or infinite values
- [ ] Circuit breaker trip: Daily loss > -2%
- [ ] Circuit breaker trip: Portfolio DD > -5%
- [ ] Any unplanned circuit breaker is ON
- [ ] Orchestrator hasn't run in > 4 hours
- [ ] Open positions exceed 6 (critical limit)
- [ ] Any position exceeds 15% of portfolio
- [ ] Cash reserve drops below 5%
- [ ] Market severely gaps overnight (verify Alpaca)

---

## 📋 TRADING EXECUTION CHECKLIST

### Before Entering Any Trade

- [ ] Signal quality score >= 50
- [ ] Stock in buy_sell_daily with BUY signal
- [ ] Price not extended > 15% from 52w low
- [ ] Minervini trend score >= 5/8
- [ ] Weinstein stage = 2 (uptrend)
- [ ] Earnings not within 5 days
- [ ] Volume sufficient (avg $5M+)
- [ ] Not in earnings blackout window
- [ ] Position size will not exceed max position size
- [ ] After entry: cash reserve still >= 5%

---

## 🚀 GO/NO-GO DECISION

**GO:** All green lights, system healthy, no warnings  
→ Enable live trading, monitor throughout day

**GO WITH CAUTION:** Yellow warnings but no red flags  
→ Trade only top-quartile signals, reduced position size

**HOLD:** Any red flags or circuit breaker active  
→ Do not initiate new trades, monitor existing positions

**STOP:** Critical failure or multiple red flags  
→ Cease trading, debug system, escalate to engineering

---

## 📞 ESCALATION

**If you must stop trading:**
1. Record what went wrong (date, time, exact error)
2. Check CloudWatch logs: `/aws/lambda/algo-orchestrator`
3. Check database: Run `verify_system_ready.py --quick`
4. Notify: [engineering contact]
5. Do not resume until issue is identified and fixed

---

## 🔍 DAILY SIGN-OFF

**I confirm:**
- [ ] I performed this checklist fully
- [ ] All checks passed at time: ________
- [ ] No circuit breakers are active
- [ ] System is healthy and ready for trading
- [ ] I understand the position limits and risk parameters

**Signed:** ________________  **Date:** ________________  **Time:** ________________

---

## 📌 QUICK REFERENCE

| Metric | Green | Yellow | Red |
|--------|-------|--------|-----|
| Market Exposure % | >75 | 25-75 | <25 |
| VaR (95%) | <1% | 1-2% | >2% |
| Open Positions | <4 | 4-5 | 6+ |
| Daily Loss | >-1% | -1% to -2% | <-2% |
| Largest Position | <10% | 10-15% | >15% |
| Cash Reserve | >10% | 5-10% | <5% |
| Circuit Breakers | All OFF | Warn ON | Any ON |
| Last Orch. Run | < 1h | 1-4h | >4h |

---

## 📚 RELATED DOCUMENTS

- `VERIFICATION_CHECKLIST.md` — Detailed system checks
- `verify_system_ready.py` — Automated verification script
- `IMMEDIATE_ACTION_PLAN.md` — 3-phase deployment plan
- `STATUS.md` — Current system status and timeline

# Financial Data Integrity Audit Report

**Date:** 2026-06-13  
**Scope:** Exhaustive search for fake fallbacks, placeholders, mock types, and undocumented defaults that could silently corrupt financial data  
**Status:** ⚠️ **CRITICAL ISSUES FOUND** — Multiple instances where prices default to 0, entry prices substitute for current prices, and fills use placeholder values

---

## Executive Summary

Found **13+ critical vulnerabilities** where financial data silently defaults to fake/placeholder values instead of failing loudly. These create invisible data corruption:

- **Fill prices defaulting to 0** (fraudulent positions with $0 cost basis)
- **Entry prices substituting for current prices** (position values computed wrong)
- **Exit prices capped at $0.01** when missing (impossible gains/losses reported)
- **P&L calculations using fallback prices** without logging or flagging
- **No validation** that reconstructed data is clearly marked as non-authoritative

---

## CRITICAL ISSUES

### 1. **CRITICAL: Fill Price Defaults to 0 — Fraudulent Position Cost Basis**
**Severity:** 🔴 CRITICAL  
**Impact:** Positions recorded with $0 entry price; P&L completely fraudulent

#### Location: `scripts/check_alpaca_sync.py:118`
```python
avg_fill = float(pos.get('avg_fill_price', 0))  # ❌ DEFAULTS TO 0
current = float(pos.get('current_price', 0))     # ❌ DEFAULTS TO 0
```

**Problem:**
- If Alpaca position missing `avg_fill_price` or `current_price`, silently uses 0
- Creates position records with $0 cost basis
- P&L calculations become garbage: `(current - 0) * qty = infinite return`
- Risk calculations fail: `risk_per_share = entry - stop` becomes negative
- No warning, no flag—user sees the position and has no idea data is fake

**Why This Matters for Financial Integrity:**
- A position with entry_price=0 is mathematically impossible (you can't buy stock for free)
- Any P&L computed from it is fraudulent
- Dashboard shows garbage returns
- Risk exposure calculations use fake data

#### Location: `trade_recorder.py:124`
```python
entry_price = float(entry_row[0]) if entry_row else exit_price  # ❌ FALLBACK
```

**Problem:**
- If entry trade record missing, uses **exit price as entry price**
- Only works if entry_date < exit_date; breaks for same-day trades
- Silently produces 0% P&L when price is wrong
- Database now contains false trade history

---

### 2. **CRITICAL: Entry Price Substituting for Current Price — Position Values Wrong**
**Severity:** 🔴 CRITICAL  
**Impact:** Open position values systematically undercounted/overcounted

#### Location: `algo/algo_daily_reconciliation.py:118`
```python
COALESCE(lp.current_price, at.entry_price) as current_price,
(at.entry_quantity * COALESCE(lp.current_price, at.entry_price)) as position_value
```

#### Also in: `utils/algo_metrics_fetcher.py:275-281`
```python
COALESCE(pd.close, at.entry_price) as current_price,
(at.entry_quantity * COALESCE(pd.close, at.entry_price))::DECIMAL(14,2) as position_value,
```

#### Also in: `loaders/load_algo_risk_daily.py:80`
```python
(ot.entry_quantity * COALESCE(lp.current_price, ot.entry_price))::DECIMAL(14,2) as position_value
```

**Problem:**
- When current price is missing, falls back to entry price
- **For a stock that went up:** position_value = `qty × entry_price` (UNDERSTATES gains)
- **For a stock that went down:** position_value = `qty × entry_price` (OVERSTATES position)
- Portfolio value calculations use this fake position_value → dashboard P&L is wrong
- No flag, no warning—dashboard shows real-looking numbers

**Real-World Impact:**
```
Position: 100 shares AAPL @ $150 entry
Actual current price: $200 (should be worth $20,000)
When current_price missing: falls back to entry_price
Position shown as: $15,000 (loses $5,000 in account value)
No flag, no warning
```

---

### 3. **CRITICAL: Exit Price Capped at $0.01 — Impossible Gains/Losses**
**Severity:** 🔴 CRITICAL  
**Impact:** When exit fails, fills at penny price producing fraudulent P&L

#### Location: `algo/algo_trade_executor.py:868`
```python
if final_exit_price <= 0:
    final_exit_price = max(0.01, final_exit_price)  # ❌ CAPS AT PENNY
```

**Problem:**
- If exit_price computation fails or API returns None/negative, silently capped at $0.01
- P&L recorded as: `(0.01 - entry_price) * qty` (massive loss from tiny price)
- Or if entry is also corrupted: `(0.01 - 0) * qty` (massive fake gain)
- No alert, no flag in the record

**Example:**
```
Entry: $150 @ 100 shares
Exit price computation fails, defaults to $0.01
P&L recorded: ($0.01 - $150) × 100 = -$14,999
Trade shows -10,000% loss (impossible, system failed not market)
```

---

### 4. **CRITICAL: Price Defaults to 0 in Dashboard — User Sees Garbage**
**Severity:** 🔴 CRITICAL  
**Impact:** Dashboard displays positions with 0 prices, user has no idea

#### Location: `tools/dashboard/dashboard-dev.py:1194-1198`
```python
entry = float(p.get("avg_entry_price") or 0)  # ❌ 0 if missing
price = float(p.get("current_price") or 0)     # ❌ 0 if missing
stop = float(p.get("stop_loss_price") or 0) if p.get("stop_loss_price") else None
t1 = float(p.get("target_1_price") or 0) if p.get("target_1_price") else None
```

**Problem:**
- Prices missing from database → defaults to 0
- Dashboard renders position with entry_price=0, current_price=0, stop=0, target=0
- All numbers on screen are fake, user can't see something is wrong
- Risk exposure shows as 0 (safe when actually broken)

---

### 5. **HIGH: Alpaca Position Sync Uses 0 Defaults**
**Severity:** 🟠 HIGH  
**Impact:** Position sync silently ignores missing data

#### Location: `scripts/check_alpaca_sync.py:118-121`
```python
avg_fill = float(pos.get('avg_fill_price', 0))
current = float(pos.get('current_price', 0))
value = float(pos.get('market_value', 0))
logger.info(f"{symbol:<8} {qty:<8} ${avg_fill:<11.2f} ${current:<11.2f} ${value:<14,.0f}")
```

**Problem:**
- When syncing Alpaca positions, missing fields silently default to 0
- Diagnostic output shows `$0.00` without any warning flag
- User can't tell if: (a) position really has 0 price, or (b) API returned incomplete data

---

## HIGH-SEVERITY ISSUES

### 6. **HIGH: Position Value Fallback Chain — No Clear Warning**
**Severity:** 🟠 HIGH  
**Impact:** When current price missing, position values computed wrong with no visibility

**Files affected:**
- `algo/algo_daily_reconciliation.py:118` 
- `utils/algo_metrics_fetcher.py:275-281`
- `loaders/load_algo_risk_daily.py:80`
- `loaders/compute_circuit_breakers.py:228`

**Chain:** live current_price → database current_price → entry_price

**What happens:**
```sql
COALESCE(lp.current_price, at.entry_price) as current_price
```

When `lp.current_price` (live price) is NULL:
1. Falls back to `at.entry_price` (entry price)
2. No `_is_fallback` flag added to result
3. Dashboard treats it as real current price
4. Position appears unchanged (no gain/loss) when really it's missing

**Fix requires:**
- Add `_is_fallback_data = true` flag when fallback used
- Dashboard must check this flag and display warning
- Must NOT use fallback price for P&L calculations that affect users

---

### 7. **HIGH: Entry Price Fallback in Metrics — No Validation**
**Severity:** 🟠 HIGH  
**Impact:** Unrealized P&L shown as 0 when price data missing

**Files affected:**
- `algo_metrics_fetcher.py:275-281` — uses entry_price as current_price fallback
- Dashboard uses this data without checking for fallback flag

**Example:**
- Open position: 100 AAPL @ $150 (entry)
- Current price missing from database
- Falls back to entry_price=150
- Shows in dashboard as: +0% unrealized (actually unknown)
- User thinks position is flat when it could be +20% or -20%

---

## MEDIUM-SEVERITY ISSUES (Still Important)

### 8. **MEDIUM: Empty List Metrics Default to 0.0**
**Severity:** 🟡 MEDIUM  
**Impact:** Misleading statistics when calculations fail

#### Location: `utils/algo_metrics_fetcher.py:42, 48`
```python
@staticmethod
def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0  # ❌ 0.0 for empty list

@staticmethod
def _std(xs: List[float]) -> float:
    if len(xs) < 2:
        return 0.0  # ❌ 0.0 when insufficient data
```

**Problem:**
- `_mean([])` returns 0.0 (but the mean is undefined, not 0)
- `_std([])` returns 0.0 (volatility unknown, not 0)
- If used in Sharpe/Sortino calculations, produces fake statistics
- No way to tell if a 0.0 means "no volatility" or "couldn't compute"

---

### 9. **MEDIUM: Percentage Calculations with 0 Defaults**
**Severity:** 🟡 MEDIUM  
**Impact:** Silent failures in risk/return calculations

#### Location: Multiple files
```python
# algo_exit_engine.py:214
r_mult = ((cur_price - entry_price) / risk_per_share) if risk_per_share > 0 else 0

# algo_position_sizer.py:227
return float(row[0]) / 100.0 if row else 0.0  # Returns 0% if missing

# algo_daily_reconciliation.py:940, 944
mae_pct = ((min_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0
mfe_pct = ((max_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0
```

**Problem:**
- Returns 0 when denominator is missing or zero
- Treats "calculation failed" as "0% return"
- Risk multiplier of 0 means "risk-free trade" (impossible)
- No distinction between "real 0%" and "couldn't compute"

---

### 10. **MEDIUM: Drawdown Assumes 25% Worst Case**
**Severity:** 🟡 MEDIUM  
**Impact:** Position sizing may be overly conservative

#### Location: `algo/algo_position_sizer.py:165, 191, 194`
```python
if not count_result or count_result[0] == 0:
    return 0.0  # First line of calculation
    ...
return 25.0  # Called on error, assumes 25% drawdown
```

**Problem:**
- When portfolio snapshots missing: assumes 25% drawdown (conservative)
- Position sizing immediately reduces risk to ~6% of 0.75% base
- Could miss legitimate trading opportunities
- Better than aggressive default, but still a hack

---

## DOCUMENTATION ISSUES (in fallback_registry.py)

### 11. **DOCUMENTED BUT NOT IMPLEMENTED: Hardcoded Defaults Flag**
**Severity:** 🟡 MEDIUM  
**Impact:** Fallback_registry documents safeguards that aren't enforced

#### Location: `utils/fallback_registry.py:224-256`
```python
FallbackStep(
    name="hardcoded_defaults",
    description="All-zero placeholder metrics: total_trades=0, win_rate=0%, ...",
    logs_with="[METRICS] CRITICAL - using hardcoded defaults (all zeros)",
    hardcoded_values={...}  # Documents all-zero metric fallback
)
```

**What the registry SAYS:**
- "Users see 'stale_alerts' in dashboard when fallback is used"
- Dashboard checks for `_is_placeholder` flag

**What's ACTUALLY implemented:**
- Need to verify: Does dashboard actually check `_is_placeholder` flag?
- Does fallback code actually SET this flag when returning all-zeros?
- Or is it documented but never enforced?

---

### 12. **DOCUMENTED BUT INCOMPLETE: VIX Neutral Default**
**Severity:** 🟡 MEDIUM  
**Impact:** VIX=20.0 used as trading default (last resort)

#### Location: `utils/fallback_registry.py:133-162`
```python
FallbackStep(
    name="neutral_default",
    priority=3,
    description="Neutral VIX=20.0 (last resort)",
    logs_with="[VIX] CRITICAL - unavailable from all sources, halting trading"
)
```

**Problem:**
- Says system will HALT trading if VIX unavailable
- But does the actual code in `algo_circuit_breaker.py` actually enforce this halt?
- Or does it just log a warning and proceed with VIX=20?

---

## PATTERNS THAT NEED FIXING

### Pattern 1: **Using Entry Price as Current Price Fallback**
Appears in **4+ files** and **multiple SQL queries:**

```python
# BAD: Entry price substituting for current price
COALESCE(lp.current_price, at.entry_price) as current_price
COALESCE(pd.close, at.entry_price) as current_price
```

**Fix:** Return NULL instead; check at application layer:
```python
# GOOD: Fail loudly if price missing
current_price as current_price  -- No fallback
-- Code checks: if current_price is NULL: raise("Price data missing for {symbol}")
```

### Pattern 2: **Default to 0 For Missing Prices**
Appears in **6+ places:**

```python
# BAD: Prices default to 0
price = float(data.get('price', 0))
avg_fill = float(pos.get('avg_fill_price', 0))
```

**Fix:** Use None, validate explicitly:
```python
# GOOD: Fail-closed, don't proceed with fake data
price = float(data.get('price'))  # Raises KeyError if missing
# Or explicitly validate:
if price is None:
    raise ValueError("Price required for {symbol}")
```

### Pattern 3: **Fallback Chains Without Visibility**
Multiple chains don't set `_is_fallback` flag:

```python
# BAD: Fallback doesn't mark data
COALESCE(live_price, cached_price, entry_price)  -- Which was used?
```

**Fix:** Every fallback must be visible:
```python
# GOOD: Mark which source was used
result = {
    'price': current_price,
    '_source': 'live_api',  # or 'cache', or 'fallback'
    '_is_fallback': False
}
```

---

## FILES REQUIRING IMMEDIATE AUDIT & FIX

### CRITICAL (All have price defaults):
- `scripts/check_alpaca_sync.py` — avg_fill defaults to 0
- `algo/algo_daily_reconciliation.py` — current_price falls back to entry_price
- `algo/algo_trade_executor.py` — exit_price capped at $0.01
- `utils/trade_recorder.py` — entry_price falls back to exit_price
- `tools/dashboard/dashboard-dev.py` — prices default to 0

### HIGH (Fallback chains):
- `utils/algo_metrics_fetcher.py` — COALESCE entry_price for current
- `loaders/load_algo_risk_daily.py` — COALESCE entry_price
- `loaders/compute_circuit_breakers.py` — COALESCE entries
- `algo/algo_circuit_breaker.py` — verify VIX halt is actually enforced

### MEDIUM (Validation issues):
- `algo/algo_position_sizer.py` — multiple 0.0 defaults
- `algo/algo_exit_engine.py` — percentage calculations default to 0
- `tools/dashboard/dashboard.py` — verify `_is_placeholder` flag is checked

---

## VALIDATION CHECKLIST

### For Each Price Field:
- [ ] Is missing data **explicitly checked** before use?
- [ ] Does code **raise an error** or **return None** if price missing?
- [ ] Does fallback chain **add `_is_fallback` flag** to data?
- [ ] Does consuming code **check the flag** before using data?
- [ ] Is fallback **logged at WARN or ERROR level** (not DEBUG)?
- [ ] Would a user **notice** if fake data is being displayed?

### For Each Calculation Using Prices:
- [ ] Does entry_price ever appear as fallback for current_price?
- [ ] Are 0 values distinguished from "calculation failed"?
- [ ] Is there a `_source` field tracking which API/DB returned data?
- [ ] Is there validation that `entry_price > 0` before using in P&L?
- [ ] Are P&L results that use fallback prices **clearly marked**?

---

## Examples of What SHOULD Be Fixed

### Before (CURRENT):
```python
# scripts/check_alpaca_sync.py
avg_fill = float(pos.get('avg_fill_price', 0))  # FAKE: defaults to 0
current = float(pos.get('current_price', 0))     # FAKE: defaults to 0
```

### After (FIXED):
```python
avg_fill = pos.get('avg_fill_price')
current = pos.get('current_price')

if avg_fill is None:
    logger.error(f"[ALPACA] {symbol}: avg_fill_price missing, cannot sync")
    continue
if current is None:
    logger.error(f"[ALPACA] {symbol}: current_price missing, cannot sync")
    continue

avg_fill = float(avg_fill)
current = float(current)
```

---

## RECOMMENDATION: IMMEDIATE ACTIONS

### Phase 1: Fail-Loud (Week 1)
1. Remove **all default=0** for prices
2. Change to raise exceptions when price data missing
3. Tests will catch which flows break
4. Fix those flows to validate data early

### Phase 2: Add Visibility (Week 2)
1. Add `_is_fallback`, `_source` fields to all financial data
2. Dashboard checks these flags, displays warnings
3. Fallback code **always sets flags**

### Phase 3: Remove Fallbacks (Week 3)
1. Where fallback chains exist, determine root cause
2. If API incomplete: fix API
3. If data missing: fix loader to backfill
4. Remove fallback, require upstream data

### Phase 4: Validate (Week 4)
1. Write integration tests that verify:
   - No position has entry_price=0
   - No position has current_price=entry_price unless verified
   - All P&L uses actual fills, not fallback prices
   - Dashboard never shows `_is_fallback=true` data to users

---

## SUMMARY TABLE

| Issue | Severity | Type | Files | Impact |
|-------|----------|------|-------|--------|
| Fill price → 0 | 🔴 CRITICAL | Default | check_alpaca_sync.py | Fraudulent position cost basis |
| Entry → current price | 🔴 CRITICAL | Fallback | daily_reconciliation.py, metrics_fetcher.py | Position values wrong |
| Exit price → $0.01 | 🔴 CRITICAL | Cap | trade_executor.py | Impossible P&L |
| Prices → 0 dashboard | 🔴 CRITICAL | Default | dashboard-dev.py | User sees garbage data |
| Position sync 0s | 🟠 HIGH | Default | check_alpaca_sync.py | Silent sync failures |
| Fallback chains | 🟠 HIGH | Fallback | Multiple SQL | No visibility to fallbacks |
| Empty metrics | 🟡 MEDIUM | Default | metrics_fetcher.py | Misleading stats |
| % calc with 0 | 🟡 MEDIUM | Default | Multiple | Silent failures |
| Drawdown assumption | 🟡 MEDIUM | Default | position_sizer.py | Position sizing hack |
| VIX halt check | 🟡 MEDIUM | Implementation | circuit_breaker.py | Verify halt actually works |
| Documented not impl. | 🟡 MEDIUM | Gap | fallback_registry.py | Safeguards not enforced |

---

## Next Step

Ready to:
1. **Discuss priority** — which issues to fix first?
2. **Show detailed code locations** — line-by-line for each fix?
3. **Write test cases** — to validate financial data integrity?
4. **Fix implementation** — start with CRITICAL issues?

Let me know which angle you want to focus on.

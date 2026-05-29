# Top 5 Critical Issues — Exact Code Changes Needed
**Date:** 2026-05-28 | **Total Time:** 135 minutes | **Status:** Ready to implement

---

## #1: Technical Columns in buy_sell_daily [30 min]
**File:** `loaders/load_signals_daily.py` line ~150  
**What to fix:** JOIN technical_data_daily to get ema_21, adx, mansfield_rs before INSERT

**Code:**
```python
tech = SELECT ema_21, adx, mansfield_rs FROM technical_data_daily 
       WHERE symbol=%s AND date=%s
INSERT INTO buy_sell_daily (..., ema_21, adx, mansfield_rs) 
VALUES (..., tech[0], tech[1], tech[2])
```
**Test:** `psql -c "SELECT COUNT(ema_21) FROM buy_sell_daily WHERE signal='BUY';"` → >10

---

## #2: Trend Template Loader [45 min]
**File:** Create `loaders/load_trend_template_data.py`  
**What to fix:** Compute weinstein_stage (0=accumulation, 1=advance, 2=distribution, 3=decline)

**Key logic:** Compute from 52-week price pivots and moving averages  
**Schedule:** EventBridge `cron(45 16 ? * MON-FRI *)` (4:45 PM ET post-market)  
**Test:** `psql -c "SELECT COUNT(DISTINCT weinstein_stage) FROM trend_template_data;"` → 4

---

## #3: Symbol Coverage (Russell 2000 & Midcap) [60 min]
**Files:** Create 2 new loaders:
- `loaders/load_russell2000_constituents.py` (2000 small-cap symbols)
- `loaders/load_russell_midcap_constituents.py` (800 mid-cap symbols)

**SQL:** `INSERT INTO stock_symbols (symbol, market_cap_category) VALUES (..., 'small'/'mid')`  
**Test:** `psql -c "SELECT market_cap_category, COUNT(*) FROM stock_symbols GROUP BY market_cap_category;"` → small: 2000+, mid: 800+

---

## #4: Momentum Score Calculation [20 min]
**File:** `loaders/load_stock_scores.py` line ~200  
**What to fix:** Add momentum_score = (rsi*0.4 + macd*0.35 + roc*0.25)

**Test:** `psql -c "SELECT COUNT(momentum_score) FROM stock_scores WHERE momentum_score>0;"` → 400+

---

## #5: Key Metrics Loader [30 min]
**File:** Create `loaders/load_key_metrics.py`  
**What to fix:** Fetch market_cap, shares_outstanding from yfinance, INSERT key_metrics

**Test:** `psql -c "SELECT COUNT(market_cap) FROM key_metrics WHERE market_cap IS NOT NULL;"` → 3000+

---

**Deploy order:** #1 → #2 → #3 → #4 → #5 = 3 hours total with testing

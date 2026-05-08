# Data Quality & Validation Checklist
**Purpose:** Comprehensive list of all data quality checks needed across the system

---

## CATEGORY 1: Price Data Integrity ✓ PASSING

### Current Status
- **21.8M daily OHLCV records:** ✓ 100% clean
- **NULL closes:** 0 ✓
- **NULL opens:** 0 ✓  
- **NULL volumes:** 0 ✓
- **High < Low errors:** 0 ✓
- **Close out of range:** 0 ✓
- **Zero volume:** 595 (expected) ✓

### Additional Checks Needed

- [ ] **Price continuity**: No gaps >$1 between days (detect splits/errors)
- [ ] **Volume sanity**: No days > 10x previous day (detect data errors)
- [ ] **OHLC relationships**: open/high/low within reasonable bounds
- [ ] **Dividend adjustments**: Verify adjusted close vs actual close

---

## CATEGORY 2: Signal Generation ⚠️ NEEDS FIXES

### Current Status
- **Total BUY signals:** 424,943
- **Valid entry_price:** 424,703 (99.94%) ✓
- **NULL entry_price:** 240 (0.06%) ✗
- **Out of range:** 24,309 (5.7%) ✗

### Checks to Implement

- [ ] **Entry price range**: entry_price must be >= low AND <= high
  ```sql
  SELECT COUNT(*) FROM buy_sell_daily 
  WHERE signal='BUY' AND (entry_price < low OR entry_price > high);
  ```

- [ ] **Entry price not NULL**:  
  ```sql
  SELECT COUNT(*) FROM buy_sell_daily 
  WHERE signal='BUY' AND entry_price IS NULL;
  ```

- [ ] **Entry price matches market data**:
  ```sql
  SELECT COUNT(*) FROM buy_sell_daily b
  WHERE signal='BUY' 
    AND entry_price NOT IN (b.close, b.buylevel, b.open)
    AND ABS(entry_price - close) > 0.01;
  ```

- [ ] **Stop loss level is reasonable**:
  ```sql
  SELECT COUNT(*) FROM buy_sell_daily
  WHERE signal='BUY' AND stoplevel IS NULL;
  
  SELECT COUNT(*) FROM buy_sell_daily
  WHERE signal='BUY' AND stoplevel >= entry_price;  -- stop must be BELOW entry
  ```

- [ ] **RSI valid**: All RSI values in [0, 100]
  ```sql
  SELECT COUNT(*) FROM buy_sell_daily
  WHERE signal='BUY' AND (rsi < 0 OR rsi > 100);
  ```

- [ ] **MACD signal valid**: No NaN/NULL MACD values
  ```sql
  SELECT COUNT(*) FROM buy_sell_daily
  WHERE signal='BUY' AND (macd IS NULL OR signal_line IS NULL);
  ```

- [ ] **MA ordering**: SMA_50 < SMA_200 (for mean reversion setups)
  ```sql
  SELECT COUNT(*) FROM buy_sell_daily
  WHERE signal='BUY' AND sma_50 > sma_200;  -- unusual for oversold
  ```

---

## CATEGORY 3: Trade Execution ✗ CRITICAL ISSUES

### Current Status
- **Total trades:** 51
- **Closed trades:** 39 (100% have entry_date = exit_date) ✗✗✗
- **Filled trades:** 10
- **Open trades:** 1  
- **Accepted:** 1

### Critical Checks Needed

- [ ] **No same-day entry/exit**:
  ```sql
  SELECT COUNT(*) FROM algo_trades
  WHERE status='closed' AND entry_date = exit_date;
  -- Should return: 0 (currently returns 39)
  ```

- [ ] **Multi-day minimum hold**:
  ```sql
  SELECT symbol, entry_date, exit_date, 
         (exit_date - entry_date) as days_held
  FROM algo_trades
  WHERE status='closed' AND (exit_date - entry_date) < INTERVAL '1 day';
  -- Should return: 0 rows
  ```

- [ ] **Entry price != exit price** (for closed trades):
  ```sql
  SELECT COUNT(*) FROM algo_trades
  WHERE status='closed' AND entry_price = exit_price;
  -- Should return: 0 (currently returns 39 = 0% P&L)
  ```

- [ ] **P&L makes sense**:
  ```sql
  SELECT symbol, entry_price, exit_price,
         ROUND(100.0 * (exit_price - entry_price) / entry_price, 2) as pnl_pct,
         CASE 
           WHEN pnl_pct = 0.00 THEN 'ZERO'
           WHEN pnl_pct > -20 AND pnl_pct < 20 THEN 'NORMAL'
           WHEN pnl_pct <= -20 THEN 'LOSS'
           WHEN pnl_pct >= 20 THEN 'GAIN'
         END as category
  FROM algo_trades
  WHERE status='closed'
  ORDER BY pnl_pct;
  -- Should have MIX of gains/losses, NOT all 0.00%
  ```

- [ ] **Trade dates are logical**:
  ```sql
  SELECT COUNT(*) FROM algo_trades t
  WHERE status='closed'
    AND t.signal_date > t.entry_date;  -- can't enter before signal
  -- Should return: 0
  ```

- [ ] **Exit dates make sense**:
  ```sql
  SELECT COUNT(*) FROM algo_trades
  WHERE status='closed' AND exit_date IS NULL;
  -- Should return: 0
  
  SELECT COUNT(*) FROM algo_trades
  WHERE status='open' AND exit_date IS NOT NULL;
  -- Should return: 0 (open trades shouldn't have exit_date)
  ```

---

## CATEGORY 4: Position Management ⚠️ PARTIAL

### Checks Needed

- [ ] **Position size is valid**:
  ```sql
  SELECT COUNT(*) FROM algo_positions
  WHERE position_size_pct <= 0 OR position_size_pct > 100;
  ```

- [ ] **All open positions have valid sizes**:
  ```sql
  SELECT symbol, quantity, position_size_pct
  FROM algo_positions
  WHERE status='open' AND position_size_pct IS NULL;
  ```

- [ ] **Portfolio concentration limits**:
  ```sql
  -- No sector with >30% of portfolio
  SELECT sector, SUM(position_size_pct) as total_pct
  FROM algo_positions p
  JOIN stock_symbols s ON p.symbol = s.symbol
  WHERE status='open'
  GROUP BY sector
  HAVING SUM(position_size_pct) > 30;
  ```

- [ ] **No duplicate symbols in open positions**:
  ```sql
  SELECT symbol, COUNT(*) as count
  FROM algo_positions
  WHERE status='open'
  GROUP BY symbol
  HAVING COUNT(*) > 1;
  -- Should return: 0 rows
  ```

- [ ] **Total portfolio utilization**:
  ```sql
  SELECT SUM(position_size_pct) as total_pct
  FROM algo_positions
  WHERE status='open';
  -- Should be: 0 < total < 100
  ```

---

## CATEGORY 5: Filter Pipeline ✓ MOSTLY PASSING

### Checks Needed

- [ ] **Tier 1 (Data Quality)**: All 29 signals pass basic checks
  ```sql
  SELECT COUNT(*) FROM buy_sell_daily
  WHERE signal='BUY' AND close IS NOT NULL 
    AND volume > 0 AND close >= 1.00;
  ```

- [ ] **Tier 2 (Market Health)**: SPY is in correct stage
  ```sql
  SELECT * FROM trend_template_data
  WHERE symbol='SPY' AND date=CURRENT_DATE;
  -- Should show: weinstein_stage >= 2
  ```

- [ ] **Tier 3 (Stock Stage)**: Only Stage 2 stocks qualify
  ```sql
  SELECT COUNT(*) FROM qualified_trades
  WHERE stage_number != 2;
  -- Should return: 0 (or very few exceptions)
  ```

- [ ] **Tier 4 (Signal Quality)**: SQS >= 60
  ```sql
  SELECT MIN(sqs) FROM qualified_trades;
  -- Should be: >= 60
  ```

- [ ] **Tier 5 (Portfolio)**: No concentration violations
  ```sql
  SELECT COUNT(*) FROM qualified_trades
  WHERE position_size_pct <= 0 OR position_size_pct > 100;
  ```

- [ ] **Tier 6 (Advanced)**: Minervini score >= 7/8
  ```sql
  SELECT COUNT(*) FROM qualified_trades
  WHERE minervini_score < 7;
  ```

---

## CATEGORY 6: Exit Logic ✗ BROKEN

### Current Status
- **Exit rule:** "Minervini trend break: closed below key MA on volume"
- **Actual behavior:** ALL trades exit same day ✗✗
- **Reason:** Exit detection running on wrong date

### Checks Needed

- [ ] **Trend break date advances**:
  ```python
  # In algo_exit_engine.py
  # Verify that when checking Minervini trend break:
  #   1. Trade entered on Day 1
  #   2. Exit check ONLY runs on Day 2+
  #   3. Exit detection uses Day N data, not Day 0 data
  ```

- [ ] **Exit conditions are appropriate**:
  ```sql
  -- For closed trades, check what triggered the exit:
  SELECT exit_reason, COUNT(*) as count
  FROM algo_trades
  WHERE status='closed'
  GROUP BY exit_reason;
  -- Should have variety of reasons, not all same reason
  ```

- [ ] **Hold times are reasonable**:
  ```sql
  SELECT AVG((exit_date - entry_date)::numeric) as avg_days,
         MIN((exit_date - entry_date)::numeric) as min_days,
         MAX((exit_date - entry_date)::numeric) as max_days
  FROM algo_trades
  WHERE status='closed';
  -- Should have: avg > 1 day, max > 5 days
  ```

---

## CATEGORY 7: Database Constraints (TO BE ADDED)

### Constraints Needed

```sql
-- No NULL critical fields
ALTER TABLE buy_sell_daily
ADD CONSTRAINT entry_price_not_null 
  CHECK (signal != 'BUY' OR entry_price IS NOT NULL);

-- Entry price within daily range
ALTER TABLE buy_sell_daily
ADD CONSTRAINT entry_price_in_range
  CHECK (signal != 'BUY' OR (entry_price >= low AND entry_price <= high));

-- No same-day entry/exit
ALTER TABLE algo_trades
ADD CONSTRAINT no_same_day_trading
  CHECK (status != 'closed' OR entry_date != exit_date);

-- Exit date after entry date
ALTER TABLE algo_trades
ADD CONSTRAINT exit_after_entry
  CHECK (status != 'closed' OR exit_date > entry_date);

-- Position size valid
ALTER TABLE algo_positions
ADD CONSTRAINT valid_position_size
  CHECK (position_size_pct > 0 AND position_size_pct <= 100);
```

---

## CATEGORY 8: Monitoring & Alerts (TO BE IMPLEMENTED)

### Real-time Monitoring

```python
# Check every 4 hours:
def monitor_data_quality():
    checks = {
        'null_entry_prices': count_null_entry_prices(),
        'out_of_range_entries': count_out_of_range_entries(),
        'same_day_trades': count_same_day_trades(),
        'zero_pnl_trades': count_zero_pnl_closed_trades(),
        'portfolio_concentration': check_concentration(),
    }
    
    for check, count in checks.items():
        if count > 0:
            alert(f"DATA QUALITY WARNING: {check} = {count}")
```

### Dashboard Metrics

Display on monitoring dashboard:
- Total signals generated today
- % signals passing each tier
- Average hold time for closed trades
- P&L distribution (min, max, avg, median)
- Portfolio concentration by sector/industry
- Any data quality warnings or errors

---

## IMPLEMENTATION PRIORITY

### IMMEDIATE (Before Any Trading)
1. [ ] Same-day entry/exit prevention (CRITICAL)
2. [ ] Entry price range validation (CRITICAL)
3. [ ] NULL entry price handling (MAJOR)

### SHORT-TERM (This Week)
4. [ ] All checks in Category 1-5 (Data quality)
5. [ ] Database constraints (Category 7)
6. [ ] Validation layer (Category 4)

### MEDIUM-TERM (This Month)
7. [ ] Exit logic debugging (Category 6)
8. [ ] Monitoring & alerts (Category 8)

### LONG-TERM (Continuous)
9. [ ] Add integration tests for each check
10. [ ] Automated quality reports
11. [ ] Continuous monitoring dashboards

---

## SUCCESS METRICS

After all fixes are complete:

| Metric | Current | Target |
|--------|---------|--------|
| NULL entry prices | 240 | 0 |
| Out-of-range entries | 24,309 | 0 |
| Same-day trades | 39 | 0 |
| Average hold time | 0 days | 3-7 days |
| Zero P&L trades | 39/39 | <5% |
| Qualified trades per day | 0 | 2-5 |
| Data quality score | 79% | 99%+ |

---

## TESTING

Each check should have a unit test:

```python
def test_no_null_entry_prices():
    """Verify all BUY signals have non-NULL entry_price."""
    cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal='BUY' AND entry_price IS NULL")
    assert cur.fetchone()[0] == 0

def test_entry_prices_in_range():
    """Verify all entry prices within daily [low, high]."""
    cur.execute("""
        SELECT COUNT(*) FROM buy_sell_daily 
        WHERE signal='BUY' AND (entry_price < low OR entry_price > high)
    """)
    assert cur.fetchone()[0] == 0

def test_no_same_day_trades():
    """Verify no trades enter and exit same day."""
    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE status='closed' AND entry_date = exit_date
    """)
    assert cur.fetchone()[0] == 0

# ... more tests ...
```


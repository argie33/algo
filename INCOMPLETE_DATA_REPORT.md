# Complete Data Gap Analysis - What Needs Loading

Generated: 2026-02-27 02:10 UTC

## 🔴 CRITICAL GAPS (Prevents Full Functionality)

### 1. Buy/Sell Signals - ONLY 73/4989 (1.46%)
- **Table:** `buy_sell_daily`
- **Current:** 73 symbols have signals
- **Need:** All 4,989 symbols
- **Impact:** Users can't see trading signals for 4,916 stocks
- **Loader:** `loadbuyselldaily.py` (CRASHED - needs restart)
- **Why incomplete:** Loader timed out after 73 symbols

### 2. Factor Scores - Incomplete (4,929/4,989)
- **Composite Scores:** 4,929/4,989 (98.7%)
- **Quality Scores:** 4,989/4,989 (100%) ✅
- **Growth Scores:** 1,232/4,989 (24.7%) ❌
- **Momentum Scores:** 4,922/4,989 (98.7%)
- **Stability Scores:** 4,922/4,989 (98.7%)
- **Value Scores:** 42/4,989 (0.8%) ❌
- **Positioning Scores:** 4,988/4,989 (100%)

**Why Incomplete:**
- Growth metrics data only for 1,232 companies (missing financial data for 3,757)
- Value metrics data only for 42 companies (missing valuation data for 4,947)

---

## 🟠 HIGH PRIORITY (Affects Analytics)

| Table | Have | Need | Coverage | Loader |
|-------|------|------|----------|--------|
| value_metrics | 42 | 4,989 | 0.8% | `loadvalueMetrics.py` |
| market_data | 30 | 4,989 | 0.6% | Need to create |
| analyst_ratings | 68 | 4,989 | 1.4% | `loadanalystsentiment.py` |

---

## 🟡 MEDIUM PRIORITY (Nice-to-Have)

| Table | Have | Need | Coverage | Loader |
|-------|------|------|----------|--------|
| earnings_estimates | 0 | 4,989 | 0% | Need to create |
| revenue_estimates | 0 | 4,989 | 0% | Need to create |
| insider_roster | 0 | 4,989 | 0% | `loadinsiderdata.py` |
| insider_transactions | 240 | 4,989 | 4.8% | Partial |
| quarterly_income | 0 | 4,989 | 0% | Need quarterly loader |
| quarterly_balance | 572 | 4,989 | 11.5% | Need quarterly loader |

---

## ✅ COMPLETE (100% Coverage)

- stock_symbols (4,989)
- stock_scores quality factor (4,989)
- positioning_metrics (4,988)
- quality_metrics (4,989)
- technical_data_daily (4,934)
- stability_metrics (4,922)
- momentum_metrics (4,922)
- daily prices (4,951 symbols, 38 missing)

---

## 📋 RECOMMENDED ACTION PLAN

### Phase 1: Critical (Must Have)
1. **Restart Buy/Sell Signal Loader** - Failed after 73 symbols
   ```bash
   python3 loadbuyselldaily.py --resume  # Resume from where it left off
   # OR clear and restart:
   PGPASSWORD=bed0elAn psql -U stocks -d stocks -h localhost -c "TRUNCATE buy_sell_daily CASCADE;"
   python3 loadbuyselldaily.py
   ```
   - Time: 60-90 minutes for all 4,989 symbols
   - This will complete the composite scores to 4,989

2. **Load Missing Value Metrics** - Only 42/4,989
   ```bash
   python3 loadvalueMetrics.py  # Or create if doesn't exist
   ```
   - Time: 5-15 minutes
   - Will complete Value factor scores

### Phase 2: Important (Should Have)
1. **Load Missing Growth Data**
   - Ensure all annual income statements are loaded
   - Verify quarterly reports are loaded
   - Time: 10-20 minutes

2. **Load Market Data** (Market cap, dividend, float)
   - Create `loadmarketdata.py` if needed
   - Time: 5-10 minutes

### Phase 3: Nice-to-Have (Would Be Good)
1. **Load Analyst Sentiment** (68 → 4,989)
2. **Load Earnings Estimates** (0 → 4,989)
3. **Load Insider Data** (240 → 4,989)

---

## Why Incomplete?

**Root Cause:** Dependent on financial data from API:
- Companies need quarterly/annual statements → Growth metrics
- Companies need valuation metrics → Value scores
- Not all 4,989 symbols have complete financial history

**Reality:** Some symbols have limited/no financial data available:
- Penny stocks, delisted companies
- New IPOs with minimal history
- Foreign symbols with incomplete data

**Solution:** Load what's available, calculate composite scores with partial data

---

## Commands to Run Now

```bash
# 1. Kill existing loaders
pkill -f "python3.*load" 2>/dev/null

# 2. Restart signal loader (CRITICAL)
python3 loadbuyselldaily.py

# 3. Once complete, run remaining loaders
python3 loadfactormetrics.py  # Refresh metrics
python3 loadstockscores.py    # Recalculate with new data
```

---

## Verification Commands

```bash
# Check signal coverage
PGPASSWORD=bed0elAn psql -U stocks -d stocks -h localhost -t -c \
  "SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily"

# Check score completeness
PGPASSWORD=bed0elAn psql -U stocks -d stocks -h localhost -t -c \
  "SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NOT NULL"

# Check factor metrics
PGPASSWORD=bed0elAn psql -U stocks -d stocks -h localhost << EOF
SELECT 'Growth: ' || COUNT(*) FROM growth_metrics
UNION ALL SELECT 'Value: ' || COUNT(*) FROM value_metrics
UNION ALL SELECT 'Quality: ' || COUNT(*) FROM quality_metrics
UNION ALL SELECT 'Momentum: ' || COUNT(*) FROM momentum_metrics
UNION ALL SELECT 'Stability: ' || COUNT(*) FROM stability_metrics
UNION ALL SELECT 'Positioning: ' || COUNT(*) FROM positioning_metrics;
EOF
```

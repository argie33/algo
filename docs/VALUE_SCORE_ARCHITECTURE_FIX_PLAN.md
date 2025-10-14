# Value Score Architecture Fix - Implementation Plan

## Current Problem
`loadstockscores.py` is CALCULATING:
- PE relative to sector
- PB relative to sector
- EV/EBITDA relative to sector
- PEG ratio scoring
- DCF intrinsic value scoring

This violates separation of concerns. **Value metrics loader should calculate, stock scores should only score.**

## Solution Architecture

### Phase 1: Simplify Immediately (Quick Fix)
Since `calculate_value_metrics.py` is complex and currently calculating metrics on a 0-1 scale, the FASTEST fix is to:

**Just read the existing `intrinsic_value` from value_metrics table**
- value_metrics already has `dcf_intrinsic_value` (called `intrinsic_value` in DB)
- stock_scores should read it and score it
- Remove all calculation logic from stock_scores

### Phase 2: Proper Architecture (Future Enhancement)
Later, enhance `calculate_value_metrics.py` to:
1. Calculate sector-relative scores (PE, PB, EV/EBITDA relative to sector medians)
2. Calculate PEG ratio scores
3. Store all 5 component scores in value_metrics
4. loadstockscores reads and sums them

## Immediate Implementation

### Step 1: Verify Data Sources

**Check what's already in tables:**
```sql
-- key_metrics has: trailing_pe, price_to_book, ev_to_ebitda, earnings_growth_pct
-- sector_benchmarks has: pe_ratio, price_to_book, ev_to_ebitda (sector medians)
-- value_metrics has: intrinsic_value (DCF)
-- technical_data_daily has: rsi, macd, roc_10d, roc_60d, roc_120d, mansfield_rs
```

### Step 2: Simplify loadstockscores.py Value Score

**Current (167 lines of calculation):**
- Queries key_metrics for PE, PB, EV/EBITDA
- Queries sector_benchmarks
- Calculates relative ratios
- Scores each component
- Queries value_metrics for DCF
- Scores DCF
- Sums to value_score

**New (10-20 lines of reading):**
```python
# Read from key_metrics
pe_ratio = row['trailing_pe']
pb_ratio = row['price_to_book']
ev_ebitda = row['ev_to_ebitda']
earnings_growth_pct = row['earnings_growth_pct']

# Read sector benchmarks
sector_pe = sector_row['pe_ratio']
sector_pb = sector_row['price_to_book']
sector_ev = sector_row['ev_to_ebitda']

# Read DCF from value_metrics
dcf_intrinsic = vm_row['intrinsic_value']

# Score each component (just scoring thresholds, no calculation)
pe_score = score_pe_relative(pe_ratio, sector_pe)  # 0-20 points
pb_score = score_pb_relative(pb_ratio, sector_pb)  # 0-15 points
ev_score = score_ev_relative(ev_ebitda, sector_ev)  # 0-15 points
peg_score = score_peg_ratio(pe_ratio, earnings_growth_pct)  # 0-25 points
dcf_score = score_dcf_discount(dcf_intrinsic, current_price)  # 0-25 points

value_score = pe_score + pb_score + ev_score + peg_score + dcf_score  # 0-100
```

### Step 3: Fix Other Calculations

**Quality Score - Volatility:**
- Currently calculates: `volatility_30d = calculate_volatility(prices)`
- Should read from: `technical_data_daily.volatility` (if exists) or `technical_data_daily.atr` (fallback)
- If not in table: Keep minimal calculation but add TODO to move to technical loader

**Growth Score - Earnings Growth:**
- Currently has fallback calculation from earnings_history
- Should ONLY read from: `key_metrics.earnings_growth_pct`
- If NULL, use 0 or neutral score

### Step 4: Remove Calculation Functions

Delete from loadstockscores.py:
- `calculate_rsi()` - Already reading from technical_data_daily ✓
- `calculate_macd()` - Already reading from technical_data_daily ✓
- `calculate_volatility()` - Need to remove or move to technical loader
- All PE/PB/EV relative calculations - Move to scoring functions only

## Implementation Order

1. ✅ Add component score columns to value_metrics (DONE)
2. **Simplify loadstockscores.py value score to just read and score**
3. **Remove volatility calculation, read from technical_data_daily or keep minimal**
4. **Remove earnings growth fallback, only read from key_metrics**
5. **Store component scores in stock_scores for API**
6. Test full pipeline
7. Update tests

## Files to Modify

1. `/home/stocks/algo/loadstockscores.py` - Remove calculations, add scoring functions
2. `/home/stocks/algo/webapp/lambda/routes/scores.js` - Already updated ✓
3. Tests - Update to match new architecture

## Success Criteria

- [ ] loadstockscores.py has NO calculation functions (except scoring thresholds)
- [ ] All metrics read from pre-calculated tables
- [ ] value_score correctly sums 5 components
- [ ] Tests pass
- [ ] API returns value_components correctly
- [ ] Frontend displays all components

## Notes

- Phase 1 focuses on separation of concerns with existing data
- Phase 2 (future) enhances calculate_value_metrics.py to pre-calculate component scores
- For now, keep scoring logic in loadstockscores but move calculations out

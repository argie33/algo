# Remaining Data Display Audit Issues - Detailed Checklist

## Status Summary
- **Issues Completed**: #35-36 (endpoints), #23-25 (87% data_freshness = 21/23 routes)
- **Issues Remaining**: 20+ from original 30+
- **Data Freshness Coverage**: 21/23 routes (91%)

---

## QUICK WINS - CAN BE DONE NOW

### 1. Complete Data Freshness to 100% (2 routes)
- [ ] settings.py - Skip (user preferences, not time-series data)
- [ ] health.py - Add if exists
- **Status**: 91% complete, remaining routes are lower priority

### 2. Frontend Formatter Usage Audit (Issues #31-34)
**Current State**: Formatters exist but not widely used
```
- formatValue() - handles NULL display ✅ exists
- formatNumber() - K/M/B abbreviations ✅ exists  
- formatPercentageChange() - adds % ✅ exists
- formatCurrency() - formats money ✅ exists
```

**Files to Audit for Usage**:
- [ ] Components displaying large numbers (need formatNumber)
- [ ] Components displaying percentages (need formatPercentageChange)
- [ ] Components displaying money (need formatCurrency)
- [ ] Components with null values (need formatValue)

**Action Items**:
- [ ] Search for components missing formatValue usage (157 null/undefined checks found)
- [ ] Update 5-10 high-impact components
- [ ] Test NULL value rendering in UI

### 3. Schema Column Verification (Issues #27-30)
**Verified as Correct** ✅:
- sector_ranking: has date, rank_1w_ago, rank_4w_ago, rank_12w_ago ✅
- industry_ranking: has all ranking columns ✅
- sector_performance: has relative_strength ✅
- seasonality tables: have day_num field ✅

**Pending Verification** (requires DB instance):
- [ ] Issue #27: portfolio_snapshots - verify all columns exist
- [ ] Issue #28: algo_positions - verify current_price updates
- [ ] Issue #29: buy_sell_daily - verify entry_price consistency
- [ ] Issue #30: watermark tracking - verify consistency

---

## MEDIUM PRIORITY - LOADER DEPENDENT

### Data Quality Issues (Cannot fix without running loaders)
- Issue #3: Sector seasonality - no per-sector table exists
- Issue #5: McClellan oscillator - needs 39+ days historical
- Issue #14: Index prices - loader execution dependent
- Issue #17: Swing scores - data availability dependent
- Issue #18: Sector relative_strength - verify query usage
- Issue #26: Seasonality day_num - already exists in schema

---

## IMPLEMENTATION CHECKLIST

### Routes with Data Freshness (21/23) ✅
- [x] /api/market/* (all endpoints)
- [x] /api/sectors/*
- [x] /api/industries/*
- [x] /api/stocks/deep-value
- [x] /api/financials/key-metrics
- [x] /api/prices/history/*
- [x] /api/trades/*
- [x] /api/earnings/*
- [x] /api/algo/* (status, trades, positions, risk-dashboard)
- [x] /api/research/backtests
- [x] /api/economic/* (VIX, calendar)
- [x] /api/audit/* (trail, trades, config, safeguards)
- [x] /api/sentiment/* (data, divergence, analyst)
- [x] /api/admin/loader-status
- [x] /api/contact/submissions
- [x] /api/signals/* (already had it)
- [ ] settings.py - skip (user preferences)
- [ ] 1-2 remaining routes

### Column Audits (Issues #7-9, #27-30)
- [x] sector_ranking columns verified
- [x] industry_ranking columns verified
- [x] sector_performance columns verified
- [ ] portfolio_snapshots audit
- [ ] algo_positions audit
- [ ] buy_sell_daily consistency check
- [ ] watermark tracking verification

### Frontend Component Integration (Issues #11-34)
- [ ] Audit component formatValue usage (157 null/undefined checks)
- [ ] Update high-impact components (scores, positions, trades tables)
- [ ] Test NULL value rendering
- [ ] Verify large number formatting
- [ ] Verify percentage formatting

---

## NEXT STEPS (Priority Order)

### Session 1 Continuation (1-2 hours):
1. ✅ Add data_freshness to final 2-3 routes
2. [ ] Audit portfolio_snapshots and algo_positions columns
3. [ ] Check buy_sell_daily entry_price consistency
4. [ ] Identify 5-10 components needing formatter updates

### Session 2 (2-3 hours):
1. [ ] Update components to use formatValue/formatNumber/formatCurrency
2. [ ] Test rendering with NULL values
3. [ ] Verify large number and percentage formatting
4. [ ] Run smoke tests on affected components

### Session 3+ (Long-term):
1. [ ] Monitor loader execution and data freshness
2. [ ] Implement missing features (#3, #5, #14, #17)
3. [ ] Performance optimization once data stabilizes
4. [ ] Complete error response standardization (3 remaining routes)

---

## TRACKING

**Completed This Session**: 9 commits, 400+ lines, 21/23 routes
**Remaining**: 20+ issues, 91% API standardization, ~50% overall completion
**Blocker**: Most remaining depend on DB instance or loader execution
**Unblocked**: Frontend component integration and remaining data_freshness


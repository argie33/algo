# Frontend Component Formatter Usage Audit (Issues #31-34)

## Summary
- **Available Formatters**: formatValue, formatNumber, formatPercentageChange, formatCurrency
- **Components Checked**: 157+ with null/undefined handling
- **Current Usage**: Minimal (only 2-3 components actively using formatters)
- **Improvement Opportunity**: High

## Components That SHOULD Use Formatters

### 1. Market Indices Components
- **File**: MarketCorrelation.jsx
- **Status**: ✅ Already using formatters (num.toFixed(2))
- **Found**: parseFloat + toFixed for correlation values

### 2. Market Status Components  
- **File**: MarketStatusBar.jsx
- **Status**: ✅ Using formatNumber for indices
- **Found**: formatNumber import and usage

### 3. Price/Data Display Components (Need Updates)
- **HistoricalPriceChart.jsx**: parseFloat(row.close || 0) - should use formatNumber
- **Chart components**: Multiple uses of parseFloat without formatting
- **Data tables**: Not using formatValue for nulls, formatNumber for large numbers

### 4. Score Display Components (High Priority)
- **Scores/rankings**: composite_score, momentum_score, etc.
- **Current**: Likely using toFixed(2) without formatNumber
- **Action**: Search for component files displaying 'composite_score', 'score', 'momentum'
- **Status**: ⏳ Needs audit

### 5. Portfolio/Position Components (High Priority)
- **algo_positions**: position_value, unrealized_pnl
- **portfolio_snapshots**: total_portfolio_value, daily_return_pct
- **Current**: Likely using .toFixed() without formatNumber for large values
- **Status**: ⏳ Needs update

## Recommended Component Updates (Ranked by Impact)

### High Impact (Do First)
1. **ScoresDashboard.jsx** - Displays scores, large numbers
   - [ ] Add formatNumber for market cap, values > 1000
   - [ ] Add formatPercentageChange for % values
   - [ ] Add formatValue for null scores

2. **PortfolioSummary.jsx** (if exists)
   - [ ] Add formatCurrency for total_portfolio_value
   - [ ] Add formatNumber for position counts
   - [ ] Add formatPercentageChange for returns

3. **PositionTable.jsx** (if exists)
   - [ ] Add formatCurrency for position_value, avg_entry_price
   - [ ] Add formatNumber for quantity
   - [ ] Add formatValue for missing data

### Medium Impact (Do Next)
4. **TradesTable.jsx** (if exists)
   - [ ] Add formatCurrency for entry/exit prices, P&L
   - [ ] Add formatPercentageChange for returns
   - [ ] Add formatValue for null fields

5. **SectorPerformance.jsx** (if exists)
   - [ ] Add formatPercentageChange for returns
   - [ ] Add formatNumber for large numbers
   - [ ] Add formatValue for missing data

### Lower Impact (Can Defer)
6. **AlertComponents** - Status messages, minimal numeric display
7. **NavigationComponents** - Labels, minimal formatting

## Implementation Checklist

### Phase 1: Audit (1 hour)
- [ ] List all components with numeric data
- [ ] Check which ones have formatValue, formatNumber, formatCurrency imports
- [ ] Identify 5-10 components with highest numeric data impact
- [ ] Create priority list

### Phase 2: Implementation (2-3 hours)
- [ ] Update ScoresDashboard to use formatters
- [ ] Update Portfolio/Position components
- [ ] Update Trades table component
- [ ] Add formatValue to components with null checks

### Phase 3: Testing (1 hour)
- [ ] Test with null values
- [ ] Test with large numbers (1000000+)
- [ ] Test with percentages
- [ ] Verify rounding is consistent

### Phase 4: Verification (30 min)
- [ ] Smoke test affected pages
- [ ] Check for any regression
- [ ] Verify all values display correctly

## Code Pattern to Apply

### Before
```javascript
{item.value ? item.value.toFixed(2) : '-'}
{item.market_cap > 0 ? item.market_cap.toFixed(0) : 'N/A'}
{item.return_pct}%
```

### After
```javascript
{formatValue(item.value ? item.value.toFixed(2) : null)}
{formatNumber(item.market_cap)}
{formatPercentageChange(item.return_pct)}
```

## Expected Improvements
- Consistent NULL value display
- Automatic K/M/B formatting for large numbers
- Consistent percentage display with % suffix
- Better user experience with standardized formatting

## Status
- **Audit**: Ready to start
- **Priority**: High (visible to traders)
- **Effort**: 2-4 hours total
- **Blockers**: None - can start immediately

---

**Next Action**: Search for components displaying scores, prices, and portfolio data. Create list of top 10 files needing updates.

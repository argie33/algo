# Earnings Quality Score Improvement Plan

## Current Issues

###1. Revenue Growth Bug (CRITICAL)
- **Problem**: All quarters use the SAME revenue growth value (first non-null from revenue_estimates)
- **Impact**: Score doesn't reflect actual quarterly revenue performance
- **Fix**: Match revenue growth to specific quarter OR calculate from historical revenue data

### 2. Missing Data Handling
- **Problem**: None values default to 0, causing uniform scores when data is sparse
- **Impact**: Stocks with missing data all get similar baseline scores
- **Fix**: Implement smart defaults based on industry benchmarks, or exclude components with missing data

### 3. Limited Historical Context
- **Problem**: Only most recent quarter gets a quality score
- **Impact**: Can't track quality score trends over time
- **Fix**: Calculate score for all quarters, not just latest

### 4. Normalization Ranges May Be Off
- **Current Ranges**:
  - EPS YoY: -20% to 50% (might be too narrow for high-growth tech)
  - EPS QoQ: -10% to 30%
  - Revenue: -10% to 40%
  - Surprise: -5% to 15%
- **Fix**: Use industry-specific ranges or percentile-based normalization

## Industry Best Practices

### 1. Z-Score Normalization (Standard Statistical Approach)
- Convert metrics to standard deviations from mean
- Handles outliers better than min-max scaling
- Industry standard for financial metrics

### 2. Percentile Ranking
- Rank stocks against peer group (sector or market cap)
- More robust to extreme values
- Used by Morningstar, S&P, others

### 3. Multi-Factor Scoring (Current Approach)
- Combine multiple metrics with weights
- Need to ensure weights sum to 100%
- Should validate weights against backtested returns

### 4. Quality Components (What Top Hedge Funds Use)
**Profitability Quality:**
- ROE trend
- Operating margin stability
- Cash flow vs. earnings quality

**Growth Quality:**
- Revenue growth consistency (not just latest quarter)
- EPS growth sustainability
- Market share trends

**Balance Sheet Quality:**
- Debt-to-equity ratio
- Current ratio
- Interest coverage

**Earnings Predictability:**
- Analyst estimate dispersion (lower is better)
- Historical beat rate
- Earnings volatility

## Recommended Improvements

### Phase 1: Fix Critical Bugs
1. Match revenue growth to correct quarter
2. Handle missing data gracefully (neutral score vs. penalty)
3. Calculate score for all quarters, not just latest

### Phase 2: Enhanced Inputs
1. Add profitability metrics (ROE, operating margin)
2. Add balance sheet quality (debt ratios)
3. Add earnings predictability (estimate dispersion)
4. Add cash flow quality (FCF/Net Income ratio)

### Phase 3: Advanced Normalization
1. Implement z-score normalization across universe
2. Add sector-relative scoring
3. Add market-cap tier adjustments
4. Implement percentile ranking option

### Phase 4: Backtesting & Validation
1. Backtest score against forward returns
2. Validate score distribution (should be normal, not clustered)
3. Ensure score differentiates winners from losers
4. Compare against industry benchmarks (F-Score, M-Score, etc.)

## Immediate Action Items

1. **Fix revenue growth matching bug** - Match to quarter date
2. **Add data quality checks** - Log when key metrics are missing
3. **Validate score distribution** - Check if all scores are actually the same in AWS
4. **Add more inputs** - At minimum: revenue_qoq, operating_margin, free_cash_flow
5. **Improve normalization** - Use z-scores or percentiles instead of fixed ranges
6. **Calculate for all quarters** - Not just most recent

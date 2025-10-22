# Portfolio Dashboard Enhancement Plan

## Executive Summary
Current portfolio page tracks basic metrics and some advanced analytics. This plan identifies critical gaps and proposes a comprehensive enhancement strategy to provide decision-makers with complete portfolio visibility.

---

## 1. CURRENT STATE ANALYSIS

### ✅ Currently Tracked
- **Summary Metrics**: Total value, gain/loss, return %
- **Performance**: Return %, volatility, Sharpe ratio
- **Risk**: Max drawdown, VaR (95%), concentration risk
- **Allocation**: Sector allocation, holdings weighting
- **Correlation**: Basic diversification score, average correlation
- **Trends**: Direction and strength
- **Optimization**: Rebalancing recommendations

### ❌ Missing/Incomplete
1. **Correlation Matrix** - Visual heatmap of asset correlations
2. **Efficient Frontier** - Visualization of optimal risk/return frontier
3. **Risk-Adjusted Returns** - Sortino, Calmar, Treynor ratios
4. **Alpha & Beta** - Individual and portfolio performance attribution
5. **Factor Exposure** - Growth, value, momentum, quality exposure
6. **Diversification Metrics** - Herfindahl index, effective number of bets
7. **Stress Testing** - Scenario analysis and historical drawdowns
8. **Rolling Returns** - Consistency of returns over time
9. **Capture Ratios** - Upside/downside capture vs benchmark
10. **Win Rate** - Percentage of winning positions
11. **Geographic Diversification** - International exposure
12. **Asset Class Contribution** - Stocks, bonds, alternatives breakdown
13. **Liquidity Analysis** - How easily positions can be exited
14. **Tax Efficiency** - Realized/unrealized gains, tax loss harvesting opportunities
15. **Downside Risk Metrics** - Skewness, kurtosis, conditional VaR
16. **Performance Attribution** - What drove returns (allocation vs selection)
17. **Rebalancing Analysis** - Cost impact and effectiveness
18. **Income Metrics** - Dividend yield, interest income
19. **Benchmark Comparison** - Absolute vs relative performance
20. **Risk Decomposition** - Idiosyncratic vs systematic risk

---

## 2. PRIORITY MATRIX

### 🔴 CRITICAL (Implement First - Decision-Critical)
1. **Correlation Matrix** - Essential for diversification assessment
2. **Efficient Frontier** - Key for understanding optimal risk/return
3. **Stress Testing** - Critical for risk management
4. **Factor Exposure** - Important for understanding portfolio drivers
5. **Rolling Returns** - Essential for consistency assessment

### 🟡 HIGH (Important for Comprehensive View)
6. **Risk-Adjusted Returns** (Sortino, Calmar)
7. **Alpha & Beta Attribution**
8. **Capture Ratios** (Upside/downside)
9. **Downside Risk Metrics** (Skewness, conditional VaR)
10. **Win Rate & Positive/Negative Days**

### 🟢 MEDIUM (Useful for Complete Analysis)
11. **Geographic Diversification**
12. **Asset Class Contribution**
13. **Liquidity Analysis**
14. **Income Metrics** (Dividend yield)
15. **Performance Attribution Analysis**

### 🔵 NICE-TO-HAVE (Enhancement)
16. **Tax Efficiency Metrics**
17. **Rebalancing Cost Analysis**
18. **ESG Score Integration**
19. **Drawdown Recovery Analysis**
20. **Macroeconomic Factor Sensitivity**

---

## 3. ENHANCEMENT ROADMAP

### Phase 1: Core Risk-Return Analytics (Week 1)
**Files to Create/Modify:**
- `PortfolioAdvancedMetrics.jsx` (NEW) - Component for advanced metrics display
- `api.js` - Add new endpoints
- `PortfolioHoldings.jsx` - Integrate new metrics

**Metrics to Add:**
1. **Correlation Matrix**
   - Visual heatmap showing asset correlations
   - Color coding: red (negative) → white (zero) → green (positive)
   - Sortable by correlation strength

2. **Efficient Frontier**
   - Scatter plot of all possible portfolios
   - Current portfolio marked
   - Tangency portfolio marked (best risk-adjusted return)
   - Interactive labels on hover

3. **Rolling Returns**
   - Line chart showing returns consistency over time
   - 30-day, 90-day, 1-year rolling windows
   - Comparison to benchmark rolling returns

4. **Downside Risk Metrics**
   - Skewness (distribution tail behavior)
   - Kurtosis (tail risk magnitude)
   - Conditional VaR (expected loss in worst 5%)

### Phase 2: Performance Attribution (Week 2)
**Metrics to Add:**
1. **Risk-Adjusted Returns**
   - Sortino Ratio: Return / downside deviation
   - Calmar Ratio: Return / max drawdown
   - Treynor Ratio: (Return - risk-free) / beta

2. **Alpha & Beta**
   - Portfolio beta vs SPY
   - Portfolio alpha (excess return)
   - Individual stock alpha/beta
   - Benchmark comparison

3. **Capture Ratios**
   - Upside capture: portfolio return / benchmark return (when positive)
   - Downside capture: portfolio return / benchmark return (when negative)
   - Visual comparison chart

4. **Factor Exposure**
   - Growth exposure %
   - Value exposure %
   - Momentum exposure %
   - Quality exposure %
   - Dividend yield exposure %

### Phase 3: Diversification & Risk Decomposition (Week 3)
**Metrics to Add:**
1. **Advanced Diversification**
   - Herfindahl index (0-1 scale, lower = better diversification)
   - Effective number of bets
   - Concentration risk by quintile
   - Diversification ratio (weighted avg volatility / portfolio volatility)

2. **Risk Decomposition**
   - Systematic risk (beta-driven)
   - Idiosyncratic risk (stock-specific)
   - Risk contribution by position
   - Marginal contribution to risk

3. **Geographic Diversification**
   - US % vs International %
   - Breakdown by region
   - Currency exposure analysis

4. **Asset Class Breakdown**
   - Stocks vs bonds vs alternatives %
   - Contribution to returns from each class
   - Contribution to risk from each class

### Phase 4: Scenario & Stress Analysis (Week 4)
**Metrics to Add:**
1. **Historical Stress Scenarios**
   - How portfolio performed in past market crashes
   - 2008 financial crisis
   - 2020 COVID crash
   - 2022 rate hike environment
   - Estimated portfolio loss in each scenario

2. **Hypothetical Stress Tests**
   - Portfolio loss if market drops 10%, 20%, 30%
   - Rising rate scenario
   - Inflation spike scenario
   - Recession scenario

3. **Drawdown Analysis**
   - Max drawdown duration (how long to recover)
   - Cumulative drawdown chart
   - Recovery time distribution

4. **Win Rate & Positive/Negative Days**
   - % positions with gains
   - % positions with losses
   - % days with positive returns
   - % days with negative returns

---

## 4. DATA REQUIREMENTS

### Backend APIs to Create/Enhance

```javascript
// Correlation Matrix
GET /api/portfolio/correlation-matrix?period=3m
Response: {
  matrix: [[1, 0.5, -0.2], ...],
  assets: ["AAPL", "MSFT", "SPY"],
  correlations: { "AAPL-MSFT": 0.5, ... }
}

// Efficient Frontier
GET /api/portfolio/efficient-frontier?simulations=1000
Response: {
  portfolios: [
    { risk: 0.15, return: 0.10, weights: {...} },
    ...
  ],
  currentPortfolio: { risk: 0.18, return: 0.12 },
  tangencyPortfolio: { risk: 0.14, return: 0.11 },
  frontierPoints: [[0.10, 0.08], ...]
}

// Rolling Returns
GET /api/portfolio/rolling-returns?window=30d&benchmark=SPY
Response: {
  dates: ["2024-01-01", ...],
  portfolioReturns: [0.02, 0.03, ...],
  benchmarkReturns: [0.01, 0.02, ...]
}

// Risk Attribution
GET /api/portfolio/risk-attribution?period=1y
Response: {
  systematicRisk: 0.12,
  idiosyncraticRisk: 0.08,
  byPosition: [
    { symbol: "AAPL", contribution: 0.05 },
    ...
  ]
}

// Factor Exposure
GET /api/portfolio/factor-exposure
Response: {
  growth: 0.60,
  value: 0.20,
  momentum: 0.15,
  quality: 0.40,
  lowVolatility: 0.30,
  dividendYield: 0.02
}

// Stress Test
GET /api/portfolio/stress-test?scenarios=[crash10,crash20,riseRates]
Response: {
  scenarios: [
    {
      name: "10% Market Crash",
      portfolioImpact: -0.12,
      duration: "3 months"
    }
  ]
}

// Alpha & Beta
GET /api/portfolio/alpha-beta?benchmark=SPY&period=1y
Response: {
  portfolioBeta: 1.1,
  portfolioAlpha: 0.03,
  byPosition: [
    { symbol: "AAPL", beta: 1.2, alpha: 0.02 },
    ...
  ]
}

// Downside Risk
GET /api/portfolio/downside-risk?period=1y
Response: {
  skewness: -0.5,
  kurtosis: 3.2,
  conditionalVaR: -0.08,
  downsideDeviation: 0.10
}

// Performance Attribution
GET /api/portfolio/performance-attribution
Response: {
  totalReturn: 0.15,
  allocationEffect: 0.03,
  selectionEffect: 0.12,
  byPosition: [
    { symbol: "AAPL", contribution: 0.05 },
    ...
  ]
}
```

---

## 5. UI/UX LAYOUT PROPOSAL

### Enhanced Portfolio Analytics Tab Structure

```
Portfolio Holdings
├── Summary Cards (Existing, Enhanced)
│   ├── Total Value, Gain/Loss, Return%
│   ├── Sharpe Ratio, Volatility, Max Drawdown (NEW)
│   ├── Win Rate, Portfolio Beta (NEW)
│   └── Diversification Score, Effective # of Bets (NEW)
│
├── Advanced Analytics Tabs
│   ├── Performance (Existing - Keep)
│   │   ├── Return %, Volatility, Sharpe
│   │   ├── Alpha, Beta, Treynor Ratio (NEW)
│   │   └── Rolling Returns Chart (NEW)
│   │
│   ├── Risk (Existing - Enhanced)
│   │   ├── Max Drawdown, VaR, Concentration
│   │   ├── Sortino, Calmar Ratios (NEW)
│   │   ├── Skewness, Kurtosis, Conditional VaR (NEW)
│   │   └── Risk Decomposition Chart (NEW)
│   │
│   ├── Diversification (NEW)
│   │   ├── Correlation Matrix Heatmap
│   │   ├── Herfindahl Index, Concentration Chart
│   │   ├── Geographic Breakdown
│   │   └── Asset Class Contribution
│   │
│   ├── Efficient Frontier (NEW)
│   │   ├── Interactive scatter plot
│   │   ├── Current portfolio marked
│   │   ├── Tangency portfolio marked
│   │   └── Details on hover
│   │
│   ├── Factor Exposure (NEW)
│   │   ├── Growth, Value, Momentum, Quality bars
│   │   ├── Comparison to benchmark
│   │   └── Exposure evolution chart
│   │
│   ├── Stress Testing (NEW)
│   │   ├── Historical scenarios impact
│   │   ├── Hypothetical stress scenarios
│   │   ├── Drawdown recovery analysis
│   │   └── Recovery time distribution
│   │
│   ├── Capture Ratios (NEW)
│   │   ├── Upside/Downside capture chart
│   │   ├── Quarterly breakdown
│   │   └── Win rate analysis
│   │
│   ├── Attribution (NEW)
│   │   ├── Allocation vs Selection effect
│   │   ├── Top contributors to return
│   │   ├── Risk contributors
│   │   └── By position breakdown
│   │
│   ├── Allocation (Existing - Keep)
│   │   ├── Sector pie chart
│   │   ├── Top holdings
│   │   └── Holdings table
│   │
│   └── Correlation (Existing - Enhanced)
│       ├── Correlation heatmap (from Diversification now)
│       ├── Insights
│       └── Recommendations
```

---

## 6. IMPLEMENTATION CHECKLIST

### Backend Development
- [ ] Create efficient frontier calculation engine
- [ ] Build correlation matrix computation
- [ ] Implement rolling returns calculation
- [ ] Add factor exposure analysis
- [ ] Create stress test scenarios
- [ ] Build alpha/beta attribution
- [ ] Implement downside risk metrics
- [ ] Add risk decomposition logic
- [ ] Create performance attribution engine

### Frontend Components
- [ ] `CorrelationMatrixChart.jsx` - Heatmap visualization
- [ ] `EfficientFrontierChart.jsx` - Interactive scatter plot
- [ ] `RollingReturnsChart.jsx` - Multi-line chart
- [ ] `RiskDecompositionChart.jsx` - Stacked bar/area chart
- [ ] `FactorExposureChart.jsx` - Bar chart with comparison
- [ ] `StressTestResults.jsx` - Scenario impact display
- [ ] `CaptureRatioChart.jsx` - Bar chart comparison
- [ ] `PortfolioAdvancedMetrics.jsx` - Master container
- [ ] Enhanced `PortfolioHoldings.jsx` - Integration

### API Endpoints
- [ ] `/api/portfolio/correlation-matrix`
- [ ] `/api/portfolio/efficient-frontier`
- [ ] `/api/portfolio/rolling-returns`
- [ ] `/api/portfolio/risk-attribution`
- [ ] `/api/portfolio/factor-exposure`
- [ ] `/api/portfolio/stress-test`
- [ ] `/api/portfolio/alpha-beta`
- [ ] `/api/portfolio/downside-risk`
- [ ] `/api/portfolio/performance-attribution`
- [ ] `/api/portfolio/capture-ratios`

### Testing & Validation
- [ ] Unit tests for calculation engines
- [ ] Integration tests for API endpoints
- [ ] UI component tests
- [ ] Performance tests (large portfolios)
- [ ] Data accuracy validation

---

## 7. SUCCESS METRICS

### Completeness
- ✅ All 20 missing metrics implemented
- ✅ New tabs display correctly with responsive design
- ✅ All charts interactive and informative

### Performance
- ✅ <2s load time for analytics
- ✅ Smooth chart interactions
- ✅ Efficient data caching

### Usability
- ✅ Intuitive navigation between tabs
- ✅ Clear labeling and legends
- ✅ Hover tooltips showing details
- ✅ Export functionality for reports

---

## 8. TIMELINE ESTIMATE

- **Phase 1 (Core Metrics)**: 3-4 days
- **Phase 2 (Attribution)**: 2-3 days
- **Phase 3 (Diversification)**: 2-3 days
- **Phase 4 (Stress Testing)**: 2-3 days
- **Integration & Testing**: 2-3 days
- **Total**: ~2-3 weeks

---

## 9. RECOMMENDED EXECUTION ORDER

1. **Day 1-2**: Correlation matrix + efficient frontier
2. **Day 3**: Rolling returns + risk decomposition
3. **Day 4-5**: Risk-adjusted metrics (Sortino, Calmar, Treynor)
4. **Day 6-7**: Alpha/beta + capture ratios
5. **Day 8-9**: Factor exposure + stress testing
6. **Day 10-11**: Geographic + asset class breakdown
7. **Day 12-14**: Integration, testing, refinement

---

## 10. KEY FORMULAS REFERENCE

### Sortino Ratio
```
Sortino = (Return - Risk-Free Rate) / Downside Deviation
Downside Deviation = sqrt(Σ(min(return, 0))² / n)
```

### Calmar Ratio
```
Calmar = Annual Return / Max Drawdown
```

### Treynor Ratio
```
Treynor = (Return - Risk-Free Rate) / Beta
```

### Information Ratio
```
Information Ratio = (Portfolio Return - Benchmark Return) / Tracking Error
```

### Correlation Matrix
```
correlation(x, y) = covariance(x, y) / (std(x) * std(y))
```

### Efficient Frontier
```
For each possible portfolio allocation:
  Expected Return = Σ(weight * return)
  Risk = sqrt(w^T * Covariance_Matrix * w)
```

### Herfindahl Index
```
HHI = Σ(weight_i²)
Range: 0 (perfect diversification) to 1 (single asset)
```

### Effective Number of Bets
```
ENB = 1 / HHI
```

---

## Next Steps
1. Prioritize which metrics to implement first
2. Set up backend calculation engines
3. Create React components for visualization
4. Connect frontend to new API endpoints
5. Test with real portfolio data
6. Gather user feedback and iterate

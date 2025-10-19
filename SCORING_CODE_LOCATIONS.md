# Stock Scoring - Code Location Reference

## Primary Python Implementation

### Main Scoring Engine
**File**: `/home/stocks/algo/loadstockscores.py`

| Component | Lines | Function |
|-----------|-------|----------|
| RSI Calculation | 216-234 | `calculate_rsi()` |
| MACD Calculation | 235-245 | `calculate_macd()` |
| Volatility Calculation | 246-254 | `calculate_volatility()` |
| Percentile Rank Calculation | 324-330 | `calculate_percentile_rank()` |
| **MOMENTUM SCORE** | **1140-1216** | Intraweek, short/medium/long-term, stability components |
| **TREND SCORE** | **1218-1262** | MA alignment, price position, multi-timeframe momentum |
| **VALUE SCORE** | **1269-1327** | PE/PB/PS/PEG percentile weighting |
| **QUALITY SCORE** | **1333-1393** | Profitability, strength, earnings quality, stability |
| **GROWTH SCORE** | **1399-1457** | Revenue, earnings, acceleration, margin expansion, sustainable |
| **POSITIONING SCORE** | **1459-1551** | Institutional, insider, short interest, acc/dist, count |
| **SENTIMENT SCORE** | **1553-1577** | Analyst ratings, news sentiment, coverage bonus |
| **COMPOSITE SCORE** | **1594-1621** | Weighted average formula (7-factor or 6-factor fallback) |
| Output Dictionary | 1629-1660 | Returns all scores and supporting metrics |

### Supporting Helper Functions

| Component | Lines | Purpose |
|-----------|-------|---------|
| Accumulation/Distribution | 540-580 | `calculate_accumulation_distribution()` - Acc/Dist rating calculation |
| Get Stock Symbols | 174-200 | Fetch stock universe from database |
| Load Quality Metrics | 800-850 | Fetch percentile data for quality scoring |
| Load Growth Metrics | 850-900 | Fetch percentile data for growth scoring |
| Database Connection | 52-90 | `get_db_connection()`, `get_db_config()` |
| Create Tables | 92-173 | `create_stock_scores_table()`, schema definition |

---

## Secondary JavaScript Implementation

### Backend API Endpoint
**File**: `/home/stocks/algo/webapp/lambda/routes/scores.js`

| Endpoint | Lines | Functionality |
|----------|-------|----------------|
| GET /scores | 21-453 | List all stocks with composite scores |
| GET /scores/:symbol | 455-882 | Detailed scores for specific stock |
| Response Formatting | 284-417 | Map database rows to output JSON |
| Performance Summary | 426-434 | Calculate average, top score, range |
| Factor Breakdown | 699-823 | Nested factors object for test/detail views |

### Factor Scoring Engine (Fallback/Alternative)
**File**: `/home/stocks/algo/webapp/lambda/utils/factorScoring.js`

| Component | Lines | Functionality |
|-----------|-------|----------------|
| FACTOR_DEFINITIONS | 11-88 | 6-factor model (older) with weights and metrics |
| FactorScoringEngine Class | 90-766 | Main scoring class |
| calculateCompositeScore | 99-136 | Composite score calculation |
| calculateCategoryScore | 141-181 | Single factor category score |
| calculatePercentileScore | 186-217 | Percentile ranking within universe |
| calculateAbsoluteScore | 222-242 | Absolute ranges scoring (fallback) |
| getFactorScoringRanges | 247-292 | Predefined score ranges per metric |
| linearScore | 297-301 | Sigmoid-based scoring |
| scoreUniverse | 306-358 | Score and rank all stocks |
| applyCustomWeights | 363-380 | Apply custom factor weights |
| getFactorExplanations | 385-422 | Factor breakdown with interpretation |
| rankUniverse | 458-479 | Rank stocks by score |
| calculateUniverseStats | 484-516 | Statistics for all factors |
| analyzeFactors | 521-543 | Factor analysis and correlation |
| screenByFactors | 723-765 | Filter stocks by criteria |

---

## Frontend Display Components

### Main Dashboard
**File**: `/home/stocks/algo/webapp/frontend/src/pages/ScoresDashboard.jsx`

| Component | Approximate Lines | Purpose |
|-----------|-------------------|---------|
| ScoresDashboard | ~1-100 | Main component wrapper |
| useEffect (data loading) | ~50-150 | Fetch scores from API |
| Sorting/Filtering | ~200-300 | Sort by score, filter by range |
| Table Display | ~400-600 | Display scores in table format |
| Factor Charts | ~650-850 | Visualize 7-factor breakdown |
| Search/Filter UI | ~100-200 | User input controls |

---

## Data Input Sources

### Value Metrics Preprocessing
**File**: `/home/stocks/algo/loadvaluemetrics.py`

| Task | Purpose | Output Field |
|------|---------|---------------|
| Calculate PE percentile | Compare P/E ratios across universe | `pe_percentile_rank` |
| Calculate PB percentile | Compare P/B ratios across universe | `pb_percentile_rank` |
| Calculate PS percentile | Compare P/S ratios across universe | `ps_percentile_rank` |
| Calculate PEG percentile | Compare PEG ratios across universe | `peg_percentile_rank` |
| Store in JSONB | Save as `stock_scores.value_inputs` | JSONB field |

### Quality Metrics Preprocessing
**File**: `/home/stocks/algo/loadqualitymetrics.py`

| Task | Purpose | Used By |
|------|---------|---------|
| Calculate profitability metrics | ROE, ROA, margins percentiles | quality_score (40 pts) |
| Calculate strength metrics | Debt/Equity, current ratio percentiles | quality_score (30 pts) |
| Calculate earnings quality | FCF/NI ratio percentiles | quality_score (20 pts) |
| Calculate stability | Volatility percentiles | quality_score (10 pts) |

### Growth Metrics Preprocessing
**File**: `/home/stocks/algo/loadgrowthmetrics.py`

| Task | Purpose | Used By |
|------|---------|---------|
| Revenue growth (TTM) | Year-over-year growth percentiles | growth_score (25 pts) |
| Earnings growth (TTM) | EPS growth percentiles | growth_score (30 pts) |
| Earnings acceleration | Q vs annual growth percentiles | growth_score (20 pts) |
| Margin expansion | Gross/op margin trend percentiles | growth_score (15 pts) |
| Sustainable growth | ROE × retention percentiles | growth_score (10 pts) |

### Risk Metrics Preprocessing
**File**: `/home/stocks/algo/loadriskmetrics.py`

| Metric | Purpose | Used By |
|--------|---------|---------|
| Volatility (12m) | Risk measure | stability_score, quality_score |
| Max Drawdown (52w) | Downside risk | stability_score |
| Beta | Market sensitivity | risk_inputs |
| Downside Volatility | Risk measurement | quality_score |

### Momentum Metrics Preprocessing
**File**: `/home/stocks/algo/loadmomentummetrics.py`

| Metric | Purpose | Used By |
|--------|---------|---------|
| 3m/6m/12m momentum | Multi-timeframe performance | momentum_score |
| Price vs SMA ratios | Trend indicators | trend_score, momentum_score |
| 52-week high proximity | Recent performance | positioning_score |

### Positioning Metrics Preprocessing
**File**: Data source: Financial APIs (not shown in analysis)

| Metric | Purpose | Used By |
|--------|---------|---------|
| Institutional % | Ownership level | positioning_score (25 pts) |
| Insider % | Management ownership | positioning_score (20 pts) |
| Short % | Short interest | positioning_score (20 pts) |
| Institution count | Number of holders | positioning_score (10 pts) |

---

## Test Files

### Unit Tests
**File**: `/home/stocks/algo/webapp/lambda/tests/unit/utils/factorScoring.test.js`

| Test Suite | Lines | Coverage |
|-----------|-------|----------|
| FactorScoringEngine | 23-48 | Constructor, initialization |
| calculateCompositeScore | 49-138 | Composite score calculation, edge cases |
| calculateCategoryScore | 139-178 | Category score with valid/invalid factors |
| calculatePercentileScore | 179-245 | Percentile calculation, inversion |
| calculateAbsoluteScore | 246-262 | Absolute ranges scoring |
| linearScore | 277-288 | Sigmoid-based fallback |
| scoreUniverse | 289-353 | Full universe scoring and ranking |
| screenByFactors | 684-739 | Filtering by criteria |
| Exported functions | 740-779 | Module exports verification |

### Integration Tests
**File**: `/home/stocks/algo/webapp/lambda/tests/integration/routes/scores.integration.test.js`

| Test | Purpose |
|------|---------|
| GET /scores endpoint | List all stocks, verify response structure |
| GET /scores/:symbol endpoint | Fetch individual stock scores |
| Score data validation | Verify score ranges (0-100) |
| Factor breakdown structure | Verify nested factors object |
| Positioning/sentiment handling | Test fallback behaviors |

---

## Database Schema

### Primary Table
**Table**: `stock_scores`

| Column | Type | Lines Used | Purpose |
|--------|------|-----------|---------|
| composite_score | DECIMAL(5,2) | 1594-1621 | Main ranking metric |
| momentum_score | DECIMAL(5,2) | 1215 | Technical momentum |
| trend_score | DECIMAL(5,2) | 1254 | Price trend |
| value_score | DECIMAL(5,2) | 1316 | Valuation |
| quality_score | DECIMAL(5,2) | 1384 | Profitability/strength |
| growth_score | DECIMAL(5,2) | 1448 | Growth rates |
| positioning_score | DECIMAL(5,2) | 1550 | Market positioning |
| sentiment_score | DECIMAL(5,2) | 1577 | Analyst/news sentiment |
| stability_score | DECIMAL(5,2) | 1208 | Risk consistency |
| value_inputs | JSONB | 1272-1320 | Percentile ranks (PE, PB, PS, PEG) |

### Supporting Tables
- `quality_metrics` - ROE, ROA, margins, debt ratios
- `growth_metrics` - Revenue/earnings growth, margins
- `momentum_metrics` - Multi-timeframe momentum, SMA ratios
- `risk_metrics` - Volatility, drawdown, beta
- `positioning_metrics` - Institutional %, insider %, short %
- `price_daily` - Price data and changes
- `technical_data_daily` - RSI, MACD, SMAs

---

## API Response Structure

### List Endpoint Response (`GET /scores`)
```javascript
{
  success: boolean,
  data: {
    stocks: [
      {
        symbol: string,
        company_name: string,
        sector: string,
        composite_score: number (0-100),
        momentum_score: number,
        value_score: number,
        quality_score: number,
        growth_score: number,
        positioning_score: number,
        sentiment_score: number,
        stability_score: number,
        // ... additional fields
        momentum_components: { short_term, medium_term, longer_term, ... },
        positioning_components: { institutional_ownership, insider_ownership, ... },
        value_inputs: { stock_pe, stock_pb, stock_ps, ... },
        quality_inputs: { return_on_equity_pct, return_on_assets_pct, ... },
        growth_inputs: { revenue_growth_3y_cagr, eps_growth_3y_cagr, ... },
        momentum_inputs: { momentum_12m_1, momentum_6m, ... },
        risk_inputs: { volatility_12m_pct, volatility_risk_component, ... }
      }
    ],
    viewType: "list"
  },
  summary: {
    totalStocks: number,
    averageScore: number,
    topScore: number,
    scoreRange: string
  },
  metadata: {
    dataSource: "stock_scores_real_table",
    factorAnalysis: "seven_factor_scoring_system"
  }
}
```

### Detail Endpoint Response (`GET /scores/:symbol`)
```javascript
{
  success: boolean,
  data: {
    symbol: string,
    composite_score: number,
    factors: {
      momentum: { score: number, components: {...}, inputs: {...} },
      value: { score: number, inputs: {...} },
      quality: { score: number, inputs: {...} },
      growth: { score: number, inputs: {...} },
      positioning: { score: number, components: {...} },
      sentiment: { score: number },
      consistency: { score: number, inputs: {...} }
    },
    performance: { priceChange1d, priceChange5d, ... },
    // ... additional fields
    stability_inputs: { volatility_12m_pct, max_drawdown_52w_pct, beta }
  },
  metadata: {
    dataSource: "stock_scores_real_table",
    factorAnalysis: "seven_factor_scoring_system",
    calculationMethod: "loadstockscores_algorithm"
  }
}
```

---

## Key Calculation Line References

### Momentum Score Calculation Path
```
1. Load price data ........................ ~1100-1130
2. Calculate RSI, MACD ................... 1140-1160
3. Calculate intraweek confirmation ..... 1165-1175
4. Calculate short-term momentum ........ 1185-1195
5. Calculate medium-term momentum ....... 1195-1205
6. Calculate stability score ............ 1175-1210
7. Scale to 100 ......................... 1215-1216
```

### Composite Score Calculation Path
```
1. Calculate all 7 factor scores ........ 1140-1551
2. Check if positioning available ....... 1600
3. If available: weighted average (7) .. 1601-1609
4. If not available: weighted average (6) 1614-1621
5. Clamp to 0-100 ....................... 1626-1628
6. Return score dictionary .............. 1629-1660
```

---

## Important Line Numbers for Modifications

| Need to Change | Location | Priority |
|----------------|----------|----------|
| Factor weights | `loadstockscores.py:1601-1621` | High - Changes entire ranking |
| Component weights within factors | Individual factor calculation sections | High |
| Percentile calculation | `loadstockscores.py:324-330` | High |
| Inversion logic | `loadstockscores.py:1357-1380` | High - Risk of score reversal |
| Fallback values | `loadstockscores.py:1326, 1392, 1456` | Medium - Affects missing data handling |
| Score clamping | `loadstockscores.py:1626-1628` | Low - Safety measure |
| Interpretation thresholds | `factorScoring.js:427-434` | Low - UI only |


# Stock Scoring/Ranking Logic - Comprehensive Analysis

## Overview
The system uses a **7-factor weighted composite scoring model** that calculates stock scores on a 0-100 scale. Scores are calculated in Python (backend) and retrieved by both the backend API and frontend dashboard.

---

## 1. Core Scoring Architecture

### Entry Points
- **Backend Python**: `/home/stocks/algo/loadstockscores.py` - Main scoring engine
- **Backend API**: `/home/stocks/algo/webapp/lambda/routes/scores.js` - Retrieves scores from database
- **Frontend Display**: `/home/stocks/algo/webapp/frontend/src/pages/ScoresDashboard.jsx` - Displays scores
- **JS Scoring Engine**: `/home/stocks/algo/webapp/lambda/utils/factorScoring.js` - Alternative scoring logic

### Score Types
1. `composite_score` - Overall 7-factor weighted average (0-100)
2. `momentum_score` - Technical momentum (0-100)
3. `trend_score` - Price trend and MA alignment (0-100)
4. `value_score` - Valuation metrics (0-100)
5. `quality_score` - Profitability and financial health (0-100)
6. `growth_score` - Revenue and earnings growth (0-100)
7. `positioning_score` - Institutional/insider activity (0-100)
8. `sentiment_score` - Analyst ratings and market sentiment (0-100)
9. `stability_score` - Risk and consistency (0-100)

---

## 2. Detailed Scoring Methodology

### **Factor 1: Momentum Score (18.95% weight, if positioning present)**

**Location**: `loadstockscores.py` lines 1140-1216

**Components (85-point total, scaled to 100)**:
1. **Intraweek Confirmation** (10 pts): Price change direction consistency
   - RSI > 50 AND price_change_1d > 0 = +10 pts
   - RSI < 50 AND price_change_1d < 0 = +10 pts
   - Otherwise = 0 pts

2. **Short-term Momentum** (25 pts): 5-10 day price movement
   - Price_change_5d percentile within full universe
   - Ranked 0-25 based on percentile position

3. **Medium-term Momentum** (25 pts): 20-60 day price movement
   - Price_change_30d percentile within full universe
   - Ranked 0-25 based on percentile position

4. **Longer-term Momentum** (15 pts): 60-120 day price movement
   - Price_change_90d (implied) percentile
   - Ranked 0-15 based on percentile position

5. **Stability Score** (10 pts): Consistency across timeframes
   - Counts agreement among RSI, MACD, price momentum signals
   - 3/3 agreement = 10 pts (strong signal)
   - 2/3 agreement = 6-8 pts (mostly aligned)
   - 1/3 agreement = 3-5 pts (mixed signals)

**Normalization**: `momentum_score = (raw_momentum_score / 85) * 100`

---

### **Factor 2: Trend Score (13.68% weight)**

**Location**: `loadstockscores.py` lines 1218-1262

**Components (100-point scale)**:

1. **Price Position Score** (50 pts):
   - `position_score = 25 + (price_vs_sma20 * 0.5) + (price_vs_sma50 * 0.3)`
   - Clamped to 0-50 range

2. **MA Alignment Bonus/Penalty** (25 pts):
   - Bullish (SMA20 > SMA50): +15 pts
     - If price above SMA20: +10 more pts (total +25)
   - Bearish (SMA50 > SMA20): -15 pts
     - If price below SMA20: -10 more pts (total -25)

3. **Multi-timeframe Momentum** (25 pts):
   - All positive (1d, 5d, 30d > 0) = 25 pts
   - All negative (1d, 5d, 30d < 0) = 0 pts
   - 5d & 30d positive = 18.75 pts
   - 5d & 30d negative = 6.25 pts
   - Other = 12.5 pts

**Fallback** (if SMA data missing): Use price changes only (40-60 base)

---

### **Factor 3: Value Score (13.68% weight)**

**Location**: `loadstockscores.py` lines 1269-1327

**Source**: Percentile ranks from `stock_scores.value_inputs` JSONB (populated by `loadvaluemetrics.py`)

**Components (100-point scale, weighted)**:
1. P/E Ratio Percentile × 35% (35 pts max)
2. P/B Ratio Percentile × 25% (25 pts max)
3. P/S Ratio Percentile × 20% (20 pts max)
4. PEG Ratio Percentile × 20% (20 pts max)

**Formula**:
```
value_components = [
  (pe_percentile / 100) * 35,      # 35% weight
  (pb_percentile / 100) * 25,      # 25% weight
  (ps_percentile / 100) * 20,      # 20% weight
  (peg_percentile / 100) * 20      # 20% weight
]
value_score = sum(value_components)  # 0-100 scale
```

**Normalization**: Inverted - lower valuation multiples = higher percentile = higher score

**Fallback**: Default to 50 if data missing

---

### **Factor 4: Quality Score (13.68% weight)**

**Location**: `loadstockscores.py` lines 1333-1393

**Source**: Percentile ranks from `quality_metrics` table

**Components (100-point scale)**:

1. **Profitability** (40 pts):
   - ROE percentile × 40% (16 pts)
   - ROA percentile × 30% (12 pts)
   - Gross Margin percentile × 30% (12 pts)

2. **Financial Strength** (30 pts):
   - Debt/Equity percentile (inverted - lower better) × 60% (18 pts)
   - Current Ratio percentile × 40% (12 pts)

3. **Earnings Quality** (20 pts):
   - FCF/Net Income percentile × 100% (20 pts)

4. **Stability** (10 pts):
   - Volatility percentile (inverted - lower better) × 100% (10 pts)

**Formula**:
```
quality_score = (profitability + strength + earnings_quality + stability)
             = max(0, min(100, score))
```

**Inversion Pattern**: 
- Lower debt/equity → higher percentile
- Lower volatility → higher percentile
- Inverted by: `-debt_to_equity` and `-volatility_30d` before percentile calculation

**Fallback**: Default to 50 if data missing

---

### **Factor 5: Growth Score (17.11% weight)**

**Location**: `loadstockscores.py` lines 1399-1457

**Source**: Percentile ranks from `growth_metrics` table

**Components (100-point scale)**:

1. **Revenue Growth** (25 pts): TTM revenue growth percentile × 25%

2. **Earnings Growth** (30 pts): TTM earnings growth percentile × 30%

3. **Earnings Acceleration** (20 pts):
   - (Quarterly growth - Annual growth) percentile × 20%
   - Positive = accelerating growth (better)

4. **Margin Expansion** (15 pts):
   - Gross Margin Growth percentile × 50% (7.5 pts)
   - Operating Margin Growth percentile × 50% (7.5 pts)

5. **Sustainable Growth** (10 pts):
   - ROE × (1 - payout_ratio) percentile × 10%

**Formula**:
```
growth_score = (revenue_growth + earnings_growth + earnings_accel + 
                margin_expansion + sustainable_growth)
            = max(0, min(100, score))
```

**Fallback**: Default to 50 if data missing

---

### **Factor 6: Stability Score (12.63% weight - NEW)**

**Location**: `loadstockscores.py` lines 1175-1208

**Components**: Risk-adjusted volatility metrics

**Purpose**: Prevents high-volatility stocks from scoring high despite good other metrics

**Formula**: Based on consistency of momentum signals and price stability

**Fallback**: Default to 50 if data missing

---

### **Factor 7: Positioning Score (10.26% weight)**

**Location**: `loadstockscores.py` lines 1459-1551

**NO FALLBACK** - If positioning data missing, score is NULL and composite is recalculated without this factor

**Components (100-point scale)**:

1. **Institutional Ownership** (25 pts):
   - 40-70%: 25 pts (optimal)
   - 30-40%: 22 pts
   - 70-80%: 20 pts
   - 20-30%: 16 pts
   - 80-90%: 14 pts (crowded)
   - <20%: 10 pts
   - >90%: 7 pts (very crowded)

2. **Insider Ownership** (20 pts):
   - ≥15%: 20 pts (very strong)
   - 10-15%: 18 pts
   - 5-10%: 15 pts (good)
   - 1-5%: 10 pts
   - <1%: 5 pts

3. **Short Interest** (20 pts):
   - <2% short: 20 pts
   - 2-5%: 15 pts
   - 5-10%: 8 pts
   - 10-20%: 3 pts
   - >20%: 0 pts (short squeeze risk)

4. **Accumulation/Distribution Rating** (25 pts):
   - Direct conversion of acc_dist_rating (0-25 scale)

5. **Institution Count** (10 pts):
   - Percentile of number of institutions holding stock

---

### **Factor 8: Sentiment Score (5% weight - special handling)**

**Location**: `loadstockscores.py` lines 1553-1577

**Note**: Sentiment is calculated but currently EXCLUDED from composite calculation (5% redistributed to other factors)

**Components**:
1. Analyst ratings: (score - 1) / 4 * 50 (scales 1-5 to 0-50)
2. News sentiment: (sentiment_score_raw - 0.5) * 50 (adds ±25 pts)
3. News count bonus: min(10, news_count * 0.5) pts

---

## 3. Composite Score Calculation

**Location**: `loadstockscores.py` lines 1594-1621

### **Weight Distribution**:

**When positioning_score IS available** (7 factors):
```
composite = momentum     * 0.1895 +
            trend        * 0.1368 +
            growth       * 0.1711 +
            value        * 0.1368 +
            quality      * 0.1368 +
            stability    * 0.1263 +
            positioning  * 0.1026
            
Total: 100% (Sentiment: excluded)
```

**When positioning_score IS NULL** (6 factors, repositioning redistributed):
```
composite = momentum     * 0.2126 +
            trend        * 0.1532 +
            growth       * 0.1917 +
            value        * 0.1532 +
            quality      * 0.1532 +
            stability    * 0.1416
            
Total: 100% (Positioning: 10.26% weight redistributed proportionally)
```

---

## 4. Normalization & Inversion Details

### **Normalization Methods**:

1. **Percentile-based** (most common):
   - Extract metric values across universe
   - Sort and find percentile rank of each stock
   - Convert to 0-1 scale (percentile / 100)
   - Apply weight to get component score

2. **Absolute ranges** (older fallback in JS):
   - Predefined score ranges per metric
   - Example P/E ranges: 0-10→90%, 10-15→80%, etc.
   - Returns 0-1 normalized score

3. **Sigmoid function** (JS fallback):
   - `normalized = 1 / (1 + exp(-value * 0.1))`
   - Handles unknown factors smoothly

### **Inversion Pattern**:

**Inverted metrics** (lower is better):
- P/E, P/B, P/S, PEG ratios
- Debt/Equity ratio
- Volatility
- Short interest %

**Inversion method**: 
```python
# For debt_to_equity in Quality Score:
debt_percentile = calculate_percentile_rank(
    -stock_debt_to_equity,
    [-d for d in quality_metrics.get('debt_to_equity', [])]
)
# Negation makes higher percentile = lower actual debt ratio
```

---

## 5. Data Flow & Dependencies

### **Input Data Sources**:

1. **Price Data** (`price_daily` table):
   - current_price, price_change_1d/5d/30d
   - volatility_30d
   - volume_avg_30d

2. **Technical Data** (`technical_data_daily` table):
   - RSI, MACD
   - SMA_20, SMA_50
   - Multi-timeframe momentum

3. **Fundamental Data** (`key_metrics` table):
   - PE ratio, PB ratio, earnings growth
   - Free cash flow, dividend yield

4. **Quality Metrics** (`quality_metrics` table):
   - ROE, ROA, margins
   - Debt/Equity, liquidity ratios
   - Earnings surprise, stability metrics

5. **Growth Metrics** (`growth_metrics` table):
   - Revenue/earnings growth (TTM & YoY)
   - Margin trends
   - Sustainable growth rate

6. **Momentum Metrics** (`momentum_metrics` table):
   - 3m/6m/12m momentum
   - Price vs SMA ratios
   - 52-week highs

7. **Risk Metrics** (`risk_metrics` table):
   - Volatility (12-month)
   - Max drawdown
   - Beta

8. **Positioning Metrics** (`positioning_metrics` table):
   - Institutional/insider ownership %
   - Short interest %
   - Institution count

9. **Value Inputs** (JSONB in `stock_scores` table):
   - Percentile ranks: pe_percentile_rank, pb_percentile_rank, etc.
   - Populated by `loadvaluemetrics.py`

### **Calculation Flow**:
```
loadstockscores.py
  ↓
For each stock symbol:
  ├─ Calculate momentum_score (from price_daily, technical_data_daily)
  ├─ Calculate trend_score (from price data + SMAs)
  ├─ Calculate value_score (from stock_scores.value_inputs percentiles)
  ├─ Calculate quality_score (from quality_metrics percentiles)
  ├─ Calculate growth_score (from growth_metrics percentiles)
  ├─ Calculate positioning_score (from positioning_metrics)
  ├─ Calculate sentiment_score (from analyst/news data)
  ├─ Calculate stability_score (from volatility/risk metrics)
  └─ Calculate composite_score (weighted average)
  ↓
Store in stock_scores table
  ↓
API retrieves via /scores endpoint
  ↓
Frontend displays in ScoresDashboard
```

---

## 6. Score Storage & Retrieval

### **Backend Storage** (Python):
- **File**: `/home/stocks/algo/loadstockscores.py`
- **Trigger**: Daily scheduled execution
- **Database**: PostgreSQL `stock_scores` table
- **Fields**: All 9 score types + supporting metrics

### **Backend Retrieval** (Node.js API):
- **File**: `/home/stocks/algo/webapp/lambda/routes/scores.js`
- **Endpoint**: 
  - `GET /scores` - List all stocks with scores
  - `GET /scores/:symbol` - Detailed scores for one stock
- **Query**: Joins stock_scores with quality/growth/momentum/risk/positioning tables
- **Response**: Flat structure + nested factor breakdown

### **Frontend Display** (React):
- **File**: `/home/stocks/algo/webapp/frontend/src/pages/ScoresDashboard.jsx`
- **Features**:
  - Sort by composite score
  - Filter by score ranges
  - Search by symbol/company name
  - Show 7-factor breakdown charts

---

## 7. Key Metrics Definitions

### **Percentile Rank Calculation**:
```python
def calculate_percentile_rank(value, all_values):
    """Calculate percentile rank of value in all_values"""
    valid_values = [v for v in all_values if v is not None]
    valid_values.sort()
    count_less = sum(1 for v in valid_values if v < value)
    return (count_less / len(valid_values)) * 100
```

### **Score Interpretation** (JS engine fallback):
- ≥80: Excellent
- 70-79: Good
- 60-69: Above Average
- 40-59: Average
- 30-39: Below Average
- <30: Poor

---

## 8. Important Implementation Details

### **Edge Cases & Fallbacks**:

1. **Missing Data**:
   - Momentum: Can be calculated if have RSI + price changes
   - Trend: Falls back to price changes only
   - Value/Quality/Growth: Default to neutral 50 if insufficient data
   - Positioning: Entire score becomes NULL (recalculates composite without it)
   - Sentiment: Defaults to 50 (neutral)

2. **Clamping**:
   - All scores clamped to 0-100 range
   - Database field: DECIMAL(5,2) supports max 999.99

3. **Weighting Distribution**:
   - Weights sum to exactly 100% (or redistributed if positioning missing)
   - No factor receives <10% when all present
   - Momentum gets highest weight (18.95%)
   - Positioning gets lowest (10.26%)

### **Known Issues/Considerations**:

1. **Sentiment excluded**: Currently not included in composite (5% weight redistributed)
2. **Stability score new**: Recently added to prevent volatility bias
3. **Positioning has no fallback**: NULL if all positioning data missing
4. **Percentile recalculated daily**: Can shift significantly with market changes
5. **Database schema**: Value inputs stored as JSONB (flexible but requires parsing)

---

## 9. Files & Code Locations

| Component | File | Key Functions |
|-----------|------|-------------------|
| Main scoring engine | `/home/stocks/algo/loadstockscores.py` | `calculate_composite_score()` |
| Score retrieval API | `/home/stocks/algo/webapp/lambda/routes/scores.js` | `GET /scores`, `GET /scores/:symbol` |
| Frontend display | `/home/stocks/algo/webapp/frontend/src/pages/ScoresDashboard.jsx` | `ScoresDashboard` component |
| JS fallback engine | `/home/stocks/algo/webapp/lambda/utils/factorScoring.js` | `FactorScoringEngine` class |
| Value metrics input | `/home/stocks/algo/loadvaluemetrics.py` | Populates percentile_rank fields |
| Growth metrics input | `/home/stocks/algo/loadgrowthmetrics.py` | Populates growth data |
| Quality metrics input | `/home/stocks/algo/loadqualitymetrics.py` | Populates quality data |
| Risk metrics input | `/home/stocks/algo/loadriskmetrics.py` | Populates risk data |

---

## 10. Testing & Validation

### **Test Files**:
- `/home/stocks/algo/webapp/lambda/tests/unit/utils/factorScoring.test.js`
- `/home/stocks/algo/webapp/lambda/tests/unit/routes/scores.test.js`
- `/home/stocks/algo/webapp/lambda/tests/integration/routes/scores.integration.test.js`

### **Key Validations**:
- Composite score: 0-100 range
- All components < 100
- Weights sum to 100%
- No null values in final composite

---

## Summary

The scoring system is **multi-layered, percentile-based, and weighted**:
- **7 primary factors** contribute to composite score
- **Percentile-based normalization** ensures relative market comparisons
- **Automatic inversion** handles "lower is better" metrics
- **Graceful fallbacks** maintain scores even with missing data
- **Daily recalculation** keeps scores current with market changes
- **No single metric dominates** (max 18.95% for momentum)

The design emphasizes **stability, growth, and value** equally while incorporating **technical momentum** and **market positioning** as supporting factors.


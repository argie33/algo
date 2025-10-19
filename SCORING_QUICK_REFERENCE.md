# Stock Scoring - Quick Reference

## 7-Factor Composite Score Model (0-100 scale)

### Score Weights (When All 7 Factors Available)
```
Momentum Score ................. 18.95%  (Technical momentum)
Trend Score ..................... 13.68%  (Price trend + MA alignment)
Growth Score .................... 17.11%  (Revenue/earnings growth)
Value Score ..................... 13.68%  (Valuation ratios)
Quality Score ................... 13.68%  (Profitability + strength)
Stability Score ................. 12.63%  (Risk consistency) - NEW
Positioning Score ............... 10.26%  (Institutional/insider ownership)
────────────────────────────────────────────
TOTAL ........................... 100%
Note: Sentiment Score (5%) currently excluded from composite
```

### When Positioning is Missing
- Positioning's 10.26% weight redistributed proportionally
- New weights: Momentum 21.26%, Trend 15.32%, Growth 19.17%, Value 15.32%, Quality 15.32%, Stability 14.16%

---

## Factor Calculation Details

### 1. MOMENTUM SCORE (18.95%)
**Components (85 pts total, scaled to 100)**
- Intraweek confirmation (RSI + price alignment): 10 pts
- Short-term momentum (5d change percentile): 25 pts
- Medium-term momentum (30d change percentile): 25 pts
- Long-term momentum (90d change percentile): 15 pts
- Stability/consistency: 10 pts

**Data Source**: price_daily, technical_data_daily
**Inversion**: None

### 2. TREND SCORE (13.68%)
**Components**
- Price vs SMA position: 50 pts
- MA alignment (SMA20 vs SMA50): 25 pts
- Multi-timeframe momentum (1d/5d/30d agreement): 25 pts

**Data Source**: technical_data_daily (SMA_20, SMA_50), price_daily
**Inversion**: None

### 3. VALUE SCORE (13.68%)
**Components (Percentile-based)**
- P/E ratio percentile: 35%
- P/B ratio percentile: 25%
- P/S ratio percentile: 20%
- PEG ratio percentile: 20%

**Data Source**: stock_scores.value_inputs (JSONB)
**Inversion**: YES - Lower valuation = higher percentile = higher score

### 4. QUALITY SCORE (13.68%)
**Components (Percentile-based)**
- Profitability (ROE, ROA, margins): 40 pts
- Financial strength (Debt/Equity, current ratio): 30 pts
- Earnings quality (FCF/NI): 20 pts
- Stability (Volatility): 10 pts

**Data Source**: quality_metrics table
**Inversion**: YES - Lower debt, lower volatility = higher score

### 5. GROWTH SCORE (17.11%)
**Components (Percentile-based)**
- Revenue growth (TTM): 25 pts
- Earnings growth (TTM): 30 pts
- Earnings acceleration (Q vs annual): 20 pts
- Margin expansion (gross + operating): 15 pts
- Sustainable growth (ROE × retention): 10 pts

**Data Source**: growth_metrics table
**Inversion**: None - Higher growth = higher score

### 6. STABILITY SCORE (12.63%)
**Components**
- Risk-adjusted volatility metrics
- Consistency of momentum signals

**Data Source**: risk_metrics, momentum_metrics
**Inversion**: YES - Lower volatility = higher score
**Purpose**: Prevent high-volatility stocks from scoring high

### 7. POSITIONING SCORE (10.26%)
**Components**
- Institutional ownership (40-70% optimal): 25 pts
- Insider ownership (higher better): 20 pts
- Short interest (lower better): 20 pts
- Accumulation/Distribution rating: 25 pts
- Institution count (percentile): 10 pts

**Data Source**: positioning_metrics table
**Inversion**: Partial (short interest, acc/dist inverted)
**Fallback**: None - if all positioning data missing, score is NULL

---

## Normalization Methods

### PERCENTILE-BASED (Primary)
```
percentile = (count of values < stock_value) / total_values * 100
score = (percentile / 100) * component_weight
```

### ABSOLUTE RANGES (JS Fallback)
Example P/E ranges:
- 0-10: 90 points
- 10-15: 80 points
- 15-20: 70 points
- etc.

### SIGMOID FUNCTION (Unknown factors)
```
sigmoid = 1 / (1 + e^(-value * 0.1))
score = sigmoid or (1 - sigmoid) if inverted
```

---

## Inversion Pattern Summary

### Metrics Where LOWER is BETTER (Inverted):
- ✓ P/E, P/B, P/S, PEG ratios
- ✓ Debt/Equity ratio
- ✓ Volatility (12-month)
- ✓ Short interest %
- ✓ Max drawdown %

### Metrics Where HIGHER is BETTER (Not Inverted):
- ✓ Revenue growth %
- ✓ Earnings growth %
- ✓ ROE, ROA, margins
- ✓ Current/Quick ratios
- ✓ Institutional ownership (optimal 40-70%)
- ✓ Insider ownership %
- ✓ Analyst ratings

---

## Composite Score Formula

### Full Formula (All Factors):
```
composite = 
  momentum * 0.1895 +
  trend * 0.1368 +
  growth * 0.1711 +
  value * 0.1368 +
  quality * 0.1368 +
  stability * 0.1263 +
  positioning * 0.1026

Then clamp(composite, 0, 100)
```

### Fallback Formula (Positioning NULL):
```
composite = 
  momentum * 0.2126 +
  trend * 0.1532 +
  growth * 0.1917 +
  value * 0.1532 +
  quality * 0.1532 +
  stability * 0.1416

Then clamp(composite, 0, 100)
```

---

## Data Dependencies

```
INPUT TABLES:
├─ price_daily ..................... Current price, daily changes, volume
├─ technical_data_daily ............ RSI, MACD, SMAs
├─ quality_metrics ................. ROE, ROA, margins, debt ratios
├─ growth_metrics .................. Revenue/earnings growth, margin trends
├─ momentum_metrics ................ Multi-timeframe momentum, price vs SMA
├─ risk_metrics ..................... Volatility, max drawdown, beta
├─ positioning_metrics ............ Institutional %, insider %, short %
└─ stock_scores.value_inputs ...... JSONB with percentile ranks

OUTPUT:
└─ stock_scores table ............. composite_score + 8 factor scores
                                    + all supporting metrics
```

---

## Score Interpretation Guide

| Score Range | Level | Interpretation |
|-------------|-------|-----------------|
| 80-100 | Excellent | Top performer, strong across metrics |
| 70-79 | Good | Above average, solid fundamentals |
| 60-69 | Above Avg | Better than market average |
| 40-59 | Average | Neutral, mixed signals |
| 30-39 | Below Avg | Concerning indicators |
| 0-29 | Poor | Weak across most metrics |

---

## Calculation Flow

```
1. Load stock data from price_daily, technical_data, fundamentals
   ↓
2. For each stock:
   a) Calculate momentum_score (RSI + price changes)
   b) Calculate trend_score (MA alignment + momentum)
   c) Calculate value_score (PE, PB, PS, PEG percentiles)
   d) Calculate quality_score (profitability, debt, margins percentiles)
   e) Calculate growth_score (revenue, earnings, acceleration percentiles)
   f) Calculate positioning_score (institutional, insider, short %)
   g) Calculate sentiment_score (analyst + news)
   h) Calculate stability_score (volatility, consistency)
   ↓
3. Apply weighted average formula
   ↓
4. Clamp to 0-100 range
   ↓
5. Store in stock_scores table
   ↓
6. API retrieves and returns to frontend
```

---

## Key Files

| File | Purpose | Key Function |
|------|---------|---------------|
| `/home/stocks/algo/loadstockscores.py` | Main scoring engine | `calculate_composite_score()` |
| `/home/stocks/algo/webapp/lambda/routes/scores.js` | API endpoint | `GET /scores` |
| `/home/stocks/algo/webapp/frontend/src/pages/ScoresDashboard.jsx` | Display layer | ScoresDashboard component |
| `/home/stocks/algo/webapp/lambda/utils/factorScoring.js` | JS scoring engine | FactorScoringEngine class |
| `/home/stocks/algo/loadvaluemetrics.py` | Value metric input | Populates percentile ranks |

---

## Important Notes

1. **Sentiment Currently Excluded**: Sentiment score is calculated (5%) but NOT included in composite (redistributed)

2. **Stability is NEW**: Recently added to prevent volatile stocks from scoring high

3. **Positioning has NO Fallback**: If all positioning data missing, composite uses 6-factor model instead

4. **Percentiles Recalculated Daily**: Market-relative scoring can shift based on universe performance

5. **Score Clamping**: All scores clamped to 0-100 regardless of calculation results

6. **All Weights Normalized**: Sum exactly to 100% (or redistribute if positioning missing)

---

## Example: How a Stock Gets Scored

**Stock: APPLE Inc (AAPL)**

```
1. MOMENTUM = 72
   (Strong: RSI 65, +5% in 5d, +8% in 30d)

2. TREND = 68
   (Good: Price above SMA20 & SMA50, bullish alignment)

3. VALUE = 45
   (Fair: PE 28 (low percentile), PB 35, PS 25, PEG 18)

4. QUALITY = 78
   (Strong: ROE 85th %-ile, debt low, FCF good)

5. GROWTH = 82
   (Excellent: Revenue +12%, Earnings +15%, margins +3%)

6. POSITIONING = 55
   (Moderate: Institutional 65%, insider 2%, short 1%)

7. STABILITY = 70
   (Good: Volatility controlled, consistent signals)

Composite = 72*0.1895 + 68*0.1368 + 82*0.1711 + 45*0.1368 
          + 78*0.1368 + 70*0.1263 + 55*0.1026
          = 13.6 + 9.3 + 14.0 + 6.2 + 10.7 + 8.8 + 5.6
          = 68.2

RESULT: AAPL scores 68.2 (Above Average)
```


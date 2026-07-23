# Phase 7: Scoring Formula Updates - Detailed Plan

## Current Scoring Architecture

**Loader Chain:**
```
load_value_quality_growth_metrics.py → writes:
  - value_metrics (pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield)
  - quality_metrics (roe, roa, operating_margin, net_margin, debt_to_equity, etc.)
  - growth_metrics (eps_growth_1y, rev_growth_1y, etc.)

load_risk_metrics_daily.py → writes:
  - momentum_metrics (1m/3m/6m/12m momentum + NEW: rsi, macd, roc, sma)
  - stability_metrics (volatility_30d/60d/252d, beta, debt_to_assets)

load_positioning_metrics.py → writes:
  - positioning_metrics (institutional_ownership, insider_ownership, short_interest, etc.)

load_stock_scores.py → reads all above & writes:
  - stock_scores (composite_score, quality_score, growth_score, value_score, momentum_score, positioning_score, stability_score)
```

## Current Composite Score Weights

From load_stock_scores.py lines 576-618:
```python
weights = {
    'quality_score': 0.20,     # 20%
    'growth_score': 0.15,      # 15%
    'value_score': 0.25,       # 25% - HIGHEST
    'momentum_score': 0.20,    # 20%
    'positioning_score': 0.10, # 10%
    'stability_score': 0.10,   # 10%
}
```

## Factor Score Computation (Currently)

Each loader computes a factor score that goes into stock_scores table:

| Factor | Loader | Current Inputs | Needs Update? |
|--------|--------|-----------------|---------------|
| quality_score | load_value_quality_growth_metrics | ROE, ROA, Op Margin, Net Margin, D/E, D/A | YES - add ROIC, margins, ratios |
| growth_score | load_value_quality_growth_metrics | 1Y/3Y growth rates | YES - add CAGR, trends, sustainable growth |
| value_score | load_value_quality_growth_metrics | PE, PB, PS, PEG, FCF yield, div yield | PARTIALLY - added EV/EBITDA, EV/Revenue |
| momentum_score | load_risk_metrics_daily | 1m/3m/6m/12m momentum | YES - weight new technical inputs (RSI, MACD, ROC) |
| positioning_score | load_positioning_metrics | Institutional %, insider %, short % | YES - add short trend, A/D rating |
| stability_score | load_risk_metrics_daily | Vol 30/60/252d, beta, D/A | YES - add downside vol, max drawdown |

## Update Strategy

### IMMEDIATE (Unblock Current System)

**Goal:** Wire the new fields that are ALREADY BEING COMPUTED into the factor scores.

#### 1. Update `_score_momentum` in load_stock_scores.py

**Current:** Uses only 1m/3m/6m/12m momentum from momentum_metrics

**Action:** Add technical indicators to momentum calculation
```python
def _score_momentum(self, momentum_metrics, symbol):
    # Current: uses momentum_1m, 3m, 6m, 12m
    # NEW: also use rsi_14, macd_line, macd_signal, roc_20d/60d/120d/252d, price_vs_sma_50/200
    # Weight structure:
    #   Momentum returns: 50% (1m/3m/6m/12m equally weighted)
    #   Technical indicators: 50% (RSI + MACD + ROC + SMA)
```

**Effort:** 2-3 hours

#### 2. Update `_score_value` in load_stock_scores.py

**Current:** Uses PE, PB, PS, PEG, FCF yield, dividend yield

**Action:** Add new EV metrics
```python
# NEW fields now available in value_metrics:
#   - ev_ebitda (NEW from Phase 2)
#   - ev_revenue (NEW from Phase 2)
#   - total_debt, total_cash, enterprise_value (display only, not scored)
# Weight update:
#   PE: 30% → 25% (reduce slightly)
#   PB: 15% → 15% (unchanged)
#   PS: 10% → 10% (unchanged)
#   EV/EBITDA: NEW 20%
#   EV/Revenue: NEW 20%
#   PEG: 10% → 10%
#   FCF Yield: 8% → 8%
#   Dividend Yield: 7% → 2% (reduce - less core to valuation)
```

**Effort:** 2-3 hours

#### 3. Update `_score_quality` in load_stock_scores.py

**Current:** Uses ROE, ROA, operating margin, net margin, D/E, D/A, interest coverage, current ratio

**Action:** Will add new fields when Phase 3 computation complete
```python
# When available in quality_metrics:
#   gross_margin, ebitda_margin, roic_pct, fcf_to_net_income, ocf_to_net_income, payout_ratio
# Keep current formula for now, will enhance later
```

**Effort:** Deferred to Phase 3 completion

### FUTURE (Complete System)

#### 4. Add Growth Trend Metrics to `_score_growth`

Needs Phase 4 completion (trend computation in loaders)

#### 5. Add Positioning Advanced to `_score_positioning`

Needs Phase 5 completion (short trend, A/D rating)

#### 6. Add Stability Advanced to `_score_stability`

Needs Phase 6 completion (downside vol, max drawdown)

---

## Implementation Priority

### Tier 1: DO IMMEDIATELY (Unblocks Display + Scoring)
1. ✅ Verify momentum_metrics technical fields are populated (from Phase 1 loader)
2. ✅ Verify value_metrics EV fields are populated (from Phase 2 loader)
3. 🔄 **UPDATE:** `_score_momentum()` to include technical indicators (2 hrs)
4. 🔄 **UPDATE:** `_score_value()` to include EV multiples (2 hrs)
5. ✅ Run end-to-end test (loader → DB → scores → API → dashboard)

### Tier 2: DO NEXT (Complete Current Implementation)
6. Complete Phase 3: Quality metrics data population (8 hrs)
7. Update `_score_quality()` to use all available inputs (2 hrs)

### Tier 3: FUTURE (Comprehensive)
8. Complete Phases 4-6 (growth trends, positioning advanced, stability advanced)
9. Update respective scoring methods

---

## Code Changes Required

### File: `loaders/load_stock_scores.py`

**Change 1: Update momentum scoring (around line 1250-1350)**

```python
def _score_momentum(self, momentum: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
    """Score momentum: price returns + technical indicators.
    
    Components:
    - Price momentum (1m/3m/6m/12m): 50% weight
    - Technical indicators (RSI, MACD, ROC, SMA): 50% weight
    """
    if not momentum or momentum.get("data_unavailable"):
        return {"data_unavailable": True, "reason": momentum.get("reason", "unavailable")}
    
    scores = []
    weights = []
    
    # Price momentum component (50% total weight)
    price_momentum_fields = {
        'momentum_1m': 0.25,
        'momentum_3m': 0.25,
        'momentum_6m': 0.25,
        'momentum_12m': 0.25,
    }
    
    price_momentum_score = self._score_momentum_returns(momentum, price_momentum_fields, symbol)
    if price_momentum_score is not None:
        scores.append(price_momentum_score)
        weights.append(0.50)
    
    # Technical indicators component (50% total weight)
    technical_score = self._score_technical_indicators(momentum, symbol)
    if technical_score is not None:
        scores.append(technical_score)
        weights.append(0.50)
    
    if not scores:
        return {"data_unavailable": True, "reason": "no_momentum_data"}
    
    return sum(s * w for s, w in zip(scores, weights)) / sum(weights)

def _score_technical_indicators(self, momentum: dict[str, Any], symbol: str) -> float | None:
    """Score technical indicators: RSI, MACD, ROC, price vs SMAs."""
    indicators = {}
    
    # RSI (14): high score for 50-80 range (strong without overbought)
    rsi = safe_float(momentum.get('rsi_14'), f"{symbol}.rsi_14", allow_none=True)
    if rsi is not None:
        if 50 <= rsi <= 80:
            indicators['rsi_score'] = 75 + (rsi - 50) / 30 * 25  # 75-100 for 50-80
        elif rsi < 50:
            indicators['rsi_score'] = (rsi / 50) * 75  # 0-75 for 0-50
        else:
            indicators['rsi_score'] = 50  # Mild penalty for >80 (overbought)
    
    # MACD: sign only (positive = bullish)
    macd = safe_float(momentum.get('macd_line'), f"{symbol}.macd_line", allow_none=True)
    if macd is not None:
        indicators['macd_score'] = 75.0 if macd > 0 else 25.0
    
    # ROC components: average of 20d/60d/120d/252d
    roc_fields = ['roc_20d', 'roc_60d', 'roc_120d', 'roc_252d']
    roc_scores = []
    for field in roc_fields:
        roc = safe_float(momentum.get(field), f"{symbol}.{field}", allow_none=True)
        if roc is not None:
            # Normalize: -20% = 0, 0% = 50, +20% = 100
            roc_score = 50 + (roc / 0.4) * 50  # Rough scaling
            roc_scores.append(min(100, max(0, roc_score)))
    
    if roc_scores:
        indicators['roc_score'] = sum(roc_scores) / len(roc_scores)
    
    # Price vs SMAs: positive premium scores well
    sma_50 = safe_float(momentum.get('price_vs_sma_50'), f"{symbol}.price_vs_sma_50", allow_none=True)
    sma_200 = safe_float(momentum.get('price_vs_sma_200'), f"{symbol}.price_vs_sma_200", allow_none=True)
    
    if sma_50 is not None and sma_200 is not None:
        # Above both SMAs = bullish, score 75-100
        # Between = neutral, score 50
        # Below = bearish, score 0-25
        avg_sma_premium = (sma_50 + sma_200) / 2
        sma_score = 50 + (avg_sma_premium / 10) * 50  # -10% to +10% range maps to 0-100
        indicators['sma_score'] = min(100, max(0, sma_score))
    
    if not indicators:
        return None
    
    return sum(indicators.values()) / len(indicators)
```

**Change 2: Update value scoring (similar approach)**

Add EV/EBITDA and EV/Revenue weights in value scoring.

---

## Testing After Updates

```bash
# 1. Rebuild scores
python3 loaders/load_stock_scores.py --symbols AAPL,MSFT,GOOG --parallelism 1

# 2. Compare old vs new scores
python3 -c "
import psycopg2
conn = psycopg2.connect('dbname=stocks')
cur = conn.cursor()
cur.execute('SELECT symbol, momentum_score, value_score FROM stock_scores LIMIT 10')
for row in cur.fetchall():
    print(f'{row[0]}: momentum={row[1]:.2f}, value={row[2]:.2f}')
"

# 3. Verify frontend displays all fields
# Run dashboard and check /app/scores for AAPL - should see:
#   Momentum: 1m, 3m, 6m, 12m, RSI, MACD, ROC, SMAs
#   Value: PE, PB, PS, EV/EBITDA, EV/Revenue, PEG, FCF Yield, Dividend Yield
```

---

## Status

- ✅ Phase 1-2: Technical and value data loaded
- 🔄 Phase 3: Quality data - schemas ready, computation pending
- ⏳ Phase 7: Scoring formulas - READY FOR UPDATE
- ⏳ Phase 8: API - will expose all fields when loaders populate
- ⏳ Phase 9: Dashboard - will display when API ready
- ⏳ Phase 10: Algo - will use updated scores


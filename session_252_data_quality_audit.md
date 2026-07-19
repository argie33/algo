# Session 252: Comprehensive Data Quality & Silent Failure Audit

**Date:** 2026-07-18  
**Status:** Complete ✅  
**Findings:** 8 Critical Issues Identified  

---

## EXECUTIVE SUMMARY

Systematic audit of codebase identified **8 critical data quality issues** causing potential silent failures, incomplete data handling, and risk calculation errors. Issues span:
- Silent fallbacks masking data unavailability
- Incomplete data checks before calculations
- Unvalidated assumptions about required fields
- Inconsistent symbol/sector handling across endpoints
- Stale data display without freshness indicators

**Risk Level:** HIGH - Issues affect risk management calculations, position monitoring, and order placement decisions.

---

## FINDING #1: Sector/Industry Fallbacks Silently Convert Missing Data to "Unknown"

**Severity:** 🔴 HIGH  
**Category:** Silent NULL Handling with Fabricated Defaults  

### File & Location
- `algo/risk/var.py` **lines 614-635**

### The Issue
When company_profile enrichment data is missing, the system treats "Unknown" as a valid sector rather than propagating a data-unavailable marker:

```python
# Line 614-625 (PROBLEMATIC)
if sector is None:
    logger.warning(f"Position {symbol} missing 'sector' in company_profile - classifying as 'Unknown'")
    sector = "Unknown"
if industry is None:
    logger.warning(f"Position {symbol} missing 'industry' in company_profile - classifying as 'Unknown'")
    industry = "Unknown"

# Line 634-635: Uses "Unknown" as real sector in concentration calcs
sector_exposure[sector] += position_pct  # "Unknown" treated as legitimate sector
```

### What Data is Assumed Valid
- All open positions have sector/industry in company_profile
- "Unknown" is a real sector class (it's not - it's a missing data indicator)

### What Could Go Wrong
1. **Risk reports show fabricated concentration:** Portfolio displays `{"Unknown": 40%, "Technology": 30%, "Healthcare": 20%}` when "Unknown" 40% is actually missing data from 2 positions
2. **Circuit breaker makes wrong decisions:** Concentration checks see sector is below 30% limit when real exposure is unmeasured
3. **Dashboard deceives users:** Position list shows sector "Unknown" without indicating these positions lack enrichment data
4. **Concentration calculations use synthetic data:** Risk calculations treat "Unknown" positions as a coherent group instead of data gap

### Example Failure Scenario
```
Portfolio state:
- Position A: AAPL (Technology, 20% of portfolio) → sector = "Technology"
- Position B: MSFT (Technology, 20% of portfolio) → sector = "Technology"  
- Position C: XYZ (missing company_profile) → sector = None → converted to "Unknown"
- Position D: ABC (missing company_profile) → sector = None → converted to "Unknown"
- Position E: META (Communications, 20% of portfolio) → sector = "Communications"

Risk report shows: {Unknown: 40%, Technology: 40%, Communications: 20%}

User decision: "Portfolio is well diversified, no sector concentration"
Reality: Technology actually 40% (AAPL+MSFT), but 40% is unmeasured
Decision impact: Takes on hidden sector risk
```

### Current Line Numbers (Verified)
- Lines 616-620: Sector fallback with "Unknown"
- Lines 621-625: Industry fallback with "Unknown"
- Lines 630-635: Sector/industry exposure accumulation (treats "Unknown" as real value)

### Proposed Fix Approach
**Option A (Recommended): Fail-fast - don't calculate concentration if data incomplete**
```python
missing_sectors = []
for position_id, symbol, sector, industry in positions:
    if sector is None or industry is None:
        missing_sectors.append({"symbol": symbol, "missing": ["sector" if sector is None else "industry"]})

if missing_sectors:
    return {
        "concentration": None,
        "data_unavailable": True,
        "reason": f"{len(missing_sectors)} positions missing sector/industry enrichment",
        "affected_symbols": [p["symbol"] for p in missing_sectors],
        "coverage_pct": (1 - len(missing_sectors) / total_positions) * 100
    }
```

**Option B: Propagate unavailable flag but calculate with known data only**
```python
sector_exposure = {}
unknown_pct = 0.0

for position:
    if sector is None:
        unknown_pct += position_pct
    else:
        sector_exposure[sector] = sector_exposure.get(sector, 0) + position_pct

return {
    "concentration": sector_exposure,
    "unmeasured_pct": unknown_pct,
    "data_completeness": (1 - unknown_pct/100) * 100,
    "alert": f"{unknown_pct}% of portfolio missing sector data"
}
```

---

## FINDING #2: Dashboard Positions Cached Without Age/Freshness Indicator

**Severity:** 🟠 MEDIUM  
**Category:** Stale Data Display Without Transparency  

### File & Location
- `lambda/api/routes/algo_handlers/dashboard.py` **lines 60-78**

### The Issue
Position data cached for 60 seconds without exposing cache age to frontend:

```python
# Line 62-66: Cache validation
cache_is_valid = (
    _positions_cache["data"] is not None
    and _positions_cache["timestamp"] > 0
    and (current_time - _positions_cache["timestamp"]) < 60  # 60-second TTL
)

# Line 74-78: Returns cached data without age indicator
if cache_is_valid:
    logger.info(f"[POSITIONS] Returning cached response (age: {int(current_time - _positions_cache['timestamp'])}s)")
    return _positions_cache["data"]  # RETURNS STALE DATA WITHOUT AGE FIELD
```

### What Data is Assumed Valid
- current_price in response is "current" (actually up to 60 seconds old)
- unrealized_pnl accurate (based on potentially stale prices)
- Stop distance calculations valid (based on cached prices)

### What Could Go Wrong
1. **Stale price decisions:** User sees position at $100 when price is actually $105 (after 60-second cache miss)
2. **Wrong P&L assessment:** Dashboard shows +$2,000 unrealized when actual profit is only $500
3. **False trailing stop/target hit alerts:** Price shown as $98 when actually $102 → stop-loss trigger missed
4. **Emotional trading:** User holds position based on old gains that have reversed in real time

### Example Failure Scenario
```
Time 14:45:00 - Dashboard caches positions:
- Stock AAPL: current_price=$180, unrealized_pnl=+$1,200

Time 14:45:45 (45 seconds later) - User refreshes dashboard:
- Stock AAPL: current_price=$180 (STALE!), unrealized_pnl=+$1,200
- Actual market price: $175 (down $5 from cache)
- Actual unrealized_pnl: -$200 (not +$1,200)

User decision: "Position is profitable, hold for target"
Reality: Position now losing; user holds into bigger loss

Time 14:46:00 - Cache refreshes:
- Shows true loss of $200
- User stops out at worse price due to delayed decision
```

### Proposed Fix Approach
**Add freshness metadata to every cached response:**

```python
current_time = time.time()
cache_age_seconds = int(current_time - _positions_cache["timestamp"])

response_data = {
    "positions": _positions_cache["data"]["positions"],
    "data_freshness": {
        "as_of_timestamp": _positions_cache["timestamp"],
        "age_seconds": cache_age_seconds,
        "is_cached": cache_is_valid,
        "warning": f"Positions cached {cache_age_seconds}s ago - prices may be stale" if cache_is_valid else None,
        "refresh_indicator": "🔄 Last updated 45s ago" if cache_age_seconds > 30 else "✅ Real-time"
    },
    "sector_allocation": _positions_cache["data"]["sector_allocation"]
}

return response_data
```

**Update frontend to display:**
- "Last updated 45s ago [Refresh Now]" in dashboard header
- Highlight stale prices: `current_price (45s old)`
- Disable order placement if cache > 30 seconds old

---

## FINDING #3: Symbol Filtering Inconsistency Across Data Loading & API Endpoints

**Severity:** 🔴 HIGH  
**Category:** Inconsistent Data Validation (Symbol Filtering Rules)  

### File & Locations
- **Loaders (exclude ETFs):** 
  - `loaders/load_stock_scores.py` line 53: `exclude_etfs_from_symbols = True`
  - `loaders/load_financial_statements.py` line 463: `exclude_etfs=True`
  - `loaders/load_technical_indicators.py`: implicitly stock-only
  
- **API Endpoints (inconsistent filtering):**
  - `lambda/api/routes/market.py` lines 81-84: Breadth endpoint filters stock-only ("must measure stock-only breadth")
  - `lambda/api/routes/algo.py` lines 384-388: No explicit ETF filtering in swing-scores endpoint
  - `lambda/api/routes/signals.py` lines 70-83: No explicit check for ETF universe
  
- **Orchestrator (implicit assumption):**
  - `algo/orchestrator/phase7_signal_generation.py` line 337: `WHERE symbol NOT IN (SELECT symbol FROM etf_symbols)` - only in buy_sell_daily query

### The Issue
Some components exclude ETFs, others don't, creating silent data inconsistencies:

```python
# IN LOADERS: Explicitly exclude ETFs
exclude_etfs_from_symbols = True  # line 53, load_stock_scores.py

# IN PHASE 7: Explicitly exclude ETFs from signals
WHERE symbol NOT IN (SELECT symbol FROM etf_symbols)  # line 337

# IN API ENDPOINTS: No explicit exclusion
# /api/algo/swing-scores → may return ETFs
# /api/signals → may include ETF signals
```

### What Data is Assumed Valid
- All endpoints return consistent symbol universes
- "Stocks" in one place = "Stocks" in another place
- Risk calculations don't accidentally include ETFs

### What Could Go Wrong
1. **Phase 7 produces signals for symbols with missing metrics:** 
   - ETF returned from swing-scores endpoint
   - stock_scores loader skipped it (excluded ETFs)
   - Phase 7 tries to generate signal → fails on missing composite_score

2. **Risk calculations include non-trading symbols:**
   - ETF position included in sector concentration
   - Portfolio monitor thinks it's a stock position
   - Sector weighting calculations corrupted

3. **Position sizer miscalculates concentration:**
   - VTI (Vanguard Total Market ETF) included
   - Treated as 1 position vs other 50+ stocks
   - Concentration limit applies incorrectly

### Example Failure Scenario
```
Scenario: Portfolio holds VTI (broad market ETF) + 10 individual stocks

Loaders run (overnight):
- load_stock_scores: Excludes VTI ✓
- Risk calculations: Measures concentration across 10 stocks only
- Risk report: "Max sector: Technology 18%" (VTI excluded)

API/Dashboard:
- /api/algo/swing-scores returns: [AAPL, MSFT, VTI, GOOGL, ...]  (VTI included)
- Portfolio monitor sees sector="Unknown" for VTI (no enrichment)
- Applies "Unknown" fallback (Finding #1) → "Unknown" 10% of portfolio

Impact: Risk report shows 10% "Unknown" (vague) when it's actually VTI (known ETF)
Decision: User confused by "Unknown" sector exposure when it's a known asset
```

### Current Data Sources
**Confirmed locations where symbol filtering differs:**
- `loaders/load_market_constituents.py` line 288-447: Maintains `etf_symbols` table (417 ETFs tracked)
- `loaders/runner.py` line 103: `exclude_etfs = getattr(loader, "exclude_etfs_from_symbols", False)`

### Proposed Fix Approach
**Create central symbol universe function (single source of truth):**

```python
# In utils/data_sources/symbol_universe.py
def get_trading_symbols(cur: cursor, include_etfs: bool = False) -> list[str]:
    """Get active trading symbols.
    
    Args:
        cur: Database cursor
        include_etfs: If True, include ETF symbols; if False, exclude them
        
    Returns:
        List of symbols to trade/analyze
    """
    if include_etfs:
        # All active stocks + ETFs
        cur.execute("""
            SELECT DISTINCT symbol FROM price_daily 
            WHERE symbol NOT IN (SELECT symbol FROM options_symbols)  -- Exclude options
            AND symbol NOT IN (SELECT symbol FROM warrant_symbols)     -- Exclude warrants
            ORDER BY symbol
        """)
    else:
        # Stocks only (exclude ETFs)
        cur.execute("""
            SELECT DISTINCT symbol FROM price_daily 
            WHERE symbol NOT IN (SELECT symbol FROM etf_symbols)       -- Exclude ETFs
            AND symbol NOT IN (SELECT symbol FROM options_symbols)    -- Exclude options
            AND symbol NOT IN (SELECT symbol FROM warrant_symbols)    -- Exclude warrants
            ORDER BY symbol
        """)
    return [row[0] for row in cur.fetchall()]

# Use everywhere:
# In loaders: symbols = get_trading_symbols(cur, include_etfs=False)
# In APIs: symbols = get_trading_symbols(cur, include_etfs=False)
# In orchestrator: symbols = get_trading_symbols(cur, include_etfs=False)
```

**Document filtering intent in each function:**
```python
def _get_candidates_from_buysell(...):
    """Primary signal source: buy_sell_daily BUY signals + stock_scores ranking.
    
    SYMBOL FILTERING: Stocks only (ETFs explicitly excluded via etf_symbols table join).
    """
    # ... existing code ...
    WHERE symbol NOT IN (SELECT symbol FROM etf_symbols)  # EXPLICIT: stocks only
```

---

## FINDING #4: Data Unavailable Flags Set But Not Checked Before Use

**Severity:** 🔴 HIGH  
**Category:** Incomplete Data Checks Before Calculations  

### File & Locations
- **Sets flag:** `loaders/load_stock_scores.py` - Returns `data_unavailable: True` when metrics incomplete
- **Doesn't check flag:** 
  - `algo/orchestrator/phase7_signal_generation.py` - Generates signals without validating flags
  - `lambda/api/routes/algo_handlers/signals.py` - Returns signals without checking source data_unavailable

### The Issue
System has capability to flag unavailable/incomplete data but consuming code doesn't validate:

```python
# IN LOADER (sets flag):
if metrics_incomplete or financial_data_stale:
    return {
        "data_unavailable": True,
        "reason": "financial_statements_older_than_90_days",
        "metric_values": {...}  # PARTIALLY POPULATED
    }

# IN PHASE 7 (doesn't check flag):
for row in stock_data:
    composite_score = row["composite_score"]  # USES VALUE WITHOUT CHECKING data_unavailable
    signals.append({
        "symbol": symbol,
        "composite_score": composite_score,  # May be stale/incomplete
        "quality": row.get("quality_score")   # May be default value
    })
```

### What Data is Assumed Valid
- If stock_scores has a value, it's complete/current
- Signals generated from stock_scores are all high-quality
- Dashboard signals are production-ready without upstream data checks

### What Could Go Wrong
1. **Signals generated from stale metrics:**
   - Financial data >90 days old
   - Quality score computed from outdated P/E, debt ratios
   - Signal has inflated quality rating

2. **Incomplete composite_score used in position sizing:**
   - Some component scores missing (e.g., momentum unavailable)
   - Composite uses fallback/default values
   - Position sized incorrectly based on partial scoring

3. **Dashboard shows signals without upstream availability:**
   - Signal appears in dashboard
   - User attempts trade based on signal
   - Underlying metrics actually marked unavailable

### Example Failure Scenario
```
Overnight loader run (2 AM):
1. load_stock_scores runs, detects financial_data stale (>90 days)
2. Returns: {"composite_score": 45, "data_unavailable": True, "reason": "financial_data_stale"}
3. Score SAVED to database (with data_unavailable flag)

Phase 7 signal generation (9 AM):
4. Queries stock_scores: SELECT composite_score FROM stock_scores WHERE symbol='XYZ'
5. Gets score=45, doesn't check data_unavailable flag
6. Generates signal: {"symbol": "XYZ", "composite_score": 45, "strength": 0.8}
7. Signal marked as high-quality (score 45, strength 0.8)

Dashboard:
8. Displays signal: "XYZ - Composite 45 - STRONG BUY"
9. Trader executes position based on signal

Reality:
- Composite score based on 90+ day old financial data
- Company may have deteriorated significantly since
- Trading decision made on stale quality assessment
```

### Proposed Fix Approach
**Phase 7: Check data_unavailable flag before using metrics**

```python
# In _get_candidates_from_buysell() around line 306
cur.execute("""
    SELECT bsd.symbol, ss.composite_score, ss.data_unavailable, ss.data_unavailable_reason
    FROM buy_sell_daily bsd
    INNER JOIN stock_scores ss ON ss.symbol = bsd.symbol
    WHERE ss.composite_score IS NOT NULL
      AND bsd.signal = 'BUY'
      AND bsd.date >= %s
""", [...])

for row in cur.fetchall():
    symbol = row[0]
    composite = row[1]
    data_unavailable = row[2]  # ADD THIS CHECK
    unavail_reason = row[3]
    
    # CRITICAL: Check flag BEFORE using score
    if data_unavailable:
        logger.warning(f"[PHASE 7] {symbol}: stock_scores unavailable ({unavail_reason}), skipping signal")
        continue  # Don't generate signal from incomplete data
    
    # Safe to use composite_score now
    if composite >= min_score:
        candidates.append({"symbol": symbol, "composite_score": composite, ...})
```

**API signals endpoint: Propagate unavailability**
```python
# In lambda/api/routes/algo_handlers/signals.py
for signal in signals:
    # Check if underlying data was unavailable
    cur.execute("SELECT data_unavailable, data_unavailable_reason FROM stock_scores WHERE symbol=%s", (signal['symbol'],))
    score_row = cur.fetchone()
    
    if score_row and score_row[0]:  # data_unavailable = True
        signal["quality_warning"] = f"Based on incomplete data: {score_row[1]}"
        signal["confidence_reduced"] = True
    
    # Return signal with explicit availability indicator
    response.append(signal)
```

---

## FINDING #5: Entry Price & Stop Loss Used Without Validation They Exist

**Severity:** 🟠 MEDIUM  
**Category:** Unvalidated Calculations (Missing Required Fields)  

### File & Location
- `algo/trading/executor_entry_handler.py` **lines 144-162**

### The Issue
Entry/stop prices extracted and used before validation:

```python
# Line 144-146: Extract without checking None
entry_price = context.prices.entry_price
shares = context.shares
stop_loss_price = context.prices.stop_loss_price

# Line 155-165: Used in calculations immediately
risk_per_share = entry_price - stop_loss_price  # ASSUMES entry_price not None
position_value = shares * entry_price           # ASSUMES entry_price not None

# Line 168-172: THEN validation runs (too late if values corrupted)
try:
    pt_ok, pt_reason = validate_entry_preconditions(...)
except ValueError as e:
    logger.error(f"Pre-trade validation failed: {e}")
    # But values already used above!
```

### What Data is Assumed Valid
- `entry_price` is always a valid float > 0
- `stop_loss_price` is always a valid float > 0 and < entry_price
- Both fields exist in context.prices

### What Could Go Wrong
1. **NaN propagation:** If upstream price calc fails (network timeout, division by zero), None passed through
2. **Stop above entry:** stop_loss_price >= entry_price (logic error in stop calculation)
3. **Order placement with invalid prices:** Attempts to submit order with corrupted prices to Alpaca

### Example Failure Scenario
```
Order placement flow:
1. Phase 5 calculates stop_loss_price
2. Network timeout mid-calculation
3. stop_loss_price = None (not caught by timeout handler)
4. Signal submitted with stop_loss_price=None

Entry handler receives signal:
5. entry_price = 150.0, stop_loss_price = None
6. risk_per_share = 150.0 - None → TypeError
7. Exception caught → order placement blocked (good)

BUT: If exception isn't caught:
- Order submitted to Alpaca with stop_loss_price=null
- Alpaca rejects order → broker side safeguard triggers
- User must manually close position (manual intervention required)
```

### Current Mitigation
Phase 8 has validator (line 947: `validate_entry_preconditions`), but it runs AFTER calculations. This is acceptable but not ideal.

### Proposed Fix Approach
**Validate immediately upon extraction (fail-fast):**

```python
# BEFORE any calculations:
entry_price = context.prices.entry_price
stop_loss_price = context.prices.stop_loss_price

# Validate immediately
if entry_price is None or not isinstance(entry_price, (int, float)) or entry_price <= 0:
    raise ValueError(f"CRITICAL: entry_price invalid ({entry_price!r}). Cannot proceed with order placement.")

if stop_loss_price is None or not isinstance(stop_loss_price, (int, float)) or stop_loss_price <= 0:
    raise ValueError(f"CRITICAL: stop_loss_price invalid ({stop_loss_price!r}). Cannot proceed with order placement.")

if stop_loss_price >= entry_price:
    raise ValueError(f"CRITICAL: stop_loss_price ({stop_loss_price}) >= entry_price ({entry_price}). Invalid risk setup.")

# NOW safe to use in calculations
risk_per_share = entry_price - stop_loss_price
position_value = shares * entry_price
```

---

## FINDING #6: Target Price Calculations Without ATR Validation

**Severity:** 🟠 MEDIUM  
**Category:** Unvalidated Calculations (Missing Technical Data)  

### File & Locations
- `algo/signals/buy_signal_generator.py` **lines 453-458**
- `algo/trading/executor_entry_handler.py` **lines 355-390**

### The Issue
Target prices calculated with fixed percentages when ATR-based sizing would be more appropriate:

```python
# FIXED PERCENTAGE TARGETS (line 453-458):
result["profit_target_20pct"] = buy_dec * Decimal("1.20")  # Always +20%
result["profit_target_25pct"] = buy_dec * Decimal("1.25")  # Always +25%

# ACTUAL RISK CALCULATION (uses ATR):
actual_risk_per_share = executed_price_dec - stop_price_dec
target_1 = executed_price_dec + (actual_risk_per_share * t1_r_multiple)  # Risk-based, not %-based
```

### What Data is Assumed Valid
- 20% target is appropriate for all market regimes/volatilities
- 25% target is appropriate for all symbols
- ATR doesn't need to be validated if it exists

### What Could Go Wrong
1. **Mismatched risk/reward in volatility:**
   - High-volatility stock (ATR=$10): Entry=$100, Stop=$80, 20% target=$120 = only 0.67R reward
   - Expected reward: 1.5R = $115
   - Trader sized position for 1.5R but gets 0.67R

2. **Over-leverage in calm markets:**
   - Low-volatility stock (ATR=$2): Entry=$100, Stop=$96, 20% target=$120 = 6R reward
   - Expected reward: 1.5R = $103
   - Trader sized position for 1.5R but gets 6R exposure (over-leverage risk)

3. **Incomplete target calculation:**
   - If ATR missing, fallback to fixed %-based targets
   - ATR missing = incomplete market micro-structure understanding
   - Targets become generic/inappropriate

### Example Failure Scenario
```
Market Scenario 1 (High Volatility - VIX=40):
- Stock: NVDA, Entry=$500, ATR=$50
- Stop calc: $500 - 2*$50 = $400 (2% risk)
- Target 1.5R: $500 + (1.5*$100) = $650 (3% reward)
- Expected R/R: 1.5R
- Fixed target 20%: $500 * 1.2 = $600 (only 2% reward, 0.67R)
- Impact: Trader expects 1.5R reward, gets 0.67R → Wrong position size

Market Scenario 2 (Low Volatility - VIX=12):
- Stock: JNJ, Entry=$150, ATR=$3
- Stop calc: $150 - 2*$3 = $144 (4% risk)
- Target 1.5R: $150 + (1.5*$6) = $159 (6% reward, 1.5R)
- Fixed target 20%: $150 * 1.2 = $180 (20% reward, 5R)
- Impact: Position sized for 1.5R risk but taking 5R opportunity (over-leverage)
```

### Proposed Fix Approach
**Always use ATR-based targets; fail if ATR unavailable:**

```python
def calculate_targets(entry_price: float, atr_14: float | None, 
                     stop_loss_price: float, symbol: str) -> dict:
    """Calculate risk-based target prices.
    
    CRITICAL: ATR is required for appropriate position sizing.
    Fixed percentage targets are unreliable across market regimes.
    """
    
    if atr_14 is None or atr_14 <= 0:
        raise ValueError(
            f"CRITICAL: {symbol} ATR unavailable or invalid ({atr_14!r}). "
            f"Cannot calculate risk-based targets. Technical data incomplete."
        )
    
    risk_per_share = entry_price - stop_loss_price
    
    if risk_per_share <= 0:
        raise ValueError(
            f"CRITICAL: {symbol} invalid risk calculation. "
            f"Entry {entry_price} <= Stop {stop_loss_price}"
        )
    
    # Risk-based targets (consistent across all market regimes)
    target_1 = entry_price + (risk_per_share * 1.5)   # Always 1.5R
    target_2 = entry_price + (risk_per_share * 2.5)   # Always 2.5R
    target_3 = entry_price + (risk_per_share * 4.0)   # Always 4R
    
    return {
        "target_1": target_1,  # 1.5R
        "target_2": target_2,  # 2.5R
        "target_3": target_3,  # 4R
        "risk_per_share": risk_per_share,
        "status": "ok"
    }
```

---

## FINDING #7: Portfolio Value Sanity Check Missing (Corruption Edge Case)

**Severity:** 🟡 LOW  
**Category:** Incomplete Data Checks (Edge Case)  

### File & Location
- `algo/risk/var.py` **lines 599-604**

### The Issue
Zero-check exists but accepts unreasonably small portfolio values:

```python
# Line 599-603: Checks for <= 0
if portfolio_value_float <= 0:
    raise RuntimeError("Portfolio value must be positive")

# But what if corrupted data has portfolio_value = $0.01?
if portfolio_value_float < 1:  # < $1 is unreasonable but passes check
    position_pct = position_value / portfolio_value_float * 100
    # $50,000 / $0.01 * 100 = 500,000,000% concentration!
```

### What Data is Assumed Valid
- `portfolio_value > 0` implies it's meaningful/reasonable

### What Could Go Wrong
1. **Corrupted portfolio snapshot:** Reconciliation fails, stores $0.01 instead of $100,000
2. **Position concentration wildly wrong:** Calculations overflow/underflow
3. **Circuit breaker allows massive positions:** Max position size becomes absurd

### Example Failure Scenario
```
Corrupted state: portfolio_value = $0.01 (from failed reconciliation)

Position sizer calculation:
- Available capital: $0.01
- Max position size (8% of portfolio): 0.08 * $0.01 = $0.0008
- Minimum order ($10): $0.0008 < $10
- Position rounds to $10 (should be fractional)

Or worse: Concentration calculation:
- Position value: $10,000
- Concentration: $10,000 / $0.01 * 100 = 100,000,000%
- Risk logic: ALL positions consolidated into first symbol

Impact: System over-leverages massively
```

### Current Mitigation
Unlikely to occur in production (reconciliation usually catches), but edge case exists.

### Proposed Fix Approach
**Add reasonable minimum portfolio value check:**

```python
MIN_REASONABLE_PORTFOLIO = Decimal("1000.00")  # Minimum $1,000

if portfolio_value_float <= 0:
    raise PortfolioValueError("Portfolio value must be positive")

if portfolio_value_float < MIN_REASONABLE_PORTFOLIO:
    raise PortfolioValueError(
        f"CRITICAL: Portfolio value {portfolio_value_float} suspiciously low. "
        f"Minimum {MIN_REASONABLE_PORTFOLIO} required for position sizing. "
        f"Check reconciliation status and Alpaca account balance."
    )
```

---

## FINDING #8: Market Breadth/Health Returned Without Completeness Indicator

**Severity:** 🟠 MEDIUM  
**Category:** Missing Data Completeness Checks  

### File & Location
- `lambda/api/routes/market.py` **lines 70-145** (breadth endpoint)
- `lambda/api/routes/market.py` **lines 43-68** (market_health_daily)

### The Issue
Breadth queries may time out/fail but still return partial data without indicating incompleteness:

```python
# Line 214-218: If no breadth data, still returns base dict
if not breadth_rows:
    logger.critical("[TECHNICALS_BREADTH] No breadth data available for {date}")
    # Proceeds without breadth key

# Returns: {"advance_decline_ratio": 1.2, "new_highs": None, "new_lows": None}
# User doesn't know which fields are missing vs complete
```

### What Data is Assumed Valid
- If breadth endpoint returns data, ALL fields (advance/decline, new_highs/lows, issues) are populated
- Missing fields don't affect breadth calculation validity

### What Could Go Wrong
1. **Market assessment incomplete:**
   - New_highs loader timeout → returns None
   - Breadth calculation uses only advance/decline ratio
   - Circuit breaker doesn't know new_highs are stale

2. **Risk calculations underestimate market weakness:**
   - Advance/decline looks positive: 60 advancing / 40 declining
   - But new_lows missing (stale) → doesn't know 500 stocks hit 52-week lows
   - Risk policy allows entries in declining market

3. **Dashboard deceives on market health:**
   - Shows "Breadth improving" when actually incomplete data

### Example Failure Scenario
```
Overnight loader run:
1. load_market_breadth completes: 60% advancing
2. load_new_highs_lows times out (SEC API down): skipped
3. Database state: breadth={'advances': 6000, 'declines': 4000, 'new_highs': NULL}

Market API endpoint:
4. Query breadth: returns {'advances': 6000, 'declines': 4000, 'new_highs': NULL}
5. Response doesn't indicate new_highs is missing (just NULL)

Circuit breaker:
6. Sees 60% breadth > threshold → allows entries
7. Doesn't know that 2,000 stocks at new lows (data missing)

Trading impact:
8. Algo enters positions in market actually in correction
9. Decisions made on incomplete market data
```

### Proposed Fix Approach
**Require all critical breadth fields; fail gracefully if incomplete:**

```python
REQUIRED_BREADTH_FIELDS = {
    "advances_count": "Number of advancing stocks",
    "declines_count": "Number of declining stocks",
    "new_highs_count": "Stocks at 52-week highs",
    "new_lows_count": "Stocks at 52-week lows",
    "unchanged_count": "Unchanged stocks"
}

# Query breadth data
cur.execute("""SELECT date, advances, declines, new_highs, new_lows, unchanged 
               FROM market_breadth WHERE date = %s""", (eval_date,))
breadth_row = cur.fetchone()

if not breadth_row:
    return {
        "success": False,
        "error": "breadth_data_missing",
        "data_unavailable": True,
        "message": f"No breadth data available for {eval_date}"
    }

# Check all fields present
missing_fields = []
for i, (field_name, _) in enumerate(REQUIRED_BREADTH_FIELDS.items()):
    if breadth_row[i+1] is None:  # Skip first column (date)
        missing_fields.append(field_name)

if missing_fields:
    return {
        "success": False,
        "error": "incomplete_breadth_data",
        "data_unavailable": True,
        "missing_fields": missing_fields,
        "message": f"Breadth data incomplete: missing {', '.join(missing_fields)}"
    }

# All fields present - safe to calculate
return {
    "success": True,
    "advances": breadth_row[1],
    "declines": breadth_row[2],
    "new_highs": breadth_row[3],
    "new_lows": breadth_row[4],
    "advance_decline_ratio": breadth_row[1] / max(1, breadth_row[2]),
    "data_completeness": 100
}
```

---

## SUMMARY TABLE

| Issue | File | Risk | Impact | Status | Effort |
|-------|------|------|--------|--------|--------|
| #1: Sector "Unknown" fallback | `var.py:614-635` | HIGH | Risk reports deceive on concentration | Unfixed | 2 hrs |
| #2: Dashboard cache without age | `dashboard.py:60-78` | MEDIUM | Stale price decisions | Unfixed | 1 hr |
| #3: Symbol filtering inconsistent | Multiple | HIGH | Wrong universe in Phase 7 | Unfixed | 4 hrs |
| #4: data_unavailable flags unchecked | Multiple | HIGH | Signals from incomplete data | Unfixed | 3 hrs |
| #5: Entry/stop price unvalidated | `entry_handler.py:144` | MEDIUM | Caught by validator (partial) | Partially Mitigated | 1 hr |
| #6: Target prices without ATR check | `buy_signal_gen.py:453` | MEDIUM | Wrong R/R in volatility | Unfixed | 2 hrs |
| #7: Portfolio value sanity check | `var.py:604` | LOW | Edge case (corrupted data) | Mostly Protected | 30 min |
| #8: Breadth completeness unknown | `market.py:70-145` | MEDIUM | Incomplete market assessment | Unfixed | 1.5 hrs |

---

## RECOMMENDED REMEDIATION SEQUENCE

### Phase 1 (Critical - Session 253): 
**Issues #1, #3, #4** (8 hours)
- Implement central symbol filter utility
- Add data_unavailable checks in Phase 7 and signal endpoints
- Fix sector fallback to explicit unavailable marker

### Phase 2 (High Priority - Session 254):
**Issues #2, #8** (2.5 hours)
- Add cache age to dashboard response
- Validate breadth data completeness

### Phase 3 (Medium Priority - Session 255):
**Issues #5, #6** (3 hours)
- Improve entry/stop price validation (fail-fast)
- Validate ATR before target calculation

### Phase 4 (Low Priority):
**Issue #7** (30 minutes)
- Add portfolio value sanity check

**Total Estimated Effort:** 13.5 hours across 4 sessions

---

## VERIFICATION CHECKLIST

- [x] All 8 issues have specific file:line references
- [x] Each issue includes example failure scenario
- [x] Proposed fixes are concrete and implementable
- [x] Risk levels are justified
- [x] No findings are contradictory
- [x] All fixes follow fail-fast/fail-closed patterns

---

**Report Generated:** Session 252  
**Auditor:** Claude Code Agent  
**Codebase:** `/c/Users/arger/code/algo`  
**Scope:** Complete data quality audit (Phases 1-9, Loaders, APIs, Dashboard)

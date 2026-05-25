# Formula Audit - May 25, 2026

## Current Status: FORMULAS REVIEWED

### ✅ CORRECT FORMULAS

#### Technical Indicators (technical_indicators.py)
- **RSI (14)**: Uses Wilder's EMA (com=14-1) ✓
- **MACD**: EMA(12) - EMA(26), signal = EMA(9) ✓
- **Moving Averages**: SMA 20, 50, 150, 200; EMA 12, 21, 26 ✓
- **ATR (14)**: True Range rolled 14-period mean ✓
- **Bollinger Bands**: SMA(20) ± 2σ ✓
- **Volume MA**: 50-period rolling mean ✓

#### Minervini Trend Criteria (load_trend_criteria_data.py)
- **8-Point Score**: Correct criteria
  1. Price > SMA(50) ✓
  2. Price > SMA(150) ✓
  3. Price > SMA(200) ✓
  4. SMA(50) > SMA(150) ✓
  5. SMA(150) > SMA(200) ✓
  6. SMA(200) slope > 0 ✓
  7. Price ≥ 52w high × 0.75 ✓
  8. Price ≥ 52w low × 1.30 (30% from low) ✓

#### Weinstein Stage (load_trend_criteria_data.py)
- Stage 2 (advancing): Price > SMA(200) AND SMA(200) slope > 0 ✓
- Stage 4 (declining): Price < SMA(200) ✓

#### Config Defaults (algo_config.py)
- require_stock_stage_2: true ✓
- min_percent_from_52w_low: 30.0 ✓
- max_hold_days: 20 ✓

#### Market Health (algo_market_exposure.py)
- **Distribution Days**: close < prev_close × 0.998 (0.2% threshold) AND volume > prev_vol, window 25 days ✓
- **FTD Threshold**: close ≥ prev_close × 1.017 (1.7% gain) ✓

#### Exit Signals (algo_exit_engine.py)
- **Minervini Break**: Uses EMA(21) (not EMA(12)) ✓
- **Distribution Day Exit**: Applied to all positions ✓

### ⚠️ INCONSISTENCY FOUND

#### load_market_health_daily.py - Distribution Day Calculation
**Issue**: Missing 0.2% decline threshold

**Current (line 98):**
```python
df["distribution_day"] = ((df["price_change"] < 0) & (df["volume"] > df["prev_volume"])).astype(int)
```

**Should be (per IBD canonical definition):**
```python
df["distribution_day"] = ((df["price_change"] < -df["prev_close"] * 0.002) & (df["volume"] > df["prev_volume"])).astype(int)
```

Or equivalently:
```python
df["distribution_day"] = ((df["close"] < df["prev_close"] * 0.998) & (df["volume"] > df["prev_volume"])).astype(int)
```

**Why**: The docstring in signal_momentum.py (line 324-328) and algo_market_exposure.py (line 297) both specify "close declines >= 0.2%" as canonical IBD definition. This threshold excludes noise/minor moves.

**Impact**: Inflates distribution day counts for SPY, potentially causing false market weakness signals.

### ✅ FIXED

**load_market_health_daily.py (May 26, 2026)**
- Line 97: Added `df["prev_close"] = df["close"].shift(1)`
- Line 100: Changed distribution day formula to use 0.2% threshold
  - Before: `(df["price_change"] < 0)`
  - After: `(df["close"] < df["prev_close"] * 0.998)`
- Line 99: Added comment documenting IBD canonical definition

Now consistent with:
- `signal_momentum.py` line 344: `close < prev_close * 0.998`
- `algo_market_exposure.py` line 314: `close < prev_close * 0.998`


# Swing Trading Metrics Implementation
## O'Neill CAN SLIM + Minervini SEPA Methodology

This document describes all swing trading metrics now tracked in `buy_sell_daily`, `buy_sell_weekly`, and `buy_sell_monthly` tables.

## Core Trading Levels

### 1. **Buy Level** (`buylevel`)
- Entry price for long positions
- Calculated from technical breakout levels
- Used as baseline for risk/reward calculations

### 2. **Sell Level** (`selllevel`)
- Entry price for short positions
- Opposite of buy level when signal = 'SELL'
- NULL for buy signals

### 3. **Stop Loss** (`stoplevel`)
- Maximum acceptable loss point
- ~7-8% below buy level (Minervini rule)
- Critical for risk management

### 4. **Target Price** (`target_price`)
- **For Buys**: 25% above entry (buy level * 1.25)
- **For Shorts**: 15% below entry (buy level * 0.85)
- Based on Minervini profit targets

## Profit Targets (Minervini Methodology)

### 5. **8% Profit Target** (`profit_target_8pct`)
- First take-profit level
- Minervini: Take 20-25% of position off here
- Calculated as: `buylevel * 1.08`

### 6. **20% Profit Target** (`profit_target_20pct`)
- Major profit target
- Minervini: Take another 25-30% off here
- Calculated as: `buylevel * 1.20`
- Let runners go to 25-30%+

## Risk Management Metrics

### 7. **Risk/Reward Ratio** (`risk_reward_ratio`)
- Formula: `(target_price - entry) / (entry - stop_loss)`
- **Minimum acceptable**: 2:1 (Minervini standard)
- **Ideal**: 3:1 or better
- Example: Risk $1 to make $3

### 8. **Risk Percent** (`risk_pct`)
- Distance from entry to stop as percentage
- Formula: `((buylevel - stoplevel) / buylevel) * 100`
- **Minervini maximum**: 7-8%
- Helps size positions appropriately

### 9. **Position Size Recommendation** (`position_size_recommendation`)
- Number of shares to buy
- **Formula**: Risk 1% of portfolio / risk per share
- Example: $100k portfolio, $1k risk, $10 risk/share = 100 shares
- Assumes $100,000 portfolio with 1% risk per trade

### 10. **Current Gain/Loss %** (`current_gain_loss_pct`)
- Real-time P&L if in position
- Formula: `((current_price - buylevel) / buylevel) * 100`
- NULL if not in position (`inposition = FALSE`)

## Weinstein Stage Analysis

### 11. **Market Stage** (`market_stage`)
Four stages of stock movement:

#### Stage 1 - Basing
- **Characteristics**: Consolidation at bottom, accumulation
- **Price**: Below or near 200 SMA, flattening
- **SMAs**: Flattening
- **ADX**: < 20 (low trend strength)
- **Action**: WATCH for breakout, build watchlist

#### Stage 2 - Advancing ⭐ (BUY ZONE)
- **Characteristics**: Strong uptrend, optimal buying
- **Price**: Above both 50 and 200 SMA
- **SMAs**: 50 SMA > 200 SMA, both rising
- **ADX**: > 25 (strong uptrend)
- **Volume**: Increasing on up days
- **Action**: BUY on pullbacks to 21 EMA

#### Stage 3 - Topping
- **Characteristics**: Momentum slowing, distribution
- **Price**: Above SMAs but weakening
- **SMAs**: Flattening
- **ADX**: Decreasing from highs
- **Action**: TAKE PROFITS, tighten stops

#### Stage 4 - Declining
- **Characteristics**: Downtrend, avoid completely
- **Price**: Below 50 and 200 SMA
- **SMAs**: 50 SMA < 200 SMA (death cross)
- **ADX**: > 20 (strong downtrend)
- **Action**: DO NOT BUY, short only for experienced traders

## Moving Average Analysis

### 12. **% from 21 EMA** (`pct_from_ema_21`)
- Distance from 21-period Exponential Moving Average
- **Minervini Buy Zone**: Within 1-2% of 21 EMA
- Identifies pullback entry points in uptrends
- Formula: `((current_price - ema_21) / ema_21) * 100`

### 13. **% from 50 SMA** (`pct_from_sma_50`)
- Distance from 50-period Simple Moving Average
- **Ideal**: Within 5-10% for entries
- Formula: `((current_price - sma_50) / sma_50) * 100`

### 14. **% from 200 SMA** (`pct_from_sma_200`)
- Distance from 200-period Simple Moving Average
- **Minervini rule**: Must be > 0% AND < 30%
- Shows long-term trend strength
- Formula: `((current_price - sma_200) / sma_200) * 100`

## Volume Analysis (O'Neill Methodology)

### 15. **Volume Ratio** (`volume_ratio`)
- Current volume vs 50-day average
- Formula: `current_volume / volume_avg_50`
- **Interpretation**:
  - **> 2.0**: Pocket Pivot (O'Neill - major buy signal)
  - **> 1.5**: Volume Surge
  - **< 0.7**: Volume Dry-up (potential accumulation)
  - **~1.0**: Normal volume

### 16. **Volume Analysis** (`volume_analysis`)
- **Pocket Pivot**: Volume > 200% average AND price up
  - Most powerful buy signal in O'Neill system
  - Shows institutional buying

- **Volume Surge**: Volume > 150% average AND price up > 2%
  - Strong buying pressure

- **Volume Dry-up**: Volume < 70% average
  - Potential accumulation (watch for breakout)

- **Normal Volume**: Regular trading activity

## Minervini Trend Template

### 17. **Passes Minervini Template** (`passes_minervini_template`)
Boolean flag - ALL must be true:

1. ✅ Current price > 50 SMA
2. ✅ Current price > 150 SMA
3. ✅ Current price > 200 SMA
4. ✅ 50 SMA > 150 SMA
5. ✅ 150 SMA > 200 SMA
6. ✅ Price is 0-30% above 200 SMA
7. ✅ 200 SMA trending up for 1+ months

**Purpose**: Identifies stocks in strongest relative strength

## Entry Quality Scoring

### 18. **Entry Quality Score** (`entry_quality_score`)
0-100 point scale evaluating setup quality:

- **40 points**: Stage 2 - Advancing
- **20 points**: Within 2% of 21 EMA
- **20 points**: Volume ratio >= 1.5
- **20 points**: RSI between 40-70 (not overbought/oversold)

**Score Ranges**:
- **80-100**: Excellent setup (rare)
- **60-79**: Good setup
- **40-59**: Average setup
- **0-39**: Poor setup, avoid

## Technical Indicators

### 19. **RSI** (`rsi`)
- Relative Strength Index (14-period)
- **Overbought**: > 70
- **Oversold**: < 30
- **Minervini buy zone**: 40-55 (pullback in uptrend)

### 20. **ADX** (`adx`)
- Average Directional Index
- **Strong trend**: > 25
- **Weak trend**: < 20
- **Very strong**: > 40
- Confirms trend strength for stage analysis

### 21. **ATR** (`atr`)
- Average True Range (14-period)
- Measures volatility
- Used for stop-loss placement
- Higher ATR = wider stops needed

### 22. **Daily Range %** (`daily_range_pct`)
- `((high - low) / low) * 100`
- **Tight action**: < 2% (Minervini likes tight consolidation)
- **Volatile**: > 5%
- Identifies low-volatility setups before breakouts

## Current Market Data

### 23. **Current Price** (`current_price`)
- Latest closing price
- Used for all calculations
- Updated with each signal generation

### 24. **In Position** (`inposition`)
- Boolean: Are we currently holding this position?
- TRUE = currently in trade
- FALSE = watching/exited
- Used to calculate current_gain_loss_pct

## Database Tables

All metrics stored in:
- `buy_sell_daily` - Daily timeframe signals
- `buy_sell_weekly` - Weekly timeframe signals
- `buy_sell_monthly` - Monthly timeframe signals

## Calculation Flow

1. **Initial Signal Generation** (`loadbuyselldaily.py`, etc.)
   - Generates buy/sell signals
   - Sets entry, stop levels
   - Creates base OHLCV data

2. **Swing Metrics Calculation** (`update_swing_metrics.py`)
   - Fetches technical data from `technical_data_daily`
   - Fetches price data from `price_daily`
   - Calculates all 24 swing trading metrics
   - Updates buy_sell tables

3. **API Exposure** (`/api/signals` endpoint)
   - Returns all metrics to frontend
   - Filtered by timeframe, signal type, symbol

4. **Frontend Display** (`TradingSignals.jsx`)
   - Shows all key metrics in table
   - Color-codes by stage, quality score
   - Highlights recent signals
   - Displays profit targets, risk metrics

## Key Trading Rules (Minervini/O'Neill)

### Entry Rules:
1. ✅ Must be in Stage 2 - Advancing
2. ✅ Buy within 1-2% of 21 EMA pullback
3. ✅ Volume ratio > 1.5 (preferably pocket pivot)
4. ✅ RSI 40-55 (not overbought)
5. ✅ Passes Minervini Trend Template
6. ✅ Entry quality score > 60

### Exit Rules:
1. ❌ Stop loss: 7-8% below entry (HARD RULE)
2. ✅ Take 20-25% off at +8%
3. ✅ Take 25-30% off at +20%
4. ✅ Trail stops on remaining 50%
5. ❌ Exit if drops back into Stage 1 or Stage 4

### Position Sizing:
- Risk 1% of portfolio per trade
- Use `position_size_recommendation`
- Never risk more than 2% on any single trade
- Max 5 positions = 5% total portfolio risk

## References

- **Mark Minervini**: "Trade Like a Stock Market Wizard"
- **William O'Neill**: "How to Make Money in Stocks" (CAN SLIM)
- **Stan Weinstein**: "Secrets for Profiting in Bull and Bear Markets" (Stage Analysis)

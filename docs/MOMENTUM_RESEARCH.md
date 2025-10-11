# Momentum Score Research & Implementation

## Executive Summary
Momentum measures the **rate of price change** (velocity) over various timeframes. It is distinct from trend direction, volume, or volatility.

## Industry-Standard Momentum Indicators

### What Momentum ETFs Use (MTUM, PDP, JMOM, QMOM)

**1. Multiple Timeframe Price Returns**
- Short-term: 1-month (20 days), 3-month (60 days)
- Medium-term: 6-month (120 days), 12-month (250 days)
- Most common: 6-month and 12-month momentum

**2. Relative Strength**
- Performance vs benchmark (S&P 500)
- Mansfield Relative Strength calculation
- Identifies stocks outperforming market

**3. Momentum Oscillators**
- RSI (14-day): Measures momentum strength (0-100)
- Identifies overbought (>70) and oversold (<30) conditions
- Used for timing and risk management

**4. Trend-Following Momentum**
- MACD: Detects momentum direction changes
- Crossovers signal momentum shifts
- Histogram shows momentum acceleration/deceleration

### What Is NOT Momentum

**Volume-Based Indicators** (Separate Factor)
- MFI (Money Flow Index)
- AD (Accumulation/Distribution)
- CMF (Chaikin Money Flow)
- These measure "money flow" or "volume confirmation" - NOT momentum

**Trend Strength Indicators** (Separate Factor)
- ADX (Average Directional Index)
- Plus DI / Minus DI
- These measure trend INTENSITY, not rate of change

**Moving Averages** (Trend Following)
- SMA, EMA
- These are lagging trend indicators, not momentum

## Our Implementation Strategy

### Available Data (from technical_data_daily)
```python
rsi          # 14-day RSI (momentum oscillator)
macd         # MACD line (trend-following momentum)
macd_signal  # MACD signal line
macd_hist    # MACD histogram (momentum acceleration)
mom          # 10-day momentum (absolute price change)
roc          # 10-day Rate of Change (percentage)
mansfield_rs # Relative strength vs S&P 500
```

### Proposed 5-Component Momentum Score

**1. Short-Term Momentum (25 points) - Days/Weeks**
- RSI (14-day): Momentum strength and overbought/oversold
- MACD: Momentum direction and acceleration
- Captures immediate price velocity

**2. Medium-Term Momentum (25 points) - Weeks**
- MOM (10-day): Absolute price change
- ROC (10-day): Percentage rate of change
- Captures sustained momentum

**3. Longer-Term Momentum (20 points) - Months**
- Calculate from price_daily: 60-day ROC (3-month), 120-day ROC (6-month)
- Captures established trends and institutional momentum
- **Needs calculation from price_daily table**

**4. Relative Strength (20 points) - Market Comparison**
- Mansfield RS: Performance vs S&P 500
- Identifies market outperformers
- Critical for momentum factor investing

**5. Momentum Consistency (10 points) - Multi-Timeframe Alignment**
- Bonus when multiple timeframes agree (all positive or all negative)
- Penalize when momentum is conflicting across timeframes
- Rewards sustained, consistent momentum

### Implementation Notes

**Timeframe Periods (Industry Standard)**
- Very Short: 1-10 days (captured by RSI, MACD, 10-day MOM/ROC)
- Short: 20-40 days (1-2 months) - **NEED TO ADD**
- Medium: 60-120 days (3-6 months) - **NEED TO ADD**
- Long: 250 days (12 months) - **OPTIONAL FOR V2**

**Key Additions Needed:**
1. Calculate 20-day ROC (1-month momentum)
2. Calculate 60-day ROC (3-month momentum)
3. Calculate 120-day ROC (6-month momentum)
4. Optional: 250-day ROC (12-month momentum)

**Weighting Philosophy:**
- Equal weight to short, medium, longer-term (25%, 25%, 20%)
- Relative strength 20% (critical for factor investing)
- Consistency bonus 10%

## References

**Academic Research:**
- Jegadeesh & Titman (1993): "Returns to Buying Winners and Selling Losers"
- Carhart (1997): Four-factor model including momentum
- Asness, Moskowitz & Pedersen (2013): "Value and Momentum Everywhere"

**Momentum ETF Methodologies:**
- iShares MSCI USA Momentum (MTUM): 6-month and 12-month price returns
- Invesco DWA Momentum (PDP): Relative strength rankings
- JPMorgan US Momentum (JMOM): 6-month and 12-month returns

**Key Insight:**
Momentum works best when combining multiple timeframes and confirming with relative strength. Short-term momentum alone is too noisy; medium-term (3-6 months) is the sweet spot used by most factor investors.

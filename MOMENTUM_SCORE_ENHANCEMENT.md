# Momentum Score Enhancement - Industry-Leading Design

## Current State Analysis

**Current Momentum Score Components** (loadstockscores.py lines 201-240):
- RSI component (0-40 points)
- MACD component (0-30 points)
- 5-day price momentum (0-30 points)

**Weight**: 21% of composite score

## Available Data Sources

### From `technical_data_daily` table (already calculated by loadtechnicalsdaily.py):
✅ **Price Momentum Indicators:**
- RSI (Relative Strength Index)
- MACD, MACD Signal, MACD Histogram
- Momentum (MOM) - 10-period
- Rate of Change (ROC) - 10-period
- ADX (Average Directional Index) - trend strength
- Plus DI / Minus DI (Directional Movement)

✅ **Volume-Based Momentum:**
- MFI (Money Flow Index) - volume-weighted RSI
- AD (Accumulation/Distribution)
- CMF (Chaikin Money Flow)

✅ **Relative Strength:**
- Mansfield RS - relative strength vs S&P 500 (SPY)

✅ **Moving Averages:**
- SMAs: 10, 20, 50, 150, 200
- EMAs: 4, 9, 21
- Bollinger Bands (upper, middle, lower)

✅ **Other:**
- DM (Directional Movement)
- Pivot highs/lows (support/resistance)

### From `price_daily` table:
✅ **Multi-timeframe Price Changes:**
- 1-day, 5-day, 30-day (currently calculated)
- Can add: 10-day, 20-day, 60-day, 90-day

✅ **Volume Data:**
- Daily volume, 30-day average volume

### Missing Indicators (need to add):

❌ **Stochastic Oscillator** (%K, %D) - momentum oscillator comparing closing price to price range
❌ **Williams %R** - momentum indicator measuring overbought/oversold levels
❌ **CCI** (Commodity Channel Index) - measures deviation from average price
❌ **Volume Trends** - volume increasing/decreasing patterns
❌ **OBV** (On-Balance Volume) - similar to AD but different calculation

---

## Enhanced Momentum Score Design

### 🎯 **Target: Industry-Leading 8-Component Momentum Score (0-100 scale)**

**Component Breakdown:**

#### 1. **Short-Term Price Momentum** (0-20 points)
- 1-day, 5-day, 10-day ROC
- Recent price acceleration
- Breakout detection using pivots

#### 2. **Medium-Term Price Momentum** (0-15 points)
- 20-day, 30-day, 60-day ROC
- Sustained trend identification
- Moving average alignment

#### 3. **Oscillator Signals** (0-15 points)
- RSI (overbought/oversold/divergence)
- Stochastic (if added)
- Williams %R (if added)
- MFI (volume confirmation)

#### 4. **Trend Strength** (0-12 points)
- ADX (trend strength)
- Plus DI vs Minus DI (directional bias)
- MACD histogram momentum
- Moving average slopes

#### 5. **MACD Analysis** (0-12 points)
- MACD line position (positive/negative)
- MACD histogram (expanding/contracting)
- MACD signal line crossovers
- MACD momentum (rate of change)

#### 6. **Volume Confirmation** (0-10 points)
- MFI (money flow strength)
- Accumulation/Distribution trend
- Volume vs average (increasing on up days)
- Chaikin Money Flow

#### 7. **Relative Strength** (0-10 points)
- Mansfield RS vs S&P 500
- Outperformance/underperformance trend
- Relative strength rank

#### 8. **Momentum Consistency** (0-6 points)
- Multi-timeframe alignment (all timeframes positive)
- Momentum divergence detection
- Trend stability (no whipsaws)

---

## Implementation Plan

### Phase 1: Calculate Additional Metrics (if needed)
**In `loadlatesttechnicalsdaily.py`** - add to existing calculation:
```python
def calculate_additional_momentum_indicators(df):
    # Stochastic Oscillator
    low_min = df['Low'].rolling(window=14).min()
    high_max = df['High'].rolling(window=14).max()
    df['stoch_k'] = 100 * (df['Close'] - low_min) / (high_max - low_min)
    df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()

    # Williams %R
    df['williams_r'] = -100 * (high_max - df['Close']) / (high_max - low_min)

    # CCI (Commodity Channel Index)
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    sma_tp = typical_price.rolling(window=20).mean()
    mad = typical_price.rolling(window=20).apply(lambda x: np.abs(x - x.mean()).mean())
    df['cci'] = (typical_price - sma_tp) / (0.015 * mad)

    # OBV (On-Balance Volume)
    obv = [0]
    for i in range(1, len(df)):
        if df['Close'].iloc[i] > df['Close'].iloc[i-1]:
            obv.append(obv[-1] + df['Volume'].iloc[i])
        elif df['Close'].iloc[i] < df['Close'].iloc[i-1]:
            obv.append(obv[-1] - df['Volume'].iloc[i])
        else:
            obv.append(obv[-1])
    df['obv'] = obv

    # Volume trend (20-day)
    df['volume_sma_20'] = df['Volume'].rolling(window=20).mean()
    df['volume_ratio'] = df['Volume'] / df['volume_sma_20']

    return df
```

### Phase 2: Update `loadstockscores.py` Momentum Calculation
**Replace lines 201-240** with comprehensive 8-component calculation:

```python
def calculate_enhanced_momentum_score(
    # Price data
    price_change_1d, price_change_5d, price_change_30d,
    current_price, sma_20, sma_50, sma_200,
    # Technical indicators
    rsi, macd, macd_hist, adx, plus_di, minus_di,
    mfi, roc, mom, ad, cmf,
    # Relative strength
    mansfield_rs,
    # Volume
    volume_avg_30d, current_volume,
    # Optional new indicators
    stoch_k=None, stoch_d=None, williams_r=None, cci=None
):
    """
    Calculate comprehensive momentum score (0-100)

    Components:
    1. Short-term price momentum (0-20)
    2. Medium-term price momentum (0-15)
    3. Oscillator signals (0-15)
    4. Trend strength (0-12)
    5. MACD analysis (0-12)
    6. Volume confirmation (0-10)
    7. Relative strength (0-10)
    8. Momentum consistency (0-6)
    """

    momentum_score = 0

    # 1. SHORT-TERM PRICE MOMENTUM (0-20 points)
    short_term = 10  # neutral
    if price_change_1d > 2:
        short_term += min(5, price_change_1d * 0.5)
    elif price_change_1d < -2:
        short_term -= min(5, abs(price_change_1d) * 0.5)

    if price_change_5d > 5:
        short_term += min(5, price_change_5d * 0.3)
    elif price_change_5d < -5:
        short_term -= min(5, abs(price_change_5d) * 0.3)

    short_term = max(0, min(20, short_term))
    momentum_score += short_term

    # 2. MEDIUM-TERM PRICE MOMENTUM (0-15 points)
    medium_term = 7.5  # neutral
    if price_change_30d > 10:
        medium_term = 15
    elif price_change_30d > 5:
        medium_term = 12
    elif price_change_30d > 0:
        medium_term = 9
    elif price_change_30d > -5:
        medium_term = 6
    elif price_change_30d > -10:
        medium_term = 3
    else:
        medium_term = 0

    momentum_score += medium_term

    # 3. OSCILLATOR SIGNALS (0-15 points)
    oscillator_score = 0

    # RSI component (0-8 points)
    if rsi is not None:
        if 50 < rsi < 70:
            oscillator_score += 8  # Strong bullish
        elif 40 < rsi <= 50:
            oscillator_score += 6  # Mildly bullish
        elif 70 <= rsi < 80:
            oscillator_score += 6  # Overbought but strong
        elif 30 < rsi <= 40:
            oscillator_score += 4  # Oversold bounce potential
        elif rsi >= 80:
            oscillator_score += 3  # Very overbought
        else:  # rsi <= 30
            oscillator_score += 2  # Very oversold

    # MFI component (0-7 points) - volume confirmation
    if mfi is not None:
        if 50 < mfi < 80:
            oscillator_score += 7  # Strong money flow
        elif 40 < mfi <= 50:
            oscillator_score += 5
        elif mfi >= 80:
            oscillator_score += 4  # Overbought
        else:
            oscillator_score += 2  # Weak money flow

    momentum_score += min(15, oscillator_score)

    # 4. TREND STRENGTH (0-12 points)
    trend_strength = 0

    # ADX component (0-6 points)
    if adx is not None:
        if adx > 50:
            trend_strength += 6  # Very strong trend
        elif adx > 25:
            trend_strength += 5  # Strong trend
        elif adx > 20:
            trend_strength += 3  # Moderate trend
        else:
            trend_strength += 1  # Weak/no trend

    # Directional bias (0-6 points)
    if plus_di is not None and minus_di is not None:
        if plus_di > minus_di:
            di_diff = plus_di - minus_di
            trend_strength += min(6, di_diff / 5)
        else:
            di_diff = minus_di - plus_di
            trend_strength -= min(6, di_diff / 5)

    momentum_score += max(0, min(12, trend_strength))

    # 5. MACD ANALYSIS (0-12 points)
    macd_score = 6  # neutral

    if macd is not None:
        # MACD position (0-6 points)
        if macd > 0:
            macd_score += min(3, macd * 0.5)
        else:
            macd_score -= min(3, abs(macd) * 0.5)

        # MACD histogram momentum (0-6 points)
        if macd_hist is not None:
            if macd_hist > 0:
                macd_score += min(3, macd_hist * 2)
            else:
                macd_score -= min(3, abs(macd_hist) * 2)

    momentum_score += max(0, min(12, macd_score))

    # 6. VOLUME CONFIRMATION (0-10 points)
    volume_score = 5  # neutral

    # MFI already used above, use AD and CMF
    if ad is not None and ad > 0:
        volume_score += 2
    elif ad is not None and ad < 0:
        volume_score -= 2

    if cmf is not None:
        if cmf > 0.1:
            volume_score += 3
        elif cmf > 0:
            volume_score += 1
        elif cmf < -0.1:
            volume_score -= 3
        else:
            volume_score -= 1

    momentum_score += max(0, min(10, volume_score))

    # 7. RELATIVE STRENGTH (0-10 points)
    rs_score = 5  # neutral

    if mansfield_rs is not None:
        if mansfield_rs > 20:
            rs_score = 10  # Strong outperformance
        elif mansfield_rs > 10:
            rs_score = 8
        elif mansfield_rs > 0:
            rs_score = 6
        elif mansfield_rs > -10:
            rs_score = 4
        elif mansfield_rs > -20:
            rs_score = 2
        else:
            rs_score = 0  # Strong underperformance

    momentum_score += rs_score

    # 8. MOMENTUM CONSISTENCY (0-6 points)
    consistency = 0

    # Multi-timeframe alignment
    if price_change_1d > 0 and price_change_5d > 0 and price_change_30d > 0:
        consistency = 6  # All positive
    elif price_change_5d > 0 and price_change_30d > 0:
        consistency = 4  # Medium/long term positive
    elif price_change_1d > 0 and price_change_5d > 0:
        consistency = 3  # Short/medium term positive
    else:
        consistency = 0

    momentum_score += consistency

    return max(0, min(100, momentum_score))
```

### Phase 3: Update Frontend to Display All Components
**In `ScoresDashboard.jsx`** - add detailed momentum component breakdown:

```jsx
{/* Momentum Score Section */}
<Accordion expanded={expanded === 'momentum'} onChange={handleChange('momentum')}>
  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
    <Typography variant="h6">Momentum Score: {stock.momentum_score?.toFixed(1) || 'N/A'}</Typography>
  </AccordionSummary>
  <AccordionDetails>
    <Grid container spacing={2}>
      {/* Score Visualization */}
      <Grid item xs={12}>
        <BarChart width={600} height={200} data={[...]}>
          <Bar dataKey="value" fill={theme.palette.primary.main} />
        </BarChart>
      </Grid>

      {/* Component Breakdown Table */}
      <Grid item xs={12}>
        <TableContainer component={Paper}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Component</TableCell>
                <TableCell align="right">Value</TableCell>
                <TableCell align="right">Score Contribution</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell>Short-Term Momentum</TableCell>
                <TableCell align="right">
                  1d: {momentum_components.price_change_1d}%
                  5d: {momentum_components.price_change_5d}%
                </TableCell>
                <TableCell align="right">{momentum_components.short_term_score}/20</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>RSI</TableCell>
                <TableCell align="right">{stock.rsi?.toFixed(2) || 'N/A'}</TableCell>
                <TableCell align="right">
                  {stock.rsi > 70 ? 'Overbought' : stock.rsi < 30 ? 'Oversold' : 'Neutral'}
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell>MACD</TableCell>
                <TableCell align="right">{stock.macd?.toFixed(4) || 'N/A'}</TableCell>
                <TableCell align="right">
                  {stock.macd > 0 ? 'Bullish' : 'Bearish'}
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell>ADX (Trend Strength)</TableCell>
                <TableCell align="right">{momentum_components.adx?.toFixed(2) || 'N/A'}</TableCell>
                <TableCell align="right">
                  {momentum_components.adx > 25 ? 'Strong Trend' : 'Weak Trend'}
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Money Flow Index</TableCell>
                <TableCell align="right">{momentum_components.mfi?.toFixed(2) || 'N/A'}</TableCell>
                <TableCell align="right">Volume Confirmation</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Relative Strength (vs SPY)</TableCell>
                <TableCell align="right">{momentum_components.mansfield_rs?.toFixed(2) || 'N/A'}%</TableCell>
                <TableCell align="right">
                  {momentum_components.mansfield_rs > 0 ? 'Outperforming' : 'Underperforming'}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </TableContainer>
      </Grid>

      {/* Momentum Indicators Chart */}
      <Grid item xs={12}>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={momentumHistory}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="rsi" stroke="#8884d8" name="RSI" />
            <Line type="monotone" dataKey="macd" stroke="#82ca9d" name="MACD" />
          </LineChart>
        </ResponsiveContainer>
      </Grid>
    </Grid>
  </AccordionDetails>
</Accordion>
```

### Phase 4: Add to Technicals Page
Ensure all new momentum indicators are displayed on the technicals page with proper formatting and explanations.

### Phase 5: Update API to Return Momentum Components
**In `webapp/lambda/routes/scores.js`** - fetch and return momentum component data:

```javascript
// Fetch momentum components from technical_data_daily
const momentumComponents = await db.query(`
  SELECT
    rsi, macd, macd_hist, adx, plus_di, minus_di,
    mfi, roc, mom, ad, cmf, mansfield_rs
  FROM technical_data_daily
  WHERE symbol = $1
  ORDER BY date DESC
  LIMIT 1
`, [symbol]);

// Add to response
momentum_components: {
  rsi: parseFloat(momentumComponents.rows[0]?.rsi) || null,
  macd: parseFloat(momentumComponents.rows[0]?.macd) || null,
  adx: parseFloat(momentumComponents.rows[0]?.adx) || null,
  mfi: parseFloat(momentumComponents.rows[0]?.mfi) || null,
  mansfield_rs: parseFloat(momentumComponents.rows[0]?.mansfield_rs) || null,
  // ... other components
}
```

---

## Testing Plan

1. **Unit Tests**: Test momentum calculation function with edge cases
2. **Integration Tests**: Verify data flows from loaders → scores → API → frontend
3. **Backtesting**: Compare new momentum score vs old score on historical data
4. **Performance**: Ensure score calculation completes within acceptable time
5. **Data Quality**: Verify all indicators have reasonable values, no NaN/Inf

---

## Success Criteria

✅ Momentum score uses 8+ distinct momentum indicators
✅ All components properly weighted and normalized (0-100)
✅ Frontend displays all momentum components with clear explanations
✅ Technicals page shows all raw momentum indicator values
✅ All tests passing
✅ Documentation updated
✅ Score correlates with actual price momentum in backtests

---

## Next: Sentiment Score Enhancement

After momentum is complete, apply similar methodology to sentiment score with:
- Reddit sentiment (mentions, upvotes, comment sentiment)
- Google Trends data
- Twitter/StockTwits mentions
- Analyst ratings (comprehensive)
- News sentiment
- Social media aggregate sentiment

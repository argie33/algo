# Market Internals Quick Reference Guide

## 🚀 What's New

Your Markets page now shows **comprehensive market internals data** with real-time market breadth, technical analysis, and positioning metrics.

## 📊 New Data Sections on Market Overview Page

### 1. **Overextension Alert** (Top of Market Internals)
Color-coded alert showing market condition:
- 🔴 **Extreme** - Market very overbought/oversold, action needed
- 🟠 **Strong** - Market extended, watch for reversal
- 🟢 **Normal** - Healthy trading range

### 2. **Market Breadth Cards**
Shows the number of stocks:
- **Advancing** - How many up
- **Declining** - How many down
- **Unchanged** - Flat
- **A/D Ratio** - Relationship between advances and declines
- **Breadth Percentile** - Where market ranks (0-100%)

### 3. **Stocks Above Moving Averages Table**
Three key technical levels:

| MA | What It Means | When It's High | When It's Low |
|----|---------------|---|---|
| **20-day** | Short-term momentum | Strong recent rally | Weakness emerging |
| **50-day** | Intermediate trend | Intermediate uptrend | Intermediate weakness |
| **200-day** | Long-term trend | Bull market is intact | Bear market signals |

Each shows:
- Count of stocks above
- Percentage of stocks above
- Average distance from the MA (how extended)

### 4. **Market Extremes (90-Day Analysis)**
Statistical analysis showing:
- **Current vs Distribution** - Where breadth is vs recent history
- **Percentiles** - 25th, 50th, 75th, 90th ranges
- **Standard Deviations** - How many σ from mean
  - 0 σ = normal
  - +2 σ = extremely overbought
  - -2 σ = extremely oversold

### 5. **Positioning & Sentiment**
- **AAII (Retail)** - What retail investors think
- **NAAIM (Professionals)** - What pros think
- **Institutional Data** - Ownership patterns, short interest
- **Fear & Greed Index** - Market sentiment (0-100)
  - <25 = Extreme fear (potential buying opportunity)
  - >75 = Extreme greed (potential selling opportunity)

## 💡 How to Use This Data

### Finding Overbought Markets
```
IF breadth_rank > 80% AND % above 200-day > 75%
THEN market may be overextended → consider taking profits
```

### Finding Oversold Markets
```
IF breadth_rank < 20% AND % above 200-day < 30%
AND Fear & Greed < 25
THEN market may be near bottom → potential buying opportunity
```

### Confirming Trends
```
% above 200-day:
- > 80% = Strong uptrend confirmed
- 50-80% = Moderate uptrend
- < 50% = Downtrend starting
```

### Watching for Reversals
```
IF StdDev from Mean > 2.0 (up or down)
THEN market in extremes → watch for reversal
```

## 🎯 Key Metrics at a Glance

| Metric | Bullish | Bearish | Neutral |
|--------|---------|---------|---------|
| Breadth Rank | >70% | <30% | 30-70% |
| % Above 200MA | >75% | <25% | 25-75% |
| A/D Ratio | <1.0 | >1.0 | ~1.0 |
| Std Deviations | >+1.5 | <-1.5 | ±1.5 |
| Fear & Greed | <30 or >75 | N/A | 30-75 |

## 📈 Market Internals Checklist

### Before a Major Position
- [ ] Check overextension level
- [ ] Look at % above 200-day MA
- [ ] Check breadth percentile rank
- [ ] Review Fear & Greed index
- [ ] See standard deviations from mean
- [ ] Note AAII vs NAAIM divergence

### During Uptrend
- [ ] Monitor breadth percentile (if >90%, watch for pullback)
- [ ] Check % above 50/200 day (should be >70% for healthy trend)
- [ ] Watch A/D ratio (should be <1.0 for ups)
- [ ] If % above 200MA drops below 50%, trend may be breaking

### During Downtrend
- [ ] Monitor breadth percentile (if <10%, watch for bounce)
- [ ] Check % above 200-day (should be <30% for severe downtrend)
- [ ] Watch A/D ratio (should be >1.0 for downs)
- [ ] When % above 200MA rises above 50%, uptrend may be starting

## 🔄 Data Refresh Rates

- **Component refreshes**: Every 60 seconds
- **Database queries**: Real-time on demand
- **Price data**: Daily (at market close)
- **Sentiment data**: Weekly (AAII, NAAIM)
- **Fear & Greed**: Daily

## 🛠️ Technical Details

### API Endpoint
```
GET /api/market/internals
```

### Response Time
- Typical: <2 seconds
- All 4 queries run in parallel for speed

### Data Freshness
- All real data from your database
- No mock values or fallbacks
- Clear errors if data unavailable

### Performance
- Optimized SQL queries with PERCENTILE_CONT
- Database indexes on date fields
- React Query caching (30 second cache)

## ⚠️ Important Notes

### Real Data Only
- No hardcoded values
- No fallback data
- Clear error messages if data missing
- Requires proper data loading via existing loaders

### Requires Data Tables
These tables must be populated for full functionality:
- `price_daily` - Must have sma_20, sma_50, sma_200 fields
- `positioning_metrics` - Institutional data
- `aaii_sentiment` - Retail sentiment
- `naaim` - Professional positioning
- `fear_greed_index` - Sentiment indicator

### Error Handling
If you see errors on page:
1. Check that data loader scripts are running
2. Verify tables exist and have data
3. Check browser console for detailed errors
4. Database connection may be down

## 🚀 Next Steps

1. **Visit Market Overview Page** - See Market Internals section
2. **Bookmark Key Metrics** - Note what normal ranges look like for your market
3. **Set Alerts** - Watch for breadth >90% or <10%
4. **Compare with Price** - See if market internals confirm price action
5. **Track Over Time** - Use historical data to learn patterns

## 📚 Further Learning

### What to Monitor Daily
- Breadth percentile (risk of reversal if >85%)
- % above 200-day MA (trend strength)
- Fear & Greed (emotion extremes)

### What to Monitor Weekly
- Standard deviations trend (is extremeness increasing?)
- AAII vs NAAIM divergence (sentiment extremes)
- Short interest changes (potential squeezes)

### What to Check Monthly
- 90-day percentile boundaries (market ranges shift)
- Institutional ownership changes
- Sector breadth patterns (which areas leading/lagging)

## 💬 Questions?

All data is calculated from your actual database tables. Check:
- `/MARKET_INTERNALS_IMPLEMENTATION.md` - Full technical details
- `/api/market/internals` endpoint - Raw data structure
- Component source: `MarketInternals.jsx` - Display logic

---

**Updated**: Market Internals system now live on Market Overview page!

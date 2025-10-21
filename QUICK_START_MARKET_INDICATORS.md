# Quick Start: Market Indicators

## ⚡ 3 Steps to Get It Working

### Step 1: Verify Database Has Data
```bash
# Check yield curve data
psql -U postgres -d stocks -c \
  "SELECT symbol, price, date FROM market_data \
   WHERE symbol IN ('^TNX', '^IRX') ORDER BY date DESC LIMIT 2;"

# Expected output:
#  symbol | price | date
# --------+-------+----------
#  ^TNX   | 4.35  | 2024-10-21
#  ^IRX   | 5.42  | 2024-10-21

# Check professional sentiment
psql -U postgres -d stocks -c \
  "SELECT date, naaim_number_mean, bullish \
   FROM naaim ORDER BY date DESC LIMIT 2;"

# Expected output:
#    date   | naaim_number_mean | bullish
# -----------+-------------------+--------
#  2024-10-21|            68.5   |  68.5

# Check retail sentiment
psql -U postgres -d stocks -c \
  "SELECT date, bullish, neutral, bearish \
   FROM aaii_sentiment ORDER BY date DESC LIMIT 2;"

# Expected output:
#    date   | bullish | neutral | bearish
# -----------+---------+---------+--------
#  2024-10-21|   45.2  |  28.1   |  26.7
```

### Step 2: If Data is Missing, Load It
```bash
# Load everything (this will take 5-10 minutes)
python3 /home/stocks/algo/loadmarket.py      # Treasuries, indices, VIX
python3 /home/stocks/algo/loadpricedaily.py  # Daily stock prices
python3 /home/stocks/algo/loadnaaim.py       # Professional sentiment
python3 /home/stocks/algo/loadaaiidata.py    # Retail sentiment
```

### Step 3: Test the Endpoints
```bash
# Start your backend server
cd /home/stocks/algo/webapp/lambda
npm start  # or however you start it

# Then test each endpoint:

# Test 1: Yield Curve (in /api/market/overview response)
curl http://localhost:3001/api/market/overview | jq '.data.yield_curve'

# Test 2: McClellan Oscillator
curl http://localhost:3001/api/market/mcclellan-oscillator

# Test 3: Sentiment Divergence
curl http://localhost:3001/api/market/sentiment-divergence
```

---

## 🎯 What Each Indicator Shows

### 1️⃣ Yield Curve (10Y-2Y Spread)
**What**: Difference between 10-year and 2-year treasury yields
**Why**: Inverted yield curves historically signal recessions
**Data**: ^TNX and ^IRX from market_data table
**Updates**: Daily after market close

```
Normal Curve:   10Y (4.35) - 2Y (5.42) = -1.07 ❌ INVERTED
Normal Curve:   10Y (4.35) - 2Y (2.42) =  +1.93 ✅ NORMAL
```

### 2️⃣ McClellan Oscillator
**What**: Breadth momentum indicator
**Why**: Shows if market advances are outpacing declines
**Data**: Calculated from price_daily (90 days of open/close)
**Updates**: Daily after market close

```
Positive (bullish):  Advances outpacing declines
Negative (bearish):  Declines outpacing advances
```

### 3️⃣ Sentiment Divergence
**What**: Professional (NAAIM) vs Retail (AAII) bullish sentiment
**Why**: Shows if retail is too bullish while pros are reducing exposure
**Data**: naaim (daily) and aaii_sentiment (weekly) tables
**Updates**: Daily (NAAIM) or Weekly (AAII)

```
Divergence > +10%:  Retail extremely bullish, professionals cautious
Divergence < -10%:  Professionals bullish, retail cautious (contrarian signal)
```

---

## ✅ Verification Checklist

- [ ] psql query for ^TNX and ^IRX returns 2 rows with prices
- [ ] psql query for naaim returns at least 1 row with recent data
- [ ] psql query for aaii_sentiment returns at least 1 row with recent data
- [ ] Backend /api/market/overview returns yield_curve in response
- [ ] Backend /api/market/mcclellan-oscillator returns current_value
- [ ] Backend /api/market/sentiment-divergence returns current divergence
- [ ] Frontend Market Overview page loads all three new indicators
- [ ] Yield Curve card shows spread and inversion status
- [ ] McClellan chart shows breadth momentum trend
- [ ] Sentiment chart shows professional vs retail comparison

---

## 🐛 Troubleshooting

### Issue: "Table not found" error
**Solution**: Run the data loaders first
```bash
python3 /home/stocks/algo/loadmarket.py
python3 /home/stocks/algo/loadnaaim.py
python3 /home/stocks/algo/loadaaiidata.py
```

### Issue: No data returned (empty arrays/nulls)
**Solution**: Check if loaders actually fetched data
```bash
# Check what loaders updated recently
psql -U postgres -d stocks -c \
  "SELECT script_name, last_run FROM last_updated \
   ORDER BY last_run DESC LIMIT 10;"
```

### Issue: "column X does not exist" error
**Already Fixed**: Column names have been corrected
- market_data uses: `symbol`, `price` (NOT ticker, current_price)
- naaim uses: `date`, `naaim_number_mean`, `bullish`
- aaii_sentiment uses: `date`, `bullish`, `neutral`, `bearish`

### Issue: Frontend shows "No data available"
**Check**:
1. Backend is returning data from endpoints
2. Frontend components are receiving the data props
3. React Query cache is working

```bash
# Test backend response directly
curl http://localhost:3001/api/market/mcclellan-oscillator | jq '.'
```

---

## 📊 Data Loading Guide

### If You Need to Load Fresh Data

```bash
# Market data (treasuries, indices, VIX, sector ETFs)
python3 /home/stocks/algo/loadmarket.py
# Expected: "Market data loading complete"

# Daily stock prices
python3 /home/stocks/algo/loadpricedaily.py
# Expected: "Price data loading complete"

# Professional sentiment (weekly updates from NAAIM)
python3 /home/stocks/algo/loadnaaim.py
# Expected: "NAAIM data loading complete"

# Retail sentiment (weekly from AAII)
python3 /home/stocks/algo/loadaaiidata.py
# Expected: "AAII Sentiment loading complete"
```

### Schedule for Regular Updates
```bash
# Add to crontab for automatic updates:
0 16 * * 1-5  python3 /home/stocks/algo/loadmarket.py      # 4 PM daily (after market close)
0 17 * * 1-5  python3 /home/stocks/algo/loadpricedaily.py  # 5 PM daily
0 6 * * 1     python3 /home/stocks/algo/loadnaaim.py       # 6 AM Monday (NAAIM releases Friday)
0 6 * * 2     python3 /home/stocks/algo/loadaaiidata.py    # 6 AM Tuesday (AAII releases Wednesday)
```

---

## 📱 Frontend Display

Once working, the Market Overview page will show:

**Top Row**:
- Yield Curve Card (left 1/3): Shows 10Y-2Y spread, inverted warning
- McClellan Chart (right 2/3): Shows breadth momentum trend

**Full Width Below**:
- Sentiment Divergence Chart: Shows professional vs retail comparison

All three update every 60 seconds automatically.

---

## 💡 Pro Tips

1. **Yield Curve**: Watch for inversions - they're historically accurate recession predictors
2. **McClellan**: Combine with price action - strong price with positive McClellan = confirmed strength
3. **Sentiment**: Use divergence for contrarian signals - when retail is extremely bullish, watch for reversals

---

## Need Help?

**Check these files for detailed info**:
- `MARKET_INDICATORS_FIXED.md` - Full technical details on what was fixed
- `TEST_MARKET_ENDPOINTS.md` - Data verification queries
- Database documentation in `START_HERE_DATABASE.md`


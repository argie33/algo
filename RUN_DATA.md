# RUN DATA LOADERS - Quick Start Guide

## 🚀 FASTEST WAY TO GET ALL DATA

### Option 1: Run Master Script (Recommended)
```bash
# Quick load (Tier 1+2) - 1-2 hours, gets you 90% of data
bash run_data_loaders.sh quick

# Full load (Tier 1-3) - 3-4 hours, adds financial statements
bash run_data_loaders.sh tier3

# Complete load (Everything) - 5-6 hours
bash run_data_loaders.sh all
```

---

### Option 2: Manual Step-by-Step

#### Step 1: Create Schema (Required - do this FIRST)
```bash
python3 init_database.py
```
**Output:** Should say "✓ Schema initialization complete!"

#### Step 2: Load Stock Symbols (Required - foundation for everything)
```bash
python3 loadstocksymbols.py
```
**Wait for:** ~5000 symbols to load

#### Step 3: Load Core Data (Run in parallel, ~1-2 hours)
```bash
# Terminal 1
python3 loadlatestpricedaily.py

# Terminal 2 (in parallel)
python3 loaddailycompanydata.py
```

#### Step 4: Load Trading Signals (Run in parallel, ~30 min)
```bash
# Terminal 1
python3 loadbuyselldaily.py

# Terminal 2 (in parallel)
python3 loadfactormetrics.py

# Terminal 3 (in parallel)
python3 loadsectors.py

# Terminal 4 (in parallel)
python3 loadearningshistory.py
```

#### Step 5: Load Financial Statements (Optional, ~1 hour)
```bash
# Run these in parallel
python3 loadannualincomestatement.py &
python3 loadannualbalancesheet.py &
python3 loadannualcashflow.py &
python3 loadquarterlyincomestatement.py &
python3 loadquarterlybalancesheet.py &
python3 loadquarterlycashflow.py &
wait
```

#### Step 6: Load Sentiment Data (Optional, ~5 min)
```bash
python3 loadaaiidata.py
python3 loadnaaim.py
python3 loadfeargreed.py
python3 loadsentiment.py
```

---

## ✅ VERIFY DATA LOADED

After running loaders, check that data exists:

### Method 1: Check via API
```bash
# Start your API server first
node webapp/lambda/index.js

# In another terminal, check diagnostics
curl http://localhost:3001/api/diagnostics | jq .
```

Should show table row counts like:
```json
{
  "stock_symbols": 5000,
  "price_daily": 1200000,
  "company_profile": 5000,
  "buy_sell_daily": 1200000,
  ...
}
```

### Method 2: Check via Database
```bash
# If you have psql installed
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_symbols;"
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM price_daily;"
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM company_profile;"
```

---

## 📊 WHAT YOU GET AT EACH TIER

### Tier 1 (Quick) - ~1 hour
- ✅ 5000+ stock symbols
- ✅ Latest daily prices
- ✅ Company profiles
- ✅ Key metrics
- ✅ Can search stocks, view company info

### Tier 2 (Fast) - +30 min
- ✅ Everything from Tier 1, PLUS:
- ✅ Trading signals (buy/sell)
- ✅ Technical indicators
- ✅ Sector rankings
- ✅ Earnings data
- ✅ Quality/growth/value metrics
- ✅ Can see signals and trade analysis

### Tier 3 (Full) - +1-2 hours
- ✅ Everything from Tier 2, PLUS:
- ✅ Annual financial statements
- ✅ Quarterly financial statements
- ✅ Cash flow analysis
- ✅ Can see complete financial pages

### All Tiers (Complete) - +30 min
- ✅ Everything from Tier 3, PLUS:
- ✅ Sentiment analysis
- ✅ Market indices
- ✅ Commodities (optional)

---

## 🔧 ENVIRONMENT SETUP

Make sure you have `.env.local` in the project root:

```bash
# Database (local development)
DB_HOST=localhost
DB_PORT=5432
DB_USER=stocks
DB_PASSWORD=<your_password>
DB_NAME=stocks

# API Keys (optional but recommended for full data)
FRED_API_KEY=<your_key>
ALPACA_API_KEY=<your_key>
ALPACA_API_SECRET=<your_secret>

# JWT for manual trades
JWT_SECRET=<any_random_string>
```

---

## ⚠️ COMMON ISSUES & FIXES

### "Database connection failed"
```
Problem: Can't connect to PostgreSQL
Fix:
1. Verify PostgreSQL is running: psql -h localhost -U stocks
2. Check .env.local has correct credentials
3. Make sure DB_HOST=localhost (not 127.0.0.1)
```

### "Table does not exist" errors
```
Problem: Loaders crashed before init_database.py ran
Fix:
1. Run: python3 init_database.py
2. Then rerun your loaders
```

### Loader times out after 1 hour
```
Problem: Too slow, network issues, or rate-limited
Fix:
1. Check internet connection
2. Try running one loader at a time instead of parallel
3. Check logs in /tmp/ for specific errors
```

### Some stocks have no data
```
Normal! Some stocks:
- Don't have earnings data (startups, OTC)
- Don't have analyst ratings
- Have sparse price history
This is expected for ~10-15% of 5000 stocks
```

---

## 🚀 NEXT: START YOUR FRONTEND

Once data is loaded, start the full stack:

```bash
# Terminal 1: API Server
node webapp/lambda/index.js

# Terminal 2: Frontend
cd webapp/frontend-admin
npm run dev

# Open browser
http://localhost:5174
```

---

## 📈 EXPECTED ROW COUNTS

After successful load:

| Table | Expected Rows |
|-------|---------------|
| stock_symbols | ~5,000 |
| price_daily | ~1,200,000 |
| company_profile | ~5,000 |
| key_metrics | ~5,000 |
| earnings_history | ~20,000 |
| buy_sell_daily | ~1,200,000 |
| technical_data_daily | ~1,200,000 |
| quality_metrics | ~4,500 |
| growth_metrics | ~4,500 |
| momentum_metrics | ~5,000 |
| stability_metrics | ~5,000 |
| value_metrics | ~4,500 |
| sector_ranking | ~50 |
| industry_ranking | ~500 |

---

## 💡 TIPS

1. **Run in screen/tmux** if you want background loaders:
   ```bash
   screen -S loaders
   bash run_data_loaders.sh quick
   # Detach: Ctrl+A then D
   # Reattach: screen -r loaders
   ```

2. **Check progress** while loaders run:
   ```bash
   # Watch database grow
   watch -n 5 "psql -h localhost -U stocks -d stocks -c 'SELECT count(*) FROM price_daily;'"
   ```

3. **Don't interrupt** - loaders use transactions and cleanup properly on failure

4. **Rerun safely** - loaders use `ON CONFLICT DO UPDATE`, so rerunning updates instead of duplicating

---

## ❓ HELP

Check specific loader issues:
```bash
# See what's actually being inserted
tail -f /tmp/loadpricedaily.log

# Or run with verbose output
python3 -v loadstocksymbols.py
```

---

## GO!

**Ready? Run this now:**

```bash
bash run_data_loaders.sh quick
```

That's it! Grab a coffee ☕ and come back in 1-2 hours with a fully populated database.

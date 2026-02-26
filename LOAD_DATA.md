# Data Loading Guide - Algo Stock Platform

## 📋 Overview

The application needs market data loaded into the database. There are **3 phases** of data loading:

1. **Phase 1 - Foundation (REQUIRED)**: Stock symbols
2. **Phase 2 - Core Data (REQUIRED)**: Prices and fundamentals needed for scores/signals
3. **Phase 3 - Complete Data (OPTIONAL)**: Additional data for all features

---

## ⚠️ Prerequisites

Before loading data, verify:

```bash
# 1. PostgreSQL is running
psql -h localhost -U stocks -d stocks -c "SELECT 1;"
# Should return: 1

# 2. Backend server is running (in another terminal)
curl http://localhost:3001/health
# Should return: {"status":"ok"}

# 3. Python environment is ready
cd /home/arger/algo
source venv/bin/activate
python3 --version
# Should show: Python 3.x.x
```

---

## 🚀 Phase 1: Foundation Data (REQUIRED FIRST)

This loads the list of all stocks and ETFs.

```bash
cd /home/arger/algo
source venv/bin/activate

# Load stock symbols (required - must run first)
echo "Loading stock symbols..."
python3 loadstocksymbols.py

# Expected output:
# ✅ Loaded XXX stock symbols
# ✅ Loaded YYY ETF symbols
```

**What it loads:**
- `stock_symbols` table - All stock tickers
- `etf_symbols` table - All ETF tickers

**Time:** ~2-5 minutes

---

## 🎯 Phase 2: Core Data (REQUIRED FOR SCORES/SIGNALS)

After Phase 1 completes, load these in order:

### 2.1 - Daily Prices (Required)

```bash
python3 loadpricedaily.py
```

**What it loads:**
- `price_daily` table - Daily OHLCV data for all stocks
- Historical price data for technical analysis

**Time:** ~5-10 minutes
**Note:** This is essential for all score calculations

### 2.2 - Company Profiles (Required)

```bash
python3 loadstocksymbols.py  # May need to re-run or check for company info loader
# OR if there's a loadcompanyinfo.py:
python3 loadcompanyinfo.py
```

**What it loads:**
- `company_profile` table - Company info, sector, industry
- Required for fundamental metrics and filters

**Time:** ~3-5 minutes

### 2.3 - Key Metrics & Fundamentals (For Scores)

```bash
# Load fundamental metrics
python3 loadfundamentalmetrics.py

# Or if separate loaders exist:
python3 loadannualbalancesheet.py
python3 loadannualincomestatement.py
python3 loadannualcashflow.py
```

**What it loads:**
- `fundamental_metrics` table - PE ratio, PB, PS, PEG, dividend yield, etc.
- `annual_balance_sheet` table - Assets, liabilities, debt
- `annual_income_statement` table - Revenue, income
- `annual_cash_flow` table - Cash flow data

**Time:** ~5-10 minutes
**Why:** Required to calculate value scores

### 2.4 - Technical Indicators & Signals (For Scores/Signals)

```bash
# Load technical indicators
python3 loadtechnicalindicators.py

# Load buy/sell signals
python3 loadbuysellDaily.py
python3 loadbuysellweekly.py
python3 loadbuysellmonthly.py
```

**What it loads:**
- Technical indicator tables (RSI, MACD, Bollinger Bands, etc.)
- `buy_sell_daily/weekly/monthly` tables - Trading signals
- Required for momentum scores and signal generation

**Time:** ~10-15 minutes
**Why:** Needed for momentum scores and trading signals

### 2.5 - Stock Scores (Optional but Recommended)

```bash
# Load pre-calculated stock scores
python3 loadstockscores.py
```

**What it loads:**
- `stock_scores` table - Composite, momentum, value, quality, growth scores
- Pre-calculated scores for all stocks

**Time:** ~5 minutes
**Why:** Provides overall stock ratings used on main dashboard

---

## 📊 Phase 3: Complete Data (OPTIONAL - For All Features)

These loaders provide data for additional pages and features:

```bash
# Market data and economic indicators
python3 loadmarket.py
python3 loadecondata.py

# ETF data
python3 loadetfpricedaily.py
python3 loadetfpriceweekly.py
python3 loadetfpricemonthly.py

# Additional metrics
python3 loadmomentummetrics.py
python3 loadgrowthmetrics.py
python3 loadqualitymetrics.py
python3 loadpositioningmetrics.py

# Earnings and analyst data
python3 loadearningshistory.py
python3 loadearningsrevisions.py
python3 loadanalystsentiment.py
python3 loadanalystupgradedowngrade.py

# Other data
python3 loadsentiment.py
python3 loadnews.py
python3 loadoptionschains.py
python3 loadseasonality.py
python3 loadrelativeperformance.py
```

**Time:** 30+ minutes total
**Why:** Populates all pages with comprehensive data

---

## 🔄 Automated Loading

Run all loaders in sequence (takes 1-2 hours):

```bash
# Option 1: Run all loaders with monitoring
bash run_all_loaders_monitored.sh

# Option 2: Run all loaders in background
bash run_all_loaders.sh

# Option 3: Use the phase-based script
bash run_all_phases.sh
```

---

## ✅ Recommended Starting Plan

### Minimum Setup (30-40 minutes)

For a working app with scores and signals:

```bash
cd /home/arger/algo
source venv/bin/activate

# Phase 1
echo "Phase 1: Loading foundation data..."
python3 loadstocksymbols.py

# Phase 2 - Core Data
echo "Phase 2a: Loading daily prices..."
python3 loadpricedaily.py

echo "Phase 2b: Loading fundamental metrics..."
python3 loadfundamentalmetrics.py

echo "Phase 2c: Loading technical indicators..."
python3 loadtechnicalindicators.py

echo "Phase 2d: Loading buy/sell signals..."
python3 loadbuysellDaily.py

echo "Phase 2e: Loading stock scores..."
python3 loadstockscores.py

echo "✅ All core data loaded!"
```

### Full Setup (1-2 hours)

For a feature-complete application:

```bash
bash run_all_loaders_monitored.sh
```

---

## 🗂️ Database Tables Summary

### After Phase 1 (Foundation)
- `stock_symbols` ✅
- `etf_symbols` ✅

### After Phase 2 (Core Data)
- `price_daily` ✅
- `company_profile` ✅
- `fundamental_metrics` ✅
- `technical indicators` ✅
- `buy_sell_daily/weekly/monthly` ✅
- `stock_scores` ✅
- All tables needed for dashboard ✅

### After Phase 3 (Complete)
- All 50+ tables populated ✅
- All features available ✅

---

## 📈 What Features Become Available After Each Phase

| Phase | Loaded Data | Available Features |
|-------|-------------|-------------------|
| **1** | Stock symbols | Nothing yet (symbols only) |
| **2a** | + Prices | Price charts, technical analysis |
| **2b** | + Fundamentals | Valuation metrics, P/E ratio filtering |
| **2c** | + Technicals | Technical indicators, RSI, MACD |
| **2d** | + Signals | Buy/sell signals, trading recommendations |
| **2e** | + Scores | Stock ranking, composite scores |
| **3** | + Everything | Full feature set |

---

## 🐛 Troubleshooting Data Loading

### Loader Hangs or Takes Too Long

```bash
# Press Ctrl+C to stop
# Check logs
tail -100 /tmp/loader_output.log

# Try with smaller batch
# Edit the loader script and reduce batch size
```

### Database Connection Error

```bash
# Verify PostgreSQL is running
sudo systemctl status postgresql

# Test connection
psql -h localhost -U stocks -d stocks -c "SELECT 1;"

# Check .env.local has correct credentials
cat .env.local | grep DB_
```

### "Module not found" Error

```bash
# Reinstall Python dependencies
source venv/bin/activate
pip install -r requirements.txt

# Try again
python3 loadstocksymbols.py
```

### Data Not Appearing in Frontend

```bash
# Check if data was inserted
PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_symbols;"

# Restart backend server (may have cached empty state)
# Stop with Ctrl+C and restart:
node index.js
```

---

## 📝 Logging and Monitoring

Check loader progress:

```bash
# Watch logs in real-time
tail -f /tmp/loader_output.log

# Check how many symbols were loaded
PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) as stocks FROM stock_symbols;"

# Check how many price records
PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) as prices FROM price_daily;"

# Check scores
PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) as scores FROM stock_scores;"
```

---

## 🎯 Next Steps After Data Loading

1. ✅ Verify data loaded: Check counts above
2. ✅ Restart backend server to clear cache
3. ✅ Refresh frontend in browser
4. ✅ Check main page shows stock scores
5. ✅ Check signals appear on signal pages
6. ✅ Load more data as needed for additional features

---

## 💡 Quick Commands

```bash
# Setup environment
cd /home/arger/algo
source venv/bin/activate

# Load everything (recommended)
bash run_all_loaders_monitored.sh

# Just phase 2 (most important)
python3 loadstocksymbols.py && \
python3 loadpricedaily.py && \
python3 loadfundamentalmetrics.py && \
python3 loadtechnicalindicators.py && \
python3 loadbuysellDaily.py && \
python3 loadstockscores.py

# Check database status
psql -h localhost -U stocks -d stocks -c "SELECT schemaname, tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"
```

---

**You're ready to load data!** Start with Phase 1, then move to Phase 2. 🚀

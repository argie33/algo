# Comprehensive Financial Data Loading Plan for Admin Dashboard

**Date Created:** February 7, 2026
**Database:** PostgreSQL (Local Development: stocks@localhost/stocks)
**Total Loaders:** 57 Python scripts
**Estimated Total Load Time:** 2-4 hours (initial full load)

---

## 1. DATABASE CONNECTIVITY & SETUP

### 1.1 Start PostgreSQL with Docker Compose

```bash
# From /home/stocks/algo directory
cd /home/stocks/algo

# Start PostgreSQL container (creates fresh database)
docker-compose up -d

# Verify postgres is healthy
docker-compose ps

# Expected output should show 'postgres' service as 'healthy'
```

### 1.2 Verify Database Connection

```bash
# Test connection with psql
PGPASSWORD=stocks psql -h localhost -U stocks -d stocks -c "SELECT 1"

# Expected output: 1 (successful connection)
```

### 1.3 Database Configuration

**Connection Details:**
- **Host:** localhost
- **Port:** 5432
- **User:** stocks
- **Password:** stocks
- **Database:** stocks

**Environment Variables Required:**
```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_PASSWORD=stocks
export DB_NAME=stocks
```

**Fallback Configuration (lib/db.py):**
The loaders will automatically try:
1. AWS Secrets Manager (if `AWS_REGION` and `DB_SECRET_ARN` are set)
2. Environment variables (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`)
3. Default values: `localhost:5432` with user `stocks`

### 1.4 Verify Database Schema Readiness

```bash
# Check if tables exist
PGPASSWORD=stocks psql -h localhost -U stocks -d stocks << 'EOF'
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
EOF

# Expected: Initially empty (loaders will create tables)
```

---

## 2. LOAD ORDER WITH DEPENDENCIES

### Dependency Graph:
```
[FOUNDATION]
  ├─ loadstocksymbols.py (Stock & ETF symbols)
  └─ loadsectors.py (Sector/Industry data)
      │
      ├─ [PRICE DATA] (32 loaders depend on symbols)
      │   ├─ loadpricedaily.py
      │   ├─ loadpriceweekly.py
      │   └─ loadpricemonthly.py
      │       │
      │       └─ [SECONDARY PRICE] (5 loaders depend on price data)
      │           ├─ loadfactormetrics.py
      │           ├─ loadrelativeperformance.py
      │           ├─ loadseasonality.py
      │           └─ loadsectors.py (secondary run)
      │
      └─ [EARNINGS] (2 loaders depend on earnings)
          ├─ loadearningshistory.py
          └─ loadearningssurprise.py
              └─ loadfactormetrics.py

[FINANCIAL STATEMENTS] (8 loaders - independent)
[SENTIMENT/ANALYST] (8 loaders - independent)
[SCORES & METRICS] (4 loaders - requires prior data)
[TECHNICAL INDICATORS] (11 loaders - independent)
[OPTIONAL/SECONDARY] (12 loaders)
```

---

## 3. CRITICAL vs OPTIONAL CLASSIFICATION

### CRITICAL (MUST RUN - Admin Dashboard Core Functions)

| Loader | Purpose | Runtime | Data Impact |
|--------|---------|---------|-------------|
| **loadstocksymbols.py** | Loads all stock and ETF symbols from NASDAQ/NYSE | ~5 min | Creates `stock_symbols` & `etf_symbols` tables |
| **loadsectors.py** | Loads sector/industry classification data | ~3 min | Creates `sectors`, `industries`, `sector_performance` tables |
| **loadpricedaily.py** | Daily OHLCV data for all 5000+ stocks | ~45 min | Creates `price_daily` table; foundation for all metrics |
| **loadearningshistory.py** | Historical earnings data | ~30 min | Creates `earnings_history` table |

**Success Criteria:** Admin dashboard displays:
- Stock lookup (symbols, sectors, industries)
- Price charts (daily data)
- Earnings information
- Portfolio performance

### DEPENDENT (32+ loaders require stock symbols)

Loaders that MUST run after `loadstocksymbols.py`:
- All price loaders (daily, weekly, monthly)
- All financial statement loaders
- All sentiment/analyst loaders
- All fundamental metric loaders
- All technical indicator loaders

### OPTIONAL (12 loaders for enhanced features)

Can be skipped for minimum viable dashboard:
- Economic data (loadeconomdata.py)
- Market indices (loadmarketindices.py)
- Options chains (loadoptionschains.py)
- SEC filings (loadsecfilings.py)
- Calendar events (loadcalendar.py)
- And others...

---

## 4. DETAILED LOAD ORDER (Recommended Sequence)

### Phase 1: FOUNDATION (Required)
**Time: ~10 minutes**
**Must complete before proceeding to Phase 2**

```
1. loadstocksymbols.py          → stock_symbols, etf_symbols
2. loadsectors.py              → sectors, industries, sector_performance
```

### Phase 2: PRICE DATA (Critical)
**Time: ~60 minutes**
**Must complete before Phase 3**

```
3. loadpricedaily.py           → price_daily (5000+ symbols × 10+ years)
4. loadpriceweekly.py          → price_weekly
5. loadpricemonthly.py         → price_monthly
6. loadlatestpricedaily.py     → latest_price_daily (real-time snapshot)
7. loadlatestpriceweekly.py    → latest_price_weekly
8. loadlatestpricemonthly.py   → latest_price_monthly
```

### Phase 3: EARNINGS DATA (Critical)
**Time: ~35 minutes**

```
9. loadearningshistory.py      → earnings_history (full earnings history)
10. loadearningssurprise.py    → earnings_surprise (EPS surprises - depends on earnings_history)
11. loadearningsrevisions.py   → earnings_revisions
12. loadguidance.py            → earnings_guidance
```

### Phase 4A: FINANCIAL STATEMENTS (Highly Recommended)
**Time: ~60 minutes**
**Can run in parallel with 4B if resources permit**

```
13. loadannualincomestatement.py
14. loadannualbalancesheet.py
15. loadannualcashflow.py
16. loadquarterlyincomestatement.py
17. loadquarterlybalancesheet.py
18. loadquarterlycashflow.py
19. loadttmincomestatement.py
20. loadttmcashflow.py
```

### Phase 4B: SENTIMENT & ANALYST DATA (Recommended)
**Time: ~45 minutes**
**Can run in parallel with 4A**

```
21. loadanalystsentiment.py
22. loadanalystupgradedowngrade.py
23. loadnews.py
24. loadsentiment.py
25. loadinsidertransactions.py
```

### Phase 5: SCORES & METRICS (Recommended)
**Time: ~30 minutes**
**Requires Phases 2-4 to be complete**

```
26. loadfactormetrics.py       → (depends on price_daily + earnings_history)
27. loadfundamentalmetrics.py
28. loadpositioningmetrics.py
29. loadstockscores.py         → Comprehensive scoring (depends on all prior)
```

### Phase 6: TECHNICAL INDICATORS (Optional)
**Time: ~40 minutes**

```
30. loadbuyselldaily.py
31. loadbuysellweekly.py
32. loadbuysellmonthly.py
33. loadbuyselldaily_etf.py
34. loadbuysellweekly_etf.py
35. loadbuysellmonthly_etf.py
36. loadrelativeperformance.py → (depends on price_daily)
37. loadseasonality.py         → (depends on price_daily)
38. loadaaiidata.py
39. loadnaaim.py
40. loadsectorranking.py
41. loadindustryranking.py
```

### Phase 7: OPTIONAL/SECONDARY (Nice-to-Have)
**Time: ~45 minutes**

```
42. loadbenchmark.py
43. loadcalendar.py
44. loadcommodities.py
45. loadcoveredcallopportunities.py
46. loaddailycompanydata.py
47. loadecondata.py
48. loadetfsignals.py
49. loadfeargreed.py
50. loadmarket.py
51. loadmarketindices.py
52. loadoptionschains.py
53. loadsecfilings.py
54. loadalpacaportfolio.py     → (requires Alpaca API credentials)
```

---

## 5. DETAILED LOADER SPECIFICATIONS

### Phase 1: FOUNDATION LOADERS

#### 1. loadstocksymbols.py

**Purpose:** Populate stock_symbols and etf_symbols tables
**Data Source:** NASDAQ Trade Reporting System (nasdaqtrader.com)
**Environment Variables:** None required
**Tables Created:**
- `stock_symbols` (primary market stocks)
- `etf_symbols` (ETF tickers)
- `last_updated` (tracking table)

**Expected Output:**
- ~5000-6000 stock symbols
- ~2000+ ETF symbols
- Filtered for valid trading instruments (excludes warrants, preferred stock, SPACs, etc.)

**Runtime:** ~3-5 minutes
**Data Validation:**
```sql
-- Check symbols loaded
SELECT COUNT(*) FROM stock_symbols;  -- Expected: 5000+
SELECT COUNT(*) FROM etf_symbols;    -- Expected: 2000+

-- Verify no duplicates
SELECT symbol, COUNT(*) FROM stock_symbols GROUP BY symbol HAVING COUNT(*) > 1;
SELECT symbol, COUNT(*) FROM etf_symbols GROUP BY symbol HAVING COUNT(*) > 1;
```

**Success Criteria:**
- At least 5000 stocks in `stock_symbols` table
- At least 2000 ETFs in `etf_symbols` table
- No duplicate symbols
- All required columns populated (exchange, security_name, etc.)

**Command:**
```bash
cd /home/stocks/algo
python3 loadstocksymbols.py
```

---

#### 2. loadsectors.py

**Purpose:** Load sector and industry classification for all stocks
**Data Source:** Internal calculation based on stock_symbols
**Environment Variables:** None required
**Dependencies:** Requires `stock_symbols` table populated
**Tables Created/Updated:**
- `sectors` (sector listing)
- `industries` (industry listing)
- `sector_performance` (performance metrics)

**Expected Output:**
- 12-13 sectors (Financials, Technology, Healthcare, etc.)
- 150+ industries
- Performance metrics (1-day, 5-day, 20-day returns, RSI, moving averages)

**Runtime:** ~2-5 minutes (can depend on calculating sector performance)
**Data Validation:**
```sql
-- Check sectors loaded
SELECT COUNT(*) FROM sectors;          -- Expected: 10-15
SELECT COUNT(*) FROM industries;       -- Expected: 100+
SELECT COUNT(*) FROM sector_performance; -- Expected: 10+
```

**Success Criteria:**
- All sectors properly classified
- All stocks have sector/industry assignments
- Sector performance metrics calculated

**Command:**
```bash
cd /home/stocks/algo
python3 loadsectors.py
```

---

### Phase 2: PRICE DATA LOADERS

#### 3. loadpricedaily.py

**Purpose:** Download and store daily OHLCV (Open, High, Low, Close, Volume) data
**Data Source:** Yahoo Finance (yfinance library)
**Environment Variables:** None required
**Dependencies:** Requires `stock_symbols` table
**Tables Created:**
- `price_daily` (historical daily prices)
- Updates `last_updated` tracking table

**Expected Output:**
- 5000+ stocks × 10+ years × 252 trading days = 12M+ price records
- Data range: ~2015-present

**Runtime:** ~45-60 minutes (yfinance rate limiting: ~20 requests/minute)
**Retry Logic:**
- Max retries: 12 per symbol
- Exponential backoff: 0.5-2.0 seconds
- Rate limit backoff: 120 seconds

**Data Validation:**
```sql
-- Check price data loaded
SELECT COUNT(*) FROM price_daily;                    -- Expected: 10M+
SELECT COUNT(DISTINCT symbol) FROM price_daily;     -- Expected: 5000+
SELECT MIN(date), MAX(date) FROM price_daily;       -- Expected: 2015+ to 2026
SELECT symbol, COUNT(*) as records FROM price_daily
GROUP BY symbol ORDER BY records DESC LIMIT 10;     -- Check data density
```

**Success Criteria:**
- All stock symbols have price data
- Date range covers last 10+ years
- No NULL values in OHLC fields
- Volume > 0 for valid trading days

**Command:**
```bash
cd /home/stocks/algo
python3 loadpricedaily.py
```

**Notes:**
- This is the most time-intensive loader
- Can handle network failures gracefully
- Logs progress every 100 symbols
- Memory usage: peak ~500MB during batch processing

---

#### 4-8. loadprice[weekly|monthly].py & loadlatestprice*.py

**Purpose:** Weekly/Monthly aggregated prices and latest snapshots
**Dependencies:** Requires `stock_symbols` table
**Runtime:** 10-15 minutes each
**Tables Created:**
- `price_weekly`, `price_monthly`
- `latest_price_daily`, `latest_price_weekly`, `latest_price_monthly`

**Data Validation:**
```sql
-- Check weekly prices
SELECT COUNT(*) FROM price_weekly;
SELECT COUNT(DISTINCT symbol) FROM price_weekly;

-- Check latest prices (should be same count as symbols)
SELECT COUNT(*) FROM latest_price_daily;
SELECT COUNT(*) FROM latest_price_weekly;
```

**Success Criteria:**
- Weekly prices match daily data
- Latest prices are current (within last business day)
- Volume aggregations are correct

**Commands:**
```bash
cd /home/stocks/algo
python3 loadpriceweekly.py
python3 loadpricemonthly.py
python3 loadlatestpricedaily.py
python3 loadlatestpriceweekly.py
python3 loadlatestpricemonthly.py
```

---

### Phase 3: EARNINGS DATA LOADERS

#### 9. loadearningshistory.py

**Purpose:** Download historical earnings data (EPS, dates, surprises)
**Data Source:** Yahoo Finance earnings data
**Environment Variables:** None required
**Dependencies:** Requires `stock_symbols` table
**Tables Created:**
- `earnings_history` (complete earnings records)

**Expected Output:**
- 5000+ stocks × 10-15 years × 4 quarters = 200K+ earnings records
- Includes actual EPS, estimated EPS, surprise %

**Runtime:** ~25-35 minutes
**Retry Logic:** Similar to price loading, with 5 retries max per batch

**Data Validation:**
```sql
-- Check earnings loaded
SELECT COUNT(*) FROM earnings_history;                    -- Expected: 100K+
SELECT COUNT(DISTINCT symbol) FROM earnings_history;     -- Expected: 3000+
SELECT MIN(date), MAX(date) FROM earnings_history;       -- Expected: 2015+ to 2026
SELECT symbol, COUNT(*) FROM earnings_history
GROUP BY symbol ORDER BY COUNT(*) DESC LIMIT 10;        -- Verify data density
```

**Success Criteria:**
- 3000+ stocks with earnings history
- Date range covers 10+ years
- Actual EPS and expected EPS populated
- Surprise calculations available

**Command:**
```bash
cd /home/stocks/algo
python3 loadearningshistory.py
```

---

#### 10-12. loadearnings[surprise|revisions].py & loadguidance.py

**Purpose:** Earnings surprises, revisions, and forward guidance
**Dependencies:** Requires `earnings_history` for earnings_surprise
**Runtime:** 15-20 minutes each
**Tables Created:**
- `earnings_surprise` (EPS surprise %)
- `earnings_revisions` (analyst revisions)
- `earnings_guidance` (forward guidance)

**Data Validation:**
```sql
SELECT COUNT(*) FROM earnings_surprise;  -- Expected: 20K+
SELECT COUNT(*) FROM earnings_revisions; -- Expected: 20K+
SELECT COUNT(*) FROM earnings_guidance;  -- Expected: 10K+
```

**Commands:**
```bash
cd /home/stocks/algo
python3 loadearningsrevisions.py
python3 loadearningssurprise.py
python3 loadguidance.py
```

---

### Phase 4A: FINANCIAL STATEMENTS LOADERS

#### 13-20. Annual/Quarterly Income, Balance Sheet, Cash Flow

**Purpose:** Load comprehensive financial statement data
**Data Source:** Yahoo Finance / SEC filings
**Dependencies:** Requires `stock_symbols` table
**Runtime:** 8-10 minutes each
**Tables Created:**
- `annual_income_statement`, `quarterly_income_statement`
- `annual_balance_sheet`, `quarterly_balance_sheet`
- `annual_cash_flow`, `quarterly_cash_flow`
- `ttm_income_statement`, `ttm_cash_flow` (Trailing Twelve Months)

**Expected Data:**
- Each company: 10+ years of annual statements
- Each company: 10+ years of quarterly statements (40+ quarters)
- All major line items (revenue, operating income, net income, total assets, etc.)

**Data Validation:**
```sql
SELECT COUNT(*) FROM annual_income_statement;    -- Expected: 50K+
SELECT COUNT(*) FROM quarterly_balance_sheet;   -- Expected: 200K+
SELECT COUNT(DISTINCT symbol) FROM annual_cash_flow; -- Expected: 3000+
```

**Commands:**
```bash
cd /home/stocks/algo
python3 loadannualincomestatement.py
python3 loadannualbalancesheet.py
python3 loadannualcashflow.py
python3 loadquarterlyincomestatement.py
python3 loadquarterlybalancesheet.py
python3 loadquarterlycashflow.py
python3 loadttmincomestatement.py
python3 loadttmcashflow.py
```

---

### Phase 4B: SENTIMENT & ANALYST LOADERS

#### 21-25. Analyst Sentiment, News, Sentiment Analysis, Insider Transactions

**Purpose:** Load market sentiment and analyst opinion data
**Data Source:** Various financial data providers
**Runtime:** 8-15 minutes each
**Tables Created:**
- `analyst_sentiment` (buy/hold/sell ratings)
- `analyst_upgrades_downgrades` (rating changes)
- `news` (financial news)
- `sentiment` (sentiment scores)
- `insider_transactions` (insider buying/selling)

**Data Validation:**
```sql
SELECT COUNT(*) FROM analyst_sentiment;         -- Expected: 5K+
SELECT COUNT(*) FROM analyst_upgrades_downgrades; -- Expected: 10K+
SELECT COUNT(*) FROM news;                      -- Expected: 50K+
```

**Commands:**
```bash
cd /home/stocks/algo
python3 loadanalystsentiment.py
python3 loadanalystupgradedowngrade.py
python3 loadnews.py
python3 loadsentiment.py
python3 loadinsidertransactions.py
```

---

### Phase 5: SCORES & METRICS LOADERS

#### 26-29. Factor Metrics, Fundamental Metrics, Positioning Metrics, Stock Scores

**Purpose:** Calculate composite scores and fundamental metrics
**Dependencies:** Requires ALL prior data (prices, earnings, financial statements)
**Runtime:** 15-20 minutes each
**Tables Created:**
- `factor_metrics` (value, growth, quality factors)
- `fundamental_metrics` (P/E, P/B, dividend yield, etc.)
- `positioning_metrics` (momentum, relative strength)
- `stock_scores` (composite 0-100 score)

**Data Validation:**
```sql
SELECT COUNT(*) FROM factor_metrics;        -- Expected: 4000+
SELECT COUNT(*) FROM fundamental_metrics;   -- Expected: 4000+
SELECT COUNT(*) FROM stock_scores;          -- Expected: 4000+
```

**Commands:**
```bash
cd /home/stocks/algo
python3 loadfactormetrics.py
python3 loadfundamentalmetrics.py
python3 loadpositioningmetrics.py
python3 loadstockscores.py
```

---

### Phase 6: TECHNICAL INDICATORS (Optional but Recommended)

#### 30-41. Buy/Sell Signals, Seasonality, Rankings, AAII, NAAIM

**Purpose:** Technical analysis indicators and market sentiment
**Runtime:** 5-10 minutes each
**Tables Created:**
- `buysell_daily`, `buysell_weekly`, `buysell_monthly` (signals for stocks)
- `buysell_etf_daily`, `buysell_etf_weekly`, `buysell_etf_monthly` (ETF signals)
- `seasonality` (seasonal patterns)
- `sector_ranking`, `industry_ranking` (sector performance rankings)
- `aaii_data` (American Association of Individual Investors)
- `naaim_data` (National Association of Active Investment Managers)
- `relative_performance` (outperformance metrics)

**Commands:**
```bash
cd /home/stocks/algo
python3 loadbuyselldaily.py
python3 loadbuysellweekly.py
python3 loadbuysellmonthly.py
python3 loadbuysell_etf_daily.py
python3 loadbuysell_etf_weekly.py
python3 loadbuysell_etf_monthly.py
python3 loadrelativeperformance.py
python3 loadseasonality.py
python3 loadaaiidata.py
python3 loadnaaim.py
python3 loadsectorranking.py
python3 loadindustryranking.py
```

---

### Phase 7: OPTIONAL/SECONDARY LOADERS

These provide additional data but aren't essential for core dashboard functionality:

```bash
# Market Data
python3 loadbenchmark.py
python3 loadcalendar.py
python3 loadcommodities.py
python3 loadecondata.py
python3 loadfeargreed.py
python3 loadmarket.py
python3 loadmarketindices.py

# Options & Advanced
python3 loadcoveredcallopportunities.py
python3 loadoptionschains.py

# Company Data
python3 loaddailycompanydata.py
python3 loadsecfilings.py

# ETF Specific
python3 loadetfpricedaily.py
python3 loadetfpriceweekly.py
python3 loadetfpricemonthly.py
python3 loadetfsignals.py

# Portfolio
python3 loadalpacaportfolio.py  # Requires ALPACA_API_KEY
```

---

## 6. AUTOMATED LOADING SCRIPT

### Full Load Sequence (All Phases)

```bash
#!/bin/bash
set -e  # Exit on first error

cd /home/stocks/algo

echo "========================================="
echo "FINANCIAL DATA LOADING - FULL SEQUENCE"
echo "========================================="

# Phase 1: Foundation
echo -e "\n[PHASE 1] Loading Foundation Data..."
python3 loadstocksymbols.py || { echo "❌ loadstocksymbols.py failed"; exit 1; }
python3 loadsectors.py || { echo "❌ loadsectors.py failed"; exit 1; }

# Phase 2: Price Data
echo -e "\n[PHASE 2] Loading Price Data..."
python3 loadpricedaily.py || { echo "❌ loadpricedaily.py failed"; exit 1; }
python3 loadpriceweekly.py
python3 loadpricemonthly.py
python3 loadlatestpricedaily.py
python3 loadlatestpriceweekly.py
python3 loadlatestpricemonthly.py

# Phase 3: Earnings Data
echo -e "\n[PHASE 3] Loading Earnings Data..."
python3 loadearningshistory.py || { echo "❌ loadearningshistory.py failed"; exit 1; }
python3 loadearningssurprise.py
python3 loadearningsrevisions.py
python3 loadguidance.py

# Phase 4A: Financial Statements
echo -e "\n[PHASE 4A] Loading Financial Statements..."
python3 loadannualincomestatement.py
python3 loadannualbalancesheet.py
python3 loadannualcashflow.py
python3 loadquarterlyincomestatement.py
python3 loadquarterlybalancesheet.py
python3 loadquarterlycashflow.py
python3 loadttmincomestatement.py
python3 loadttmcashflow.py

# Phase 4B: Sentiment & Analyst Data
echo -e "\n[PHASE 4B] Loading Sentiment & Analyst Data..."
python3 loadanalystsentiment.py
python3 loadanalystupgradedowngrade.py
python3 loadnews.py
python3 loadsentiment.py
python3 loadinsidertransactions.py

# Phase 5: Scores & Metrics
echo -e "\n[PHASE 5] Loading Scores & Metrics..."
python3 loadfactormetrics.py
python3 loadfundamentalmetrics.py
python3 loadpositioningmetrics.py
python3 loadstockscores.py

# Phase 6: Technical Indicators (Optional)
echo -e "\n[PHASE 6] Loading Technical Indicators..."
python3 loadbuyselldaily.py
python3 loadbuysellweekly.py
python3 loadbuysellmonthly.py
python3 loadbuysell_etf_daily.py
python3 loadbuysell_etf_weekly.py
python3 loadbuysell_etf_monthly.py
python3 loadrelativeperformance.py
python3 loadseasonality.py
python3 loadaaiidata.py
python3 loadnaaim.py
python3 loadsectorranking.py
python3 loadindustryranking.py

echo -e "\n========================================="
echo "✅ FULL LOAD COMPLETE!"
echo "========================================="
echo "Total estimated time: 3-4 hours"
echo "Database: stocks@localhost/stocks"
```

### Minimal Load Sequence (Core Only)

```bash
#!/bin/bash
set -e  # Exit on first error

cd /home/stocks/algo

echo "========================================="
echo "FINANCIAL DATA LOADING - CORE ONLY"
echo "========================================="

# Phase 1: Foundation
echo -e "\n[PHASE 1] Loading Foundation Data..."
python3 loadstocksymbols.py || { echo "❌ loadstocksymbols.py failed"; exit 1; }
python3 loadsectors.py || { echo "❌ loadsectors.py failed"; exit 1; }

# Phase 2: Price Data
echo -e "\n[PHASE 2] Loading Price Data..."
python3 loadpricedaily.py || { echo "❌ loadpricedaily.py failed"; exit 1; }

# Phase 3: Earnings Data
echo -e "\n[PHASE 3] Loading Earnings Data..."
python3 loadearningshistory.py || { echo "❌ loadearningshistory.py failed"; exit 1; }

echo -e "\n========================================="
echo "✅ CORE LOAD COMPLETE!"
echo "========================================="
echo "Total estimated time: 90-120 minutes"
echo "Database: stocks@localhost/stocks"
echo ""
echo "You can now:"
echo "  - Start the admin dashboard"
echo "  - View stock listings and prices"
echo "  - See earnings dates and history"
echo "  - Access sector/industry analysis"
```

---

## 7. ERROR HANDLING & RECOVERY

### Common Issues & Solutions

#### 1. Database Connection Errors

**Error:** `FATAL: password authentication failed for user "stocks"`

**Solution:**
```bash
# Verify .env.local has correct credentials
cat .env.local | grep DB_

# Check PostgreSQL container is running
docker-compose ps

# Try resetting database
docker-compose down
docker-compose up -d
```

#### 2. Rate Limiting from Yahoo Finance

**Error:** `HTTP Error 429` or timeouts

**Solution:**
```python
# Already handled in loaders with exponential backoff
# Default behavior: wait 120 seconds, then retry
# If persistent, increase BATCH_PAUSE in loader script:
BATCH_PAUSE = 8.0  # Increase to 10-15 seconds
```

#### 3. Out of Memory

**Error:** Memory usage exceeds available RAM

**Solution:**
```bash
# Monitor memory during load
watch -n 5 'ps aux | grep python3'

# Run loaders one at a time instead of parallel
# Reduce batch size in loader scripts if available
```

#### 4. Partial Data Load (Interrupted)

**Solution:**
```bash
# Check which loaders completed
PGPASSWORD=stocks psql -h localhost -U stocks -d stocks << 'EOF'
SELECT * FROM last_updated ORDER BY last_run DESC;
EOF

# Re-run only failed loaders
python3 loadpricedaily.py  # (re-runs and appends/updates data)
```

---

## 8. DATA VALIDATION & COMPLETENESS CHECKS

### Comprehensive Validation Script

```bash
#!/bin/bash
# Validate database completeness

cd /home/stocks/algo

PGPASSWORD=stocks psql -h localhost -U stocks -d stocks << 'EOF'

echo "========================================"
echo "DATABASE VALIDATION REPORT"
echo "========================================"

-- Foundation Data
echo ""
echo "[FOUNDATION DATA]"
SELECT 'Stock Symbols' AS dataset, COUNT(*) as record_count FROM stock_symbols;
SELECT 'ETF Symbols' AS dataset, COUNT(*) as record_count FROM etf_symbols;
SELECT 'Sectors' AS dataset, COUNT(*) as record_count FROM sectors;
SELECT 'Industries' AS dataset, COUNT(*) as record_count FROM industries;

-- Price Data
echo ""
echo "[PRICE DATA]"
SELECT 'Daily Prices' AS dataset, COUNT(*) as record_count FROM price_daily;
SELECT 'Weekly Prices' AS dataset, COUNT(*) as record_count FROM price_weekly;
SELECT 'Monthly Prices' AS dataset, COUNT(*) as record_count FROM price_monthly;

-- Earnings Data
echo ""
echo "[EARNINGS DATA]"
SELECT 'Earnings History' AS dataset, COUNT(*) as record_count FROM earnings_history;
SELECT 'Earnings Surprise' AS dataset, COUNT(*) as record_count FROM earnings_surprise;
SELECT 'Earnings Revisions' AS dataset, COUNT(*) as record_count FROM earnings_revisions;
SELECT 'Earnings Guidance' AS dataset, COUNT(*) as record_count FROM earnings_guidance;

-- Financial Statements
echo ""
echo "[FINANCIAL STATEMENTS]"
SELECT 'Annual Income Stmt' AS dataset, COUNT(*) as record_count FROM annual_income_statement;
SELECT 'Quarterly Balance Sheet' AS dataset, COUNT(*) as record_count FROM quarterly_balance_sheet;

-- Scores & Metrics
echo ""
echo "[SCORES & METRICS]"
SELECT 'Stock Scores' AS dataset, COUNT(*) as record_count FROM stock_scores;
SELECT 'Fundamental Metrics' AS dataset, COUNT(*) as record_count FROM fundamental_metrics;

-- Final Summary
echo ""
echo "[COMPLETENESS SUMMARY]"
SELECT
    (SELECT COUNT(*) FROM stock_symbols) as stock_count,
    (SELECT COUNT(DISTINCT symbol) FROM price_daily) as stocks_with_prices,
    (SELECT COUNT(DISTINCT symbol) FROM earnings_history) as stocks_with_earnings,
    (SELECT COUNT(DISTINCT symbol) FROM stock_scores) as stocks_with_scores;

EOF
```

### Success Criteria Checklist

- [ ] stock_symbols: 5000+ records
- [ ] etf_symbols: 2000+ records
- [ ] sectors: 10-15 records
- [ ] industries: 100+ records
- [ ] price_daily: 10M+ records
- [ ] stocks with prices: 4500+ symbols
- [ ] earnings_history: 100K+ records
- [ ] stocks with earnings: 3000+ symbols
- [ ] annual_income_statement: 50K+ records
- [ ] stock_scores: 3000+ symbols with scores
- [ ] last_updated: All loaders present in tracking table

---

## 9. TIMELINE & RESOURCE REQUIREMENTS

### Single-Machine Sequential Load (Recommended for local dev)

| Phase | Loaders | Time | CPU | RAM |
|-------|---------|------|-----|-----|
| 1 | Foundation (2) | 10 min | 1 core | 256MB |
| 2 | Price Data (8) | 60 min | 1-2 cores | 500MB |
| 3 | Earnings (4) | 30 min | 1 core | 400MB |
| 4A | Financial Statements (8) | 60 min | 1 core | 300MB |
| 4B | Sentiment/Analyst (5) | 40 min | 1 core | 250MB |
| 5 | Scores/Metrics (4) | 25 min | 2 cores | 600MB |
| 6 | Technical Indicators (12) | 90 min | 1 core | 250MB |
| 7 | Optional (14) | 60 min | 1 core | 200MB |
| **TOTAL** | **57** | **4-5 hours** | **2 cores** | **2GB** |

### Recommended Hardware (Local Development)

- **CPU:** 2+ cores (Intel i5/i7 or equivalent)
- **RAM:** 4GB+ (8GB recommended)
- **Storage:** 50GB+ for full database + indexes
- **Network:** Stable internet (required for data downloads)
- **Disk I/O:** SSD strongly recommended

### Parallel Loading (If Running Multiple Loaders)

```bash
# Run non-dependent loaders in parallel
# Phase 4A and 4B can run simultaneously

# Terminal 1: Financial Statements (Phase 4A)
python3 loadannualincomestatement.py &
python3 loadannualbalancesheet.py &
python3 loadannualcashflow.py &

# Terminal 2: Sentiment/Analyst (Phase 4B)
python3 loadanalystsentiment.py &
python3 loadanalystupgradedowngrade.py &

# Wait for all to complete
wait
```

---

## 10. MAINTENANCE & UPDATES

### Daily Update Schedule

For keeping data current with minimal re-runs:

```bash
#!/bin/bash
# Daily update (run each day after market close)

cd /home/stocks/algo

# Update only latest prices (quick, 5 min)
python3 loadlatestpricedaily.py

# Update latest earnings if any released (quick, 5 min)
python3 loadearningshistory.py

# Recalculate scores (15 min)
python3 loadstockscores.py
```

### Weekly Update Schedule

```bash
#!/bin/bash
# Weekly update (run each weekend)

cd /home/stocks/algo

# Update all price data (45 min)
python3 loadpricedaily.py
python3 loadpriceweekly.py
python3 loadpricemonthly.py

# Update metrics (30 min)
python3 loadfactormetrics.py
python3 loadfundamentalmetrics.py
python3 loadpositioningmetrics.py
python3 loadstockscores.py

# Update sentiment (20 min)
python3 loadanalystsentiment.py
python3 loadnews.py
python3 loadsentiment.py
```

### Monthly Update Schedule

```bash
#!/bin/bash
# Monthly update (full refresh except symbols)

cd /home/stocks/algo

# Re-download all financial statements
python3 loadannualincomestatement.py
python3 loadannualbalancesheet.py
python3 loadannualcashflow.py
python3 loadquarterlyincomestatement.py
python3 loadquarterlybalancesheet.py
python3 loadquarterlycashflow.py
python3 loadttmincomestatement.py
python3 loadttmcashflow.py

# Refresh all technical indicators
python3 loadbuyselldaily.py
python3 loadbuysellweekly.py
python3 loadbuysellmonthly.py
python3 loadseasonality.py
python3 loadrelativeperformance.py
```

### Quarterly Update Schedule

```bash
#!/bin/bash
# Quarterly update (symbols + comprehensive refresh)

cd /home/stocks/algo

# Update symbol list (in case of new IPOs, delistings)
python3 loadstocksymbols.py
python3 loadsectors.py

# Then run full load sequence (see Phase 1-6 above)
```

---

## 11. TROUBLESHOOTING & DEBUGGING

### Enable Debug Logging

```bash
# Most loaders write to stdout/stderr
# To save output:
python3 loadpricedaily.py > load_price_daily.log 2>&1 &

# Monitor in real-time:
tail -f load_price_daily.log
```

### Check Database Status

```bash
# Connect to database directly
PGPASSWORD=stocks psql -h localhost -U stocks -d stocks

# List all tables
\dt

# Check table row counts
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;

# Count records in specific table
SELECT COUNT(*) FROM stock_symbols;

# View last updates
SELECT * FROM last_updated ORDER BY last_run DESC LIMIT 10;

# Check for errors in recent loads
SELECT * FROM pg_stat_statements ORDER BY query_start DESC LIMIT 10;
```

### Memory Profiling

```bash
# Monitor memory during load
python3 -u loadpricedaily.py 2>&1 | tee memory_profile.log

# Extract memory usage from logs
grep "MEM" memory_profile.log
```

### Network Issues

```bash
# Test connectivity to data sources
ping nasdaqtrader.com
curl -I https://query1.finance.yahoo.com

# Check if yfinance is working
python3 << 'EOF'
import yfinance as yf
ticker = yf.Ticker("AAPL")
print(ticker.history(period="1d"))
EOF
```

---

## 12. QUICK START CHECKLIST

- [ ] Start PostgreSQL: `docker-compose up -d`
- [ ] Verify connection: `PGPASSWORD=stocks psql -h localhost -U stocks -d stocks -c "SELECT 1"`
- [ ] Set environment variables (if needed): `export DB_HOST=localhost` etc.
- [ ] Run Phase 1: `python3 loadstocksymbols.py && python3 loadsectors.py`
- [ ] Run Phase 2: `python3 loadpricedaily.py` (this takes 45+ min)
- [ ] Run Phase 3: `python3 loadearningshistory.py`
- [ ] Validate data: Run validation script above
- [ ] Start admin dashboard: `cd /home/stocks/algo/webapp/frontend-admin && npm start`
- [ ] Access dashboard: `http://localhost:3000`

---

## 13. PERFORMANCE METRICS

### Expected Query Performance (After Full Load)

```sql
-- Stock lookup (should be < 100ms)
SELECT * FROM stock_symbols WHERE symbol = 'AAPL';

-- Price history for 1 stock (should be < 100ms)
SELECT * FROM price_daily WHERE symbol = 'AAPL'
ORDER BY date DESC LIMIT 252;

-- Sector performance (should be < 200ms)
SELECT * FROM sector_performance
WHERE date = CURRENT_DATE;

-- Top movers (should be < 500ms)
SELECT symbol, close, (close - open) as change
FROM latest_price_daily
ORDER BY change DESC LIMIT 100;

-- Stock scores ranking (should be < 500ms)
SELECT symbol, overall_score
FROM stock_scores
ORDER BY overall_score DESC LIMIT 50;
```

### Index Recommendations

```sql
-- Create indexes for faster queries
CREATE INDEX idx_stock_symbols_exchange ON stock_symbols(exchange);
CREATE INDEX idx_price_daily_symbol_date ON price_daily(symbol, date DESC);
CREATE INDEX idx_price_daily_date ON price_daily(date);
CREATE INDEX idx_earnings_history_symbol_date ON earnings_history(symbol, date DESC);
CREATE INDEX idx_annual_income_symbol_date ON annual_income_statement(symbol, fiscal_year DESC);
CREATE INDEX idx_stock_scores_score ON stock_scores(overall_score DESC);
```

---

## Summary

This comprehensive plan provides:

1. **Database Setup:** Docker-based PostgreSQL with proper initialization
2. **Critical Path:** 4 essential loaders for minimum viable dashboard
3. **Complete Load Order:** 57 loaders organized by dependency
4. **Detailed Specifications:** Runtime, data validation, success criteria for each loader
5. **Automated Scripts:** Ready-to-run bash scripts for different load scenarios
6. **Error Handling:** Common issues and their solutions
7. **Validation:** SQL queries to verify data completeness
8. **Maintenance:** Daily, weekly, monthly update schedules
9. **Performance:** Expected query times and index recommendations

**Total Load Time:** 3-5 hours for complete data load from scratch
**Minimum Viable:** 1.5-2 hours for critical data only

Start with Phase 1 & 2 to get the admin dashboard functional, then add additional phases as needed.

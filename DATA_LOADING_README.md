# Financial Data Loading Guide

**Complete documentation for loading all financial data locally**

## Documents Included

### 1. **LOAD_PLAN_SUMMARY.txt** (Start Here!)
**Quick reference guide - 2-3 minute read**
- Executive summary
- Quick start commands
- Three load scenarios (MVP, Standard, Complete)
- Common troubleshooting
- Key tables overview

**Best for:** Getting oriented quickly, understanding the scope

### 2. **FINANCIAL_DATA_LOAD_PLAN.md** (Complete Reference)
**Comprehensive 13-section guide - 30 minute read**
- Database connectivity setup
- Complete load order with dependencies
- Critical vs optional classification
- Detailed specifications for all 57 loaders
  - Purpose, data source, runtime, environment variables
  - Data validation queries
  - Success criteria
- Automated loading scripts (full, minimal, daily update)
- Error handling and recovery
- Data validation checklists
- Timeline and resource requirements
- Maintenance schedules (daily, weekly, monthly)
- Performance metrics and index recommendations

**Best for:** Running the loaders, understanding each one in detail

### 3. **LOADER_DEPENDENCY_MATRIX.md** (Technical Reference)
**Complete dependency analysis - 20 minute read**
- All 57 loaders organized by dependency tier
- Dependency chain analysis
- Parallel execution strategies
- Load order cheat sheets
- Runtime optimization (sequential vs parallel)
- Blocker dependencies critical path
- Troubleshooting by loader

**Best for:** Understanding dependencies, optimizing load strategy, parallel execution

### 4. **QUICK_START_GUIDE.sh** (Interactive Tool)
**Executable bash script - menu-driven interface**

Features:
- Setup PostgreSQL with docker-compose
- Verify database connection
- Load critical data (4 loaders)
- Load recommended data (25 loaders)
- Load all data (57 loaders)
- Validate database completeness
- Show database statistics
- Clean database (reset)
- Run daily updates

Usage:
```bash
chmod +x QUICK_START_GUIDE.sh
./QUICK_START_GUIDE.sh
```

**Best for:** Automated, guided data loading

---

## Quick Start (5 minutes)

```bash
# 1. Start PostgreSQL
cd /home/stocks/algo
docker-compose up -d

# 2. Verify connection
PGPASSWORD=stocks psql -h localhost -U stocks -d stocks -c "SELECT 1"

# 3. Load critical data
python3 loadstocksymbols.py      # 5 min
python3 loadsectors.py           # 5 min
python3 loadpricedaily.py        # 60 min (longest)
python3 loadearningshistory.py   # 30 min

# 4. Start dashboard
cd /home/stocks/algo/webapp/frontend-admin
npm start
```

Total time: ~100 minutes for minimum viable dashboard

---

## Load Scenarios

### Scenario A: MVP (Minimum Viable Product)
**Time: 90-120 minutes | 4 loaders**

Loads:
- Stock symbols (5,000+ stocks)
- Sector/industry classification
- Daily prices (10M+ records)
- Earnings history (100K+ records)

Provides: Stock lookup, price charts, earnings dates

```bash
python3 loadstocksymbols.py
python3 loadsectors.py
python3 loadpricedaily.py
python3 loadearningshistory.py
```

### Scenario B: Standard (Full Featured)
**Time: 3-3.5 hours | 25 loaders**

Adds to MVP:
- Weekly/monthly price data
- Financial statements (income, balance sheet, cash flow)
- Analyst sentiment and ratings
- Earnings surprises and revisions
- Factor metrics and fundamental metrics
- Stock composite scores

Provides: Feature-complete dashboard

See FINANCIAL_DATA_LOAD_PLAN.md Phase 1-5

### Scenario C: Complete (All Data)
**Time: 4-5 hours | 57 loaders**

Adds to Standard:
- Technical indicators and buy/sell signals
- Market sentiment (AAII, NAAIM)
- Options chains and covered calls
- Economic indicators
- SEC filings and news
- Seasonality and performance rankings

Provides: Comprehensive financial platform

See FINANCIAL_DATA_LOAD_PLAN.md Phase 1-7

---

## Database Structure

### Connection Details
- **Host:** localhost
- **Port:** 5432
- **User:** stocks
- **Password:** stocks
- **Database:** stocks
- **Setup:** docker-compose.yml (includes PostgreSQL 16)

### Key Tables Created

**Foundation:**
- `stock_symbols` - All tradeable stocks
- `etf_symbols` - All ETFs
- `sectors` - Sector classifications
- `industries` - Industry classifications

**Prices:**
- `price_daily`, `price_weekly`, `price_monthly`
- `latest_price_*` - Current price snapshots
- `etf_price_*` - ETF price data

**Earnings:**
- `earnings_history` - Complete earnings data
- `earnings_surprise` - EPS surprise %
- `earnings_revisions` - Analyst revisions
- `earnings_guidance` - Forward guidance

**Financial Statements:**
- `annual_income_statement`, `quarterly_income_statement`, `ttm_income_statement`
- `annual_balance_sheet`, `quarterly_balance_sheet`
- `annual_cash_flow`, `quarterly_cash_flow`, `ttm_cash_flow`

**Sentiment/Analyst:**
- `analyst_sentiment`, `analyst_upgrades_downgrades`
- `news`, `sentiment`, `insider_transactions`

**Metrics:**
- `factor_metrics` - Value/growth/quality factors
- `fundamental_metrics` - P/E, P/B, dividend yield
- `positioning_metrics` - Momentum, relative strength
- `stock_scores` - Composite 0-100 scores

**Tracking:**
- `last_updated` - Timestamp of each loader run

---

## Critical Path (Dependencies)

```
loadstocksymbols.py (5 min)
    ↓ (32 loaders depend on this)
loadpricedaily.py (60 min) ← LONGEST STEP
    ↓ (5 loaders depend on this)
loadearningshistory.py (30 min)
    ↓ (1 loader depends on this)
loadearningssurprise.py (10 min)
    ↓ (blocks score calculation)
loadfactormetrics.py (20 min)
    ↓ (requires all other metrics)
loadstockscores.py (20 min) ← RUN LAST
```

---

## Documentation Guide

| Need | Document | Section | Time |
|------|----------|---------|------|
| Quick overview | LOAD_PLAN_SUMMARY.txt | All | 5 min |
| Get started | QUICK_START_GUIDE.sh | Menu | 1 min |
| MVP setup | FINANCIAL_DATA_LOAD_PLAN.md | Phase 1-2 | 15 min |
| Full details | FINANCIAL_DATA_LOAD_PLAN.md | All | 30 min |
| Understand dependencies | LOADER_DEPENDENCY_MATRIX.md | All | 20 min |
| Optimize parallel load | LOADER_DEPENDENCY_MATRIX.md | Parallel Execution Matrix | 10 min |
| Troubleshoot | FINANCIAL_DATA_LOAD_PLAN.md | Error Handling | 10 min |
| Check data quality | FINANCIAL_DATA_LOAD_PLAN.md | Data Validation | 5 min |

---

## Common Commands

```bash
# Start/stop database
docker-compose up -d                    # Start
docker-compose ps                       # Check status
docker-compose down                     # Stop

# Database connection
PGPASSWORD=stocks psql -h localhost -U stocks -d stocks

# Load data
cd /home/stocks/algo
python3 loadstocksymbols.py

# Check progress
PGPASSWORD=stocks psql -h localhost -U stocks -d stocks -c \
  "SELECT * FROM last_updated ORDER BY last_run DESC LIMIT 5"

# Count records
PGPASSWORD=stocks psql -h localhost -U stocks -d stocks -c \
  "SELECT COUNT(*) FROM stock_symbols"

# View table list
PGPASSWORD=stocks psql -h localhost -U stocks -d stocks -c \
  "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
```

---

## Estimated Timeline

| Phase | Duration | Loaders | What You Get |
|-------|----------|---------|--------------|
| Phase 1: Foundation | 10 min | 2 | Symbols, sectors |
| Phase 2: Prices | 60 min | 8 | Daily/weekly/monthly prices |
| Phase 3: Earnings | 30 min | 4 | Earnings history |
| Phase 4A: Financial Statements | 60 min | 8 | Income, balance sheet, cash flow |
| Phase 4B: Sentiment | 40 min | 5 | Analyst ratings, news, sentiment |
| Phase 5: Metrics | 25 min | 4 | Factor, fundamental, scores |
| Phase 6: Technical | 90 min | 12 | Buy/sell signals, seasonality |
| Phase 7: Optional | 60 min | 14 | Economic data, options, etc. |
| **TOTAL** | **4.5 hr** | **57** | **Complete platform** |

---

## Hardware Requirements

**Minimum:**
- CPU: 2 cores
- RAM: 4GB
- Storage: 50GB
- Network: Stable internet

**Recommended:**
- CPU: 4+ cores
- RAM: 8GB
- Storage: 100GB
- Network: High-speed internet
- Disk: SSD

---

## Support & Troubleshooting

### Database won't start
```bash
docker-compose down -v    # Remove old data
docker-compose up -d      # Start fresh
```

### Connection refused
```bash
docker-compose ps         # Check if running
PGPASSWORD=stocks psql -h localhost -U stocks -d stocks -c "SELECT 1"
```

### Loader fails
1. Check error message
2. Re-run single loader
3. Check last_updated table
4. See FINANCIAL_DATA_LOAD_PLAN.md Error Handling section

### Rate limiting (HTTP 429)
- Wait 2-5 minutes
- Loader has exponential backoff built-in
- Re-run the loader

### Out of memory
- Run loaders sequentially instead of parallel
- Monitor with: watch -n 5 'ps aux | grep python'

---

## Next Steps

1. **Read:** LOAD_PLAN_SUMMARY.txt (5 min)
2. **Run:** QUICK_START_GUIDE.sh (interactive)
   OR
   **Execute:** Manual commands in LOAD_PLAN_SUMMARY.txt
3. **Monitor:** Check last_updated table and dashboard
4. **Add Data:** Run additional loaders as needed
5. **Maintain:** Set up daily/weekly schedules (see FINANCIAL_DATA_LOAD_PLAN.md)

---

## File Inventory

```
/home/stocks/algo/

Data Loading Documentation:
├── DATA_LOADING_README.md              ← You are here
├── LOAD_PLAN_SUMMARY.txt               ← 2-3 min executive summary
├── FINANCIAL_DATA_LOAD_PLAN.md         ← 30 min comprehensive guide
├── LOADER_DEPENDENCY_MATRIX.md         ← 20 min technical reference
├── QUICK_START_GUIDE.sh                ← Interactive menu tool

Python Loaders (57 total):
├── loadstocksymbols.py                 ← CRITICAL: Foundation
├── loadsectors.py                      ← CRITICAL: Foundation
├── loadpricedaily.py                   ← CRITICAL: Prices
├── loadearningshistory.py              ← CRITICAL: Earnings
├── load[...]*.py                       ← 53 additional loaders
└── ...

Configuration:
├── docker-compose.yml                  ← PostgreSQL setup
├── init-db.sql                        ← Database initialization
├── .env.local                         ← Environment variables
├── lib/db.py                          ← Database utilities

Application:
├── webapp/
│   ├── frontend-admin/                ← Admin dashboard
│   ├── frontend/                      ← User frontend
│   └── lambda/                        ← AWS Lambda functions
└── ...
```

---

## Key Takeaways

1. **Start Simple:** Load only critical data (MVP) first (~100 min)
2. **Respect Dependencies:** Follow the load order (see dependency matrix)
3. **Database Setup:** Use docker-compose for quick PostgreSQL setup
4. **Monitor Progress:** Check `last_updated` table after each loader
5. **Validate Data:** Use provided SQL queries to verify completeness
6. **Scale Up:** Add more loaders as needed for enhanced features
7. **Automate:** Use QUICK_START_GUIDE.sh for reliable, reproducible loads

---

## Questions?

Check:
1. LOAD_PLAN_SUMMARY.txt → Quick troubleshooting
2. FINANCIAL_DATA_LOAD_PLAN.md → Detailed specifications & error handling
3. LOADER_DEPENDENCY_MATRIX.md → Dependency analysis & optimization
4. QUICK_START_GUIDE.sh → Interactive step-by-step

For AWS deployment, see lib/db.py for AWS Secrets Manager integration.


# System Architecture Audit & Diagnosis
**Date:** 2026-04-25  
**Purpose:** Identify architectural mess and plan clean fixes  
**Status:** DIAGNOSIS - No changes made yet, awaiting team decision

---

## PROBLEM STATEMENT

**Frontend shows NO DATA.** Routes query tables that don't exist in the database schema.

**Root Cause:** Three conflicting database schema files created different table structures, but routes were written for a schema that doesn't match the actual database.

---

## THE THREE CONFLICTING SCHEMAS

### File 1: `init-db.sql`
**Status:** May be outdated  
**Defines:** Basic tables (stock_symbols, price_daily, technical_data_daily, etc.)  
**Purpose:** Initial setup (but is this still used?)

### File 2: `create-portfolio-tables.sql`
**Status:** Separate portfolio schema  
**Defines:** portfolio_holdings, portfolio_performance, trades  
**Problem:** Might have different column names than what routes expect

### File 3: `reset-database-to-loaders.sql` 
**Status:** Used by loaders, most authoritative  
**Defines:** Annual/quarterly/TTM financial statements, buy_sell tables, etc.  
**Problem:** Doesn't include all tables that routes query

**RESULT:** Routes written for merged schema that doesn't exist anywhere.

---

## BROKEN ENDPOINTS (Top 15)

| Endpoint | File | Issue | Missing Table(s) |
|----------|------|-------|------------------|
| `/api/technicals/daily` | technicals.js | queries `technical_data_daily` | ✗ NOT DEFINED |
| `/api/sentiment/data` | sentiment.js | queries sentiment tables | ✗ analyst_sentiment_analysis |
| `/api/portfolio/metrics` | portfolio.js | JOINs stability_metrics | ✗ stability_metrics |
| `/api/portfolio/holdings` | portfolio.js | JOINs multiple missing tables | ✗ Multiple |
| `/api/earnings` | earnings.js | queries earnings_history | ✗ earnings_history |
| `/api/options/chains` | options.js | queries options_chains | ✗ options_chains, options_greeks |
| `/api/commodities` | commodities.js | queries commodity tables | ✗ commodity_prices |
| `/api/trades` | trades.js | INSERT into trades | ✗ trades (form crashes) |
| `/api/sectors` | sectors.js | queries multiple tables | ✗ Multiple |
| `/api/market/overview` | market.js | queries market_data | ✗ market_data |

---

## SCHEMA CONFLICTS - Examples

### Conflict #1: technical_data_daily
```
Routes expect:
  SELECT rsi, macd, macd_signal, macd_hist, mom, roc, ...
  FROM technical_data_daily

But table is NOT DEFINED in any of the 3 schema files
```

### Conflict #2: portfolio_holdings
```
Schema (create-portfolio-tables.sql) has:
  symbol, quantity, average_cost, current_price, market_value

Routes expect (portfolio.js line 554):
  symbol, quantity, average_cost, sector, return_percent, unrealized_pnl

Missing: sector, return_percent, unrealized_pnl
```

### Conflict #3: stock_scores
```
Loaders (loadstockscores.py) populate:
  composite_score, value_metrics, growth_metrics, quality_metrics, momentum_metrics, stability_metrics

Routes query (optimization.js):
  stock_scores table directly for all fields
  
But: stock_scores only has composite_score, other metrics are SEPARATE TABLES that don't exist
```

---

## DUPLICATE ENDPOINTS

| Endpoint | Files | Issue |
|----------|-------|-------|
| `/daily` technical data | technicals.js + price.js + signals.js | 3 different implementations |
| `/weekly` data | price.js + technicals.js + signals.js | Duplicated logic |
| `/monthly` data | price.js + technicals.js + signals.js | Duplicated logic |
| `/list` signals | signals.js (2 different routes) | Lines 38 & 200+ identical |
| Portfolio summary | portfolio.js (multiple endpoints) | `/metrics`, `/summary`, `/data` all return similar data |

---

## UTILITY SCRIPT CLUTTER

**Check Scripts (50+ files):**
- check-data.js, check-data-quality.js, check-data-status.py, check-db-tables.js, check-full-schema.js, check-key-metrics.js, check-schema.js, check-tables.js, check-yfinance.py

**Setup Scripts (20+ files):**
- setup-database.bat, setup-dev.js, setup-postgres.ps1, setup-portfolio-tables.py, setup-stocks.sql

**Init Scripts (10+ files):**
- init-db.sql, init_database.py, init_database_OLD.py, initialize-schema.py.OBSOLETE

**Populate Scripts (15+ files):**
- populate-technicals.js, populate_metrics_now.py, populate_missing_metrics.py, populate_sp500.py

**Reset Scripts (5+ files):**
- reset-db.py, reset-signals.py, reset-database-to-loaders.sql

**Total:** 100+ maintenance scripts, unclear which to run, which are current, which are broken.

---

## LOADERS NOT MATCHING SCHEMA

| Loader | Target Tables | Status |
|--------|---------------|--------|
| loadstockscores.py | stock_scores, quality_metrics, growth_metrics, etc. | ⚠️ quality_metrics NOT in any schema |
| loadfactormetrics.py | positioning_metrics, quality_metrics, growth_metrics | ⚠️ None of these defined |
| loadanalystsentiment.py | analyst_sentiment_analysis | ✗ Table not defined |
| loadoptionschains.py | options_chains, options_greeks | ✗ Tables not defined |
| loadalpacaportfolio.py | portfolio_holdings, portfolio_performance, trades | ⚠️ trades not defined |
| loadtechnicalsdaily.py | technical_data_daily | ✗ Table not defined |

---

## WHAT ACTUALLY EXISTS

**Tables that ARE properly defined in reset-database-to-loaders.sql:**
- stock_symbols ✅
- etf_symbols ✅
- price_daily ✅
- price_weekly ✅
- price_monthly ✅
- buy_sell_daily ✅
- buy_sell_weekly ✅
- buy_sell_monthly ✅
- annual_income_statement ✅
- annual_balance_sheet ✅
- annual_cash_flow ✅
- quarterly_income_statement ✅
- quarterly_balance_sheet ✅
- quarterly_cash_flow ✅
- ttm_income_statement ✅
- ttm_cash_flow ✅
- company_profile ✅
- key_metrics ✅
- last_updated ✅

**What routes expect but doesn't exist:**
- 44 additional tables

---

## DECISION REQUIRED

### Option A: CLEAN SLATE FIX (Recommended for long-term health)
1. Pick ONE authoritative schema file (reset-database-to-loaders.sql is most complete)
2. Update ALL routes to use ONLY tables in that schema
3. Remove routes that require non-existent tables (or defer them)
4. Remove duplicate endpoints (keep 1 clean version per resource)
5. Delete 100+ utility scripts (keep only 1 master setup, 1 master reset)
6. Verify all loaders match final schema
7. Result: Clean, maintainable system
8. **Time:** 4-6 hours, requires careful work

### Option B: MINIMAL PATCH FIX (Quick but adds more mess)
1. Add missing tables to database schema
2. Update loaders to populate them
3. Fix route SQL queries
4. Leave duplicates and utility scripts as-is
5. Result: Data displays but system stays messy
6. **Time:** 2-3 hours, but creates maintenance burden

### Option C: HYBRID - Clean routes first, defer schema until later
1. Fix routes to query ONLY existing tables
2. Disable broken endpoints temporarily
3. Get core data displaying (portfolio, technicals, trades)
4. Schedule schema cleanup for next sprint
5. Result: Partial functionality, plan to fix properly
6. **Time:** 2 hours, defers full fix

---

## QUESTIONS FOR TEAM

Before proceeding, clarify:

1. **Is anyone actively using:**
   - The 100+ utility scripts? (Which ones?)
   - The 3 different schema files? (Which is authoritative?)
   - The duplicate endpoints? (Which versions are used?)

2. **What should be the single source of truth:**
   - For database schema? → `reset-database-to-loaders.sql`?
   - For API endpoints? → Which existing routes are "the good ones"?

3. **What's the priority:**
   - Get working system quickly? → Option B or C
   - Build proper architecture? → Option A
   - Balance both? → Hybrid approach

4. **Blockers:**
   - Are loaders currently running and populating data?
   - Are other team members actively developing?
   - Any critical features depending on currently-broken endpoints?

---

## RECOMMENDED APPROACH

Given your statement "cleanest solution always", I recommend:

**Phased Clean Architecture Fix:**

**Phase 1 (TODAY - 2 hours):** 
- Consolidate to ONE schema file
- Fix critical routes (portfolio, technicals, trades)
- Remove duplicate endpoints
- Get core data displaying

**Phase 2 (NEXT - 2 hours):**
- Delete all utility clutter (keep only 1 master setup + reset)
- Verify all loaders match schema
- Update documentation

**Phase 3 (ONGOING):**
- Fix remaining non-critical endpoints
- Add proper error handling
- Document the clean architecture

**Result:** Clean system that other developers won't corrupt with more layers of mess.

---

## DECISION CHECKPOINT

**Before proceeding with fixes:**
1. Review this diagnosis with team
2. Confirm which approach (A, B, C, or Hybrid)
3. Identify any work-in-progress that might conflict
4. Then I execute the clean fix without creating more mess

**Do NOT proceed until team agrees on direction.**

# System Status

**Last Updated:** 2026-05-16 (Session 19: Comprehensive QA Audit)  
**Status:** 🟡 **CRITICAL BUGS FOUND** | Loader failures blocking data | API endpoints returning empty

---

## 🔴 CRITICAL ISSUES FOUND (Session 19 Audit)

### **Issue #1: Stock Scores Loader — Duplicate Row Bug (BLOCKS TRADING SIGNALS)**
**Severity:** CRITICAL  
**Impact:** `stock_scores` table stays empty → portfolio/scoring pages return no data

**Root Cause:**  
Loader returns one row per price point (~100+ rows per symbol), but table primary key is `(symbol)` only.  
PostgreSQL rejects as duplicates in single INSERT: `"ON CONFLICT DO UPDATE command cannot affect row a second time"`

**Fix Required:**  
- Change primary key to `("symbol", "date")` OR
- Modify loader to return only 1 row per symbol (most recent score)
- Decision: Return 1 aggregated score per symbol (less data, more useful)

**Status:** Not yet fixed

---

### **Issue #2: Buy/Sell Loader — Schema Mismatch (BLOCKS TRADING SIGNALS)**
**Severity:** CRITICAL  
**Impact:** `buy_sell_daily` table stays empty → signal pages show nothing

**Root Cause:**  
Loader tries to insert `timeframe` column (set to "Daily") that doesn't exist in table schema.  
Table schema: `(symbol, date, signal, strength, reason, created_at)`  
Loader includes: `timeframe` field

**Fix Required:**  
Remove `timeframe` from loader output (it's redundant—table is already daily)

**Status:** Not yet fixed

---

### **Issue #3: Trend Template Loader — NameError Crash (BLOCKS TREND ANALYSIS)**
**Severity:** CRITICAL  
**Impact:** Loader crashes before running

**Root Cause:**  
Line 135: `_get_db_password()` — typo, should be `get_db_password()`  
Same import used in other loaders works fine; this is inconsistent.

**Fix Required:**  
Change to `get_db_password()` (remove underscore prefix)

**Status:** Not yet fixed

---

## 📊 DATA POPULATION STATUS (as of now)

| Table | Rows | Status | Blocks |
|-------|------|--------|--------|
| stock_symbols | 38 | ✓ OK | None |
| price_daily | 47,391 | ✓ OK | None |
| **stock_scores** | **0** | ✗ EMPTY | Portfolio, Scoring pages |
| **buy_sell_daily** | **0** | ✗ EMPTY | Signals, Trading pages |
| trend_template_data | 4 | ⚠ PARTIAL | Technical analysis |
| **economic_data** | **0** | ✗ EMPTY | Economic dashboard |
| **company_profile** | **0** | ✗ EMPTY | Stock detail pages |
| annual_income_statement | 0 | ✗ EMPTY | Financials pages |
| annual_balance_sheet | 0 | ✗ EMPTY | Financials pages |
| annual_cash_flow | 0 | ✗ EMPTY | Financials pages |

**Key Finding:** API endpoints are wired correctly and query these tables, but most return empty because loaders are broken.

---

---

## 🟡 SECONDARY ISSUES (Lower Priority)

### **Issue #4: Economic Data Loader — Missing API Key**
**Severity:** MEDIUM  
**Impact:** `economic_data` table stays empty → Economic Dashboard shows nothing

**Current State:**  
Loader checks for `FRED_API_KEY` env var and exits early if missing.  
This is correct behavior — just needs configuration.

**Fix Required:**  
- Add FRED_API_KEY to `.env.local` (free from https://fred.stlouisfed.org/docs/api/api_key.html)
- Then run: `python3 loadecondata.py`

**Decision:**  
- For LOCAL: Optional (economic data not critical for algo)
- For AWS: Required (circuit breaker uses yield curve)

**Status:** Blocked on user key setup

---

### **Issue #5: Company Profile / Financial Data — No Loaders**
**Severity:** MEDIUM  
**Impact:** Stock detail pages, Financial pages show no data

**Current State:**  
Tables exist and schema is correct, but:
- No loader populates `company_profile` (sector, industry, market cap)
- Financial loaders (`load_income_statement.py`, etc.) run but populate nothing
  - Probably querying external APIs that have rate limits or require auth

**Fix Required:**  
- Find if financial data loaders are working or need fixing
- If broken: add simple fallback (hide these pages or show "data unavailable")

**Status:** TBD after investigation

---

### **Issue #6: Trend Template Data — Only 4 Rows**
**Severity:** LOW  
**Impact:** Technical analysis pages show minimal data

**Current State:**  
- Loader runs (no crashes) but only loads 4 rows
- Probably incomplete fetching or stopped early

**Fix Required:**  
- Investigate why it stops at 4 rows
- Likely: not all symbols fetched, or early exit after first error

**Status:** Investigate during loader fixes

---

## 📋 COMPREHENSIVE AUDIT CHECKLIST

### Architecture & Design
- [x] All 25 frontend pages wired to API endpoints
- [x] API endpoints query real database tables (not hardcoded mock data)
- [ ] **BROKEN**: Loaders populating tables (3 critical failures)
- [ ] **TODO**: Verify orchestrator 7-phase logic is sound
- [ ] **TODO**: Verify trade execution logic (risk management, position sizing)
- [ ] **TODO**: Check calculation correctness (metrics, scores, indicators)

### Data Pipeline (Tier 0-4)
- [x] Tier 0: Stock symbols loading (38 symbols)
- [x] Tier 1: Price daily loading (47K records)
- [x] Tier 1b: Price aggregates (weekly/monthly)
- [ ] **BROKEN** Tier 2: Reference data (3 loaders failing)
  - stock_scores.py (duplicate row bug)
  - economic data (needs API key)
  - company profile (needs loader)
- [ ] **BROKEN** Tier 3: Trading signals (buy_sell_daily.py schema mismatch)
- [ ] Tier 3b: Signal aggregates
- [ ] Tier 4: Algo metrics

### Frontend Data Coverage
- [ ] EconomicDashboard — needs economic_data (currently: EMPTY)
- [ ] PortfolioDashboard — needs stock_scores (currently: EMPTY)
- [ ] SectorAnalysis — needs sector rankings (check: loadsectors.py status)
- [ ] TradingSignals — needs buy_sell_daily (currently: EMPTY)
- [ ] StockDetail — needs company_profile (currently: EMPTY)
- [ ] Financial pages — need income_statement, balance_sheet, cash_flow (currently: EMPTY)

---

## 🛠️ FIX PLAN (Priority Order)

### Phase 1: Fix Critical Loaders (Blocks 80% of features)
1. **Fix stock_scores.py** — Change to 1 row/symbol aggregate
2. **Fix loadbuyselldaily.py** — Remove timeframe column
3. **Fix load_trend_template_data.py** — Fix typo (_get_db_password)

**Expected time:** ~30 mins  
**Expected impact:** stock_scores, buy_sell_daily, trend_template_data tables populated

---

### Phase 2: Audit Other Loaders
4. **Check financial data loaders** — Are they working or broken?
5. **Check sector/industry loaders** — Are they working?
6. **Check algo_metrics loader** — Does it work?

**Expected time:** ~30 mins

---

### Phase 3: Orchestrator & Trade Logic Verification
7. **Verify orchestrator 7-phase logic** — Is it correct?
8. **Verify position sizing** — Are allocation sizes correct?
9. **Verify exit logic** — Are stops, targets working?
10. **Verify circuit breakers** — Do kill-switches work?

---

### Phase 4: Calculation Verification
11. **Verify score calculations** — Are formulas correct?
12. **Verify technical indicators** — RSI, MACD, trends correct?
13. **Verify risk metrics** — Sharpe, Sortino, max DD correct?

---

## Recent Fixes (Session 18 — PRIOR WORK)

---

## Health Check — Run After Fixes

```bash
# After fixing loaders, run this to populate data:
python3 loadstockscores.py          # After Issue #1 fix
python3 loadbuyselldaily.py         # After Issue #2 fix
python3 load_trend_template_data.py # After Issue #3 fix

# Check population:
python3 -c "
import psycopg2, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('.env.local'))
conn = psycopg2.connect(host=os.getenv('DB_HOST'), user=os.getenv('DB_USER'),
                        password=os.getenv('DB_PASSWORD'), database=os.getenv('DB_NAME'))
cur = conn.cursor()
tables = ['stock_scores', 'buy_sell_daily', 'trend_template_data', 'economic_data']
for t in tables:
    cur.execute(f'SELECT COUNT(*) FROM {t}')
    print(f'{t}: {cur.fetchone()[0]:,} rows')
conn.close()
"

# Test orchestrator (should work better with real data)
python3 algo_orchestrator.py --mode paper --dry-run
```

---

## NEXT IMMEDIATE ACTIONS (Pick A or B)

### **Option A: Deep Audit First** (Recommended)
1. Start with Phase 1 fixes (critical loaders)
2. Then Phase 2 audit (other loaders)
3. Then Phase 3 (orchestrator logic)
4. Then Phase 4 (calculations)

**Time estimate:** 4-6 hours  
**Output:** Complete understanding of all issues + all fixes

---

### **Option B: Quick Wins First**
1. Just fix Phase 1 (3 loaders)
2. Get data populating
3. Test frontend
4. Come back for Phase 2-4 later

**Time estimate:** 30 mins  
**Output:** 80% of pages show data, remaining issues TBD

---

**RECOMMENDATION:** Option A — you asked for "make everything work right the best way it can be" which requires understanding all issues first.


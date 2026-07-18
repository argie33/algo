# Symbol Filtering Audit - Session 246

**Status:** Discovery phase complete. Filtering logic is fragmented across 3 distinct systems with no single source of truth.

**CRITICAL:** Centralized `symbol_filters.py` module exists but **is never imported or used anywhere**. This is dead code and a maintenance liability.

---

## Current State: Filtering Locations & Logic

### 1. LOADER SYMBOL SELECTION
**File:** `loaders/helpers.py:get_active_symbols()`

**Mechanism:** Parameter `exclude_etfs` controls what gets loaded.

**exclude_etfs=False (default):**
```sql
SELECT symbol FROM stock_symbols WHERE active = true ORDER BY symbol
-- Result: ALL symbols (stocks, ETFs, indices, everything)
-- Used by: price loaders, market data loaders (stock + etf tables)
```

**exclude_etfs=True (financial data only):**
```sql
SELECT symbol FROM stock_symbols
WHERE active = true
  AND (etf IS NULL OR etf = 'N')
  AND security_name NOT ILIKE '%Right%'
  AND security_name NOT ILIKE '%Warrant%'
  AND security_name NOT ILIKE '%UNIT%'
  AND security_name NOT ILIKE '%Contingent Value%'
  AND security_name NOT ILIKE '%ETN%'
  AND security_name NOT ILIKE '%Exchange Traded Note%'
  AND security_name NOT ILIKE '%Double Long%'
  AND security_name NOT ILIKE '%Double Short%'
  AND security_name NOT ILIKE '%Inverse%'
  AND security_name NOT ILIKE '%Leveraged%'
  AND security_name NOT ILIKE '%Acquisition Corp%'
  AND security_name NOT ILIKE '%Acquisition Corp.%'
  AND security_name NOT ILIKE '%SPAC%'
  AND security_name NOT ILIKE '%Bitcoin%'
  AND security_name NOT ILIKE '%Crypto%'
  AND symbol !~ '[A-Z]+R$'
ORDER BY symbol
-- Result: Real stocks only (excludes 11+ asset type patterns)
-- Used by: financial statement, growth, quality, value, positioning, risk, stability loaders
```

**Loaders Using exclude_etfs=True (16 total):**
- load_yfinance_snapshot.py:53
- load_yfinance_derived_metrics.py:63
- load_value_quality_growth_metrics.py:64
- load_stock_scores.py:53
- load_risk_metrics_daily.py:50
- load_price_extremes.py:15
- load_positioning_metrics.py:53
- load_market_cap_computed.py:16
- load_institutional_holdings_13f.py:54
- load_insider_holdings_sec.py:61
- load_earnings_calendar_sec.py:58
- load_company_info_sec.py:59
- load_short_interest_finra.py:50
- load_sec_valuations.py:51
- helpers/sec_base.py:55

**Loaders Using exclude_etfs=False (default):**
- load_prices.py (no attribute set - uses default False)
- load_technical_indicators.py (default)
- load_market_status_daily.py (default)
- All other loaders not explicitly setting the flag

---

### 2. API ENDPOINT FILTERING
**File:** `lambda/api/routes/`

#### `/api/scores` (scores.py:112)
```python
where_clause = """
    WHERE sc.composite_score > 0
    AND (ss.symbol NOT IN (SELECT symbol FROM etf_symbols) AND (ss.etf IS NULL OR ss.etf = 'N'))
    """
```
**Result:** Stocks only (excludes ETFs via two-condition AND)

#### `/api/market/breadth` (market.py:102-104)
```python
JOIN price_daily t ON t.date = dp.d
    AND t.symbol NOT LIKE '^%' AND t.close IS NOT NULL
JOIN price_daily y ON y.date = dp.prev_d AND y.symbol = t.symbol
    AND y.symbol NOT LIKE '^%' AND y.close IS NOT NULL
```
**Result:** Excludes indices only (includes stocks + ETFs)

#### `/api/market/technicals` (market.py:183)
```python
WHERE close IS NOT NULL AND symbol NOT LIKE '^%'
```
**Result:** Excludes indices only (includes stocks + ETFs)

#### `/api/signals/etf` (signals.py:99)
```python
def _get_signals_etf(cur: cursor, limit: int) -> Any:
    # Dedicated ETF endpoint
    # [Implementation calls into separate ETF signal table]
```
**Result:** ETFs only (inverse filter - opposite of `/api/signals`)

#### `/api/signals/stocks` (signals.py:83)
```python
# Queries buy_sell_daily table (composition depends on upstream Phase 7)
# No explicit ETF filter - relies on buy_sell_daily source data
```
**Result:** Depends on orchestrator (likely stocks only, but not guaranteed)

---

### 3. ORCHESTRATOR PHASE 7 (Signal Generation)
**File:** `algo/orchestrator/phase7_signal_generation.py`

**Signal Source:** `buy_sell_daily` + `stock_scores` join

**Current Query (around line 200+):**
```sql
SELECT DISTINCT ON (symbol) *
FROM buy_sell_daily
WHERE [various conditions]
```

**Filtering:** Depends on what Phase 3 (technical signal generation) puts into `buy_sell_daily`. No explicit ETF/stock filter in Phase 7 itself.

---

### 4. DEAD CODE: symbol_filters.py
**File:** `utils/symbol_filters.py`

**Defined functions (never used):**
```python
def filter_etfs(cursor) -> str:
    return "(ss.symbol NOT IN (SELECT symbol FROM etf_symbols) AND (ss.etf IS NULL OR ss.etf = 'N'))"

def filter_indices(cursor) -> str:
    return "sc.symbol NOT LIKE '^%'"

def build_symbol_filter_clause(exclude_etfs=True, exclude_indices=True) -> str:
    # Combines the above
```

**Import count:** 0 (never imported)
**Usage count:** 0 (never called)
**Maintenance risk:** HIGH (exists as if it's centralized, but isn't)

---

## Inconsistencies & Risks

| System | Filters ETFs? | Filters Indices? | Filter Method | Risk Level |
|--------|---|---|---|---|
| **Loaders** | Selective (16 of X) | No | SQL WHERE + parameter | 🟡 MEDIUM |
| **API /scores** | Yes (2-condition AND) | No | Hardcoded SQL | 🟡 MEDIUM |
| **API /market** | No | Yes (LIKE) | Hardcoded SQL | 🟡 MEDIUM |
| **API /signals/etf** | Yes (inverse) | No | Separate endpoint | 🟠 HIGH (inverse logic) |
| **API /signals/stocks** | Depends | No | Inherits from Phase 7 | 🔴 HIGH (implicit) |
| **Orchestrator Phase 7** | Implicit | No | Depends on upstream | 🔴 HIGH (no explicit gate) |
| **symbol_filters.py** | Yes (defined) | Yes (defined) | **NOT USED** | 🔴 CRITICAL (dead code) |

---

## Specific Issues

### Issue #1: Two-Condition ETF Filter Inconsistency
**Locations:** API /scores, definitions in symbol_filters.py

The ETF filter uses AND logic:
```python
(ss.symbol NOT IN (SELECT symbol FROM etf_symbols) 
 AND (ss.etf IS NULL OR ss.etf = 'N'))
```

**Why two conditions?**
- `etf_symbols` table: curated list of known ETFs
- `etf` flag: marker in stock_symbols table

**Risk:** If one source is out of sync, an ETF could pass through. Example: A new ETF added to market but not yet in `etf_symbols` table → would still be filtered by `etf='Y'` flag, but if flag is NULL → PASSES.

---

### Issue #2: No ETF Filter on /api/signals/stocks
**Location:** `lambda/api/routes/signals.py:114`

The legacy `/api/signals/stocks` endpoint queries `buy_sell_daily` but doesn't explicitly filter out ETFs. If `buy_sell_daily` contains ETF signals (from Phase 3), they would be returned.

**Current expectation:** Phase 7 doesn't generate ETF signals (only stock signals), but this is implicit, not enforced.

---

### Issue #3: Orchestrator Phase 3 (Technical Signals) Doesn't Specify Asset Class
**Location:** `algo/orchestrator/phase3b_trend_template.py` (or wherever buy_sell_daily is generated)

When generating `buy_sell_daily` signals, there's no explicit filtering for "stocks only" vs "include ETFs". Whatever lands in that table is what gets returned.

**Risk:** If Phase 3 accidentally includes ETF symbols in buy_sell_daily, they flow through to signals without filtration.

---

### Issue #4: Index Filtering Inconsistent
**Locations:**
- market.py: Uses `NOT LIKE '^%'`
- scores.py: No explicit index filter
- signal_filters.py: Defines `filter_indices()` but never used

**Risk:** If an index symbol (^GSPC, etc.) ends up in stock_scores (unlikely, but possible through data loading bug), it would pass through scores API but be filtered from market breadth API. Inconsistent behavior.

---

### Issue #5: Duplicate Filter Logic in API
**Locations:**
- scores.py line 112: Hardcoded `(ss.symbol NOT IN (SELECT symbol FROM etf_symbols) AND (ss.etf IS NULL OR ss.etf = 'N'))`
- symbol_filters.py line 27: Same definition in `filter_etfs()`
- market.py line 102: Hardcoded `NOT LIKE '^%'`
- symbol_filters.py line 36: Same definition in `filter_indices()`

**If filtering rules need to change:** Must update in 2+ places → maintenance burden and divergence risk.

---

## Governance Mismatch

From `steering/GOVERNANCE.md`:
> "For financial data loaders: only real stocks, exclude ETFs/bonds/CLOs/warrants/rights"

**Implementation:** `get_active_symbols(exclude_etfs=True)` achieves this for loaders.

**But API endpoints don't follow consistent naming/documentation:**
- `/api/scores` filters ETFs (matches governance)
- `/api/market/breadth` includes ETFs (different behavior)
- `/api/signals` has separate `/etf` endpoint (ETF-aware architecture)

**Question:** Is this intentional (different endpoints for different purposes) or inconsistency?

---

## Required Fixes (Session 246+)

### Priority 1: CRITICAL - Remove Dead Code
- [ ] Delete `utils/symbol_filters.py` (or consolidate into a used location)
- [ ] Document why centralized filters weren't used (was design decision abandoned?)

### Priority 2: HIGH - Enforce Single Source of Truth
- [ ] If symbol_filters.py is restored, ensure ALL filtering goes through it
- [ ] If filters stay hardcoded, document why centralization was rejected
- [ ] Add import checks to CI (ensure filters.py isn't imported unnecessarily)

### Priority 3: HIGH - API Endpoint Consistency
- [ ] [ ] Audit: does `/api/market/breadth` INTEND to include ETFs? (document decision)
- [ ] [ ] Audit: does `/api/signals/stocks` INTEND to exclude ETFs? (enforce in query)
- [ ] [ ] Add comments to each API endpoint documenting intentional filtering (stocks only, ETFs included, indices excluded)

### Priority 4: MEDIUM - Orchestrator Clarity
- [ ] [ ] Document: does Phase 3 generate ETF signals? (if yes, Phase 7 must filter; if no, why?)
- [ ] [ ] Document: does Phase 7 filter the signals before returning? (currently implicit)
- [ ] [ ] Add explicit WHERE clause to Phase 7 to exclude/include ETFs based on design decision

### Priority 5: MEDIUM - Two-Condition ETF Filter
- [ ] [ ] Audit: why are both `etf_symbols` table AND `etf='N'` flag required?
- [ ] [ ] Consolidate to single condition if possible, or document why both are necessary

---

## Questions for User

Before we proceed with fixes, clarify intent:

1. **Should `/api/market/breadth` include ETFs?**
   - Current: Includes ETFs (only filters indices)
   - Governance suggests: Should probably be stocks only?
   - Or is market breadth intentionally including all tradeable assets?

2. **Should symbol_filters.py be restored and used everywhere?**
   - Current: Dead code, never imported
   - Option A: Delete it (filters are intentionally distributed)
   - Option B: Restore it and enforce all filtering through it (centralization)

3. **Should `/api/signals/stocks` explicitly exclude ETFs?**
   - Current: Relies on Phase 7's upstream filtering
   - Recommendation: Add explicit filter to API for defense-in-depth

4. **Should Phase 7 filter its output?**
   - Current: Implicit (depends on what's in buy_sell_daily)
   - Recommendation: Add explicit WHERE clause in Phase 7 (or document why not needed)

---

## Summary Table: Current Filtering Coverage

```
╔════════════════════════════════════════╦════════╦════════╦═══════════════════════╗
║ Component                              ║ Stocks ║ ETFs   ║ Indices (^)           ║
╠════════════════════════════════════════╬════════╬════════╬═══════════════════════╣
║ Loaders (prices, technical)            ║ ✅     ║ ✅     ║ ✅ (via get_active)   ║
║ Loaders (financial, exclude_etfs=True) ║ ✅     ║ ❌     ║ ❌                    ║
║ API /api/scores                        ║ ✅     ║ ❌     ║ No explicit filter    ║
║ API /api/market/breadth                ║ ✅     ║ ✅     ║ ❌                    ║
║ API /api/signals/etf                   ║ ❌     ║ ✅     ║ ❌                    ║
║ API /api/signals/stocks                ║ ✅?    ║ ?      ║ ❌                    ║
║ Orchestrator Phase 7                   ║ ✅?    ║ ?      ║ ❌                    ║
╚════════════════════════════════════════╩════════╩════════╩═══════════════════════╝

✅ = Explicitly filtered
❌ = Explicitly excluded
? = Implicit (depends on upstream)
```

---

## Files Involved

**Core filtering:**
- `utils/symbol_filters.py` (dead code - never used)
- `utils/loaders/helpers.py:get_active_symbols()` (actual loader filtering)
- `loaders/runner.py` (calls get_active_symbols with exclude_etfs)

**API filtering:**
- `lambda/api/routes/scores.py` (hardcoded ETF filter)
- `lambda/api/routes/market.py` (hardcoded index filter)
- `lambda/api/routes/signals.py` (ETF vs stock separation)

**Orchestrator filtering:**
- `algo/orchestrator/phase3b_trend_template.py` (generates buy_sell_daily)
- `algo/orchestrator/phase7_signal_generation.py` (consumes buy_sell_daily)

---

Next: Await guidance on design decisions, then implement fixes.

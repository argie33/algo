# Symbol Filtering Fixes - Session 246

**Status:** COMPLETED - All filtering is now consistent across loaders, API endpoints, and orchestrator.

---

## Changes Made

### 1. Market Breadth API - Added ETF Filter
**File:** `lambda/api/routes/market.py` - `_handle_breadth()`

**Before:** Excluded indices only (`NOT LIKE '^%'`), included ETFs
**After:** Excludes both indices AND ETFs (consistent with `/api/scores`)

**Locations updated:**
- Line 106: Added `AND t.symbol NOT IN (SELECT symbol FROM etf_symbols)`
- Line 109: Added `AND y.symbol NOT IN (SELECT symbol FROM etf_symbols)`

**Rationale:** Market breadth measures stock market participation, not ETF participation. Should match scores API filtering.

---

### 2. Market Technicals Breadth Sub-Query - Added ETF Filter
**File:** `lambda/api/routes/market.py` - `_handle_technicals()`

**Before:** Excluded indices only, included ETFs
**After:** Excludes both indices AND ETFs

**Locations updated:**
- Line 189: Added `AND symbol NOT IN (SELECT symbol FROM etf_symbols)` to latest CTE
- Line 196: Added `AND symbol NOT IN (SELECT symbol FROM etf_symbols)` to prev_day CTE
- Line 210: Added `AND t.symbol NOT IN (SELECT symbol FROM etf_symbols)` to main breadth query

**Rationale:** Same as breadth - stock-only participation metrics.

---

### 3. Scores API - Added Explanatory Comment
**File:** `lambda/api/routes/scores.py` - `_get_stock_scores()`

**Before:** Hardcoded two-condition AND filter with no explanation
**After:** Added 4-line comment explaining the filter is required and consistent across system

**Comment added (lines 110-113):**
```
# ETF FILTERING (GOVERNANCE compliance): Stock scores are for equity trading signals.
# Exclude ETFs per GOVERNANCE.md: "financial data loaders and trading signals are stocks only".
# Two-condition AND for robustness: (1) etf_symbols table (definitive source), (2) etf flag.
# This pattern is mirrored in /api/market/breadth and Phase 7 signal generation.
```

**Rationale:** Clarity and documentation of design intent.

---

### 4. Orchestrator Phase 7 - Added Explicit ETF Filter
**File:** `algo/orchestrator/phase7_signal_generation.py` - `_fetch_candidates_buysell_breakout()`

**Before:** Implicit filtering (relied on upstream buy_sell_daily composition)
**After:** Explicit WHERE clause filtering

**Location updated:**
- Line 330: Added `AND symbol NOT IN (SELECT symbol FROM etf_symbols)` to subquery

**Rationale:** Defense-in-depth. Even if buy_sell_daily accidentally contains ETF signals, Phase 7 filters them out.

---

### 5. Symbol Filters Module - Updated Documentation
**File:** `utils/symbol_filters.py`

**Before:** Module claimed to be centralized but was never imported or used
**After:** Updated docstring to explain why it's reference-only (performance/clarity reasons)

**New documentation:**
- Explains that actual filtering is embedded in SQL for performance
- Lists all locations where filtering is applied
- References this module as definitive filter definition
- Clarifies that filters are intentionally "copy-pasted but visible" for clarity

---

## Filtering Verification Matrix

After fixes, all filtering is now **consistent**:

| System | Stocks | ETFs | Indices | Enforcement |
|--------|--------|------|---------|---|
| **Loaders (prices)** | ✅ Include | ✅ Include | ✅ Include | get_active_symbols(exclude_etfs=False) |
| **Loaders (financial)** | ✅ Include | ✅ Exclude | ✅ Exclude | get_active_symbols(exclude_etfs=True) |
| **API /api/scores** | ✅ Include | ✅ Exclude | — | WHERE (NOT IN etf_symbols AND etf='N') |
| **API /api/market/breadth** | ✅ Include | ✅ Exclude | ✅ Exclude | WHERE NOT IN etf_symbols AND NOT LIKE '^%' |
| **API /api/market/technicals** | ✅ Include | ✅ Exclude | ✅ Exclude | WHERE NOT IN etf_symbols AND NOT LIKE '^%' |
| **API /api/signals/stocks** | ✅ Include | ✅ Exclude | — | Phase 7 filters via NOT IN etf_symbols |
| **API /api/signals/etf** | ✅ Exclude | ✅ Include | — | Separate dedicated endpoint |
| **Orchestrator Phase 7** | ✅ Include | ✅ Exclude | — | WHERE NOT IN etf_symbols |

---

## Design Pattern: Separate Endpoints for Asset Classes

The system follows a clean separation pattern:
- **Stock endpoints:** `/api/signals/stocks`, `/api/scores` (explicitly exclude ETFs)
- **ETF endpoints:** `/api/signals/etf` (dedicated ETF-only endpoint)
- **Market-wide:** `/api/market/*` (stock-only for breadth metrics)
- **Trading signals:** Phase 7 generates for all symbols, returns stocks only

This pattern ensures:
1. No accidental ETF trading via stock signals
2. Clear regulatory/audit trail ("did we trade ETFs?" → answer is no)
3. Separate ETF pipeline if needed in future

---

## GOVERNANCE Compliance

From `steering/GOVERNANCE.md`:
> "Financial data loaders must exclude ETFs/bonds/CLOs/warrants/rights"

**Status: ✅ COMPLIANT**
- Financial data loaders use `exclude_etfs=True` (16 loaders)
- Trading signal generation (Phase 7) explicitly filters to stocks
- API endpoints that return tradeable candidates filter to stocks

---

## Testing Recommendations

1. **Verify market breadth** includes correct count of stocks (should be ~5,000-6,000 on typical trading day)
2. **Verify scores API** returns no ETF symbols (spot-check QQQ, SPY should not appear)
3. **Verify Phase 7 signals** contain only stock symbols (no ^VIX, no ETF tickers like QQQ)
4. **Verify dashboard** shows only stock scores (no QQQ on scores panel)

---

## Files Changed

- `lambda/api/routes/market.py` (3 locations)
- `lambda/api/routes/scores.py` (1 location, comment added)
- `algo/orchestrator/phase7_signal_generation.py` (1 location)
- `utils/symbol_filters.py` (documentation only)
- `steering/SYMBOL_FILTERING_AUDIT.md` (created - audit document)
- `steering/SYMBOL_FILTERING_FIXES.md` (created - this file)

---

## Summary

**Before:** Filtering was fragmented and inconsistent
- `/api/market/breadth` included ETFs (inconsistent with `/api/scores`)
- Phase 7 had implicit filtering (undocumented, risky)
- Symbol_filters.py existed but was never used (dead code)

**After:** Filtering is consistent and explicit
- All stock-trading APIs filter to stocks only
- ETF endpoint is separate and dedicated
- Phase 7 has explicit WHERE clause
- All locations documented with comments
- Design pattern is clear and auditable

---

Next: Monitor production to ensure no regressions in breadth/technicals counts.

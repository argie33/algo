# Loader Cleanup — Final Decisions

**Date:** 2026-05-09  
**Analysis Basis:** Purpose review + usage check + trading relevance + Phase scope  
**Principle:** Keep Phase 1 critical path only; archive/delete everything else

---

## Decision Summary

| Status | Count | Action |
|--------|-------|--------|
| **INTEGRATE** | 1 | Add to Terraform + schedule (performance improvement) |
| **ARCHIVE** | 15 | Move to `/experimental/` (future features or alternatives) |
| **DELETE** | 7 | Remove entirely (dead code or duplicates) |

---

## Tier 1: INTEGRATE (1 loader)

### ✓ `load_eod_bulk.py` — INTEGRATE
**Rationale:**
- **Purpose:** Fast bulk refresh of price_daily for all 5000+ symbols (~5 min vs hours)
- **Current state:** Per-symbol `loadpricedaily.py` is scheduled 4am ET
- **Why integrate:** Performance improvement; EOD bulk is faster approach for daily refresh
- **Phase:** Phase 1 (improves current pipeline)
- **Usage:** Standalone, no conflicts
- **Action:** Add to Terraform at end of trading day (10pm ET = 5:00am UTC next day), schedule after signals complete

**New schedule:** `cron(0 5 ? * TUE-SAT *)` (5am UTC = midnight ET, day after trading)

---

## Tier 2: ARCHIVE to `/experimental/` (15 loaders)

These are legitimate code with clear purpose but not part of current pipeline. Archive for future phases or optional features.

### **Market/Health Extensions (2)**

#### ⊘ `load_market_health_daily.py` — ARCHIVE
**Purpose:** Market breadth, distribution days, market stage (Weinstein), VIX, yield curve  
**Why archive:** Advanced market regime detection — useful for future circuit breaker enhancements but not currently used  
**Phase:** Phase 2 (market regime monitoring)  
**Reason not integrated:** No algo code references market health metrics yet

#### ⊘ `loadcommodities.py` — ARCHIVE
**Purpose:** Commodity prices (oil, gold, etc.)  
**Why archive:** May be useful for macro-driven trading in future, but not in current scope  
**Phase:** Phase 2+ (macro hedge strategies)  
**Reason not integrated:** No commodity impact on equity trading logic

---

### **Content/News Integration (2)**

#### ⊘ `loadnews.py` — ARCHIVE
**Purpose:** Financial news sentiment scraping  
**Why archive:** Alternative to `loadsentiment.py` (already official); news integration is future enhancement  
**Phase:** Phase 2+ (sentiment enhancement)  
**Reason not integrated:** Sentiment already handled by official social_sentiment loader

#### ⊘ `loadsecfilings.py` — ARCHIVE
**Purpose:** SEC filing monitoring (10-K, 10-Q, 8-K)  
**Why archive:** Advanced fundamental analysis; not used by current trading logic  
**Phase:** Phase 3+ (earnings/fundamental event trading)  
**Reason not integrated:** No algo code reacts to SEC filings

---

### **Options/Derivatives (2)**

#### ⊘ `loadoptionschains.py` — ARCHIVE
**Purpose:** Options market data (chains, greeks, IV)  
**Why archive:** For future options trading strategies  
**Phase:** Phase 3+ (covered calls, spreads, hedging)  
**Reason not integrated:** Current scope is equity-only; no options logic in algo

#### ⊘ `loadcoveredcallopportunities.py` — ARCHIVE
**Purpose:** Covered call candidate identification  
**Why archive:** Part of future income strategies; depends on options chains loader  
**Phase:** Phase 3+ (options strategies)  
**Reason not integrated:** No covered call logic in current algo

---

### **Advanced Technical Analysis (3)**

#### ⊘ `loadmeanreversionsignals.py` — ARCHIVE
**Purpose:** Mean reversion signal generator  
**Why archive:** Alternative signal approach; official signals use trend/momentum logic  
**Phase:** Phase 2 (strategy variation)  
**Reason not integrated:** Not in current signal tier architecture; different strategy approach

#### ⊘ `loadrangesignals.py` — ARCHIVE
**Purpose:** Support/resistance range-based signals  
**Why archive:** Complements trend-based signals; nice to have but not critical  
**Phase:** Phase 2 (signal enhancement)  
**Reason not integrated:** Signal tiers already complete; adds complexity without proven benefit

#### ⊘ `loadswingscores.py` — ARCHIVE
**Purpose:** Swing trading score (different timeframe than day/trend scope)  
**Why archive:** For swing traders; current scope is intraday + trend (multi-day)  
**Phase:** Phase 2 (strategy variation)  
**Reason not integrated:** Different trading horizon; complicates current model

---

### **Comparative/Ranking Analysis (3)**

#### ⊘ `loadbenchmark.py` — ARCHIVE
**Purpose:** Benchmark returns comparison (stock vs SPY)  
**Why archive:** For performance analytics; not needed for trading decisions  
**Phase:** Phase 2 (dashboard analytics)  
**Reason not integrated:** Used by dashboard, not by algo trading logic

#### ⊘ `loadsectorranking.py` — ARCHIVE
**Purpose:** Sector momentum ranking (alternative to `loadsectors.py`)  
**Why archive:** Sector data already loaded by official `loadsectors.py`; this is alternative calculation  
**Phase:** Phase 1 (but superseded)  
**Reason not integrated:** Duplicate concept; official loader already provides sector data

#### ⊘ `loadindustryranking.py` — ARCHIVE
**Purpose:** Industry momentum ranking  
**Why archive:** Sector-level analysis; might complement stock scores but not critical  
**Phase:** Phase 2 (enhanced stock ranking)  
**Reason not integrated:** No industry-level logic in current algo; sector-level data sufficient

---

### **Company Data Extensions (2)**

#### ⊘ `loaddailycompanydata.py` — ARCHIVE
**Purpose:** Daily company metrics (employee count, market cap changes, etc.)  
**Why archive:** Interesting but not used for trading; nice to have for analytics  
**Phase:** Phase 2+ (fundamental analytics)  
**Reason not integrated:** No algo code references daily company data

#### ⊘ `loadforwardeps.py` — ARCHIVE
**Purpose:** Forward earnings estimates  
**Why archive:** Earnings data already loaded (`earnings_revisions`, `earnings_surprise`); this is variant  
**Phase:** Phase 1 (but superseded)  
**Reason not integrated:** Earnings data already available; forward vs trailing is minor distinction

---

### **Account Integration (1)**

#### ⊘ `loadalpacaportfolio.py` — ARCHIVE
**Purpose:** Real-time Alpaca account holdings for dashboard  
**Why archive:** Dashboard can use `algo_positions` table; this adds complexity for live sync  
**Phase:** Phase 2 (dashboard live updates)  
**Reason not integrated:** Position reconciliation already happens in Phase 7 (`algo_daily_reconciliation.py`); portfolio_holdings table unused by algo

---

## Tier 3: DELETE (7 loaders)

These files should be removed entirely — either dead code, superseded, or redundant.

### ✗ `loadmultisource_ohlcv.py` — DELETE
**Reason:** Multi-source OHLCV pattern (Alpaca primary + yfinance fallback) never used; `loadpricedaily.py` uses single yfinance source and works fine  
**Risk:** No imports, no usage  
**Action:** Delete

### ✗ `loader_base_optimized.py` — DELETE
**Reason:** Template/pattern file; actual loaders don't inherit from this  
**Risk:** No imports  
**Action:** Delete (not examples/, actual template that's never used)

### ✗ `loader_with_watermark_example.py` — DELETE
**Reason:** Example code for watermark integration; `optimal_loader.py` shows the real pattern  
**Risk:** No imports  
**Action:** Delete (documentation example, not production code)

### ✗ `loader_polars_base.py` — DELETE
**Reason:** Polars-based base class (pandas version already working fine); tech spike that didn't ship  
**Risk:** No imports, no active usage  
**Action:** Delete

### ✗ Files that don't exist or are .DISABLED:

#### ✗ `loaders.sh.DISABLED` — DELETE
**Reason:** Shell script for manual loader execution; Terraform/EventBridge replaced this  
**Risk:** Outdated, not used  
**Action:** Delete

---

## Summary Table

| Loader | Decision | Reason | Archive Dir |
|--------|----------|--------|-------------|
| load_eod_bulk.py | **INTEGRATE** | Faster price refresh | — |
| load_market_health_daily.py | ARCHIVE | Market regime (Phase 2) | experimental/ |
| loadcommodities.py | ARCHIVE | Macro hedging (Phase 2+) | experimental/ |
| loadnews.py | ARCHIVE | News sentiment (Phase 2) | experimental/ |
| loadsecfilings.py | ARCHIVE | Fundamental events (Phase 3+) | experimental/ |
| loadoptionschains.py | ARCHIVE | Options trading (Phase 3+) | experimental/ |
| loadcoveredcallopportunities.py | ARCHIVE | Covered calls (Phase 3+) | experimental/ |
| loadmeanreversionsignals.py | ARCHIVE | Alt signal (Phase 2) | experimental/ |
| loadrangesignals.py | ARCHIVE | Alt signal (Phase 2) | experimental/ |
| loadswingscores.py | ARCHIVE | Swing trading (Phase 2) | experimental/ |
| loadbenchmark.py | ARCHIVE | Performance analytics (Phase 2) | experimental/ |
| loadsectorranking.py | ARCHIVE | Redundant sector data | experimental/ |
| loadindustryranking.py | ARCHIVE | Industry analysis (Phase 2) | experimental/ |
| loaddailycompanydata.py | ARCHIVE | Company metrics (Phase 2+) | experimental/ |
| loadforwardeps.py | ARCHIVE | Earnings variant (Phase 1) | experimental/ |
| loadalpacaportfolio.py | ARCHIVE | Live dashboard sync (Phase 2) | experimental/ |
| loadmultisource_ohlcv.py | DELETE | Unused fallback pattern | — |
| loader_base_optimized.py | DELETE | Unused template | — |
| loader_with_watermark_example.py | DELETE | Unused example | — |
| loader_polars_base.py | DELETE | Unused tech spike | — |
| loaders.sh.DISABLED | DELETE | Outdated shell script | — |

---

## Implementation Plan

### Step 1: Create `/experimental/` directory
```
experimental/
  README.md (explains these are future/optional features)
  loaders/
    load_market_health_daily.py
    loadcommodities.py
    ... (all 15 archived loaders)
```

### Step 2: Delete unused code
- `loadmultisource_ohlcv.py`
- `loader_base_optimized.py`
- `loader_with_watermark_example.py`
- `loader_polars_base.py`
- `loaders.sh.DISABLED`

### Step 3: Integrate `load_eod_bulk.py`
Add to `terraform/modules/loaders/main.tf`:
```hcl
"eod_bulk_refresh" = "load_eod_bulk.py"

"eod_bulk_refresh" = {
  schedule    = "cron(0 5 ? * TUE-SAT *)"  # 5am UTC = midnight ET next day
  description = "EOD bulk price refresh - all symbols in 5 min"
}

"eod_bulk_refresh" = { cpu = 512, memory = 1024, timeout = 600 }
```

### Step 4: Verify no orphaned imports
```bash
for f in loadmultisource_ohlcv.py loader_base_optimized.py ...; do
  grep -r "from ${f%.*} import\|import ${f%.*}" algo*.py
done
```
(Should return nothing)

### Step 5: Commit with clear rationale
```
feat: Consolidate loader architecture - 1 integrate, 15 archive, 5 delete

INTEGRATE:
- load_eod_bulk.py: Faster EOD price refresh (5 min vs hours)

ARCHIVED to /experimental/:
- Market health, commodities, news, SEC filings, options, alternative signals,
  comparative analysis, company data, account sync (all Phase 2+ features)

DELETED:
- Unused templates, examples, fallback patterns, outdated scripts
```

---

## Result

**Official Pipeline:** 42 loaders (41 original + 1 eod_bulk)  
**Experimental Pipeline:** 15 loaders (future phases)  
**Removed:** 5 files (dead code)  
**Total codebase:** 62 files (down from 67)

**Architecture benefit:** Clean separation between Phase 1 (production) and Phase 2+ (future), eliminating confusion about which loaders are shipped vs aspirational.

# Financial Data Loader Dependency Matrix

**Complete dependency analysis of all 57 data loaders**
**Generated: February 7, 2026**

---

## Quick Reference: Critical Path

```
CRITICAL PATH (Minimum for Admin Dashboard):
  1. loadstocksymbols.py (10 min)
     ↓
  2. loadsectors.py (5 min)
     ↓
  3. loadpricedaily.py (60 min) ← LONGEST
     ↓
  4. loadearningshistory.py (30 min)

Total: ~105 minutes (1.75 hours)
Symbols after: 5000+
Prices after: 10M+ records
Earnings after: 100K+ records
```

---

## Foundation Loaders (Independent)

### Group 1: Base Data

| Loader | Purpose | Inputs | Outputs | Time | Critical |
|--------|---------|--------|---------|------|----------|
| **loadstocksymbols.py** | Load all stock & ETF symbols | NASDAQ API | stock_symbols, etf_symbols | 3-5 min | YES |
| **loadsectors.py** | Load sector/industry classification | stock_symbols | sectors, industries, sector_performance | 2-5 min | YES |

**Dependencies:** None - can run first
**Blocking:** 32+ loaders depend on stock_symbols

---

## Price Data Loaders

### Group 2A: Daily Price Data (Depends on: stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadpricedaily.py** | Historical daily OHLCV for stocks | stock_symbols | price_daily | 45-60 min | stock_symbols |
| **loadpriceweekly.py** | Weekly aggregated prices | stock_symbols | price_weekly | 10-15 min | stock_symbols |
| **loadpricemonthly.py** | Monthly aggregated prices | stock_symbols | price_monthly | 10-15 min | stock_symbols |
| **loadlatestpricedaily.py** | Latest daily price snapshot | stock_symbols | latest_price_daily | 5-10 min | stock_symbols |
| **loadlatestpriceweekly.py** | Latest weekly price snapshot | stock_symbols | latest_price_weekly | 5-10 min | stock_symbols |
| **loadlatestpricemonthly.py** | Latest monthly price snapshot | stock_symbols | latest_price_monthly | 5-10 min | stock_symbols |

**Critical Success Factor:**
- `loadpricedaily.py` is the longest-running loader
- Must complete before metrics/score calculation
- Can run multiple price loaders in parallel after symbols loaded

### Group 2B: ETF Price Data (Depends on: etf_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadetfpricedaily.py** | Historical daily OHLCV for ETFs | etf_symbols | etf_price_daily | 15-20 min | etf_symbols |
| **loadetfpriceweekly.py** | Weekly aggregated ETF prices | etf_symbols | etf_price_weekly | 5-10 min | etf_symbols |
| **loadetfpricemonthly.py** | Monthly aggregated ETF prices | etf_symbols | etf_price_monthly | 5-10 min | etf_symbols |

---

## Earnings Data Loaders

### Group 3: Earnings (Depends on: stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies | Blocks |
|--------|---------|--------|---------|------|--------------|--------|
| **loadearningshistory.py** | Historical earnings history | stock_symbols | earnings_history | 25-35 min | stock_symbols | earnings_surprise |
| **loadearningssurprise.py** | EPS surprise percentages | stock_symbols, earnings_history | earnings_surprise | 10-15 min | earnings_history | factor_metrics |
| **loadearningsrevisions.py** | Analyst estimate revisions | stock_symbols | earnings_revisions | 10-15 min | stock_symbols | - |
| **loadguidance.py** | Forward earnings guidance | stock_symbols | earnings_guidance | 8-12 min | stock_symbols | - |

**Critical:**
- `loadearningshistory.py` must complete before `loadearningssurprise.py`
- `earnings_surprise` data feeds into `loadfactormetrics.py`

---

## Financial Statements Loaders

### Group 4: Income Statements (Depends on: stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadannualincomestatement.py** | Annual income statements | stock_symbols | annual_income_statement | 8-10 min | stock_symbols |
| **loadquarterlyincomestatement.py** | Quarterly income statements | stock_symbols | quarterly_income_statement | 8-10 min | stock_symbols |
| **loadttmincomestatement.py** | TTM income data | stock_symbols | ttm_income_statement | 5-8 min | stock_symbols |

### Group 5: Balance Sheets (Depends on: stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadannualbalancesheet.py** | Annual balance sheets | stock_symbols | annual_balance_sheet | 8-10 min | stock_symbols |
| **loadquarterlybalancesheet.py** | Quarterly balance sheets | stock_symbols | quarterly_balance_sheet | 8-10 min | stock_symbols |

### Group 6: Cash Flow (Depends on: stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadannualcashflow.py** | Annual cash flow statements | stock_symbols | annual_cash_flow | 8-10 min | stock_symbols |
| **loadquarterlycashflow.py** | Quarterly cash flow statements | stock_symbols | quarterly_cash_flow | 8-10 min | stock_symbols |
| **loadttmcashflow.py** | TTM cash flow data | stock_symbols | ttm_cash_flow | 5-8 min | stock_symbols |

---

## Sentiment & Analyst Data Loaders

### Group 7: Analyst Data (Depends on: stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadanalystsentiment.py** | Analyst buy/hold/sell ratings | stock_symbols | analyst_sentiment | 10-15 min | stock_symbols |
| **loadanalystupgradedowngrade.py** | Rating changes | stock_symbols | analyst_upgrades_downgrades | 8-12 min | stock_symbols |
| **loadanalystrevisiondata.py** | Estimate revisions | stock_symbols | analyst_revision_data | 8-12 min | stock_symbols |

### Group 8: Market Sentiment (Depends on: stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadsentiment.py** | Market sentiment scores | stock_symbols | sentiment | 8-12 min | stock_symbols |
| **loadnews.py** | Financial news data | stock_symbols | news | 15-20 min | stock_symbols |

### Group 9: Insider Data (Depends on: stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadinsidertransactions.py** | Insider buying/selling | stock_symbols | insider_transactions | 10-15 min | stock_symbols |

---

## Metrics & Scores Loaders

### Group 10: Factor Metrics (Depends on: price_daily, earnings_history)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies | Blocks |
|--------|---------|--------|---------|------|--------------|--------|
| **loadfactormetrics.py** | Value/growth/quality factors | price_daily, earnings_history, earnings_surprise | factor_metrics | 15-20 min | price_daily, earnings_history | stock_scores |

**Critical:**
- Requires BOTH price_daily AND earnings_history
- Must complete before stock_scores calculation

### Group 11: Fundamental Metrics (Depends on: stock_symbols, financial statements)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies | Blocks |
|--------|---------|--------|---------|------|--------------|--------|
| **loadfundamentalmetrics.py** | P/E, P/B, dividend yield, etc. | stock_symbols, financial data | fundamental_metrics | 12-15 min | stock_symbols | stock_scores |
| **loadpositioningmetrics.py** | Positioning metrics | stock_symbols, price_daily | positioning_metrics | 10-12 min | price_daily | stock_scores |

### Group 12: Composite Scores (Depends on: All prior metrics)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadstockscores.py** | Comprehensive 0-100 scores | factor_metrics, fundamental_metrics, positioning_metrics | stock_scores | 15-20 min | All metric loaders |

**Critical:**
- FINAL loader in metrics chain
- Synthesizes all prior metrics
- Should run LAST of all loaders

---

## Technical Indicator Loaders

### Group 13: Buy/Sell Signals (Depends on: stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadbuyselldaily.py** | Daily buy/sell signals | stock_symbols | buysell_daily | 8-12 min | stock_symbols |
| **loadbuysellweekly.py** | Weekly buy/sell signals | stock_symbols | buysell_weekly | 8-12 min | stock_symbols |
| **loadbuysellmonthly.py** | Monthly buy/sell signals | stock_symbols | buysell_monthly | 8-12 min | stock_symbols |

### Group 14: ETF Buy/Sell Signals (Depends on: etf_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadbuysell_etf_daily.py** | Daily ETF signals | etf_symbols | buysell_etf_daily | 5-8 min | etf_symbols |
| **loadbuysell_etf_weekly.py** | Weekly ETF signals | etf_symbols | buysell_etf_weekly | 5-8 min | etf_symbols |
| **loadbuysell_etf_monthly.py** | Monthly ETF signals | etf_symbols | buysell_etf_monthly | 5-8 min | etf_symbols |

### Group 15: Performance & Rankings (Depends on: price_daily, stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadrelativeperformance.py** | Outperformance metrics | price_daily | relative_performance | 10-12 min | price_daily |
| **loadseasonality.py** | Seasonal patterns | price_daily | seasonality | 8-10 min | price_daily |
| **loadsectorranking.py** | Sector performance rankings | sectors | sector_ranking | 5-8 min | stock_symbols |
| **loadindustryranking.py** | Industry performance rankings | industries | industry_ranking | 5-8 min | stock_symbols |

### Group 16: Market Sentiment (Depends on: stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadaaiidata.py** | AAII investor sentiment | stock_symbols | aaii_data | 8-10 min | stock_symbols |
| **loadnaaim.py** | NAAIM positioning data | stock_symbols | naaim_data | 8-10 min | stock_symbols |

---

## Optional/Secondary Loaders

### Group 17: Economic & Market Data (Independent)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadecondata.py** | Economic indicators | External APIs | econ_data | 10-15 min | - |
| **loadfeargreed.py** | CNN Fear & Greed Index | External APIs | fear_greed | 5 min | - |
| **loadmarket.py** | Market data & indices | External APIs | market_data | 10-12 min | - |
| **loadmarketindices.py** | Major indices data | External APIs | market_indices | 8-10 min | - |
| **loadbenchmark.py** | Benchmark performance | External APIs | benchmark_data | 8-10 min | - |

### Group 18: Company Data (Depends on: stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loaddailycompanydata.py** | Real-time company data | stock_symbols, APIs | daily_company_data | 15-20 min | stock_symbols |
| **loadsecfilings.py** | SEC filing data | stock_symbols, SEC APIs | sec_filings | 15-20 min | stock_symbols |

### Group 19: Options & Derivatives (Depends on: stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadoptionschains.py** | Options chain data | price_daily | options_chains | 20-30 min | price_daily |
| **loadcoveredcallopportunities.py** | Covered call opportunities | price_daily | covered_calls | 15-20 min | price_daily |

### Group 20: Calendar & Other (Depends on: stock_symbols)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadcalendar.py** | Economic calendar | External APIs | calendar_events | 5-10 min | - |
| **loadcommodities.py** | Commodity prices | External APIs | commodities | 8-10 min | - |

### Group 21: Portfolio (Depends on: Alpaca API)

| Loader | Purpose | Inputs | Outputs | Time | Dependencies |
|--------|---------|--------|---------|------|--------------|
| **loadalpacaportfolio.py** | Alpaca portfolio data | Alpaca API | portfolio_data | 5-10 min | ALPACA_API_KEY |

---

## Dependency Chain Analysis

### Tier 0: Independent (Can run anytime)

```
loadstocksymbols.py
loadsectors.py
```

### Tier 1: Depends on stock_symbols (32 loaders)

```
loadpricedaily.py
loadpriceweekly.py
loadpricemonthly.py
loadlatestpricedaily.py
loadlatestpriceweekly.py
loadlatestpricemonthly.py
... (and 26 more)
```

### Tier 2: Depends on Tier 1 (price data)

```
loadfactormetrics.py          → requires price_daily
loadrelativeperformance.py    → requires price_daily
loadseasonality.py            → requires price_daily
loadsectors.py                → requires price_daily (secondary run)
loadoptionschains.py          → requires price_daily
```

### Tier 3: Depends on earnings data

```
loadearningssurprise.py       → requires earnings_history
loadfactormetrics.py          → requires earnings_history + earnings_surprise
```

### Tier 4: Depends on all metrics

```
loadstockscores.py            → requires ALL metric loaders
```

---

## Parallel Execution Matrix

**Loaders that CAN run in parallel:**

```
PHASE 1 (0 dependencies):
  loadstocksymbols.py
  loadsectors.py

PHASE 2 (depends on symbols):
  loadpricedaily.py
  loadpriceweekly.py         ┐
  loadpricemonthly.py        │ Can run in parallel
  loadlatestpricedaily.py    │
  loadlatestpriceweekly.py   │
  loadlatestpricemonthly.py  ┘

  loadearningshistory.py     ┐
  loadearningsrevisions.py   │ Can run in parallel
  loadguidance.py            ┘

  loadannualincomestatement.py   ┐
  loadquarterlyincomestatement.py├─ Financial statements
  loadannualbalancesheet.py      │  Can run in parallel
  loadquarterlybalancesheet.py   │
  loadannualcashflow.py          │
  loadquarterlycashflow.py       ┘

  loadanalystsentiment.py        ┐
  loadanalystupgradedowngrade.py├─ Analyst data
  loadnews.py                    │  Can run in parallel
  loadsentiment.py               │
  loadinsidertransactions.py     ┘

PHASE 3 (depends on Phase 2):
  loadfactormetrics.py
  loadfundamentalmetrics.py  ┐
  loadpositioningmetrics.py  │ Can run in parallel

PHASE 4 (depends on Phase 3):
  loadstockscores.py         ← MUST run last

PHASE 5 (independent):
  Technical indicators      ┐
  Market data              │ Can run in parallel
  Optional loaders         │ (except after core phases)
  ETF data                 ┘
```

---

## Load Order Cheat Sheet

### Minimum (MVP Dashboard)

```
1. loadstocksymbols.py        (5 min)
2. loadsectors.py             (5 min)
3. loadpricedaily.py          (60 min)
4. loadearningshistory.py     (30 min)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total: ~100 minutes
```

### Standard (Full Featured)

```
1. loadstocksymbols.py
2. loadsectors.py
3. loadpricedaily.py
4. loadpriceweekly.py
5. loadpricemonthly.py
6. loadearningshistory.py
7. loadearningsrevisions.py
8. loadearningssurprise.py
9-16. Financial statements (8 loaders)
17-21. Analyst data (5 loaders)
22. loadfactormetrics.py
23. loadfundamentalmetrics.py
24. loadpositioningmetrics.py
25. loadstockscores.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total: ~3.5 hours
```

### Complete (All 57 loaders)

```
All of Standard, plus:
26-38. Technical indicators (13 loaders)
39-57. Optional/secondary (19 loaders)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total: ~4.5 hours
```

---

## Runtime Optimization

### Sequential (Safe, Memory-Efficient)
- **Total Time:** 4.5 hours
- **RAM Peak:** 600MB
- **Disk I/O:** Continuous
- **Best for:** Laptops, shared infrastructure

```bash
for loader in loadstocksymbols loadpricedaily loadearningshistory ...; do
  python3 ${loader}.py || exit 1
done
```

### Parallel Phase Groups (Balanced)
- **Total Time:** 2.5-3 hours
- **RAM Peak:** 1-2GB
- **Disk I/O:** Spiky
- **Best for:** Development machines with 4+ cores

```bash
# Run groups in parallel
{
  python3 loadannualincomestatement.py
  python3 loadannualbalancesheet.py
  python3 loadannualcashflow.py
} &

{
  python3 loadanalystsentiment.py
  python3 loadanalystupgradedowngrade.py
  python3 loadnews.py
} &

wait
python3 loadstockscores.py  # Run last
```

### Full Parallel (Aggressive)
- **Total Time:** 1.5-2 hours
- **RAM Peak:** 2-4GB
- **Disk I/O:** Very heavy
- **Best for:** Powerful workstations only
- **Caution:** May overwhelm network, yfinance rate limiting

```bash
# Run all non-blocking loaders in parallel
python3 loadstocksymbols.py &
python3 loadsectors.py &
wait

# Then run all tier-1 loaders in parallel
python3 loadpricedaily.py &
python3 loadearningshistory.py &
... (all symbol-dependent loaders) &
wait

# Finally run metric loaders
python3 loadfactormetrics.py &
python3 loadfundamentalmetrics.py &
python3 loadpositioningmetrics.py &
wait

python3 loadstockscores.py
```

---

## Blocker Dependencies (Critical Path)

```
loadstocksymbols.py
    ↓ (blocks 32 loaders)
loadpricedaily.py
    ↓ (blocks 5 loaders)
loadfactormetrics.py
    ↓ (blocks 1 loader)
loadstockscores.py ← FINAL

loadearningshistory.py
    ↓ (blocks 1 loader)
loadearningssurprise.py
    ↓ (blocks 1 loader)
loadfactormetrics.py (also blocks on this)
```

---

## Common Troubleshooting by Loader

| Loader | Common Issues | Solution |
|--------|---------------|----------|
| loadstocksymbols.py | Network timeout | Retry, may need VPN |
| loadpricedaily.py | Rate limiting (429) | Wait 2-5 minutes, retry |
| loadearningshistory.py | Missing data for IPOs | Expected, loader skips |
| loadfactormetrics.py | Missing dependencies | Ensure price + earnings loaded |
| loadstockscores.py | NULL values in output | Check all metric loaders completed |
| loadoptionschains.py | OOM | Split into batches or run separately |
| Any loader | Database connection error | Verify PostgreSQL running |
| Any loader | Table not found | Re-run dependency loader |

---

## Notes

1. **Order Matters:** Respect the dependency chain. Running loaders out of order will cause failures.

2. **Idempotent:** Most loaders are idempotent - running them twice is safe and will update data.

3. **Incremental:** Use `last_updated` table to track which loaders ran and when.

4. **Rate Limiting:** yfinance has aggressive rate limiting (~20 req/min). Loaders include exponential backoff but sequential runs are safer.

5. **Memory:** Each loader has peak memory usage during batch processing. Monitor with `watch -n 5 'ps aux | grep python3'`

6. **Network:** All loaders download external data. Ensure stable internet connection, especially for price/earnings data.

7. **Database:** PostgreSQL must be running and accessible. Use `PGPASSWORD=stocks psql` to test connection.

8. **Timestamps:** Check `last_updated` table to verify loader completion and troubleshoot failures.


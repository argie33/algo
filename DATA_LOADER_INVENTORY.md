# Complete Data Loader Inventory

## Loaders by Category

### CORE PRICE DATA
| Loader | Table | Full Data? | Status | Dependencies |
|--------|-------|-----------|--------|--------------|
| `loadpricedaily.py` | `price_daily` | ✅ 2.05M rows (10K+ stocks) | COMPLETE | eod_bulk_refresh |
| `load_technical_data_daily.py` | `technical_data_daily` | ⏳ In progress | PENDING | price_daily (10K+ stocks) |
| `technical_indicators.py` | technical_data_daily | ⏳ In progress | PENDING | price_daily |

### EARNINGS & FINANCIAL DATA
| Loader | Table | Full Data? | Status | Notes |
|--------|-------|-----------|--------|-------|
| `loadearningsestimates.py` | earnings_estimates | ? | TBD | Need to run on all 10K+ stocks |
| `loadearningshistory.py` | earnings_history | ? | TBD | Need to run on all 10K+ stocks |
| `load_earnings_calendar.py` | earnings_calendar | ? | TBD | Upcoming earnings |
| `loadearningsrevisions.py` | (joins earnings_estimates) | ? | TBD | Estimate revisions |
| `load_income_statement.py` | (financial data) | ? | TBD | P&L data |
| `load_balance_sheet.py` | (financial data) | ? | TBD | Balance sheet |
| `load_cash_flow.py` | (financial data) | ? | TBD | Cash flow |

### FUNDAMENTAL METRICS & SCORES
| Loader | Table | Full Data? | Status | Notes |
|--------|-------|-----------|--------|-------|
| `load_quality_metrics.py` | quality_metrics | ? | TBD | ROE, margins, ratios |
| `load_growth_metrics.py` | growth_metrics | ? | TBD | Revenue/EPS growth |
| `load_value_metrics.py` | value_metrics | ? | TBD | P/E, P/B, yield |
| `load_swing_trader_scores.py` | stock_scores | ? | TBD | Swing trading ranking |
| `loadstockscores.py` | stock_scores | ? | TBD | Composite quality score |

### ANALYST DATA
| Loader | Table | Full Data? | Status | Notes |
|--------|-------|-----------|--------|-------|
| `loadanalystsentiment.py` | analyst_sentiment_analysis | ? | TBD | Buy/hold/sell consensus |
| `loadanalystupgradedowngrade.py` | analyst_upgrade_downgrade | ? | TBD | Rating changes |

### MARKET & SECTOR DATA
| Loader | Table | Full Data? | Status | Notes |
|--------|-------|-----------|--------|-------|
| `loadstocksymbols.py` | stock_symbols | ✅ | COMPLETE | Master stock list |
| `loadcompanyprofile.py` | company_profile | ? | TBD | Sector, industry info |
| `loadsectors.py` | (sector data) | ? | TBD | Sector metrics |
| `loadindustryranking.py` | (industry data) | ? | TBD | Industry metrics |
| `load_sector_ranking.py` | (sector ranking) | ? | TBD | Sector rankings |
| `loadmarketindices.py` | market_data | ? | TBD | S&P, Nasdaq, Dow |

### SENTIMENT & PSYCHOLOGICAL DATA
| Loader | Table | Full Data? | Status | Notes |
|--------|-------|-----------|--------|-------|
| `loadaaiidata.py` | aaii_sentiment | ? | TBD | AAII survey |
| `loadnaaim.py` | naaim | ? | TBD | NAAIM strategist index |
| `loadfeargreed.py` | fear_greed_index | ? | TBD | CNN Fear/Greed |

### ECONOMIC & MARKET HEALTH DATA
| Loader | Table | Full Data? | Status | Notes |
|--------|-------|-----------|--------|-------|
| `loadecondata.py` | (economic data) | ? | TBD | Fed rate, GDP, inflation |
| `load_market_health_daily.py` | market_sentiment | ? | TBD | VIX, put/call, breadth |
| `loadseasonality.py` | (seasonal data) | ? | TBD | Seasonal patterns |
| `load_ttm_aggregates.py` | (TTM data) | ? | TBD | Trailing twelve months |

### TRADING SIGNALS & ALGO
| Loader | Table | Full Data? | Status | Notes |
|--------|-------|-----------|--------|-------|
| `loadbuyselldaily.py` | buy_sell_daily | ? | TBD | Daily trade signals |
| `load_signal_quality_scores.py` | (signal scores) | ? | TBD | Signal quality ratings |
| `load_algo_metrics_daily.py` | (algo metrics) | ? | TBD | Algorithm performance |
| `algo_continuous_monitor.py` | (monitoring) | - | LIVE MONITOR | Real-time monitoring |

### POSITIONING DATA
| Loader | Table | Full Data? | Status | Notes |
|--------|-------|-----------|--------|-------|
| `load_weight_optimization.py` | (weight data) | ? | TBD | Portfolio weights |

### SYSTEM TABLES (Pre-populated)
| Loader | Table | Full Data? | Status | Notes |
|--------|-------|-----------|--------|-------|
| (manual) | stock_symbols | ✅ | COMPLETE | Master list |
| (manual) | users | ✅ | COMPLETE | User accounts |
| (manual) | (other system tables) | ✅ | COMPLETE | Settings, schemas |

---

## API Endpoint Hierarchy

**API Routes** (from api_router.py):
```
/api/algo          — Trading algorithm state
/api/financials    — Income statement, balance sheet, cash flow
/api/earnings      — Historical + estimated earnings
/api/signals       — Daily/weekly/monthly buy/sell signals
/api/prices        — Daily/weekly/monthly OHLCV prices
/api/stocks        — Stock info, symbols, master data
/api/sectors       — Sector performance, grouping
/api/industries    — Industry metrics, rankings
/api/market        — Market indices, breadth, health
/api/economic      — Fed data, treasury rates, macro
/api/sentiment     — Analyst, AAII, NAAIM, Fear/Greed
/api/scores        — Quality, growth, value, momentum scores
/api/research      — Company research, profiles
/api/audit         — Data loader audit trail
/api/trades        — User trades and positions
/api/admin         — Admin operations
/api/contact       — Contact form handling
/api/settings      — User preferences
```

---

## Data Dependencies Tree

**Level 0 (Base/Master):**
- `stock_symbols` (10,153 stocks)

**Level 1 (Price Data - feeds everything):**
- `price_daily` ← loadpricedaily.py ✅ COMPLETE (2.05M rows)
- `company_profile` ← loadcompanyprofile.py (sectors, industries)

**Level 2 (Derived Indicators - built from Level 1):**
- `technical_data_daily` ← load_technical_data_daily.py ⏳ PENDING
- `buy_sell_daily` ← Generated by signals engine (Phase 5)
- `stock_scores` ← Composite from quality/growth/value/momentum

**Level 3 (Fundamental/Analyst):**
- Earnings, analyst sentiment, balance sheet, cash flow
- Growth metrics, quality metrics, value metrics

**Level 4 (Market Context):**
- Economic data, market indices, sentiment indices
- AAII, NAAIM, Fear/Greed

---

## Priority Load Order

### PHASE 1: FOUNDATION ✅
1. ✅ stock_symbols (10,153 stocks)
2. ✅ price_daily (2.05M rows from loadpricedaily.py + eod_bulk_refresh)

### PHASE 2: READY (do next)
3. ⏳ **technical_data_daily** (load_technical_data_daily.py on all 10K stocks)
4. ⏳ **buy_sell_daily** (algo signals engine on all stocks)
5. ⏳ **company_profile** (sector/industry mapping for all stocks)

### PHASE 3: CORE BUSINESS DATA (in parallel)
6. Earnings data (all 3 loaders: estimates, history, calendar)
7. Analyst sentiment + upgrades/downgrades
8. Fundamental metrics (quality, growth, value, positioning)
9. Stock scores (composite)

### PHASE 4: MARKET CONTEXT
10. Market health (indices, breadth, VIX, put/call)
11. Economic data (Fed, Treasury, inflation)
12. Sentiment indices (AAII, NAAIM, Fear/Greed)
13. Seasonality patterns

### PHASE 5: NICE-TO-HAVE
14. TTM aggregates, weight optimization, research data

---

## What's Missing / Blocked?

| Status | Item | Impact |
|--------|------|--------|
| ⏳ | technical_data_daily on 10K stocks | Frontend can't show indicators, signals can't generate |
| ⏳ | buy_sell_daily signals | Frontend trade signals empty, user value = 0 |
| ❓ | Earnings data (all 3 loaders) | Frontend earnings tab empty |
| ❓ | Analyst sentiment | Frontend sentiment empty |
| ❓ | Fundamental metrics | Frontend valuation/growth tabs empty |
| ❓ | Stock scores composite | Can't rank/filter stocks |
| ❓ | Market health data | Dashboard missing context |
| ❓ | Economic data | Macro view missing |
| ✅ | Price data | 2.05M rows loaded |
| ✅ | Stock symbols | 10,153 stocks |

---

## Questions to Answer

1. **Scale**: How many rows per loader for 10K+ stocks? Estimate API call counts per loader.
2. **Rates**: Which data sources rate-limit? (yfinance capped at 150 calls/min now, what about others?)
3. **Scope**: Do ALL loaders need ALL stocks, or is there a subset (e.g., S&P 500 only)?
4. **Frequency**: Which loaders run daily vs. once/weekly/monthly?
5. **Data freshness**: How old is acceptable for each data type?

---

## Success Criteria

- [ ] All loaders run without timeout/rate-limit errors
- [ ] All 10,153 stocks have price data (2.05M+ rows) ✅
- [ ] All 10,153 stocks have technical indicators
- [ ] All 10,153 stocks have buy/sell signals
- [ ] All 10,153 stocks have earnings data (estimates + history)
- [ ] All 10,153 stocks have analyst sentiment
- [ ] All 10,153 stocks have fundamental metrics
- [ ] All 10,153 stocks have composite scores
- [ ] Frontend dashboard shows real data (4/13 pages at 100%)
- [ ] API endpoints return non-empty results for all routes

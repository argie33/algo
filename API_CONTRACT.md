# API Contract Specification

**Purpose:** Define required columns/fields for each Lambda API endpoint to ensure frontend-API alignment.

**Status:** Production - Base specification. Update when endpoints change.

---

## Critical Endpoints (Used on Dashboard)

### 1. `/api/scores/stockscores`
**Frontend Page:** ScoresDashboard.jsx  
**Method:** GET  
**Required Columns:**
- `symbol` (string)
- `swing_score` (float, 0-100)
- `grade` (string, A+/A/B/C/D/F)
- `trend_score` (float)
- `market_cap` (numeric)
- `price` (float)
- `change_pct` (float, percentage)
- `date` (date)

**Query:** Must select from `swing_trader_scores` LEFT JOIN `price_daily` + `company_profile`

---

### 2. `/api/stocks/deep-value`
**Frontend Page:** DeepValueStocks.jsx  
**Method:** GET  
**Required Columns:**
- `symbol` (string)
- `company_name` (string)
- `price` (float)
- `eps` (float)
- `pe_ratio` (float)
- `pb_ratio` (float)
- `roe` (float, %)
- `debt_to_equity` (float)
- `market_cap` (numeric)
- `sector` (string)
- `industry` (string)

---

### 3. `/api/algo/swing-scores?symbol={SYMBOL}`
**Frontend Page:** Dashboard (individual stock details)  
**Method:** GET  
**Required Columns:**
- `swing_score` (float)
- `grade` (string)
- `components` (JSON):
  - `setup_quality` {pts, max, detail}
  - `trend_quality` {pts, max, detail}
  - `momentum_rs` {pts, max, detail}
  - `volume` {pts, max, detail}
  - `fundamentals` {pts, max, detail}
  - `sector_industry` {pts, max, detail}
  - `multi_timeframe` {pts, max, detail}

---

### 4. `/api/prices/history/{SYMBOL}`
**Frontend Page:** Portfolio, TradeTracker (chart data)  
**Method:** GET  
**Required Columns:**
- `date` (date/timestamp)
- `open` (float)
- `high` (float)
- `low` (float)
- `close` (float)
- `volume` (numeric)

**Parameters:**
- `timeframe` (daily, weekly, monthly)
- `limit` (number of records)

---

### 5. `/api/algo/circuit-breakers`
**Frontend Page:** ServiceHealth.jsx  
**Method:** GET  
**Required Columns:**
- `name` (string, CB1/CB2/CB3)
- `status` (string, active/triggered/normal)
- `threshold` (string/numeric)
- `current_value` (numeric)
- `triggered_at` (timestamp, nullable)
- `last_check` (timestamp)

---

### 6. `/api/sectors/trends-batch`
**Frontend Page:** Sentiment.jsx  
**Method:** GET  
**Query Param:** `sectors={LIST}` (comma-separated)  
**Required Columns Per Sector:**
- `sector_name` (string)
- `momentum_score` (float)
- `relative_strength` (float, percentile)
- `avg_change_pct` (float)
- `stock_count` (int)

---

### 7. `/api/algo/notifications`
**Frontend Page:** NotificationCenter.jsx  
**Method:** GET  
**Required Columns:**
- `id` (UUID)
- `type` (string: trade, alert, system)
- `title` (string)
- `message` (string)
- `severity` (string: info, warning, error)
- `is_read` (boolean)
- `created_at` (timestamp)
- `data` (JSON, optional context)

---

### 8. `/api/audit/trades`
**Frontend Page:** TradeTracker.jsx  
**Method:** GET  
**Required Columns:**
- `trade_id` (UUID)
- `symbol` (string)
- `side` (string: buy/sell/close)
- `quantity` (numeric)
- `price` (float)
- `executed_at` (timestamp)
- `status` (string: pending/filled/rejected)
- `pnl` (float, nullable)

---

### 9. `/api/algo/performance`
**Frontend Page:** PerformanceMetrics.jsx  
**Method:** GET  
**Required Columns:**
- `total_pnl` (float)
- `pnl_pct` (float, %)
- `win_rate` (float, %)
- `avg_winner` (float)
- `avg_loser` (float)
- `sharpe_ratio` (float)
- `max_drawdown` (float, %)
- `current_drawdown` (float, %)
- `trades_count` (int)
- `period` (string: today/week/month/ytd/all)

---

### 10. `/api/algo/data-status`
**Frontend Page:** ServiceHealth.jsx  
**Method:** GET  
**Required Columns:**
- `source_name` (string: prices, signals, fundamentals, etc.)
- `last_update` (timestamp)
- `record_count` (int)
- `status` (string: ok, stale, error)
- `expected_frequency` (string: daily, real-time)
- `lag_hours` (float, nullable)

---

## Validation Strategy

1. **On Startup:** Each Lambda route handler should validate response shape
2. **On Deploy:** Run schema validation test before pushing
3. **On Request:** Log if frontend receives unexpected column names
4. **Monthly:** Audit 10% of responses to spot column drifts early

## Recent Fixes (2026-05-17)

- ✅ Expanded `/api/scores/stockscores` to include `trend_score`, `grade`, `date`
- ✅ Expanded `/api/stocks/deep-value` to include all 10 required columns
- ✅ Fixed `/api/algo/swing-scores` to return nested components JSON
- ✅ Added `/api/sectors/trends-batch` support for bulk sector queries

## TODO: Validate

- [ ] `/api/research/backtests` - columns match BacktestResults component
- [ ] `/api/algo/patrol` - column output schema
- [ ] `/api/algo/config/:key` - response format for settings pages
- [ ] `/api/economic/indicators` - macro data columns (if used)

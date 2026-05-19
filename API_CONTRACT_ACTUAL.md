# API Contract - Financial Dashboard (ACTUAL Implementation)

**CRITICAL:** This document reflects the ACTUAL API implementation. The old API_CONTRACT.md had incorrect paths - this is the authoritative source.

**Base URL:** Local: `http://localhost:3001/api` | AWS: `https://{api-gateway-url}/api`

**Content-Type:** `application/json`

---

## Core Data Endpoints

### GET `/health`
Health check (no database required).
- **Status Code:** 200
- **Response:** `{ "status": "healthy" }`

### GET `/stocks`
List all stocks with metadata.
- **Query Parameters:**
  - `limit` (optional): Limit results (default: all)
- **Status Code:** 200
- **Response:**
```json
{
  "items": [
    {
      "symbol": "AAPL",
      "company_name": "Apple Inc.",
      "sector": "Technology",
      "industry": "Consumer Electronics",
      "is_sp500": true
    }
  ],
  "total": 10153
}
```

### GET `/prices/history/{symbol}`
Historical prices for a symbol.
- **Query Parameters:**
  - `timeframe`: `daily` | `weekly` | `monthly` (default: `daily`)
  - `limit`: Max rows (default: 252)
  - `days`: Days back (e.g., `days=90`)
- **Status Code:** 200
- **Response:**
```json
{
  "items": [
    {
      "date": "2026-05-18",
      "open": 206.94,
      "high": 208.0,
      "low": 200.52,
      "close": 203.25,
      "volume": 87349208
    }
  ]
}
```

### GET `/signals` or `/signals/stocks`
Trading signals (buy/sell) for stocks.
- **Query Parameters:**
  - `limit`: Max results (default: 50000)
  - `timeframe`: `daily` | `weekly` | `monthly` (default: `daily`)
  - `symbol`: Filter by symbol (optional)
- **Status Code:** 200
- **Response:**
```json
{
  "items": [
    {
      "id": 2473177,
      "symbol": "AGG",
      "signal": "BUY",
      "date": "2026-05-18",
      "signal_triggered_date": "2026-05-18",
      "strength": 0.75,
      "reason": "...",
      "rsi": 96.39,
      "sma_50": 101.55,
      "sma_200": 101.99,
      "ema_12": 108.37,
      "ema_21": 104.86,
      "ema_26": 104.02,
      "atr": 4.97,
      "base_type": null,
      "base_length_days": null,
      "market_stage": "2",
      "trend": "uptrend",
      "grade": "F",
      "swing_score": 0.0,
      "entry_quality_score": 0.0,
      "signal_quality_score": 0.0,
      "risk_reward_ratio": 0.0,
      "volume_surge_pct": 0.0,
      "security_name": "iShares Core U.S. Aggregate Bond ETF",
      "sector": null,
      "industry": null
    }
  ]
}
```

### GET `/signals/etf`
Trading signals for ETFs.
- **Status Code:** 200
- **Response:** Same as `/signals` but filtered to ETFs only.

### GET `/scores`
Stock quality scores.
- **Query Parameters:**
  - `limit`: Max results (default: 50)
- **Status Code:** 200
- **Response:**
```json
{
  "items": [
    {
      "symbol": "MSFT",
      "company_name": "Microsoft Corporation",
      "growth_score": 85,
      "value_score": 60,
      "momentum_score": 92,
      "dividend_score": 30,
      "composite_score": 78,
      "industry": "Software",
      "sector": "Technology"
    }
  ]
}
```

### GET `/scores/stockscores`
Alias for `/scores` (returns same data).

### GET `/sectors`
Sector list and performance.
- **Query Parameters:**
  - `limit`: Max sectors (default: all)
- **Status Code:** 200
- **Response:**
```json
{
  "items": [
    {
      "sector": "Technology",
      "avg_score": 75.5,
      "momentum": 0.85,
      "signal_count": 45
    }
  ]
}
```

### GET `/sectors/performance`
Sector performance metrics.
- **Status Code:** 200

### GET `/industries`
Industry list.
- **Query Parameters:**
  - `limit`: Max industries (default: all)
- **Status Code:** 200

## Market & Economic Data

### GET `/market`
Overall market status and indices.
- **Status Code:** 200
- **Response:**
```json
{
  "spy_price": 450.25,
  "vix": 18.5,
  "market_stage": 2,
  "distribution_days": 3,
  "advance_decline_ratio": 1.2
}
```

### GET `/market/status`
Market health details.

### GET `/market/indices`
Major market indices.

### GET `/market/top-movers`
Top gainers/losers.

### GET `/market/breadth`
Market breadth data.

### GET `/market/distribution-days`
Market distribution day count.

### GET `/market/sentiment`
Market sentiment indicators.

### GET `/market/fear-greed`
Fear & Greed Index.

### GET `/market/naaim`
NAAIM data.

### GET `/market/seasonality`
Seasonal patterns.

### GET `/market/correlation`
Stock correlation matrix.

### GET `/market/cap-distribution`
Market cap distribution.

### GET `/market/technicals`
Market-wide technical indicators.

### GET `/market/latest`
Latest market data snapshot.

### GET `/economic`
Economic indicators summary.
- **Status Code:** 200

### GET `/economic/indicators`
Detailed economic indicators.

### GET `/economic/leading-indicators`
Leading economic indicators (LEI).

### GET `/economic/VIX`
VIX (volatility) data.

### GET `/economic/yield-curve-full`
Full yield curve data.

### GET `/economic/calendar`
Economic calendar.

## Sentiment & Research

### GET `/sentiment/summary`
Sentiment summary across sources.

### GET `/sentiment/data`
Sentiment by symbol or market-wide.
- **Query Parameters:**
  - `symbol` (optional): Filter by symbol
- **Status Code:** 200

### GET `/sentiment/vix`
VIX-based sentiment.

### GET `/sentiment/divergence`
Sentiment/price divergence alerts.

### GET `/sentiment/analyst/insights/{symbol}`
Analyst sentiment for a symbol.

### GET `/sentiment/social/insights/{symbol}`
Social media sentiment for a symbol.

## Trading & Positions

### GET `/trades`
Trade history and summaries.
- **Status Code:** 200
- **Response:**
```json
{
  "items": [
    {
      "symbol": "AAPL",
      "entry_date": "2026-05-10",
      "entry_price": 200.50,
      "exit_date": "2026-05-15",
      "exit_price": 210.25,
      "return_pct": 4.85,
      "win": true
    }
  ]
}
```

### GET `/trades/summary`
Trade summary statistics.

## Algorithmic Trading

### GET `/algo/status`
Orchestrator status and metrics.
- **Status Code:** 200
- **Response:**
```json
{
  "orchestrator_status": "running",
  "last_run": "2026-05-19T15:30:00Z",
  "phases_completed": 5,
  "open_positions": 12,
  "failed_trades": 0,
  "total_pnl": 15250.50
}
```

### GET `/algo/data-status`
Data freshness and completeness.

### GET `/algo/positions`
Current open positions with details.

### GET `/algo/performance`
Performance metrics (returns, Sharpe ratio, etc.).

### GET `/algo/equity-curve`
Equity curve (balance over time).

### GET `/algo/swing-scores`
Latest swing trader scores.

### GET `/algo/swing-scores-history`
Historical swing scores by symbol/date.

### GET `/algo/notifications`
Pending notifications (fills, alerts, etc.).

### GET `/algo/circuit-breakers`
Circuit breaker status.

### GET `/algo/exposure-policy`
Current sector exposure vs limits.

### GET `/algo/sector-rotation`
Sector rotation signals.

### GET `/algo/sector-breadth`
Sector breadth analysis.

### GET `/algo/sector-stage2`
Stocks in sector stage 2.

### GET `/algo/markets`
Market condition summary.

### GET `/algo/rejection-funnel`
Trade rejection reasons and counts.

### GET `/algo/patrol-log`
Data quality patrol log.

### GET `/algo/data-quality`
Data quality metrics.

### GET `/algo/config`
Orchestrator configuration.

### GET `/algo/config/{key}`
Get specific config value.

### POST `/algo/patrol`
Trigger data quality check.

### POST `/algo/pre-trade-impact`
Analyze order impact.

### POST `/algo/evaluate`
Evaluate a trade idea.

### GET `/algo/audit-log`
Audit log of recent actions.

## Administration

### GET `/admin/loader-status`
Data loader health and completeness.
- **Status Code:** 200
- **Response:**
```json
{
  "loaders": [
    {
      "loader": "load_technical_data_daily",
      "status": "active",
      "last_run": "2026-05-19T14:00:00Z",
      "rows_loaded": 4500000,
      "symbols_complete": 6000,
      "symbols_pending": 411
    }
  ]
}
```

### GET `/admin/system-health`
Overall system health.

### GET `/admin/database-stats`
Database statistics and sizes.

### GET `/admin/data-quality`
Data quality audit results.

## Audit & Compliance

### GET `/audit/trail`
Audit trail of all actions.

### GET `/audit/trades`
Trade audit details.

### GET `/audit/config`
Configuration audit history.

### GET `/audit/safeguards`
Risk safeguard status and violations.

## Research & Backtesting

### GET `/research/backtests`
List of backtests.

### GET `/research/backtests/{id}`
Backtest results.

### POST `/research/backtests`
Create new backtest.

---

## Common Query Parameters

Most endpoints support:
- `limit`: Result limit (varies by endpoint)
- `offset`: Pagination offset
- `sort`: Sort field (varies by endpoint)
- `order`: `asc` | `desc`

## Error Responses

All endpoints return error responses in this format:
```json
{
  "statusCode": 404,
  "errorType": "not_found",
  "message": "Symbol not found"
}
```

Common status codes:
- 200: Success
- 400: Bad request
- 404: Not found
- 500: Server error

---

## NOTES

1. **Data Gaps:** Many fields return 0.0 or null because underlying loaders are incomplete (signal_quality_scores, market_health_daily, swing_trader_scores tables have minimal data)

2. **Timeframe Support:** Endpoints with `timeframe` parameter support `daily`, `weekly`, `monthly`

3. **Limits:** Default limits vary by endpoint (typically 50-50000 rows)

4. **Database Tables:** Endpoints query these core tables:
   - `price_daily`, `price_weekly`, `price_monthly` (5.8M+ rows)
   - `buy_sell_daily` (466k rows)
   - `technical_data_daily` (4.5M rows)
   - `trend_template_data` (748k rows)
   - `stock_symbols` (10k+ rows)
   - `stock_scores` (10k rows)
   - Other reference tables (sectors, industries, etc.)

5. **Missing Tables with Data:** The following tables exist but have minimal/no data:
   - `signal_quality_scores` (3 rows)
   - `market_health_daily` (2 rows)
   - `swing_trader_scores` (723 rows)

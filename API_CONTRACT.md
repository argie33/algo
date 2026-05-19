# API Contract - Financial Dashboard

**Base URL:** `{AWS_API_GATEWAY_URL}/{stage}` (e.g., `https://api.example.com/api`)

**Authentication:** JWT token via Cognito (passed in `Authorization: Bearer` header). Validated at API Gateway level before reaching Lambda.

**Content-Type:** `application/json`

---

## Health & Status Endpoints

### GET `/health`
System health check (minimal, no dependencies).
- **Response:** `{ "status": "healthy", "healthy": true, "service": "Financial Dashboard API" }`
- **Status Code:** 200

### GET `/health/detailed`
Detailed health check (database connectivity, table counts).
- **Response:**
  ```json
  {
    "status": "healthy",
    "dbStatus": "connected",
    "tables": {
      "price_daily": 5800000,
      "buy_sell_daily": 100000,
      "positions": 1500
    }
  }
  ```
- **Status Code:** 200 | 503 (if DB unavailable)

### GET `/status`
Overall system status and orchestrator state.
- **Response:**
  ```json
  {
    "orchestrator_status": "running|idle|error",
    "last_run": "2026-05-19T15:30:00Z",
    "phases_completed": 7,
    "open_positions": 45,
    "failed_trades": 0
  }
  ```
- **Status Code:** 200

---

## Price Data Endpoints

### GET `/prices/{symbol}`
Historical daily price data for a symbol.
- **Query Parameters:**
  - `start_date` (optional): YYYY-MM-DD format (default: 1 year ago)
  - `end_date` (optional): YYYY-MM-DD format (default: today)
  - `limit` (optional): Max rows to return (default: 250)
- **Response:**
  ```json
  {
    "symbol": "AAPL",
    "prices": [
      {
        "date": "2026-05-18",
        "open": 180.50,
        "high": 182.30,
        "low": 179.80,
        "close": 181.25,
        "volume": 45000000
      }
    ]
  }
  ```
- **Status Code:** 200 | 404 (symbol not found)

### GET `/prices/{symbol}/latest`
Latest price for a symbol.
- **Response:**
  ```json
  {
    "symbol": "AAPL",
    "date": "2026-05-18",
    "close": 181.25,
    "volume": 45000000
  }
  ```
- **Status Code:** 200 | 404

---

## Signals Endpoints

### GET `/signals/{symbol}`
Buy/sell signals for a symbol (daily/weekly/monthly).
- **Query Parameters:**
  - `timeframe` (optional): `daily` | `weekly` | `monthly` (default: daily)
  - `limit` (optional): Max rows (default: 50)
- **Response:**
  ```json
  {
    "symbol": "AAPL",
    "signals": [
      {
        "date": "2026-05-17",
        "signal_type": "BUY",
        "strength": 75,
        "reason": "RSI oversold + MACD bullish"
      }
    ]
  }
  ```
- **Status Code:** 200 | 404

### GET `/signals`
All recent signals across portfolio.
- **Query Parameters:**
  - `limit` (optional): Max signals (default: 100)
  - `signal_type` (optional): `BUY` | `SELL` | `HOLD`
- **Response:**
  ```json
  {
    "total": 23,
    "signals": [...]
  }
  ```
- **Status Code:** 200

---

## Scores & Rankings Endpoints

### GET `/scores/{symbol}`
Composite quality scores for a symbol.
- **Response:**
  ```json
  {
    "symbol": "AAPL",
    "date": "2026-05-18",
    "growth_score": 85,
    "value_score": 60,
    "momentum_score": 92,
    "dividend_score": 30,
    "composite_score": 78
  }
  ```
- **Status Code:** 200 | 404

### GET `/scores`
Top-ranked symbols by score.
- **Query Parameters:**
  - `limit` (optional): Top N symbols (default: 50)
  - `metric` (optional): `growth` | `value` | `momentum` | `composite`
- **Response:**
  ```json
  {
    "metric": "composite",
    "symbols": [
      { "symbol": "MSFT", "score": 92 },
      { "symbol": "AAPL", "score": 88 }
    ]
  }
  ```
- **Status Code:** 200

### GET `/signal-quality`
Signal quality scores (confidence 0-100).
- **Query Parameters:**
  - `symbol` (required)
  - `date` (optional): Specific date, default latest
- **Response:**
  ```json
  {
    "symbol": "AAPL",
    "date": "2026-05-18",
    "quality_score": 75,
    "components": {
      "signal_confidence": 70,
      "technical_confirmation": 80,
      "trend_alignment": 75
    }
  }
  ```
- **Status Code:** 200 | 404

---

## Trading Endpoints

### GET `/positions`
Open positions.
- **Response:**
  ```json
  {
    "total_positions": 12,
    "total_value": 500000,
    "positions": [
      {
        "symbol": "MSFT",
        "shares": 100,
        "entry_price": 350.25,
        "current_price": 365.50,
        "pnl": 1525,
        "pnl_percent": 4.35
      }
    ]
  }
  ```
- **Status Code:** 200

### POST `/positions/{symbol}/close`
Close a position.
- **Body:** `{ "quantity": 100 }`
- **Response:**
  ```json
  {
    "order_id": "ORDER-123",
    "symbol": "MSFT",
    "quantity": 100,
    "fill_price": 365.50,
    "status": "filled"
  }
  ```
- **Status Code:** 200 | 400 (invalid quantity)

### GET `/trades`
Trade history.
- **Query Parameters:**
  - `limit` (optional): Max trades (default: 100)
  - `symbol` (optional): Filter by symbol
- **Response:**
  ```json
  {
    "total_trades": 342,
    "trades": [
      {
        "order_id": "ORDER-123",
        "symbol": "MSFT",
        "side": "BUY",
        "quantity": 100,
        "fill_price": 350.25,
        "filled_at": "2026-05-18T10:30:00Z",
        "pnl": 1525
      }
    ]
  }
  ```
- **Status Code:** 200

### GET `/trades/reconcile`
Verify that trade reconciliation matches Alpaca.
- **Response:**
  ```json
  {
    "matches": true,
    "local_trades": 342,
    "alpaca_trades": 342,
    "discrepancies": []
  }
  ```
- **Status Code:** 200 | 500 (reconciliation failed)

---

## Market & Sector Endpoints

### GET `/market/health`
Market-wide health metrics (market stage, distribution days, breadth).
- **Response:**
  ```json
  {
    "date": "2026-05-18",
    "market_trend": "uptrend",
    "market_stage": 2,
    "distribution_days": 3,
    "advance_decline_ratio": 1.8,
    "breadth_momentum": 72
  }
  ```
- **Status Code:** 200

### GET `/sectors`
Sector performance and rotation data.
- **Response:**
  ```json
  {
    "sectors": [
      {
        "name": "Technology",
        "score": 85,
        "momentum": "positive",
        "allocated_percent": 35
      }
    ]
  }
  ```
- **Status Code:** 200

### GET `/industries`
Industry-level rankings.
- **Response:**
  ```json
  {
    "industries": [
      {
        "name": "Software",
        "score": 88,
        "count": 25
      }
    ]
  }
  ```
- **Status Code:** 200

---

## Analytics & Performance Endpoints

### GET `/performance`
Portfolio performance metrics.
- **Query Parameters:**
  - `period` (optional): `1d` | `1w` | `1m` | `ytd` | `all` (default: ytd)
- **Response:**
  ```json
  {
    "period": "ytd",
    "total_return": 0.142,
    "annualized_return": 0.18,
    "max_drawdown": 0.08,
    "sharpe_ratio": 1.65,
    "win_rate": 0.58,
    "trades": 342
  }
  ```
- **Status Code:** 200

### GET `/performance/attribution`
Performance attribution by sector/strategy.
- **Response:**
  ```json
  {
    "by_sector": {
      "Technology": 0.085,
      "Healthcare": 0.032,
      "Financials": 0.020
    },
    "by_signal_type": {
      "Momentum": 0.072,
      "MeanReversion": 0.045,
      "TrendFollowing": 0.040
    }
  }
  ```
- **Status Code:** 200

### POST `/backtests`
Backtest a strategy.
- **Body:**
  ```json
  {
    "symbol": "SPY",
    "strategy": "mean_reversion",
    "start_date": "2024-01-01",
    "end_date": "2025-12-31",
    "initial_capital": 100000
  }
  ```
- **Response:**
  ```json
  {
    "backtest_id": "BT-123",
    "status": "running|completed",
    "total_return": 0.42,
    "sharpe_ratio": 1.82
  }
  ```
- **Status Code:** 202 (accepted) | 400 (invalid params)

### GET `/backtests/{backtest_id}`
Retrieve backtest results.
- **Response:**
  ```json
  {
    "backtest_id": "BT-123",
    "status": "completed",
    "results": {
      "total_return": 0.42,
      "trades": 127,
      "max_drawdown": 0.12
    }
  }
  ```
- **Status Code:** 200 | 404

---

## Economic & Sentiment Endpoints

### GET `/economic`
Economic indicators (GDP, inflation, unemployment, etc.).
- **Response:**
  ```json
  {
    "gdp_growth": 0.032,
    "inflation_rate": 0.028,
    "unemployment_rate": 0.039,
    "fed_rate": 0.048,
    "last_updated": "2026-05-15"
  }
  ```
- **Status Code:** 200

### GET `/sentiment`
Market sentiment indicators (VIX, put/call ratios, etc.).
- **Response:**
  ```json
  {
    "vix_level": 18.5,
    "put_call_ratio": 0.72,
    "market_sentiment": "neutral",
    "breadth": 65
  }
  ```
- **Status Code:** 200

---

## Commodities & Macro Endpoints

### GET `/commodities`
Commodity prices (crude, gold, DXY, etc.).
- **Response:**
  ```json
  {
    "commodities": [
      { "name": "Crude Oil", "price": 75.50, "change_percent": 2.1 },
      { "name": "Gold", "price": 2045.25, "change_percent": -0.5 }
    ]
  }
  ```
- **Status Code:** 200

### GET `/macro`
Macroeconomic trends (interest rates, yield curve, credit spreads).
- **Response:**
  ```json
  {
    "fed_rate": 0.048,
    "yield_curve": "normal|inverted|flat",
    "hy_spread": 0.034,
    "ig_spread": 0.008
  }
  ```
- **Status Code:** 200

---

## Audit & Diagnostics Endpoints

### GET `/audit`
Audit log of recent activities (trades, position changes, alerts).
- **Query Parameters:**
  - `limit` (optional): Max entries (default: 100)
  - `entity_type` (optional): `trade` | `position` | `alert`
- **Response:**
  ```json
  {
    "entries": [
      {
        "timestamp": "2026-05-18T10:30:00Z",
        "event_type": "TRADE_FILLED",
        "symbol": "MSFT",
        "details": "BUY 100 @ 350.25"
      }
    ]
  }
  ```
- **Status Code:** 200

### GET `/diagnostics`
System diagnostics (loader status, data freshness, lag detection).
- **Response:**
  ```json
  {
    "last_data_refresh": "2026-05-18T22:00:00Z",
    "loaders_status": {
      "loadpricedaily": "success",
      "loadbuyselldaily": "success",
      "load_technical_data_daily": "success"
    },
    "data_lag_minutes": 0,
    "alerts": []
  }
  ```
- **Status Code:** 200

### GET `/diagnostics/loaders`
Detailed loader status and last-run timestamps.
- **Response:**
  ```json
  {
    "loaders": [
      {
        "name": "loadpricedaily",
        "last_run": "2026-05-18T22:00:00Z",
        "status": "success",
        "records_loaded": 100000,
        "duration_seconds": 15
      }
    ]
  }
  ```
- **Status Code:** 200

---

## Error Responses

All endpoints follow this error format:

```json
{
  "error": "Error message here",
  "error_code": "INVALID_PARAMS",
  "timestamp": "2026-05-18T10:30:00Z"
}
```

**Common Error Codes:**
- `INVALID_PARAMS` — 400: Missing or invalid query/body parameters
- `UNAUTHORIZED` — 401: Missing or invalid JWT token
- `FORBIDDEN` — 403: Insufficient permissions
- `NOT_FOUND` — 404: Resource not found
- `CONFLICT` — 409: Operation conflicts with current state
- `RATE_LIMITED` — 429: Too many requests
- `INTERNAL_ERROR` — 500: Unexpected server error
- `SERVICE_UNAVAILABLE` — 503: Database or external service down

---

## Authentication

All endpoints (except `/health`) require a valid JWT token in the `Authorization` header:

```
Authorization: Bearer eyJhbGc...
```

The token is validated by API Gateway (Cognito JWT authorizer) before reaching the Lambda function.

---

## Rate Limiting

- **Authenticated users:** 1000 requests per minute
- **Burst limit:** 100 requests per 10 seconds
- **Response header:** `X-RateLimit-Remaining: 999`

If rate-limited, the API returns `429 Too Many Requests`.

---

## Versioning

Current API version: `v1`

Future breaking changes will increment the version (e.g., `/v2/prices/{symbol}`).

---

## SLA & Uptime

- **API Availability:** 99.9% (monthly)
- **Response Time (p95):** < 500 ms
- **Data Freshness:** Updated daily by 10 PM ET

See `/health/detailed` for real-time status.

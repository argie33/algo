# API Contract - Stock Analytics Platform

**Base URL:** `{API_BASE_URL}` (e.g., `https://api.example.com/api` or `http://localhost:3000/api` in dev)

**Authentication:** JWT token via Cognito (passed in `Authorization: Bearer` header).

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

---

## Price Data Endpoints

### GET `/api/prices/history/{symbol}`
Historical daily/weekly/monthly price data for a symbol.
- **Query Parameters:**
  - `timeframe` (optional): `daily` | `weekly` | `monthly` (default: daily)
  - `limit` (optional): Max rows to return (default: 252, max: 2000)
  - `days` (optional): Last N days of data
- **Response:**
  ```json
  [
    {
      "date": "2026-05-18",
      "open": 180.50,
      "high": 182.30,
      "low": 179.80,
      "close": 181.25,
      "volume": 45000000
    }
  ]
  ```
- **Status Code:** 200 | 404 (symbol not found)

---

## Stock Data Endpoints

### GET `/api/stocks`
List all stocks with optional filtering and pagination.
- **Query Parameters:**
  - `limit` (optional): Rows per page (default: 500, max: 50000)
  - `offset` (optional): Pagination offset (default: 0)
  - `search` (optional): Search by symbol or company name
  - `sector` (optional): Filter by sector
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
    "total": 5000
  }
  ```
- **Status Code:** 200

### GET `/api/stocks/{symbol}`
Get detailed information for a specific stock.
- **Response:**
  ```json
  {
    "symbol": "AAPL",
    "company_name": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "website": "https://apple.com",
    "employees": 161000,
    "exchange": "NASDAQ"
  }
  ```
- **Status Code:** 200 | 404

### GET `/api/stocks/deep-value`
Get deep value stocks (screened for value investors).
- **Query Parameters:**
  - `limit` (optional): Max results (default: 600, max: 1000)
- **Response:**
  ```json
  [
    {
      "symbol": "IBM",
      "company_name": "International Business Machines",
      "sector": "Technology",
      "industry": "Software & IT Services",
      "market_cap": 250000000000
    }
  ]
  ```
- **Status Code:** 200

---

## Signal Data Endpoints

### GET `/api/signals`
Get all recent trading signals (BUY/SELL) with technical enrichment.
- **Query Parameters:**
  - `limit` (optional): Max signals (default: 50000, max: 50000)
  - `timeframe` (optional): `daily` | `weekly` | `monthly` (default: daily)
  - `symbol` (optional): Filter by specific symbol
- **Response:**
  ```json
  {
    "items": [
      {
        "id": 12345,
        "symbol": "AAPL",
        "signal": "BUY",
        "date": "2026-05-18",
        "signal_triggered_date": "2026-05-18",
        "strength": 75,
        "reason": "RSI oversold + MACD bullish",
        "close": 181.25,
        "rsi": 28,
        "atr": 2.5,
        "sma_50": 175.5,
        "sma_200": 160.0,
        "ema_12": 178.0,
        "ema_21": 176.5,
        "ema_26": 175.0,
        "market_stage": "Stage 2",
        "trend": "Uptrend",
        "company_name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "swing_score": 82,
        "grade": "A",
        "base_type": "Accumulation",
        "base_length_days": 45,
        "buylevel": 178.50,
        "stoplevel": 175.00,
        "risk_reward_ratio": 2.5,
        "volume_surge_pct": 15.5,
        "entry_quality_score": 85,
        "signal_quality_score": 78,
        "buy_zone_start": 178.00,
        "buy_zone_end": 180.00,
        "pivot_price": 179.25,
        "initial_stop": 175.00,
        "trailing_stop": 177.50,
        "position_size_recommendation": "1.0",
        "profit_target_8pct": 195.60,
        "profit_target_20pct": 217.50,
        "profit_target_25pct": 226.56,
        "exit_trigger_1_price": 176.50,
        "exit_trigger_2_price": 174.00,
        "sell_level": 180.00,
        "rs_rating": 92,
        "avg_volume_50d": 52000000
      }
    ]
  }
  ```
- **Status Code:** 200

### GET `/api/signals/etf`
Get ETF trading signals (SPY, QQQ, IWM, DIA, EEM, EFA).
- **Query Parameters:**
  - `limit` (optional): Max signals (default: 50000)
- **Response:** Array of signal objects (similar structure to `/api/signals`)
- **Status Code:** 200

---

## Scores & Rankings Endpoints

### GET `/api/scores`
Get stock scores with multi-factor ranking.
- **Query Parameters:**
  - `limit` (optional): Max results (default: 50000, max: 50000)
  - `offset` (optional): Pagination offset (default: 0)
  - `sortBy` (optional): Column to sort by (default: `composite_score`)
    - Valid: `composite_score`, `momentum_score`, `quality_score`, `value_score`, `growth_score`, `positioning_score`, `stability_score`, `symbol`
  - `sortOrder` (optional): `asc` | `desc` (default: `desc`)
  - `sp500Only` (optional): `true` | `false` (default: `false`)
  - `symbol` (optional): Filter by specific symbol
- **Response:**
  ```json
  [
    {
      "symbol": "MSFT",
      "company_name": "Microsoft Corporation",
      "sector": "Technology",
      "industry": "Software & IT Services",
      "composite_score": 92,
      "momentum_score": 88,
      "quality_score": 85,
      "value_score": 72,
      "growth_score": 90,
      "positioning_score": 80,
      "stability_score": 75,
      "current_price": 450.25,
      "price": 450.25,
      "change_percent": 2.5,
      "market_cap": 3000000000000,
      "trailing_pe": 32.5,
      "price_to_book": 12.5,
      "roe_pct": 42.5,
      "debt_to_equity": 0.25,
      "dividend_yield": 0.85,
      "revenue_growth_yoy_pct": 8.5,
      "eps_growth_yoy_pct": 12.0
    }
  ]
  ```
- **Status Code:** 200

---

## Sector & Industry Endpoints

### GET `/api/sectors`
Get sector performance and rankings with pagination.
- **Query Parameters:**
  - `limit` (optional): Rows per page (default: 50000, max: 50000)
  - `page` (optional): Page number (default: 1)
- **Response:**
  ```json
  {
    "data": [
      {
        "sector_name": "Technology",
        "current_rank": 1,
        "stock_count": 156,
        "composite_score": 82,
        "momentum_score": 78,
        "value_score": 65,
        "quality_score": 80,
        "growth_score": 85,
        "stability_score": 72,
        "current_momentum": "Strong",
        "current_trend": "Uptrend",
        "pe": {
          "trailing": 28.5,
          "forward": 24.0,
          "percentile": 65.0
        }
      }
    ],
    "total": 11,
    "page": 1,
    "limit": 50000
  }
  ```
- **Status Code:** 200

### GET `/api/sectors/{sector_name}`
Get performance data for a specific sector.
- **Query Parameters:**
  - `days` (optional): Last N days (default: 90, max: 365)
- **Response:** Array of performance records by date
- **Status Code:** 200 | 404

### GET `/api/sectors/{sector_name}/trend`
Get sector trend data with moving averages.
- **Query Parameters:**
  - `days` (optional): Last N days (default: 90, max: 365)
- **Response:**
  ```json
  {
    "trendData": [
      {
        "date": "2026-05-18",
        "avgPrice": 1250.50,
        "dailyStrengthScore": 2.5,
        "rank": 65.0,
        "momentumScore": 5.2,
        "momentum": "momentum",
        "ma_10": 1245.25,
        "ma_20": 1240.75
      }
    ]
  }
  ```
- **Status Code:** 200

### GET `/api/sectors/trends-batch`
Get trends for multiple sectors at once.
- **Query Parameters:**
  - `sectors` (required): Comma-separated sector names
  - `days` (optional): Last N days (default: 90, max: 365)
- **Response:**
  ```json
  {
    "data": {
      "Technology": [...],
      "Healthcare": [...]
    }
  }
  ```
- **Status Code:** 200

### GET `/api/industries`
Get all industries with stock counts.
- **Response:**
  ```json
  [
    {
      "industry_name": "Software & IT Services",
      "sector_name": "Technology",
      "stock_count": 145,
      "avg_composite_score": 78,
      "avg_momentum_score": 75
    }
  ]
  ```
- **Status Code:** 200

---

## Market Data Endpoints

### GET `/api/market`
Get latest market status summary.
- **Response:** Market health snapshot (see `/api/market/status`)
- **Status Code:** 200

### GET `/api/market/status`
Get current market health and technicals.
- **Response:**
  ```json
  {
    "date": "2026-05-18",
    "market_trend": "Uptrend",
    "market_stage": "Stage 2",
    "advance_decline_ratio": 1.5,
    "new_highs_count": 250,
    "new_lows_count": 45,
    "vix_level": 18.5,
    "put_call_ratio": 0.65,
    "distribution_days_4w": 3,
    "up_volume_percent": 55.0,
    "breadth_momentum_10d": 12.5
  }
  ```
- **Status Code:** 200

### GET `/api/market/technicals`
Get market technical indicators (same as `/api/market/status`).
- **Status Code:** 200

### GET `/api/market/indices`
Get major market indices data (SPY, QQQ, IWM, DIA).
- **Response:**
  ```json
  {
    "indices": [
      {
        "symbol": "^GSPC",
        "date": "2026-05-18",
        "open": 5100.0,
        "high": 5120.5,
        "low": 5090.0,
        "close": 5115.25,
        "volume": 1500000000
      }
    ],
    "history": {
      "^GSPC": [
        {"date": "2026-05-18", "close": 5115.25},
        {"date": "2026-05-17", "close": 5110.00}
      ]
    }
  }
  ```
- **Status Code:** 200

### GET `/api/market/breadth`
Get market breadth data (advances vs declines).
- **Response:**
  ```json
  [
    {
      "date": "2026-05-18",
      "total": 5000,
      "advances": 3200
    }
  ]
  ```
- **Status Code:** 200

### GET `/api/market/top-movers`
Get top 20 daily movers.
- **Response:**
  ```json
  [
    {
      "symbol": "TSLA",
      "security_name": "Tesla Inc.",
      "pct_change": 5.25
    }
  ]
  ```
- **Status Code:** 200

### GET `/api/market/distribution-days`
Get distribution days count.
- **Response:** Array of distribution day records
- **Status Code:** 200

### GET `/api/market/seasonality`
Get market seasonality data (monthly and day-of-week patterns).
- **Response:**
  ```json
  {
    "monthly": [
      {
        "month": 1,
        "month_name": "January",
        "avg_return": 1.5,
        "best_return": 5.0,
        "worst_return": -4.5,
        "winning_years": 45,
        "losing_years": 20,
        "years_counted": 65
      }
    ],
    "day_of_week": [
      {
        "day": "Monday",
        "day_num": 1,
        "avg_return": -0.1,
        "win_rate": 48.0,
        "days_counted": 1300
      }
    ]
  }
  ```
- **Status Code:** 200

### GET `/api/market/sentiment`
Get market fear/greed sentiment over time.
- **Query Parameters:**
  - `range` or `days` (optional): Number of days (default: 30)
- **Response:**
  ```json
  [
    {
      "date": "2026-05-18",
      "fear_greed_value": 65,
      "fear_greed_label": "Greed"
    }
  ]
  ```
- **Status Code:** 200

### GET `/api/market/fear-greed`
Get fear/greed index history.
- **Query Parameters:**
  - `range` or `days` (optional): Number of days (default: 30)
- **Response:** Array of fear/greed records
- **Status Code:** 200

### GET `/api/market/naaim`
Get NAAIM (market sentiment) data.
- **Response:**
  ```json
  {
    "current": 65.5,
    "history": [
      {"date": "2026-05-18", "naaim_number_mean": 65.5}
    ]
  }
  ```
- **Status Code:** 200

### GET `/api/market/latest`
Get combined latest market data (status, sentiment, recent prices).
- **Response:**
  ```json
  {
    "market": {...},
    "sentiment": {...},
    "prices": [...]
  }
  ```
- **Status Code:** 200

---

## Economic Data Endpoints

### GET `/api/economic`
Get leading economic indicators.
- **Response:**
  ```json
  {
    "indicators": [
      {
        "name": "10-Year Yield",
        "value": 4.25,
        "date": "2026-05-18",
        "direction": "up"
      }
    ]
  }
  ```
- **Status Code:** 200

### GET `/api/economic/indicators`
Get economic indicators (same as `/api/economic`).
- **Status Code:** 200

### GET `/api/economic/leading-indicators`
Get leading economic indicators with historical data.
- **Status Code:** 200

### GET `/api/economic/vix`
Get VIX (volatility) historical data.
- **Response:**
  ```json
  [
    {
      "date": "2026-05-18",
      "vix": 18.5
    }
  ]
  ```
- **Status Code:** 200

### GET `/api/economic/yield-curve-full`
Get yield curve data (2Y, 5Y, 10Y, 30Y yields).
- **Response:**
  ```json
  {
    "yield_curve": [
      {"maturity": "2Y", "yield": 4.50},
      {"maturity": "10Y", "yield": 4.25},
      {"maturity": "30Y", "yield": 4.30}
    ]
  }
  ```
- **Status Code:** 200

### GET `/api/economic/calendar`
Get economic calendar events.
- **Response:**
  ```json
  [
    {
      "date": "2026-05-20",
      "event_name": "CPI Release",
      "country": "USA",
      "importance": "High",
      "category": "Inflation",
      "event_time": "08:30",
      "forecast_value": 3.2,
      "actual_value": 3.1,
      "previous_value": 3.3
    }
  ]
  ```
- **Status Code:** 200

---

## Algo & Trading Endpoints

### GET `/api/algo/status`
Get algo orchestrator status.
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

### GET `/api/algo/trades`
Get recent algo trades.
- **Query Parameters:**
  - `limit` (optional): Max results (default: 50000, max: 50000)
- **Response:**
  ```json
  [
    {
      "id": 12345,
      "symbol": "AAPL",
      "signal_type": "BUY",
      "entry_price": 180.50,
      "entry_date": "2026-05-18",
      "shares": 100,
      "status": "open|closed"
    }
  ]
  ```
- **Status Code:** 200

### GET `/api/algo/positions`
Get current open positions.
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
        "current_price": 375.50,
        "current_value": 37550,
        "unrealized_pnl": 2525,
        "unrealized_pnl_pct": 7.2
      }
    ]
  }
  ```
- **Status Code:** 200

### GET `/api/algo/performance`
Get algo performance metrics.
- **Status Code:** 200

### POST `/api/algo/patrol`
Manually trigger patrol (market watch).
- **Response:** `{ "status": "triggered", "message": "Patrol triggered" }`
- **Status Code:** 200

### POST `/api/algo/pre-trade-impact`
Analyze pre-trade impact (slippage, cost analysis).
- **Body:**
  ```json
  {
    "symbol": "AAPL",
    "shares": 100,
    "current_price": 180.50
  }
  ```
- **Response:** Impact analysis data
- **Status Code:** 200

### PATCH `/api/algo/notifications/{id}/read`
Mark notification as read.
- **Status Code:** 200

### DELETE `/api/algo/notifications/{id}`
Delete notification.
- **Status Code:** 200

---

## Audit & Admin Endpoints

### GET `/api/audit/changes`
Get audit log of data changes.
- **Status Code:** 200

### GET `/api/admin/health`
Admin health check endpoint.
- **Status Code:** 200

---

## Response Format Standards

### Success Response (HTTP 200)
For endpoints returning lists:
```json
[
  { "field": "value" }
]
```

For endpoints returning single objects:
```json
{
  "field": "value"
}
```

For endpoints returning paginated data:
```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "limit": 50
}
```

### Error Response
```json
{
  "statusCode": 400,
  "errorType": "bad_request",
  "message": "Error description"
}
```

---

## Rate Limiting & Pagination

- **Pagination:** Use `limit` and `offset` (or `page` for sectors)
- **Rate Limiting:** No explicit rate limits (configurable at API Gateway)
- **Default Page Size:** Varies by endpoint (50-50000)
- **Max Page Size:** 50000 for most endpoints

---

## Notes

1. All datetime values are in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
2. Numeric values are returned as numbers (not strings)
3. Null/missing data is omitted or represented as `null`
4. All responses are UTF-8 encoded JSON
5. Response times should be < 1s for most endpoints
6. Large datasets (prices, signals) can take 2-5s due to database queries

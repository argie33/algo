# API Reference

All endpoints live in `webapp/lambda/index.js`. Base URL: `/api`

## Response Format

### Success (Single Object)
```json
{
  "success": true,
  "data": { /* object */ },
  "timestamp": "2026-05-04T12:00:00.000Z"
}
```

### Success (Paginated List)
```json
{
  "success": true,
  "items": [ /* array */ ],
  "pagination": {
    "limit": 50,
    "offset": 0,
    "total": 4969,
    "page": 1,
    "totalPages": 100,
    "hasNext": true,
    "hasPrev": false
  },
  "timestamp": "2026-05-04T12:00:00.000Z"
}
```

### Error
```json
{
  "success": false,
  "error": "Descriptive error message",
  "timestamp": "2026-05-04T12:00:00.000Z"
}
```

---

## Core Endpoints

### Stocks

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/stocks` | GET | List all stocks (paginated) |
| `/api/stocks/:symbol` | GET | Get stock details |
| `/api/stocks/search?q=apple` | GET | Search stocks by name |

### Price Data

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/price/history/:symbol?timeframe=daily&limit=250` | GET | Price history (daily/weekly/monthly) |
| `/api/price/latest/:symbol` | GET | Latest price for a stock |

### Earnings & Financials

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/earnings/info?symbol=AAPL` | GET | Earnings estimates |
| `/api/financials/:symbol/balance-sheet?period=annual` | GET | Balance sheet |
| `/api/financials/:symbol/income-statement?period=annual` | GET | Income statement |
| `/api/financials/:symbol/cash-flow?period=annual` | GET | Cash flow |

### Market Data

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/market/overview` | GET | Market summary |
| `/api/sectors/sectors?page=1&limit=20` | GET | Sector rankings |

### Trading Signals

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/signals/buy-sell/:symbol` | GET | Buy/sell signals |
| `/api/technical/:symbol` | GET | Technical indicators |

### Portfolio & Trading (Authenticated)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/portfolio/metrics` | GET | Portfolio performance |
| `/api/trades/history` | GET | Trade history |
| `/api/trades/:id` | GET | Trade details |

### Algo (Authenticated)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/algo/status` | GET | Algo system status |
| `/api/algo/positions` | GET | Active positions |
| `/api/algo/trades` | GET | Trade history with reasoning |
| `/api/algo/config` | GET | Current configuration |
| `/api/algo/audit-log` | GET | Decision audit log |
| `/api/algo/run` | POST | Trigger algo execution |

### Health & Status

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | API health check |
| `/api/status` | GET | Quick status |
| `/api/diagnostics` | GET | Full system diagnostics |

---

## Critical Database Tables

Use these exact names in queries (not synonyms):

```
price_daily          (daily OHLCV data)
price_weekly         (weekly OHLCV data)
price_monthly        (monthly OHLCV data)
technical_data_daily (technical indicators)
buy_sell_daily       (Pine Script signals)
buy_sell_weekly
buy_sell_monthly
earnings_estimates   (earnings guidance)
earnings_history     (historical earnings)
earnings_revisions   (analyst revisions)
balance_sheet_annual
balance_sheet_quarterly
income_statement_annual
income_statement_quarterly
cash_flow_annual
cash_flow_quarterly
algo_trades          (executed trades)
algo_positions       (open positions)
algo_config          (algo configuration)
algo_audit_log       (decision log)
market_exposure_daily (market health)
sector_rotation_signal
swing_trader_scores
```

---

## Authentication

Some endpoints require JWT authentication (for portfolio, algo endpoints):

```bash
# Send JWT in Authorization header
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" http://localhost:3001/api/portfolio/metrics
```

JWT is created via login endpoint (not documented here — see webapp/lambda/routes/auth.js).

---

## Pagination

For list endpoints, use query parameters:

```bash
# Get page 2, 100 items per page
GET /api/stocks?page=2&limit=100

# Or use offset/limit
GET /api/stocks?offset=100&limit=100
```

---

## Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (invalid params) |
| 401 | Unauthorized (missing JWT) |
| 404 | Not found |
| 500 | Server error |

---

## Examples

### Get stock price history
```bash
curl "http://localhost:3001/api/price/history/AAPL?timeframe=daily&limit=250"
```

### Get buy/sell signals
```bash
curl "http://localhost:3001/api/signals/buy-sell/AAPL"
```

### Get market overview
```bash
curl "http://localhost:3001/api/market/overview"
```

### Get sector rankings
```bash
curl "http://localhost:3001/api/sectors/sectors?page=1&limit=50"
```

---

## See Also

- `API_REFERENCE.md` (this file) — All endpoints
- `LOCAL_SETUP.md` — Local development setup
- `AWS_DEPLOYMENT.md` — Production deployment
- `TROUBLESHOOTING.md` — Common issues

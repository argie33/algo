# MCP Server Tools Reference

Quick reference for all available tools in the Stocks Algo MCP server.

## Tool Categories

### 📈 Stock Tools (3 tools)

#### search-stocks
Search for stocks by symbol or company name.

```
Input:
  query (required): string - Stock symbol or company name
  limit (optional): number - Max results (default: 20)
  type (optional): string - Filter by type (stock, etf, etc.)

Example:
  { query: "Apple", limit: 10 }

Returns:
  Array of matching stocks with basic info
```

#### get-stock
Get detailed information about a specific stock.

```
Input:
  symbol (required): string - Stock ticker (e.g., AAPL)
  include (optional): string - Additional data (profile, quotes, etc.)

Example:
  { symbol: "AAPL" }

Returns:
  Complete stock profile and current data
```

#### compare-stocks
Compare multiple stocks side by side.

```
Input:
  symbols (required): string[] - Array of ticker symbols

Example:
  { symbols: ["AAPL", "MSFT", "GOOGL"] }

Returns:
  Side-by-side comparison of stocks
```

---

### ⭐ Scoring Tools (2 tools)

#### get-stock-scores
Get composite scores for one or more stocks.

```
Input:
  symbols (required): string[] - Array of stock symbols
  factors (optional): string[] - Specific factors
    (quality, momentum, value, growth, positioning, sentiment, stability)

Example:
  { symbols: ["AAPL", "MSFT"], factors: ["momentum", "value"] }

Returns:
  Composite scores (0-100) for each stock by factor
```

#### top-stocks
Get top-ranked stocks by a specific scoring factor.

```
Input:
  factor (required): string - Factor name
    (quality, momentum, value, growth, positioning, sentiment, stability)
  limit (optional): number - Number of results (default: 20)
  sector (optional): string - Filter by sector

Example:
  { factor: "momentum", limit: 20, sector: "Technology" }

Returns:
  Top stocks ranked by the specified factor
```

---

### 📊 Technical Analysis Tools (2 tools)

#### get-technical-indicators
Get technical indicators for a stock.

```
Input:
  symbol (required): string - Stock ticker
  indicators (optional): string[] - Specific indicators
    (RSI, MACD, Bollinger Bands, Stochastic, etc.)
  period (optional): string - Time period (daily, weekly, monthly)

Example:
  { symbol: "AAPL", indicators: ["RSI", "MACD"], period: "daily" }

Returns:
  Technical indicator values and signals
```

#### analyze-technical
Get technical analysis summary.

```
Input:
  symbol (required): string - Stock ticker

Example:
  { symbol: "AAPL" }

Returns:
  Summary of technical analysis with recommendations
```

---

### 💰 Financial Data Tools (2 tools)

#### get-financial-statements
Get financial statements for a stock.

```
Input:
  symbol (required): string - Stock ticker
  period (optional): string - quarterly or annual (default: quarterly)

Example:
  { symbol: "AAPL", period: "quarterly" }

Returns:
  Income statement, balance sheet, cash flow statement
```

#### get-financial-metrics
Get financial metrics and ratios.

```
Input:
  symbol (required): string - Stock ticker

Example:
  { symbol: "AAPL" }

Returns:
  PE ratio, PB ratio, ROE, ROA, debt ratios, etc.
```

---

### 💼 Portfolio Tools (3 tools)

#### get-portfolio
Get portfolio overview.

```
Input:
  (none)

Example:
  {}

Returns:
  Portfolio summary, total value, allocation
```

#### get-holdings
Get detailed portfolio holdings.

```
Input:
  (none)

Example:
  {}

Returns:
  List of all holdings with shares, cost, current value
```

#### get-portfolio-performance
Get portfolio performance metrics.

```
Input:
  (none)

Example:
  {}

Returns:
  Returns, Sharpe ratio, max drawdown, win rate, etc.
```

---

### 🌍 Market Data Tools (2 tools)

#### get-market-overview
Get market overview with indices.

```
Input:
  (none)

Example:
  {}

Returns:
  SPY, QQQ, DIA, VIX, bond yields, market sentiment
```

#### get-market-breadth
Get market breadth indicators.

```
Input:
  (none)

Example:
  {}

Returns:
  Advance/decline ratio, breadth indicators, market health
```

---

### 🏢 Sector Tools (2 tools)

#### get-sector-data
Get sector analysis and performance.

```
Input:
  sector (optional): string - Specific sector name
    (Technology, Healthcare, Finance, Energy, etc.)

Example:
  { sector: "Technology" }

Returns:
  Sector performance, top stocks, metrics
```

#### get-sector-rotation
Get sector rotation analysis.

```
Input:
  (none)

Example:
  {}

Returns:
  Sector rotation trends and recommendations
```

---

### 📡 Signals Tools (1 tool)

#### get-signals
Get trading signals from the system.

```
Input:
  symbol (optional): string - Filter for specific stock
  type (optional): string - Signal type (buy, sell, hold)
  limit (optional): number - Max signals (default: 20)

Example:
  { symbol: "AAPL", type: "buy", limit: 20 }

Returns:
  List of trading signals with scores and reasoning
```

---

### 📈 Earnings Tools (2 tools)

#### get-earnings-calendar
Get earnings calendar.

```
Input:
  days (optional): number - Days ahead to look (default: 30)
  symbols (optional): string[] - Filter for specific symbols

Example:
  { days: 30, symbols: ["AAPL", "MSFT"] }

Returns:
  Upcoming earnings with estimates and dates
```

#### get-earnings-data
Get earnings data for a specific stock.

```
Input:
  symbol (required): string - Stock ticker

Example:
  { symbol: "AAPL" }

Returns:
  Historical earnings, estimates, surprises, revisions
```

---

### 🔧 Advanced Tool (1 tool)

#### call-api
Make direct API calls to any endpoint (advanced).

```
Input:
  endpoint (required): string - API path (e.g., /api/stocks/AAPL)
  method (optional): string - HTTP method (GET, POST, PUT, DELETE)
  params (optional): object - Query parameters
  body (optional): object - Request body for POST/PUT

Example:
  {
    endpoint: "/api/stocks/AAPL/price",
    method: "GET",
    params: { include: "quote,history" }
  }

Returns:
  Raw API response
```

---

## Common Queries

### Find investment opportunities
1. `top-stocks` with factor: "momentum" + "value"
2. `get-stock-scores` for top picks
3. `get-technical-indicators` to confirm entry
4. `get-financial-metrics` to validate quality

### Analyze a specific stock
1. `get-stock` for overview
2. `get-stock-scores` for ranking
3. `get-technical-indicators` for trend
4. `get-financial-statements` for fundamentals
5. `get-signals` for recent signals

### Portfolio review
1. `get-portfolio` for overview
2. `get-holdings` for details
3. `get-portfolio-performance` for metrics
4. Compare holdings with `compare-stocks`

### Market analysis
1. `get-market-overview` for indices
2. `get-market-breadth` for health
3. `get-sector-rotation` for trends
4. `top-stocks` by factor for leaders

### Earnings watch
1. `get-earnings-calendar` for upcoming
2. `get-earnings-data` for specific stock
3. `search-stocks` for related tickers

---

## Tool Input Specifications

### Required vs Optional

| Tool | Required | Optional |
|------|----------|----------|
| search-stocks | query | limit, type |
| get-stock | symbol | include |
| compare-stocks | symbols | - |
| get-stock-scores | symbols | factors |
| top-stocks | factor | limit, sector |
| get-technical-indicators | symbol | indicators, period |
| analyze-technical | symbol | - |
| get-financial-statements | symbol | period |
| get-financial-metrics | symbol | - |
| get-portfolio | - | - |
| get-holdings | - | - |
| get-portfolio-performance | - | - |
| get-market-overview | - | - |
| get-market-breadth | - | - |
| get-sector-data | - | sector |
| get-sector-rotation | - | - |
| get-signals | - | symbol, type, limit |
| get-earnings-calendar | - | days, symbols |
| get-earnings-data | symbol | - |
| call-api | endpoint | method, params, body |

---

## Response Format

All tools return responses in this format:

```json
{
  "content": [
    {
      "type": "text",
      "text": "JSON response from API"
    }
  ]
}
```

For errors:

```json
{
  "content": [
    {
      "type": "text",
      "text": "Error message describing what went wrong"
    }
  ],
  "isError": true
}
```

---

## HTTP Methods

- **GET** (default): Fetch data (search, get, analyze)
- **POST**: Submit data (compare, batch operations)
- **PUT**: Update data (modify, adjust)
- **DELETE**: Remove data (delete alerts, etc.)

---

## Error Handling

Common errors and solutions:

| Error | Cause | Solution |
|-------|-------|----------|
| "401 Unauthorized" | Invalid auth token | Check `DEV_AUTH_TOKEN` in `.env` |
| "404 Not Found" | Invalid endpoint | Verify endpoint path is correct |
| "Timeout" | API too slow | Increase timeout in config, check backend performance |
| "API Error" | Server error | Check backend logs, verify data exists |

---

## Rate Limits

The MCP server respects backend API rate limits:
- No rate limiting in development
- Production: Check with API owner
- Recommended: Implement caching for repeated queries

---

## Best Practices

1. **Use specific tools** rather than generic `call-api`
2. **Combine tools** for comprehensive analysis
3. **Cache results** for frequently accessed data
4. **Check errors** and handle gracefully
5. **Use optional params** to filter and reduce data
6. **Test with small queries** before large operations
7. **Monitor performance** and adjust as needed

---

## Need More Info?

- Full MCP Server docs: `/home/stocks/algo/mcp-server/README.md`
- Setup guide: `/home/stocks/algo/SETUP_MCP_SERVER.md`
- Backend API routes: `/home/stocks/algo/webapp/lambda/routes/`
- Frontend API client: `/home/stocks/algo/webapp/frontend/src/services/api.js`

# Stocks Algo MCP Server

A Model Context Protocol (MCP) server that provides Claude Code access to all APIs in the Stocks Algo financial platform.

## Overview

This MCP server exposes comprehensive tools for interacting with the Stocks Algo platform's 757+ API endpoints, enabling Claude Code to:

- Search and analyze stocks
- Get composite stock scores
- Perform technical analysis
- Access financial data
- Manage portfolios
- View market data
- Analyze sectors
- Get trading signals
- And much more...

## Features

### Supported API Categories

- **Stocks**: Search, quotes, profiles, comparisons
- **Scoring**: Composite scores by factor (quality, momentum, value, growth, positioning, sentiment, stability)
- **Technical Analysis**: Indicators, charting, analysis summaries
- **Financial Data**: Statements, metrics, ratios
- **Portfolio Management**: Holdings, performance, allocation
- **Market Data**: Indices, breadth, overview
- **Sectors**: Sector data, rotation analysis
- **Trading Signals**: Buy/sell signals, recommendations
- **Earnings**: Calendar, estimates, results
- **And more...** (45+ API route categories)

### Available Tools

#### Stock Tools
- `search-stocks` - Search for stocks by symbol or name
- `get-stock` - Get detailed stock information
- `compare-stocks` - Compare multiple stocks

#### Scoring Tools
- `get-stock-scores` - Get composite scores for stocks
- `top-stocks` - Get top stocks by factor

#### Technical Analysis Tools
- `get-technical-indicators` - Get technical indicators (RSI, MACD, Bollinger Bands)
- `analyze-technical` - Get technical analysis summary

#### Financial Data Tools
- `get-financial-statements` - Get financial statements
- `get-financial-metrics` - Get financial metrics (PE, PB, ROE, etc.)

#### Portfolio Tools
- `get-portfolio` - Get portfolio overview
- `get-holdings` - Get portfolio holdings
- `get-portfolio-performance` - Get performance metrics

#### Market Data Tools
- `get-market-overview` - Get market indices and data
- `get-market-breadth` - Get market breadth indicators

#### Sector Tools
- `get-sector-data` - Get sector analysis
- `get-sector-rotation` - Get sector rotation analysis

#### Signals Tools
- `get-signals` - Get trading signals

#### Earnings Tools
- `get-earnings-calendar` - Get earnings calendar
- `get-earnings-data` - Get earnings data for stocks

#### Advanced Tools
- `call-api` - Make direct API calls to any endpoint

## Installation

### 1. Install Dependencies

```bash
cd /home/stocks/algo/mcp-server
npm install
```

### 2. Configure Environment

The MCP server uses environment variables from `.env`:

```bash
# Development (default)
NODE_ENV=development
API_URL_DEV=http://localhost:3001
DEV_AUTH_TOKEN=dev-bypass-token

# Production (optional)
API_URL_PROD=https://your-prod-domain.com
API_AUTH_TOKEN=your-prod-token
```

### 3. Enable in Claude Code

The MCP server is configured in `/home/stocks/algo/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "stocks-algo": {
      "command": "node",
      "args": ["/home/stocks/algo/mcp-server/index.js"],
      "env": {
        "NODE_ENV": "development",
        "API_URL_DEV": "http://localhost:3001",
        "DEV_AUTH_TOKEN": "dev-bypass-token"
      }
    }
  }
}
```

## Usage in Claude Code

Once installed and configured, you can use the MCP server tools in Claude Code:

### Examples

**Search for a stock:**
```
Use the `search-stocks` tool with query: "Apple"
```

**Get a stock's composite score:**
```
Use the `get-stock-scores` tool with symbols: ["AAPL"]
```

**Analyze technical indicators:**
```
Use the `get-technical-indicators` tool with symbol: "AAPL"
```

**Get financial metrics:**
```
Use the `get-financial-metrics` tool with symbol: "AAPL"
```

**Find top performers by momentum:**
```
Use the `top-stocks` tool with factor: "momentum", limit: 20
```

**Get portfolio performance:**
```
Use the `get-portfolio-performance` tool
```

**Get market overview:**
```
Use the `get-market-overview` tool
```

**Make a direct API call:**
```
Use the `call-api` tool with endpoint: "/api/stocks/AAPL/price"
```

## Architecture

### Server Components

1. **index.js** - Main MCP server entry point
   - Initializes MCP server
   - Registers all tools
   - Handles tool requests
   - Manages API communication

2. **config.js** - Configuration management
   - API endpoint configuration
   - Tool definitions
   - Environment settings
   - API category mappings

3. **package.json** - Dependencies
   - @modelcontextprotocol/sdk - MCP protocol
   - axios - HTTP client
   - dotenv - Environment configuration

### Authentication

The server automatically adds authentication headers to all API requests:

```javascript
Authorization: Bearer ${DEV_AUTH_TOKEN}
```

Development mode uses: `dev-bypass-token`

### Error Handling

All API errors are caught and returned with descriptive messages:

```json
{
  "content": [{"type": "text", "text": "Error: API Error Message"}],
  "isError": true
}
```

## API Endpoints Reference

The MCP server communicates with the backend Express API running on localhost:3001 (dev) or configured production URL.

### Core API Routes

- `/api/stocks/*` - Stock data (search, quotes, profiles)
- `/api/scores/*` - Stock scoring system
- `/api/technical/*` - Technical indicators
- `/api/financials/*` - Financial data
- `/api/portfolio/*` - Portfolio management
- `/api/market/*` - Market data
- `/api/sectors/*` - Sector analysis
- `/api/signals/*` - Trading signals
- `/api/earnings/*` - Earnings data
- `/api/alerts/*` - Price alerts
- `/api/watchlist/*` - Custom watchlists
- `/api/trades/*` - Trade execution
- `/api/user/*` - User management
- And 28+ more...

### Full API Documentation

For complete API documentation, see:
- Backend: `/home/stocks/algo/webapp/lambda/routes/`
- Frontend Client: `/home/stocks/algo/webapp/frontend/src/services/api.js`

## Development

### Testing the MCP Server

1. **Start the backend API:**
```bash
cd /home/stocks/algo
npm run dev:backend
```

2. **Test MCP server directly:**
```bash
cd /home/stocks/algo/mcp-server
npm start
```

3. **Use in Claude Code:**
   - The MCP server will be available automatically in Claude Code
   - Use any of the available tools

### Adding New Tools

To add a new tool:

1. **Create tool handler function** in `index.js`
2. **Register tool** in the `tools` object with:
   - Description
   - Input schema
   - Handler function
3. **Update config.js** if needed

Example:
```javascript
const handleNewTool = async (params) => {
  const response = await callApi("/api/endpoint", "GET", params);
  return {
    content: [{ type: "text", text: JSON.stringify(response, null, 2) }],
  };
};

tools["new-tool-name"] = {
  description: "Description of what the tool does",
  inputSchema: {
    type: "object",
    properties: {
      param1: { type: "string", description: "First parameter" },
    },
    required: ["param1"],
  },
  handler: handleNewTool,
};
```

## Troubleshooting

### MCP Server Won't Start

1. Check Node.js version: `node --version` (requires >=18.0.0)
2. Install dependencies: `npm install`
3. Check environment variables in `.env`
4. Verify backend API is running on `http://localhost:3001`

### API Requests Fail

1. Verify backend API is running: `curl http://localhost:3001/api/health`
2. Check authentication token in `.env`
3. Verify endpoint path is correct
4. Check Claude Code console for detailed error messages

### Claude Code Doesn't See Tools

1. Verify `.claude/mcp.json` is configured correctly
2. Restart Claude Code
3. Check that the MCP server process is running
4. Review MCP server logs for errors

## Performance

- **Timeout**: 30 seconds per API request
- **Rate Limiting**: Subject to backend API limits
- **Caching**: Not implemented in MCP server (backend handles caching)

## Security

- Development uses `dev-bypass-token` (development only)
- Production uses environment variable `API_AUTH_TOKEN`
- All requests include `Authorization` header
- HTTPS recommended for production

## Future Enhancements

- [ ] Caching layer for frequently accessed data
- [ ] Batch operation support
- [ ] Streaming responses for large datasets
- [ ] WebSocket support for real-time data
- [ ] Rate limiting and quota management
- [ ] Request/response logging
- [ ] Performance metrics collection

## Support

For issues or questions:

1. Check MCP server logs
2. Verify backend API is running
3. Review tool input schemas
4. Check API endpoint documentation
5. Review .env configuration

## License

MIT

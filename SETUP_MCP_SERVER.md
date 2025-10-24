# Setting Up the MCP Server for Stocks Algo

This guide walks you through setting up and using the MCP (Model Context Protocol) server for your Stocks Algo platform.

## What is the MCP Server?

The MCP server is a bridge between Claude Code and your Stocks Algo APIs. It exposes all 757+ API endpoints through simple, structured tools that Claude Code can call.

## Quick Start

### Step 1: Install Dependencies

```bash
cd /home/stocks/algo/mcp-server
npm install
```

This installs:
- `@modelcontextprotocol/sdk` - MCP protocol implementation
- `axios` - HTTP client for API calls
- `dotenv` - Environment variable management

### Step 2: Verify Configuration

The MCP server is already configured in `/home/stocks/algo/.claude/mcp.json`. The configuration is set for local development:

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

### Step 3: Start Your Backend API

Make sure your backend Express API is running:

```bash
cd /home/stocks/algo
npm run dev:backend
# Or manually: node webapp/lambda/index.js
```

The API should be accessible at `http://localhost:3001`

### Step 4: Test the MCP Server

You can test the MCP server directly:

```bash
cd /home/stocks/algo/mcp-server
npm start
```

You should see the MCP server initialize successfully. Press Ctrl+C to stop.

### Step 5: Use in Claude Code

The MCP server is automatically configured for Claude Code. You can now use tools to interact with your APIs.

## Available Tools

The MCP server provides 20+ tools organized by domain:

### Stock Tools
- **search-stocks** - Search for stocks by symbol or name
  ```
  Tool: search-stocks
  Input: { query: "Apple", limit: 20 }
  ```

- **get-stock** - Get detailed information
  ```
  Tool: get-stock
  Input: { symbol: "AAPL" }
  ```

- **compare-stocks** - Compare multiple stocks
  ```
  Tool: compare-stocks
  Input: { symbols: ["AAPL", "MSFT", "GOOGL"] }
  ```

### Scoring Tools
- **get-stock-scores** - Get composite scores
  ```
  Tool: get-stock-scores
  Input: { symbols: ["AAPL", "MSFT"] }
  ```

- **top-stocks** - Get top stocks by factor
  ```
  Tool: top-stocks
  Input: { factor: "momentum", limit: 20, sector: "Technology" }
  ```

### Technical Analysis Tools
- **get-technical-indicators** - Get technical indicators
  ```
  Tool: get-technical-indicators
  Input: { symbol: "AAPL", indicators: ["RSI", "MACD"], period: "daily" }
  ```

- **analyze-technical** - Get analysis summary
  ```
  Tool: analyze-technical
  Input: { symbol: "AAPL" }
  ```

### Financial Tools
- **get-financial-statements** - Get financial statements
  ```
  Tool: get-financial-statements
  Input: { symbol: "AAPL", period: "quarterly" }
  ```

- **get-financial-metrics** - Get financial metrics
  ```
  Tool: get-financial-metrics
  Input: { symbol: "AAPL" }
  ```

### Portfolio Tools
- **get-portfolio** - Get portfolio overview
  ```
  Tool: get-portfolio
  Input: {}
  ```

- **get-holdings** - Get holdings
  ```
  Tool: get-holdings
  Input: {}
  ```

- **get-portfolio-performance** - Get performance
  ```
  Tool: get-portfolio-performance
  Input: {}
  ```

### Market Tools
- **get-market-overview** - Get market overview
  ```
  Tool: get-market-overview
  Input: {}
  ```

- **get-market-breadth** - Get market breadth
  ```
  Tool: get-market-breadth
  Input: {}
  ```

### Sector Tools
- **get-sector-data** - Get sector data
  ```
  Tool: get-sector-data
  Input: { sector: "Technology" }
  ```

- **get-sector-rotation** - Get rotation analysis
  ```
  Tool: get-sector-rotation
  Input: {}
  ```

### Signals Tools
- **get-signals** - Get trading signals
  ```
  Tool: get-signals
  Input: { symbol: "AAPL", type: "buy", limit: 20 }
  ```

### Earnings Tools
- **get-earnings-calendar** - Get earnings calendar
  ```
  Tool: get-earnings-calendar
  Input: { days: 30, symbols: ["AAPL"] }
  ```

- **get-earnings-data** - Get earnings data
  ```
  Tool: get-earnings-data
  Input: { symbol: "AAPL" }
  ```

### Advanced Tool
- **call-api** - Make direct API calls
  ```
  Tool: call-api
  Input: {
    endpoint: "/api/stocks/AAPL/price",
    method: "GET",
    params: { include: "quote" }
  }
  ```

## Configuration

### Environment Variables

Edit `/home/stocks/algo/mcp-server/.env`:

```bash
# Development (default)
NODE_ENV=development
API_URL_DEV=http://localhost:3001
DEV_AUTH_TOKEN=dev-bypass-token

# Production (when ready)
API_URL_PROD=https://your-prod-domain.com
API_AUTH_TOKEN=your-prod-token
```

### Changing MCP Configuration

To modify the MCP server configuration in Claude Code, edit `/home/stocks/algo/.claude/mcp.json`:

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

## Usage Examples

### Example 1: Search for Apple Stock and Get Scores

```
Claude: Search for Apple stock and get its composite score
MCP: Calls search-stocks with query: "Apple"
MCP: Calls get-stock-scores with symbol: "AAPL"
Result: Apple stock information + composite scores
```

### Example 2: Find Top Momentum Stocks

```
Claude: Find the top 20 momentum stocks
MCP: Calls top-stocks with factor: "momentum", limit: 20
Result: List of 20 stocks ranked by momentum score
```

### Example 3: Analyze a Stock Completely

```
Claude: Analyze MSFT for investment potential
MCP: Calls get-stock with symbol: "MSFT"
MCP: Calls get-stock-scores with symbol: "MSFT"
MCP: Calls get-technical-indicators with symbol: "MSFT"
MCP: Calls get-financial-metrics with symbol: "MSFT"
Result: Comprehensive analysis of MSFT
```

### Example 4: Portfolio Review

```
Claude: Show me my portfolio and its performance
MCP: Calls get-portfolio
MCP: Calls get-holdings
MCP: Calls get-portfolio-performance
Result: Complete portfolio overview
```

### Example 5: Market Analysis

```
Claude: What's the current market sentiment?
MCP: Calls get-market-overview
MCP: Calls get-market-breadth
MCP: Calls get-sector-rotation
Result: Current market conditions and trends
```

## Troubleshooting

### "MCP server not responding"

**Check:**
1. Backend API is running: `curl http://localhost:3001/api/health`
2. MCP server process: `ps aux | grep "mcp-server"`
3. Dependencies installed: `npm install` in `/home/stocks/algo/mcp-server`

**Fix:**
```bash
# Stop any existing processes
pkill -f "mcp-server"

# Reinstall dependencies
cd /home/stocks/algo/mcp-server
npm install

# Start backend API
cd /home/stocks/algo
npm run dev:backend

# Restart Claude Code
```

### "API Error: 401 Unauthorized"

**Check:**
1. `DEV_AUTH_TOKEN` in `.env` matches backend expectation
2. Backend is running in development mode
3. No authentication middleware blocking dev token

**Fix:**
```bash
# Verify backend uses dev-bypass-token
grep -r "dev-bypass-token" /home/stocks/algo/webapp/lambda

# Update .env if needed
echo "DEV_AUTH_TOKEN=dev-bypass-token" >> /home/stocks/algo/mcp-server/.env
```

### "Cannot find endpoint /api/stocks"

**Check:**
1. Endpoint path is correct
2. Backend API is serving the route
3. Route is registered in `/home/stocks/algo/webapp/lambda/routes/stocks.js`

**Fix:**
```bash
# Verify routes are registered
curl http://localhost:3001/api/stocks/search?q=AAPL
```

### "Timeout: API call took too long"

**Check:**
1. Backend API is responding slowly
2. Database queries are slow
3. Network latency

**Fix:**
- Increase timeout in `/home/stocks/algo/mcp-server/config.js`: `timeout: 60000`
- Profile backend performance
- Check database indexes

## Adding New Tools

To add a new tool for an API endpoint:

1. **Create handler function** in `/home/stocks/algo/mcp-server/index.js`:
   ```javascript
   const handleMyNewTool = async (params) => {
     const { symbol } = params;
     const response = await callApi(`/api/my-endpoint/${symbol}`, "GET");
     return {
       content: [{ type: "text", text: JSON.stringify(response, null, 2) }],
     };
   };
   ```

2. **Register tool** in the `tools` object:
   ```javascript
   tools["my-new-tool"] = {
     description: "Description of my new tool",
     inputSchema: {
       type: "object",
       properties: {
         symbol: { type: "string", description: "Stock symbol" },
       },
       required: ["symbol"],
     },
     handler: handleMyNewTool,
   };
   ```

3. **Restart MCP server** for changes to take effect

## Production Deployment

When deploying to production:

1. **Update environment variables:**
   ```bash
   API_URL_PROD=https://your-prod-domain.com
   API_AUTH_TOKEN=your-prod-token
   NODE_ENV=production
   ```

2. **Update MCP configuration:**
   ```json
   {
     "mcpServers": {
       "stocks-algo": {
         "env": {
           "NODE_ENV": "production",
           "API_URL_PROD": "https://your-prod-domain.com",
           "API_AUTH_TOKEN": "your-prod-token"
         }
       }
     }
   }
   ```

3. **Use HTTPS** for all API calls

4. **Implement rate limiting** to protect API

5. **Monitor MCP server logs** for errors

## Next Steps

1. ✅ MCP server is installed and configured
2. ✅ Backend API is running locally
3. ✅ 20+ tools are available in Claude Code
4. Test with a simple query: "Find top 10 momentum stocks"
5. Explore more complex analyses using multiple tools
6. Add custom tools for your specific needs
7. Deploy to production when ready

## More Information

- **MCP Server Code**: `/home/stocks/algo/mcp-server/index.js`
- **Configuration**: `/home/stocks/algo/mcp-server/config.js`
- **Claude Code Config**: `/home/stocks/algo/.claude/mcp.json`
- **Backend API**: `/home/stocks/algo/webapp/lambda/`
- **Frontend API Client**: `/home/stocks/algo/webapp/frontend/src/services/api.js`

## Support

For questions or issues:

1. Check the troubleshooting section above
2. Review MCP server logs: `npm start` in `/home/stocks/algo/mcp-server`
3. Test API endpoints directly: `curl http://localhost:3001/api/stocks/search?q=AAPL`
4. Review backend logs for API errors

Happy analyzing! 📈

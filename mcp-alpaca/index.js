#!/usr/bin/env node

/**
 * Alpaca Trading MCP Server
 *
 * This MCP server provides Claude Code access to Alpaca paper trading APIs.
 * It exposes tools for:
 * - Account information
 * - Market data and quotes
 * - Orders and trades
 * - Positions
 * - Real-time websocket data
 */

require("dotenv").config();

const { Server } = require("@modelcontextprotocol/sdk/server/index.js");
const {
  StdioServerTransport,
} = require("@modelcontextprotocol/sdk/server/stdio.js");
const {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  TextContent,
} = require("@modelcontextprotocol/sdk/types.js");

// HTTP client
const https = require("https");

// Initialize the server
const server = new Server(
  {
    name: "alpaca-trading-mcp",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Alpaca API Configuration
const ALPACA_API_KEY = process.env.ALPACA_API_KEY;
const ALPACA_SECRET_KEY = process.env.ALPACA_SECRET_KEY;
const ALPACA_BASE_URL = process.env.ALPACA_BASE_URL || "https://paper-api.alpaca.markets";
const ALPACA_DATA_URL = process.env.ALPACA_DATA_URL || "https://data.alpaca.markets";

if (!ALPACA_API_KEY || !ALPACA_SECRET_KEY) {
  console.error("❌ Missing Alpaca API credentials in environment variables");
  process.exit(1);
}

// Helper function to make HTTP requests to Alpaca API
async function alpacaRequest(method, path, body = null) {
  return new Promise((resolve, reject) => {
    const url = new URL(path.startsWith("http") ? path : ALPACA_BASE_URL + path);
    const options = {
      method,
      headers: {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "Content-Type": "application/json",
      },
    };

    const req = https.request(url, options, (res) => {
      let data = "";
      res.on("data", (chunk) => {
        data += chunk;
      });
      res.on("end", () => {
        try {
          if (res.statusCode >= 400) {
            reject({
              status: res.statusCode,
              message: data,
            });
          } else {
            resolve(JSON.parse(data || "{}"));
          }
        } catch (e) {
          reject(e);
        }
      });
    });

    req.on("error", reject);

    if (body) {
      req.write(JSON.stringify(body));
    }
    req.end();
  });
}

// Tool definitions
const tools = [
  {
    name: "get-account",
    description: "Get account information including cash, portfolio value, and buying power",
    inputSchema: {
      type: "object",
      properties: {},
      required: [],
    },
  },
  {
    name: "get-positions",
    description: "Get list of current positions in the account",
    inputSchema: {
      type: "object",
      properties: {},
      required: [],
    },
  },
  {
    name: "get-orders",
    description: "Get list of orders (open or closed)",
    inputSchema: {
      type: "object",
      properties: {
        status: {
          type: "string",
          description: "Filter by status: open, closed, all (default: all)",
        },
        limit: {
          type: "number",
          description: "Number of orders to return (default: 100)",
        },
      },
    },
  },
  {
    name: "place-order",
    description: "Place a new order to buy or sell a symbol",
    inputSchema: {
      type: "object",
      properties: {
        symbol: {
          type: "string",
          description: "Stock symbol (e.g., AAPL)",
        },
        qty: {
          type: "number",
          description: "Number of shares to buy/sell",
        },
        side: {
          type: "string",
          description: "buy or sell",
          enum: ["buy", "sell"],
        },
        order_type: {
          type: "string",
          description: "market, limit, stop, trailing_stop (default: market)",
        },
        limit_price: {
          type: "number",
          description: "Limit price (required for limit orders)",
        },
        stop_price: {
          type: "number",
          description: "Stop price (required for stop orders)",
        },
        time_in_force: {
          type: "string",
          description: "day, gtc, opg, cls (default: day)",
        },
      },
      required: ["symbol", "qty", "side"],
    },
  },
  {
    name: "cancel-order",
    description: "Cancel an open order by ID",
    inputSchema: {
      type: "object",
      properties: {
        order_id: {
          type: "string",
          description: "Order ID to cancel",
        },
      },
      required: ["order_id"],
    },
  },
  {
    name: "get-quote",
    description: "Get current quote data for a symbol",
    inputSchema: {
      type: "object",
      properties: {
        symbol: {
          type: "string",
          description: "Stock symbol (e.g., AAPL)",
        },
      },
      required: ["symbol"],
    },
  },
  {
    name: "get-quotes",
    description: "Get quotes for multiple symbols",
    inputSchema: {
      type: "object",
      properties: {
        symbols: {
          type: "string",
          description: "Comma-separated list of symbols (e.g., AAPL,MSFT,GOOGL)",
        },
      },
      required: ["symbols"],
    },
  },
  {
    name: "get-bars",
    description: "Get historical bar data for a symbol",
    inputSchema: {
      type: "object",
      properties: {
        symbol: {
          type: "string",
          description: "Stock symbol (e.g., AAPL)",
        },
        timeframe: {
          type: "string",
          description: "Bar timeframe: 1min, 5min, 15min, 1h, 1d (default: 1h)",
        },
        limit: {
          type: "number",
          description: "Number of bars to return (default: 100)",
        },
      },
      required: ["symbol"],
    },
  },
  {
    name: "get-calendar",
    description: "Get market calendar (trading days and hours)",
    inputSchema: {
      type: "object",
      properties: {
        start: {
          type: "string",
          description: "Start date (YYYY-MM-DD)",
        },
        end: {
          type: "string",
          description: "End date (YYYY-MM-DD)",
        },
      },
    },
  },
  {
    name: "get-clock",
    description: "Get current market time and status",
    inputSchema: {
      type: "object",
      properties: {},
      required: [],
    },
  },
];

// Register tools
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: tools,
}));

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  try {
    const { name, arguments: args } = request;

    switch (name) {
      case "get-account":
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                await alpacaRequest("GET", "/v2/account"),
                null,
                2
              ),
            },
          ],
        };

      case "get-positions":
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                await alpacaRequest("GET", "/v2/positions"),
                null,
                2
              ),
            },
          ],
        };

      case "get-orders": {
        const status = args.status || "all";
        const limit = args.limit || 100;
        const endpoint = `/v2/orders?status=${status}&limit=${limit}`;
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                await alpacaRequest("GET", endpoint),
                null,
                2
              ),
            },
          ],
        };
      }

      case "place-order": {
        const {
          symbol,
          qty,
          side,
          order_type = "market",
          limit_price,
          stop_price,
          time_in_force = "day",
        } = args;

        const orderData = {
          symbol,
          qty,
          side,
          type: order_type,
          time_in_force,
        };

        if (limit_price) orderData.limit_price = limit_price;
        if (stop_price) orderData.stop_price = stop_price;

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                await alpacaRequest("POST", "/v2/orders", orderData),
                null,
                2
              ),
            },
          ],
        };
      }

      case "cancel-order": {
        const { order_id } = args;
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                await alpacaRequest("DELETE", `/v2/orders/${order_id}`),
                null,
                2
              ),
            },
          ],
        };
      }

      case "get-quote": {
        const { symbol } = args;
        // Use Data API for quotes
        const url = `${ALPACA_DATA_URL}/v1beta3/latest/quotes?symbols=${symbol}`;
        try {
          const result = await alpacaRequest("GET", url);
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(result, null, 2),
              },
            ],
          };
        } catch (e) {
          // Fallback to account endpoint if data API fails
          return {
            content: [
              {
                type: "text",
                text: `Quote endpoint error: ${e.message || e}. Alpaca Data API may require additional setup.`,
              },
            ],
          };
        }
      }

      case "get-quotes": {
        const { symbols } = args;
        const url = `${ALPACA_DATA_URL}/v1beta3/latest/quotes?symbols=${symbols}`;
        try {
          const result = await alpacaRequest("GET", url);
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(result, null, 2),
              },
            ],
          };
        } catch (e) {
          return {
            content: [
              {
                type: "text",
                text: `Quotes endpoint error: ${e.message || e}. Alpaca Data API may require additional setup.`,
              },
            ],
          };
        }
      }

      case "get-bars": {
        const { symbol, timeframe = "1h", limit = 100 } = args;
        const url = `${ALPACA_DATA_URL}/v1beta3/latest/bars?symbols=${symbol}&timeframe=${timeframe}&limit=${limit}`;
        try {
          const result = await alpacaRequest("GET", url);
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(result, null, 2),
              },
            ],
          };
        } catch (e) {
          return {
            content: [
              {
                type: "text",
                text: `Bars endpoint error: ${e.message || e}. Alpaca Data API may require additional setup.`,
              },
            ],
          };
        }
      }

      case "get-calendar": {
        const start = args.start || "2025-01-01";
        const end = args.end || "2025-12-31";
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                await alpacaRequest("GET", `/v1/calendar?start=${start}&end=${end}`),
                null,
                2
              ),
            },
          ],
        };
      }

      case "get-clock":
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                await alpacaRequest("GET", "/v1/clock"),
                null,
                2
              ),
            },
          ],
        };

      default:
        return {
          content: [
            {
              type: "text",
              text: `Unknown tool: ${name}`,
            },
          ],
          isError: true,
        };
    }
  } catch (error) {
    return {
      content: [
        {
          type: "text",
          text: `Error: ${error.message || JSON.stringify(error)}`,
        },
      ],
      isError: true,
    };
  }
});

// Start the server
const transport = new StdioServerTransport();
server.connect(transport);

console.log("🚀 Alpaca Trading MCP Server started");
console.log("API Key: " + ALPACA_API_KEY.substring(0, 4) + "***");
console.log("Environment: " + (ALPACA_BASE_URL.includes("paper") ? "PAPER TRADING" : "LIVE TRADING"));
console.log("Ready to receive tool requests from Claude...");

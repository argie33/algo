#!/usr/bin/env node

/**
 * Stocks Algo MCP Server
 *
 * This MCP server provides Claude Code access to all APIs in the Stocks Algo platform.
 * It exposes tools for:
 * - Stock data and search
 * - Technical analysis
 * - Financial data
 * - Portfolio management
 * - Market data
 * - Trading signals
 * - And more...
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

const axios = require("axios");
const config = require("./config.js");

// Initialize the server
const server = new Server(
  {
    name: "stocks-algo-mcp",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// API client configuration
const getApiConfig = () => {
  const env = config.environment === "production" ? "prod" : "dev";
  return config.api[env];
};

const apiClient = axios.create({
  timeout: config.api.dev.timeout,
});

// Add authentication to requests
apiClient.interceptors.request.use((config) => {
  const apiConfig = getApiConfig();
  config.headers["Authorization"] = `Bearer ${apiConfig.authToken}`;
  Object.assign(config.headers, config.headers);
  return config;
});

/**
 * Helper function to make API calls
 */
const callApi = async (endpoint, method = "GET", params = {}, data = null) => {
  try {
    const apiConfig = getApiConfig();
    const url = `${apiConfig.baseUrl}${endpoint}`;

    const response = await apiClient({
      method,
      url,
      params: method === "GET" ? params : undefined,
      data: method !== "GET" ? data || params : undefined,
      headers: config.headers,
    });

    return response.data;
  } catch (error) {
    const errorMessage =
      error.response?.data?.message ||
      error.message ||
      "Unknown API error";
    throw new Error(`API Error: ${errorMessage}`);
  }
};

/**
 * Tool Implementations
 */

// Stock Tools
const handleSearchStocks = async (params) => {
  const { query, limit = 20, type } = params;
  if (!query) throw new Error("query parameter is required");

  const response = await callApi("/api/stocks/search", "GET", {
    q: query,
    limit,
    ...(type && { type }),
  });

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

const handleGetStock = async (params) => {
  const { symbol, include } = params;
  if (!symbol) throw new Error("symbol parameter is required");

  // Use quote endpoint which works reliably
  const response = await callApi(`/api/stocks/quote/${symbol}`, "GET", {
    ...(include && { include }),
  });

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

const handleCompareStocks = async (params) => {
  const { symbols } = params;
  if (!symbols || !Array.isArray(symbols) || symbols.length === 0) {
    throw new Error("symbols array is required");
  }

  // Use GET with query params for compare endpoint
  const response = await callApi("/api/stocks/compare", "GET", {
    symbols: symbols.join(","),
  });

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

// Scores Tools
const handleGetStockScores = async (params) => {
  const { symbols, factors } = params;
  if (!symbols || !Array.isArray(symbols) || symbols.length === 0) {
    throw new Error("symbols array is required");
  }

  const response = await callApi("/api/scores/batch", "POST", {
    symbols,
    ...(factors && { factors }),
  });

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

const handleTopStocks = async (params) => {
  const { factor, limit = 20, sector } = params;
  if (!factor) throw new Error("factor parameter is required");

  // Get all scores and filter/sort in response
  const response = await callApi("/api/scores", "GET", {
    limit: 100,
    ...(sector && { sector }),
  });

  if (response.data?.stocks) {
    // Sort by requested factor - REAL DATA ONLY, filter out stocks without real score data
    response.data.stocks = response.data.stocks
      .filter(stock => {
        // Only include stocks with real score data (not null, not undefined, not 0 as fake default)
        const score = stock[`${factor}_score`];
        return score !== null && score !== undefined && typeof score === 'number';
      })
      .sort((a, b) => {
        const aScore = a[`${factor}_score`];
        const bScore = b[`${factor}_score`];
        return bScore - aScore;
      })
      .slice(0, limit);
  }

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

// Technical Analysis Tools
const handleGetTechnicalIndicators = async (params) => {
  const { symbol, indicators, period = "daily" } = params;
  if (!symbol) throw new Error("symbol parameter is required");

  const response = await callApi(`/api/technical/${symbol}`, "GET", {
    period,
    ...(indicators && { indicators }),
  });

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

const handleAnalyzeTechnical = async (params) => {
  const { symbol } = params;
  if (!symbol) throw new Error("symbol parameter is required");

  // Use analysis endpoint which summarizes technical data
  const response = await callApi(
    `/api/stocks/analysis/${symbol}`,
    "GET"
  );

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

// Financial Data Tools
const handleGetFinancialStatements = async (params) => {
  const { symbol, period = "quarterly" } = params;
  if (!symbol) throw new Error("symbol parameter is required");

  // Use financials endpoint which returns statements
  const response = await callApi(`/api/financials/${symbol}`, "GET", {
    period,
  });

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

const handleGetFinancialMetrics = async (params) => {
  const { symbol } = params;
  if (!symbol) throw new Error("symbol parameter is required");

  const response = await callApi(`/api/financials/${symbol}/metrics`, "GET");

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

// Portfolio Tools
const handleGetPortfolio = async (params) => {
  const response = await callApi("/api/portfolio", "GET");
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

const handleGetHoldings = async (params) => {
  const response = await callApi("/api/portfolio/holdings", "GET");
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

const handleGetPortfolioPerformance = async (params) => {
  const response = await callApi("/api/portfolio/performance", "GET");
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

// Market Data Tools
const handleGetMarketOverview = async (params) => {
  const response = await callApi("/api/market/overview", "GET");
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

const handleGetMarketBreadth = async (params) => {
  const response = await callApi("/api/market/breadth", "GET");
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

// Sector Tools
const handleGetSectorData = async (params) => {
  const { sector } = params;
  const response = await callApi("/api/sectors", "GET", {
    ...(sector && { sector }),
  });
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

const handleGetSectorRotation = async (params) => {
  const response = await callApi("/api/sectors/rotation", "GET");
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

// Signals Tools
const handleGetSignals = async (params) => {
  const { symbol, type, limit = 20 } = params;
  const response = await callApi("/api/signals", "GET", {
    ...(symbol && { symbol }),
    ...(type && { type }),
    limit,
  });
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

// Earnings Tools
const handleGetEarningsCalendar = async (params) => {
  const { days = 30, symbols } = params;
  // Use calendar endpoint for earnings calendar
  const response = await callApi("/api/calendar", "GET", {
    days,
    type: "earnings",
    ...(symbols && { symbols }),
  });
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

const handleGetEarningsData = async (params) => {
  const { symbol } = params;
  if (!symbol) throw new Error("symbol parameter is required");

  const response = await callApi(`/api/earnings/${symbol}`, "GET");
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

// Generic API Call Tool
const handleCallApi = async (params) => {
  const { endpoint, method = "GET", params: queryParams, body } = params;
  if (!endpoint) throw new Error("endpoint parameter is required");

  const response = await callApi(endpoint, method, queryParams, body);
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(response, null, 2),
      },
    ],
  };
};

/**
 * Tool Registry
 */
const tools = {
  "search-stocks": {
    description: "Search for stocks by symbol or name",
    inputSchema: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Stock symbol or company name to search for",
        },
        limit: {
          type: "number",
          description: "Maximum number of results (default: 20)",
        },
        type: {
          type: "string",
          description: "Filter by type (stock, etf, etc.)",
        },
      },
      required: ["query"],
    },
    handler: handleSearchStocks,
  },

  "get-stock": {
    description: "Get detailed information about a specific stock",
    inputSchema: {
      type: "object",
      properties: {
        symbol: {
          type: "string",
          description: "Stock ticker symbol",
        },
        include: {
          type: "string",
          description: "Additional data to include (profile, quotes, etc.)",
        },
      },
      required: ["symbol"],
    },
    handler: handleGetStock,
  },

  "compare-stocks": {
    description: "Compare multiple stocks side by side",
    inputSchema: {
      type: "object",
      properties: {
        symbols: {
          type: "array",
          items: { type: "string" },
          description: "Array of stock symbols to compare",
        },
      },
      required: ["symbols"],
    },
    handler: handleCompareStocks,
  },

  "get-stock-scores": {
    description: "Get composite scores for one or more stocks",
    inputSchema: {
      type: "object",
      properties: {
        symbols: {
          type: "array",
          items: { type: "string" },
          description: "Array of stock symbols",
        },
        factors: {
          type: "array",
          items: { type: "string" },
          description:
            "Specific factors to include (quality, momentum, value, growth, positioning, sentiment, stability)",
        },
      },
      required: ["symbols"],
    },
    handler: handleGetStockScores,
  },

  "top-stocks": {
    description: "Get top-ranked stocks by a specific scoring factor",
    inputSchema: {
      type: "object",
      properties: {
        factor: {
          type: "string",
          description:
            "Scoring factor (quality, momentum, value, growth, positioning, sentiment, stability)",
        },
        limit: {
          type: "number",
          description: "Number of top stocks to return (default: 20)",
        },
        sector: {
          type: "string",
          description: "Filter by sector",
        },
      },
      required: ["factor"],
    },
    handler: handleTopStocks,
  },

  "get-technical-indicators": {
    description:
      "Get technical indicators for a stock (RSI, MACD, Bollinger Bands, etc.)",
    inputSchema: {
      type: "object",
      properties: {
        symbol: {
          type: "string",
          description: "Stock symbol",
        },
        indicators: {
          type: "array",
          items: { type: "string" },
          description: "Specific indicators to include",
        },
        period: {
          type: "string",
          description: "Time period (daily, weekly, monthly)",
        },
      },
      required: ["symbol"],
    },
    handler: handleGetTechnicalIndicators,
  },

  "analyze-technical": {
    description: "Get technical analysis summary for a stock",
    inputSchema: {
      type: "object",
      properties: {
        symbol: {
          type: "string",
          description: "Stock symbol",
        },
      },
      required: ["symbol"],
    },
    handler: handleAnalyzeTechnical,
  },

  "get-financial-statements": {
    description:
      "Get financial statements (income, balance sheet, cash flow) for a stock",
    inputSchema: {
      type: "object",
      properties: {
        symbol: {
          type: "string",
          description: "Stock symbol",
        },
        period: {
          type: "string",
          description: "Period type (quarterly or annual)",
        },
      },
      required: ["symbol"],
    },
    handler: handleGetFinancialStatements,
  },

  "get-financial-metrics": {
    description: "Get financial metrics (PE, PB, ROE, etc.) for a stock",
    inputSchema: {
      type: "object",
      properties: {
        symbol: {
          type: "string",
          description: "Stock symbol",
        },
      },
      required: ["symbol"],
    },
    handler: handleGetFinancialMetrics,
  },

  "get-portfolio": {
    description: "Get the user's portfolio overview",
    inputSchema: {
      type: "object",
      properties: {},
    },
    handler: handleGetPortfolio,
  },

  "get-holdings": {
    description: "Get the user's portfolio holdings",
    inputSchema: {
      type: "object",
      properties: {},
    },
    handler: handleGetHoldings,
  },

  "get-portfolio-performance": {
    description: "Get portfolio performance metrics",
    inputSchema: {
      type: "object",
      properties: {},
    },
    handler: handleGetPortfolioPerformance,
  },

  "get-market-overview": {
    description: "Get market overview with indices and market data",
    inputSchema: {
      type: "object",
      properties: {},
    },
    handler: handleGetMarketOverview,
  },

  "get-market-breadth": {
    description: "Get market breadth indicators (advance/decline, etc.)",
    inputSchema: {
      type: "object",
      properties: {},
    },
    handler: handleGetMarketBreadth,
  },

  "get-sector-data": {
    description: "Get sector analysis and performance data",
    inputSchema: {
      type: "object",
      properties: {
        sector: {
          type: "string",
          description: "Specific sector to get data for",
        },
      },
    },
    handler: handleGetSectorData,
  },

  "get-sector-rotation": {
    description: "Get sector rotation analysis",
    inputSchema: {
      type: "object",
      properties: {},
    },
    handler: handleGetSectorRotation,
  },

  "get-signals": {
    description: "Get trading signals from the system",
    inputSchema: {
      type: "object",
      properties: {
        symbol: {
          type: "string",
          description: "Filter signals for a specific stock",
        },
        type: {
          type: "string",
          description: "Signal type (buy, sell, hold)",
        },
        limit: {
          type: "number",
          description: "Maximum number of signals to return",
        },
      },
    },
    handler: handleGetSignals,
  },

  "get-earnings-calendar": {
    description: "Get earnings calendar",
    inputSchema: {
      type: "object",
      properties: {
        days: {
          type: "number",
          description: "Number of days ahead to look (default: 30)",
        },
        symbols: {
          type: "array",
          items: { type: "string" },
          description: "Filter for specific symbols",
        },
      },
    },
    handler: handleGetEarningsCalendar,
  },

  "get-earnings-data": {
    description: "Get earnings data for a specific stock",
    inputSchema: {
      type: "object",
      properties: {
        symbol: {
          type: "string",
          description: "Stock symbol",
        },
      },
      required: ["symbol"],
    },
    handler: handleGetEarningsData,
  },

  "call-api": {
    description:
      "Make a direct API call to any Stocks Algo API endpoint (advanced)",
    inputSchema: {
      type: "object",
      properties: {
        endpoint: {
          type: "string",
          description: "API endpoint path (e.g., /api/stocks/AAPL)",
        },
        method: {
          type: "string",
          description: "HTTP method (GET, POST, PUT, DELETE)",
        },
        params: {
          type: "object",
          description: "Query parameters",
        },
        body: {
          type: "object",
          description: "Request body for POST/PUT requests",
        },
      },
      required: ["endpoint"],
    },
    handler: handleCallApi,
  },
};

/**
 * MCP Server Handlers
 */

// List available tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: Object.entries(tools).map(([name, tool]) => ({
      name,
      description: tool.description,
      inputSchema: tool.inputSchema,
    })),
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const toolName = request.params.name;
  const toolInput = request.params.arguments;

  const tool = tools[toolName];
  if (!tool) {
    return {
      content: [
        {
          type: "text",
          text: `Tool not found: ${toolName}`,
        },
      ],
      isError: true,
    };
  }

  try {
    const result = await tool.handler(toolInput);
    return result;
  } catch (error) {
    return {
      content: [
        {
          type: "text",
          text: `Error: ${error.message}`,
        },
      ],
      isError: true,
    };
  }
});

/**
 * Start the server
 */
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});

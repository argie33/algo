// MCP Server Configuration for Stocks Algo APIs

module.exports = {
  // API Server Configuration
  api: {
    // Development environment - AWS API Gateway
    dev: {
      baseUrl: process.env.API_URL_DEV || "https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev",
      authToken: process.env.DEV_AUTH_TOKEN || "",
      timeout: 60000, // Increased to 60 seconds for large queries
    },
    // Production environment - AWS API Gateway
    prod: {
      baseUrl: process.env.API_URL_PROD || "https://qda42av7je.execute-api.us-east-1.amazonaws.com/prod",
      authToken: process.env.API_AUTH_TOKEN || "",
      timeout: 60000,
    },
  },

  // Environment configuration - Set to production to use AWS API
  environment: process.env.NODE_ENV || "production",

  // API Categories - Grouped by domain
  apiCategories: {
    stocks: {
      name: "Stock Data & Search",
      routes: ["/api/stocks"],
      description: "Stock search, quotes, profiles, comparisons",
    },
    scores: {
      name: "Stock Scoring",
      routes: ["/api/scores"],
      description: "Composite stock scores and rankings",
    },
    technical: {
      name: "Technical Analysis",
      routes: ["/api/technical"],
      description: "Technical indicators and charting",
    },
    financials: {
      name: "Financial Data",
      routes: ["/api/financials"],
      description: "Financial statements and metrics",
    },
    portfolio: {
      name: "Portfolio Management",
      routes: ["/api/portfolio"],
      description: "User portfolio and holdings",
    },
    trades: {
      name: "Trade Execution",
      routes: ["/api/trades", "/api/orders"],
      description: "Trading and order management",
    },
    signals: {
      name: "Trading Signals",
      routes: ["/api/signals"],
      description: "Buy/sell signals",
    },
    market: {
      name: "Market Data",
      routes: ["/api/market"],
      description: "Market overview and breadth",
    },
    sectors: {
      name: "Sector Analysis",
      routes: ["/api/sectors"],
      description: "Sector data and rotation",
    },
    economic: {
      name: "Economic Data",
      routes: ["/api/economic"],
      description: "FRED economic indicators",
    },
    earnings: {
      name: "Earnings Data",
      routes: ["/api/earnings"],
      description: "Earnings estimates and results",
    },
    sentiment: {
      name: "Market Sentiment",
      routes: ["/api/sentiment"],
      description: "Sentiment and market psychology",
    },
    alerts: {
      name: "Alerts & Notifications",
      routes: ["/api/alerts"],
      description: "Price and portfolio alerts",
    },
    watchlist: {
      name: "Watchlists",
      routes: ["/api/watchlist"],
      description: "Custom watchlists",
    },
    dashboard: {
      name: "Dashboard",
      routes: ["/api/dashboard"],
      description: "Dashboard aggregated data",
    },
    user: {
      name: "User Management",
      routes: ["/api/user", "/api/settings"],
      description: "User profile and preferences",
    },
    analytics: {
      name: "Analytics",
      routes: ["/api/analytics"],
      description: "Analytics and reporting",
    },
    research: {
      name: "Research",
      routes: ["/api/research"],
      description: "Research and analysis",
    },
  },

  // Tools configuration
  tools: {
    // Stock tools
    stocks: {
      "search-stocks": {
        description: "Search for stocks by symbol or name",
        params: ["query"],
        optional: ["limit", "type"],
      },
      "get-stock": {
        description: "Get detailed stock information",
        params: ["symbol"],
        optional: ["include"],
      },
      "compare-stocks": {
        description: "Compare multiple stocks",
        params: ["symbols"],
      },
    },

    // Scoring tools
    scores: {
      "get-stock-scores": {
        description: "Get composite scores for stocks",
        params: ["symbols"],
        optional: ["factors"],
      },
      "top-stocks": {
        description: "Get top stocks by score",
        params: ["factor"],
        optional: ["limit", "sector"],
      },
    },

    // Technical analysis tools
    technical: {
      "get-technical-indicators": {
        description: "Get technical indicators for a stock",
        params: ["symbol"],
        optional: ["indicators", "period"],
      },
      "analyze-technical": {
        description: "Get technical analysis summary",
        params: ["symbol"],
      },
    },

    // Financial data tools
    financials: {
      "get-financial-statements": {
        description: "Get financial statements",
        params: ["symbol"],
        optional: ["period"],
      },
      "get-financial-metrics": {
        description: "Get financial metrics",
        params: ["symbol"],
      },
    },

    // Portfolio tools
    portfolio: {
      "get-portfolio": {
        description: "Get user's portfolio",
      },
      "get-holdings": {
        description: "Get portfolio holdings",
      },
      "get-portfolio-performance": {
        description: "Get portfolio performance metrics",
      },
    },

    // Market data tools
    market: {
      "get-market-overview": {
        description: "Get market overview and indices",
      },
      "get-market-breadth": {
        description: "Get market breadth indicators",
      },
    },

    // Sector tools
    sectors: {
      "get-sector-data": {
        description: "Get sector analysis data",
        optional: ["sector"],
      },
      "get-sector-rotation": {
        description: "Get sector rotation analysis",
      },
    },

    // Signals tools
    signals: {
      "get-signals": {
        description: "Get trading signals",
        optional: ["symbol", "type", "limit"],
      },
    },

    // Earnings tools
    earnings: {
      "get-earnings-calendar": {
        description: "Get earnings calendar",
        optional: ["days", "symbols"],
      },
      "get-earnings-data": {
        description: "Get earnings data for a stock",
        params: ["symbol"],
      },
    },

    // Generic API call tool
    api: {
      "call-api": {
        description: "Make a direct API call to any endpoint",
        params: ["endpoint"],
        optional: ["method", "params", "body"],
      },
    },
  },

  // HTTP headers
  headers: {
    "Content-Type": "application/json",
    "User-Agent": "StocksAlgo-MCP-Server/1.0",
  },
};

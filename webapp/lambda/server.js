// Load environment variables first
require("dotenv").config();

const cors = require("cors");
const express = require("express");
const helmet = require("helmet");
const morgan = require("morgan");

const _errorHandler = require("./middleware/errorHandler");
const responseFormatter = require("./middleware/responseFormatter");
const { initializeDatabase } = require("./utils/database");
const alertsRoutes = require("./routes/alerts");
const analyticsRoutes = require("./routes/analytics");
const analystRoutes = require("./routes/analysts");
const authRoutes = require("./routes/auth");
const benchmarksRoutes = require("./routes/benchmarks");
const calendarRoutes = require("./routes/calendar");
const commoditiesRoutes = require("./routes/commodities");
const dashboardRoutes = require("./routes/dashboard");
const diagnosticsRoutes = require("./routes/diagnostics");
const dividendRoutes = require("./routes/dividend");
const earningsRoutes = require("./routes/earnings");
const economicRoutes = require("./routes/economic");
const etfRoutes = require("./routes/etf");
const financialRoutes = require("./routes/financials");
const healthRoutes = require("./routes/health");
const insiderRoutes = require("./routes/insider");
const marketRoutes = require("./routes/market");
const metricsRoutes = require("./routes/metrics");
const momentumRoutes = require("./routes/momentum");
const newsRoutes = require("./routes/news");
const ordersRoutes = require("./routes/orders");
const performanceRoutes = require("./routes/performance");
const portfolioRoutes = require("./routes/portfolio");
const positioningMetricsRoutes = require("./routes/positioning-metrics");
const positioningRoutes = require("./routes/positioning");
const priceRoutes = require("./routes/price");
const recommendationsRoutes = require("./routes/recommendations");
const researchRoutes = require("./routes/research");
const riskRoutes = require("./routes/risk");
// const scoringRoutes = require("./routes/scoring"); // Deprecated - use scores routes instead
const scoresRoutes = require("./routes/scores");
const screenerRoutes = require("./routes/screener");
const sectorsRoutes = require("./routes/sectors");
const sentimentRoutes = require("./routes/sentiment");
const settingsRoutes = require("./routes/settings");
// const socialRoutes = require("./routes/social"); // Social trading removed - not implemented
const stockRoutes = require("./routes/stocks");
const strategyBuilderRoutes = require("./routes/strategyBuilder");
const technicalRoutes = require("./routes/technical");
const tradingRoutes = require("./routes/trading");
const tradesRoutes = require("./routes/trades");
const userRoutes = require("./routes/user");
const watchlistRoutes = require("./routes/watchlist");
const websocketRoutes = require("./routes/websocket");

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(helmet());
// Dynamic CORS configuration
const allowedOrigins = [
  "http://localhost:3000",
  "http://127.0.0.1:3000",
  "http://localhost:3001",
  "http://localhost:3002",
  "http://localhost:3003",
  "http://localhost:5173", // Common Vite port
  "http://localhost:5174", // Vite alternate port
  "http://localhost:5175", // Vite alternate port
  "http://localhost:5176", // Vite alternate port
  "http://localhost:5177", // Vite alternate port
  "http://127.0.0.1:3001",
  "http://127.0.0.1:3002",
  "http://127.0.0.1:3003",
  "http://127.0.0.1:5173",
  "http://127.0.0.1:5174",
  "http://127.0.0.1:5175",
  "http://127.0.0.1:5176",
  "http://127.0.0.1:5177",
];

// Add API Gateway URL if available
if (process.env.API_GATEWAY_URL) {
  allowedOrigins.push(process.env.API_GATEWAY_URL);
}

// Add custom CORS origins from environment
if (process.env.CORS_ALLOWED_ORIGINS) {
  const customOrigins = process.env.CORS_ALLOWED_ORIGINS.split(",").map((o) =>
    o.trim()
  );
  allowedOrigins.push(...customOrigins);
}

app.use(
  cors({
    origin: [
      ...allowedOrigins,
      /^https:\/\/.*\.cloudfront\.net$/,
      /^https:\/\/.*\.amazonaws\.com$/,
    ],
    credentials: true,
  })
);

// Logging
if (process.env.NODE_ENV !== "production") {
  app.use(morgan("combined"));
}

// Body parsing with error handling
app.use(
  express.json({
    limit: "10mb",
    // Add error handling for invalid JSON
    verify: (req, res, buf, encoding) => {
      if (buf && buf.length) {
        req.rawBody = buf.toString(encoding || "utf8");
      }
    },
  })
);
app.use(express.urlencoded({ extended: true, limit: "10mb" }));

// Response formatter middleware (adds res.success and res.error)
app.use(responseFormatter);

// Serve static frontend files
const path = require("path");
app.use(express.static(path.join(__dirname, "dist")));

// Initialize database connection
initializeDatabase();

// Routes
app.use("/api/alerts", alertsRoutes);
app.use("/api/analytics", analyticsRoutes);
app.use("/api/auth", authRoutes);
app.use("/api/stocks", stockRoutes);
app.use("/api/strategies", strategyBuilderRoutes);
app.use("/api/strategy-builder", strategyBuilderRoutes);
app.use("/api/metrics", metricsRoutes);
app.use("/api/health", healthRoutes);
app.use("/health", healthRoutes);
app.use("/api/market", marketRoutes);
app.use("/api/momentum", momentumRoutes);
app.use("/api/positioning-metrics", positioningMetricsRoutes);
app.use("/api/analysts", analystRoutes);
app.use("/api/benchmarks", benchmarksRoutes);
app.use("/api/calendar", calendarRoutes);
app.use("/api/commodities", commoditiesRoutes);
app.use("/api/dashboard", dashboardRoutes);
app.use("/api/diagnostics", diagnosticsRoutes);
app.use("/api/dividend", dividendRoutes);
app.use("/api/earnings", earningsRoutes);
app.use("/api/economic", economicRoutes);
app.use("/api/etf", etfRoutes);
app.use("/api/financials", financialRoutes);
app.use("/api/insider", insiderRoutes);
app.use("/api/news", newsRoutes);
app.use("/api/orders", ordersRoutes);
app.use("/api/performance", performanceRoutes);
app.use("/api/portfolio", portfolioRoutes);
app.use("/api/positioning", positioningRoutes);
app.use("/api/price", priceRoutes);
app.use("/api/recommendations", recommendationsRoutes);
app.use("/api/research", researchRoutes);
app.use("/api/risk", riskRoutes);
// app.use("/api/scoring", scoringRoutes); // Deprecated - use /api/scores instead
app.use("/api/scores", scoresRoutes);
app.use("/api/screener", screenerRoutes);
app.use("/api/sectors", sectorsRoutes);
app.use("/api/sentiment", sentimentRoutes);
app.use("/api/settings", settingsRoutes);
// app.use("/api/social", socialRoutes); // Social trading removed - not implemented
app.use("/api/technical", technicalRoutes);
app.use("/api/trading", tradingRoutes);
app.use("/api/trades", tradesRoutes);
app.use("/api/user", userRoutes);
app.use("/api/watchlist", watchlistRoutes);
app.use("/api/websocket", websocketRoutes);

// Health check endpoint
app.get("/health", (req, res) => {
  res.json({
    status: "healthy",
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV || "development",
    service: "Financial Dashboard API",
    version: "1.0.0",
  });
});

// All endpoints now use real database data - no mock endpoints needed

// API info endpoint
app.get("/api", (req, res) => {
  res.json({
    name: "LoadFundamentals API",
    version: "1.0.0",
    endpoints: {
      stocks: "/api/stocks",
      metrics: "/api/metrics",
      health: "/api/health",
      market: "/api/market",
      analysts: "/api/analysts",
      financials: "/api/financials",
      trading: "/api/trading",
      technical: "/api/technical",
      calendar: "/api/calendar",
      data: "/api/data",
    },
    timestamp: new Date().toISOString(),
  });
});

// Default route
app.get("/", (req, res) => {
  res.json({
    message: "Financial Dashboard API",
    version: "1.0.0",
    status: "operational",
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV || "development",
    endpoints: {
      health: {
        quick: "/health?quick=true",
        full: "/health",
      },
      api: {
        stocks: "/api/stocks",
        screen: "/api/stocks/screen",
        metrics: "/api/metrics",
        market: "/api/market",
        analysts: "/api/analysts",
        trading: "/api/trading",
        technical: "/api/technical",
        calendar: "/api/calendar",
      },
    },
    notes:
      "Use /health?quick=true for fast status check without database dependency",
  });
});

// Serve React app for client-side routes
app.get("*", (req, res) => {
  // Don't interfere with API routes - they're handled above
  if (req.path.startsWith("/api") || req.path.startsWith("/health")) {
    return res.status(404).json({
      success: false,
      error: "Not Found",
      message: `Route ${req.originalUrl} not found`,
      timestamp: new Date().toISOString(),
    });
  }
  res.sendFile(path.join(__dirname, "dist", "index.html"));
});

// Error handling
app.use((err, req, res, _next) => {
  try {
    console.error("Error:", err);
  } catch (e) {
    // Ignore console logging errors
  }

  // Handle JSON parsing errors specifically
  if (err.type === "entity.parse.failed" || err.name === "SyntaxError") {
    return res.status(400).json({
      success: false,
      error: "Invalid JSON format",
      message: "Request body contains malformed JSON",
      details:
        process.env.NODE_ENV === "development"
          ? {
              body:
                err.body ||
                (req.rawBody ? req.rawBody.substring(0, 200) : "No body"),
              parseError: err.message,
            }
          : undefined,
      timestamp: new Date().toISOString(),
    });
  }

  // Handle other client errors
  if (err.status >= 400 && err.status < 500) {
    return res.status(err.status).json({
      success: false,
      error: err.message || "Bad Request",
      timestamp: new Date().toISOString(),
    });
  }

  // Handle server errors
  res.status(500).json({
    success: false,
    error: "Internal Server Error",
    message:
      process.env.NODE_ENV === "development"
        ? err.message
        : "Something went wrong",
    timestamp: new Date().toISOString(),
  });
});

// 404 handler
app.use("*", (req, res) => {
  res.status(404).json({
    success: false,
    error: "Not Found",
    message: `Route ${req.originalUrl} not found`,
    timestamp: new Date().toISOString(),
  });
});

// Start server
if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`🚀 Financial Dashboard API server running on port ${PORT}`);
    console.log(`📊 Environment: ${process.env.NODE_ENV || "development"}`);
    console.log(`🌐 Health check: http://localhost:${PORT}/health`);
    console.log(`📋 API info: http://localhost:${PORT}/api`);
  });
}

module.exports = app;

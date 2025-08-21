// Load environment variables first
require("dotenv").config();

const express = require("express");
const cors = require("cors");
const helmet = require("helmet");
const morgan = require("morgan");
const { initializeDatabase } = require("./utils/database");
const _errorHandler = require("./middleware/errorHandler");

// Import routes
const authRoutes = require("./routes/auth");
const stockRoutes = require("./routes/stocks");
const metricsRoutes = require("./routes/metrics");
const healthRoutes = require("./routes/health");
const marketRoutes = require("./routes/market");
const analystRoutes = require("./routes/analysts");
const financialRoutes = require("./routes/financials");
const tradingRoutes = require("./routes/trading");
const technicalRoutes = require("./routes/technical");
const calendarRoutes = require("./routes/calendar");
const signalsRoutes = require("./routes/signals");
const dataRoutes = require("./routes/data");
const dashboardRoutes = require("./routes/dashboard");

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(helmet());
// Dynamic CORS configuration
const allowedOrigins = ["http://localhost:3000", "http://127.0.0.1:3000"];

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

// Body parsing
app.use(express.json({ limit: "10mb" }));
app.use(express.urlencoded({ extended: true, limit: "10mb" }));

// Initialize database connection
initializeDatabase();

// Routes
app.use("/api/auth", authRoutes);
app.use("/api/stocks", stockRoutes);
app.use("/api/metrics", metricsRoutes);
app.use("/api/health", healthRoutes);
app.use("/api/market", marketRoutes);
app.use("/api/analysts", analystRoutes);
app.use("/api/financials", financialRoutes);
app.use("/api/trading", tradingRoutes);
app.use("/api/technical", technicalRoutes);
app.use("/api/calendar", calendarRoutes);
app.use("/api/signals", signalsRoutes);
app.use("/api/data", dataRoutes);
app.use("/api/dashboard", dashboardRoutes);

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
      signals: "/api/signals",
      data: "/api/data",
    },
    timestamp: new Date().toISOString(),
  });
});

// Mock endpoints for development
if (process.env.NODE_ENV !== "production") {
  app.get("/api/stocks", (req, res) => {
    res.json({
      success: true,
      data: [
        { symbol: "AAPL", name: "Apple Inc.", price: 150.0 },
        { symbol: "GOOGL", name: "Alphabet Inc.", price: 2800.0 },
        { symbol: "MSFT", name: "Microsoft Corporation", price: 300.0 },
      ],
      message: "Mock stock data for development",
    });
  });

  app.get("/api/market", (req, res) => {
    res.json({
      success: true,
      data: {
        sp500: { value: 4500, change: 25.5, changePercent: 0.57 },
        nasdaq: { value: 14000, change: -50.2, changePercent: -0.36 },
        dow: { value: 35000, change: 100.0, changePercent: 0.29 },
      },
      message: "Mock market data for development",
    });
  });

  app.get("/api/health/full", (req, res) => {
    res.json({
      status: "healthy",
      healthy: true,
      service: "Financial Dashboard API",
      timestamp: new Date().toISOString(),
      environment: process.env.NODE_ENV || "development",
      memory: process.memoryUsage(),
      uptime: process.uptime(),
      database: { status: "mock_mode" },
      api: {
        version: "1.0.0",
        environment: process.env.NODE_ENV || "development",
      },
    });
  });
}

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
        signals: "/api/signals",
      },
    },
    notes:
      "Use /health?quick=true for fast status check without database dependency",
  });
});

// Error handling
app.use((err, req, res, _next) => {
  console.error("Error:", err);
  res.status(500).json({
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

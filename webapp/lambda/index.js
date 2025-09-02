// Load environment variables first
require("dotenv").config();

// Financial Dashboard API - Lambda Function
// Updated: 2025-06-25 - Fixed CORS configuration for API Gateway

const cors = require("cors");
const express = require("express");
const helmet = require("helmet");
const morgan = require("morgan");
const serverless = require("serverless-http");

const errorHandler = require("./middleware/errorHandler");
const responseFormatterMiddleware = require("./middleware/responseFormatter");
const { initializeDatabase } = require("./utils/database");
const alertsRoutes = require("./routes/alerts");
const analystRoutes = require("./routes/analysts");
const analyticsRoutes = require("./routes/analytics");
const authRoutes = require("./routes/auth");
const backtestRoutes = require("./routes/backtest");
const calendarRoutes = require("./routes/calendar");
const commoditiesRoutes = require("./routes/commodities");
const dashboardRoutes = require("./routes/dashboard");
const diagnosticsRoutes = require("./routes/diagnostics");
const economicRoutes = require("./routes/economic");
const financialRoutes = require("./routes/financials");
const healthRoutes = require("./routes/health");
const liveDataRoutes = require("./routes/liveData");
const marketRoutes = require("./routes/market");
const metricsRoutes = require("./routes/metrics");
const newsRoutes = require("./routes/news");
const ordersRoutes = require("./routes/orders");
const performanceRoutes = require("./routes/performance");
const portfolioRoutes = require("./routes/portfolio");
const priceRoutes = require("./routes/price");
const recommendationsRoutes = require("./routes/recommendations");
const researchRoutes = require("./routes/research");
const earningsRoutes = require("./routes/earnings");
const riskRoutes = require("./routes/risk");
const scoringRoutes = require("./routes/scoring");
const scoresRoutes = require("./routes/scores");
const screenerRoutes = require("./routes/screener");
const sectorsRoutes = require("./routes/sectors");
const sentimentRoutes = require("./routes/sentiment");
const settingsRoutes = require("./routes/settings");
const signalsRoutes = require("./routes/signals");
const stockRoutes = require("./routes/stocks");
const technicalRoutes = require("./routes/technical");
const tradingRoutes = require("./routes/trading");
const tradesRoutes = require("./routes/trades");
const watchlistRoutes = require("./routes/watchlist");
const websocketRoutes = require("./routes/websocket");
const etfRoutes = require("./routes/etf");
const insiderRoutes = require("./routes/insider");
const dividendRoutes = require("./routes/dividend");
const positioningRoutes = require("./routes/positioning");

const app = express();

// Debug endpoint for AWS Secrets Manager
app.get("/api/debug-secret", async (req, res) => {
  try {
    const {
      SecretsManagerClient,
      GetSecretValueCommand,
    } = require("@aws-sdk/client-secrets-manager");

    const secretsManager = new SecretsManagerClient({
      region: process.env.AWS_REGION || "us-east-1",
    });

    const secretArn = process.env.DB_SECRET_ARN;
    if (!secretArn) {
      return res.json({ error: "DB_SECRET_ARN not set" });
    }

    const command = new GetSecretValueCommand({ SecretId: secretArn });
    const result = await secretsManager.send(command);

    const debugInfo = {
      secretType: typeof result.SecretString,
      secretLength: result.SecretString?.length,
      secretPreview: result.SecretString?.substring(0, 100),
      first5Chars: JSON.stringify(result.SecretString?.substring(0, 5)),
      isString: typeof result.SecretString === "string",
      isObject: typeof result.SecretString === "object",
      parseAttempt: null,
      parseError: null,
    };

    if (typeof result.SecretString === "string") {
      try {
        const parsed = JSON.parse(result.SecretString);
        debugInfo.parseAttempt = "SUCCESS";
        debugInfo.parsedKeys = Object.keys(parsed);
      } catch (parseError) {
        debugInfo.parseAttempt = "FAILED";
        debugInfo.parseError = parseError.message;
      }
    } else if (
      typeof result.SecretString === "object" &&
      result.SecretString !== null
    ) {
      debugInfo.parseAttempt = "OBJECT_ALREADY_PARSED";
      debugInfo.parsedKeys = Object.keys(result.SecretString);
    }

    res.json({
      status: "debug",
      timestamp: new Date().toISOString(),
      debugInfo: debugInfo,
    });
  } catch (error) {
    console.error("Error debugging secret:", error);
    res.status(500).json({
      status: "error",
      error: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Trust proxy when running behind API Gateway/CloudFront
app.set("trust proxy", true);

// Enhanced security middleware for enterprise production deployment
app.use(
  helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        styleSrc: ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
        fontSrc: ["'self'", "https://fonts.gstatic.com"],
        imgSrc: ["'self'", "data:", "https:", "blob:"],
        scriptSrc: ["'self'", "'unsafe-inline'"],
        connectSrc: ["'self'", "wss:", "https:"],
        frameSrc: ["'none'"],
        objectSrc: ["'none'"],
        baseUri: ["'self'"],
        formAction: ["'self'"],
        upgradeInsecureRequests: [],
      },
    },
    hsts: {
      maxAge: 31536000, // 1 year
      includeSubDomains: true,
      preload: true,
    },
    frameguard: { action: "deny" },
    noSniff: true,
    xssFilter: true,
    referrerPolicy: { policy: "strict-origin-when-cross-origin" },
    permittedCrossDomainPolicies: false,
    crossOriginEmbedderPolicy: false, // Disabled for financial data APIs
    crossOriginOpenerPolicy: { policy: "same-origin" },
    crossOriginResourcePolicy: { policy: "cross-origin" },
  })
);

// Additional security headers for financial applications
app.use((req, res, next) => {
  // Prevent MIME type sniffing
  res.setHeader("X-Content-Type-Options", "nosniff");

  // Prevent clickjacking
  res.setHeader("X-Frame-Options", "DENY");

  // Enable XSS protection
  res.setHeader("X-XSS-Protection", "1; mode=block");

  // Strict transport security
  res.setHeader(
    "Strict-Transport-Security",
    "max-age=31536000; includeSubDomains; preload"
  );

  // Referrer policy
  res.setHeader("Referrer-Policy", "strict-origin-when-cross-origin");

  // Feature policy for financial applications
  res.setHeader(
    "Permissions-Policy",
    "geolocation=(), microphone=(), camera=(), payment=(), usb=(), " +
      "screen-wake-lock=(), web-share=(), gyroscope=(), magnetometer=()"
  );

  // Cache control for sensitive financial data
  if (req.path.includes("/portfolio") || req.path.includes("/trading")) {
    res.setHeader(
      "Cache-Control",
      "no-store, no-cache, must-revalidate, proxy-revalidate"
    );
    res.setHeader("Pragma", "no-cache");
    res.setHeader("Expires", "0");
  }

  // API rate limiting headers
  res.setHeader("X-RateLimit-Limit", "1000");
  res.setHeader("X-RateLimit-Window", "3600");

  next();
});

// Note: Rate limiting removed - API Gateway handles this

// CORS configuration (allow specific origins including CloudFront)
app.use(
  cors({
    origin: (origin, callback) => {
      // Allow requests with no origin (like mobile apps or curl requests)
      if (!origin) {
        return callback(null, true);
      }

      // Specific allowed origins
      const allowedOrigins = [
        "https://d1copuy2oqlazx.cloudfront.net",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
      ];

      // Allow specific origins or patterns
      if (
        allowedOrigins.includes(origin) ||
        origin.includes(".execute-api.") ||
        origin.includes(".cloudfront.net") ||
        origin.includes("localhost") ||
        origin.includes("127.0.0.1") ||
        origin === process.env.FRONTEND_URL
      ) {
        callback(null, true);
      } else {
        console.warn("CORS blocked origin:", origin);
        callback(new Error("Not allowed by CORS"));
      }
    },
    credentials: true,
    methods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allowedHeaders: [
      "Content-Type",
      "Authorization",
      "X-Requested-With",
      "X-Api-Key",
      "X-Amz-Date",
      "X-Amz-Security-Token",
    ],
  })
);

// Request parsing
app.use(express.json({ limit: "10mb" }));
app.use(express.urlencoded({ extended: true, limit: "10mb" }));

// JSON parsing error handler
app.use((error, req, res, next) => {
  if (error instanceof SyntaxError && error.status === 400 && "body" in error) {
    return res.status(400).json({
      success: false,
      error: "Bad Request",
      message: "Invalid JSON format",
    });
  }
  next(error);
});

// Note: API Gateway strips the /api prefix before sending to Lambda

// Logging (simplified for Lambda)
const nodeEnv = process.env.NODE_ENV || "production";
const isProduction = nodeEnv === "production" || nodeEnv === "prod";

if (!isProduction) {
  app.use(morgan("combined"));
}

// Global database initialization promise
let dbInitPromise = null;
let __dbAvailable = false;

// Initialize database connection with shorter timeout
const ensureDatabase = async () => {
  if (!dbInitPromise) {
    console.log("Initializing database connection...");
    dbInitPromise = Promise.race([
      initializeDatabase().catch((err) => {
        console.error("Database initialization error details:", {
          message: err.message,
          stack: err.stack,
          config: err.config,
          env: err.env,
        });
        throw err;
      }),
      new Promise((_, reject) =>
        setTimeout(
          () =>
            reject(
              new Error("Database initialization timeout after 15 seconds")
            ),
          15000
        )
      ),
    ])
      .then((pool) => {
        __dbAvailable = true;
        console.log("Database connection established successfully");
        return pool;
      })
      .catch((err) => {
        console.error("Failed to initialize database:", err);
        dbInitPromise = null; // Reset to allow retry
        __dbAvailable = false;
        throw err;
      });
  }
  return dbInitPromise;
};

// Middleware to check database requirement based on endpoint
app.use(async (req, res, next) => {
  console.log(`Processing request: ${req.method} ${req.path}`);

  // Endpoints that don't require database
  const nonDbEndpoints = ["/", "/health"];
  const isHealthQuick = req.path === "/health" && req.query.quick === "true";

  if (nonDbEndpoints.includes(req.path) || isHealthQuick) {
    console.log("Endpoint does not require database connection");
    return next();
  }

  // For endpoints that need database, try to ensure connection
  try {
    await ensureDatabase();
    console.log("Database connection verified for database-dependent endpoint");
    next();
  } catch (error) {
    console.error(
      "Database initialization failed for database-dependent endpoint:",
      {
        message: error.message,
        stack: error.stack,
        config: error.config,
        env: error.env,
      }
    );

    // For health endpoint (non-quick), still allow it to proceed with DB error info
    if (req.path === "/health") {
      req.dbError = error;
      return next();
    }

    // For other endpoints, return service unavailable instead of forbidden
    res.status(503).json({
      error: "Service temporarily unavailable - database connection failed",
      message: "The database is currently unavailable. Please try again later.",
      timestamp: new Date().toISOString(),
      details: !isProduction ? error.message : undefined,
      debug: !isProduction
        ? {
            config: error.config,
            env: error.env,
          }
        : undefined,
    });
  }
});

// Response formatter middleware - adds standard response methods
app.use(responseFormatterMiddleware);

// Routes (note: API Gateway handles the /api prefix)
app.use("/health", healthRoutes);
app.use("/auth", authRoutes);
app.use("/stocks", stockRoutes);
app.use("/screener", screenerRoutes);
app.use("/websocket", websocketRoutes);
app.use("/scores", scoresRoutes);
app.use("/metrics", metricsRoutes);
app.use("/market", marketRoutes);
app.use("/analysts", analystRoutes);
app.use("/analytics", analyticsRoutes);
app.use("/commodities", commoditiesRoutes);
app.use("/financials", financialRoutes);
app.use("/trading", tradingRoutes);
app.use("/technical", technicalRoutes);
app.use("/calendar", calendarRoutes);
app.use("/dashboard", dashboardRoutes);
app.use("/signals", signalsRoutes);
app.use("/backtest", backtestRoutes);
app.use("/portfolio", portfolioRoutes);
app.use("/performance", performanceRoutes);
app.use("/scoring", scoringRoutes);
app.use("/price", priceRoutes);
app.use("/risk", riskRoutes);
app.use("/sectors", sectorsRoutes);
app.use("/sentiment", sentimentRoutes);
app.use("/settings", settingsRoutes);
app.use("/trades", tradesRoutes);
app.use("/live-data", liveDataRoutes);
app.use("/orders", ordersRoutes);
app.use("/news", newsRoutes);
app.use("/diagnostics", diagnosticsRoutes);
app.use("/watchlist", watchlistRoutes);
app.use("/etf", etfRoutes);
app.use("/insider", insiderRoutes);
app.use("/dividend", dividendRoutes);

// Also mount routes with /api prefix for frontend compatibility
app.use("/api/alerts", alertsRoutes);
app.use("/api/health", healthRoutes);
app.use("/api/auth", authRoutes);
app.use("/api/stocks", stockRoutes);
app.use("/api/screener", screenerRoutes);
app.use("/api/websocket", websocketRoutes);
app.use("/api/scores", scoresRoutes);
app.use("/api/metrics", metricsRoutes);
app.use("/api/market", marketRoutes);
app.use("/api/analyst", analystRoutes);
app.use("/api/analysts", analystRoutes);
app.use("/api/analytics", analyticsRoutes);
app.use("/api/commodities", commoditiesRoutes);
app.use("/api/financials", financialRoutes);
app.use("/api/trading", tradingRoutes);
app.use("/api/technical", technicalRoutes);
app.use("/api/watchlist", watchlistRoutes);
app.use("/api/watchlists", watchlistRoutes);
app.use("/api/calendar", calendarRoutes);
app.use("/api/dashboard", dashboardRoutes);
app.use("/api/economic", economicRoutes);
app.use("/api/signals", signalsRoutes);
app.use("/api/backtest", backtestRoutes);
app.use("/api/portfolio", portfolioRoutes);
app.use("/api/performance", performanceRoutes);
app.use("/api/recommendations", recommendationsRoutes);
app.use("/api/research", researchRoutes);
app.use("/api/earnings", earningsRoutes);
app.use("/api/scoring", scoringRoutes);
app.use("/api/price", priceRoutes);
app.use("/api/risk", riskRoutes);
app.use("/api/sectors", sectorsRoutes);
app.use("/api/sentiment", sentimentRoutes);
app.use("/api/settings", settingsRoutes);
app.use("/api/trades", tradesRoutes);
app.use("/api/live-data", liveDataRoutes);
app.use("/api/orders", ordersRoutes);
app.use("/api/news", newsRoutes);
app.use("/api/diagnostics", diagnosticsRoutes);
app.use("/api/etf", etfRoutes);
app.use("/api/insider", insiderRoutes);
app.use("/api/dividend", dividendRoutes);
app.use("/api/positioning", positioningRoutes);

// Default route
app.get("/", (req, res) => {
  res.json({
    message: "Financial Dashboard API",
    version: "1.0.0",
    status: "operational",
    timestamp: new Date().toISOString(),
    environment: nodeEnv,
    endpoints: {
      health: {
        quick: "/health?quick=true",
        full: "/health",
      },
      api: {
        stocks: "/stocks",
        screen: "/stocks/screen",
        metrics: "/metrics",
        market: "/market",
        analysts: "/analysts",
        trading: "/trading",
        technical: "/technical",
        calendar: "/calendar",
        signals: "/signals",
      },
    },
    notes:
      "Use /health?quick=true for fast status check without database dependency",
  });
});

// 404 handler
app.use("*", (req, res) => {
  res.notFound(`Endpoint ${req.originalUrl}`);
});

// Error handling middleware (should be last)
app.use(errorHandler);

// Export Lambda handler
module.exports.handler = serverless(app, {
  // Lambda-specific options
  request: (request, event, context) => {
    // Add AWS event/context to request if needed
    request.event = event;
    request.context = context;
  },
});

// Export app for local testing
module.exports.app = app;

// For local testing
if (require.main === module) {
  const PORT = process.env.PORT || 3001;
  app.listen(PORT, () => {
    console.log(
      `Financial Dashboard API server running on port ${PORT} (local mode)`
    );
    console.log(`Health check: http://localhost:${PORT}/health`);
    console.log(`Stocks: http://localhost:${PORT}/stocks`);
    console.log(`Technical: http://localhost:${PORT}/technical/daily`);
  });
}

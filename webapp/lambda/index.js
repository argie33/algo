// Load environment variables ONCE at startup from .env.local (local dev only)
// Production: No .env file needed - uses AWS environment variables or Secrets Manager
const path = require("path");

const envPath = path.resolve(__dirname, "../../.env.local");
console.log(`🔧 Loading environment from: ${envPath}`);
const envResult = require("dotenv").config({ path: envPath });
console.log(`🔧 Environment load result:`, {
  path: envPath,
  fileExists: require("fs").existsSync(envPath),
  loaded: envResult.parsed ? Object.keys(envResult.parsed).length : 0,
  keys: envResult.error ? `ERROR: ${envResult.error.message}` : "OK",
  hasAlpacaKey: !!process.env.ALPACA_API_KEY
});

// Financial Dashboard API - Lambda Function
// Updated: 2025-10-26 - Fixed CORS configuration (CloudFront: https://d1copuy2oqlazx.cloudfront.net)

const { createServer } = require("http");

const cors = require("cors");
const express = require("express");
const helmet = require("helmet");
const morgan = require("morgan");

// const responseFormatterMiddleware = require("./middleware/responseFormatter"); // DEPRECATED
const errorHandler = require("./middleware/errorHandler");
const { cacheMiddleware } = require("./middleware/cache");
const { initializeDatabase, query } = require("./utils/database");
const { initializeAlpacaSync } = require("./utils/alpacaSyncScheduler");
const analystsRoutes = require("./routes/analysts");
const authRoutes = require("./routes/auth");
const communityRoutes = require("./routes/community");
const commoditiesRoutes = require("./routes/commodities");
const contactRoutes = require("./routes/contact");
const earningsRoutes = require("./routes/earnings");
const economicRoutes = require("./routes/economic");
const financialRoutes = require("./routes/financials");
const healthRoutes = require("./routes/health");
const industriesRoutes = require("./routes/industries");
const manualTradesRoutes = require("./routes/manual-trades");
const marketRoutes = require("./routes/market");
const metricsRoutes = require("./routes/metrics");
const optionsRoutes = require("./routes/options");
const optimizationRoutes = require("./routes/optimization");
const portfolioRoutes = require("./routes/portfolio");
const priceRoutes = require("./routes/price");
// const scoringRoutes = require("./routes/scoring"); // DEPRECATED - Use scores system instead
const scoresRoutes = require("./routes/scores");
const sectorsRoutes = require("./routes/sectors");
const sentimentRoutes = require("./routes/sentiment");
const signalsRoutes = require("./routes/signals");
const stocksRoutes = require("./routes/stocks");
const strategiesRoutes = require("./routes/strategies");
const technicalRoutes = require("./routes/technicals");
const tradesRoutes = require("./routes/trades");
const userRoutes = require("./routes/user");

const app = express();



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

  // Cache control - ABSOLUTELY NO CACHING
  res.setHeader("Cache-Control", "no-store, no-cache, no-transform, must-revalidate, max-age=0, private");
  res.setHeader("Pragma", "no-cache");
  res.setHeader("Expires", "0");
  res.setHeader("Surrogate-Control", "no-store");
  res.removeHeader("ETag");
  res.setHeader("Last-Modified", new Date().toUTCString());

  // Remove X-Powered-By header to reduce info disclosure
  res.removeHeader("X-Powered-By");

  // API rate limiting headers
  res.setHeader("X-RateLimit-Limit", "1000");
  res.setHeader("X-RateLimit-Window", "3600");

  next();
});

// Note: Rate limiting removed - API Gateway handles this

// Global OPTIONS handler for CORS preflight requests (MUST be before CORS middleware)
app.options('*', (req, res) => {
  console.log(`🔄 Global OPTIONS handler for: ${req.path} from origin: ${req.headers.origin}`);

  // Ensure CORS headers are explicitly set for AWS API Gateway compatibility
  const origin = req.headers.origin;
  const defaultCloudFront = process.env.CLOUDFRONT_DOMAIN || "https://d1copuy2oqlazx.cloudfront.net";
  const allowedOrigin = origin && (origin.includes(".cloudfront.net") || origin.includes("localhost")) ? origin : defaultCloudFront;

  res.header("Access-Control-Allow-Origin", allowedOrigin);
  res.header("Access-Control-Allow-Credentials", "true");
  res.header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS,HEAD,PATCH");
  res.header(
    "Access-Control-Allow-Headers",
    "Content-Type,Authorization,X-Requested-With,X-Api-Key,X-Amz-Date,X-Amz-Security-Token,X-Request-ID,Accept,Accept-Language,Cache-Control,Origin"
  );
  res.header("Access-Control-Max-Age", "86400");
  res.header("Vary", "Origin,Access-Control-Request-Method,Access-Control-Request-Headers");

  res.status(200).end();
});

// CORS configuration (allow specific origins including CloudFront)
app.use(
  cors({
    origin: (origin, callback) => {
      // Allow requests with no origin (like mobile apps or curl requests)
      if (!origin) {
        return callback(null, true);
      }

      // In test environment, allow additional test domains for CORS testing
      const isTestEnv = process.env.NODE_ENV === "test";

      // Specific allowed origins
      const allowedOrigins = [
        // CloudFront & AWS Endpoints
        process.env.CLOUDFRONT_DOMAIN || "https://d1copuy2oqlazx.cloudfront.net",
        process.env.API_GATEWAY_URL || "https://qda42av7je.execute-api.us-east-1.amazonaws.com",

        // Production domains - update these with your actual domains
        "https://example.com",           // Site A - Markets & Stocks (public)
        "https://admin.example.com",     // Site B - Admin/Portfolio (private)
        "https://www.example.com",
        "https://www.admin.example.com",

        // Local development
        "http://localhost:3000",
        "http://localhost:5173",         // Markets site dev
        "http://localhost:5174",         // Admin site dev
        "http://localhost:5175",
        "http://localhost:5176",
        "http://localhost:5177",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://127.0.0.1:5176",
        "http://127.0.0.1:5177",
      ];

      // Test-only origins for CORS testing
      const testOnlyOrigins = [
        "https://example.com",
        "https://test.example.com",
        "http://test-domain.local"
      ];

      // Combine origins based on environment
      const finalAllowedOrigins = isTestEnv ?
        [...allowedOrigins, ...testOnlyOrigins] :
        allowedOrigins;

      // Allow specific origins or patterns
      if (
        finalAllowedOrigins.includes(origin) ||
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
    methods: ["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    allowedHeaders: [
      "Content-Type",
      "Authorization",
      "X-Requested-With",
      "X-Api-Key",
      "X-Amz-Date",
      "X-Amz-Security-Token",
      "X-Request-ID",
      "Accept",
      "Accept-Language",
      "Cache-Control",
      "Origin",
    ],
    preflightContinue: false,
    optionsSuccessStatus: 200,
  })
);

// Enhanced CORS headers for AWS API Gateway compatibility
app.use((req, res, next) => {
  const origin = req.headers.origin;

  // AWS Lambda/API Gateway environment detection
  const isLambda = process.env.AWS_LAMBDA_FUNCTION_NAME;
  const isAPIGateway = req.headers['x-forwarded-for'] || req.headers['x-amzn-requestid'];

  // Always set CORS headers for all requests (crucial for AWS API Gateway)
  const defaultCloudFront = process.env.CLOUDFRONT_DOMAIN || "https://d1copuy2oqlazx.cloudfront.net";
  const allowedOrigin = origin && (origin.includes(".cloudfront.net") ||
                                   origin.includes("localhost") ||
                                   origin.includes("127.0.0.1")) ? origin :
                       defaultCloudFront;

  res.header("Access-Control-Allow-Origin", allowedOrigin);
  res.header("Access-Control-Allow-Credentials", "true");
  res.header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS,HEAD,PATCH");
  res.header(
    "Access-Control-Allow-Headers",
    "Content-Type,Authorization,X-Requested-With,X-Api-Key,X-Amz-Date,X-Amz-Security-Token,X-Request-ID,Accept,Accept-Language,Cache-Control,Origin"
  );
  res.header("Access-Control-Max-Age", "86400"); // Cache preflight for 24 hours

  // Additional headers for AWS environments
  if (isLambda || isAPIGateway) {
    res.header("Access-Control-Expose-Headers", "X-Request-ID,X-Amzn-RequestId");
    res.header("Vary", "Origin,Access-Control-Request-Method,Access-Control-Request-Headers");
  }

  // CORS headers are now set above for all requests

  // Add AWS-specific context to request for debugging
  if (isLambda) {
    req.context = {
      awsRequestId: req.headers['x-amzn-requestid'],
      functionName: process.env.AWS_LAMBDA_FUNCTION_NAME,
      functionVersion: process.env.AWS_LAMBDA_FUNCTION_VERSION,
      remainingTimeInMillis: () => 30000 // Default to 30 seconds
    };
  }

  // Handle preflight requests with enhanced AWS support
  if (req.method === "OPTIONS") {
    console.log(`🔄 CORS preflight request for: ${req.path}`);
    res.status(200).end();
    return;
  }

  next();
});

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

if (!isProduction && nodeEnv !== 'test') {
  app.use(morgan("combined"));
}

// DISABLED: No caching for finance data - must always be fresh
// app.use(cacheMiddleware(5 * 60 * 1000));
// Finance sites MUST NOT serve stale data

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
      new Promise((_, reject) => {
        const timeoutMs = parseInt(process.env.DB_INIT_TIMEOUT) || 30000; // Default 30 seconds, configurable via env
        setTimeout(
          () =>
            reject(
              new Error(
                `Database initialization timeout after ${timeoutMs / 1000} seconds`
              )
            ),
          timeoutMs
        );
      }),
    ])
      .then((pool) => {
        __dbAvailable = true;
        if (process.env.NODE_ENV !== 'test') {
          console.log("Database connection established successfully");
        }
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
  if (process.env.NODE_ENV !== 'test') {
    console.log(`Processing request: ${req.method} ${req.path}`);
  }

  // Endpoints that don't require database
  const nonDbEndpoints = ["/"];

  if (nonDbEndpoints.includes(req.path)) {
    console.log("Endpoint does not require database connection");
    return next();
  }

  // For endpoints that need database, try to ensure connection
  try {
    await ensureDatabase();
    if (process.env.NODE_ENV !== 'test') {
      console.log("Database connection verified for database-dependent endpoint");
    }
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

// API routes use standard Express response methods - see RULES.md for response pattern

// Canonical API Routes - all under /api prefix
app.use("/api/analysts", analystsRoutes);
app.use("/api/auth", authRoutes);
app.use("/api/commodities", commoditiesRoutes);
app.use("/api/community", communityRoutes);
app.use("/api/contact", contactRoutes);
app.use("/api/earnings", earningsRoutes);
app.use("/api/economic", economicRoutes);
app.use("/api/financials", financialRoutes);
app.use("/api/health", healthRoutes);
app.use("/api/industries", industriesRoutes);
app.use("/api/market", marketRoutes);
app.use("/api/metrics", metricsRoutes);
app.use("/api/options", optionsRoutes);
app.use("/api/optimization", optimizationRoutes);
app.use("/api/portfolio", portfolioRoutes);
app.use("/api/price", priceRoutes);
app.use("/api/scores", scoresRoutes);
app.use("/api/sectors", sectorsRoutes);
app.use("/api/sentiment", sentimentRoutes);
app.use("/api/signals", signalsRoutes);
app.use("/api/stocks", stocksRoutes);
app.use("/api/strategies", strategiesRoutes);
app.use("/api/technicals", technicalRoutes);
app.use("/api/trades", tradesRoutes);
app.use("/api/trades/manual", manualTradesRoutes);
app.use("/api/user", userRoutes);

// API info endpoint
app.get("/api", (req, res) => {
  res.json({
    data: {
      name: "Financial Dashboard API",
      version: "2.0.0",
      status: "operational",
      endpoints: {
        auth: "/api/auth",
        commodities: "/api/commodities",
        earnings: "/api/earnings",
        economic: "/api/economic",
        financials: "/api/financials",
        health: "/api/health",
        market: "/api/market",
        portfolio: "/api/portfolio",
        price: "/api/price",
        scores: "/api/scores",
        sectors: "/api/sectors",
        sentiment: "/api/sentiment",
        signals: "/api/signals",
        user: "/api/user",
        trades: "/api/trades"
      },
      timestamp: new Date().toISOString(),
    },
    success: true
  });
});

// Default route - API documentation
// NOTE: Disabled to serve admin SPA instead - see static middleware at bottom
// If you need API root endpoint, use /api instead
/*
app.get("/", (req, res) => {
  res.json({
    message: "Financial Dashboard API",
    version: "1.0.0",
    status: "operational",
    timestamp: new Date().toISOString(),
    environment: nodeEnv,
    notes: "Use /health?quick=true for fast status check without database dependency",
    endpoints: {
      health: "/health?quick=true",
      api_stocks: "/api/stocks",
      api_scores: "/api/scores",
      api_sectors: "/api/sectors",
      api_alerts: "/api/alerts",
      api_signals: "/api/signals",
    },
  });
});
*/

// Create HTTP server (WebSocket removed)
const server = createServer(app);


// Serve main frontend static files
const mainBuildPath = path.join(__dirname, '../frontend/dist');
app.use(express.static(mainBuildPath, {
  maxAge: '1d',
  etag: false
}));

// Fallback to index.html for SPA routing
app.get('/', (req, res) => {
  res.sendFile(path.join(mainBuildPath, 'index.html'));
});

// Serve admin site static files (BEFORE 404 handler)
const adminBuildPath = path.join(__dirname, '../frontend-admin/dist-admin');
app.use(express.static(adminBuildPath, {
  maxAge: '1d',
  etag: false,
  index: false // Don't serve index.html for directory requests
}));

// 404 handler (for any remaining unhandled requests)
app.use("*", (req, res) => {
  res.status(404).json({
    error: "Not Found",
    message: `Endpoint ${req.originalUrl} does not exist`,
    timestamp: new Date().toISOString()
  });
});

// Error handling middleware (should be last)
app.use(errorHandler);

// AWS Lambda / EC2 handler - listen directly on existing server (supports both HTTP and WebSocket)
const PORT = process.env.PORT || 3001;

// Detect Lambda environment - don't call server.listen() in Lambda (serverless-http handles it)
const isLambdaEnvironment = !!process.env.LAMBDA_TASK_ROOT || !!process.env.AWS_LAMBDA_FUNCTION_NAME;

if (!isLambdaEnvironment) {
  // Local development or EC2 - start HTTP server
  server.listen(PORT, '::', () => {
    console.log(
      `✅ Financial Dashboard API running on port ${PORT}`
    );
    console.log(`🌐 Health check: http://localhost:${PORT}/api/health`);
    console.log(`🌐 Health check: http://127.0.0.1:${PORT}/api/health`);
    console.log(`📈 Sectors: http://localhost:${PORT}/api/sectors`);
    console.log(`💼 Scores (Stock Data): http://localhost:${PORT}/api/scores/stockscores`);
    console.log(`⚡ All endpoints available at http://localhost:${PORT}/api/*`);

    // Initialize Alpaca portfolio sync scheduler
    // Syncs every 10 minutes automatically
    initializeAlpacaSync();
  });
} else {
  // AWS Lambda environment - serverless-http wrapper handles HTTP request routing
  console.log('🔷 Running in AWS Lambda environment - using serverless-http handler');
}

// Handle graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down gracefully...');
  server.close(() => {
    console.log('Server closed');
    // eslint-disable-next-line no-process-exit
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  console.log('SIGINT received, shutting down gracefully...');
  server.close(() => {
    console.log('Server closed');
    // eslint-disable-next-line no-process-exit
    process.exit(0);
  });
});

// Export app for testing/importing
module.exports = app;

// AWS Lambda handler - CRITICAL FOR LAMBDA TO WORK
// This MUST be exported for Lambda to find the handler function
const serverlessHttp = require('serverless-http');
module.exports.handler = serverlessHttp(app);

// Force redeploy Thu Oct  2 18:22:58 CDT 2025
// Emergency fix 1759448244
// Trigger Lambda deployment - test schema fixes
// Fixed: Added serverless-http handler export 2025-10-28 17:04 UTC
// Fixed: Restored stocks.js route handler (HTTP 404 fix)
// Trigger: Rebuild Lambda with fixed routes - 2026-01-03

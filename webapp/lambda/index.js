// Load environment variables ONCE at startup from .env.local (LOCAL DEVELOPMENT ONLY)
// Production (Lambda/CI): NEVER load from .env files - uses AWS environment variables or Secrets Manager
const path = require("path");
const fs = require("fs");

// Only load .env.local in local development (never in Lambda/CI)
if (!process.env.AWS_LAMBDA_FUNCTION_NAME && !process.env.CI) {
  const envPath = path.resolve(__dirname, "../../.env.local");
  try {
    const envResult = require("dotenv").config({ path: envPath });
    if (envResult.parsed) {
      console.log(`[Startup] Loaded .env.local from ${envPath} (local development)`);
    }
  } catch (e) {
    console.debug(`[Startup] .env.local not found or not readable (normal in production)`);
  }
}

// Financial Dashboard API - Lambda Function
// Updated: 2026-05-09 - Fixed CORS configuration + auth flow

// Note: Authentication is handled by API Gateway (Cognito JWT authorizer)
// No custom JWT signing/verification is performed in this Lambda
// The Cognito JWT token is validated at the API Gateway level before reaching this function

const cors = require("cors");
const express = require("express");

const { createServer } = require("http");

const helmet = require("helmet");
const morgan = require("morgan");

const serverlessHttp = require('serverless-http');

const errorHandler = require("./middleware/errorHandler");
const requestLogger = require("./middleware/requestLogger");
const auditLogger = require("./middleware/auditLogger");
const { authenticateToken } = require("./middleware/auth");
const { initializeDatabase, initializeSchema, query } = require("./utils/database");
const { initializeAlpacaSync } = require("./utils/alpacaSyncScheduler");
const { marketCache } = require("./utils/market-cache");
const responseNormalizer = require("./middleware/responseNormalizer");
const { cacheMiddleware } = require("./middleware/cacheMiddleware");
const { sendSuccess, sendError } = require("./utils/apiResponse");
const auditRoutes = require("./routes/audit");
const commoditiesRoutes = require("./routes/commodities");
const diagnosticsRoutes = require("./routes/diagnostics");
const economicRoutes = require("./routes/economic");
const healthRoutes = require("./routes/health");
const industriesRoutes = require("./routes/industries");
const manualTradesRoutes = require("./routes/manual-trades");
const marketRoutes = require("./routes/market");
const optimizationRoutes = require("./routes/optimization");
const scoresRoutes = require("./routes/scores");
const sectorsRoutes = require("./routes/sectors");
const sentimentRoutes = require("./routes/sentiment");
const signalsRoutes = require("./routes/signals");
const strategiesRoutes = require("./routes/strategies");
const tradesRoutes = require("./routes/trades");
const backtestsRoutes = require("./routes/backtests");
const statusRoutes = require("./routes/status");
const performanceRoutes = require("./routes/performance");
const logoutRoutes = require("./routes/logout");

const app = express();

// CRITICAL: Catch unhandled errors to prevent orphaned processes
process.on('unhandledRejection', (reason, promise) => {
  console.error(' Unhandled Promise Rejection:', reason);
  if (reason && reason.stack) console.error('Stack:', reason.stack);
});

process.on('uncaughtException', (error) => {
  console.error(' Uncaught Exception:', error);
  console.error('Stack:', error.stack);
  console.error('⚠️ Server continues running (DO NOT EXIT - prevents orphaned processes)');
});

// Global request timeout to prevent hanging requests
const REQUEST_TIMEOUT = 60000;
app.use((req, res, next) => {
  // Only set socket timeout if socket exists (not in Lambda)
  if (req.socket && typeof req.socket.setTimeout === 'function') {
    req.socket.setTimeout(REQUEST_TIMEOUT);
    req.socket.on('timeout', () => {
      console.error(`⏱️ Request timeout: ${req.method} ${req.path}`);
      if (!res.headersSent) {
        sendError(res, 'Request timeout - server busy', 503);
      }
      req.socket.destroy();
    });
  }
  next();
});

// SECURITY FIX #8: Trust 2 hops (CloudFront + API Gateway) to extract real client IP
// CloudFront adds X-Forwarded-For header, then API Gateway adds its own
// trust proxy 2 skips the rightmost 2 IPs to get the real client IP
app.set("trust proxy", 2);

// Enhanced security middleware for enterprise production deployment
app.use(
  helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        // FIXED: Reduce unsafe-inline usage in production
        styleSrc: ["'self'", "https://fonts.googleapis.com"],
        // Note: If inline styles are required, add nonces instead of unsafe-inline
        // styleSrc: ["'self'", "https://fonts.googleapis.com", `'nonce-${nonce}'`]
        fontSrc: ["'self'", "https://fonts.gstatic.com"],
        // FIXED: Use specific domains instead of wildcard "https:"
        // Allows data URIs and blobs for charts/images, but restricts external images to whitelist
        imgSrc: [
          "'self'",
          "data:",
          "blob:",
          process.env.CLOUDFRONT_DOMAIN,
          "https://fonts.gstatic.com",
          "https://fonts.googleapis.com"
        ].filter(Boolean),
        scriptSrc: ["'self'"],
        // Note: If inline scripts are required, add nonces instead of unsafe-inline
        // scriptSrc: ["'self'", `'nonce-${nonce}'`]
        // SECURITY FIX #7: Use specific domains instead of wildcard patterns
        // Replace wildcard patterns (https:*, wss:*, https://d*.cloudfront.net, etc) with explicit domains
        connectSrc: [
          "'self'",
          process.env.API_GATEWAY_URL,
          process.env.CLOUDFRONT_DOMAIN,
          "https://cognito-idp.us-east-1.amazonaws.com", // Cognito auth endpoint
        ].filter(Boolean),
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
      "screen-wake-lock=(), gyroscope=(), magnetometer=()"
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

// CORS configuration - FIXED: Use exact domain matching only, no wildcard patterns
// (OPTIONS handler removed - cors() middleware handles preflight)
app.use(
  cors({
    origin: (origin, callback) => {
      // Server-to-server and same-origin requests have no Origin header — allow them.
      // Note: Lambda-to-Lambda and ECS task calls won't have an Origin header.
      // The "null" string origin (from sandboxed iframes) is intentionally blocked.
      if (!origin || origin === 'null') {
        // Allow only if not a browser preflight — browser preflights always send Origin.
        // Plain server-side calls have no origin at all (undefined/null JS value, not string "null").
        if (origin === 'null') {
          console.warn("CORS blocked 'null' origin (sandboxed iframe attempt)");
          return callback(new Error("Not allowed by CORS"));
        }
        return callback(null, true);
      }

      // In test environment, allow additional test domains for CORS testing
      const isTestEnv = process.env.NODE_ENV === "test";

      // FIXED: Tighten CORS configuration - production safe
      const isProduction = process.env.NODE_ENV === "production";
      const baseAllowedOrigins = [
        // CloudFront & AWS Endpoints - must be set via environment variables
        process.env.CLOUDFRONT_DOMAIN,
        process.env.API_GATEWAY_URL,

        // Custom frontend URL from environment
        process.env.FRONTEND_URL,
      ].filter(Boolean); // Remove undefined/null values

      // Local development ONLY - NEVER in production
      // In dev, allow ANY localhost origin (flexible port handling for Vite dev server)
      const isLocalhost = origin && (origin.startsWith('http://localhost:') || origin.startsWith('http://127.0.0.1:'));
      if (!isProduction && isLocalhost) {
        return callback(null, origin);
      }

      // Test-only origins for CORS testing (test environment only)
      const testOnlyOrigins = isTestEnv ? [
        // Placeholder for test environment additional origins
      ] : [];

      // Combine origins based on environment
      const finalAllowedOrigins = [...baseAllowedOrigins, ...testOnlyOrigins];

      // FIXED: Use exact matching only - no substring patterns like .includes()
      if (finalAllowedOrigins.includes(origin)) {
        callback(null, origin);
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

// Request parsing — 1MB limit prevents large-payload DoS
app.use(express.json({ limit: "1mb" }));
app.use(express.urlencoded({ extended: true, limit: "1mb" }));

// Note: CSRF protection not needed — all endpoints use Bearer token authentication,
// which is immune to CSRF attacks (tokens are not sent automatically by browsers).

// Response normalizer - ensures all responses follow standard format
app.use(responseNormalizer);

// JSON parsing error handler
app.use((error, req, res, next) => {
  if (error instanceof SyntaxError && error.status === 400 && "body" in error) {
    return sendError(res, "Invalid JSON format", 400);
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

// Comprehensive audit logging middleware - logs all requests for compliance
app.use(auditLogger);

// Request/response logging middleware for debugging all API calls
app.use(requestLogger);

// DISABLED: No caching for finance data - must always be fresh
// app.use(cacheMiddleware(5 * 60 * 1000));
// Finance sites MUST NOT serve stale data

// Global database initialization promise
let dbInitPromise = null;
let __dbAvailable = false;

// Initialize database connection with shorter timeout
const ensureDatabase = async () => {
  if (!dbInitPromise) {
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
      .then(async (pool) => {
        __dbAvailable = true;
        if (process.env.NODE_ENV !== 'test') {
        }
        // Initialize schema (materialized views, etc) after connection is established
        try {
          await initializeSchema();
        } catch (err) {
          console.warn("Schema initialization warning (non-critical):", err.message);
          // Don't fail - schema initialization is non-critical
        }
        // Preload market cache for MAX(date) optimization
        try {
          await marketCache.preload();
        } catch (err) {
          console.warn("Market cache preload warning (non-critical):", err.message);
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
  }

  // Endpoints that don't require database
  const nonDbEndpoints = ["/", "/api/health"];

  if (nonDbEndpoints.includes(req.path)) {
    return next();
  }

  // For endpoints that need database, try to ensure connection with timeout
  try {
    // Use longer timeout for database initialization (60 seconds max to allow schema creation)
    await Promise.race([
      ensureDatabase(),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("DB init timeout")), 60000)
      )
    ]);
    if (process.env.NODE_ENV !== 'test') {
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
    const errorDetails = {
      message: "The database is currently unavailable. Please try again later."
    };
    if (!isProduction) {
      errorDetails.debug = {
        config: error.config,
        env: error.env,
      };
    }
    return sendError(res, "Service temporarily unavailable - database connection failed", 503, errorDetails);
  }
});

// API routes use standard Express response methods - see RULES.md for response pattern

// Root-level health check alias (AWS ALB / CI expect /health without /api prefix)
app.use("/health", healthRoutes);

// Canonical API Routes - all under /api prefix
app.use("/api/audit", auditRoutes);
app.use("/api/commodities", cacheMiddleware(60), commoditiesRoutes);
app.use("/api/diagnostics", diagnosticsRoutes);
app.use("/api/economic", cacheMiddleware(120), economicRoutes);
app.use("/api/health", healthRoutes);
app.use("/api/industries", cacheMiddleware(120), industriesRoutes);
app.use("/api/market", cacheMiddleware(60), marketRoutes);
app.use("/api/optimization", optimizationRoutes);
app.use("/api/scores", cacheMiddleware(120), scoresRoutes);
app.use("/api/sectors", cacheMiddleware(60), sectorsRoutes);
app.use("/api/sentiment", cacheMiddleware(120), sentimentRoutes);
// STANDALONE signals search endpoint - FULL FILTERING SUPPORT with aggressive caching for AWS stability
app.get("/api/signals/search", authenticateToken, cacheMiddleware(60), async (req, res) => {
  try {
    const {
      type = 'swing',
      timeframe = 'daily',
      dataType = 'stocks',
      symbol,
      signal,
      base_type,
      limit = 50,  // Reduce default limit from 100 to 50 for faster queries on AWS
      page = 1,
      days = '365', // Default to 1 year instead of 10 years to prevent timeout
      min_price,
      max_price,
      min_volume,
      max_volume,
      min_rsi,
      max_rsi,
      min_adx,
      sort = 'date',
      sort_order = 'DESC'
    } = req.query;

    const safeLimit = Math.min(parseInt(limit) || 100, 50000);
    const safePage = Math.max(1, parseInt(page) || 1);
    const offset = (safePage - 1) * safeLimit;

    // Validate dataType
    if (!['stocks', 'etf'].includes(dataType)) {
      return sendError(res, "Invalid dataType. Must be 'stocks' or 'etf'", 400);
    }

    // Map type and timeframe to table (with support for both stocks and ETFs)
    let tableName;
    const etfSuffix = dataType === 'etf' ? '_etf' : '';

    if (type === 'swing') {
      const timeframeMap = {
        daily: `buy_sell_daily${etfSuffix}`,
        weekly: `buy_sell_weekly${etfSuffix}`,
        monthly: `buy_sell_monthly${etfSuffix}`
      };
      tableName = timeframeMap[timeframe] || `buy_sell_daily${etfSuffix}`;
    } else if (type === 'range') {
      tableName = `range_signals_daily${etfSuffix}`;
    } else if (type === 'mean-reversion') {
      tableName = `mean_reversion_signals_daily${etfSuffix}`;
    } else {
      return sendError(res, 'Invalid type', 400);
    }

    // Build WHERE clause with ALL filters
    const whereConditions = [];
    const params = [];
    let paramIndex = 1;

    // Date filter
    const dayRange = parseInt(days) || 3650;
    if (dayRange > 0) {
      whereConditions.push(`date >= CURRENT_DATE - MAKE_INTERVAL(days => $${paramIndex})`);
      params.push(dayRange);
      paramIndex++;
    }

    // Always filter to BUY/SELL
    whereConditions.push(`UPPER(signal) IN ('BUY', 'SELL')`);

    // Signal type filter (overrides the above if specified)
    if (signal) {
      whereConditions.pop(); // Remove generic BUY/SELL filter
      whereConditions.push(`UPPER(signal) = $${paramIndex}`);
      params.push(signal.toUpperCase());
      paramIndex++;
    }

    // Symbol filter
    if (symbol) {
      whereConditions.push(`symbol = $${paramIndex}`);
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // Base type filter
    if (base_type) {
      whereConditions.push(`base_type = $${paramIndex}`);
      params.push(base_type);
      paramIndex++;
    }

    // Price filters
    if (min_price) {
      whereConditions.push(`close >= $${paramIndex}`);
      params.push(parseFloat(min_price));
      paramIndex++;
    }
    if (max_price) {
      whereConditions.push(`close <= $${paramIndex}`);
      params.push(parseFloat(max_price));
      paramIndex++;
    }

    // Volume filters
    if (min_volume) {
      whereConditions.push(`volume >= $${paramIndex}`);
      params.push(parseInt(min_volume));
      paramIndex++;
    }
    if (max_volume) {
      whereConditions.push(`volume <= $${paramIndex}`);
      params.push(parseInt(max_volume));
      paramIndex++;
    }

    // Technical filters
    if (min_rsi) {
      whereConditions.push(`rsi >= $${paramIndex}`);
      params.push(parseFloat(min_rsi));
      paramIndex++;
    }
    if (max_rsi) {
      whereConditions.push(`rsi <= $${paramIndex}`);
      params.push(parseFloat(max_rsi));
      paramIndex++;
    }
    if (min_adx) {
      whereConditions.push(`adx >= $${paramIndex}`);
      params.push(parseFloat(min_adx));
      paramIndex++;
    }

    const whereClause = whereConditions.length > 0 ? `WHERE ${whereConditions.join(' AND ')}` : '';

    // Sorting
    const validSortFields = ['date', 'symbol', 'close', 'volume'];
    const sortField = validSortFields.includes(sort) ? sort : 'date';
    const sortDir = ['ASC', 'DESC'].includes(sort_order.toUpperCase()) ? sort_order.toUpperCase() : 'DESC';
    const orderBy = `ORDER BY ${sortField} ${sortDir}`;

    // Data query - select only needed columns for performance
    // For large result sets, use LIMIT to prevent table scans
    const columns = [
      'id', 'symbol', 'date', 'signal', 'timeframe', 'open', 'high', 'low', 'close', 'volume',
      'rsi', 'adx', 'buylevel', 'stoplevel', 'signal_strength', 'base_type', 'base_length_days',
      'breakout_quality', 'market_stage', 'entry_quality_score', 'profit_target_20pct',
      'profit_target_25pct', 'atr', 'mansfield_rs', 'buy_zone_start', 'buy_zone_end',
      'risk_reward_ratio', 'avg_volume_50d', 'volume_surge_pct', 'rs_rating'
    ].join(',');

    // More aggressive limit for AWS to prevent 504 timeouts - scan max 2000 rows
    const maxRowsToScan = 2000;
    const maxRows = Math.min(safeLimit + 1, maxRowsToScan);
    params.push(maxRows, offset);
    const dataQuery = `SELECT ${columns} FROM ${tableName} ${whereClause} ${orderBy} LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`;

    let dataResult;
    try {
      // Execute query with reasonable timeout
      dataResult = await query(dataQuery, params);
    } catch (err) {
      // If query fails with timeout, return graceful response instead of crashing
      console.warn(`Query failed: ${err.message}`);
      return sendSuccess(res, {
        items: [],
        pagination: {
          limit: safeLimit,
          offset,
          total: 0,
          page: safePage,
          totalPages: 0,
          hasNext: false,
          hasPrev: false
        },
        note: 'Query timeout on large dataset. Try with more specific filters (symbol, date range, or signal type).'
      });
    }

    // Check if there are more results
    const hasMore = dataResult.rows.length > safeLimit;
    const items = hasMore ? dataResult.rows.slice(0, safeLimit) : dataResult.rows;

    // For total count, use approximate count from table stats if filtering is minimal
    let total = 0;
    if (whereConditions.length <= 2) {
      // Use table statistics for approximate count (much faster)
      const statsQuery = `SELECT n_live_tup::bigint as approx_total FROM pg_stat_user_tables WHERE relname = $1`;
      try {
        const statsResult = await query(statsQuery, [tableName]);
        total = parseInt(statsResult.rows[0]?.approx_total || 0);
      } catch (e) {
        total = offset + items.length + (hasMore ? 1 : 0);
      }
    } else {
      // For complex filters, approximate based on what we fetched
      total = offset + items.length + (hasMore ? Math.max(100, safeLimit * 10) : 0);
    }

    return sendSuccess(res, {
      items,
      pagination: {
        limit: safeLimit,
        offset,
        total,
        page: safePage,
        totalPages: Math.ceil(total / safeLimit),
        hasNext: hasMore,
        hasPrev: safePage > 1
      }
    });
  } catch (error) {
    console.error('Signals search error:', error);
    return sendError(res, error.message, 500);
  }
});
// Cache signals endpoint: 15 second TTL (short cache for data freshness)
app.use("/api/signals", cacheMiddleware(15), signalsRoutes);
app.use("/api/strategies", cacheMiddleware(120), strategiesRoutes);
app.use("/api/trades/manual", manualTradesRoutes);  // Mount more specific route first
app.use("/api/trades", cacheMiddleware(90), tradesRoutes);

// Research and backtest routes
app.use("/api/research/backtests", cacheMiddleware(120), backtestsRoutes);
app.use("/api/backtests", cacheMiddleware(120), backtestsRoutes);  // alias for frontend compatibility

// Status and performance routes
app.use("/api/status", cacheMiddleware(30), statusRoutes);
app.use("/api/performance", cacheMiddleware(30), performanceRoutes);

// Swing trading algo routes
app.use("/api/algo", require("./routes/algo"));

// Stock market data routes
app.use("/api/stocks", cacheMiddleware(60), require("./routes/stocks"));
app.use("/api/prices", cacheMiddleware(60), require("./routes/prices"));
app.use("/api/financials", cacheMiddleware(120), require("./routes/financials"));
app.use("/api/earnings", cacheMiddleware(60), require("./routes/earnings"));

// SECURITY FIX #1: Apply authenticateToken BEFORE cacheMiddleware on /api/trades
// to prevent cache bypass of authentication checks (cache must not bypass auth)
app.use("/api/trades", authenticateToken);

// Authentication routes
app.use("/api/logout", logoutRoutes);

// API info endpoint
app.get("/api", (req, res) => {
  return sendSuccess(res, {
    name: "Financial Dashboard API",
    version: "2.0.0",
    status: "operational",
    endpoints: {
      algo: "/api/algo",
      economic: "/api/economic",
      health: "/api/health",
      logout: "/api/logout",
      market: "/api/market",
      sectors: "/api/sectors",
      signals: "/api/signals",
      trades: "/api/trades"
    }
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


// Error handling middleware (should be last)
app.use(errorHandler);

// 404 handler for all unmatched routes
app.all('*', (req, res) => {
  return sendError(res, `Endpoint ${req.originalUrl} does not exist (API only, no web UI)`, 404);
});

// AWS Lambda / EC2 handler - listen directly on existing server (supports both HTTP and WebSocket)
const PORT = process.env.PORT || 3001;

// Detect Lambda environment - don't call server.listen() in Lambda (serverless-http handles it)
const isLambdaEnvironment = !!process.env.LAMBDA_TASK_ROOT || !!process.env.AWS_LAMBDA_FUNCTION_NAME;

if (!isLambdaEnvironment) {
  // Local development or EC2 - start HTTP server
  server.listen(PORT, '::', () => {
    console.log(`Financial Dashboard API running on port ${PORT}`);

    // Initialize Alpaca portfolio sync scheduler
    // Syncs every 10 minutes automatically
    initializeAlpacaSync();
  });
} else {
  // AWS Lambda environment - serverless-http wrapper handles HTTP request routing
}

// Handle graceful shutdown
process.on('SIGTERM', () => {
  server.close(() => {
    // eslint-disable-next-line no-process-exit
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  server.close(() => {
    // eslint-disable-next-line no-process-exit
    process.exit(0);
  });
});

// Export app for testing/importing
module.exports = app;

// AWS Lambda handler - CRITICAL FOR LAMBDA TO WORK
// This MUST be exported for Lambda to find the handler function
module.exports.handler = serverlessHttp(app);



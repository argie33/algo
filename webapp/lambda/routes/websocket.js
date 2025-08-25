const express = require("express");

// eslint-disable-next-line import/order
const { success, error } = require("../utils/responseFormatter");

// Import dependencies with error handling
const { authenticateToken } = require("../middleware/auth");
let apiKeyService, AlpacaService, validationMiddleware;
try {
  apiKeyService = require("../utils/apiKeyService");
  AlpacaService = require("../utils/alpacaService");
  const validation = require("../middleware/validation");
  validationMiddleware = validation.createValidationMiddleware;
} catch (loadError) {
  console.warn("Some websocket dependencies not available:", loadError.message);
}

const router = express.Router();

// Debug test endpoint
router.get("/test", (req, res) => {
  res.json({
    status: "websocket route is working",
    timestamp: new Date().toISOString(),
  });
});

// Simple error response helper
const createErrorResponse = (message, details = {}) => ({
  success: false,
  error: message,
  ...details,
  timestamp: new Date().toISOString(),
});

// Basic health endpoint for websocket service
router.get("/health", (req, res) => {
  try {
    // Check if responseFormatter is available
    if (typeof success !== "function") {
      return res.json({
        success: true,
        status: "operational",
        service: "websocket",
        timestamp: new Date().toISOString(),
        message: "WebSocket service is running (fallback response)",
        type: "http_polling_realtime_data",
        dependencies: {
          responseFormatter: false,
          apiKeyService: !!apiKeyService,
          alpacaService: !!AlpacaService,
          validationMiddleware: !!validationMiddleware,
        },
      });
    }

    const response = success({
      status: "operational",
      service: "websocket",
      timestamp: new Date().toISOString(),
      message: "WebSocket service is running",
      type: "http_polling_realtime_data",
      dependencies: {
        responseFormatter: true,
        apiKeyService: !!apiKeyService,
        alpacaService: !!AlpacaService,
        validationMiddleware: !!validationMiddleware,
      },
    });
    res.status(response.statusCode).json(response.response);
  } catch (healthError) {
    console.error("WebSocket health check error:", healthError);
    res.status(500).json({
      success: false,
      error: "Health check failed",
      message: healthError.message,
      stack: healthError.stack,
      timestamp: new Date().toISOString(),
    });
  }
});

// Basic status endpoint
router.get("/status", (req, res) => {
  try {
    const response = success({
      activeUsers: 0,
      cachedSymbols: 0,
      service: "websocket",
      serverTime: new Date().toISOString(),
      uptime: process.uptime(),
      dependencies: {
        apiKeyService: !!apiKeyService,
        alpacaService: !!AlpacaService,
        validationMiddleware: !!validationMiddleware,
      },
    });
    res.status(response.statusCode).json(response.response);
  } catch (statusError) {
    console.error("WebSocket status check error:", statusError);
    res.status(500).json({
      success: false,
      error: "Status check failed",
      message: statusError.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Validation schemas for websocket endpoints
const _websocketValidationSchemas = {
  stream: {
    symbols: {
      required: true,
      type: "string",
      sanitizer: (value) => {
        if (typeof value !== "string") return "";
        // Split by comma, clean each symbol, and rejoin
        return value
          .split(",")
          .map((s) =>
            s
              .trim()
              .toUpperCase()
              .replace(/[^A-Z0-9]/g, "")
          )
          .filter((s) => s.length > 0)
          .slice(0, 20) // Limit to 20 symbols max for real-time
          .join(",");
      },
      validator: (value) => {
        if (!value) return false;
        const symbols = value.split(",");
        return (
          symbols.length > 0 &&
          symbols.length <= 20 &&
          symbols.every((s) => /^[A-Z]{1,10}$/.test(s.trim()))
        );
      },
      errorMessage:
        "Symbols must be a comma-separated list of 1-20 valid stock symbols",
    },
  },
};

// Real-time data endpoints for authenticated Alpaca data
// Simplified approach using HTTP polling instead of WebSocket for Lambda compatibility

// In-memory cache for real-time data (Lambda-friendly)
const realtimeDataCache = new Map();
const userSubscriptions = new Map(); // userId -> Set of symbols
const lastUpdateTime = new Map(); // symbol -> timestamp

// Cache TTL in milliseconds
const CACHE_TTL = 30000; // 30 seconds
const UPDATE_INTERVAL = 5000; // 5 seconds

/**
 * Get real-time market data for subscribed symbols with comprehensive authentication logging
 * This endpoint replaces WebSocket functionality with HTTP polling for Lambda compatibility
 */
router.get("/stream/:symbols", authenticateToken, async (req, res) => {
  const requestId = require("crypto").randomUUID().split("-")[0];
  const requestStart = Date.now();

  try {
    const userId = req.user.sub;

    console.log(`🚀 [${requestId}] Live data stream request initiated`, {
      symbols: req.params.symbols,
      userId: userId ? `${userId.substring(0, 8)}...` : "undefined",
      userAgent: req.headers["user-agent"],
      ip: req.ip,
      timestamp: new Date().toISOString(),
    });

    // Parse and validate symbols
    console.log(
      `🔍 [${requestId}] Parsing requested symbols: ${req.params.symbols}`
    );
    const symbols = req.params.symbols
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter((s) => s.length > 0 && s.length <= 10 && /^[A-Z]+$/.test(s));

    if (symbols.length === 0) {
      console.error(`❌ [${requestId}] Invalid symbols provided:`, {
        originalSymbols: req.params.symbols,
        filteredSymbols: symbols,
        impact: "No valid symbols to stream",
      });
      return res.status(400).json(
        error("No valid symbols provided", 400, {
          requestId,
          timestamp: new Date().toISOString(),
        }).response
      );
    }

    console.log(`✅ [${requestId}] Symbols validated:`, {
      validSymbols: symbols,
      symbolCount: symbols.length,
    });

    // Get user's Alpaca credentials with comprehensive error handling
    console.log(
      `🔑 [${requestId}] Retrieving user API credentials for live data access`
    );
    const credentialsStart = Date.now();

    let credentials;
    try {
      credentials = await apiKeyService.getDecryptedApiKey(userId, "alpaca");
      const credentialsDuration = Date.now() - credentialsStart;

      if (!credentials) {
        console.error(
          `❌ [${requestId}] No API credentials found after ${credentialsDuration}ms`,
          {
            requestedProvider: "alpaca",
            userId: `${userId.substring(0, 8)}...`,
            impact: "Live market data will not be available",
            recommendation:
              "User needs to configure Alpaca API keys in settings",
          }
        );

        return res.status(400).json({
          success: false,
          error: "API credentials not configured",
          message:
            "Please configure your Alpaca API keys in Settings to access live market data",
          error_code: "API_CREDENTIALS_MISSING",
          provider: "alpaca",
          actions: [
            "Go to Settings > API Keys",
            "Add your Alpaca API credentials",
            "Choose the correct environment (Paper Trading or Live Trading)",
            "Test the connection to verify your credentials",
          ],
          request_info: {
            request_id: requestId,
            timestamp: new Date().toISOString(),
          },
        });
      }

      console.log(
        `✅ [${requestId}] API credentials retrieved in ${credentialsDuration}ms`,
        {
          provider: "alpaca",
          environment: credentials.isSandbox ? "sandbox" : "live",
          keyLength: credentials.apiKey ? credentials.apiKey.length : 0,
          hasSecret: !!credentials.apiSecret,
        }
      );
    } catch (credentialsError) {
      const credentialsDuration = Date.now() - credentialsStart;
      console.error(
        `❌ [${requestId}] Failed to retrieve API credentials after ${credentialsDuration}ms:`,
        {
          error: credentialsError.message,
          errorStack: credentialsError.stack,
          provider: "alpaca",
          impact: "Cannot access live market data",
          recommendation:
            "Check API key configuration and database connectivity",
        }
      );

      return res.status(500).json({
        success: false,
        error: "Failed to retrieve API credentials",
        message:
          "There was an error accessing your API credentials. Please try again or contact support.",
        error_code: "API_CREDENTIALS_ERROR",
        details:
          process.env.NODE_ENV === "development"
            ? credentialsError.message
            : "Internal error",
        request_info: {
          request_id: requestId,
          error_duration_ms: credentialsDuration,
          timestamp: new Date().toISOString(),
        },
      });
    }

    // Initialize Alpaca service for this user with comprehensive error handling
    console.log(`🏭 [${requestId}] Initializing Alpaca service for live data`);
    const alpacaInitStart = Date.now();
    let userAlpacaService;

    try {
      userAlpacaService = new AlpacaService(
        credentials.apiKey,
        credentials.apiSecret,
        credentials.isSandbox
      );
      const alpacaInitDuration = Date.now() - alpacaInitStart;

      console.log(
        `✅ [${requestId}] Alpaca service initialized in ${alpacaInitDuration}ms`,
        {
          environment: credentials.isSandbox ? "sandbox" : "live",
          hasApiKey: !!credentials.apiKey,
          hasSecret: !!credentials.apiSecret,
        }
      );
    } catch (alpacaError) {
      const alpacaInitDuration = Date.now() - alpacaInitStart;
      console.error(
        `❌ [${requestId}] Alpaca service initialization FAILED after ${alpacaInitDuration}ms:`,
        {
          error: alpacaError.message,
          errorStack: alpacaError.stack,
          environment: credentials.isSandbox ? "sandbox" : "live",
          impact: "Cannot initialize live data service",
          recommendation: "Check API key validity and Alpaca service status",
        }
      );

      return res.status(500).json({
        success: false,
        error: "Failed to initialize live data service",
        message:
          "Unable to connect to your broker for live data. Please verify your API credentials or try again later.",
        error_code: "LIVE_DATA_SERVICE_INIT_ERROR",
        details:
          process.env.NODE_ENV === "development"
            ? alpacaError.message
            : "Service initialization failed",
        provider: "alpaca",
        environment: credentials.isSandbox ? "sandbox" : "live",
        actions: [
          "Verify your API credentials are correct",
          "Check if your API keys have market data permissions",
          "Try switching between Paper Trading and Live Trading modes",
          "Contact broker support if the issue persists",
        ],
        request_info: {
          request_id: requestId,
          error_duration_ms: alpacaInitDuration,
          timestamp: new Date().toISOString(),
        },
      });
    }

    // Update user subscriptions with logging
    console.log(`📝 [${requestId}] Updating user subscriptions`, {
      previousSubscriptions: Array.from(userSubscriptions.get(userId) || []),
      newSubscriptions: symbols,
    });
    userSubscriptions.set(userId, new Set(symbols));

    // Get latest quotes for requested symbols with comprehensive error handling
    console.log(
      `📊 [${requestId}] Fetching market data for ${symbols.length} symbols`
    );
    const marketData = {};
    const now = Date.now();
    const dataFetchStart = Date.now();

    let successfulFetches = 0;
    let cachedSymbols = 0;
    let failedSymbols = 0;

    for (const symbol of symbols) {
      const symbolFetchStart = Date.now();
      try {
        console.log(`📊 [${requestId}] Processing symbol: ${symbol}`);

        // Check if we have fresh cached data
        const cacheKey = `quote:${symbol}`;
        const cachedData = realtimeDataCache.get(cacheKey);
        const lastUpdate = lastUpdateTime.get(symbol) || 0;
        const dataAge = now - lastUpdate;

        if (cachedData && dataAge < CACHE_TTL) {
          marketData[symbol] = {
            ...cachedData,
            cached: true,
            age: dataAge,
          };
          cachedSymbols++;
          console.log(`📋 [${requestId}] Using cached data for ${symbol}`, {
            age: `${dataAge}ms`,
            ttl: `${CACHE_TTL}ms`,
          });
        } else {
          // Fetch fresh data from Alpaca with timeout protection
          console.log(
            `📡 [${requestId}] Fetching fresh data for ${symbol} from Alpaca`
          );
          const alpacaFetchStart = Date.now();

          const quote = await Promise.race([
            userAlpacaService.getLatestQuote(symbol),
            new Promise((_, reject) =>
              setTimeout(
                () =>
                  reject(
                    new Error(
                      `Quote fetch timeout for ${symbol} after 8 seconds`
                    )
                  ),
                8000
              )
            ),
          ]);

          const alpacaFetchDuration = Date.now() - alpacaFetchStart;

          if (quote) {
            const formattedQuote = {
              symbol: symbol,
              bidPrice: quote.bidPrice,
              askPrice: quote.askPrice,
              bidSize: quote.bidSize,
              askSize: quote.askSize,
              timestamp: quote.timestamp || now,
              cached: false,
              age: 0,
              fetchTime: alpacaFetchDuration,
            };

            // Cache the data
            realtimeDataCache.set(cacheKey, formattedQuote);
            lastUpdateTime.set(symbol, now);
            marketData[symbol] = formattedQuote;
            successfulFetches++;

            console.log(
              `✅ [${requestId}] Fresh data fetched for ${symbol} in ${alpacaFetchDuration}ms`,
              {
                bidPrice: quote.bidPrice,
                askPrice: quote.askPrice,
                spread: quote.askPrice - quote.bidPrice,
              }
            );
          } else {
            console.warn(
              `⚠️ [${requestId}] No quote data returned for ${symbol}`
            );
            marketData[symbol] = {
              symbol: symbol,
              error: "Quote data unavailable",
              timestamp: now,
              cached: false,
            };
            failedSymbols++;
          }
        }

        const symbolDuration = Date.now() - symbolFetchStart;
        console.log(
          `✅ [${requestId}] Symbol ${symbol} processed in ${symbolDuration}ms`
        );
      } catch (error) {
        const symbolDuration = Date.now() - symbolFetchStart;
        console.error(
          `❌ [${requestId}] Failed to get quote for ${symbol} after ${symbolDuration}ms:`,
          {
            error: error.message,
            errorStack: error.stack,
            errorCode: error.code,
            statusCode: error.status,
            impact: "Symbol will show error status",
          }
        );

        // Determine error type for better user messaging
        let errorMessage = "Quote unavailable";
        let errorCode = "QUOTE_ERROR";

        if (error.message?.includes("timeout")) {
          errorMessage = "Request timeout";
          errorCode = "QUOTE_TIMEOUT";
        } else if (
          error.status === 401 ||
          error.message?.includes("unauthorized")
        ) {
          errorMessage = "API credentials invalid";
          errorCode = "QUOTE_UNAUTHORIZED";
        } else if (
          error.status === 403 ||
          error.message?.includes("forbidden")
        ) {
          errorMessage = "Insufficient permissions";
          errorCode = "QUOTE_FORBIDDEN";
        } else if (
          error.status === 429 ||
          error.message?.includes("rate limit")
        ) {
          errorMessage = "Rate limit exceeded";
          errorCode = "QUOTE_RATE_LIMITED";
        }

        marketData[symbol] = {
          symbol: symbol,
          error: errorMessage,
          error_code: errorCode,
          errorMessage: error.message,
          timestamp: now,
          cached: false,
        };
        failedSymbols++;
      }
    }

    const dataFetchDuration = Date.now() - dataFetchStart;
    const totalDuration = Date.now() - requestStart;

    console.log(
      `✅ [${requestId}] Live data stream completed in ${totalDuration}ms`,
      {
        summary: {
          totalSymbols: symbols.length,
          successfulFetches,
          cachedSymbols,
          failedSymbols,
          successRate: `${Math.round(((successfulFetches + cachedSymbols) / symbols.length) * 100)}%`,
        },
        performance: {
          totalDuration: `${totalDuration}ms`,
          dataFetchDuration: `${dataFetchDuration}ms`,
          avgPerSymbol: `${Math.round(dataFetchDuration / symbols.length)}ms`,
        },
        cache: {
          totalCachedSymbols: realtimeDataCache.size,
          hitRate: `${Math.round((cachedSymbols / symbols.length) * 100)}%`,
        },
        status: "SUCCESS",
      }
    );

    const responseData = {
      symbols: symbols,
      data: marketData,
      updateInterval: UPDATE_INTERVAL,
      cacheStatus: {
        totalCachedSymbols: realtimeDataCache.size,
        userSubscriptions: Array.from(userSubscriptions.get(userId) || []),
        cacheHitRate: Math.round((cachedSymbols / symbols.length) * 100),
        cacheTTL: CACHE_TTL,
      },
      statistics: {
        successful: successfulFetches,
        cached: cachedSymbols,
        failed: failedSymbols,
        total: symbols.length,
      },
      request_info: {
        request_id: requestId,
        total_duration_ms: totalDuration,
        data_fetch_duration_ms: dataFetchDuration,
        timestamp: new Date().toISOString(),
      },
    };

    const response = success(responseData);
    res.status(response.statusCode).json(response.response);
  } catch (streamError) {
    const errorDuration = Date.now() - requestStart;
    console.error(
      `❌ [${requestId}] Live data stream FAILED after ${errorDuration}ms:`,
      {
        error: streamError.message,
        errorStack: streamError.stack,
        errorCode: streamError.code,
        symbols: req.params.symbols,
        impact: "Live data stream request failed completely",
        recommendation:
          "Check authentication, API credentials, and Alpaca service status",
      }
    );

    res.status(500).json(
      createErrorResponse("Failed to stream market data", {
        requestId,
        error_duration_ms: errorDuration,
        details:
          process.env.NODE_ENV === "development"
            ? streamError.message
            : "Internal server error",
      })
    );
  }
});

/**
 * Get latest trade data for symbols
 */
router.get("/trades/:symbols", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;

    // Parse symbols
    const symbols = req.params.symbols
      .split(",")
      .map((s) => s.trim().toUpperCase());

    // Get user's Alpaca credentials
    const credentials = await apiKeyService.getDecryptedApiKey(
      userId,
      "alpaca"
    );
    if (!credentials) {
      return res
        .status(403)
        .json(createErrorResponse("No Alpaca API key configured"));
    }

    // Initialize Alpaca service
    const userAlpacaService = new AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      credentials.isSandbox
    );

    // Get latest trades
    const tradeData = {};
    for (const symbol of symbols) {
      try {
        const trade = await userAlpacaService.getLatestTrade(symbol);
        tradeData[symbol] = trade
          ? {
              symbol: symbol,
              price: trade.price,
              size: trade.size,
              timestamp: trade.timestamp,
              conditions: trade.conditions,
            }
          : { symbol: symbol, error: "Trade data unavailable" };
      } catch (error) {
        tradeData[symbol] = { symbol: symbol, error: error.message };
      }
    }

    const response = success(tradeData);
    res.status(response.statusCode).json(response.response);
  } catch (error) {
    console.error("Trades endpoint error:", error);
    res.status(500).json(createErrorResponse("Failed to get trade data"));
  }
});

/**
 * Get bars/OHLCV data for symbols
 */
router.get("/bars/:symbols", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;

    // Parse symbols and timeframe
    const symbols = req.params.symbols
      .split(",")
      .map((s) => s.trim().toUpperCase());
    const timeframe = req.query.timeframe || "1Min";

    // Get user's Alpaca credentials
    const credentials = await apiKeyService.getDecryptedApiKey(
      userId,
      "alpaca"
    );
    if (!credentials) {
      return res
        .status(403)
        .json(createErrorResponse("No Alpaca API key configured"));
    }

    // Initialize Alpaca service
    const userAlpacaService = new AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      credentials.isSandbox
    );

    // Get bars data
    const barsData = {};
    for (const symbol of symbols) {
      try {
        const bars = await userAlpacaService.getBars(symbol, {
          timeframe: timeframe,
          start: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(), // Last 24 hours
          limit: 100,
        });
        barsData[symbol] = bars || {
          symbol: symbol,
          error: "Bars data unavailable",
        };
      } catch (error) {
        barsData[symbol] = { symbol: symbol, error: error.message };
      }
    }

    const response = success(barsData);
    res.status(response.statusCode).json(response.response);
  } catch (error) {
    console.error("Bars endpoint error:", error);
    res.status(500).json(createErrorResponse("Failed to get bars data"));
  }
});

/**
 * Subscribe to symbols (for tracking user interest)
 */
router.post("/subscribe", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;

    const { symbols, dataTypes } = req.body;

    if (!symbols || !Array.isArray(symbols)) {
      return res.status(400).json(createErrorResponse("Invalid symbols array"));
    }

    // Update user subscriptions
    const userSymbols = symbols.map((s) => s.toUpperCase());
    userSubscriptions.set(userId, new Set(userSymbols));

    const response = success({
      subscribed: userSymbols,
      dataTypes: dataTypes || ["quotes"],
      message: `Subscribed to ${userSymbols.length} symbols`,
      streamEndpoints: {
        quotes: `/api/websocket/stream/${userSymbols.join(",")}`,
        trades: `/api/websocket/trades/${userSymbols.join(",")}`,
        bars: `/api/websocket/bars/${userSymbols.join(",")}`,
      },
    });
    res.status(response.statusCode).json(response.response);
  } catch (error) {
    console.error("Subscribe endpoint error:", error);
    res.status(500).json(createErrorResponse("Failed to subscribe"));
  }
});

/**
 * Get user's current subscriptions
 */
router.get("/subscriptions", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;

    const subscriptions = Array.from(userSubscriptions.get(userId) || []);

    const response = success({
      symbols: subscriptions,
      count: subscriptions.length,
      streamEndpoints:
        subscriptions.length > 0
          ? {
              quotes: `/api/websocket/stream/${subscriptions.join(",")}`,
              trades: `/api/websocket/trades/${subscriptions.join(",")}`,
              bars: `/api/websocket/bars/${subscriptions.join(",")}`,
            }
          : null,
    });
    res.status(response.statusCode).json(response.response);
  } catch (error) {
    console.error("Subscriptions endpoint error:", error);
    res.status(500).json(createErrorResponse("Failed to get subscriptions"));
  }
});

/**
 * Unsubscribe from symbols
 */
router.delete("/subscribe", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;

    const { symbols } = req.body;

    if (symbols && Array.isArray(symbols)) {
      // Remove specific symbols
      const userSymbols = userSubscriptions.get(userId) || new Set();
      symbols.forEach((symbol) => userSymbols.delete(symbol.toUpperCase()));
      userSubscriptions.set(userId, userSymbols);
    } else {
      // Remove all subscriptions
      userSubscriptions.delete(userId);
    }

    const response = success({
      message: "Unsubscribed successfully",
      remainingSubscriptions: Array.from(userSubscriptions.get(userId) || []),
    });
    res.status(response.statusCode).json(response.response);
  } catch (error) {
    console.error("Unsubscribe endpoint error:", error);
    res.status(500).json(createErrorResponse("Failed to unsubscribe"));
  }
});

// Health check endpoint (duplicate removed - using earlier endpoint)

// Status endpoint with detailed metrics
router.get("/status", (req, res) => {
  const now = Date.now();
  const cacheDetails = {};

  for (const [key, _value] of realtimeDataCache.entries()) {
    const symbol = key.split(":")[1];
    const lastUpdate = lastUpdateTime.get(symbol) || 0;
    cacheDetails[symbol] = {
      lastUpdate: new Date(lastUpdate).toISOString(),
      age: now - lastUpdate,
      fresh: now - lastUpdate < CACHE_TTL,
    };
  }

  const response = success({
    activeUsers: userSubscriptions.size,
    cachedSymbols: realtimeDataCache.size,
    cacheDetails,
    userSubscriptions: Object.fromEntries(
      Array.from(userSubscriptions.entries()).map(([userId, symbols]) => [
        userId.substring(0, 8) + "...",
        Array.from(symbols),
      ])
    ),
    serverTime: new Date().toISOString(),
    uptime: process.uptime(),
  });
  res.status(response.statusCode).json(response.response);
});

// Cleanup expired cache entries periodically (skip in test environment)
if (process.env.NODE_ENV !== "test") {
  setInterval(() => {
    const now = Date.now();
    const expiredKeys = [];

    for (const [key, _data] of realtimeDataCache.entries()) {
      const symbol = key.split(":")[1];
      const lastUpdate = lastUpdateTime.get(symbol) || 0;

      if (now - lastUpdate > CACHE_TTL * 2) {
        // Double TTL for cleanup
        expiredKeys.push(key);
        lastUpdateTime.delete(symbol);
      }
    }

    expiredKeys.forEach((key) => realtimeDataCache.delete(key));

    if (expiredKeys.length > 0) {
      console.log(`Cleaned up ${expiredKeys.length} expired cache entries`);
    }
  }, CACHE_TTL);
}

module.exports = router;

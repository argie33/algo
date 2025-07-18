const express = require('express');
const { success, error } = require('../utils/responseFormatter');

// Import dependencies with error handling
let jwt, apiKeyService, alpacaService, validationMiddleware;
try {
  jwt = require('aws-jwt-verify');
  apiKeyService = require('../utils/apiKeyServiceResilient');
  alpacaService = require('../utils/alpacaService');
  const validation = require('../middleware/validation');
  validationMiddleware = validation.createValidationMiddleware;
} catch (loadError) {
  console.warn('Some websocket dependencies not available:', loadError.message);
}

const router = express.Router();

// Simple error response helper
const createErrorResponse = (message, details = {}) => ({
  success: false,
  error: message,
  ...details,
  timestamp: new Date().toISOString()
});

// Basic health endpoint for websocket service
router.get('/health', (req, res) => {
  res.json(success({
    status: 'operational',
    service: 'websocket',
    timestamp: new Date().toISOString(),
    message: 'WebSocket service is running',
    type: 'http_polling_realtime_data'
  }));
});

// Basic status endpoint
router.get('/status', (req, res) => {
  res.json(success({
    activeUsers: 0,
    cachedSymbols: 0,
    service: 'websocket',
    serverTime: new Date().toISOString(),
    uptime: process.uptime()
  }));
});

// Validation schemas for websocket endpoints
const websocketValidationSchemas = {
  stream: {
    symbols: {
      required: true,
      type: 'string',
      sanitizer: (value) => {
        if (typeof value !== 'string') return '';
        // Split by comma, clean each symbol, and rejoin
        return value.split(',')
          .map(s => s.trim().toUpperCase().replace(/[^A-Z0-9]/g, ''))
          .filter(s => s.length > 0)
          .slice(0, 20) // Limit to 20 symbols max for real-time
          .join(',');
      },
      validator: (value) => {
        if (!value) return false;
        const symbols = value.split(',');
        return symbols.length > 0 && 
               symbols.length <= 20 && 
               symbols.every(s => /^[A-Z]{1,10}$/.test(s.trim()));
      },
      errorMessage: 'Symbols must be a comma-separated list of 1-20 valid stock symbols'
    }
  }
};

// Real-time data endpoints for authenticated Alpaca data
// WebSocket streaming for true real-time market data

// WebSocket connection management for real-time streaming
const activeConnections = new Map(); // connectionId -> WebSocket
const userSubscriptions = new Map(); // userId -> Set of symbols
const streamingData = new Map(); // symbol -> latest streaming data

// Real-time streaming settings
const STREAM_INTERVAL = 1000; // 1 second for real-time updates
const CONNECTION_TIMEOUT = 30000; // 30 seconds

/**
 * WebSocket connection handler for real-time streaming
 * Establishes and manages WebSocket connections for live market data
 */
router.ws('/stream', (ws, req) => {
  const connectionId = require('crypto').randomUUID();
  const connectionStart = Date.now();
  
  console.log(`🔌 [${connectionId}] WebSocket connection established`);
  
  // Store connection
  activeConnections.set(connectionId, {
    ws,
    userId: null,
    subscriptions: new Set(),
    lastSeen: Date.now(),
    authenticated: false
  });
  
  // Handle messages
  ws.on('message', async (message) => {
    try {
      const data = JSON.parse(message);
      await handleWebSocketMessage(connectionId, data);
    } catch (error) {
      console.error(`❌ [${connectionId}] Message handling error:`, error);
      ws.send(JSON.stringify({
        type: 'error',
        message: 'Invalid message format'
      }));
    }
  });
  
  // Handle connection close
  ws.on('close', () => {
    console.log(`🔌 [${connectionId}] WebSocket connection closed`);
    activeConnections.delete(connectionId);
  });
  
  // Handle errors
  ws.on('error', (error) => {
    console.error(`❌ [${connectionId}] WebSocket error:`, error);
    activeConnections.delete(connectionId);
  });
  
  // Send welcome message
  ws.send(JSON.stringify({
    type: 'connected',
    connectionId,
    timestamp: new Date().toISOString(),
    message: 'WebSocket connection established'
  }));
});

/**
 * Handle WebSocket messages for authentication and subscription management
 */
async function handleWebSocketMessage(connectionId, data) {
  const connection = activeConnections.get(connectionId);
  if (!connection) return;
  
  const { ws } = connection;
  
  switch (data.type) {
    case 'authenticate':
      await handleAuthentication(connectionId, data);
      break;
      
    case 'subscribe':
      await handleSubscription(connectionId, data);
      break;
      
    case 'unsubscribe':
      await handleUnsubscription(connectionId, data);
      break;
      
    case 'ping':
      ws.send(JSON.stringify({
        type: 'pong',
        timestamp: new Date().toISOString()
      }));
      break;
      
    default:
      ws.send(JSON.stringify({
        type: 'error',
        message: 'Unknown message type'
      }));
  }
}

/**
 * Handle WebSocket authentication
 */
async function handleAuthentication(connectionId, data) {
  const connection = activeConnections.get(connectionId);
  if (!connection) return;
  
  const { ws } = connection;
  
  try {
    if (!data.token) {
      throw new Error('Authentication token required');
    }
    
    // Verify JWT token
    const verifier = jwt.CognitoJwtVerifier.create({
      userPoolId: process.env.COGNITO_USER_POOL_ID,
      tokenUse: 'access',
      clientId: process.env.COGNITO_CLIENT_ID
    });
    
    const payload = await verifier.verify(data.token);
    
    // Update connection with authenticated user
    connection.userId = payload.sub;
    connection.authenticated = true;
    connection.lastSeen = Date.now();
    
    console.log(`✅ [${connectionId}] User authenticated: ${payload.sub.substring(0, 8)}...`);
    
    ws.send(JSON.stringify({
      type: 'authenticated',
      userId: payload.sub,
      timestamp: new Date().toISOString()
    }));
    
  } catch (error) {
    console.error(`❌ [${connectionId}] Authentication failed:`, error);
    ws.send(JSON.stringify({
      type: 'auth_error',
      message: 'Authentication failed'
    }));
  }
}

/**
 * Handle subscription requests
 */
async function handleSubscription(connectionId, data) {
  const connection = activeConnections.get(connectionId);
  if (!connection || !connection.authenticated) {
    connection.ws.send(JSON.stringify({
      type: 'error',
      message: 'Authentication required'
    }));
    return;
  }
  
  const { ws, userId } = connection;
  
  try {
    const symbols = data.symbols || [];
    if (!Array.isArray(symbols) || symbols.length === 0) {
      throw new Error('Valid symbols array required');
    }
    
    // Add to user subscriptions
    if (!userSubscriptions.has(userId)) {
      userSubscriptions.set(userId, new Set());
    }
    
    const userSymbols = userSubscriptions.get(userId);
    symbols.forEach(symbol => {
      userSymbols.add(symbol.toUpperCase());
      connection.subscriptions.add(symbol.toUpperCase());
    });
    
    console.log(`📊 [${connectionId}] Subscribed to:`, symbols);
    
    ws.send(JSON.stringify({
      type: 'subscribed',
      symbols: symbols,
      timestamp: new Date().toISOString()
    }));
    
    // Start streaming for this connection
    startStreamingForConnection(connectionId);
    
  } catch (error) {
    console.error(`❌ [${connectionId}] Subscription failed:`, error);
    ws.send(JSON.stringify({
      type: 'subscription_error',
      message: error.message
    }));
  }
}

/**
 * Start real-time streaming for a connection
 */
async function startStreamingForConnection(connectionId) {
  const connection = activeConnections.get(connectionId);
  if (!connection || !connection.authenticated) return;
  
  const { ws, userId, subscriptions } = connection;
  
  try {
    // Get user's API credentials
    const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
    if (!credentials) {
      ws.send(JSON.stringify({
        type: 'error',
        message: 'API credentials not configured'
      }));
      return;
    }
    
    // Initialize Alpaca service
    const userAlpacaService = new alpacaService.AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      credentials.isSandbox
    );
    
    // Stream live data
    const streamData = async () => {
      if (!activeConnections.has(connectionId)) return;
      
      const symbols = Array.from(subscriptions);
      if (symbols.length === 0) return;
      
      try {
        const quotes = {};
        
        for (const symbol of symbols) {
          const quote = await userAlpacaService.getLatestQuote(symbol);
          if (quote) {
            quotes[symbol] = {
              symbol,
              bidPrice: quote.bidPrice,
              askPrice: quote.askPrice,
              bidSize: quote.bidSize,
              askSize: quote.askSize,
              timestamp: quote.timestamp || Date.now()
            };
            
            // Cache the data
            streamingData.set(symbol, quotes[symbol]);
          }
        }
        
        // Send to WebSocket
        if (Object.keys(quotes).length > 0) {
          ws.send(JSON.stringify({
            type: 'market_data',
            data: quotes,
            timestamp: new Date().toISOString()
          }));
        }
        
      } catch (error) {
        console.error(`❌ [${connectionId}] Streaming error:`, error);
        ws.send(JSON.stringify({
          type: 'streaming_error',
          message: 'Error fetching market data'
        }));
      }
    };
    
    // Start streaming loop
    const streamingInterval = setInterval(streamData, STREAM_INTERVAL);
    
    // Store interval for cleanup
    connection.streamingInterval = streamingInterval;
    
    // Initial data fetch
    streamData();
    
  } catch (error) {
    console.error(`❌ [${connectionId}] Failed to start streaming:`, error);
    ws.send(JSON.stringify({
      type: 'error',
      message: 'Failed to start streaming'
    }));
  }
}

/**
 * Handle unsubscription requests
 */
async function handleUnsubscription(connectionId, data) {
  const connection = activeConnections.get(connectionId);
  if (!connection || !connection.authenticated) {
    connection.ws.send(JSON.stringify({
      type: 'error',
      message: 'Authentication required'
    }));
    return;
  }
  
  const { ws, userId } = connection;
  
  try {
    const symbols = data.symbols || [];
    
    if (symbols.length === 0) {
      // Unsubscribe from all symbols
      connection.subscriptions.clear();
      userSubscriptions.delete(userId);
      
      // Clear streaming interval
      if (connection.streamingInterval) {
        clearInterval(connection.streamingInterval);
        connection.streamingInterval = null;
      }
      
      ws.send(JSON.stringify({
        type: 'unsubscribed',
        message: 'Unsubscribed from all symbols',
        timestamp: new Date().toISOString()
      }));
      
    } else {
      // Unsubscribe from specific symbols
      const userSymbols = userSubscriptions.get(userId);
      if (userSymbols) {
        symbols.forEach(symbol => {
          userSymbols.delete(symbol.toUpperCase());
          connection.subscriptions.delete(symbol.toUpperCase());
        });
        
        if (userSymbols.size === 0) {
          userSubscriptions.delete(userId);
        }
      }
      
      ws.send(JSON.stringify({
        type: 'unsubscribed',
        symbols: symbols,
        timestamp: new Date().toISOString()
      }));
    }
    
    console.log(`📊 [${connectionId}] Unsubscribed from:`, symbols.length > 0 ? symbols : 'all symbols');
    
  } catch (error) {
    console.error(`❌ [${connectionId}] Unsubscription failed:`, error);
    ws.send(JSON.stringify({
      type: 'unsubscription_error',
      message: error.message
    }));
  }
}

/**
 * HTTP endpoint for WebSocket connection info (fallback)
 */
router.get('/stream/:symbols', async (req, res) => {
  const requestId = require('crypto').randomUUID().split('-')[0];
  const requestStart = Date.now();
  
  try {
    console.log(`🚀 [${requestId}] Live data stream request initiated`, {
      symbols: req.params.symbols,
      userAgent: req.headers['user-agent'],
      ip: req.ip,
      hasAuth: !!req.headers.authorization,
      timestamp: new Date().toISOString()
    });

    // Verify authentication with detailed logging
    const authHeader = req.headers.authorization;
    if (!authHeader) {
      console.error(`❌ [${requestId}] Authentication failure - no authorization header provided`);
      return res.status(401).json(error(
        'No authorization token provided',
        401,
        { requestId, timestamp: new Date().toISOString() }
      ).response);
    }

    if (!authHeader.startsWith('Bearer ')) {
      console.error(`❌ [${requestId}] Authentication failure - invalid authorization header format`);
      return res.status(401).json(error(
        'Invalid authorization header format',
        401,
        { requestId, timestamp: new Date().toISOString() }
      ).response);
    }

    const token = authHeader.replace('Bearer ', '');
    console.log(`🔍 [${requestId}] Verifying JWT token`, {
      tokenLength: token.length,
      tokenPrefix: token.substring(0, 20) + '...'
    });
    
    // Verify JWT token with comprehensive error handling
    const verifyStart = Date.now();
    let payload, userId;
    try {
      const verifier = jwt.CognitoJwtVerifier.create({
        userPoolId: process.env.COGNITO_USER_POOL_ID,
        tokenUse: 'access',
        clientId: process.env.COGNITO_CLIENT_ID
      });

      payload = await verifier.verify(token);
      userId = payload.sub;
      const verifyDuration = Date.now() - verifyStart;
      
      console.log(`✅ [${requestId}] JWT token verified successfully in ${verifyDuration}ms`, {
        userId: userId ? `${userId.substring(0, 8)}...` : 'undefined',
        tokenType: payload.token_use,
        clientId: payload.client_id,
        issuer: payload.iss
      });
      
    } catch (jwtError) {
      const verifyDuration = Date.now() - verifyStart;
      console.error(`❌ [${requestId}] JWT verification FAILED after ${verifyDuration}ms:`, {
        error: jwtError.message,
        errorType: jwtError.name,
        tokenLength: token.length,
        impact: 'Live data access denied',
        recommendation: 'User needs to re-authenticate'
      });
      
      return res.status(401).json(error(
        'Invalid or expired authentication token',
        401,
        { 
          requestId, 
          error: 'Authentication failed',
          timestamp: new Date().toISOString() 
        }
      ).response);
    }

    // Parse and validate symbols
    console.log(`🔍 [${requestId}] Parsing requested symbols: ${req.params.symbols}`);
    const symbols = req.params.symbols.split(',')
      .map(s => s.trim().toUpperCase())
      .filter(s => s.length > 0 && s.length <= 10 && /^[A-Z]+$/.test(s));
    
    if (symbols.length === 0) {
      console.error(`❌ [${requestId}] Invalid symbols provided:`, {
        originalSymbols: req.params.symbols,
        filteredSymbols: symbols,
        impact: 'No valid symbols to stream'
      });
      return res.status(400).json(error(
        'No valid symbols provided',
        400,
        { requestId, timestamp: new Date().toISOString() }
      ).response);
    }
    
    console.log(`✅ [${requestId}] Symbols validated:`, {
      validSymbols: symbols,
      symbolCount: symbols.length
    });
    
    // Get user's Alpaca credentials with comprehensive error handling
    console.log(`🔑 [${requestId}] Retrieving user API credentials for live data access`);
    const credentialsStart = Date.now();
    
    let credentials;
    try {
      credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
      const credentialsDuration = Date.now() - credentialsStart;
      
      if (!credentials) {
        console.error(`❌ [${requestId}] No API credentials found after ${credentialsDuration}ms`, {
          requestedProvider: 'alpaca',
          userId: `${userId.substring(0, 8)}...`,
          impact: 'Live market data will not be available',
          recommendation: 'User needs to configure Alpaca API keys in settings'
        });
        
        return res.status(400).json({
          success: false,
          error: 'API credentials not configured',
          message: 'Please configure your Alpaca API keys in Settings to access live market data',
          error_code: 'API_CREDENTIALS_MISSING',
          provider: 'alpaca',
          actions: [
            'Go to Settings > API Keys',
            'Add your Alpaca API credentials',
            'Choose the correct environment (Paper Trading or Live Trading)',
            'Test the connection to verify your credentials'
          ],
          request_info: {
            request_id: requestId,
            timestamp: new Date().toISOString()
          }
        });
      }
      
      console.log(`✅ [${requestId}] API credentials retrieved in ${credentialsDuration}ms`, {
        provider: 'alpaca',
        environment: credentials.isSandbox ? 'sandbox' : 'live',
        keyLength: credentials.apiKey ? credentials.apiKey.length : 0,
        hasSecret: !!credentials.apiSecret
      });
      
    } catch (credentialsError) {
      const credentialsDuration = Date.now() - credentialsStart;
      console.error(`❌ [${requestId}] Failed to retrieve API credentials after ${credentialsDuration}ms:`, {
        error: credentialsError.message,
        errorStack: credentialsError.stack,
        provider: 'alpaca',
        impact: 'Cannot access live market data',
        recommendation: 'Check API key configuration and database connectivity'
      });
      
      return res.status(500).json({
        success: false,
        error: 'Failed to retrieve API credentials',
        message: 'There was an error accessing your API credentials. Please try again or contact support.',
        error_code: 'API_CREDENTIALS_ERROR',
        details: process.env.NODE_ENV === 'development' ? credentialsError.message : 'Internal error',
        request_info: {
          request_id: requestId,
          error_duration_ms: credentialsDuration,
          timestamp: new Date().toISOString()
        }
      });
    }


    // Initialize Alpaca service for this user with comprehensive error handling
    console.log(`🏭 [${requestId}] Initializing Alpaca service for live data`);
    const alpacaInitStart = Date.now();
    let userAlpacaService;
    
    try {
      userAlpacaService = new alpacaService.AlpacaService(
        credentials.apiKey, 
        credentials.apiSecret, 
        credentials.isSandbox
      );
      const alpacaInitDuration = Date.now() - alpacaInitStart;
      
      console.log(`✅ [${requestId}] Alpaca service initialized in ${alpacaInitDuration}ms`, {
        environment: credentials.isSandbox ? 'sandbox' : 'live',
        hasApiKey: !!credentials.apiKey,
        hasSecret: !!credentials.apiSecret
      });
      
    } catch (alpacaError) {
      const alpacaInitDuration = Date.now() - alpacaInitStart;
      console.error(`❌ [${requestId}] Alpaca service initialization FAILED after ${alpacaInitDuration}ms:`, {
        error: alpacaError.message,
        errorStack: alpacaError.stack,
        environment: credentials.isSandbox ? 'sandbox' : 'live',
        impact: 'Cannot initialize live data service',
        recommendation: 'Check API key validity and Alpaca service status'
      });
      
      return res.status(500).json({
        success: false,
        error: 'Failed to initialize live data service',
        message: 'Unable to connect to your broker for live data. Please verify your API credentials or try again later.',
        error_code: 'LIVE_DATA_SERVICE_INIT_ERROR',
        details: process.env.NODE_ENV === 'development' ? alpacaError.message : 'Service initialization failed',
        provider: 'alpaca',
        environment: credentials.isSandbox ? 'sandbox' : 'live',
        actions: [
          'Verify your API credentials are correct',
          'Check if your API keys have market data permissions',
          'Try switching between Paper Trading and Live Trading modes',
          'Contact broker support if the issue persists'
        ],
        request_info: {
          request_id: requestId,
          error_duration_ms: alpacaInitDuration,
          timestamp: new Date().toISOString()
        }
      });
    }

    // Update user subscriptions with logging
    console.log(`📝 [${requestId}] Updating user subscriptions`, {
      previousSubscriptions: Array.from(userSubscriptions.get(userId) || []),
      newSubscriptions: symbols
    });
    userSubscriptions.set(userId, new Set(symbols));

    // Get latest quotes for requested symbols with comprehensive error handling
    console.log(`📊 [${requestId}] Fetching market data for ${symbols.length} symbols`);
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
            age: dataAge
          };
          cachedSymbols++;
          console.log(`📋 [${requestId}] Using cached data for ${symbol}`, {
            age: `${dataAge}ms`,
            ttl: `${CACHE_TTL}ms`
          });
        } else {
          // Fetch fresh data from Alpaca with timeout protection
          console.log(`📡 [${requestId}] Fetching fresh data for ${symbol} from Alpaca`);
          const alpacaFetchStart = Date.now();
          
          const quote = await Promise.race([
            userAlpacaService.getLatestQuote(symbol),
            new Promise((_, reject) => 
              setTimeout(() => reject(new Error(`Quote fetch timeout for ${symbol} after 8 seconds`)), 8000)
            )
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
              fetchTime: alpacaFetchDuration
            };

            // Cache the data
            realtimeDataCache.set(cacheKey, formattedQuote);
            lastUpdateTime.set(symbol, now);
            marketData[symbol] = formattedQuote;
            successfulFetches++;
            
            console.log(`✅ [${requestId}] Fresh data fetched for ${symbol} in ${alpacaFetchDuration}ms`, {
              bidPrice: quote.bidPrice,
              askPrice: quote.askPrice,
              spread: quote.askPrice - quote.bidPrice
            });
          } else {
            console.warn(`⚠️ [${requestId}] No quote data returned for ${symbol}`);
            marketData[symbol] = {
              symbol: symbol,
              error: 'Quote data unavailable',
              timestamp: now,
              cached: false
            };
            failedSymbols++;
          }
        }
        
        const symbolDuration = Date.now() - symbolFetchStart;
        console.log(`✅ [${requestId}] Symbol ${symbol} processed in ${symbolDuration}ms`);
        
      } catch (error) {
        const symbolDuration = Date.now() - symbolFetchStart;
        console.error(`❌ [${requestId}] Failed to get quote for ${symbol} after ${symbolDuration}ms:`, {
          error: error.message,
          errorStack: error.stack,
          errorCode: error.code,
          statusCode: error.status,
          impact: 'Symbol will show error status'
        });
        
        // Determine error type for better user messaging
        let errorMessage = 'Quote unavailable';
        let errorCode = 'QUOTE_ERROR';
        
        if (error.message?.includes('timeout')) {
          errorMessage = 'Request timeout';
          errorCode = 'QUOTE_TIMEOUT';
        } else if (error.status === 401 || error.message?.includes('unauthorized')) {
          errorMessage = 'API credentials invalid';
          errorCode = 'QUOTE_UNAUTHORIZED';
        } else if (error.status === 403 || error.message?.includes('forbidden')) {
          errorMessage = 'Insufficient permissions';
          errorCode = 'QUOTE_FORBIDDEN';
        } else if (error.status === 429 || error.message?.includes('rate limit')) {
          errorMessage = 'Rate limit exceeded';
          errorCode = 'QUOTE_RATE_LIMITED';
        }
        
        marketData[symbol] = {
          symbol: symbol,
          error: errorMessage,
          error_code: errorCode,
          errorMessage: error.message,
          timestamp: now,
          cached: false
        };
        failedSymbols++;
      }
    }

    const dataFetchDuration = Date.now() - dataFetchStart;
    const totalDuration = Date.now() - requestStart;

    console.log(`✅ [${requestId}] Live data stream completed in ${totalDuration}ms`, {
      summary: {
        totalSymbols: symbols.length,
        successfulFetches,
        cachedSymbols,
        failedSymbols,
        successRate: `${Math.round((successfulFetches + cachedSymbols) / symbols.length * 100)}%`
      },
      performance: {
        totalDuration: `${totalDuration}ms`,
        dataFetchDuration: `${dataFetchDuration}ms`,
        avgPerSymbol: `${Math.round(dataFetchDuration / symbols.length)}ms`
      },
      cache: {
        totalCachedSymbols: realtimeDataCache.size,
        hitRate: `${Math.round(cachedSymbols / symbols.length * 100)}%`
      },
      status: 'SUCCESS'
    });

    const responseData = {
      symbols: symbols,
      data: marketData,
      updateInterval: UPDATE_INTERVAL,
      cacheStatus: {
        totalCachedSymbols: realtimeDataCache.size,
        userSubscriptions: Array.from(userSubscriptions.get(userId) || []),
        cacheHitRate: Math.round(cachedSymbols / symbols.length * 100),
        cacheTTL: CACHE_TTL
      },
      statistics: {
        successful: successfulFetches,
        cached: cachedSymbols,
        failed: failedSymbols,
        total: symbols.length
      },
      request_info: {
        request_id: requestId,
        total_duration_ms: totalDuration,
        data_fetch_duration_ms: dataFetchDuration,
        timestamp: new Date().toISOString()
      }
    };

    res.json(success(responseData));

  } catch (streamError) {
    const errorDuration = Date.now() - requestStart;
    console.error(`❌ [${requestId}] Live data stream FAILED after ${errorDuration}ms:`, {
      error: streamError.message,
      errorStack: streamError.stack,
      errorCode: streamError.code,
      symbols: req.params.symbols,
      impact: 'Live data stream request failed completely',
      recommendation: 'Check authentication, API credentials, and Alpaca service status'
    });
    
    res.status(500).json(createErrorResponse(
      'Failed to stream market data',
      {
        requestId,
        error_duration_ms: errorDuration,
        details: process.env.NODE_ENV === 'development' ? streamError.message : 'Internal server error'
      }
    ));
  }
});

/**
 * Get latest trade data for symbols
 */
router.get('/trades/:symbols', async (req, res) => {
  try {
    // Verify authentication
    const authHeader = req.headers.authorization;
    if (!authHeader) {
      return res.status(401).json(createErrorResponse('No authorization token provided'));
    }

    const token = authHeader.replace('Bearer ', '');
    
    const verifier = jwt.CognitoJwtVerifier.create({
      userPoolId: process.env.COGNITO_USER_POOL_ID,
      tokenUse: 'access',
      clientId: process.env.COGNITO_CLIENT_ID
    });

    const payload = await verifier.verify(token);
    const userId = payload.sub;

    // Parse symbols
    const symbols = req.params.symbols.split(',').map(s => s.trim().toUpperCase());
    
    // Get user's Alpaca credentials
    const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
    if (!credentials) {
      return res.status(403).json(createErrorResponse('No Alpaca API key configured'));
    }

    // Initialize Alpaca service
    const userAlpacaService = new alpacaService.AlpacaService(
      credentials.apiKey, 
      credentials.apiSecret, 
      credentials.isSandbox
    );

    // Get latest trades
    const tradeData = {};
    for (const symbol of symbols) {
      try {
        const trade = await userAlpacaService.getLatestTrade(symbol);
        tradeData[symbol] = trade ? {
          symbol: symbol,
          price: trade.price,
          size: trade.size,
          timestamp: trade.timestamp,
          conditions: trade.conditions
        } : { symbol: symbol, error: 'Trade data unavailable' };
      } catch (error) {
        tradeData[symbol] = { symbol: symbol, error: error.message };
      }
    }

    res.json(success(tradeData));

  } catch (error) {
    console.error('Trades endpoint error:', error);
    res.status(500).json(createErrorResponse('Failed to get trade data'));
  }
});

/**
 * Get bars/OHLCV data for symbols
 */
router.get('/bars/:symbols', async (req, res) => {
  try {
    // Verify authentication
    const authHeader = req.headers.authorization;
    if (!authHeader) {
      return res.status(401).json(createErrorResponse('No authorization token provided'));
    }

    const token = authHeader.replace('Bearer ', '');
    
    const verifier = jwt.CognitoJwtVerifier.create({
      userPoolId: process.env.COGNITO_USER_POOL_ID,
      tokenUse: 'access',
      clientId: process.env.COGNITO_CLIENT_ID
    });

    const payload = await verifier.verify(token);
    const userId = payload.sub;

    // Parse symbols and timeframe
    const symbols = req.params.symbols.split(',').map(s => s.trim().toUpperCase());
    const timeframe = req.query.timeframe || '1Min';
    
    // Get user's Alpaca credentials
    const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
    if (!credentials) {
      return res.status(403).json(createErrorResponse('No Alpaca API key configured'));
    }

    // Initialize Alpaca service
    const userAlpacaService = new alpacaService.AlpacaService(
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
          limit: 100
        });
        barsData[symbol] = bars || { symbol: symbol, error: 'Bars data unavailable' };
      } catch (error) {
        barsData[symbol] = { symbol: symbol, error: error.message };
      }
    }

    res.json(success(barsData));

  } catch (error) {
    console.error('Bars endpoint error:', error);
    res.status(500).json(createErrorResponse('Failed to get bars data'));
  }
});

/**
 * Subscribe to symbols (for tracking user interest)
 */
router.post('/subscribe', async (req, res) => {
  try {
    // Verify authentication
    const authHeader = req.headers.authorization;
    if (!authHeader) {
      return res.status(401).json(createErrorResponse('No authorization token provided'));
    }

    const token = authHeader.replace('Bearer ', '');
    
    const verifier = jwt.CognitoJwtVerifier.create({
      userPoolId: process.env.COGNITO_USER_POOL_ID,
      tokenUse: 'access',
      clientId: process.env.COGNITO_CLIENT_ID
    });

    const payload = await verifier.verify(token);
    const userId = payload.sub;

    const { symbols, dataTypes } = req.body;
    
    if (!symbols || !Array.isArray(symbols)) {
      return res.status(400).json(createErrorResponse('Invalid symbols array'));
    }

    // Update user subscriptions
    const userSymbols = symbols.map(s => s.toUpperCase());
    userSubscriptions.set(userId, new Set(userSymbols));

    res.json(success({
      subscribed: userSymbols,
      dataTypes: dataTypes || ['quotes'],
      message: `Subscribed to ${userSymbols.length} symbols`,
      streamEndpoints: {
        quotes: `/api/websocket/stream/${userSymbols.join(',')}`,
        trades: `/api/websocket/trades/${userSymbols.join(',')}`,
        bars: `/api/websocket/bars/${userSymbols.join(',')}`
      }
    }));

  } catch (error) {
    console.error('Subscribe endpoint error:', error);
    res.status(500).json(createErrorResponse('Failed to subscribe'));
  }
});

/**
 * Get user's current subscriptions
 */
router.get('/subscriptions', async (req, res) => {
  try {
    // Verify authentication
    const authHeader = req.headers.authorization;
    if (!authHeader) {
      return res.status(401).json(createErrorResponse('No authorization token provided'));
    }

    const token = authHeader.replace('Bearer ', '');
    
    const verifier = jwt.CognitoJwtVerifier.create({
      userPoolId: process.env.COGNITO_USER_POOL_ID,
      tokenUse: 'access',
      clientId: process.env.COGNITO_CLIENT_ID
    });

    const payload = await verifier.verify(token);
    const userId = payload.sub;

    const subscriptions = Array.from(userSubscriptions.get(userId) || []);

    res.json(success({
      symbols: subscriptions,
      count: subscriptions.length,
      streamEndpoints: subscriptions.length > 0 ? {
        quotes: `/api/websocket/stream/${subscriptions.join(',')}`,
        trades: `/api/websocket/trades/${subscriptions.join(',')}`,
        bars: `/api/websocket/bars/${subscriptions.join(',')}`
      } : null
    }));

  } catch (error) {
    console.error('Subscriptions endpoint error:', error);
    res.status(500).json(createErrorResponse('Failed to get subscriptions'));
  }
});

/**
 * Unsubscribe from symbols
 */
router.delete('/subscribe', async (req, res) => {
  try {
    // Verify authentication
    const authHeader = req.headers.authorization;
    if (!authHeader) {
      return res.status(401).json(createErrorResponse('No authorization token provided'));
    }

    const token = authHeader.replace('Bearer ', '');
    
    const verifier = jwt.CognitoJwtVerifier.create({
      userPoolId: process.env.COGNITO_USER_POOL_ID,
      tokenUse: 'access',
      clientId: process.env.COGNITO_CLIENT_ID
    });

    const payload = await verifier.verify(token);
    const userId = payload.sub;

    const { symbols } = req.body;
    
    if (symbols && Array.isArray(symbols)) {
      // Remove specific symbols
      const userSymbols = userSubscriptions.get(userId) || new Set();
      symbols.forEach(symbol => userSymbols.delete(symbol.toUpperCase()));
      userSubscriptions.set(userId, userSymbols);
    } else {
      // Remove all subscriptions
      userSubscriptions.delete(userId);
    }

    res.json(success({
      message: 'Unsubscribed successfully',
      remainingSubscriptions: Array.from(userSubscriptions.get(userId) || [])
    }));

  } catch (error) {
    console.error('Unsubscribe endpoint error:', error);
    res.status(500).json(createErrorResponse('Failed to unsubscribe'));
  }
});

// Health check endpoint
router.get('/health', (req, res) => {
  const connectionStats = {
    activeConnections: activeConnections.size,
    authenticatedUsers: Array.from(activeConnections.values()).filter(c => c.authenticated).length,
    totalSubscriptions: Array.from(userSubscriptions.values()).reduce((sum, set) => sum + set.size, 0),
    streamingSymbols: streamingData.size
  };
  
  res.json(success({
    status: 'operational',
    type: 'websocket_realtime_streaming',
    streamInterval: STREAM_INTERVAL,
    connectionTimeout: CONNECTION_TIMEOUT,
    ...connectionStats
  }));
});

// Status endpoint with detailed metrics
router.get('/status', (req, res) => {
  const now = Date.now();
  const streamingDetails = {};
  
  for (const [symbol, data] of streamingData.entries()) {
    streamingDetails[symbol] = {
      lastUpdate: new Date(data.timestamp).toISOString(),
      age: now - data.timestamp,
      bidPrice: data.bidPrice,
      askPrice: data.askPrice
    };
  }

  const connectionDetails = Array.from(activeConnections.entries()).map(([connectionId, conn]) => ({
    connectionId: connectionId.substring(0, 8) + '...',
    authenticated: conn.authenticated,
    userId: conn.userId ? conn.userId.substring(0, 8) + '...' : null,
    subscriptions: Array.from(conn.subscriptions),
    lastSeen: new Date(conn.lastSeen).toISOString()
  }));

  res.json(success({
    activeConnections: activeConnections.size,
    authenticatedUsers: Array.from(activeConnections.values()).filter(c => c.authenticated).length,
    streamingSymbols: streamingData.size,
    streamingDetails,
    connectionDetails,
    userSubscriptions: Object.fromEntries(
      Array.from(userSubscriptions.entries()).map(([userId, symbols]) => [
        userId.substring(0, 8) + '...', 
        Array.from(symbols)
      ])
    ),
    serverTime: new Date().toISOString(),
    uptime: process.uptime()
  }));
});

// Cleanup inactive connections periodically
setInterval(() => {
  const now = Date.now();
  const inactiveConnections = [];
  
  for (const [connectionId, connection] of activeConnections.entries()) {
    if (now - connection.lastSeen > CONNECTION_TIMEOUT) {
      inactiveConnections.push(connectionId);
      
      // Clear streaming interval
      if (connection.streamingInterval) {
        clearInterval(connection.streamingInterval);
      }
    }
  }
  
  inactiveConnections.forEach(connectionId => {
    activeConnections.delete(connectionId);
    console.log(`🧹 Cleaned up inactive connection: ${connectionId}`);
  });
  
  // Clean up streaming data for symbols with no active subscriptions
  const activeSymbols = new Set();
  for (const connection of activeConnections.values()) {
    if (connection.authenticated) {
      connection.subscriptions.forEach(symbol => activeSymbols.add(symbol));
    }
  }
  
  for (const symbol of streamingData.keys()) {
    if (!activeSymbols.has(symbol)) {
      streamingData.delete(symbol);
    }
  }
  
}, CONNECTION_TIMEOUT / 2);

module.exports = router;
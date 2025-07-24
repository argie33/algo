const express = require('express');
const { success, error } = require('../utils/responseFormatter');

// Import dependencies with error handling
let jwt, apiKeyService, alpacaService, validationMiddleware, hftService;
try {
  jwt = require('aws-jwt-verify');
  apiKeyService = require('../utils/simpleApiKeyService');
  alpacaService = require('../utils/alpacaService');
  const validation = require('../middleware/validation');
  validationMiddleware = validation.createValidationMiddleware;
  const HFTService = require('../services/hftService');
  hftService = new HFTService();
} catch (loadError) {
  console.warn('Some websocket dependencies not available:', loadError.message);
}

const router = express.Router();

// Simple error response helper
const createErrorResponse = (message, details = {}) => ({
  success: false,
  error: message,
  details,
  timestamp: new Date().toISOString()
});

/**
 * WebSocket Information endpoint
 * Lambda doesn't support persistent WebSocket connections
 * This provides information about WebSocket alternatives
 */
router.get('/info', (req, res) => {
  console.log('📡 WebSocket info endpoint accessed');
  
  res.success({
    service: 'WebSocket Alternative Service',
    environment: 'AWS Lambda',
    websocketSupport: false,
    reason: 'Lambda functions do not support persistent WebSocket connections',
    alternatives: {
      polling: {
        endpoint: '/api/realtime/poll',
        description: 'HTTP polling for real-time data updates',
        interval: '1-5 seconds recommended'
      },
      serverSentEvents: {
        endpoint: '/api/realtime/stream',
        description: 'Server-sent events for streaming data',
        contentType: 'text/event-stream'
      },
      restApi: {
        endpoint: '/api/market-data/live',
        description: 'RESTful API for on-demand market data',
        method: 'GET'
      }
    },
    supportedFeatures: [
      'HTTP polling for real-time data',
      'Server-sent events streaming',
      'RESTful API endpoints',
      'JWT authentication',
      'Market data subscriptions'
    ],
    documentation: {
      realtime: '/api/realtime',
      marketData: '/api/market-data',
      authentication: '/api/auth'
    }
  });
});

/**
 * WebSocket connection status endpoint
 * Provides alternatives to WebSocket functionality
 */
router.get('/stream', (req, res) => {
  console.log('📡 WebSocket stream endpoint accessed - providing alternatives');
  
  res.success({
    message: 'WebSocket connections not supported in Lambda environment',
    alternatives: {
      polling: '/api/realtime/poll',
      serverSentEvents: '/api/realtime/stream',
      restApi: '/api/market-data/live'
    },
    supportedFeatures: [
      'HTTP polling for real-time data',
      'Server-sent events streaming',
      'RESTful API endpoints'
    ],
    documentation: 'See /api/realtime for streaming data options'
  });
});

/**
 * Connection status endpoint
 * Provides information about active connections and alternatives
 */
/**
 * Market data processing endpoint for HFT integration
 * Forwards market data to HFT engine for real-time analysis
 */
router.post('/market-data', async (req, res) => {
  try {
    const { symbol, data } = req.body;
    
    if (!symbol || !data) {
      return res.status(400).json(createErrorResponse(
        'Missing required fields: symbol and data',
        { received: { symbol: !!symbol, data: !!data } }
      ));
    }

    console.log(`📊 Processing market data for HFT: ${symbol}`);
    
    // Forward to HFT service if available
    if (hftService && typeof hftService.processMarketData === 'function') {
      await hftService.processMarketData({ symbol, data });
      
      res.success({
        message: 'Market data processed for HFT analysis',
        symbol: symbol,
        timestamp: Date.now(),
        hftEnabled: true
      });
    } else {
      res.success({
        message: 'Market data logged (HFT service not available)',
        symbol: symbol,
        timestamp: Date.now(),
        hftEnabled: false
      });
    }
    
  } catch (error) {
    console.error('❌ Error processing market data for HFT:', error);
    res.status(500).json(createErrorResponse(
      'Failed to process market data',
      { error: error.message }
    ));
  }
});

router.get('/status', (req, res) => {
  res.success({
    service: 'WebSocket Alternative Service',
    status: 'operational',
    connectionType: 'HTTP',
    environment: 'AWS Lambda',
    supportedEndpoints: {
      info: '/api/websocket/info',
      status: '/api/websocket/status',
      stream: '/api/websocket/stream',
      subscribe: '/api/realtime/subscribe',
      data: '/api/market-data/live'
    },
    features: [
      'Real-time market data via HTTP polling',
      'Server-sent events for streaming',
      'REST API for on-demand data',
      'JWT authentication',
      'Symbol subscription management'
    ],
    limits: {
      pollingInterval: '1 second minimum',
      maxSymbols: 100,
      authenticationRequired: true
    },
    timestamp: new Date().toISOString()
  });
});

/**
 * Authentication endpoint for real-time services
 * Replaces WebSocket authentication with HTTP
 */
router.post('/authenticate', async (req, res) => {
  try {
    const { token } = req.body;
    
    if (!token) {
      return res.badRequest('Authentication token required', {
        expectedFormat: 'Bearer token in Authorization header or token in request body'
      });
    }
    
    // Verify JWT token if available
    if (jwt && process.env.COGNITO_USER_POOL_ID) {
      try {
        const verifier = jwt.CognitoJwtVerifier.create({
          userPoolId: process.env.COGNITO_USER_POOL_ID,
          tokenUse: 'access',
          clientId: process.env.COGNITO_CLIENT_ID
        });
        
        const payload = await verifier.verify(token);
        
        res.success({
          authenticated: true,
          userId: payload.sub,
          email: payload.email,
          username: payload.username,
          nextSteps: {
            subscribe: 'POST /api/realtime/subscribe',
            poll: 'GET /api/realtime/poll',
            stream: 'GET /api/realtime/stream'
          }
        });
      } catch (verifyError) {
        res.unauthorized('Token verification failed', {
          error: verifyError.message,
          hint: 'Check token format and expiration'
        });
      }
    } else {
      // Development mode or missing Cognito config
      res.success({
        authenticated: true,
        userId: 'dev-user',
        email: 'dev@example.com',
        mode: 'development',
        nextSteps: {
          subscribe: 'POST /api/realtime/subscribe',
          poll: 'GET /api/realtime/poll',
          stream: 'GET /api/realtime/stream'
        }
      });
    }
  } catch (error) {
    res.serverError('Authentication failed', {
      error: error.message
    });
  }
});

/**
 * Subscription management endpoint
 * Replaces WebSocket subscription with HTTP
 */
router.post('/subscribe', async (req, res) => {
  try {
    const { symbols, userId } = req.body;
    
    if (!symbols || !Array.isArray(symbols)) {
      return res.badRequest('Valid symbols array required', {
        example: { symbols: ['AAPL', 'MSFT', 'GOOGL'] }
      });
    }
    
    if (symbols.length > 100) {
      return res.badRequest('Too many symbols', {
        maximum: 100,
        provided: symbols.length
      });
    }
    
    // Validate symbol format
    const validSymbols = symbols.filter(symbol => 
      typeof symbol === 'string' && /^[A-Z]{1,10}$/.test(symbol)
    );
    
    if (validSymbols.length !== symbols.length) {
      return res.badRequest('Invalid symbol format', {
        validSymbols,
        invalidSymbols: symbols.filter(s => !validSymbols.includes(s)),
        format: 'Uppercase letters, 1-10 characters'
      });
    }
    
    res.success({
      subscribed: true,
      symbols: validSymbols,
      userId: userId || 'anonymous',
      dataAccess: {
        polling: `GET /api/realtime/poll?symbols=${validSymbols.join(',')}`,
        streaming: `GET /api/realtime/stream?symbols=${validSymbols.join(',')}`,
        restApi: 'GET /api/market-data/live'
      },
      updateInterval: '1-5 seconds recommended'
    });
  } catch (error) {
    res.serverError('Subscription failed', {
      error: error.message
    });
  }
});

/**
 * Health check for WebSocket alternative service
 */
router.get('/health', (req, res) => {
  const healthStatus = {
    service: 'WebSocket Alternative Service',
    status: 'healthy',
    environment: 'AWS Lambda',
    capabilities: {
      httpPolling: true,
      serverSentEvents: true,
      restApi: true,
      authentication: !!jwt,
      cognitoIntegration: !!(process.env.COGNITO_USER_POOL_ID && process.env.COGNITO_CLIENT_ID)
    },
    dependencies: {
      jwt: !!jwt,
      apiKeyService: !!apiKeyService,
      alpacaService: !!alpacaService,
      validationMiddleware: !!validationMiddleware
    },
    timestamp: new Date().toISOString()
  };
  
  const allHealthy = Object.values(healthStatus.capabilities).every(Boolean);
  
  if (allHealthy) {
    res.success(healthStatus);
  } else {
    res.status(503).json({
      success: false,
      data: healthStatus,
      message: 'Some capabilities unavailable',
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const apiKeyService = require('../utils/simpleApiKeyService');
const AlpacaService = require('../utils/alpacaService');
const { 
  createValidationMiddleware, 
  rateLimitConfigs, 
  sqlInjectionPrevention, 
  xssPrevention,
  sanitizers
} = require('../middleware/validation');
const validator = require('validator');

const router = express.Router();

// Market data validation schemas
const marketDataValidationSchemas = {
  quotes: {
    symbols: {
      required: true,
      type: 'string',
      sanitizer: (value) => {
        if (typeof value !== 'string') return '';
        // Split by comma, clean each symbol, and rejoin
        return value.split(',')
          .map(s => sanitizers.symbol(s.trim()))
          .filter(s => s.length > 0)
          .slice(0, 50) // Limit to 50 symbols max
          .join(',');
      },
      validator: (value) => {
        if (!value) return false;
        const symbols = value.split(',');
        return symbols.length > 0 && 
               symbols.length <= 50 && 
               symbols.every(s => /^[A-Z]{1,10}$/.test(s.trim()));
      },
      errorMessage: 'Symbols must be a comma-separated list of 1-50 valid stock symbols'
    }
  },

  bars: {
    symbol: {
      required: true,
      type: 'string',
      sanitizer: sanitizers.symbol,
      validator: (value) => /^[A-Z]{1,10}$/.test(value),
      errorMessage: 'Symbol must be 1-10 uppercase letters'
    },
    timeframe: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 20, alphaNumOnly: false }),
      validator: (value) => !value || ['1Min', '5Min', '15Min', '30Min', '1Hour', '1Day', '1Week', '1Month'].includes(value),
      errorMessage: 'Timeframe must be one of: 1Min, 5Min, 15Min, 30Min, 1Hour, 1Day, 1Week, 1Month'
    },
    start: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 20 }),
      validator: (value) => !value || validator.isISO8601(value),
      errorMessage: 'Start date must be in ISO8601 format (YYYY-MM-DDTHH:mm:ssZ)'
    },
    end: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 20 }),
      validator: (value) => !value || validator.isISO8601(value),
      errorMessage: 'End date must be in ISO8601 format (YYYY-MM-DDTHH:mm:ssZ)'
    },
    limit: {
      type: 'integer',
      sanitizer: (value) => sanitizers.integer(value, { min: 1, max: 1000, defaultValue: 100 }),
      validator: (value) => !value || (value >= 1 && value <= 1000),
      errorMessage: 'Limit must be between 1 and 1000'
    }
  },

  trades: {
    symbol: {
      required: true,
      type: 'string',
      sanitizer: sanitizers.symbol,
      validator: (value) => /^[A-Z]{1,10}$/.test(value),
      errorMessage: 'Symbol must be 1-10 uppercase letters'
    },
    start: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 20 }),
      validator: (value) => !value || validator.isISO8601(value),
      errorMessage: 'Start date must be in ISO8601 format'
    },
    end: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 20 }),
      validator: (value) => !value || validator.isISO8601(value),
      errorMessage: 'End date must be in ISO8601 format'
    },
    limit: {
      type: 'integer',
      sanitizer: (value) => sanitizers.integer(value, { min: 1, max: 1000, defaultValue: 100 }),
      validator: (value) => !value || (value >= 1 && value <= 1000),
      errorMessage: 'Limit must be between 1 and 1000'
    }
  },

  calendar: {
    start: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10 }),
      validator: (value) => !value || validator.isDate(value, { format: 'YYYY-MM-DD' }),
      errorMessage: 'Start date must be in YYYY-MM-DD format'
    },
    end: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10 }),
      validator: (value) => !value || validator.isDate(value, { format: 'YYYY-MM-DD' }),
      errorMessage: 'End date must be in YYYY-MM-DD format'
    }
  }
};

// Apply security middleware to authenticated routes
router.use('/quotes', sqlInjectionPrevention, xssPrevention, rateLimitConfigs.api);
router.use('/bars', sqlInjectionPrevention, xssPrevention, rateLimitConfigs.api);
router.use('/trades', sqlInjectionPrevention, xssPrevention, rateLimitConfigs.api);
router.use('/calendar', sqlInjectionPrevention, xssPrevention, rateLimitConfigs.api);

// Root market-data endpoint for health checks (no auth required)
router.get('/', (req, res) => {
  res.success({
    system: 'Market Data API',
    version: '1.0.0',
    status: 'operational',
    available_endpoints: [
      'GET /market-data/status - Market status and trading hours',
      'GET /market-data/quotes - Real-time quotes for symbols',
      'GET /market-data/bars/:symbol - Historical price bars',
      'GET /market-data/trades/:symbol - Latest trades',
      'GET /market-data/calendar - Market calendar',
      'GET /market-data/assets - Tradeable assets'
    ]
  });
});

// Market Data Service Health Check - Tests API key functionality and external service connectivity
router.get('/health', authenticateToken, async (req, res) => {
  const requestId = require('crypto').randomUUID().split('-')[0];
  const requestStart = Date.now();
  
  try {
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    console.log(`🚀 [${requestId}] Market data health check initiated`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'undefined',
      userAgent: req.headers['user-agent'],
      ip: req.ip,
      timestamp: new Date().toISOString()
    });

    // Test API key availability and functionality
    console.log(`🔑 [${requestId}] Testing API key availability for market data access`);
    const credentialsStart = Date.now();
    const credentials = await getUserApiKey(userId, 'alpaca');
    const credentialsDuration = Date.now() - credentialsStart;
    
    const healthResult = {
      overall_status: 'healthy',
      timestamp: new Date().toISOString(),
      request_id: requestId,
      api_key_status: {},
      external_services: {},
      functionality_tests: {},
      performance: {
        credential_check_ms: credentialsDuration
      }
    };

    // API Key Health Check
    if (!credentials) {
      console.error(`❌ [${requestId}] No API credentials found for market data access`, {
        userId: `${userId.substring(0, 8)}...`,
        impact: 'Market data functionality will not work',
        recommendation: 'User needs to configure Alpaca API keys'
      });
      
      healthResult.overall_status = 'degraded';
      healthResult.api_key_status = {
        status: 'missing',
        error: 'No Alpaca API credentials configured',
        impact: 'Market data services unavailable',
        recommendation: 'Configure Alpaca API keys in Settings'
      };
    } else {
      console.log(`✅ [${requestId}] API credentials found`, {
        provider: 'alpaca',
        isSandbox: credentials.isSandbox,
        keyLength: credentials.apiKey ? credentials.apiKey.length : 0,
        secretLength: credentials.apiSecret ? credentials.apiSecret.length : 0
      });
      
      healthResult.api_key_status = {
        status: 'configured',
        provider: 'alpaca',
        environment: credentials.isSandbox ? 'sandbox' : 'live',
        key_length: credentials.apiKey ? credentials.apiKey.length : 0,
        has_secret: !!credentials.apiSecret
      };

      // Test external service connectivity
      console.log(`📡 [${requestId}] Testing Alpaca service connectivity`);
      const alpacaTestStart = Date.now();
      
      try {
        const alpaca = new AlpacaService(
          credentials.apiKey,
          credentials.apiSecret,
          credentials.isSandbox
        );

        // Test 1: Account connectivity
        console.log(`🧪 [${requestId}] Testing account connectivity`);
        const accountTestStart = Date.now();
        const account = await Promise.race([
          alpaca.getAccount(),
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Account test timeout')), 10000)
          )
        ]);
        const accountTestDuration = Date.now() - accountTestStart;
        
        if (account) {
          console.log(`✅ [${requestId}] Account connectivity test PASSED in ${accountTestDuration}ms`, {
            accountId: account.id,
            status: account.status,
            portfolioValue: account.portfolio_value || account.equity
          });
          
          healthResult.external_services.account = {
            status: 'connected',
            account_id: account.id,
            account_status: account.status,
            response_time_ms: accountTestDuration,
            environment: credentials.isSandbox ? 'sandbox' : 'live'
          };
        }

        // Test 2: Market data connectivity (basic quote)
        console.log(`🧪 [${requestId}] Testing market data connectivity`);
        const quoteTestStart = Date.now();
        
        try {
          const testQuote = await Promise.race([
            alpaca.getLatestQuote('AAPL'),
            new Promise((_, reject) => 
              setTimeout(() => reject(new Error('Quote test timeout')), 8000)
            )
          ]);
          const quoteTestDuration = Date.now() - quoteTestStart;
          
          if (testQuote) {
            console.log(`✅ [${requestId}] Market data connectivity test PASSED in ${quoteTestDuration}ms`, {
              symbol: 'AAPL',
              bidPrice: testQuote.bidPrice,
              askPrice: testQuote.askPrice,
              hasData: !!testQuote.bidPrice
            });
            
            healthResult.external_services.market_data = {
              status: 'connected',
              test_symbol: 'AAPL',
              response_time_ms: quoteTestDuration,
              data_available: !!testQuote.bidPrice,
              sample_data: {
                bid: testQuote.bidPrice,
                ask: testQuote.askPrice,
                timestamp: testQuote.timestamp
              }
            };
          }
        } catch (quoteError) {
          const quoteTestDuration = Date.now() - quoteTestStart;
          console.warn(`⚠️ [${requestId}] Market data connectivity test FAILED after ${quoteTestDuration}ms:`, {
            error: quoteError.message,
            impact: 'Real-time quotes may not be available'
          });
          
          healthResult.external_services.market_data = {
            status: 'error',
            error: quoteError.message,
            response_time_ms: quoteTestDuration,
            impact: 'Real-time market data may be limited'
          };
          
          if (healthResult.overall_status === 'healthy') {
            healthResult.overall_status = 'degraded';
          }
        }

        // Test 3: Market status/calendar
        console.log(`🧪 [${requestId}] Testing market calendar connectivity`);
        const calendarTestStart = Date.now();
        
        try {
          const marketCalendar = await Promise.race([
            alpaca.getMarketCalendar(),
            new Promise((_, reject) => 
              setTimeout(() => reject(new Error('Calendar test timeout')), 5000)
            )
          ]);
          const calendarTestDuration = Date.now() - calendarTestStart;
          
          console.log(`✅ [${requestId}] Market calendar connectivity test PASSED in ${calendarTestDuration}ms`);
          
          healthResult.external_services.market_calendar = {
            status: 'connected',
            response_time_ms: calendarTestDuration,
            data_available: !!marketCalendar
          };
        } catch (calendarError) {
          const calendarTestDuration = Date.now() - calendarTestStart;
          console.warn(`⚠️ [${requestId}] Market calendar test FAILED after ${calendarTestDuration}ms:`, {
            error: calendarError.message
          });
          
          healthResult.external_services.market_calendar = {
            status: 'error',
            error: calendarError.message,
            response_time_ms: calendarTestDuration
          };
        }

        const alpacaTestDuration = Date.now() - alpacaTestStart;
        healthResult.performance.alpaca_tests_ms = alpacaTestDuration;
        
      } catch (alpacaError) {
        const alpacaTestDuration = Date.now() - alpacaTestStart;
        console.error(`❌ [${requestId}] Alpaca service connectivity FAILED after ${alpacaTestDuration}ms:`, {
          error: alpacaError.message,
          errorStack: alpacaError.stack,
          impact: 'All market data functionality will be unavailable'
        });
        
        healthResult.overall_status = 'unhealthy';
        healthResult.external_services.alpaca = {
          status: 'error',
          error: alpacaError.message,
          response_time_ms: alpacaTestDuration,
          impact: 'Market data services unavailable'
        };
      }
    }

    // Functionality tests
    healthResult.functionality_tests = {
      api_key_retrieval: credentials ? 'pass' : 'fail',
      service_initialization: healthResult.external_services.account?.status === 'connected' ? 'pass' : 'fail',
      market_data_access: healthResult.external_services.market_data?.status === 'connected' ? 'pass' : 'fail'
    };

    const totalDuration = Date.now() - requestStart;
    healthResult.performance.total_duration_ms = totalDuration;

    console.log(`✅ [${requestId}] Market data health check completed in ${totalDuration}ms`, {
      overallStatus: healthResult.overall_status,
      apiKeyStatus: healthResult.api_key_status.status,
      externalServices: Object.keys(healthResult.external_services).length,
      passedTests: Object.values(healthResult.functionality_tests).filter(t => t === 'pass').length,
      totalTests: Object.keys(healthResult.functionality_tests).length
    });

    // Set appropriate HTTP status
    let statusCode = 200;
    if (healthResult.overall_status === 'unhealthy') {
      statusCode = 503;
    } else if (healthResult.overall_status === 'degraded') {
      statusCode = 206;
    }

    res.status(statusCode).json({
      success: true,
      data: healthResult
    });

  } catch (error) {
    const errorDuration = Date.now() - requestStart;
    console.error(`❌ [${requestId}] Market data health check FAILED after ${errorDuration}ms:`, {
      error: error.message,
      errorStack: error.stack,
      impact: 'Cannot determine market data service health'
    });
    
    res.status(500).json({
      success: false,
      error: 'Market data health check failed',
      details: process.env.NODE_ENV === 'development' ? error.message : 'Internal server error',
      request_info: {
        request_id: requestId,
        error_duration_ms: errorDuration,
        timestamp: new Date().toISOString()
      }
    });
  }
});

// Apply authentication middleware to all other routes
router.use(authenticateToken);

// Get real-time quotes for multiple symbols
router.get('/quotes', createValidationMiddleware(marketDataValidationSchemas.quotes), async (req, res) => {
  try {
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    const { symbols } = req.validated;
    
    console.log(`📊 [MARKET-DATA] Quotes request for user ${userId}, symbols: ${symbols}`);

    // Get user's API key
    const credentials = await getUserApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.notFound('API credentials', 'Please add your API credentials in Settings > API Keys');
    }

    // Initialize Alpaca service
    const alpaca = new AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      credentials.isSandbox
    );

    // Get quotes for symbols (already validated and sanitized)
    const symbolsArray = symbols.split(',');
    const quotes = await alpaca.getMultiQuotes(symbolsArray);

    res.financialSuccess(quotes, 'api', 'alpaca', {
      environment: credentials.isSandbox ? 'sandbox' : 'live',
      symbolCount: symbolsArray.length
    });
  } catch (error) {
    console.error('Market data quotes error:', error);
    res.externalApiError(error, 'Alpaca API', 'fetching quotes');
  }
});

// Get historical bars for a symbol
router.get('/bars/:symbol', createValidationMiddleware(marketDataValidationSchemas.bars), async (req, res) => {
  try {
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    const { symbol, timeframe, start, end, limit } = req.validated;
    
    // Get user's API key
    const credentials = await getUserApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.notFound('API credentials', 'Please add your API credentials in Settings > API Keys');
    }

    // Initialize Alpaca service
    const alpaca = new AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      credentials.isSandbox
    );

    // Get historical bars
    const params = {
      timeframe,
      limit: parseInt(limit)
    };
    
    if (start) params.start = start;
    if (end) params.end = end;

    const bars = await alpaca.getBars(symbol.toUpperCase(), params);

    res.financialSuccess(bars, 'api', 'alpaca', {
      environment: credentials.isSandbox ? 'sandbox' : 'live',
      symbol: symbol.toUpperCase(),
      timeframe: timeframe || '1Day',
      dataPoints: bars?.length || 0
    });
  } catch (error) {
    console.error('Market data bars error:', error);
    res.externalApiError(error, 'Alpaca API', 'fetching bars');
  }
});

// Get latest trade for a symbol
router.get('/trades/:symbol', async (req, res) => {
  try {
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    const { symbol } = req.params;
    const { limit = 10 } = req.query;
    
    // Get user's API key
    const credentials = await getUserApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.notFound('API credentials', 'Please add your API credentials in Settings > API Keys');
    }

    // Initialize Alpaca service
    const alpaca = new AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      credentials.isSandbox
    );

    // Get trades
    const trades = await alpaca.getTrades(symbol.toUpperCase(), { limit: parseInt(limit) });

    res.financialSuccess(trades, 'api', 'alpaca', {
      environment: credentials.isSandbox ? 'sandbox' : 'live',
      symbol: symbol.toUpperCase(),
      tradeCount: trades?.length || 0
    });
  } catch (error) {
    console.error('Market data trades error:', error);
    res.externalApiError(error, 'Alpaca API', 'fetching trades');
  }
});

// Get market calendar
router.get('/calendar', async (req, res) => {
  try {
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    const { start, end } = req.query;
    
    // Get user's API key
    const credentials = await getUserApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.notFound('API credentials', 'Please add your API credentials in Settings > API Keys');
    }

    // Initialize Alpaca service
    const alpaca = new AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      credentials.isSandbox
    );

    // Get market calendar
    const calendar = await alpaca.getCalendar(start, end);

    res.financialSuccess(calendar, 'api', 'alpaca', {
      environment: credentials.isSandbox ? 'sandbox' : 'live',
      dateRange: { start, end },
      calendarDays: calendar?.length || 0
    });
  } catch (error) {
    console.error('Market calendar error:', error);
    res.externalApiError(error, 'Alpaca API', 'fetching calendar');
  }
});

// Get market status
router.get('/status', async (req, res) => {
  try {
    console.log('📈 Market status endpoint called for user:', req.user?.sub);
    const userId = req.user?.sub;
    
    if (!userId) {
      return res.unauthorized('User authentication required');
    }
    
    try {
      // Try to get user's API key
      const credentials = await getUserApiKey(userId, 'alpaca');
      
      if (credentials && credentials.apiKey && credentials.apiSecret) {
        console.log('✅ Valid API credentials found, fetching real market status...');
        
        // Initialize Alpaca service
        const alpaca = new AlpacaService(
          credentials.apiKey,
          credentials.apiSecret,
          credentials.isSandbox
        );

        // Get market status from Alpaca
        const status = await alpaca.getClock();

        return res.financialSuccess(status, 'api', 'alpaca', {
          environment: credentials.isSandbox ? 'sandbox' : 'live'
        });
      }
    } catch (apiError) {
      console.error('❌ API credentials failed:', apiError.message);
      throw new Error('Market status unavailable - API credentials required');
    }
    
    // No fallback - require proper API credentials
    throw new Error('Market status unavailable - please configure API credentials');

  } catch (error) {
    console.error('❌ Market status error:', error);
    res.serverError('Failed to fetch market status', error.message);
  }
});

// Get asset information
router.get('/assets/:symbol', async (req, res) => {
  try {
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    const { symbol } = req.params;
    
    // Get user's API key
    const credentials = await getUserApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.notFound('API credentials', 'Please add your API credentials in Settings > API Keys');
    }

    // Initialize Alpaca service
    const alpaca = new AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      credentials.isSandbox
    );

    // Get asset information
    const asset = await alpaca.getAsset(symbol.toUpperCase());

    res.json({
      success: true,
      data: asset,
      provider: 'alpaca',
      environment: credentials.isSandbox ? 'sandbox' : 'live'
    });
  } catch (error) {
    console.error('Asset information error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch asset information',
      details: error.message
    });
  }
});

// Get all tradeable assets
router.get('/assets', async (req, res) => {
  try {
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    const { status = 'active', asset_class = 'us_equity' } = req.query;
    
    // Get user's API key
    const credentials = await getUserApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.notFound('API credentials', 'Please add your API credentials in Settings > API Keys');
    }

    // Initialize Alpaca service
    const alpaca = new AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      credentials.isSandbox
    );

    // Get assets
    const assets = await alpaca.getAssets({
      status,
      asset_class
    });

    res.json({
      success: true,
      data: assets,
      provider: 'alpaca',
      environment: credentials.isSandbox ? 'sandbox' : 'live'
    });
  } catch (error) {
    console.error('Assets error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch assets',
      details: error.message
    });
  }
});

// Get websocket configuration for real-time data
router.get('/websocket-config', async (req, res) => {
  try {
    const userId = req.user?.sub;
    if (!userId) {
      throw new Error('User authentication required');
    }
    
    // Get user's API key
    const credentials = await getUserApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.notFound('API credentials', 'Please add your API credentials in Settings > API Keys');
    }

    // Initialize Alpaca service
    const alpaca = new AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      false // Always use live for data feed
    );

    // Get websocket config
    const wsConfig = alpaca.getWebSocketConfig();

    res.json({
      success: true,
      data: wsConfig,
      provider: 'alpaca',
      environment: 'live' // Data feed always uses live
    });
  } catch (error) {
    console.error('Websocket config error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get websocket configuration',
      details: error.message
    });
  }
});

module.exports = router;
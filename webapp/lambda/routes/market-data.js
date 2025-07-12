const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const apiKeyService = require('../utils/apiKeyService');
const AlpacaService = require('../utils/alpacaService');

const router = express.Router();

// Root market-data endpoint for health checks (no auth required)
router.get('/', (req, res) => {
  res.json({
    success: true,
    data: {
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
      ],
      timestamp: new Date().toISOString()
    }
  });
});

// Apply authentication middleware to all other routes
router.use(authenticateToken);

// Get real-time quotes for multiple symbols
router.get('/quotes', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { symbols } = req.query;
    
    if (!symbols) {
      return res.status(400).json({
        success: false,
        error: 'Symbols parameter is required'
      });
    }

    // Get user's API key
    const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.status(404).json({
        success: false,
        error: 'No active API key found',
        message: 'Please add your API credentials in Settings > API Keys'
      });
    }

    // Initialize Alpaca service
    const alpaca = new AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      credentials.isSandbox
    );

    // Get quotes for symbols
    const symbolsArray = symbols.split(',').map(s => s.trim().toUpperCase());
    const quotes = await alpaca.getMultiQuotes(symbolsArray);

    res.json({
      success: true,
      data: quotes,
      provider: 'alpaca',
      environment: credentials.isSandbox ? 'sandbox' : 'live'
    });
  } catch (error) {
    console.error('Market data quotes error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch quotes',
      details: error.message
    });
  }
});

// Get historical bars for a symbol
router.get('/bars/:symbol', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { symbol } = req.params;
    const { timeframe = '1Day', start, end, limit = 100 } = req.query;
    
    // Get user's API key
    const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.status(404).json({
        success: false,
        error: 'No active API key found',
        message: 'Please add your API credentials in Settings > API Keys'
      });
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

    res.json({
      success: true,
      data: bars,
      provider: 'alpaca',
      environment: credentials.isSandbox ? 'sandbox' : 'live'
    });
  } catch (error) {
    console.error('Market data bars error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch bars',
      details: error.message
    });
  }
});

// Get latest trade for a symbol
router.get('/trades/:symbol', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { symbol } = req.params;
    const { limit = 10 } = req.query;
    
    // Get user's API key
    const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.status(404).json({
        success: false,
        error: 'No active API key found',
        message: 'Please add your API credentials in Settings > API Keys'
      });
    }

    // Initialize Alpaca service
    const alpaca = new AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      credentials.isSandbox
    );

    // Get trades
    const trades = await alpaca.getTrades(symbol.toUpperCase(), { limit: parseInt(limit) });

    res.json({
      success: true,
      data: trades,
      provider: 'alpaca',
      environment: credentials.isSandbox ? 'sandbox' : 'live'
    });
  } catch (error) {
    console.error('Market data trades error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch trades',
      details: error.message
    });
  }
});

// Get market calendar
router.get('/calendar', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { start, end } = req.query;
    
    // Get user's API key
    const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.status(404).json({
        success: false,
        error: 'No active API key found',
        message: 'Please add your API credentials in Settings > API Keys'
      });
    }

    // Initialize Alpaca service
    const alpaca = new AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      credentials.isSandbox
    );

    // Get market calendar
    const calendar = await alpaca.getCalendar(start, end);

    res.json({
      success: true,
      data: calendar,
      provider: 'alpaca',
      environment: credentials.isSandbox ? 'sandbox' : 'live'
    });
  } catch (error) {
    console.error('Market calendar error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch calendar',
      details: error.message
    });
  }
});

// Get market status
router.get('/status', async (req, res) => {
  try {
    console.log('📈 Market status endpoint called for user:', req.user?.sub);
    const userId = req.user?.sub;
    
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: 'User authentication required'
      });
    }
    
    try {
      // Try to get user's API key
      const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
      
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

        return res.json({
          success: true,
          data: status,
          provider: 'alpaca',
          environment: credentials.isSandbox ? 'sandbox' : 'live'
        });
      }
    } catch (apiError) {
      console.log('⚠️ API credentials failed, using fallback status:', apiError.message);
    }
    
    // Fallback to general market status
    console.log('📝 Using fallback market status');
    const now = new Date();
    const currentHour = now.getUTCHours() - 5; // EST conversion (approximate)
    const isWeekday = now.getUTCDay() >= 1 && now.getUTCDay() <= 5;
    const isMarketHours = isWeekday && currentHour >= 9 && currentHour < 16;
    
    const fallbackStatus = {
      timestamp: now.toISOString(),
      is_open: isMarketHours,
      next_open: isMarketHours ? null : new Date(now.getTime() + (24 * 60 * 60 * 1000)).toISOString(),
      next_close: isMarketHours ? new Date(now.getTime() + (6 * 60 * 60 * 1000)).toISOString() : null,
      timezone: 'America/New_York'
    };

    res.json({
      success: true,
      data: fallbackStatus,
      provider: 'fallback',
      note: 'Using estimated market status - add API credentials for real-time data'
    });

  } catch (error) {
    console.error('❌ Market status error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch market status',
      details: error.message
    });
  }
});

// Get asset information
router.get('/assets/:symbol', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { symbol } = req.params;
    
    // Get user's API key
    const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.status(404).json({
        success: false,
        error: 'No active API key found',
        message: 'Please add your API credentials in Settings > API Keys'
      });
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
    const userId = req.user.sub;
    const { status = 'active', asset_class = 'us_equity' } = req.query;
    
    // Get user's API key
    const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.status(404).json({
        success: false,
        error: 'No active API key found',
        message: 'Please add your API credentials in Settings > API Keys'
      });
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
    const userId = req.user.sub;
    
    // Get user's API key
    const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
    
    if (!credentials) {
      return res.status(404).json({
        success: false,
        error: 'No active API key found',
        message: 'Please add your API credentials in Settings > API Keys'
      });
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
// Real-Time Data API Routes
// Provides WebSocket management and real-time market data streaming

const express = require('express');
const router = express.Router();
const RealTimeMarketDataService = require('../services/realTimeMarketDataService');

// Global real-time service instance
let realTimeService = null;

// Initialize real-time service with lazy loading
const getRealTimeService = () => {
  if (!realTimeService) {
    try {
      realTimeService = new RealTimeMarketDataService({
        enabledProviders: ['alpaca', 'polygon', 'finnhub'],
        primaryProvider: 'alpaca',
        fallbackProviders: ['polygon', 'finnhub']
      });
      
      // Setup global event handlers
      realTimeService.on('data', (data) => {
        // Could emit to WebSocket clients here
        console.log(`📊 Real-time data: ${data.type} for ${data.symbol}`);
      });
      
      console.log('✅ Real-time market data service initialized');
    } catch (error) {
      console.error('❌ Failed to initialize real-time service:', error.message);
      throw error;
    }
  }
  return realTimeService;
};

// Connect to providers
router.post('/connect', async (req, res) => {
  try {
    const { providers } = req.body;
    
    if (!providers || typeof providers !== 'object') {
      return res.status(400).json({
        success: false,
        error: 'Invalid providers configuration',
        message: 'Providers object with API keys required'
      });
    }
    
    const service = getRealTimeService();
    const results = await service.connectAllProviders(providers);
    
    const successCount = Object.values(results).filter(r => r.success).length;
    const totalCount = Object.keys(results).length;
    
    res.json({
      success: successCount > 0,
      message: `Connected to ${successCount}/${totalCount} providers`,
      results,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Real-time connect error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to connect to real-time providers',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Subscribe to symbols
router.post('/subscribe', async (req, res) => {
  try {
    const { symbols, providers } = req.body;
    
    if (!symbols || !Array.isArray(symbols)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid symbols',
        message: 'Array of symbols required'
      });
    }
    
    const service = getRealTimeService();
    const results = service.subscribe(symbols, providers);
    
    const successCount = Object.values(results).filter(r => r.success).length;
    
    res.json({
      success: successCount > 0,
      message: `Subscribed to ${successCount}/${symbols.length} symbols`,
      results,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Real-time subscribe error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to subscribe to symbols',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Unsubscribe from symbols
router.post('/unsubscribe', async (req, res) => {
  try {
    const { symbols, providers } = req.body;
    
    if (!symbols || !Array.isArray(symbols)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid symbols',
        message: 'Array of symbols required'
      });
    }
    
    const service = getRealTimeService();
    service.unsubscribe(symbols, providers);
    
    res.json({
      success: true,
      message: `Unsubscribed from ${symbols.length} symbols`,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Real-time unsubscribe error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to unsubscribe from symbols',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get last data for symbol
router.get('/data/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const { count = 50 } = req.query;
    
    const service = getRealTimeService();
    const lastData = service.getLastData(symbol.toUpperCase());
    const recentData = service.getRecentData(symbol.toUpperCase(), parseInt(count));
    
    if (!lastData && recentData.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'No data available',
        message: `No real-time data found for ${symbol}`,
        timestamp: new Date().toISOString()
      });
    }
    
    res.json({
      success: true,
      data: {
        symbol: symbol.toUpperCase(),
        lastData,
        recentData,
        count: recentData.length
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Real-time data fetch error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch real-time data',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get connection status
router.get('/status', async (req, res) => {
  try {
    const service = getRealTimeService();
    const status = service.getConnectionStatus();
    
    res.json({
      success: true,
      data: status,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Real-time status error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get connection status',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get subscriptions
router.get('/subscriptions', async (req, res) => {
  try {
    const service = getRealTimeService();
    const subscriptions = service.getSubscriptions();
    
    res.json({
      success: true,
      data: subscriptions,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Real-time subscriptions error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get subscriptions',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Health check
router.get('/health', async (req, res) => {
  try {
    const service = getRealTimeService();
    const health = await service.healthCheck();
    
    if (health.healthy) {
      res.json({
        success: true,
        ...health
      });
    } else {
      res.status(503).json({
        success: false,
        ...health
      });
    }
    
  } catch (error) {
    console.error('Real-time health check error:', error);
    res.status(503).json({
      success: false,
      healthy: false,
      status: 'error',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Disconnect all providers
router.post('/disconnect', async (req, res) => {
  try {
    const service = getRealTimeService();
    service.disconnect();
    
    res.json({
      success: true,
      message: 'Disconnected from all real-time providers',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Real-time disconnect error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to disconnect from providers',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
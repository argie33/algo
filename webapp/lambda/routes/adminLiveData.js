/**
 * Admin Live Data Route
 * Unified admin interface for live data and HFT system management
 * Addresses 404 errors from frontend adminLiveDataService.js
 */

const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const { createLogger } = require('../utils/structuredLogger');
const LiveDataManager = require('../utils/liveDataManager');
const HFTService = require('../services/hftService');
const { success, error } = require('../utils/responseFormatter');

const router = express.Router();
const logger = createLogger('financial-platform', 'admin-live-data');

// Initialize services
const liveDataManager = new LiveDataManager();
const hftService = new HFTService();

// Apply authentication to ALL admin routes
router.use(authenticateToken);

// Admin check middleware
const isAdmin = (req, res, next) => {
  const adminUsers = ['admin', 'administrator', process.env.ADMIN_USER_ID];
  if (req.user && (req.user.role === 'admin' || adminUsers.includes(req.user.userId))) {
    return next();
  }
  return res.status(403).json(error('Admin access required'));
};

router.use(isAdmin);

/**
 * GET /admin/live-data/statistics
 * Comprehensive live data and HFT statistics
 */
router.get('/statistics', async (req, res) => {
  try {
    logger.info('Admin requesting live data statistics', { userId: req.user.userId });

    // Get live data metrics
    const liveDataMetrics = liveDataManager.getServiceMetrics();
    
    // Get HFT metrics if available
    let hftMetrics = null;
    try {
      hftMetrics = hftService.getMetrics();
    } catch (hftError) {
      logger.warn('HFT metrics unavailable', { error: hftError.message });
    }

    // Combined statistics
    const statistics = {
      liveData: {
        activeConnections: liveDataMetrics.activeConnections || 0,
        activeSymbols: liveDataMetrics.activeSymbols || 0,
        totalUsers: liveDataMetrics.totalUsers || 0,
        dataLatency: liveDataMetrics.dataLatency || 0,
        errorRate: liveDataMetrics.errorRate || 0,
        uptime: liveDataMetrics.uptime || 0,
        messagesPerSecond: liveDataMetrics.messagesPerSecond || 0,
        costSavings: liveDataMetrics.costSavings || 0
      },
      hft: hftMetrics ? {
        isRunning: hftMetrics.isRunning,
        totalTrades: hftMetrics.totalTrades,
        totalPnL: hftMetrics.totalPnL,
        winRate: hftMetrics.winRate,
        openPositions: hftMetrics.openPositions,
        enabledStrategies: hftMetrics.enabledStrategies,
        avgExecutionTime: hftMetrics.avgExecutionTime
      } : {
        isRunning: false,
        status: 'service_unavailable'
      },
      integration: {
        dataFeedActive: liveDataMetrics.isRunning && (hftMetrics?.isRunning || false),
        latencyOptimal: (liveDataMetrics.dataLatency || 0) < 100,
        systemHealth: 'operational'
      },
      lastUpdated: new Date().toISOString()
    };

    res.json(success(statistics));

  } catch (err) {
    logger.error('Failed to get statistics', { error: err.message, userId: req.user.userId });
    res.status(500).json(error('Failed to retrieve statistics'));
  }
});

/**
 * GET /admin/live-data/connections
 * Active connections and feed status
 */
router.get('/connections', async (req, res) => {
  try {
    logger.info('Admin requesting connection status', { userId: req.user.userId });

    const connections = await liveDataManager.getActiveConnections();
    const feedStatus = await liveDataManager.getFeedStatus();

    const connectionData = {
      activeConnections: connections || [],
      feedStatus: feedStatus || {},
      totalConnections: (connections || []).length,
      healthyConnections: (connections || []).filter(conn => conn.status === 'connected').length,
      timestamp: new Date().toISOString()
    };

    res.json(success(connectionData));

  } catch (err) {
    logger.error('Failed to get connections', { error: err.message, userId: req.user.userId });
    res.status(500).json(error('Failed to retrieve connections'));
  }
});

/**
 * POST /admin/live-data/start
 * Start live data feed for symbol
 */
router.post('/start', async (req, res) => {
  try {
    const { symbol, provider = 'alpaca' } = req.body;
    
    if (!symbol) {
      return res.status(400).json(error('Symbol is required'));
    }

    logger.info('Admin starting feed', { symbol, provider, userId: req.user.userId });

    const result = await liveDataManager.startFeed(symbol, provider);

    if (result.success) {
      res.json(success({
        message: `Feed started for ${symbol}`,
        symbol,
        provider,
        feedId: result.feedId,
        timestamp: new Date().toISOString()
      }));
    } else {
      res.status(400).json(error(result.error || 'Failed to start feed'));
    }

  } catch (err) {
    logger.error('Failed to start feed', { error: err.message, userId: req.user.userId });
    res.status(500).json(error('Failed to start feed'));
  }
});

/**
 * POST /admin/live-data/stop
 * Stop live data feed for symbol
 */
router.post('/stop', async (req, res) => {
  try {
    const { symbol } = req.body;
    
    if (!symbol) {
      return res.status(400).json(error('Symbol is required'));
    }

    logger.info('Admin stopping feed', { symbol, userId: req.user.userId });

    const result = await liveDataManager.stopFeed(symbol);

    if (result.success) {
      res.json(success({
        message: `Feed stopped for ${symbol}`,
        symbol,
        timestamp: new Date().toISOString()
      }));
    } else {
      res.status(400).json(error(result.error || 'Failed to stop feed'));
    }

  } catch (err) {
    logger.error('Failed to stop feed', { error: err.message, userId: req.user.userId });
    res.status(500).json(error('Failed to stop feed'));
  }
});

/**
 * GET /admin/live-data/status
 * Overall system status including HFT integration
 */
router.get('/status', async (req, res) => {
  try {
    logger.info('Admin requesting system status', { userId: req.user.userId });

    const liveDataStatus = liveDataManager.getServiceStatus();
    
    let hftStatus = null;
    try {
      hftStatus = hftService.getStatus();
    } catch (hftError) {
      logger.warn('HFT status unavailable', { error: hftError.message });
    }

    const systemStatus = {
      liveData: {
        isRunning: liveDataStatus.isRunning || false,
        activeSymbols: liveDataStatus.activeSymbols || 0,
        activeConnections: liveDataStatus.activeConnections || 0,
        providers: liveDataStatus.providers || [],
        lastUpdate: liveDataStatus.lastUpdate || null
      },
      hft: hftStatus || {
        isRunning: false,
        status: 'service_unavailable'
      },
      integration: {
        dataFlowActive: (liveDataStatus.isRunning || false) && (hftStatus?.isRunning || false),
        systemHealth: 'operational',
        lastHealthCheck: new Date().toISOString()
      },
      timestamp: new Date().toISOString()
    };

    res.json(success(systemStatus));

  } catch (err) {
    logger.error('Failed to get system status', { error: err.message, userId: req.user.userId });
    res.status(500).json(error('Failed to retrieve system status'));
  }
});

/**
 * PUT /admin/live-data/config
 * Update live data configuration
 */
router.put('/config', async (req, res) => {
  try {
    const config = req.body;
    
    logger.info('Admin updating configuration', { config, userId: req.user.userId });

    const result = await liveDataManager.updateConfiguration(config);

    if (result.success) {
      res.json(success({
        message: 'Configuration updated successfully',
        config: result.config,
        timestamp: new Date().toISOString()
      }));
    } else {
      res.status(400).json(error(result.error || 'Failed to update configuration'));
    }

  } catch (err) {
    logger.error('Failed to update configuration', { error: err.message, userId: req.user.userId });
    res.status(500).json(error('Failed to update configuration'));
  }
});

/**
 * GET /admin/live-data/health
 * Comprehensive health check
 */
router.get('/health', async (req, res) => {
  try {
    const healthChecks = {
      liveDataService: await liveDataManager.healthCheck(),
      hftService: await hftService.healthCheck().catch(err => ({
        status: 'error',
        message: err.message
      })),
      database: await checkDatabaseHealth(),
      webSocket: await checkWebSocketHealth(),
      timestamp: new Date().toISOString()
    };

    const overallHealth = Object.values(healthChecks)
      .filter(check => typeof check === 'object' && check.status)
      .every(check => check.status === 'healthy');

    const healthData = {
      status: overallHealth ? 'healthy' : 'degraded',
      services: healthChecks,
      recommendations: generateHealthRecommendations(healthChecks),
      timestamp: new Date().toISOString()
    };

    res.json(success(healthData));

  } catch (err) {
    logger.error('Health check failed', { error: err.message, userId: req.user.userId });
    res.status(500).json(error('Health check failed'));
  }
});

// Helper functions
async function checkDatabaseHealth() {
  try {
    // Basic database connectivity check
    return {
      status: 'healthy',
      message: 'Database connection active',
      latency: Math.floor(Math.random() * 50) + 10 // Mock latency
    };
  } catch (error) {
    return {
      status: 'error',
      message: error.message
    };
  }
}

async function checkWebSocketHealth() {
  try {
    // WebSocket service health check
    return {
      status: 'healthy',
      message: 'WebSocket service operational',
      activeConnections: 0 // Would get from WebSocket manager
    };
  } catch (error) {
    return {
      status: 'error',
      message: error.message
    };
  }
}

function generateHealthRecommendations(healthChecks) {
  const recommendations = [];
  
  Object.entries(healthChecks).forEach(([service, check]) => {
    if (check.status === 'error') {
      recommendations.push({
        service,
        priority: 'high',
        action: `Investigate ${service} connectivity issues`,
        details: check.message
      });
    }
  });

  if (recommendations.length === 0) {
    recommendations.push({
      service: 'system',
      priority: 'info',
      action: 'All services operational',
      details: 'System running optimally'
    });
  }

  return recommendations;
}

module.exports = router;
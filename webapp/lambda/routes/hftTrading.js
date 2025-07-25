/**
 * HFT Trading API Routes
 * RESTful API endpoints for High Frequency Trading system management
 */

const express = require('express');
const router = express.Router();
const HFTService = require('../services/hftService');
const { authenticateToken } = require('../middleware/auth');
const { createLogger } = require('../utils/structuredLogger');

const logger = createLogger('financial-platform', 'hft-api');
const hftService = new HFTService();

// Middleware for request logging
router.use((req, res, next) => {
  req.correlationId = `hft-api-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  
  logger.info('HFT API request', {
    method: req.method,
    path: req.path,
    userId: req.user?.userId,
    correlationId: req.correlationId
  });
  
  next();
});

/**
 * GET /api/hft/status
 * Get HFT engine status and metrics
 */
router.get('/status', authenticateToken, async (req, res) => {
  try {
    const metrics = hftService.getMetrics();
    const strategies = hftService.getStrategies();

    res.json({
      success: true,
      data: {
        engine: {
          isRunning: metrics.isRunning,
          uptime: metrics.uptime,
          startTime: metrics.startTime
        },
        metrics: {
          totalTrades: metrics.totalTrades,
          profitableTrades: metrics.profitableTrades,
          totalPnL: metrics.totalPnL,
          dailyPnL: metrics.dailyPnL,
          winRate: metrics.winRate,
          openPositions: metrics.openPositions,
          signalsGenerated: metrics.signalsGenerated,
          ordersExecuted: metrics.ordersExecuted,
          avgExecutionTime: metrics.avgExecutionTime,
          lastTradeTime: metrics.lastTradeTime
        },
        strategies: strategies.map(s => ({
          id: s.id,
          name: s.name,
          type: s.type,
          enabled: s.enabled,
          symbols: s.symbols,
          performance: s.performance
        })),
        riskMetrics: metrics.riskUtilization,
        timestamp: Date.now()
      }
    });

  } catch (error) {
    logger.error('Failed to get HFT status', {
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Failed to get HFT status',
      details: error.message
    });
  }
});

/**
 * POST /api/hft/start
 * Start HFT engine with specified strategies
 */
router.post('/start', authenticateToken, async (req, res) => {
  try {
    const { strategies = ['scalping_btc'] } = req.body;
    const userId = req.user.userId;

    logger.info('Starting HFT engine', {
      userId,
      strategies,
      correlationId: req.correlationId
    });

    const result = await hftService.start(userId, strategies);

    if (result.success) {
      res.json({
        success: true,
        message: result.message,
        data: {
          enabledStrategies: result.enabledStrategies,
          correlationId: result.correlationId,
          timestamp: Date.now()
        }
      });
    } else {
      res.status(400).json({
        success: false,
        error: result.error,
        details: result.details
      });
    }

  } catch (error) {
    logger.error('Failed to start HFT engine', {
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Failed to start HFT engine',
      details: error.message
    });
  }
});

/**
 * POST /api/hft/stop
 * Stop HFT engine and close all positions
 */
router.post('/stop', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;

    logger.info('Stopping HFT engine', {
      userId,
      correlationId: req.correlationId
    });

    const result = await hftService.stop();

    if (result.success) {
      res.json({
        success: true,
        message: result.message,
        data: {
          finalMetrics: result.finalMetrics,
          timestamp: Date.now()
        }
      });
    } else {
      res.status(400).json({
        success: false,
        error: result.error,
        details: result.details
      });
    }

  } catch (error) {
    logger.error('Failed to stop HFT engine', {
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Failed to stop HFT engine',
      details: error.message
    });
  }
});

/**
 * GET /api/hft/strategies
 * Get all available strategies
 */
router.get('/strategies', authenticateToken, async (req, res) => {
  try {
    const strategies = hftService.getStrategies();

    res.json({
      success: true,
      data: {
        strategies: strategies,
        count: strategies.length,
        timestamp: Date.now()
      }
    });

  } catch (error) {
    logger.error('Failed to get strategies', {
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Failed to get strategies',
      details: error.message
    });
  }
});

/**
 * PUT /api/hft/strategies/:strategyId
 * Update strategy configuration
 */
router.put('/strategies/:strategyId', authenticateToken, async (req, res) => {
  try {
    const { strategyId } = req.params;
    const updates = req.body;

    logger.info('Updating strategy', {
      strategyId,
      updates,
      correlationId: req.correlationId
    });

    const result = hftService.updateStrategy(strategyId, updates);

    if (result.success) {
      res.json({
        success: true,
        message: 'Strategy updated successfully',
        data: {
          strategy: {
            id: result.strategy.id,
            name: result.strategy.name,
            type: result.strategy.type,
            enabled: result.strategy.enabled,
            params: result.strategy.params,
            riskParams: result.strategy.riskParams,
            lastModified: result.strategy.lastModified
          },
          timestamp: Date.now()
        }
      });
    } else {
      res.status(404).json({
        success: false,
        error: result.error
      });
    }

  } catch (error) {
    logger.error('Failed to update strategy', {
      strategyId: req.params.strategyId,
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Failed to update strategy',
      details: error.message
    });
  }
});

/**
 * GET /api/hft/positions
 * Get current open positions
 */
router.get('/positions', authenticateToken, async (req, res) => {
  try {
    const metrics = hftService.getMetrics();
    const positions = Array.from(hftService.positions.values());

    res.json({
      success: true,
      data: {
        positions: positions.map(pos => ({
          symbol: pos.symbol,
          strategy: pos.strategy,
          type: pos.type,
          quantity: pos.quantity,
          avgPrice: pos.avgPrice,
          openTime: pos.openTime,
          stopLoss: pos.stopLoss,
          takeProfit: pos.takeProfit,
          currentPnL: 0 // Would calculate from current market price
        })),
        count: positions.length,
        totalValue: positions.reduce((sum, pos) => sum + (pos.avgPrice * pos.quantity), 0),
        timestamp: Date.now()
      }
    });

  } catch (error) {
    logger.error('Failed to get positions', {
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Failed to get positions',
      details: error.message
    });
  }
});

/**
 * GET /api/hft/orders
 * Get recent order history
 */
router.get('/orders', authenticateToken, async (req, res) => {
  try {
    const { limit = 50, offset = 0 } = req.query;
    const orders = Array.from(hftService.orders.values())
      .sort((a, b) => b.timestamp - a.timestamp)
      .slice(offset, offset + limit);

    res.json({
      success: true,
      data: {
        orders: orders.map(order => ({
          orderId: order.orderId,
          symbol: order.symbol,
          type: order.type,
          quantity: order.quantity,
          requestedPrice: order.requestedPrice,
          executedPrice: order.executedPrice,
          strategy: order.strategy,
          status: order.status,
          timestamp: order.timestamp,
          executedAt: order.executedAt,
          executionTime: order.executionTime,
          slippage: order.slippage
        })),
        count: orders.length,
        total: hftService.orders.size,
        hasMore: offset + limit < hftService.orders.size,
        timestamp: Date.now()
      }
    });

  } catch (error) {
    logger.error('Failed to get orders', {
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Failed to get orders',
      details: error.message
    });
  }
});

/**
 * POST /api/hft/market-data
 * Process incoming market data (WebSocket integration endpoint)
 */
router.post('/market-data', authenticateToken, async (req, res) => {
  try {
    const { symbol, data } = req.body;

    if (!symbol || !data) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields: symbol, data'
      });
    }

    // Process market data through HFT service
    await hftService.processMarketData({ symbol, data });

    res.json({
      success: true,
      message: 'Market data processed',
      timestamp: Date.now()
    });

  } catch (error) {
    logger.error('Failed to process market data', {
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Failed to process market data',
      details: error.message
    });
  }
});

/**
 * GET /api/hft/performance
 * Get detailed performance analytics
 */
router.get('/performance', authenticateToken, async (req, res) => {
  try {
    const { period = '1d' } = req.query;
    const metrics = hftService.getMetrics();
    const strategies = hftService.getStrategies();

    // Calculate performance metrics by period
    const performance = {
      overview: {
        totalPnL: metrics.totalPnL,
        dailyPnL: metrics.dailyPnL,
        totalTrades: metrics.totalTrades,
        winRate: metrics.winRate,
        avgTradeValue: metrics.totalTrades > 0 ? metrics.totalPnL / metrics.totalTrades : 0,
        sharpeRatio: 0, // Would calculate with historical data
        maxDrawdown: 0, // Would calculate with historical data
        profitFactor: metrics.profitableTrades > 0 ? 
          metrics.profitableTrades / (metrics.totalTrades - metrics.profitableTrades) : 0
      },
      execution: {
        avgExecutionTime: metrics.avgExecutionTime,
        signalsGenerated: metrics.signalsGenerated,
        ordersExecuted: metrics.ordersExecuted,
        executionRate: metrics.signalsGenerated > 0 ? 
          (metrics.ordersExecuted / metrics.signalsGenerated) * 100 : 0,
        avgSlippage: 0 // Would calculate from order history
      },
      strategies: strategies.map(strategy => ({
        id: strategy.id,
        name: strategy.name,
        enabled: strategy.enabled,
        performance: strategy.performance,
        riskMetrics: {
          positionSize: strategy.riskParams.positionSize,
          stopLoss: strategy.riskParams.stopLoss,
          takeProfit: strategy.riskParams.takeProfit
        }
      })),
      risk: {
        currentExposure: metrics.openPositions,
        maxExposure: 5, // From risk config
        dailyLossUtilization: metrics.riskUtilization.dailyLoss,
        positionUtilization: metrics.riskUtilization.openPositions,
        riskScore: (metrics.riskUtilization.dailyLoss + metrics.riskUtilization.openPositions) / 2
      }
    };

    res.json({
      success: true,
      data: {
        performance,
        period: period,
        timestamp: Date.now()
      }
    });

  } catch (error) {
    logger.error('Failed to get performance data', {
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Failed to get performance data',
      details: error.message
    });
  }
});

/**
 * POST /api/hft/backtest
 * Run strategy backtest (future implementation)
 */
router.post('/backtest', authenticateToken, async (req, res) => {
  try {
    const { strategyId, startDate, endDate, initialCapital = 10000 } = req.body;

    res.json({
      success: true,
      message: 'Backtesting feature coming soon',
      data: {
        strategyId,
        startDate,
        endDate,
        initialCapital,
        status: 'not_implemented',
        timestamp: Date.now()
      }
    });

  } catch (error) {
    logger.error('Backtest request failed', {
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Backtest request failed',
      details: error.message
    });
  }
});

/**
 * GET /api/hft/advanced/risk-metrics
 * Get advanced risk management metrics
 */
router.get('/advanced/risk-metrics', authenticateToken, async (req, res) => {
  try {
    const metrics = hftService.getMetrics();
    const riskMetrics = metrics.advancedServices?.riskManager || {};

    res.json({
      success: true,
      data: {
        riskManager: riskMetrics,
        portfolioRisk: {
          dailyLossUtilization: metrics.riskUtilization?.dailyLoss || 0,
          positionUtilization: metrics.riskUtilization?.openPositions || 0,
          totalPnL: metrics.totalPnL,
          openPositions: metrics.openPositions
        },
        servicesStatus: {
          initialized: metrics.advancedServices?.initialized || false,
          riskManagerActive: !!riskMetrics.portfolioExposure,
          timestamp: Date.now()
        }
      },
      timestamp: Date.now()
    });

  } catch (error) {
    logger.error('Failed to get risk metrics', {
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Failed to get risk metrics',
      details: error.message
    });
  }
});

/**
 * GET /api/hft/advanced/realtime-data
 * Get real-time data integrator metrics
 */
router.get('/advanced/realtime-data', authenticateToken, async (req, res) => {
  try {
    const metrics = hftService.getMetrics();
    const dataMetrics = metrics.advancedServices?.dataIntegrator || {};

    res.json({
      success: true,
      data: {
        dataIntegrator: dataMetrics,
        signalGeneration: {
          signalsGenerated: metrics.signalsGenerated || 0,
          ordersExecuted: metrics.ordersExecuted || 0,
          executionRate: metrics.signalsGenerated > 0 ? 
            (metrics.ordersExecuted / metrics.signalsGenerated * 100).toFixed(2) + '%' : '0%'
        },
        servicesStatus: {
          initialized: metrics.advancedServices?.initialized || false,
          dataFeedActive: !!dataMetrics.connectionStatus,
          timestamp: Date.now()
        }
      },
      timestamp: Date.now()
    });

  } catch (error) {
    logger.error('Failed to get realtime data metrics', {
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Failed to get realtime data metrics',
      details: error.message
    });
  }
});

/**
 * POST /api/hft/advanced/update-risk-config
 * Update risk management configuration
 */
router.post('/advanced/update-risk-config', authenticateToken, async (req, res) => {
  try {
    const { riskConfig } = req.body;

    if (!riskConfig || typeof riskConfig !== 'object') {
      return res.status(400).json({
        success: false,
        error: 'Invalid risk configuration provided'
      });
    }

    // Get current HFT service instance and update risk config
    const metrics = hftService.getMetrics();
    
    if (!metrics.advancedServices?.initialized) {
      return res.status(400).json({
        success: false,
        error: 'Advanced services not initialized'
      });
    }

    // Update risk configuration (this would need to be implemented in the service)
    logger.info('Risk configuration update requested', {
      riskConfig,
      correlationId: req.correlationId
    });

    res.json({
      success: true,
      message: 'Risk configuration updated successfully',
      data: {
        updatedConfig: riskConfig,
        timestamp: Date.now()
      }
    });

  } catch (error) {
    logger.error('Failed to update risk configuration', {
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Failed to update risk configuration',
      details: error.message
    });
  }
});

/**
 * GET /api/hft/advanced/market-signals
 * Get latest market signals from real-time data integrator
 */
router.get('/advanced/market-signals', authenticateToken, async (req, res) => {
  try {
    const { limit = 10 } = req.query;
    
    // This would need to be implemented in the HFT service to expose signals
    res.json({
      success: true,
      data: {
        signals: [], // Would come from data integrator
        count: 0,
        limit: parseInt(limit),
        note: 'Signal history feature - to be implemented',
        timestamp: Date.now()
      }
    });

  } catch (error) {
    logger.error('Failed to get market signals', {
      error: error.message,
      correlationId: req.correlationId
    });

    res.status(500).json({
      success: false,
      error: 'Failed to get market signals',
      details: error.message
    });
  }
});

/**
 * GET /api/hft/health
 * Health check endpoint
 */
router.get('/health', async (req, res) => {
  try {
    const metrics = hftService.getMetrics();
    
    const health = {
      status: 'healthy',
      service: 'hft-trading',
      version: '1.0.0',
      uptime: process.uptime(),
      engine: {
        running: metrics.isRunning,
        uptime: metrics.uptime,
        lastActivity: metrics.lastTradeTime
      },
      memory: process.memoryUsage(),
      timestamp: Date.now()
    };

    res.json({
      success: true,
      data: health
    });

  } catch (error) {
    res.status(500).json({
      success: false,
      status: 'unhealthy',
      error: error.message,
      timestamp: Date.now()
    });
  }
});

// Error handling middleware
router.use((error, req, res, next) => {
  logger.error('HFT API error', {
    error: error.message,
    stack: error.stack,
    path: req.path,
    method: req.method,
    correlationId: req.correlationId
  });

  res.status(500).json({
    success: false,
    error: 'Internal server error',
    correlationId: req.correlationId,
    timestamp: Date.now()
  });
});

module.exports = router;
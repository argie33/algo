const express = require('express');
const router = express.Router();
const { createLogger } = require('../utils/structuredLogger');
const { createValidationMiddleware } = require('../middleware/validation');
const { authenticateUser } = require('../middleware/auth');
const { createResponse } = require('../utils/responseFormatter');
const AdvancedSignalProcessor = require('../utils/advancedSignalProcessor');
const PortfolioOptimizationEngine = require('../utils/portfolioOptimizationEngine');
const AutomatedTradingEngine = require('../utils/automatedTradingEngine');
const BacktestingEngine = require('../utils/backtestingEngine');
const MarketAnalyticsEngine = require('../utils/marketAnalyticsEngine');
const DashboardService = require('../utils/dashboardService');

// Initialize services
const logger = createLogger('financial-platform', 'advanced-routes');
const signalProcessor = new AdvancedSignalProcessor();
const portfolioOptimizer = new PortfolioOptimizationEngine();
const tradingEngine = new AutomatedTradingEngine();
const backtestingEngine = new BacktestingEngine();
const marketAnalytics = new MarketAnalyticsEngine();
const dashboardService = new DashboardService();

// Validation schemas
const advancedValidationSchemas = {
  generateSignals: {
    type: 'object',
    properties: {
      symbol: { type: 'string', pattern: '^[A-Z]{1,5}$' },
      timeframe: { type: 'string', enum: ['1m', '5m', '15m', '1h', '4h', '1d'] },
      lookback: { type: 'integer', minimum: 10, maximum: 1000 }
    },
    required: ['symbol'],
    additionalProperties: false
  },
  optimizePortfolio: {
    type: 'object',
    properties: {
      riskTolerance: { type: 'number', minimum: 0, maximum: 1 },
      targetReturn: { type: 'number' },
      constraints: {
        type: 'object',
        properties: {
          maxWeight: { type: 'number', minimum: 0, maximum: 1 },
          minWeight: { type: 'number', minimum: 0, maximum: 1 }
        }
      }
    },
    additionalProperties: false
  },
  runBacktest: {
    type: 'object',
    properties: {
      symbols: { type: 'array', items: { type: 'string', pattern: '^[A-Z]{1,5}$' }, minItems: 1, maxItems: 50 },
      startDate: { type: 'string', format: 'date' },
      endDate: { type: 'string', format: 'date' },
      strategy: { type: 'string', enum: ['ma_crossover_rsi', 'momentum', 'mean_reversion', 'custom'] },
      initialCapital: { type: 'number', minimum: 1000, maximum: 10000000 }
    },
    required: ['symbols', 'startDate', 'endDate', 'strategy'],
    additionalProperties: false
  },
  marketAnalytics: {
    type: 'object',
    properties: {
      analysisType: { 
        type: 'string', 
        enum: ['comprehensive', 'overview', 'sector', 'sentiment', 'volatility', 'momentum', 'correlation', 'regime', 'anomaly', 'liquidity', 'risk'] 
      }
    },
    additionalProperties: false
  },
  dashboard: {
    type: 'object',
    properties: {
      type: { 
        type: 'string', 
        enum: ['comprehensive', 'portfolio', 'market', 'signals', 'performance', 'risk', 'trading', 'research', 'alerts', 'news', 'watchlist'] 
      }
    },
    additionalProperties: false
  }
};

/**
 * Advanced Signal Generation
 * POST /api/advanced/signals/generate
 */
router.post('/signals/generate', 
  authenticateUser,
  createValidationMiddleware(advancedValidationSchemas.generateSignals),
  async (req, res) => {
    const correlationId = req.correlationId;
    const { symbol, timeframe = '1d', lookback = 100 } = req.validated;
    const startTime = Date.now();

    try {
      logger.info('Advanced signal generation requested', {
        userId: req.user.userId,
        symbol,
        timeframe,
        lookback,
        correlationId
      });

      const signalData = await signalProcessor.generateAdvancedSignals(symbol, timeframe, lookback);
      const processingTime = Date.now() - startTime;

      logger.info('Advanced signal generation completed', {
        userId: req.user.userId,
        symbol,
        processingTime,
        correlationId
      });

      res.json(createResponse(true, 'Advanced signals generated successfully', {
        symbol,
        signals: signalData,
        metadata: {
          timeframe,
          lookback,
          processingTime,
          correlationId,
          timestamp: new Date().toISOString()
        }
      }));

    } catch (error) {
      logger.error('Advanced signal generation failed', {
        userId: req.user.userId,
        symbol,
        error: error.message,
        correlationId,
        processingTime: Date.now() - startTime
      });

      res.status(500).json(createResponse(false, 'Failed to generate advanced signals', {
        error: error.message,
        correlationId
      }));
    }
  }
);

/**
 * Portfolio Optimization
 * POST /api/advanced/portfolio/optimize
 */
router.post('/portfolio/optimize', 
  authenticateUser,
  createValidationMiddleware(advancedValidationSchemas.optimizePortfolio),
  async (req, res) => {
    const correlationId = req.correlationId;
    const { riskTolerance, targetReturn, constraints } = req.validated;
    const startTime = Date.now();

    try {
      logger.info('Portfolio optimization requested', {
        userId: req.user.userId,
        riskTolerance,
        targetReturn,
        constraints,
        correlationId
      });

      // Get user's current portfolio
      const currentPortfolio = await dashboardService.getCurrentPortfolio(req.user.userId);
      
      if (!currentPortfolio || currentPortfolio.length === 0) {
        return res.status(400).json(createResponse(false, 'No portfolio positions found for optimization', {
          correlationId
        }));
      }

      const preferences = { riskTolerance, targetReturn, ...constraints };
      const optimizationResult = await portfolioOptimizer.optimizePortfolio(currentPortfolio, req.user.userId, preferences);
      const processingTime = Date.now() - startTime;

      logger.info('Portfolio optimization completed', {
        userId: req.user.userId,
        success: optimizationResult.success,
        processingTime,
        correlationId
      });

      res.json(createResponse(true, 'Portfolio optimization completed successfully', {
        optimization: optimizationResult,
        metadata: {
          processingTime,
          correlationId,
          timestamp: new Date().toISOString()
        }
      }));

    } catch (error) {
      logger.error('Portfolio optimization failed', {
        userId: req.user.userId,
        error: error.message,
        correlationId,
        processingTime: Date.now() - startTime
      });

      res.status(500).json(createResponse(false, 'Failed to optimize portfolio', {
        error: error.message,
        correlationId
      }));
    }
  }
);

/**
 * Automated Trading Execution
 * POST /api/advanced/trading/execute
 */
router.post('/trading/execute', 
  authenticateUser,
  async (req, res) => {
    const correlationId = req.correlationId;
    const preferences = req.body || {};
    const startTime = Date.now();

    try {
      logger.info('Automated trading execution requested', {
        userId: req.user.userId,
        preferences,
        correlationId
      });

      const tradingResult = await tradingEngine.executeAutomatedStrategy(req.user.userId, preferences);
      const processingTime = Date.now() - startTime;

      logger.info('Automated trading execution completed', {
        userId: req.user.userId,
        success: tradingResult.success,
        decisions: tradingResult.decisions?.length || 0,
        orders: tradingResult.executionPlan?.orders?.length || 0,
        processingTime,
        correlationId
      });

      res.json(createResponse(true, 'Automated trading execution completed successfully', {
        trading: tradingResult,
        metadata: {
          processingTime,
          correlationId,
          timestamp: new Date().toISOString()
        }
      }));

    } catch (error) {
      logger.error('Automated trading execution failed', {
        userId: req.user.userId,
        error: error.message,
        correlationId,
        processingTime: Date.now() - startTime
      });

      res.status(500).json(createResponse(false, 'Failed to execute automated trading', {
        error: error.message,
        correlationId
      }));
    }
  }
);

/**
 * Backtesting Engine
 * POST /api/advanced/backtest/run
 */
router.post('/backtest/run', 
  authenticateUser,
  createValidationMiddleware(advancedValidationSchemas.runBacktest),
  async (req, res) => {
    const correlationId = req.correlationId;
    const { symbols, startDate, endDate, strategy, initialCapital = 100000 } = req.validated;
    const startTime = Date.now();

    try {
      logger.info('Backtesting requested', {
        userId: req.user.userId,
        symbols: symbols.length,
        startDate,
        endDate,
        strategy,
        initialCapital,
        correlationId
      });

      const backtestResult = await backtestingEngine.runBacktest(symbols, startDate, endDate, strategy, initialCapital);
      const processingTime = Date.now() - startTime;

      logger.info('Backtesting completed', {
        userId: req.user.userId,
        success: backtestResult.success,
        totalTrades: backtestResult.backtest?.results?.trades?.length || 0,
        finalValue: backtestResult.backtest?.results?.finalPortfolioValue || 0,
        processingTime,
        correlationId
      });

      res.json(createResponse(true, 'Backtesting completed successfully', {
        backtest: backtestResult,
        metadata: {
          processingTime,
          correlationId,
          timestamp: new Date().toISOString()
        }
      }));

    } catch (error) {
      logger.error('Backtesting failed', {
        userId: req.user.userId,
        error: error.message,
        correlationId,
        processingTime: Date.now() - startTime
      });

      res.status(500).json(createResponse(false, 'Failed to run backtest', {
        error: error.message,
        correlationId
      }));
    }
  }
);

/**
 * Market Analytics
 * GET /api/advanced/market/analytics
 */
router.get('/market/analytics', 
  authenticateUser,
  createValidationMiddleware(advancedValidationSchemas.marketAnalytics),
  async (req, res) => {
    const correlationId = req.correlationId;
    const { analysisType = 'comprehensive' } = req.validated;
    const startTime = Date.now();

    try {
      logger.info('Market analytics requested', {
        userId: req.user.userId,
        analysisType,
        correlationId
      });

      const analyticsResult = await marketAnalytics.generateMarketAnalytics(analysisType);
      const processingTime = Date.now() - startTime;

      logger.info('Market analytics completed', {
        userId: req.user.userId,
        success: analyticsResult.success,
        analysisType,
        processingTime,
        correlationId
      });

      res.json(createResponse(true, 'Market analytics generated successfully', {
        analytics: analyticsResult,
        metadata: {
          processingTime,
          correlationId,
          timestamp: new Date().toISOString()
        }
      }));

    } catch (error) {
      logger.error('Market analytics failed', {
        userId: req.user.userId,
        error: error.message,
        correlationId,
        processingTime: Date.now() - startTime
      });

      res.status(500).json(createResponse(false, 'Failed to generate market analytics', {
        error: error.message,
        correlationId
      }));
    }
  }
);

/**
 * Advanced Dashboard
 * GET /api/advanced/dashboard
 */
router.get('/dashboard', 
  authenticateUser,
  createValidationMiddleware(advancedValidationSchemas.dashboard),
  async (req, res) => {
    const correlationId = req.correlationId;
    const { type = 'comprehensive' } = req.validated;
    const startTime = Date.now();

    try {
      logger.info('Advanced dashboard requested', {
        userId: req.user.userId,
        type,
        correlationId
      });

      const dashboardResult = await dashboardService.generateDashboard(req.user.userId, type);
      const processingTime = Date.now() - startTime;

      logger.info('Advanced dashboard completed', {
        userId: req.user.userId,
        success: dashboardResult.success,
        type,
        processingTime,
        correlationId
      });

      res.json(createResponse(true, 'Advanced dashboard generated successfully', {
        dashboard: dashboardResult,
        metadata: {
          processingTime,
          correlationId,
          timestamp: new Date().toISOString()
        }
      }));

    } catch (error) {
      logger.error('Advanced dashboard failed', {
        userId: req.user.userId,
        error: error.message,
        correlationId,
        processingTime: Date.now() - startTime
      });

      res.status(500).json(createResponse(false, 'Failed to generate advanced dashboard', {
        error: error.message,
        correlationId
      }));
    }
  }
);

/**
 * Portfolio Analysis
 * GET /api/advanced/portfolio/analysis
 */
router.get('/portfolio/analysis', 
  authenticateUser,
  async (req, res) => {
    const correlationId = req.correlationId;
    const startTime = Date.now();

    try {
      logger.info('Portfolio analysis requested', {
        userId: req.user.userId,
        correlationId
      });

      const portfolioAnalysis = await dashboardService.generatePortfolioOverview(req.user.userId);
      const processingTime = Date.now() - startTime;

      logger.info('Portfolio analysis completed', {
        userId: req.user.userId,
        holdingsCount: portfolioAnalysis?.holdings?.length || 0,
        processingTime,
        correlationId
      });

      res.json(createResponse(true, 'Portfolio analysis completed successfully', {
        analysis: portfolioAnalysis,
        metadata: {
          processingTime,
          correlationId,
          timestamp: new Date().toISOString()
        }
      }));

    } catch (error) {
      logger.error('Portfolio analysis failed', {
        userId: req.user.userId,
        error: error.message,
        correlationId,
        processingTime: Date.now() - startTime
      });

      res.status(500).json(createResponse(false, 'Failed to analyze portfolio', {
        error: error.message,
        correlationId
      }));
    }
  }
);

/**
 * Performance Analytics
 * GET /api/advanced/performance
 */
router.get('/performance', 
  authenticateUser,
  async (req, res) => {
    const correlationId = req.correlationId;
    const startTime = Date.now();

    try {
      logger.info('Performance analytics requested', {
        userId: req.user.userId,
        correlationId
      });

      const performanceAnalytics = await dashboardService.generatePerformanceAnalytics(req.user.userId);
      const processingTime = Date.now() - startTime;

      logger.info('Performance analytics completed', {
        userId: req.user.userId,
        processingTime,
        correlationId
      });

      res.json(createResponse(true, 'Performance analytics generated successfully', {
        performance: performanceAnalytics,
        metadata: {
          processingTime,
          correlationId,
          timestamp: new Date().toISOString()
        }
      }));

    } catch (error) {
      logger.error('Performance analytics failed', {
        userId: req.user.userId,
        error: error.message,
        correlationId,
        processingTime: Date.now() - startTime
      });

      res.status(500).json(createResponse(false, 'Failed to generate performance analytics', {
        error: error.message,
        correlationId
      }));
    }
  }
);

/**
 * Risk Management
 * GET /api/advanced/risk
 */
router.get('/risk', 
  authenticateUser,
  async (req, res) => {
    const correlationId = req.correlationId;
    const startTime = Date.now();

    try {
      logger.info('Risk management analysis requested', {
        userId: req.user.userId,
        correlationId
      });

      const riskAnalysis = await dashboardService.generateRiskManagement(req.user.userId);
      const processingTime = Date.now() - startTime;

      logger.info('Risk management analysis completed', {
        userId: req.user.userId,
        processingTime,
        correlationId
      });

      res.json(createResponse(true, 'Risk management analysis completed successfully', {
        risk: riskAnalysis,
        metadata: {
          processingTime,
          correlationId,
          timestamp: new Date().toISOString()
        }
      }));

    } catch (error) {
      logger.error('Risk management analysis failed', {
        userId: req.user.userId,
        error: error.message,
        correlationId,
        processingTime: Date.now() - startTime
      });

      res.status(500).json(createResponse(false, 'Failed to analyze risk management', {
        error: error.message,
        correlationId
      }));
    }
  }
);

/**
 * Health Check
 * GET /api/advanced/health
 */
router.get('/health', async (req, res) => {
  const correlationId = req.correlationId;
  const startTime = Date.now();

  try {
    logger.info('Advanced features health check requested', {
      correlationId
    });

    const healthStatus = {
      status: 'healthy',
      services: {
        signalProcessor: 'operational',
        portfolioOptimizer: 'operational',
        tradingEngine: 'operational',
        backtestingEngine: 'operational',
        marketAnalytics: 'operational',
        dashboardService: 'operational'
      },
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      memory: process.memoryUsage(),
      correlationId
    };

    const processingTime = Date.now() - startTime;

    logger.info('Advanced features health check completed', {
      processingTime,
      correlationId
    });

    res.json(createResponse(true, 'Advanced features are healthy', {
      health: healthStatus,
      metadata: {
        processingTime,
        correlationId,
        timestamp: new Date().toISOString()
      }
    }));

  } catch (error) {
    logger.error('Advanced features health check failed', {
      error: error.message,
      correlationId,
      processingTime: Date.now() - startTime
    });

    res.status(500).json(createResponse(false, 'Advanced features health check failed', {
      error: error.message,
      correlationId
    }));
  }
});

module.exports = router;
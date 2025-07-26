// Performance Monitoring Routes
// API endpoints for performance metrics, alerts, and optimization recommendations

const express = require('express');
const router = express.Router();
const { authenticateToken } = require('../middleware/auth');
const { createValidationMiddleware, sanitizers } = require('../middleware/validation');
const apiKeyService = require('../utils/apiKeyService');
const AlpacaService = require('../utils/alpacaService');
const PerformanceMonitoringService = require('../services/performanceMonitoringService');
const AdvancedPerformanceAnalytics = require('../utils/advancedPerformanceAnalytics');

// Initialize service
const performanceService = new PerformanceMonitoringService();

// Standard paper trading validation schema
const paperTradingValidationSchema = {
  accountType: {
    type: 'string',
    sanitizer: (value) => sanitizers.string(value, { defaultValue: 'paper' }),
    validator: (value) => ['paper', 'live'].includes(value),
    errorMessage: 'accountType must be paper or live'
  },
  force: {
    type: 'boolean',
    sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
    validator: (value) => typeof value === 'boolean',
    errorMessage: 'force must be true or false'
  }
};

// Helper function to get user API key with proper format (matching portfolio.js pattern)
const getUserApiKey = async (userId, provider) => {
  try {
    const credentials = await apiKeyService.getApiKey(userId, provider);
    if (!credentials) {
      return null;
    }
    
    return {
      apiKey: credentials.keyId,
      apiSecret: credentials.secretKey,
      isSandbox: credentials.version === '1.0' // Default to sandbox for v1.0
    };
  } catch (error) {
    console.error(`Failed to get API key for ${provider}:`, error);
    return null;
  }
};

// Helper function to setup Alpaca service with account type
const setupAlpacaService = async (userId, accountType = 'paper') => {
  const credentials = await getUserApiKey(userId, 'alpaca');
  
  if (!credentials) {
    throw new Error(`No Alpaca API keys configured`);
  }
  
  // Determine if we should use sandbox based on account type preference and credentials
  const useSandbox = accountType === 'paper' || credentials.isSandbox;
  
  return new AlpacaService(
    credentials.apiKey,
    credentials.apiSecret,
    useSandbox
  );
};

// Apply authentication to protected routes
router.use('/portfolio', authenticateToken);
router.use('/analytics', authenticateToken);
router.use('/dashboard', authenticateToken);

// Get performance dashboard with paper trading support
router.get('/dashboard', 
  createValidationMiddleware(paperTradingValidationSchema),
  async (req, res) => {
    try {
      const { accountType = 'paper' } = req.query;
      const userId = req.user?.sub;
      
      // Get system performance dashboard
      const systemDashboard = performanceService.getPerformanceDashboard();
      
      // Get user's portfolio performance if authenticated
      let portfolioPerformance = null;
      if (userId) {
        try {
          const alpacaService = await setupAlpacaService(userId, accountType);
          const performanceAnalytics = new AdvancedPerformanceAnalytics();
          
          // Get portfolio data from Alpaca
          const account = await alpacaService.getAccount();
          const positions = await alpacaService.getPositions();
          
          // Calculate performance metrics
          portfolioPerformance = await performanceAnalytics.calculateBaseMetrics({
            account,
            positions,
            accountType
          });
        } catch (alpacaError) {
          console.warn(`Alpaca performance data unavailable for ${accountType}:`, alpacaError.message);
        }
      }
      
      res.json({
        success: true,
        data: {
          system: systemDashboard,
          portfolio: portfolioPerformance
        },
        accountType,
        tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
        timestamp: new Date().toISOString()
      });
      
    } catch (error) {
      console.error('Performance dashboard failed:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to get performance dashboard',
        message: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }
);

// Record performance metric
router.post('/metrics', async (req, res) => {
  try {
    const { name, value, category = 'general', metadata = {} } = req.body;
    
    if (!name || value === undefined) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields',
        message: 'name and value are required'
      });
    }
    
    if (typeof value !== 'number') {
      return res.status(400).json({
        success: false,
        error: 'Invalid value type',
        message: 'value must be a number'
      });
    }
    
    const metric = performanceService.recordMetric(name, value, category, {
      ...metadata,
      source: 'api',
      userAgent: req.get('User-Agent'),
      endpoint: req.originalUrl
    });
    
    res.json({
      success: true,
      data: {
        metricId: metric.id,
        name: metric.name,
        value: metric.value,
        category: metric.category,
        timestamp: metric.timestamp
      },
      message: 'Performance metric recorded successfully',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Metric recording failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to record performance metric',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get all alerts
router.get('/alerts', async (req, res) => {
  try {
    const { 
      severity, 
      status = 'all', 
      limit = 50, 
      acknowledged 
    } = req.query;
    
    let alerts = [...performanceService.alerts];
    
    // Filter by severity
    if (severity) {
      alerts = alerts.filter(alert => 
        alert.severity.toLowerCase() === severity.toLowerCase()
      );
    }
    
    // Filter by status
    if (status !== 'all') {
      alerts = alerts.filter(alert => 
        alert.status.toLowerCase() === status.toLowerCase()
      );
    }
    
    // Filter by acknowledgment
    if (acknowledged !== undefined) {
      const isAcknowledged = acknowledged === 'true';
      alerts = alerts.filter(alert => alert.acknowledged === isAcknowledged);
    }
    
    // Sort by most recent and limit
    alerts = alerts
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .slice(0, parseInt(limit));
    
    const summary = {
      total: alerts.length,
      critical: alerts.filter(a => a.severity === 'CRITICAL').length,
      warning: alerts.filter(a => a.severity === 'WARNING').length,
      active: alerts.filter(a => a.status === 'ACTIVE').length,
      acknowledged: alerts.filter(a => a.acknowledged).length
    };
    
    res.json({
      success: true,
      data: {
        alerts,
        summary,
        filters: { severity, status, acknowledged, limit }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Alerts retrieval failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get alerts',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get optimization recommendations
router.get('/recommendations', async (req, res) => {
  try {
    const { 
      priority, 
      category, 
      implemented = 'false', 
      limit = 20 
    } = req.query;
    
    let recommendations = [...performanceService.recommendations];
    
    // Filter by implementation status
    const isImplemented = implemented === 'true';
    recommendations = recommendations.filter(rec => rec.implemented === isImplemented);
    
    // Filter by priority
    if (priority) {
      recommendations = recommendations.filter(rec => 
        rec.priority.toLowerCase() === priority.toLowerCase()
      );
    }
    
    // Filter by category
    if (category) {
      recommendations = recommendations.filter(rec => 
        rec.category.toLowerCase() === category.toLowerCase()
      );
    }
    
    // Sort by priority and timestamp
    const priorityOrder = { 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1 };
    recommendations = recommendations
      .sort((a, b) => {
        const priorityDiff = priorityOrder[b.priority] - priorityOrder[a.priority];
        if (priorityDiff !== 0) return priorityDiff;
        return new Date(b.timestamp) - new Date(a.timestamp);
      })
      .slice(0, parseInt(limit));
    
    const summary = {
      total: recommendations.length,
      high: recommendations.filter(r => r.priority === 'HIGH').length,
      medium: recommendations.filter(r => r.priority === 'MEDIUM').length,
      low: recommendations.filter(r => r.priority === 'LOW').length
    };
    
    res.json({
      success: true,
      data: {
        recommendations,
        summary,
        filters: { priority, category, implemented, limit }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Recommendations retrieval failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get recommendations',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get portfolio performance analytics with paper trading support
router.get('/portfolio/:accountId',
  createValidationMiddleware({
    ...paperTradingValidationSchema,
    period: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { defaultValue: '1M' }),
      validator: (value) => ['1D', '1W', '1M', '3M', '6M', '1Y', 'YTD', 'ALL'].includes(value),
      errorMessage: 'period must be 1D, 1W, 1M, 3M, 6M, 1Y, YTD, or ALL'
    }
  }),
  async (req, res) => {
    try {
      const { accountId } = req.params;
      const { accountType = 'paper', period = '1M' } = req.query;
      const userId = req.user?.sub;
      
      if (!userId) {
        return res.status(401).json({
          success: false,
          error: 'Authentication required'
        });
      }
      
      const alpacaService = await setupAlpacaService(userId, accountType);
      const performanceAnalytics = new AdvancedPerformanceAnalytics();
      
      // FIXED: Sequential API calls with proper timeout management to prevent rate limiting
      // and reduce concurrent connection load on Lambda
      const account = await alpacaService.getAccount();
      const positions = await alpacaService.getPositions();
      // Only get history if we have positions (optimization)
      const portfolioHistory = positions && positions.length > 0 
        ? await alpacaService.getPortfolioHistory({ period, timeframe: '1Day' })
        : null;
      
      // Calculate comprehensive performance metrics
      const performanceMetrics = await performanceAnalytics.generatePerformanceReport({
        account,
        positions,
        portfolioHistory,
        accountType,
        period
      });
      
      res.json({
        success: true,
        data: performanceMetrics,
        accountType,
        tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
        period,
        source: 'alpaca',
        timestamp: new Date().toISOString()
      });
      
    } catch (error) {
      console.error('Portfolio performance analysis failed:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to analyze portfolio performance',
        message: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }
);

// Get detailed performance analytics with paper trading support
router.get('/analytics/detailed',
  createValidationMiddleware({
    ...paperTradingValidationSchema,
    includeRisk: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'includeRisk must be true or false'
    },
    includeAttribution: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'includeAttribution must be true or false'
    }
  }),
  async (req, res) => {
    try {
      const { accountType = 'paper', includeRisk = true, includeAttribution = true } = req.query;
      const userId = req.user?.sub;
      
      if (!userId) {
        return res.status(401).json({
          success: false,
          error: 'Authentication required'
        });
      }
      
      const alpacaService = await setupAlpacaService(userId, accountType);
      const performanceAnalytics = new AdvancedPerformanceAnalytics();
      
      // Get comprehensive portfolio data
      const [account, positions, portfolioHistory, orders] = await Promise.all([
        alpacaService.getAccount(),
        alpacaService.getPositions(),
        alpacaService.getPortfolioHistory({ period: '1Y', timeframe: '1Day' }),
        alpacaService.getOrders({ status: 'all', limit: 500 })
      ]);
      
      // Calculate detailed analytics
      const analytics = {};
      
      // Base performance metrics
      analytics.performance = await performanceAnalytics.calculateBaseMetrics({
        account,
        positions,
        portfolioHistory,
        accountType
      });
      
      // Risk metrics if requested
      if (includeRisk) {
        analytics.risk = await performanceAnalytics.calculateRiskMetrics({
          positions,
          portfolioHistory,
          accountType
        });
      }
      
      // Attribution analysis if requested
      if (includeAttribution) {
        analytics.attribution = await performanceAnalytics.calculateAttributionAnalysis({
          positions,
          orders,
          portfolioHistory,
          accountType
        });
      }
      
      // Sector and diversification analysis
      analytics.diversification = await performanceAnalytics.calculateSectorAnalysis(positions);
      analytics.diversificationScore = await performanceAnalytics.calculateDiversificationScore(positions);
      
      // Performance grade
      analytics.grade = await performanceAnalytics.getPerformanceGrade(analytics.performance);
      
      res.json({
        success: true,
        data: analytics,
        accountType,
        tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
        source: 'alpaca',
        responseTime: Date.now() - req.startTime,
        timestamp: new Date().toISOString(),
        
        // Paper trading specific info
        paperTradingInfo: accountType === 'paper' ? {
          isPaperAccount: true,
          virtualCash: account?.cash || 0,
          restrictions: ['No real money risk', 'Delayed market data'],
          benefits: ['Risk-free testing', 'Strategy development']
        } : undefined
      });
      
    } catch (error) {
      console.error('Detailed performance analytics failed:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to generate detailed performance analytics',
        message: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }
);

// Performance health check
router.get('/health', async (req, res) => {
  try {
    // Test performance monitoring functionality
    const testMetric = performanceService.recordMetric(
      'health_check_response_time', 
      Date.now() % 1000, 
      'api', 
      { test: true }
    );
    
    const dashboard = performanceService.getPerformanceDashboard();
    
    res.json({
      success: true,
      message: 'Performance monitoring services operational',
      services: {
        metricCollection: {
          status: testMetric ? 'operational' : 'error',
          totalMetrics: performanceService.metrics.size
        },
        alerting: {
          status: 'operational',
          totalAlerts: performanceService.alerts.length,
          activeAlerts: performanceService.alerts.filter(a => a.status === 'ACTIVE').length
        },
        recommendations: {
          status: 'operational',
          totalRecommendations: performanceService.recommendations.length,
          activeRecommendations: performanceService.recommendations.filter(r => !r.implemented).length
        },
        dashboard: {
          status: dashboard ? 'operational' : 'error',
          healthScore: dashboard.healthScore
        }
      },
      statistics: {
        metrics: performanceService.metrics.size,
        alerts: performanceService.alerts.length,
        recommendations: performanceService.recommendations.length,
        systemHealth: dashboard.summary.systemHealth
      },
      thresholds: performanceService.thresholds,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Performance monitoring health check failed:', error);
    res.status(503).json({
      success: false,
      error: 'Performance monitoring services unhealthy',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
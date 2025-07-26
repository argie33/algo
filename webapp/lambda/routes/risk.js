const express = require('express');
const router = express.Router();
const { authenticateToken } = require('../middleware/auth');
const { createValidationMiddleware, sanitizers } = require('../middleware/validation');
const { query } = require('../utils/database');
const apiKeyService = require('../utils/apiKeyService');
const AlpacaService = require('../utils/alpacaService');
const RiskEngine = require('../utils/riskEngine');

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

// Health endpoint (no auth required)
router.get('/health', (req, res) => {
  res.json({
    success: true,
    status: 'operational',
    service: 'risk-analysis',
    timestamp: new Date().toISOString(),
    message: 'Risk Analysis service is running'
  });
});

// Basic root endpoint (public)
router.get('/', (req, res) => {
  res.json({
    success: true,
    message: 'Risk Analysis API - Ready',
    timestamp: new Date().toISOString(),
    status: 'operational'
  });
});

// Apply authentication to all routes
router.use(authenticateToken);

// Initialize risk engine
const riskEngine = new RiskEngine();

// Get portfolio risk metrics with paper trading support
router.get('/portfolio/:portfolioId',
  createValidationMiddleware({
    ...paperTradingValidationSchema,
    timeframe: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { defaultValue: '1Y' }),
      validator: (value) => ['1D', '1W', '1M', '3M', '6M', '1Y', '2Y'].includes(value),
      errorMessage: 'timeframe must be 1D, 1W, 1M, 3M, 6M, 1Y, or 2Y'
    },
    confidence_level: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0.8, max: 0.99, defaultValue: 0.95 }),
      validator: (value) => !value || (value >= 0.8 && value <= 0.99),
      errorMessage: 'confidence_level must be between 0.8 and 0.99'
    }
  }),
  async (req, res) => {
    try {
      const { portfolioId } = req.params;
      const { accountType = 'paper', timeframe = '1Y', confidence_level = 0.95 } = req.query;
      const userId = req.user.sub;
      
      // Setup Alpaca service for account type
      const alpacaService = await setupAlpacaService(userId, accountType);
      
      // FIXED: Sequential API calls to prevent rate limiting and reduce Lambda load
      const account = await alpacaService.getAccount();
      const positions = await alpacaService.getPositions();
      // Only fetch history if needed for risk calculations
      const portfolioHistory = positions && positions.length > 0 
        ? await alpacaService.getPortfolioHistory({ period: timeframe, timeframe: '1Day' })
        : null;
      
      if (!positions || positions.length === 0) {
        return res.json({
          success: true,
          data: {
            portfolioId: `${accountType}-${userId}`,
            riskMetrics: {
              message: 'No positions found for risk analysis',
              totalValue: account?.portfolio_value || 0,
              positionCount: 0
            }
          },
          accountType,
          tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
          timestamp: new Date().toISOString()
        });
      }
      
      // Calculate risk metrics using portfolio data
      const riskMetrics = await riskEngine.calculatePortfolioRisk(
        { positions, portfolioHistory, account, accountType },
        timeframe,
        parseFloat(confidence_level)
      );
      
      res.json({
        success: true,
        data: {
          portfolioId: `${accountType}-${userId}`,
          riskMetrics,
          accountInfo: {
            totalValue: account?.portfolio_value,
            cash: account?.cash,
            dayTradeCount: account?.day_trade_count,
            positionCount: positions.length
          }
        },
        accountType,
        tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
        source: 'alpaca',
        timestamp: new Date().toISOString(),
        
        // Paper trading specific info
        paperTradingInfo: accountType === 'paper' ? {
          isPaperAccount: true,
          virtualCash: account?.cash || 0,
          restrictions: ['No real money risk', 'Simulated risk calculations'],
          benefits: ['Risk-free analysis', 'Strategy testing']
        } : undefined
      });
    } catch (error) {
      console.error('Error calculating portfolio risk:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to calculate portfolio risk',
        message: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }
);

// Get Value at Risk (VaR) analysis with paper trading support
router.get('/var',
  createValidationMiddleware({
    ...paperTradingValidationSchema,
    method: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { defaultValue: 'historical' }),
      validator: (value) => ['historical', 'parametric', 'monte_carlo'].includes(value),
      errorMessage: 'method must be historical, parametric, or monte_carlo'
    },
    confidence_level: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0.8, max: 0.99, defaultValue: 0.95 }),
      validator: (value) => !value || (value >= 0.8 && value <= 0.99),
      errorMessage: 'confidence_level must be between 0.8 and 0.99'
    },
    time_horizon: {
      type: 'integer',
      sanitizer: (value) => sanitizers.integer(value, { min: 1, max: 30, defaultValue: 1 }),
      validator: (value) => !value || (value >= 1 && value <= 30),
      errorMessage: 'time_horizon must be between 1 and 30 days'
    },
    lookback_days: {
      type: 'integer',
      sanitizer: (value) => sanitizers.integer(value, { min: 30, max: 1000, defaultValue: 252 }),
      validator: (value) => !value || (value >= 30 && value <= 1000),
      errorMessage: 'lookback_days must be between 30 and 1000'
    }
  }),
  async (req, res) => {
    try {
      const { 
        accountType = 'paper',
        method = 'historical', 
        confidence_level = 0.95, 
        time_horizon = 1,
        lookback_days = 252
      } = req.query;
      const userId = req.user.sub;
      
      // Setup Alpaca service for account type
      const alpacaService = await setupAlpacaService(userId, accountType);
      
      // Get portfolio data from Alpaca
      const [account, positions, portfolioHistory] = await Promise.all([
        alpacaService.getAccount(),
        alpacaService.getPositions(),
        alpacaService.getPortfolioHistory({ 
          period: lookback_days > 365 ? '2Y' : '1Y', 
          timeframe: '1Day' 
        })
      ]);
      
      if (!positions || positions.length === 0) {
        return res.json({
          success: true,
          data: {
            var: 0,
            message: 'No positions found for VaR analysis',
            totalValue: account?.portfolio_value || 0
          },
          accountType,
          tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
          timestamp: new Date().toISOString()
        });
      }
      
      // Calculate VaR using portfolio data
      const varAnalysis = await riskEngine.calculateVaR(
        { positions, portfolioHistory, account, accountType },
        method,
        parseFloat(confidence_level),
        parseInt(time_horizon),
        parseInt(lookback_days)
      );
      
      res.json({
        success: true,
        data: {
          ...varAnalysis,
          parameters: {
            method,
            confidence_level: parseFloat(confidence_level),
            time_horizon: parseInt(time_horizon),
            lookback_days: parseInt(lookback_days)
          },
          accountInfo: {
            totalValue: account?.portfolio_value,
            positionCount: positions.length
          }
        },
        accountType,
        tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
        source: 'alpaca',
        timestamp: new Date().toISOString(),
        
        // Paper trading specific info
        paperTradingInfo: accountType === 'paper' ? {
          isPaperAccount: true,
          virtualRisk: true,
          disclaimer: 'VaR calculations based on simulated portfolio data'
        } : undefined
      });
    } catch (error) {
      console.error('Error calculating VaR:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to calculate VaR',
        message: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }
);

// Get stress testing results
router.post('/stress-test/:portfolioId', async (req, res) => {
  try {
    const { portfolioId } = req.params;
    const { 
      scenarios = [],
      shock_magnitude = 0.1,
      correlation_adjustment = false
    } = req.body;
    const userId = req.user.sub;
    
    // Verify portfolio ownership
    const portfolioResult = await query(`
      SELECT id FROM portfolios 
      WHERE id = $1 AND user_id = $2
    `, [portfolioId, userId]);
    
    if (portfolioResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'Portfolio not found'
      });
    }
    
    const stressTestResults = await riskEngine.performStressTest(
      portfolioId,
      scenarios,
      shock_magnitude,
      correlation_adjustment
    );
    
    res.json({
      success: true,
      data: stressTestResults
    });
  } catch (error) {
    console.error('Error performing stress test:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to perform stress test',
      message: error.message
    });
  }
});

// Get risk alerts
router.get('/alerts', async (req, res) => {
  try {
    const { 
      severity = 'all',
      status = 'active',
      limit = 50,
      offset = 0
    } = req.query;
    const userId = req.user.sub;
    
    let whereClause = 'WHERE ra.user_id = $1';
    const params = [userId];
    let paramIndex = 2;
    
    if (severity !== 'all') {
      whereClause += ` AND ra.severity = $${paramIndex}`;
      params.push(severity);
      paramIndex++;
    }
    
    if (status !== 'all') {
      whereClause += ` AND ra.status = $${paramIndex}`;
      params.push(status);
      paramIndex++;
    }
    
    const result = await query(`
      SELECT 
        ra.id,
        ra.alert_type,
        ra.severity,
        ra.title,
        ra.description,
        ra.metric_name,
        ra.current_value,
        ra.threshold_value,
        ra.portfolio_id,
        ra.symbol,
        ra.created_at,
        ra.updated_at,
        ra.status,
        ra.acknowledged_at,
        p.name as portfolio_name
      FROM risk_alerts ra
      LEFT JOIN portfolios p ON ra.portfolio_id = p.id
      ${whereClause}
      ORDER BY ra.created_at DESC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `, [...params, parseInt(limit), parseInt(offset)]);
    
    // Get total count
    const countResult = await query(`
      SELECT COUNT(*) as total
      FROM risk_alerts ra
      ${whereClause}
    `, params);
    
    res.json({
      success: true,
      data: {
        alerts: result.rows,
        total: parseInt(countResult.rows[0].total),
        limit: parseInt(limit),
        offset: parseInt(offset)
      }
    });
  } catch (error) {
    console.error('Error fetching risk alerts:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch risk alerts',
      message: error.message
    });
  }
});

// Acknowledge risk alert
router.put('/alerts/:alertId/acknowledge', async (req, res) => {
  try {
    const { alertId } = req.params;
    const userId = req.user.sub;
    
    // Verify alert ownership
    const alertResult = await query(`
      SELECT id FROM risk_alerts 
      WHERE id = $1 AND user_id = $2
    `, [alertId, userId]);
    
    if (alertResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'Alert not found'
      });
    }
    
    await query(`
      UPDATE risk_alerts 
      SET status = 'acknowledged', acknowledged_at = CURRENT_TIMESTAMP
      WHERE id = $1
    `, [alertId]);
    
    res.json({
      success: true,
      message: 'Alert acknowledged successfully'
    });
  } catch (error) {
    console.error('Error acknowledging alert:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to acknowledge alert',
      message: error.message
    });
  }
});

// Get correlation matrix
router.get('/correlation/:portfolioId', async (req, res) => {
  try {
    const { portfolioId } = req.params;
    const { lookback_days = 252 } = req.query;
    const userId = req.user.sub;
    
    // Verify portfolio ownership
    const portfolioResult = await query(`
      SELECT id FROM portfolios 
      WHERE id = $1 AND user_id = $2
    `, [portfolioId, userId]);
    
    if (portfolioResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'Portfolio not found'
      });
    }
    
    const correlationMatrix = await riskEngine.calculateCorrelationMatrix(
      portfolioId,
      parseInt(lookback_days)
    );
    
    res.json({
      success: true,
      data: correlationMatrix
    });
  } catch (error) {
    console.error('Error calculating correlation matrix:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to calculate correlation matrix',
      message: error.message
    });
  }
});

// Get risk attribution analysis
router.get('/attribution/:portfolioId', async (req, res) => {
  try {
    const { portfolioId } = req.params;
    const { attribution_type = 'factor' } = req.query;
    const userId = req.user.sub;
    
    // Verify portfolio ownership
    const portfolioResult = await query(`
      SELECT id FROM portfolios 
      WHERE id = $1 AND user_id = $2
    `, [portfolioId, userId]);
    
    if (portfolioResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'Portfolio not found'
      });
    }
    
    const attribution = await riskEngine.calculateRiskAttribution(
      portfolioId,
      attribution_type
    );
    
    res.json({
      success: true,
      data: attribution
    });
  } catch (error) {
    console.error('Error calculating risk attribution:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to calculate risk attribution',
      message: error.message
    });
  }
});

// Get risk limits and thresholds
router.get('/limits/:portfolioId', async (req, res) => {
  try {
    const { portfolioId } = req.params;
    const userId = req.user.sub;
    
    // Verify portfolio ownership
    const portfolioResult = await query(`
      SELECT id FROM portfolios 
      WHERE id = $1 AND user_id = $2
    `, [portfolioId, userId]);
    
    if (portfolioResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'Portfolio not found'
      });
    }
    
    const limitsResult = await query(`
      SELECT 
        id,
        metric_name,
        threshold_value,
        warning_threshold,
        threshold_type,
        is_active,
        created_at,
        updated_at
      FROM risk_limits
      WHERE portfolio_id = $1
      ORDER BY metric_name
    `, [portfolioId]);
    
    res.json({
      success: true,
      data: {
        limits: limitsResult.rows,
        portfolio_id: portfolioId
      }
    });
  } catch (error) {
    console.error('Error fetching risk limits:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch risk limits',
      message: error.message
    });
  }
});

// Update risk limits
router.put('/limits/:portfolioId', async (req, res) => {
  try {
    const { portfolioId } = req.params;
    const { limits } = req.body;
    const userId = req.user.sub;
    
    // Verify portfolio ownership
    const portfolioResult = await query(`
      SELECT id FROM portfolios 
      WHERE id = $1 AND user_id = $2
    `, [portfolioId, userId]);
    
    if (portfolioResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'Portfolio not found'
      });
    }
    
    // Update each limit
    for (const limit of limits) {
      await query(`
        INSERT INTO risk_limits (
          portfolio_id, metric_name, threshold_value, warning_threshold,
          threshold_type, is_active, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP)
        ON CONFLICT (portfolio_id, metric_name) DO UPDATE SET
          threshold_value = EXCLUDED.threshold_value,
          warning_threshold = EXCLUDED.warning_threshold,
          threshold_type = EXCLUDED.threshold_type,
          is_active = EXCLUDED.is_active,
          updated_at = CURRENT_TIMESTAMP
      `, [
        portfolioId,
        limit.metric_name,
        limit.threshold_value,
        limit.warning_threshold,
        limit.threshold_type,
        limit.is_active
      ]);
    }
    
    res.json({
      success: true,
      message: 'Risk limits updated successfully'
    });
  } catch (error) {
    console.error('Error updating risk limits:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to update risk limits',
      message: error.message
    });
  }
});

// Get risk dashboard summary with paper trading support
router.get('/dashboard',
  createValidationMiddleware(paperTradingValidationSchema),
  async (req, res) => {
    try {
      const { accountType = 'paper' } = req.query;
      const userId = req.user.sub;
      
      // Setup Alpaca service for account type
      const alpacaService = await setupAlpacaService(userId, accountType);
      
      // Get portfolio data from Alpaca
      const [account, positions, portfolioHistory] = await Promise.all([
        alpacaService.getAccount(),
        alpacaService.getPositions(),
        alpacaService.getPortfolioHistory({ period: '3M', timeframe: '1Day' })
      ]);
      
      // Calculate risk summary
      let riskSummary = {
        totalValue: account?.portfolio_value || 0,
        positionCount: positions?.length || 0,
        cashBalance: account?.cash || 0,
        dayTradeCount: account?.day_trade_count || 0,
        riskMetrics: null
      };
      
      // Calculate risk metrics if positions exist
      if (positions && positions.length > 0) {
        try {
          const portfolioRisk = await riskEngine.calculatePortfolioRisk(
            { positions, portfolioHistory, account, accountType },
            '3M',
            0.95
          );
          
          riskSummary.riskMetrics = {
            var95: portfolioRisk.var_95,
            volatility: portfolioRisk.volatility,
            beta: portfolioRisk.beta,
            sharpeRatio: portfolioRisk.sharpe_ratio,
            maxDrawdown: portfolioRisk.max_drawdown
          };
        } catch (riskError) {
          console.warn('Risk calculation failed:', riskError.message);
        }
      }
      
      // Get risk alerts from database (account-type aware)
      const alertsResult = await query(`
        SELECT 
          severity,
          COUNT(*) as count
        FROM risk_alerts
        WHERE user_id = $1 AND status = 'active' AND account_type = $2
        GROUP BY severity
      `, [userId, accountType]);
      
      // Get market risk indicators (same for both paper and live)
      const marketRiskResult = await query(`
        SELECT 
          indicator_name,
          current_value,
          risk_level,
          last_updated
        FROM market_risk_indicators
        WHERE last_updated >= CURRENT_DATE
        ORDER BY risk_level DESC
        LIMIT 10
      `);
      
      const alertCounts = alertsResult.rows.reduce((acc, row) => {
        acc[row.severity] = parseInt(row.count);
        return acc;
      }, { high: 0, medium: 0, low: 0 });
      
      // Portfolio risk classification
      const riskLevel = riskSummary.riskMetrics?.var95 ? 
        (riskSummary.riskMetrics.var95 > 0.05 ? 'high' : 
         riskSummary.riskMetrics.var95 > 0.02 ? 'medium' : 'low') : 'unknown';
      
      res.json({
        success: true,
        data: {
          portfolio: {
            id: `${accountType}-${userId}`,
            name: `${accountType === 'paper' ? 'Paper' : 'Live'} Trading Account`,
            ...riskSummary,
            riskLevel
          },
          alert_counts: alertCounts,
          market_indicators: marketRiskResult.rows,
          summary: {
            total_portfolios: 1,
            total_alerts: Object.values(alertCounts).reduce((sum, count) => sum + count, 0),
            high_risk_portfolios: riskLevel === 'high' ? 1 : 0,
            account_type: accountType
          }
        },
        accountType,
        tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
        source: 'alpaca',
        timestamp: new Date().toISOString(),
        
        // Paper trading specific info
        paperTradingInfo: accountType === 'paper' ? {
          isPaperAccount: true,
          virtualRisk: true,
          disclaimer: 'All risk calculations are based on simulated trading data'
        } : undefined
      });
    } catch (error) {
      console.error('Error fetching risk dashboard:', error);
      res.status(500).json({
        success: false,
        error: 'Failed to fetch risk dashboard',
        message: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }
);

// Start real-time risk monitoring
router.post('/monitoring/start', async (req, res) => {
  try {
    const { portfolio_ids = [], check_interval = 300000 } = req.body; // 5 minutes default
    const userId = req.user.sub;
    
    // Verify portfolio ownership
    if (portfolio_ids.length > 0) {
      const portfolioResult = await query(`
        SELECT id FROM portfolios 
        WHERE id = ANY($1) AND user_id = $2
      `, [portfolio_ids, userId]);
      
      if (portfolioResult.rows.length !== portfolio_ids.length) {
        return res.status(400).json({
          success: false,
          error: 'One or more portfolios not found'
        });
      }
    }
    
    // Start monitoring for user's portfolios
    const monitoringResult = await riskEngine.startRealTimeMonitoring(
      userId,
      portfolio_ids,
      check_interval
    );
    
    res.json({
      success: true,
      data: monitoringResult
    });
  } catch (error) {
    console.error('Error starting risk monitoring:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to start risk monitoring',
      message: error.message
    });
  }
});

// Stop real-time risk monitoring
router.post('/monitoring/stop', async (req, res) => {
  try {
    const userId = req.user.sub;
    
    const result = await riskEngine.stopRealTimeMonitoring(userId);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('Error stopping risk monitoring:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to stop risk monitoring',
      message: error.message
    });
  }
});

// Get monitoring status
router.get('/monitoring/status', async (req, res) => {
  try {
    const userId = req.user.sub;
    
    const status = await riskEngine.getMonitoringStatus(userId);
    
    res.json({
      success: true,
      data: status
    });
  } catch (error) {
    console.error('Error fetching monitoring status:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch monitoring status',
      message: error.message
    });
  }
});

// ============================================================================
// RISK MANAGEMENT ENDPOINTS (consolidated from risk-management.js)
// ============================================================================

// Additional imports for risk management functionality
const RiskManager = require('../utils/riskManager');
const riskManager = new RiskManager();

// Enhanced validation schemas for risk management endpoints
const riskManagementSchemas = {
  positionSize: {
    symbol: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10, trim: true }),
      validator: (value) => /^[A-Z]{1,10}$/.test(value),
      errorMessage: 'Symbol must be 1-10 uppercase letters'
    },
    direction: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10, toLowerCase: true }),
      validator: (value) => ['buy', 'sell'].includes(value),
      errorMessage: 'Direction must be buy or sell'
    },
    portfolioValue: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 1000 }),
      validator: (value) => !value || (value >= 1000 && value <= 100000000),
      errorMessage: 'Portfolio value must be between $1,000 and $100,000,000'
    },
    riskPerTrade: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0.001, max: 0.1, defaultValue: 0.02 }),
      validator: (value) => value >= 0.001 && value <= 0.1,
      errorMessage: 'Risk per trade must be between 0.1% and 10%'
    },
    maxPositionSize: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0.01, max: 0.5, defaultValue: 0.1 }),
      validator: (value) => value >= 0.01 && value <= 0.5,
      errorMessage: 'Max position size must be between 1% and 50%'
    }
  },
  
  stopLoss: {
    symbol: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10, trim: true }),
      validator: (value) => /^[A-Z]{1,10}$/.test(value),
      errorMessage: 'Symbol must be 1-10 uppercase letters'
    },
    entryPrice: {
      required: true,
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0.01 }),
      validator: (value) => value > 0,
      errorMessage: 'Entry price must be greater than 0'
    },
    direction: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10, toLowerCase: true }),
      validator: (value) => ['buy', 'sell'].includes(value),
      errorMessage: 'Direction must be buy or sell'
    }
  }
};

// Calculate position size based on risk management
// POST /api/risk/management/position-size
router.post('/management/position-size', createValidationMiddleware(riskManagementSchemas.positionSize), async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const startTime = Date.now();
  
  try {
    const userId = req.user.sub;
    const { symbol, direction, portfolioValue, riskPerTrade = 0.02, maxPositionSize = 0.1 } = req.validated;
    
    console.log(`🎯 [${requestId}] Calculating position size`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
      symbol: symbol,
      direction: direction,
      portfolioValue: portfolioValue,
      riskPerTrade: riskPerTrade,
      maxPositionSize: maxPositionSize
    });

    // Get user's portfolio value if not provided
    let actualPortfolioValue = portfolioValue;
    if (!actualPortfolioValue) {
      const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
      if (credentials) {
        const alpacaService = new AlpacaService(credentials.apiKey, credentials.apiSecret, credentials.isSandbox);
        const account = await alpacaService.getAccount();
        actualPortfolioValue = parseFloat(account.portfolio_value);
      } else {
        return res.status(400).json({
          success: false,
          error: 'Portfolio value required when no API credentials available'
        });
      }
    }

    // Calculate position size using risk manager
    const positionSizing = await riskManager.calculatePositionSize({
      userId: userId,
      symbol: symbol,
      portfolioValue: actualPortfolioValue,
      riskPerTrade: riskPerTrade,
      maxPositionSize: maxPositionSize,
      volatilityAdjustment: true,
      correlationAdjustment: true
    });

    // Prepare response data
    const responseData = {
      symbol: symbol,
      direction: direction,
      portfolioValue: actualPortfolioValue,
      positionSizing: {
        recommendedSize: positionSizing.recommendedSize,
        positionValue: positionSizing.positionValue,
        riskAmount: positionSizing.riskAmount,
        maxLoss: positionSizing.maxLoss
      },
      riskMetrics: positionSizing.riskMetrics,
      adjustments: positionSizing.adjustments,
      limits: positionSizing.limits,
      recommendation: positionSizing.recommendation,
      metadata: {
        processingTime: positionSizing.processingTime,
        timestamp: new Date().toISOString()
      }
    };

    console.log(`✅ [${requestId}] Position size calculated`, {
      symbol: symbol,
      recommendedSize: positionSizing.recommendedSize,
      riskScore: positionSizing.riskMetrics?.overallRiskScore,
      recommendation: positionSizing.recommendation?.recommendation,
      totalTime: Date.now() - startTime
    });
    
    res.json({
      success: true,
      data: responseData,
      message: 'Position size calculated successfully'
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Position size calculation failed`, {
      error: error.message,
      errorStack: error.stack,
      totalTime: Date.now() - startTime
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to calculate position size',
      details: error.message
    });
  }
});

// Calculate stop loss and take profit levels
// POST /api/risk/management/stop-loss
router.post('/management/stop-loss', createValidationMiddleware(riskManagementSchemas.stopLoss), async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const startTime = Date.now();
  
  try {
    const userId = req.user.sub;
    const { symbol, entryPrice, direction } = req.validated;
    
    console.log(`🛡️ [${requestId}] Calculating stop loss levels`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
      symbol: symbol,
      entryPrice: entryPrice,
      direction: direction
    });

    // Calculate stop loss using risk manager
    const stopLossLevels = await riskManager.calculateStopLoss({
      userId: userId,
      symbol: symbol,
      entryPrice: entryPrice,
      direction: direction,
      useVolatilityBased: true,
      useTechnicalLevels: true
    });

    const responseData = {
      symbol: symbol,
      entryPrice: entryPrice,
      direction: direction,
      stopLossLevels: stopLossLevels.levels,
      recommendation: stopLossLevels.recommendation,
      riskMetrics: stopLossLevels.riskMetrics,
      metadata: {
        processingTime: stopLossLevels.processingTime,
        timestamp: new Date().toISOString()
      }
    };

    console.log(`✅ [${requestId}] Stop loss calculated`, {
      symbol: symbol,
      recommendedLevel: stopLossLevels.recommendation?.recommendedPrice,
      riskPercentage: stopLossLevels.recommendation?.riskPercentage,
      totalTime: Date.now() - startTime
    });
    
    res.json({
      success: true,
      data: responseData,
      message: 'Stop loss levels calculated successfully'
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Stop loss calculation failed`, {
      error: error.message,
      errorStack: error.stack,
      totalTime: Date.now() - startTime
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to calculate stop loss levels',
      details: error.message
    });
  }
});

// Get portfolio risk analysis
// GET /api/risk/management/portfolio-analysis
router.get('/management/portfolio-analysis', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const startTime = Date.now();
  
  try {
    const userId = req.user.sub;
    
    console.log(`📊 [${requestId}] Performing portfolio risk analysis`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
    });

    // Get comprehensive portfolio risk analysis
    const riskAnalysis = await riskManager.analyzePortfolioRisk(userId);

    const responseData = {
      overallRisk: riskAnalysis.overallRisk,
      diversification: riskAnalysis.diversification,
      correlationMatrix: riskAnalysis.correlationMatrix,
      sectorExposure: riskAnalysis.sectorExposure,
      concentrationRisk: riskAnalysis.concentrationRisk,
      volatilityMetrics: riskAnalysis.volatilityMetrics,
      recommendations: riskAnalysis.recommendations,
      metadata: {
        processingTime: riskAnalysis.processingTime,
        timestamp: new Date().toISOString()
      }
    };

    console.log(`✅ [${requestId}] Portfolio risk analysis completed`, {
      overallRiskScore: riskAnalysis.overallRisk?.score,
      diversificationScore: riskAnalysis.diversification?.score,
      recommendationCount: riskAnalysis.recommendations?.length || 0,
      totalTime: Date.now() - startTime
    });
    
    res.json({
      success: true,
      data: responseData,
      message: 'Portfolio risk analysis completed successfully'
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Portfolio risk analysis failed`, {
      error: error.message,
      errorStack: error.stack,
      totalTime: Date.now() - startTime
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to perform portfolio risk analysis',
      details: error.message
    });
  }
});

// Get risk management settings
// GET /api/risk/management/settings
router.get('/management/settings', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  
  try {
    const userId = req.user.sub;
    
    console.log(`⚙️ [${requestId}] Fetching risk management settings`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
    });

    // Get user's risk management settings
    const settings = await riskManager.getUserSettings(userId);

    const responseData = {
      defaultRiskPerTrade: settings.defaultRiskPerTrade || 0.02,
      maxPositionSize: settings.maxPositionSize || 0.1,
      maxDailyRisk: settings.maxDailyRisk || 0.05,
      stopLossMethod: settings.stopLossMethod || 'volatility',
      correlationLimit: settings.correlationLimit || 0.7,
      sectorConcentrationLimit: settings.sectorConcentrationLimit || 0.25,
      enableRealTimeAlerts: settings.enableRealTimeAlerts || false,
      alertThresholds: settings.alertThresholds || {
        portfolioDrawdown: 0.05,
        positionLoss: 0.02,
        correlationIncrease: 0.8
      }
    };

    console.log(`✅ [${requestId}] Risk management settings retrieved`);
    
    res.json({
      success: true,
      data: responseData,
      message: 'Risk management settings retrieved successfully'
    });
    
  } catch (error) {
    console.error(`❌ [${requestId}] Failed to fetch risk management settings`, {
      error: error.message,
      errorStack: error.stack
    });
    
    res.status(500).json({
      success: false,
      error: 'Failed to retrieve risk management settings',
      details: error.message
    });
  }
});

module.exports = router;
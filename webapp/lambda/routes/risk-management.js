const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const { createValidationMiddleware, sanitizers } = require('../middleware/validation');
const RiskManager = require('../utils/riskManager');
const AlpacaService = require('../utils/alpacaService');
const apiKeyService = require('../utils/apiKeyService');
const logger = require('../utils/logger');
const { responseFormatter } = require('../utils/responseFormatter');

const router = express.Router();

// Apply authentication middleware to all routes
router.use(authenticateToken);

// Initialize risk manager
const riskManager = new RiskManager();

// Validation schemas for risk management endpoints
const riskValidationSchemas = {
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
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10, trim: true }),
      validator: (value) => ['buy', 'sell', 'long', 'short'].includes(value.toLowerCase()),
      errorMessage: 'Direction must be buy, sell, long, or short'
    },
    portfolioValue: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 1000, max: 100000000 }),
      validator: (value) => !value || (value >= 1000 && value <= 100000000),
      errorMessage: 'Portfolio value must be between 1,000 and 100,000,000'
    },
    riskPerTrade: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0.001, max: 0.1, defaultValue: 0.02 }),
      validator: (value) => !value || (value >= 0.001 && value <= 0.1),
      errorMessage: 'Risk per trade must be between 0.1% and 10%'
    },
    maxPositionSize: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0.01, max: 0.5, defaultValue: 0.1 }),
      validator: (value) => !value || (value >= 0.01 && value <= 0.5),
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
      sanitizer: (value) => sanitizers.number(value, { min: 0.01, max: 100000 }),
      validator: (value) => value >= 0.01 && value <= 100000,
      errorMessage: 'Entry price must be between 0.01 and 100,000'
    },
    direction: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10, trim: true }),
      validator: (value) => ['long', 'short'].includes(value.toLowerCase()),
      errorMessage: 'Direction must be long or short'
    }
  }
};

// Calculate position size based on risk management
router.post('/position-size', createValidationMiddleware(riskValidationSchemas.positionSize), async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const startTime = Date.now();
  
  try {
    const userId = req.user.sub;
    const { symbol, direction, portfolioValue, riskPerTrade = 0.02, maxPositionSize = 0.1 } = req.validated;
    
    logger.info(`🎯 [${requestId}] Calculating position size`, {
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
        const response = responseFormatter.error('Portfolio value required when no API credentials available', 400);
        return res.status(400).json(response);
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

    const response = responseFormatter.success(responseData, 'Position size calculated successfully');
    
    logger.info(`✅ [${requestId}] Position size calculated`, {
      symbol: symbol,
      recommendedSize: positionSizing.recommendedSize,
      riskScore: positionSizing.riskMetrics.overallRiskScore,
      recommendation: positionSizing.recommendation.recommendation,
      totalTime: Date.now() - startTime
    });
    
    res.json(response);
    
  } catch (error) {
    logger.error(`❌ [${requestId}] Position size calculation failed`, {
      error: error.message,
      errorStack: error.stack,
      totalTime: Date.now() - startTime
    });
    
    const response = responseFormatter.error(
      'Failed to calculate position size',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

// Calculate stop loss and take profit levels
router.post('/stop-loss', createValidationMiddleware(riskValidationSchemas.stopLoss), async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const startTime = Date.now();
  
  try {
    const userId = req.user.sub;
    const { symbol, entryPrice, direction } = req.validated;
    
    logger.info(`🛡️ [${requestId}] Calculating stop loss levels`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
      symbol: symbol,
      entryPrice: entryPrice,
      direction: direction
    });

    // Calculate stop loss and take profit levels
    const stopLossLevels = await riskManager.calculateStopLossTakeProfit({
      symbol: symbol,
      entryPrice: entryPrice,
      direction: direction,
      riskPerTrade: 0.02
    });

    // Prepare response data
    const responseData = {
      symbol: symbol,
      entryPrice: entryPrice,
      direction: direction,
      stopLoss: stopLossLevels.stopLoss,
      takeProfit: stopLossLevels.takeProfit,
      levels: {
        stopLossDistance: stopLossLevels.stopLossDistance,
        takeProfitDistance: stopLossLevels.takeProfitDistance,
        riskRewardRatio: stopLossLevels.riskRewardRatio,
        maxRiskAmount: stopLossLevels.maxRiskAmount
      },
      prices: {
        entry: entryPrice,
        stopLoss: stopLossLevels.stopLoss,
        takeProfit: stopLossLevels.takeProfit
      },
      percentages: {
        stopLossPercent: direction === 'long' ? 
          ((entryPrice - stopLossLevels.stopLoss) / entryPrice * 100).toFixed(2) :
          ((stopLossLevels.stopLoss - entryPrice) / entryPrice * 100).toFixed(2),
        takeProfitPercent: direction === 'long' ? 
          ((stopLossLevels.takeProfit - entryPrice) / entryPrice * 100).toFixed(2) :
          ((entryPrice - stopLossLevels.takeProfit) / entryPrice * 100).toFixed(2)
      },
      metadata: {
        timestamp: new Date().toISOString(),
        processingTime: Date.now() - startTime
      }
    };

    const response = responseFormatter.success(responseData, 'Stop loss levels calculated successfully');
    
    logger.info(`✅ [${requestId}] Stop loss levels calculated`, {
      symbol: symbol,
      stopLoss: stopLossLevels.stopLoss,
      takeProfit: stopLossLevels.takeProfit,
      riskRewardRatio: stopLossLevels.riskRewardRatio,
      totalTime: Date.now() - startTime
    });
    
    res.json(response);
    
  } catch (error) {
    logger.error(`❌ [${requestId}] Stop loss calculation failed`, {
      error: error.message,
      errorStack: error.stack,
      totalTime: Date.now() - startTime
    });
    
    const response = responseFormatter.error(
      'Failed to calculate stop loss levels',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

// Get portfolio risk analysis
router.get('/portfolio-analysis', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const startTime = Date.now();
  
  try {
    const userId = req.user.sub;
    
    logger.info(`📊 [${requestId}] Generating portfolio risk analysis`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
    });

    // Get user's API credentials
    const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
    if (!credentials) {
      const response = responseFormatter.error('API credentials required for portfolio analysis', 400);
      return res.status(400).json(response);
    }

    // Get portfolio composition
    const portfolioComposition = await riskManager.getPortfolioComposition(userId);
    
    // Calculate portfolio risk metrics
    const portfolioRisk = await riskManager.calculatePortfolioRisk(portfolioComposition);
    
    // Get account information
    const alpacaService = new AlpacaService(credentials.apiKey, credentials.apiSecret, credentials.isSandbox);
    const account = await alpacaService.getAccount();
    const portfolioValue = parseFloat(account.portfolio_value);

    // Calculate position count and diversification
    const positionCount = Object.keys(portfolioComposition).length;
    const diversificationScore = Math.min(1.0, positionCount / 20);
    
    // Calculate largest position concentration
    const totalValue = Object.values(portfolioComposition).reduce((sum, value) => sum + value, 0);
    const concentrations = Object.entries(portfolioComposition)
      .map(([symbol, value]) => ({
        symbol: symbol,
        value: value,
        concentration: totalValue > 0 ? value / totalValue : 0
      }))
      .sort((a, b) => b.concentration - a.concentration);

    // Prepare response data
    const responseData = {
      portfolioValue: portfolioValue,
      positionCount: positionCount,
      diversificationScore: diversificationScore,
      portfolioRisk: portfolioRisk,
      riskLevel: portfolioRisk < 0.3 ? 'low' : portfolioRisk < 0.6 ? 'moderate' : 'high',
      concentrations: concentrations.slice(0, 10),
      riskMetrics: {
        diversificationRisk: 1.0 - diversificationScore,
        concentrationRisk: concentrations[0]?.concentration || 0,
        portfolioRisk: portfolioRisk,
        overallRiskScore: Math.max(portfolioRisk, concentrations[0]?.concentration || 0)
      },
      recommendations: generatePortfolioRecommendations({
        positionCount,
        diversificationScore,
        portfolioRisk,
        maxConcentration: concentrations[0]?.concentration || 0
      }),
      metadata: {
        timestamp: new Date().toISOString(),
        processingTime: Date.now() - startTime
      }
    };

    const response = responseFormatter.success(responseData, 'Portfolio risk analysis completed successfully');
    
    logger.info(`✅ [${requestId}] Portfolio risk analysis completed`, {
      positionCount: positionCount,
      portfolioRisk: portfolioRisk,
      diversificationScore: diversificationScore,
      totalTime: Date.now() - startTime
    });
    
    res.json(response);
    
  } catch (error) {
    logger.error(`❌ [${requestId}] Portfolio risk analysis failed`, {
      error: error.message,
      errorStack: error.stack,
      totalTime: Date.now() - startTime
    });
    
    const response = responseFormatter.error(
      'Failed to analyze portfolio risk',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

// Get risk management settings and limits
router.get('/settings', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  
  try {
    const userId = req.user.sub;
    
    logger.info(`⚙️ [${requestId}] Fetching risk management settings`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
    });

    const riskSettings = {
      positionSizing: {
        defaultRiskPerTrade: 0.02,
        maxRiskPerTrade: 0.1,
        defaultMaxPositionSize: 0.1,
        maxPositionSize: 0.5
      },
      concentrationLimits: {
        maxSinglePosition: 0.15,
        maxSectorExposure: {
          'Technology': 0.30,
          'Healthcare': 0.25,
          'Financial Services': 0.20,
          'Consumer Discretionary': 0.20,
          'Industrials': 0.15,
          'Energy': 0.10,
          'Materials': 0.10,
          'Real Estate': 0.10,
          'Utilities': 0.10,
          'Consumer Staples': 0.15,
          'Communication Services': 0.15,
          'Other': 0.05
        }
      },
      stopLossSettings: {
        defaultStopLoss: 0.05,
        maxStopLoss: 0.20,
        defaultTakeProfit: 0.10,
        defaultRiskRewardRatio: 2.0,
        minRiskRewardRatio: 1.0,
        maxRiskRewardRatio: 5.0
      },
      riskLevels: {
        low: { threshold: 0.3, description: 'Conservative risk profile' },
        moderate: { threshold: 0.6, description: 'Balanced risk profile' },
        high: { threshold: 0.8, description: 'Aggressive risk profile' },
        extreme: { threshold: 1.0, description: 'Very high risk profile' }
      },
      diversificationTargets: {
        minPositions: 10,
        optimalPositions: 20,
        maxPositions: 50,
        minSectors: 5,
        optimalSectors: 8
      }
    };

    const response = responseFormatter.success(riskSettings, 'Risk management settings retrieved successfully');
    res.json(response);
    
  } catch (error) {
    logger.error(`❌ [${requestId}] Error retrieving risk settings`, {
      error: error.message,
      errorStack: error.stack
    });
    
    const response = responseFormatter.error(
      'Failed to retrieve risk management settings',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

// Helper method for portfolio recommendations
function generatePortfolioRecommendations({ positionCount, diversificationScore, portfolioRisk, maxConcentration }) {
  const recommendations = [];
  
  if (positionCount < 10) {
    recommendations.push({
      type: 'diversification',
      priority: 'high',
      message: 'Consider adding more positions to improve diversification',
      target: `Add ${10 - positionCount} more positions`
    });
  }
  
  if (maxConcentration > 0.15) {
    recommendations.push({
      type: 'concentration',
      priority: 'high',
      message: 'Reduce concentration in largest position',
      target: `Reduce largest position to under 15%`
    });
  }
  
  if (portfolioRisk > 0.7) {
    recommendations.push({
      type: 'risk_reduction',
      priority: 'medium',
      message: 'Consider reducing overall portfolio risk',
      target: 'Improve diversification and reduce position sizes'
    });
  }
  
  if (diversificationScore < 0.5) {
    recommendations.push({
      type: 'diversification',
      priority: 'medium',
      message: 'Portfolio needs better diversification',
      target: 'Add positions in different sectors'
    });
  }
  
  return recommendations;
}

module.exports = router;
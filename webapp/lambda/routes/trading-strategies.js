const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const { createValidationMiddleware, sanitizers } = require('../middleware/validation');
const tradingStrategyEngine = require('../utils/tradingStrategyEngine');
const logger = require('../utils/logger');
const { responseFormatter } = require('../utils/responseFormatter');

const router = express.Router();

// Apply authentication middleware to all routes
router.use(authenticateToken);

// Validation schemas for trading strategy endpoints
const strategyValidationSchemas = {
  create: {
    type: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 50, trim: true }),
      validator: (value) => ['momentum', 'mean_reversion', 'breakout', 'pattern_recognition'].includes(value),
      errorMessage: 'Type must be one of: momentum, mean_reversion, breakout, pattern_recognition'
    },
    symbols: {
      required: true,
      type: 'array',
      validator: (value) => Array.isArray(value) && value.length > 0 && value.length <= 10,
      errorMessage: 'Symbols must be an array with 1-10 stock symbols'
    },
    active: {
      type: 'boolean',
      sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
      validator: (value) => typeof value === 'boolean',
      errorMessage: 'Active must be true or false'
    },
    name: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 100, trim: true }),
      validator: (value) => !value || (value.length >= 2 && value.length <= 100),
      errorMessage: 'Name must be 2-100 characters if provided'
    },
    description: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 500, trim: true }),
      validator: (value) => !value || value.length <= 500,
      errorMessage: 'Description must be 500 characters or less'
    }
  },
  
  execute: {
    signal: {
      type: 'object',
      validator: (value) => !value || (typeof value === 'object' && value.type),
      errorMessage: 'Signal must be an object with a type property'
    }
  }
};

// Get all trading strategies for authenticated user
router.get('/', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  
  try {
    const userId = req.user.sub;
    
    logger.info(`📊 [${requestId}] Fetching user trading strategies`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
    });
    
    const strategies = await tradingStrategyEngine.getUserStrategies(userId);
    
    const response = responseFormatter.success({
      strategies,
      totalCount: strategies.length,
      activeCount: strategies.filter(s => s.is_active).length
    }, 'Trading strategies retrieved successfully');
    
    logger.info(`✅ [${requestId}] User strategies retrieved`, {
      totalCount: strategies.length,
      activeCount: strategies.filter(s => s.is_active).length
    });
    
    res.json(response);
  } catch (error) {
    logger.error(`❌ [${requestId}] Error retrieving strategies`, {
      error: error.message,
      errorStack: error.stack
    });
    
    const response = responseFormatter.error(
      'Failed to retrieve trading strategies',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

// Get specific trading strategy
router.get('/:strategyId', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const { strategyId } = req.params;
  
  try {
    const userId = req.user.sub;
    
    logger.info(`📊 [${requestId}] Fetching strategy details`, {
      strategyId,
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
    });
    
    const strategy = await tradingStrategyEngine.getStrategyPerformance(strategyId);
    
    if (!strategy) {
      const response = responseFormatter.error('Strategy not found', 404);
      return res.status(404).json(response);
    }
    
    // Verify ownership
    if (strategy.user_id !== userId) {
      const response = responseFormatter.error('Access denied', 403);
      return res.status(403).json(response);
    }
    
    const response = responseFormatter.success(strategy, 'Strategy details retrieved successfully');
    
    logger.info(`✅ [${requestId}] Strategy details retrieved`, {
      strategyId,
      strategyType: strategy.strategy_type
    });
    
    res.json(response);
  } catch (error) {
    logger.error(`❌ [${requestId}] Error retrieving strategy details`, {
      error: error.message,
      errorStack: error.stack,
      strategyId
    });
    
    const response = responseFormatter.error(
      'Failed to retrieve strategy details',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

// Create new trading strategy
router.post('/', createValidationMiddleware(strategyValidationSchemas.create), async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const startTime = Date.now();
  
  try {
    const userId = req.user.sub;
    const { type, symbols, parameters, riskManagement, active, name, description } = req.body;
    
    logger.info(`🚀 [${requestId}] Creating new trading strategy`, {
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
      strategyType: type,
      symbols: symbols,
      active: active
    });
    
    // Build strategy configuration
    const strategyConfig = {
      type,
      symbols,
      parameters: parameters || {},
      riskManagement: riskManagement || {
        riskPerTrade: 0.02,
        maxPositionSize: 0.1,
        stopLoss: 0.05,
        takeProfit: 0.10
      },
      active: active || false,
      name: name || `${type} Strategy`,
      description: description || `Automated ${type} trading strategy`,
      provider: 'alpaca'
    };
    
    // Register strategy with engine
    const result = await tradingStrategyEngine.registerStrategy(userId, strategyConfig);
    
    const response = responseFormatter.success({
      strategyId: result.strategyId,
      status: result.status,
      active: result.active,
      configuration: strategyConfig
    }, 'Trading strategy created successfully');
    
    logger.info(`✅ [${requestId}] Strategy created successfully`, {
      strategyId: result.strategyId,
      strategyType: type,
      totalTime: Date.now() - startTime
    });
    
    res.status(201).json(response);
  } catch (error) {
    logger.error(`❌ [${requestId}] Error creating strategy`, {
      error: error.message,
      errorStack: error.stack,
      totalTime: Date.now() - startTime
    });
    
    const response = responseFormatter.error(
      'Failed to create trading strategy',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

// Execute trading strategy
router.post('/:strategyId/execute', createValidationMiddleware(strategyValidationSchemas.execute), async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const { strategyId } = req.params;
  const { signal } = req.body;
  const startTime = Date.now();
  
  try {
    const userId = req.user.sub;
    
    logger.info(`🎯 [${requestId}] Executing trading strategy`, {
      strategyId,
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
      hasSignal: !!signal
    });
    
    // Execute strategy
    const executionResult = await tradingStrategyEngine.executeStrategy(strategyId, signal);
    
    const response = responseFormatter.success({
      executionId: `exec-${Date.now()}`,
      strategyId,
      executionResult,
      executionTime: Date.now() - startTime
    }, 'Strategy executed successfully');
    
    logger.info(`✅ [${requestId}] Strategy executed successfully`, {
      strategyId,
      ordersPlaced: executionResult.orders?.length || 0,
      totalValue: executionResult.totalValue || 0,
      totalTime: Date.now() - startTime
    });
    
    res.json(response);
  } catch (error) {
    logger.error(`❌ [${requestId}] Error executing strategy`, {
      error: error.message,
      errorStack: error.stack,
      strategyId,
      totalTime: Date.now() - startTime
    });
    
    const response = responseFormatter.error(
      'Failed to execute trading strategy',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

// Update trading strategy
router.put('/:strategyId', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const { strategyId } = req.params;
  
  try {
    const userId = req.user.sub;
    const { active, parameters, riskManagement, name, description } = req.body;
    
    logger.info(`🔄 [${requestId}] Updating trading strategy`, {
      strategyId,
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
      active
    });
    
    // For now, we'll implement a simple active/inactive toggle
    // More comprehensive updates would require additional validation
    if (active === false) {
      const result = await tradingStrategyEngine.deactivateStrategy(strategyId);
      
      if (result) {
        const response = responseFormatter.success({
          strategyId,
          status: 'deactivated'
        }, 'Strategy deactivated successfully');
        
        logger.info(`✅ [${requestId}] Strategy deactivated`, { strategyId });
        res.json(response);
      } else {
        const response = responseFormatter.error('Failed to deactivate strategy', 500);
        res.status(500).json(response);
      }
    } else {
      const response = responseFormatter.error('Strategy updates not fully implemented', 501);
      res.status(501).json(response);
    }
  } catch (error) {
    logger.error(`❌ [${requestId}] Error updating strategy`, {
      error: error.message,
      errorStack: error.stack,
      strategyId
    });
    
    const response = responseFormatter.error(
      'Failed to update trading strategy',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

// Delete trading strategy
router.delete('/:strategyId', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const { strategyId } = req.params;
  
  try {
    const userId = req.user.sub;
    
    logger.info(`🗑️ [${requestId}] Deleting trading strategy`, {
      strategyId,
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
    });
    
    // First deactivate the strategy
    await tradingStrategyEngine.deactivateStrategy(strategyId);
    
    // Then delete from database
    const { query } = require('../utils/database');
    await query(`
      DELETE FROM trading_strategies 
      WHERE id = $1 AND user_id = $2
    `, [strategyId, userId]);
    
    const response = responseFormatter.success({
      strategyId,
      status: 'deleted'
    }, 'Strategy deleted successfully');
    
    logger.info(`✅ [${requestId}] Strategy deleted`, { strategyId });
    res.json(response);
  } catch (error) {
    logger.error(`❌ [${requestId}] Error deleting strategy`, {
      error: error.message,
      errorStack: error.stack,
      strategyId
    });
    
    const response = responseFormatter.error(
      'Failed to delete trading strategy',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

// Get strategy execution history
router.get('/:strategyId/executions', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  const { strategyId } = req.params;
  const { limit = 50, offset = 0 } = req.query;
  
  try {
    const userId = req.user.sub;
    
    logger.info(`📊 [${requestId}] Fetching strategy execution history`, {
      strategyId,
      userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
      limit,
      offset
    });
    
    const { query } = require('../utils/database');
    const result = await query(`
      SELECT 
        e.*,
        s.user_id
      FROM strategy_executions e
      JOIN trading_strategies s ON e.strategy_id = s.id
      WHERE e.strategy_id = $1 AND s.user_id = $2
      ORDER BY e.executed_at DESC
      LIMIT $3 OFFSET $4
    `, [strategyId, userId, limit, offset]);
    
    const response = responseFormatter.success({
      executions: result.rows,
      strategyId,
      pagination: {
        limit: parseInt(limit),
        offset: parseInt(offset),
        total: result.rows.length
      }
    }, 'Strategy execution history retrieved successfully');
    
    logger.info(`✅ [${requestId}] Execution history retrieved`, {
      strategyId,
      executionCount: result.rows.length
    });
    
    res.json(response);
  } catch (error) {
    logger.error(`❌ [${requestId}] Error retrieving execution history`, {
      error: error.message,
      errorStack: error.stack,
      strategyId
    });
    
    const response = responseFormatter.error(
      'Failed to retrieve execution history',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

// Get available strategy types and their configurations
router.get('/config/types', async (req, res) => {
  const requestId = res.locals.requestId || 'unknown';
  
  try {
    logger.info(`📋 [${requestId}] Fetching available strategy types`);
    
    const strategyTypes = {
      momentum: {
        name: 'Momentum Strategy',
        description: 'Follows price momentum and trend direction',
        parameters: {
          lookbackPeriod: { type: 'number', default: 20, min: 5, max: 100 },
          momentumThreshold: { type: 'number', default: 0.02, min: 0.01, max: 0.1 },
          rsiOverbought: { type: 'number', default: 70, min: 50, max: 90 },
          rsiOversold: { type: 'number', default: 30, min: 10, max: 50 }
        }
      },
      mean_reversion: {
        name: 'Mean Reversion Strategy',
        description: 'Trades based on price returning to historical average',
        parameters: {
          lookbackPeriod: { type: 'number', default: 20, min: 10, max: 50 },
          smaLength: { type: 'number', default: 20, min: 10, max: 50 },
          buyThreshold: { type: 'number', default: -0.02, min: -0.1, max: -0.01 },
          sellThreshold: { type: 'number', default: 0.02, min: 0.01, max: 0.1 }
        }
      },
      breakout: {
        name: 'Breakout Strategy',
        description: 'Trades on price breaking through support or resistance',
        parameters: {
          lookbackPeriod: { type: 'number', default: 50, min: 20, max: 100 },
          breakoutPeriod: { type: 'number', default: 20, min: 10, max: 50 },
          volumeMultiplier: { type: 'number', default: 1.5, min: 1.0, max: 3.0 }
        }
      },
      pattern_recognition: {
        name: 'Pattern Recognition Strategy',
        description: 'Trades based on technical chart patterns',
        parameters: {
          lookbackPeriod: { type: 'number', default: 100, min: 50, max: 200 },
          confidenceThreshold: { type: 'number', default: 0.7, min: 0.5, max: 0.9 },
          patterns: { type: 'array', default: ['double_top', 'double_bottom', 'head_shoulders'] }
        }
      }
    };
    
    const response = responseFormatter.success({
      strategyTypes,
      supportedProviders: ['alpaca'],
      riskManagementDefaults: {
        riskPerTrade: 0.02,
        maxPositionSize: 0.1,
        stopLoss: 0.05,
        takeProfit: 0.10
      }
    }, 'Strategy configuration retrieved successfully');
    
    res.json(response);
  } catch (error) {
    logger.error(`❌ [${requestId}] Error retrieving strategy config`, {
      error: error.message,
      errorStack: error.stack
    });
    
    const response = responseFormatter.error(
      'Failed to retrieve strategy configuration',
      500,
      { details: error.message }
    );
    res.status(500).json(response);
  }
});

module.exports = router;
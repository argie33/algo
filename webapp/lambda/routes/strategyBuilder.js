/**
 * Strategy Builder API Routes
 * Handles AI strategy generation, validation, backtesting, and HFT deployment
 */

const express = require('express');

const { createLogger } = require('../utils/logger');
const { query } = require('../utils/database');
const AIStrategyGenerator = require('../services/aiStrategyGenerator');
const AIStrategyGeneratorStreaming = require('../services/aiStrategyGeneratorStreaming');
const { authenticateToken } = require('../middleware/auth');

const router = express.Router();

// Initialize services  
const logger = createLogger();
const aiGenerator = new AIStrategyGenerator();
const _aiStreamingGenerator = new AIStrategyGeneratorStreaming();

/**
 * Generate strategy from natural language
 * POST /api/strategies/ai-generate
 */
router.post('/ai-generate', authenticateToken, async (req, res) => {
  try {
    const { prompt, symbols = [], preferences = {} } = req.body;
    const userId = req.user.id;
    
    logger.info('AI strategy generation request', {
      userId,
      prompt: prompt?.substring(0, 100),
      symbolCount: symbols.length
    });

    // Validate input
    if (!prompt || prompt.trim().length < 10) {
      return res.status(400).json({
        success: false,
        error: 'Strategy description must be at least 10 characters long'
      });
    }

    // Get available symbols if none provided
    let targetSymbols = symbols;
    if (targetSymbols.length === 0) {
      return res.error("No symbols provided for strategy", 400, {
        message: "Strategy requires at least one symbol"
      });
    }

    // Generate strategy using AI
    const result = await aiGenerator.generateFromNaturalLanguage(
      prompt,
      targetSymbols,
      { userId, ...preferences }
    );

    if (result.success) {
      logger.info('AI strategy generated successfully', {
        userId,
        strategyName: result.strategy.name,
        strategyType: result.strategy.strategyType
      });

      res.json({
        success: true,
        strategy: result.strategy
      });
    } else {
      logger.warn('AI strategy generation failed', {
        userId,
        error: result.error
      });

      return res.status(400).json({
        success: false,
        error: result.error
      });
    }
  } catch (error) {
    logger.error('AI strategy generation error', {
      userId: req.user?.id,
      error: error.message
    });

    return res.status(500).json({
      success: false,
      error: 'Internal server error during strategy generation'
    });
  }
});

/**
 * Validate strategy code and configuration
 * POST /api/strategies/validate
 */
router.post('/validate', authenticateToken, async (req, res) => {
  try {
    const { strategy } = req.body;
    const userId = req.user.id;
    
    logger.info('Strategy validation request', {
      userId,
      strategyName: strategy?.name
    });

    if (!strategy || !strategy.code) {
      return res.status(400).json({
        success: false,
        error: 'Strategy code is required for validation'
      });
    }

    // Validate strategy
    const validation = await aiGenerator.validateStrategy(strategy);
    
    logger.info('Strategy validation completed', {
      userId,
      isValid: validation.isValid,
      errorCount: validation.errors?.length || 0,
      warningCount: validation.warnings?.length || 0
    });

    res.json({
      success: true,
      validation: validation
    });
  } catch (error) {
    logger.error('Strategy validation error', {
      userId: req.user?.id,
      error: error.message
    });

    return res.status(500).json({
      success: false,
      error: 'Internal server error during strategy validation'
    });
  }
});

/**
 * Run backtest for AI-generated strategy
 * POST /api/backtest/run-ai-strategy
 */
router.post('/run-ai-strategy', authenticateToken, async (req, res) => {
  try {
    const { strategy, config = {}, symbols = [] } = req.body;
    const userId = req.user.id;
    
    logger.info('AI strategy backtest request', {
      userId,
      strategyName: strategy?.name,
      symbolCount: symbols.length
    });

    if (!strategy || !strategy.code) {
      return res.status(400).json({
        success: false,
        error: 'Strategy is required for backtesting'
      });
    }

    // Set default backtest configuration
    const _backtestConfig = {
      startDate: config.startDate || '2023-01-01',
      endDate: config.endDate || '2023-12-31',
      initialCapital: config.initialCapital || 100000,
      commission: config.commission || 0.001,
      slippage: config.slippage || 0.0005,
      ...config
    };

    // Use strategy symbols if none provided
    const backtestSymbols = symbols.length > 0 ? symbols : (strategy.symbols);
    if (backtestSymbols.length === 0) {
      return res.status(400).json({
        success: false,
        error: 'At least one symbol is required for backtesting'
      });
    }

    // Run backtest - not implemented yet
    return res.error("Strategy backtesting not implemented", 501, {
      message: "Backtesting service is not yet available",
      service: "strategy-backtest"
    });
    
    // TODO: Implement actual backtesting service
    // const result = await backtestService.runAIStrategyBacktest(userId, {
    //   strategy,
    //   config: backtestConfig,
    //   symbols: backtestSymbols
    // });
  } catch (error) {
    logger.error('AI strategy backtest error', {
      userId: req.user?.id,
      error: error.message
    });

    return res.status(500).json({
      success: false,
      error: 'Internal server error during backtest execution'
    });
  }
});

/**
 * Deploy strategy to HFT engine
 * POST /api/strategies/deploy-hft
 */
router.post('/deploy-hft', authenticateToken, async (req, res) => {
  try {
    const { strategy, backtestResults, hftConfig: _hftConfig = {} } = req.body;
    const userId = req.user.id;
    
    logger.info('HFT deployment request', {
      userId,
      strategyName: strategy?.name,
      sharpeRatio: backtestResults?.metrics?.sharpeRatio
    });

    if (!strategy || !backtestResults) {
      return res.status(400).json({
        success: false,
        error: 'Strategy and backtest results are required for HFT deployment'
      });
    }

    // Check if strategy qualifies for HFT
    const qualificationCheck = {
      minSharpe: backtestResults.metrics.sharpeRatio >= 1.0,
      maxDrawdown: backtestResults.metrics.maxDrawdown <= 0.25,
      minWinRate: backtestResults.metrics.winRate >= 0.45
    };

    const isQualified = Object.values(qualificationCheck).every(Boolean);
    
    if (!isQualified) {
      return res.status(400).json({
        success: false,
        error: 'Strategy does not meet HFT deployment requirements',
        requirements: {
          sharpeRatio: { required: '>= 1.0', actual: backtestResults.metrics.sharpeRatio },
          maxDrawdown: { required: '<= 25%', actual: `${(backtestResults.metrics.maxDrawdown * 100).toFixed(1)}%` },
          winRate: { required: '>= 45%', actual: `${(backtestResults.metrics.winRate * 100).toFixed(1)}%` }
        }
      });
    }

    // Deploy to HFT engine - not implemented yet
    return res.error("HFT deployment not implemented", 501, {
      message: "High-frequency trading deployment is not yet available",
      service: "hft-deployment"
    });
    
    // TODO: Implement actual HFT deployment service
    // const deploymentResult = await tradingService.deployToHFT(userId, {
    //   strategy,
    //   backtestResults,
    //   riskSettings: {
    //     positionSize: hftConfig.positionSize || 0.1,
    //     stopLoss: hftConfig.stopLoss || 0.02,
    //     takeProfit: hftConfig.takeProfit || 0.015,
    //     riskLevel: hftConfig.riskLevel || 'medium'
    //   }
    // });

    // Deployment result handling removed - not implemented
  } catch (error) {
    logger.error('HFT deployment error', {
      userId: req.user?.id,
      error: error.message
    });

    return res.status(500).json({
      success: false,
      error: 'Internal server error during HFT deployment'
    });
  }
});

/**
 * Get available symbols for strategy creation
 * GET /api/strategies/available-symbols
 */
router.get('/available-symbols', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.id;
    logger.info('Available symbols request', { userId });
    
    // Get available symbols from database
    const result = await query(
      "SELECT DISTINCT symbol FROM stock_symbols WHERE is_active = true ORDER BY symbol LIMIT 100"
    );
    
    if (!result || !result.rows) {
      return res.error("Unable to fetch available symbols", 503, {
        service: "symbols"
      });
    }
    
    const symbols = result.rows.map(row => row.symbol);
    
    res.json({
      success: true,
      symbols: symbols,
      count: symbols.length
    });
  } catch (error) {
    logger.error('Available symbols error', {
      userId: req.user?.id,
      error: error.message
    });

    return res.status(500).json({
      success: false,
      error: 'Failed to retrieve available symbols'
    });
  }
});

/**
 * Get user's strategies with status
 * GET /api/strategies/list
 */
router.get('/list', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.id;
    const { includeBacktests = false, includeDeployments = false } = req.query;
    
    logger.info('User strategies list request', {
      userId,
      includeBacktests,
      includeDeployments
    });

    // User strategies service not implemented yet
    return res.error("User strategies not implemented", 501, {
      message: "User strategy management is not yet available",
      service: "user-strategies"
    });
    
    // TODO: Implement actual user strategies service
    // const result = await tradingService.getUserStrategies(userId);
    
    // User strategies result handling removed - not implemented
  } catch (error) {
    logger.error('User strategies list error', {
      userId: req.user?.id,
      error: error.message
    });

    return res.status(500).json({
      success: false,
      error: 'Failed to retrieve user strategies'
    });
  }
});

/**
 * Get strategy templates for AI generation
 * GET /api/strategies/templates
 */
router.get('/templates', authenticateToken, async (req, res) => {
  try {
    const templates = Object.entries(aiGenerator.strategyTemplates || {}).map(([key, template]) => ({
      id: key,
      name: template.description || key,
      type: key,
      description: template.description,
      parameters: template.parameters,
      complexity: template.complexity || 'medium',
      aiEnhanced: true // Mark as AI-enhanced
    }));

    res.json({
      success: true,
      templates: templates,
      count: templates.length,
      aiFeatures: {
        streamingEnabled: true,
        optimizationSupported: true,
        insightsGeneration: true,
        explanationLevels: ['basic', 'medium', 'detailed']
      }
    });
  } catch (error) {
    logger.error('Strategy templates error', {
      userId: req.user?.id,
      error: error.message
    });

    return res.status(500).json({
      success: false,
      error: 'Failed to retrieve strategy templates'
    });
  }
});

module.exports = router;
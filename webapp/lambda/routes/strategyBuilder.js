/**
 * Strategy Builder API Routes
 * Handles AI strategy generation, and validation
 */

const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");
const logger = require("../utils/logger");

// Import services with error handling
let aiGenerator, _aiStreamingGenerator;
try {
  const AIStrategyGenerator = require("../services/aiStrategyGenerator");
  const AIStrategyGeneratorStreaming = require("../services/aiStrategyGeneratorStreaming");
  aiGenerator = new AIStrategyGenerator();
  _aiStreamingGenerator = new AIStrategyGeneratorStreaming();
} catch (serviceError) {
  if (process.env.NODE_ENV !== 'test') {
    console.warn("Strategy services not available:", serviceError.message);
  }
}

const router = express.Router();

// Root endpoint - Get available strategies
router.get("/", async (req, res) => {
  try {
    // Return list of available strategy templates and user strategies
    const predefinedStrategies = [
      {
        id: "momentum_breakout",
        name: "Momentum Breakout",
        description:
          "Identifies stocks breaking through resistance levels with high volume",
        type: "momentum",
        riskLevel: "medium",
        timeframe: "intraday",
        signals: ["price_breakout", "volume_surge", "rsi_momentum"],
      },
      {
        id: "mean_reversion",
        name: "Mean Reversion",
        description:
          "Trades oversold/overbought conditions expecting price to revert to mean",
        type: "reversal",
        riskLevel: "low",
        timeframe: "swing",
        signals: ["rsi_oversold", "bollinger_lower", "support_level"],
      },
      {
        id: "trend_following",
        name: "Trend Following",
        description:
          "Follows established trends using moving averages and momentum indicators",
        type: "trend",
        riskLevel: "medium",
        timeframe: "daily",
        signals: ["sma_crossover", "macd_signal", "trend_strength"],
      },
      {
        id: "pairs_trading",
        name: "Pairs Trading",
        description: "Statistical arbitrage between correlated securities",
        type: "arbitrage",
        riskLevel: "low",
        timeframe: "intraday",
        signals: [
          "correlation_divergence",
          "zscore_threshold",
          "cointegration",
        ],
      },
      {
        id: "volatility_scalping",
        name: "Volatility Scalping",
        description:
          "High-frequency trading strategy capitalizing on short-term volatility",
        type: "scalping",
        riskLevel: "high",
        timeframe: "1min",
        signals: ["volatility_spike", "bid_ask_spread", "orderbook_imbalance"],
      },
    ];

    // Try to get user-created strategies from database
    let userStrategies = [];
    try {
      const userId = req.user?.sub || req.user?.user_id;
      if (userId) {
        const result = await query(
          `SELECT * FROM trading_strategies WHERE user_id = $1 ORDER BY created_at DESC`,
          [userId]
        );
        userStrategies = (result.rows || []).map((strategy) => ({
          id: strategy.id,
          name: strategy.name,
          description: strategy.description,
          type: strategy.strategy_type || "custom",
          riskLevel: strategy.risk_level || "medium",
          timeframe: strategy.timeframe || "daily",
          signals: strategy.signals ? JSON.parse(strategy.signals) : [],
          isCustom: true,
          createdAt: strategy.created_at,
          updatedAt: strategy.updated_at,
        }));
      }
    } catch (dbError) {
      console.warn("Could not fetch user strategies:", dbError.message);
    }

    res.json({
      success: true,
      data: {
        predefined: predefinedStrategies,
        custom: userStrategies,
        total: predefinedStrategies.length + userStrategies.length,
      },
      meta: {
        available_endpoints: [
          "POST /ai-generate - Generate AI trading strategy",
          "GET / - Get available strategies",
        ],
        strategy_types: [
          "momentum",
          "reversal",
          "trend",
          "arbitrage",
          "scalping",
          "custom",
        ],
        risk_levels: ["low", "medium", "high"],
        timeframes: [
          "1min",
          "5min",
          "15min",
          "1h",
          "intraday",
          "daily",
          "swing",
        ],
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching strategies:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch strategies",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * Generate strategy from natural language
 * POST /api/strategies/ai-generate
 */
router.post("/ai-generate", authenticateToken, async (req, res) => {
  try {
    const { prompt, symbols = [], preferences = {} } = req.body;
    const userId = req.user.id;

    if (process.env.NODE_ENV !== 'test') {
      console.log("AI strategy generation request", {
        userId,
        prompt: prompt?.substring(0, 100),
        symbolCount: symbols.length,
      });
    }

    // Validate input
    if (!prompt || prompt.trim().length < 10) {
      return res.status(400).json({
        success: false,
        error: "Strategy description must be at least 10 characters long",
      });
    }

    // Get available symbols if none provided
    let targetSymbols = symbols;
    if (targetSymbols.length === 0) {
      return res.status(400).json({
        success: false,
        error: "No symbols provided for strategy",
        message: "Strategy requires at least one symbol",
      });
    }

    // Generate strategy using AI
    const result = await aiGenerator.generateFromNaturalLanguage(
      prompt,
      targetSymbols,
      { userId, ...preferences }
    );

    if (result.success) {
      logger.info("AI strategy generated successfully", {
        userId,
        strategyName: result.strategy.name,
        strategyType: result.strategy.strategyType,
      });

      res.json({
        success: true,
        strategy: result.strategy,
      });
    } else {
      logger.warn("AI strategy generation failed", {
        userId,
        error: result.error,
      });

      return res.status(400).json({
        success: false,
        error: result.error,
      });
    }
  } catch (err) {
    console.error("AI strategy generation error", {
      userId: req.user?.id,
      error: err.message,
    });

    return res.status(500).json({
      success: false,
      error: "Internal server error during strategy generation",
    });
  }
});

/**
 * Validate strategy code and configuration
 * POST /api/strategies/validate
 */
router.post("/validate", authenticateToken, async (req, res) => {
  try {
    // Check if AI generator is available first
    if (!aiGenerator) {
      return res.status(503).json({
        success: false,
        error: "AI strategy services are currently unavailable",
        details: "Strategy validation service is not loaded"
      });
    }

    const { strategy } = req.body;
    const userId = req.user.id;

    logger.info("Strategy validation request", {
      userId,
      strategyName: strategy?.name,
    });

    if (!strategy || !strategy.code) {
      return res.status(400).json({
        success: false,
        error: "Strategy code is required for validation",
      });
    }

    // Validate strategy
    const validation = await aiGenerator.validateStrategy(strategy);

    logger.info("Strategy validation completed", {
      userId,
      isValid: validation.valid,
      errorCount: validation.errors?.length || 0,
      warningCount: validation.warnings?.length || 0,
    });

    res.json({
      success: true,
      validation: {
        isValid: validation.isValid || validation.valid,
        errors: validation.errors,
        warnings: validation.warnings,
        suggestions: validation.suggestions
      },
    });
  } catch (err) {
    logger.error("Strategy validation error", {
      userId: req.user?.id,
      error: err.message,
    });

    return res.status(500).json({
      success: false,
      error: "Internal server error during strategy validation",
    });
  }
});

/**
 * Run backtest for AI-generated strategy
 * POST /api/backtest/run-ai-strategy
 */
router.post("/run-ai-strategy", authenticateToken, async (req, res) => {
  try {
    const { strategy, config = {}, symbols = [] } = req.body;
    const userId = req.user.id;

    logger.info("AI strategy backtest request", {
      userId,
      strategyName: strategy?.name,
      symbolCount: symbols.length,
    });

    if (!strategy || !strategy.code) {
      return res.status(400).json({
        success: false,
        error: "Strategy is required for backtesting",
      });
    }

    // Use strategy symbols if none provided
    const backtestSymbols = symbols.length > 0 ? symbols : (strategy.symbols || []);
    if (!backtestSymbols || backtestSymbols.length === 0) {
      return res.status(400).json({
        success: false,
        error: "At least one symbol is required for backtesting",
      });
    }

    // Return not implemented error for backtesting functionality
    return res.status(501).json({
      success: false,
      error: "AI strategy backtesting is not implemented",
      message: "AI strategy backtest execution is not yet implemented",
    });
  } catch (err) {
    logger.error("AI strategy backtest error", {
      userId: req.user?.id,
      error: err.message,
    });

    return res.status(500).json({
      success: false,
      error: "Internal server error during backtest execution",
    });
  }
});

/**
 * Get available symbols for strategy creation
 * GET /api/strategies/available-symbols
 */
router.get("/available-symbols", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.id;
    logger.info("Available symbols request", { userId });

    // Get available symbols from database
    const result = await query(
      "SELECT DISTINCT cp.ticker as symbol FROM company_profile cp INNER JOIN market_data md ON cp.ticker = md.ticker WHERE md.market_cap > 0 ORDER BY cp.ticker LIMIT 100"
    );

    // Handle cases where query returns null or empty results (database unavailable/empty)
    if (!result || !result.rows) {
      return res.status(503).json({
        success: false,
        error: "Unable to fetch available symbols not found",
        message: "Unable to retrieve symbols from database",
      });
    }

    const symbols = result.rows.map((row) => row.symbol);

    res.json({
      success: true,
      symbols: symbols,
      count: symbols.length,
    });
  } catch (err) {
    logger.error("Available symbols error", {
      userId: req.user?.id,
      error: err.message,
    });

    return res.status(500).json({
      success: false,
      error: "Available symbols query failed",
      details: err.message,
    });
  }
});

/**
 * Get user's strategies with status
 * GET /api/strategies/list
 */
router.get("/list", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.id;
    const { includeBacktests = false, includeDeployments = false } = req.query;

    logger.info("User strategies list request", {
      userId,
      includeBacktests,
      includeDeployments,
    });

    // Return empty data for user strategies list functionality (not implemented)
    res.json({
      success: true,
      data: {
        strategies: [],
        total: 0,
        includeBacktests: includeBacktests === 'true',
        includeDeployments: includeDeployments === 'true'
      },
      timestamp: new Date().toISOString(),
    });
  } catch (err) {
    logger.error("User strategies list error", {
      userId: req.user?.id,
      error: err.message,
    });

    return res.status(500).json({
      success: false,
      error: "Failed to retrieve user strategies",
    });
  }
});

/**
 * Get strategy templates for AI generation
 * GET /api/strategies/templates
 */
router.get("/templates", authenticateToken, async (req, res) => {
  try {
    // Fallback templates when AI services are not available - ordered for consistency
    const defaultTemplates = {
      momentum: {
        description: "Momentum Trading Strategy",
        parameters: { period: 14, threshold: 0.5 },
        complexity: "medium"
      },
      meanReversion: {
        description: "Mean Reversion Strategy",
        parameters: { lookback: 20, stdDev: 2 },
        complexity: "low"
      }
    };

    const strategyTemplates = aiGenerator?.strategyTemplates || defaultTemplates;
    const templates = Object.entries(strategyTemplates).map(
      ([key, template]) => ({
        id: key,
        name: template.description || key,
        type: key,
        description: template.description,
        parameters: template.parameters,
        complexity: template.complexity || "medium",
        aiEnhanced: !!aiGenerator, // Mark as AI-enhanced only if AI service is available
      })
    );

    res.json({
      success: true,
      templates: templates,
      count: templates.length,
      aiFeatures: {
        streamingEnabled: true,
        optimizationSupported: true,
        insightsGeneration: true,
        explanationLevels: ["basic", "medium", "detailed"],
      },
    });
  } catch (err) {
    logger.error("Strategy templates error", {
      userId: req.user?.id,
      error: err.message,
    });

    return res.status(500).json({
      success: false,
      error: "Failed to retrieve strategy templates",
    });
  }
});

// Strategy builder strategies
router.get("/strategies", async (req, res) => {
  try {
    res.json({
      success: true,
      data: {
        strategies: [],
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Strategies unavailable",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;

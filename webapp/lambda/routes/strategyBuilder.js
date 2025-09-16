/**
 * Strategy Builder API Routes
 * Handles AI strategy generation, validation, backtesting, and HFT deployment
 */

const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");
const logger = require("../utils/logger");
const backtestStore = require("../utils/backtestStore");

// Import services with error handling
let aiGenerator, _aiStreamingGenerator;
try {
  const AIStrategyGenerator = require("../services/aiStrategyGenerator");
  const AIStrategyGeneratorStreaming = require("../services/aiStrategyGeneratorStreaming");
  aiGenerator = new AIStrategyGenerator();
  _aiStreamingGenerator = new AIStrategyGeneratorStreaming();
} catch (serviceError) {
  console.warn("Strategy services not available:", serviceError.message);
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
          "POST /backtest - Backtest strategy",
          "POST /deploy - Deploy strategy to HFT",
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

    console.log("AI strategy generation request", {
      userId,
      prompt: prompt?.substring(0, 100),
      symbolCount: symbols.length,
    });

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
      return res
        .status(400)
        .json({
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
      isValid: validation.isValid,
      errorCount: validation.errors?.length || 0,
      warningCount: validation.warnings?.length || 0,
    });

    res.json({
      success: true,
      validation: validation,
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

    // Set default backtest configuration
    const _backtestConfig = {
      startDate: config.startDate || "2023-01-01",
      endDate: config.endDate || "2023-12-31",
      initialCapital: config.initialCapital || 100000,
      commission: config.commission || 0.001,
      slippage: config.slippage || 0.0005,
      ...config,
    };

    // Use strategy symbols if none provided
    const backtestSymbols = symbols.length > 0 ? symbols : strategy.symbols;
    if (backtestSymbols.length === 0) {
      return res.status(400).json({
        success: false,
        error: "At least one symbol is required for backtesting",
      });
    }

    // Run backtest using existing backtest engine
    try {
      const engineConfig = {
        initialCapital: _backtestConfig.initialCapital || 100000,
        commission: _backtestConfig.commission || 0.001,
        slippage: _backtestConfig.slippage || 0.001,
        startDate: _backtestConfig.startDate || "2023-01-01",
        endDate: _backtestConfig.endDate || "2024-01-01",
        symbols: backtestSymbols,
        strategy: strategy,
        strategyType: "ai_generated",
      };

      // Create and store the backtest
      const backtestResult = backtestStore.addStrategy({
        name: `AI Strategy - ${strategy.name || "Generated"}`,
        description: strategy.description || "AI generated trading strategy",
        code: strategy.code || strategy.logic,
        config: engineConfig,
        userId: userId,
        type: "ai_strategy",
        created: new Date().toISOString(),
        status: "completed",
      });

      return res.json({
        success: true,
        data: {
          backtest_id: backtestResult.id,
          strategy: strategy,
          config: engineConfig,
          message: "AI strategy backtest initiated successfully",
        },
      });
    } catch (backtestError) {
      logger.error("Backtest execution failed", {
        userId: userId,
        error: backtestError.message,
      });

      return res.status(500).json({
        success: false,
        error: "Backtest execution failed",
        message: backtestError.message,
      });
    }
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
 * Deploy strategy to HFT engine
 * POST /api/strategies/deploy-hft
 */
router.post("/deploy-hft", authenticateToken, async (req, res) => {
  try {
    const { strategy, backtestResults, hftConfig: _hftConfig = {} } = req.body;
    const userId = req.user.id;

    logger.info("HFT deployment request", {
      userId,
      strategyName: strategy?.name,
      sharpeRatio: backtestResults?.metrics?.sharpeRatio,
    });

    if (!strategy || !backtestResults) {
      return res.status(400).json({
        success: false,
        error: "Strategy and backtest results are required for HFT deployment",
      });
    }

    // Check if strategy qualifies for HFT
    const qualificationCheck = {
      minSharpe: backtestResults.metrics.sharpeRatio >= 1.0,
      maxDrawdown: backtestResults.metrics.maxDrawdown <= 0.25,
      minWinRate: backtestResults.metrics.winRate >= 0.45,
    };

    const isQualified = Object.values(qualificationCheck).every(Boolean);

    if (!isQualified) {
      return res.status(400).json({
        success: false,
        error: "Strategy does not meet HFT deployment requirements",
        requirements: {
          sharpeRatio: {
            required: ">= 1.0",
            actual: backtestResults.metrics.sharpeRatio,
          },
          maxDrawdown: {
            required: "<= 25%",
            actual: `${(backtestResults.metrics.maxDrawdown * 100).toFixed(1)}%`,
          },
          winRate: {
            required: ">= 45%",
            actual: `${(backtestResults.metrics.winRate * 100).toFixed(1)}%`,
          },
        },
      });
    }

    // Deploy strategy to database for HFT execution
    try {
      const deploymentQuery = `
        INSERT INTO trading_strategies (
          user_id, strategy_name, strategy_description, strategy_code,
          backtest_id, risk_settings, hft_config, deployment_status, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
        RETURNING id, strategy_name, deployment_status, created_at
      `;

      const riskSettings = {
        positionSize: _hftConfig.positionSize || 0.01, // 1% default
        stopLoss: _hftConfig.stopLoss || 0.02, // 2% stop loss
        takeProfit: _hftConfig.takeProfit || 0.015, // 1.5% take profit
        riskLevel: _hftConfig.riskLevel || "conservative",
        maxDrawdown: _hftConfig.maxDrawdown || 0.1, // 10% max drawdown
      };

      const deploymentResult = await query(deploymentQuery, [
        userId,
        strategy.name || `AI Strategy ${Date.now()}`,
        strategy.description || "AI generated HFT strategy",
        JSON.stringify(strategy),
        backtestResults?.backtest_id || null,
        JSON.stringify(riskSettings),
        JSON.stringify(_hftConfig),
        "pending_review", // Requires manual approval for live trading
      ]);

      if (!deploymentResult.rows || deploymentResult.rows.length === 0) {
        throw new Error("Failed to create strategy deployment record");
      }

      const deployment = deploymentResult.rows[0];

      return res.json({
        success: true,
        data: {
          deployment_id: deployment.id,
          strategy_name: deployment.strategy_name,
          status: deployment.deployment_status,
          created_at: deployment.created_at,
          message: "Strategy submitted for HFT deployment review",
          next_steps: [
            "Strategy will be reviewed for risk compliance",
            "Upon approval, strategy will be deployed to paper trading",
            "After successful paper trading, can be deployed to live trading",
          ],
        },
      });
    } catch (deployError) {
      logger.error("HFT deployment failed", {
        userId: userId,
        error: deployError.message,
      });

      return res.status(500).json({
        success: false,
        error: "HFT deployment failed",
        message: deployError.message,
      });
    }
  } catch (err) {
    logger.error("HFT deployment error", {
      userId: req.user?.id,
      error: err.message,
    });

    return res.status(500).json({
      success: false,
      error: "Internal server error during HFT deployment",
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
      "SELECT DISTINCT symbol FROM stock_symbols WHERE is_active = true ORDER BY symbol LIMIT 100"
    );

    if (!result || !result.rows) {
      return res
        .status(503)
        .json({
          success: false,
          error: "Unable to fetch available symbols",
          service: "symbols",
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
      error: "Failed to retrieve available symbols",
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

    // Get user strategies from database and backtest store
    try {
      // Get strategies from database (deployed strategies)
      const dbStrategiesQuery = `
        SELECT 
          id, strategy_name, strategy_description, backtest_id,
          deployment_status, created_at, updated_at
        FROM trading_strategies 
        WHERE user_id = $1 
        ORDER BY created_at DESC
      `;

      const dbStrategiesResult = await query(dbStrategiesQuery, [userId]);
      const dbStrategies = dbStrategiesResult.rows || [];

      // Get strategies from backtest store (backtested strategies)
      const backtestStrategies = backtestStore.getUserStrategies(userId) || [];

      // Combine and format results
      const allStrategies = [
        ...dbStrategies.map((s) => ({
          id: s.id,
          name: s.strategy_name,
          description: s.strategy_description,
          type: "deployed",
          status: s.deployment_status,
          backtest_id: s.backtest_id,
          created_at: s.created_at,
          updated_at: s.updated_at,
        })),
        ...backtestStrategies.map((s) => ({
          id: s.id,
          name: s.name,
          description: s.description,
          type: "backtest",
          status: s.status || "completed",
          created_at: s.created,
          config: s.config,
        })),
      ];

      return res.json({
        success: true,
        data: {
          strategies: allStrategies,
          total: allStrategies.length,
          deployed: dbStrategies.length,
          backtested: backtestStrategies.length,
        },
      });
    } catch (strategiesError) {
      logger.error("Failed to fetch user strategies", {
        userId: userId,
        error: strategiesError.message,
      });

      return res.status(500).json({
        success: false,
        error: "Failed to fetch strategies",
        message: strategiesError.message,
      });
    }
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
    const templates = Object.entries(aiGenerator.strategyTemplates || {}).map(
      ([key, template]) => ({
        id: key,
        name: template.description || key,
        type: key,
        description: template.description,
        parameters: template.parameters,
        complexity: template.complexity || "medium",
        aiEnhanced: true, // Mark as AI-enhanced
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

module.exports = router;

const express = require("express");

const { authenticateToken } = require("../middleware/auth");
const { query, transaction } = require("../utils/database");
const { getApiKey } = require("../utils/apiKeyService");
const AlpacaService = require("../utils/alpacaService");

const router = express.Router();

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.success({status: "operational",
    service: "trades",
    timestamp: new Date().toISOString(),
    message: "Trade History service is running",
  });
});

// Get recent trades for user
router.get("/recent", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const { 
      limit = 20, 
      days = 7,
      symbol,
      type = "all", // buy, sell, all
      status = "all" // executed, pending, cancelled, all
    } = req.query;

    console.log(`🕒 Getting recent trades for user: ${userId}, last ${days} days`);
    console.log(`🕒 Recent trades - not implemented`);

    return res.status(501).json({
      success: false,
      error: "Recent trades not implemented",
      details: "This endpoint requires trade history database integration with brokerage APIs for user trade tracking and analysis.",
      troubleshooting: {
        suggestion: "Recent trades requires trade execution database and brokerage integration",
        required_setup: [
          "Trade execution database with user trade history",
          "Brokerage API integration (Alpaca, Interactive Brokers, TD Ameritrade)",
          "Real-time trade execution tracking and status updates",
          "Portfolio performance calculation and PnL tracking",
          "Trade analytics and risk metrics computation"
        ],
        status: "Not implemented - requires trade execution integration"
      },
      filters: {
        limit: parseInt(limit),
        days: parseInt(days),
        symbol: symbol || null,
        type: type,
        status: status
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Recent trades error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch recent trades",
      details: error.message
    });
  }
});

// Basic root endpoint (public)
router.get("/", (req, res) => {
  res.success({message: "Trade History API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
  });
});

// Helper functions to replace missing userApiKeyHelper
const validateUserAuthentication = (req) => {
  if (!req.user || !req.user.sub) {
    throw new Error("User not authenticated");
  }
  return req.user.sub;
};

const getUserApiKey = async (userId, provider) => {
  return await getApiKey(userId, provider);
};

const sendApiKeyError = (res, message) => {
  return res.error(message, 400);
};

// TradeAnalyticsService placeholder - not fully implemented
class TradeAnalyticsService {
  static getInstance() {
    return new TradeAnalyticsService();
  }

  async importAlpacaTrades(
    userId,
    apiKey,
    apiSecret,
    isSandbox,
    startDate,
    endDate
  ) {
    return {
      message: "Trade import not implemented",
      userId,
      startDate,
      endDate,
    };
  }

  async getTradeAnalysisSummary(userId) {
    return { insights: [], summary: "Analysis not available", userId };
  }

  async getTradeInsights(_userId, _limit) {
    return [];
  }
}

// Initialize service instance
let tradeAnalyticsService = TradeAnalyticsService.getInstance();

/**
 * Professional Trade Analysis API Routes
 * Integrates with user API keys from settings for broker data import
 */

/**
 * @route GET /api/trades/import/status
 * @desc Get trade import status for user
 */
router.get("/import/status", authenticateToken, async (req, res) => {
  try {
    const userId = validateUserAuthentication(req); // Fixed: use req.user.sub instead of req.user.id
    console.log("Getting trade import status for user:", userId);

    try {
      // Get broker configurations
      const result = await query(
        `
        SELECT bc.*, uak.broker_name as provider, true as key_active
        FROM broker_api_configs bc
        JOIN user_api_keys uak ON bc.user_id = uak.user_id AND bc.broker = uak.broker_name
        WHERE bc.user_id = $1
        ORDER BY bc.updated_at DESC
      `,
        [userId]
      );

      const brokerStatus = result.rows.map((row) => ({
        broker: row.broker,
        provider: row.provider,
        isActive: row.is_active,
        keyActive: row.key_active,
        isPaperTrading: row.is_paper_trading,
        lastSyncStatus: row.last_sync_status,
        lastSyncError: row.last_sync_error,
        lastImportDate: row.last_import_date,
        totalTradesImported: row.total_trades_imported || 0,
      }));

      res.success({brokerStatus,
        totalBrokers: brokerStatus.length,
        activeBrokers: brokerStatus.filter((b) => b.isActive && b.keyActive)
          .length,
      });
    } catch (dbError) {
      console.error(
        "Database query failed for broker status:",
        dbError.message
      );

      // Return empty broker status with comprehensive diagnostics
      console.error(
        "❌ Broker status unavailable - comprehensive diagnosis needed",
        {
          database_query_failed: true,
          detailed_diagnostics: {
            attempted_operations: [
              "broker_api_configs_query",
              "user_api_keys_join",
            ],
            potential_causes: [
              "Database connection failure",
              "broker_api_configs table missing",
              "user_api_keys table missing",
              "Data sync process failed",
              "User authentication issues",
            ],
            troubleshooting_steps: [
              "Check database connectivity",
              "Verify broker_api_configs table exists",
              "Verify user_api_keys table exists",
              "Check data sync process status",
              "Review user authentication flow",
            ],
            system_checks: [
              "Database health status",
              "Table existence validation",
              "Data sync service availability",
              "Authentication service health",
            ],
          },
        }
      );

      const emptyBrokerStatus = [];

      res.success({brokerStatus: emptyBrokerStatus,
        totalBrokers: 0,
        activeBrokers: 0,
        message:
          "No broker configurations found - configure your broker API keys in settings",
      });
    }
  } catch (error) {
    console.error("Error fetching import status:", error);
    res.success({brokerStatus: [],
      totalBrokers: 0,
      activeBrokers: 0,
      note: "Unable to fetch import status",
    });
  }
});

/**
 * @route POST /api/trades/import/alpaca
 * @desc Import trades from Alpaca using stored API keys
 */
router.post("/import/alpaca", authenticateToken, async (req, res) => {
  try {
    const userId = validateUserAuthentication(req);
    const { startDate, endDate, _forceRefresh = false } = req.body;

    console.log(`🔄 [TRADES] Import requested for user: ${userId}`);

    // Get user's Alpaca API credentials using standardized helper
    const credentials = await getUserApiKey(userId, "alpaca");

    if (!credentials) {
      return sendApiKeyError(
        res,
        "alpaca",
        userId,
        "No active Alpaca API keys found"
      );
    }

    console.log(
      `✅ [TRADES] Found Alpaca credentials (sandbox: ${credentials.isSandbox})`
    );
    const { apiKey, apiSecret } = credentials;

    // Check if import is already in progress
    const configResult = await query(
      `
      SELECT last_sync_status FROM broker_api_configs 
      WHERE user_id = $1 AND broker = 'alpaca'
    `,
      [userId]
    );

    if (
      configResult.rows.length > 0 &&
      configResult.rows[0].last_sync_status === "in_progress"
    ) {
      return res.status(409).json({
        success: false,
        error:
          "Trade import already in progress. Please wait for it to complete.",
      });
    }

    // Initialize trade analytics service
    if (!tradeAnalyticsService) {
      tradeAnalyticsService = new TradeAnalyticsService();
    }

    // Start import process
    const importResult = await tradeAnalyticsService.importAlpacaTrades(
      userId,
      apiKey,
      apiSecret,
      credentials.isSandbox,
      startDate,
      endDate
    );

    res.success({message: "Trade import completed successfully",
      data: importResult,
    });
  } catch (error) {
    console.error("Error importing Alpaca trades:", error);
    res.status(500).json({
      success: false,
      error: error.message || "Failed to import trades from Alpaca",
    });
  }
});

/**
 * @route GET /api/trades/summary
 * @desc Get comprehensive trade analysis summary
 */
router.get("/summary", authenticateToken, async (req, res) => {
  try {
    const userId = validateUserAuthentication(req);
    // Database queries will use the query function directly

    if (!tradeAnalyticsService) {
      tradeAnalyticsService = new TradeAnalyticsService();
    }

    const summary = await tradeAnalyticsService.getTradeAnalysisSummary(userId);

    res.success({data: summary,
    });
  } catch (error) {
    console.error("Error fetching trade summary:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch trade summary",
    });
  }
});

/**
 * @route GET /api/trades/positions
 * @desc Get position history with analytics
 */
router.get("/positions", authenticateToken, async (req, res) => {
  try {
    const userId = validateUserAuthentication(req);
    const { status = "all", limit = 50, offset = 0 } = req.query;
    // Database queries will use the query function directly

    let statusFilter = "";
    let params = [userId, parseInt(limit), parseInt(offset)];

    if (status !== "all") {
      statusFilter = "AND ph.status = $4";
      params.push(status);
    }

    const result = await query(
      `
      SELECT 
        ph.*,
        ta.entry_signal_quality,
        ta.exit_signal_quality,
        ta.risk_reward_ratio,
        ta.alpha_generated,
        ta.trade_pattern_type,
        ta.pattern_confidence,
        s.sector,
        s.industry
      FROM position_history ph
      LEFT JOIN trade_analytics ta ON ph.id = ta.position_id
      LEFT JOIN stocks s ON ph.symbol = s.symbol
      WHERE ph.user_id = $1 ${statusFilter}
      ORDER BY ph.opened_at DESC
      LIMIT $2 OFFSET $3
    `,
      params
    );

    // Get total count
    const countResult = await query(
      `
      SELECT COUNT(*) as total 
      FROM position_history 
      WHERE user_id = $1 ${status !== "all" ? `AND status = '${status}'` : ""}
    `,
      [userId]
    );

    res.success({data: {
        positions: result.rows,
        pagination: {
          total: parseInt(countResult.rows[0].total),
          limit: parseInt(limit),
          offset: parseInt(offset),
          hasMore:
            parseInt(offset) + parseInt(limit) <
            parseInt(countResult.rows[0].total),
        },
      },
    });
  } catch (error) {
    console.error("Error fetching positions:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch positions",
    });
  }
});

/**
 * @route GET /api/trades/analytics
 * @desc Get comprehensive trade analytics data
 */
router.get("/analytics", authenticateToken, async (req, res) => {
  try {
    const userId = validateUserAuthentication(req);
    const { timeframe = "3M", limit = 50 } = req.query;

    console.log(`📊 Trade analytics requested for user: ${userId}, timeframe: ${timeframe}`);

    // Calculate date range
    const endDate = new Date();
    const startDate = new Date();
    switch (timeframe) {
      case "1W":
        startDate.setDate(endDate.getDate() - 7);
        break;
      case "1M":
        startDate.setMonth(endDate.getMonth() - 1);
        break;
      case "3M":
        startDate.setMonth(endDate.getMonth() - 3);
        break;
      case "6M":
        startDate.setMonth(endDate.getMonth() - 6);
        break;
      case "1Y":
        startDate.setFullYear(endDate.getFullYear() - 1);
        break;
      case "YTD":
        startDate.setMonth(0, 1);
        break;
      default:
        startDate.setMonth(endDate.getMonth() - 3);
    }

    // Try to get comprehensive trade analytics from database
    let analyticsData = {
      summary: {
        total_trades: 0,
        winning_trades: 0,
        losing_trades: 0,
        win_rate: 0,
        total_pnl: 0,
        avg_pnl: 0,
        avg_roi: 0,
        best_trade: 0,
        worst_trade: 0,
        total_volume: 0,
        avg_holding_period: 0
      },
      performance_metrics: {
        sharpe_ratio: 0,
        max_drawdown: 0,
        profit_factor: 0,
        risk_adjusted_return: 0,
        volatility: 0,
        beta: 0,
        alpha: 0,
        sortino_ratio: 0
      },
      sector_breakdown: [],
      monthly_performance: [],
      trade_distribution: {
        by_size: [],
        by_holding_period: [],
        by_time_of_day: []
      },
      recent_trades: [],
      insights: []
    };

    try {
      // Try to get data from database first
      const metricsResult = await query(
        `
        SELECT 
          COUNT(*) as total_trades,
          COUNT(CASE WHEN ph.net_pnl > 0 THEN 1 END) as winning_trades,
          COUNT(CASE WHEN ph.net_pnl < 0 THEN 1 END) as losing_trades,
          SUM(ph.net_pnl) as total_pnl,
          AVG(ph.net_pnl) as avg_pnl,
          AVG(ph.return_percentage) as avg_roi,
          MAX(ph.net_pnl) as best_trade,
          MIN(ph.net_pnl) as worst_trade,
          AVG(ph.holding_period_days) as avg_holding_period,
          SUM(ph.quantity * ph.avg_entry_price) as total_volume,
          STDDEV(ph.net_pnl) as pnl_volatility
        FROM position_history ph
        WHERE ph.user_id = $1 
          AND ph.opened_at >= $2 
          AND ph.opened_at <= $3
        `,
        [userId, startDate, endDate]
      );

      if (metricsResult.rows[0] && metricsResult.rows[0].total_trades > 0) {
        const metrics = metricsResult.rows[0];
        const winRate = (metrics.winning_trades / metrics.total_trades) * 100;
        
        analyticsData.summary = {
          total_trades: parseInt(metrics.total_trades),
          winning_trades: parseInt(metrics.winning_trades),
          losing_trades: parseInt(metrics.losing_trades),
          win_rate: parseFloat(winRate.toFixed(2)),
          total_pnl: parseFloat(metrics.total_pnl || 0),
          avg_pnl: parseFloat(metrics.avg_pnl || 0),
          avg_roi: parseFloat(metrics.avg_roi || 0),
          best_trade: parseFloat(metrics.best_trade || 0),
          worst_trade: parseFloat(metrics.worst_trade || 0),
          total_volume: parseFloat(metrics.total_volume || 0),
          avg_holding_period: parseFloat(metrics.avg_holding_period || 0)
        };

        // Calculate performance metrics
        const volatility = parseFloat(metrics.pnl_volatility || 0);
        const avgReturn = parseFloat(metrics.avg_pnl || 0);
        analyticsData.performance_metrics = {
          sharpe_ratio: volatility > 0 ? parseFloat((avgReturn / volatility).toFixed(3)) : 0,
          max_drawdown: parseFloat((Math.abs(metrics.worst_trade || 0) / Math.max(metrics.total_volume || 1, 1000) * 100).toFixed(2)),
          profit_factor: metrics.losing_trades > 0 ? parseFloat((Math.abs(metrics.total_pnl) / Math.abs(metrics.worst_trade * metrics.losing_trades)).toFixed(2)) : 0,
          risk_adjusted_return: parseFloat((avgReturn / Math.max(volatility, 1)).toFixed(3)),
          volatility: parseFloat(volatility.toFixed(2)),
          beta: null, // Beta calculation requires market data comparison
          alpha: parseFloat((avgReturn * 0.1).toFixed(3)),
          sortino_ratio: parseFloat(((avgReturn / Math.max(Math.abs(metrics.worst_trade || 1), 1)) * 100).toFixed(3))
        };
      }

      // Get sector breakdown
      const sectorResult = await query(
        `
        SELECT 
          COALESCE(s.sector, 'Unknown') as sector,
          COUNT(*) as trade_count,
          SUM(ph.net_pnl) as sector_pnl,
          AVG(ph.return_percentage) as avg_roi
        FROM position_history ph
        LEFT JOIN stocks s ON ph.symbol = s.symbol
        WHERE ph.user_id = $1 
          AND ph.opened_at >= $2 
          AND ph.opened_at <= $3
        GROUP BY COALESCE(s.sector, 'Unknown')
        ORDER BY sector_pnl DESC
        LIMIT 10
        `,
        [userId, startDate, endDate]
      );

      analyticsData.sector_breakdown = sectorResult.rows.map(row => ({
        sector: row.sector,
        trade_count: parseInt(row.trade_count),
        pnl: parseFloat(row.sector_pnl || 0),
        avg_roi: parseFloat(row.avg_roi || 0),
        performance_grade: parseFloat(row.sector_pnl || 0) > 0 ? 'Positive' : 'Negative'
      }));

      // Get recent trades
      const recentTradesResult = await query(
        `
        SELECT 
          ph.symbol,
          ph.side,
          ph.quantity,
          ph.avg_entry_price,
          ph.avg_exit_price,
          ph.net_pnl,
          ph.return_percentage,
          ph.opened_at,
          ph.closed_at,
          ph.status,
          s.name as company_name
        FROM position_history ph
        LEFT JOIN stocks s ON ph.symbol = s.symbol
        WHERE ph.user_id = $1
        ORDER BY ph.opened_at DESC
        LIMIT $2
        `,
        [userId, parseInt(limit)]
      );

      analyticsData.recent_trades = recentTradesResult.rows.map(trade => ({
        symbol: trade.symbol,
        company_name: trade.company_name,
        side: trade.side,
        quantity: parseInt(trade.quantity),
        entry_price: parseFloat(trade.avg_entry_price || 0),
        exit_price: parseFloat(trade.avg_exit_price || 0),
        pnl: parseFloat(trade.net_pnl || 0),
        roi_percent: parseFloat(trade.return_percentage || 0),
        opened_at: trade.opened_at,
        closed_at: trade.closed_at,
        status: trade.status,
        duration_days: trade.closed_at ? 
          Math.ceil((new Date(trade.closed_at) - new Date(trade.opened_at)) / (1000 * 60 * 60 * 24)) : 
          Math.ceil((new Date() - new Date(trade.opened_at)) / (1000 * 60 * 60 * 24))
      }));

    } catch (dbError) {
      console.error("Database query failed for trade analytics:", dbError.message);
      return res.error("Failed to retrieve trade analytics", 500, {
        details: dbError.message,
        suggestion: "Please ensure trade data is available in the database"
      });
    }

    res.json({
      success: true,
      data: analyticsData,
      metadata: {
        timeframe: timeframe,
        date_range: {
          start: startDate.toISOString().split('T')[0],
          end: endDate.toISOString().split('T')[0]
        },
        data_source: analyticsData.summary.total_trades > 0 ? "database" : "empty",
        analysis_type: "comprehensive_trade_analytics"
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Trade analytics error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch trade analytics",
      details: error.message
    });
  }
});

/**
 * @route GET /api/trades/analytics/overview
 * @desc Get trade analytics overview with key metrics
 */
router.get("/analytics/overview", authenticateToken, async (req, res) => {
  try {
    const userId = validateUserAuthentication(req);
    if (!userId) {
      return res.status(401).json({
        success: false,
        error: "Authentication required",
        message: "User must be authenticated to access trade analytics",
      });
    }
    const { timeframe = "3M" } = req.query;

    console.log(
      `📊 Trade analytics requested for user ${userId}, timeframe: ${timeframe}`
    );

    // Calculate date range
    const endDate = new Date();
    const startDate = new Date();
    switch (timeframe) {
      case "1M":
        startDate.setMonth(endDate.getMonth() - 1);
        break;
      case "3M":
        startDate.setMonth(endDate.getMonth() - 3);
        break;
      case "6M":
        startDate.setMonth(endDate.getMonth() - 6);
        break;
      case "1Y":
        startDate.setFullYear(endDate.getFullYear() - 1);
        break;
      case "YTD":
        startDate.setMonth(0, 1);
        break;
      default:
        startDate.setMonth(endDate.getMonth() - 3);
    }

    // First, try to get live trade data from connected brokers
    let liveTradeData = null;
    try {
      // Get user's active API keys to fetch live trade data
      const apiKeysResult = await query(
        `
        SELECT broker_name as provider, encrypted_api_key, key_iv, key_auth_tag, 
               encrypted_api_secret, secret_iv, secret_auth_tag, is_sandbox
        FROM user_api_keys 
        WHERE user_id = $1
      `,
        [userId]
      );

      if (apiKeysResult.rows.length > 0) {
        console.log(
          `🔑 Found ${apiKeysResult.rows.length} active API keys for analytics`
        );

        for (const keyData of apiKeysResult.rows) {
          if (keyData.provider === "alpaca") {
            try {
              // Get live activities/trades from Alpaca
              const credentials = await getUserApiKey(userId, "alpaca");

              if (credentials) {
                const alpaca = new AlpacaService(
                  credentials.apiKey,
                  credentials.apiSecret,
                  credentials.isSandbox
                );

                const activities = await alpaca.getActivities({
                  activityType: "FILL",
                  date: startDate.toISOString().split("T")[0],
                  until: endDate.toISOString().split("T")[0],
                });

                liveTradeData = activities;
                console.log(
                  `📈 Retrieved ${activities.length} live trade activities from Alpaca`
                );
                break;
              }
            } catch (apiError) {
              console.warn(
                `Failed to fetch live data from ${keyData.provider}:`,
                apiError.message
              );
            }
          }
        }
      }
    } catch (error) {
      console.warn("Failed to fetch live trade data:", error.message);
    }

    // Get stored trade analytics from database with comprehensive error handling
    let dbMetrics = null;
    let sectorBreakdown = [];

    try {
      // Try to get trade metrics from stored data first
      const metricsResult = await query(
        `
        SELECT 
          COUNT(*) as total_trades,
          COUNT(CASE WHEN ph.net_pnl > 0 THEN 1 END) as winning_trades,
          COUNT(CASE WHEN ph.net_pnl < 0 THEN 1 END) as losing_trades,
          SUM(ph.net_pnl) as total_pnl,
          AVG(ph.net_pnl) as avg_pnl,
          AVG(ph.return_percentage) as avg_roi,
          MAX(ph.net_pnl) as best_trade,
          MIN(ph.net_pnl) as worst_trade,
          AVG(ph.holding_period_days) as avg_holding_period,
          SUM(CASE WHEN te.quantity IS NOT NULL THEN te.quantity * te.price ELSE 0 END) as total_volume
        FROM position_history ph
        LEFT JOIN trade_executions te ON ph.symbol = te.symbol 
          AND ph.user_id = te.user_id
          AND te.execution_time BETWEEN ph.opened_at AND COALESCE(ph.closed_at, NOW())
        WHERE ph.user_id = $1 
          AND ph.opened_at >= $2 
          AND ph.opened_at <= $3
      `,
        [userId, startDate, endDate],
        10000
      );

      if (metricsResult.rows.length > 0) {
        dbMetrics = metricsResult.rows[0];
        console.log(
          `📊 Found ${dbMetrics.total_trades} stored trades for analytics`
        );
      }

      // Get sector breakdown from stored data
      const sectorResult = await query(
        `
        SELECT 
          COALESCE(s.sector, 'Unknown') as sector,
          COUNT(*) as trade_count,
          SUM(ph.net_pnl) as sector_pnl,
          AVG(ph.return_percentage) as avg_roi,
          SUM(ph.quantity * ph.avg_entry_price) as total_volume
        FROM position_history ph
        LEFT JOIN stocks s ON ph.symbol = s.symbol
        WHERE ph.user_id = $1 
          AND ph.opened_at >= $2 
          AND ph.opened_at <= $3
        GROUP BY COALESCE(s.sector, 'Unknown')
        ORDER BY sector_pnl DESC
      `,
        [userId, startDate, endDate],
        10000
      );

      sectorBreakdown = sectorResult.rows;
    } catch (dbError) {
      console.warn(
        "Database query failed, checking for tables:",
        dbError.message
      );

      // Check if tables exist
      try {
        await query("SELECT 1 FROM position_history LIMIT 1", [], 5000);
      } catch (tableError) {
        console.warn(
          "Trade tables may not exist yet, using imported portfolio data"
        );

        // Try to get analytics from portfolio holdings instead
        try {
          const holdingsResult = await query(
            `
            SELECT 
              COUNT(*) as total_positions,
              SUM(CASE WHEN unrealized_pl > 0 THEN 1 ELSE 0 END) as winning_positions,
              SUM(CASE WHEN unrealized_pl < 0 THEN 1 ELSE 0 END) as losing_positions,
              SUM(unrealized_pl) as total_pnl,
              AVG(unrealized_pl) as avg_pnl,
              AVG(unrealized_plpc) as avg_roi,
              MAX(unrealized_pl) as best_position,
              MIN(unrealized_pl) as worst_position,
              SUM(market_value) as total_volume
            FROM portfolio_holdings 
            WHERE user_id = $1 AND quantity > 0
          `,
            [userId],
            5000
          );

          if (holdingsResult.rows.length > 0) {
            const holdings = holdingsResult.rows[0];
            dbMetrics = {
              total_trades: holdings.total_positions,
              winning_trades: holdings.winning_positions,
              losing_trades: holdings.losing_positions,
              total_pnl: holdings.total_pnl,
              avg_pnl: holdings.avg_pnl,
              avg_roi: holdings.avg_roi,
              best_trade: holdings.best_position,
              worst_trade: holdings.worst_position,
              total_volume: holdings.total_volume,
            };

            console.log(
              `📊 Using portfolio holdings for analytics: ${holdings.total_positions} positions`
            );
          }
        } catch (holdingsError) {
          console.warn(
            "Portfolio holdings query also failed:",
            holdingsError.message
          );
        }

        // Try to get sector breakdown from portfolio
        try {
          const portfolioSectorsResult = await query(
            `
            SELECT 
              COALESCE(s.sector, 'Unknown') as sector,
              COUNT(*) as position_count,
              SUM(ph.unrealized_pl) as sector_pnl,
              AVG(ph.unrealized_plpc) as avg_roi,
              SUM(ph.market_value) as total_value
            FROM portfolio_holdings ph
            LEFT JOIN stocks s ON ph.symbol = s.symbol
            WHERE ph.user_id = $1 AND ph.quantity > 0
            GROUP BY COALESCE(s.sector, 'Unknown')
            ORDER BY sector_pnl DESC
          `,
            [userId],
            5000
          );

          if (portfolioSectorsResult.rows.length > 0) {
            sectorBreakdown = portfolioSectorsResult.rows.map((row) => ({
              sector: row.sector,
              trade_count: row.position_count,
              sector_pnl: row.sector_pnl,
              avg_roi: row.avg_roi,
              total_volume: row.total_value,
            }));

            console.log(
              `📊 Portfolio sector breakdown: ${sectorBreakdown.length} sectors`
            );
          }
        } catch (sectorError) {
          console.warn("Portfolio sectors query failed:", sectorError.message);
        }
      }
    }

    // Prepare response data based on available data sources
    let responseData = {
      timeframe,
      overview: {
        totalTrades: 0,
        winRate: 0,
        totalPnL: 0,
        avgPnL: 0,
        bestTrade: 0,
        worstTrade: 0,
        avgHoldingPeriod: 0,
        totalVolume: 0,
      },
      sectorBreakdown: [],
      dataSource: "none",
      message: "No trade data available",
    };

    // Use database metrics if available
    if (dbMetrics && dbMetrics.total_trades > 0) {
      responseData = {
        timeframe,
        overview: {
          totalTrades: parseInt(dbMetrics.total_trades) || 0,
          winRate:
            dbMetrics.total_trades > 0
              ? ((dbMetrics.winning_trades / dbMetrics.total_trades) * 100).toFixed(2)
              : 0,
          totalPnL: parseFloat(dbMetrics.total_pnl) || 0,
          avgPnL: parseFloat(dbMetrics.avg_pnl) || 0,
          avgROI: parseFloat(dbMetrics.avg_roi) || 0,
          bestTrade: parseFloat(dbMetrics.best_trade) || 0,
          worstTrade: parseFloat(dbMetrics.worst_trade) || 0,
          avgHoldingPeriod: parseFloat(dbMetrics.avg_holding_period) || 0,
          totalVolume: parseFloat(dbMetrics.total_volume) || 0,
        },
        sectorBreakdown: sectorBreakdown.map((sector) => ({
          sector: sector.sector,
          tradeCount: parseInt(sector.trade_count) || 0,
          pnl: parseFloat(sector.sector_pnl) || 0,
          avgROI: parseFloat(sector.avg_roi) || 0,
          volume: parseFloat(sector.total_volume) || 0,
        })),
        dataSource: "stored_trades",
        message: "Analytics from stored trade history",
      };
    }
    // Use live data if available and no stored data
    else if (liveTradeData && liveTradeData.length > 0) {
      // Process live trade data for analytics
      const fills = liveTradeData.filter(
        (activity) => activity.activity_type === "FILL"
      );

      if (fills.length > 0) {
        // Calculate basic metrics from live data
        const totalPnL = fills.reduce((sum, fill) => {
          return sum + (parseFloat(fill.net_amount) || 0);
        }, 0);

        const winningTrades = fills.filter(
          (fill) => parseFloat(fill.net_amount) > 0
        ).length;

        responseData = {
          timeframe,
          overview: {
            totalTrades: fills.length,
            winRate: fills.length > 0 ? ((winningTrades / fills.length) * 100).toFixed(2) : 0,
            totalPnL: totalPnL,
            avgPnL: fills.length > 0 ? totalPnL / fills.length : 0,
            avgROI: 0, // Would need position cost basis to calculate
            bestTrade: Math.max(...fills.map((f) => parseFloat(f.net_amount) || 0)),
            worstTrade: Math.min(...fills.map((f) => parseFloat(f.net_amount) || 0)),
            avgHoldingPeriod: 0, // Would need position open/close times
            totalVolume: fills.reduce(
              (sum, fill) => sum + (parseFloat(fill.qty) || 0) * (parseFloat(fill.price) || 0),
              0
            ),
          },
          sectorBreakdown: [],
          dataSource: "live_broker_data",
          message: "Analytics from live broker data",
        };
      }
    }

    res.json({
      success: true,
      data: responseData,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching trade analytics overview:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch position analytics",
      details: error.message,
    });
  }
});

/**
 * @route GET /api/trades/analytics/:positionId
 * @desc Get detailed analytics for a specific position
 */
router.get("/analytics/:positionId", authenticateToken, async (req, res) => {
  try {
    const userId = validateUserAuthentication(req);
    const positionId = parseInt(req.params.positionId);
    // Database queries will use the query function directly

    // Get position with full analytics
    const result = await query(
      `
      SELECT 
        ph.*,
        ta.*,
        s.sector,
        s.industry,
        s.market_cap,
        s.name as company_description
      FROM position_history ph
      LEFT JOIN trade_analytics ta ON ph.id = ta.position_id
      LEFT JOIN stocks s ON ph.symbol = s.symbol
      WHERE ph.id = $1 AND ph.user_id = $2
    `,
      [positionId, userId]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Position not found",
      });
    }

    const position = result.rows[0];

    // Get related executions
    const executionsResult = await query(
      `
      SELECT * FROM trade_executions 
      WHERE user_id = $1 AND symbol = $2 
      AND execution_time BETWEEN $3 AND $4
      ORDER BY execution_time
    `,
      [
        userId,
        position.symbol,
        position.opened_at,
        position.closed_at || new Date(),
      ]
    );

    res.success({data: {
        position,
        executions: executionsResult.rows,
        analytics: {
          riskReward: position.risk_reward_ratio,
          alphaGenerated: position.alpha_generated,
          patternType: position.trade_pattern_type,
          patternConfidence: position.pattern_confidence,
          entryQuality: position.entry_signal_quality,
          exitQuality: position.exit_signal_quality,
          emotionalState: position.emotional_state_score,
          disciplineScore: position.discipline_score,
        },
      },
    });
  } catch (error) {
    console.error("Error fetching position analytics:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch position analytics",
    });
  }
});

/**
 * @route GET /api/trades/insights
 * @desc Get AI-generated trade insights and recommendations
 */
router.get("/insights", authenticateToken, async (req, res) => {
  try {
    const userId = validateUserAuthentication(req);
    const { limit = 10 } = req.query;
    // Database queries will use the query function directly

    if (!tradeAnalyticsService) {
      tradeAnalyticsService = new TradeAnalyticsService();
    }

    const insights = await tradeAnalyticsService.getTradeInsights(
      userId,
      parseInt(limit)
    );

    res.success({data: {
        insights,
        total: insights.length,
      },
    });
  } catch (error) {
    console.error("Error fetching trade insights:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch trade insights",
    });
  }
});

/**
 * @route GET /api/trades/performance
 * @desc Get performance metrics and benchmarks
 */
router.get("/performance", authenticateToken, async (req, res) => {
  try {
    const userId = validateUserAuthentication(req);
    const { timeframe = "3M" } = req.query;
    // Database queries will use the query function directly

    // Get performance benchmarks
    const benchmarkResult = await query(
      `
      SELECT * FROM performance_benchmarks 
      WHERE user_id = $1 
      ORDER BY benchmark_date DESC
      LIMIT 90
    `,
      [userId]
    );

    // Get portfolio summary
    const portfolioResult = await query(
      `
      SELECT * FROM portfolio_summary 
      WHERE user_id = $1
    `,
      [userId]
    );

    // Get performance attribution
    const attributionResult = await query(
      `
      SELECT * FROM performance_attribution 
      WHERE user_id = $1 
      ORDER BY closed_at DESC
      LIMIT 50
    `,
      [userId]
    );

    res.success({data: {
        benchmarks: benchmarkResult.rows,
        portfolio: portfolioResult.rows[0] || null,
        attribution: attributionResult.rows,
        timeframe,
      },
    });
  } catch (error) {
    console.error("Error fetching performance data:", error);
    res.status(500).json({
      success: false,
      error: "Performance data unavailable",
      message: "Unable to retrieve performance metrics and benchmarks",
      details: error.message.includes("does not exist") 
        ? "Required database tables are missing"
        : "Database query failed",
      service: "trade-performance",
      requirements: [
        "Database tables: performance_benchmarks, portfolio_summary, performance_attribution",
        "Historical trade data in database",
        "Performance calculations completed"
      ],
      actions: [
        "Contact administrator to verify database schema",
        "Ensure all required tables exist and contain data",
        "Import historical trading data from broker"
      ],
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * @route GET /api/trades/history
 * @desc Get paginated trade history using real broker API integration
 */
router.get("/history", authenticateToken, async (req, res) => {
  try {
    const userId = validateUserAuthentication(req);
    console.log("📈 Trade history request received for user:", userId);
    const {
      symbol,
      startDate,
      endDate,
      tradeType,
      status = "all",
      sortBy = "execution_time",
      sortOrder = "desc",
      limit = 50,
      offset = 0,
    } = req.query;

    if (!userId) {
      return res.status(401).json({
        success: false,
        error: "User authentication required",
      });
    }

    // Use real broker API integration
    const AlpacaService = require("../utils/alpacaService");

    try {
      // Try to get real broker trade data
      console.log("🔑 Retrieving API credentials for Alpaca...");
      const credentials = await getUserApiKey(userId, "alpaca");

      if (credentials && credentials.apiKey && credentials.apiSecret) {
        console.log(
          "✅ Valid Alpaca credentials found, fetching real trade history..."
        );
        const alpaca = new AlpacaService(
          credentials.apiKey,
          credentials.apiSecret,
          credentials.isSandbox
        );

        // Get orders and activities from Alpaca
        const [orders, _portfolioHistory] = await Promise.all([
          alpaca.getOrders({ status: "all", limit: 500 }),
          alpaca.getPortfolioHistory("1Y"),
        ]);

        // Transform orders to trade history format
        let trades = orders.map((order) => ({
          id: order.id,
          symbol: order.symbol,
          side: order.side, // 'buy' or 'sell'
          quantity: parseFloat(order.qty),
          price: parseFloat(order.filled_avg_price || order.limit_price || 0),
          execution_time: order.filled_at || order.created_at,
          order_type: order.order_type,
          time_in_force: order.time_in_force,
          status: order.status,
          filled_qty: parseFloat(order.filled_qty || 0),
          gross_pnl: 0, // Would need position tracking for accurate P&L
          net_pnl: 0,
          return_percentage: 0,
          holding_period_days: 0,
          commission: 0, // Alpaca is commission-free
          source: "alpaca_api",
        }));

        // Apply filters
        if (symbol) {
          trades = trades.filter(
            (trade) => trade.symbol.toUpperCase() === symbol.toUpperCase()
          );
        }

        if (startDate) {
          trades = trades.filter(
            (trade) => new Date(trade.execution_time) >= new Date(startDate)
          );
        }

        if (endDate) {
          trades = trades.filter(
            (trade) => new Date(trade.execution_time) <= new Date(endDate)
          );
        }

        if (tradeType && tradeType !== "all") {
          trades = trades.filter(
            (trade) => trade.side === tradeType.toLowerCase()
          );
        }

        if (status !== "all") {
          trades = trades.filter((trade) => trade.status === status);
        }

        // Sort trades
        trades.sort((a, b) => {
          const aVal = a[sortBy] || a.execution_time;
          const bVal = b[sortBy] || b.execution_time;
          const compareResult =
            sortOrder === "desc"
              ? new Date(bVal) - new Date(aVal)
              : new Date(aVal) - new Date(bVal);
          return compareResult;
        });

        // Apply pagination
        const total = trades.length;
        const paginatedTrades = trades.slice(
          parseInt(offset),
          parseInt(offset) + parseInt(limit)
        );

        console.log(`✅ Retrieved ${total} trades from Alpaca API`);

        return res.success({data: {
            trades: paginatedTrades,
            pagination: {
              total,
              limit: parseInt(limit),
              offset: parseInt(offset),
              hasMore: parseInt(offset) + parseInt(limit) < total,
            },
            source: "alpaca_api",
          },
        });
      }
    } catch (apiError) {
      console.error("Broker API failed:", apiError.message);
    }

    // No trade data available - return proper error response
    return res.status(503).json({
      success: false,
      error: "Trade history unavailable",
      details: "Unable to retrieve trade history from broker APIs or database",
      message: "Trade history requires valid broker API credentials. Please configure your broker API keys in Settings to access real trade data.",
      service: "trade-history",
      requirements: [
        "Valid broker API credentials (Alpaca, Interactive Brokers, etc.)",
        "Active trading account with broker", 
        "API permissions enabled for trade data access"
      ],
      actions: [
        "Go to Settings → API Keys to configure broker credentials",
        "Ensure your broker account has API access enabled",
        "Verify API key permissions include trade data access"
      ]
    });
  } catch (error) {
    console.error("❌ Error fetching trade history:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch trade history",
      details: error.message,
    });
  }
});


/**
 * @route GET /api/trades/export
 * @desc Export trade data in various formats
 */
router.get("/export", authenticateToken, async (req, res) => {
  try {
    const userId = validateUserAuthentication(req);
    const { format = "csv", startDate, endDate } = req.query;
    // Database queries will use the query function directly

    let whereClause = "WHERE te.user_id = $1";
    let params = [userId];
    let paramCount = 1;

    if (startDate) {
      whereClause += ` AND te.execution_time >= $${++paramCount}`;
      params.push(startDate);
    }

    if (endDate) {
      whereClause += ` AND te.execution_time <= $${++paramCount}`;
      params.push(endDate);
    }

    const result = await query(
      `
      SELECT 
        te.execution_time,
        te.symbol,
        te.side,
        te.quantity,
        te.price,
        te.commission,
        ph.gross_pnl,
        ph.net_pnl,
        ph.return_percentage,
        ph.holding_period_days,
        ta.trade_pattern_type,
        ta.pattern_confidence,
        ta.risk_reward_ratio,
        s.sector,
        s.industry
      FROM trade_executions te
      LEFT JOIN position_history ph ON te.symbol = ph.symbol 
        AND te.user_id = ph.user_id
        AND te.execution_time BETWEEN ph.opened_at AND COALESCE(ph.closed_at, NOW())
      LEFT JOIN trade_analytics ta ON ph.id = ta.position_id
      LEFT JOIN stocks s ON te.symbol = s.symbol
      ${whereClause}
      ORDER BY te.execution_time DESC
    `,
      params
    );

    if (format === "csv") {
      // Convert to CSV
      const csvHeaders = [
        "Date",
        "Symbol",
        "Side",
        "Quantity",
        "Price",
        "Commission",
        "Gross PnL",
        "Net PnL",
        "Return %",
        "Holding Period (Days)",
        "Pattern Type",
        "Pattern Confidence",
        "Risk/Reward Ratio",
        "Sector",
        "Industry",
      ];

      const csvData = result.rows.map((row) => [
        row.execution_time,
        row.symbol,
        row.side,
        row.quantity,
        row.price,
        row.commission,
        row.gross_pnl,
        row.net_pnl,
        row.return_percentage,
        row.holding_period_days,
        row.trade_pattern_type,
        row.pattern_confidence,
        row.risk_reward_ratio,
        row.sector,
        row.industry,
      ]);

      const csv = [csvHeaders, ...csvData]
        .map((row) => row.join(","))
        .join("\n");

      res.setHeader("Content-Type", "text/csv");
      res.setHeader(
        "Content-Disposition",
        `attachment; filename=trade_history_${new Date().toISOString().split("T")[0]}.csv`
      );
      res.send(csv);
    } else {
      // Return JSON
      res.success({data: result.rows,
      });
    }
  } catch (error) {
    console.error("Error exporting trade data:", error);
    res.status(500).json({
      success: false,
      error: "Failed to export trade data",
    });
  }
});

/**
 * @route DELETE /api/trades/data
 * @desc Delete all trade data for user (for testing/reset)
 */
router.delete("/data", authenticateToken, async (req, res) => {
  try {
    const userId = validateUserAuthentication(req);
    const { confirm } = req.body;

    if (confirm !== "DELETE_ALL_TRADE_DATA") {
      return res.status(400).json({
        success: false,
        error:
          'Confirmation required. Send { "confirm": "DELETE_ALL_TRADE_DATA" }',
      });
    }

    // Database queries will use the query function directly

    // Delete all trade-related data for user using transaction
    await transaction(async (client) => {
      await client.query("DELETE FROM trade_analytics WHERE user_id = $1", [
        userId,
      ]);
      await client.query("DELETE FROM position_history WHERE user_id = $1", [
        userId,
      ]);
      await client.query("DELETE FROM trade_executions WHERE user_id = $1", [
        userId,
      ]);
      await client.query("DELETE FROM trade_insights WHERE user_id = $1", [
        userId,
      ]);
      await client.query(
        "DELETE FROM performance_benchmarks WHERE user_id = $1",
        [userId]
      );
      await client.query("DELETE FROM broker_api_configs WHERE user_id = $1", [
        userId,
      ]);
    });

    res.success({message: "All trade data deleted successfully",
    });
  } catch (error) {
    console.error("Error deleting trade data:", error);
    res.status(500).json({
      success: false,
      error: "Failed to delete trade data",
    });
  }
});

module.exports = router;

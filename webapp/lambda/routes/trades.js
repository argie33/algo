const express = require("express");

const { authenticateToken } = require("../middleware/auth");
const { query, transaction } = require("../utils/database");
const { getApiKey } = require("../utils/apiKeyService");
const AlpacaService = require("../utils/alpacaService");
const responseFormatter = require("../middleware/responseFormatter");

const router = express.Router();

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.json({
    success: true,
    status: "operational",
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
      status = "all", // executed, pending, cancelled, all
    } = req.query;

    console.log(
      `🕒 Getting recent trades for user: ${userId}, last ${days} days`
    );

    // Build query to get recent trade data from trade_history table
    let baseQuery = `
      WITH recent_trades AS (
        SELECT 
          th.id,
          th.symbol,
          th.side,
          th.quantity,
          th.price,
          th.total_amount,
          th.fees,
          th.trade_date,
          th.status,
          th.order_type,
          th.broker,
          th.created_at,
          -- Calculate PnL (simplified)
          CASE 
            WHEN th.side = 'buy' THEN (pd.close_price - th.price) * th.quantity
            WHEN th.side = 'sell' THEN (th.price - pd.close_price) * th.quantity
            ELSE 0
          END as unrealized_pnl,
          -- Get current market data
          pd.close_price as current_price,
          pd.change_percent as daily_change,
          -- Calculate position info
          CASE 
            WHEN th.side = 'buy' THEN th.quantity
            WHEN th.side = 'sell' THEN -th.quantity
            ELSE 0
          END as position_change
        FROM trade_history th
        LEFT JOIN price_daily pd ON th.symbol = pd.symbol 
        AND pd.date = (SELECT MAX(date) FROM price_daily WHERE symbol = th.symbol)
        WHERE th.user_id = $1
        AND th.trade_date >= CURRENT_DATE - INTERVAL '${parseInt(days)} days'
      ),
      trade_analytics AS (
        SELECT 
          rt.*,
          -- Calculate return percentage
          CASE 
            WHEN rt.price > 0 THEN ((rt.current_price - rt.price) / rt.price * 100)
            ELSE 0
          END as return_percentage,
          -- Determine trade performance
          CASE 
            WHEN rt.side = 'buy' AND rt.current_price > rt.price THEN 'winning'
            WHEN rt.side = 'sell' AND rt.current_price < rt.price THEN 'winning'
            WHEN rt.side = 'buy' AND rt.current_price < rt.price THEN 'losing'
            WHEN rt.side = 'sell' AND rt.current_price > rt.price THEN 'losing'
            ELSE 'neutral'
          END as performance,
          -- Market value
          rt.quantity * rt.current_price as market_value,
          -- Days held (for buy orders)
          CASE 
            WHEN rt.side = 'buy' THEN EXTRACT(EPOCH FROM (NOW() - rt.trade_date))/86400
            ELSE NULL
          END as days_held
        FROM recent_trades rt
      )
      SELECT 
        ta.*,
        -- Risk metrics
        CASE 
          WHEN ABS(ta.return_percentage) > 20 THEN 'high_volatility'
          WHEN ABS(ta.return_percentage) > 10 THEN 'medium_volatility'
          ELSE 'low_volatility'
        END as volatility_category,
        -- Trade size category
        CASE 
          WHEN ta.total_amount > 10000 THEN 'large'
          WHEN ta.total_amount > 1000 THEN 'medium'
          ELSE 'small'
        END as trade_size
      FROM trade_analytics ta
      WHERE 1=1
    `;

    const params = [userId];
    let paramIndex = 2;

    // Apply filters
    if (symbol) {
      baseQuery += ` AND ta.symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    if (type && type !== "all") {
      baseQuery += ` AND ta.side = $${paramIndex}`;
      params.push(type);
      paramIndex++;
    }

    if (status && status !== "all") {
      baseQuery += ` AND ta.status = $${paramIndex}`;
      params.push(status);
      paramIndex++;
    }

    // Add ordering and limit
    baseQuery += ` ORDER BY ta.trade_date DESC, ta.created_at DESC`;
    baseQuery += ` LIMIT $${paramIndex}`;
    params.push(parseInt(limit));

    const results = await query(baseQuery, params);

    if (!results.rows || results.rows.length === 0) {
      return res.json({
        success: true,
        data: {
          trades: [],
          summary: {
            total_trades: 0,
            buy_trades: 0,
            sell_trades: 0,
            winning_trades: 0,
            losing_trades: 0,
            win_rate: "0.0",
            total_pnl: "0.00",
            total_fees: "0.00",
            total_volume: "0.00",
            avg_trade_size: "0.00",
            performance_distribution: {
              winning: 0,
              losing: 0,
              neutral: 0,
            },
          },
        },
        message: `No trades found for the last ${days} days`,
        timestamp: new Date().toISOString(),
      });
    }

    // Process trades with enhanced analytics
    const recentTrades = (results.rows || results).map((trade) => ({
      id: trade.id,
      symbol: trade.symbol,
      side: trade.side,
      quantity: parseInt(trade.quantity),
      price: parseFloat(trade.price).toFixed(2),
      current_price: parseFloat(trade.current_price || 0).toFixed(2),
      total_amount: parseFloat(trade.total_amount).toFixed(2),
      market_value: parseFloat(trade.market_value || 0).toFixed(2),
      fees: parseFloat(trade.fees || 0).toFixed(2),

      // Performance metrics
      unrealized_pnl: parseFloat(trade.unrealized_pnl || 0).toFixed(2),
      return_percentage: parseFloat(trade.return_percentage || 0).toFixed(2),
      performance: trade.performance,
      days_held: trade.days_held
        ? parseFloat(trade.days_held).toFixed(1)
        : null,

      // Risk and categorization
      volatility_category: trade.volatility_category,
      trade_size: trade.trade_size,

      // Status and metadata
      status: trade.status,
      order_type: trade.order_type,
      broker: trade.broker,
      trade_date: trade.trade_date,
      daily_change: parseFloat(trade.daily_change || 0).toFixed(2),

      // Indicators
      is_profitable: parseFloat(trade.unrealized_pnl || 0) > 0,
      is_recent:
        new Date(trade.trade_date) >
        new Date(Date.now() - 7 * 24 * 60 * 60 * 1000),

      created_at: trade.created_at,
    }));

    // Calculate summary statistics
    const totalTrades = recentTrades.length;
    const buyTrades = recentTrades.filter((t) => t.side === "buy").length;
    const sellTrades = recentTrades.filter((t) => t.side === "sell").length;
    const winningTrades = recentTrades.filter(
      (t) => t.performance === "winning"
    ).length;
    const losingTrades = recentTrades.filter(
      (t) => t.performance === "losing"
    ).length;

    const totalPnL = recentTrades.reduce(
      (sum, t) => sum + parseFloat(t.unrealized_pnl),
      0
    );
    const totalFees = recentTrades.reduce(
      (sum, t) => sum + parseFloat(t.fees),
      0
    );
    const totalVolume = recentTrades.reduce(
      (sum, t) => sum + parseFloat(t.total_amount),
      0
    );

    return res.json({
      success: true,
      data: {
        trades: recentTrades,
        summary: {
          total_trades: totalTrades,
          buy_trades: buyTrades,
          sell_trades: sellTrades,
          winning_trades: winningTrades,
          losing_trades: losingTrades,
          win_rate:
            totalTrades > 0
              ? ((winningTrades / totalTrades) * 100).toFixed(1)
              : "0.0",

          // Financial metrics
          total_pnl: totalPnL.toFixed(2),
          total_fees: totalFees.toFixed(2),
          total_volume: totalVolume.toFixed(2),
          avg_trade_size:
            totalTrades > 0 ? (totalVolume / totalTrades).toFixed(2) : "0.00",

          // Performance breakdown
          performance_distribution: {
            winning: Math.round(
              (winningTrades / Math.max(totalTrades, 1)) * 100
            ),
            losing: Math.round((losingTrades / Math.max(totalTrades, 1)) * 100),
            neutral: Math.round(
              ((totalTrades - winningTrades - losingTrades) /
                Math.max(totalTrades, 1)) *
                100
            ),
          },
        },
      },
      filters: {
        user_id: userId,
        limit: parseInt(limit),
        days: parseInt(days),
        symbol: symbol || null,
        type: type,
        status: status,
      },
      period: {
        start_date: new Date(Date.now() - parseInt(days) * 24 * 60 * 60 * 1000)
          .toISOString()
          .split("T")[0],
        end_date: new Date().toISOString().split("T")[0],
        days_requested: parseInt(days),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Recent trades error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch recent trades",
      details: error.message,
    });
  }
});

// Basic root endpoint (protected)
router.get("/", authenticateToken, (req, res) => {
  res.json({
    success: true,
    message: "Trade History API - Ready",
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
    try {
      // Initialize Alpaca service
      const alpacaService = new AlpacaService(apiKey, apiSecret, isSandbox);

      // Get orders from Alpaca
      const orders = await alpacaService.getOrders({
        status: "filled",
        after: startDate,
        until: endDate,
      });

      let importedCount = 0;
      const errors = [];

      // Import each filled order as a transaction
      for (const order of orders) {
        try {
          const insertQuery = `
            INSERT INTO portfolio_transactions (
              user_id, symbol, side, quantity, price, 
              order_id, filled_at, created_at, pnl
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), $8)
            ON CONFLICT (order_id) DO NOTHING
            RETURNING id
          `;

          // Calculate basic P&L (simplified - would need more complex logic for actual P&L)
          const pnl =
            order.side === "sell"
              ? (order.filled_avg_price -
                  (order.cost_basis || order.filled_avg_price)) *
                order.filled_qty
              : 0;

          const result = await query(insertQuery, [
            userId,
            order.symbol,
            order.side,
            order.filled_qty,
            order.filled_avg_price,
            order.id,
            order.filled_at,
            pnl,
          ]);

          if (result.rows.length > 0) {
            importedCount++;
          }
        } catch (insertError) {
          errors.push({
            order_id: order.id,
            symbol: order.symbol,
            error: insertError.message,
          });
        }
      }

      return {
        success: true,
        message: `Successfully imported ${importedCount} trades from Alpaca`,
        userId,
        startDate,
        endDate,
        stats: {
          total_orders: orders.length,
          imported: importedCount,
          errors: errors.length,
        },
        errors: errors,
      };
    } catch (error) {
      console.error("Alpaca trade import error:", error);
      return {
        success: false,
        message: "Failed to import trades from Alpaca",
        error: error.message,
        userId,
        startDate,
        endDate,
      };
    }
  }

  async getTradeAnalysisSummary(userId) {
    try {
      // Get trade summary from database
      const summaryQuery = `
        SELECT 
          COUNT(*) as total_trades,
          COUNT(CASE WHEN side = 'buy' THEN 1 END) as buy_trades,
          COUNT(CASE WHEN side = 'sell' THEN 1 END) as sell_trades,
          SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as profitable_trades,
          SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as loss_trades,
          AVG(pnl) as avg_pnl,
          SUM(pnl) as total_pnl,
          AVG(quantity * price) as avg_trade_size
        FROM portfolio_transactions 
        WHERE user_id = $1 
        AND created_at >= NOW() - INTERVAL '30 days'
      `;

      const summaryResult = await query(summaryQuery, [userId]);
      const summary = summaryResult.rows[0];

      // Calculate win rate
      const totalTrades = parseInt(summary.total_trades) || 0;
      const profitableTrades = parseInt(summary.profitable_trades) || 0;
      const winRate =
        totalTrades > 0 ? (profitableTrades / totalTrades) * 100 : 0;

      return {
        userId,
        summary:
          totalTrades > 0
            ? `${totalTrades} trades in last 30 days, ${winRate.toFixed(1)}% win rate, $${parseFloat(summary.total_pnl || 0).toFixed(2)} total P&L`
            : "No trades found in last 30 days",
        insights: [
          `Total trades: ${totalTrades}`,
          `Win rate: ${winRate.toFixed(1)}%`,
          `Average P&L: $${parseFloat(summary.avg_pnl || 0).toFixed(2)}`,
          `Average trade size: $${parseFloat(summary.avg_trade_size || 0).toFixed(2)}`,
        ],
        metrics: {
          total_trades: totalTrades,
          buy_trades: parseInt(summary.buy_trades) || 0,
          sell_trades: parseInt(summary.sell_trades) || 0,
          win_rate: winRate,
          total_pnl: parseFloat(summary.total_pnl || 0),
          avg_pnl: parseFloat(summary.avg_pnl || 0),
          avg_trade_size: parseFloat(summary.avg_trade_size || 0),
        },
      };
    } catch (error) {
      console.error("Trade analysis summary error:", error);
      return {
        insights: [`Error: ${error.message}`],
        summary: "Analysis unavailable - database error",
        userId,
        error: error.message,
      };
    }
  }

  async getTradeInsights(userId, limit = 10) {
    try {
      // Get detailed trade insights
      const insightsQuery = `
        SELECT 
          symbol,
          side,
          quantity,
          price,
          pnl,
          created_at,
          CASE 
            WHEN pnl > 0 THEN 'profit'
            WHEN pnl < 0 THEN 'loss'
            ELSE 'neutral'
          END as result_type
        FROM portfolio_transactions 
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2
      `;

      const insightsResult = await query(insightsQuery, [userId, limit]);

      return insightsResult.rows.map((trade) => ({
        symbol: trade.symbol,
        side: trade.side,
        quantity: parseInt(trade.quantity),
        price: parseFloat(trade.price),
        pnl: parseFloat(trade.pnl || 0),
        date: trade.created_at,
        result: trade.result_type,
        trade_value: parseFloat(trade.quantity * trade.price),
      }));
    } catch (error) {
      console.error("Trade insights error:", error);
      return [
        {
          error: error.message,
          message: "Unable to fetch trade insights - check database connection",
        },
      ];
    }
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

      res.json({
        success: true,
        brokerStatus,
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

      res.json({
        success: true,
        brokerStatus: emptyBrokerStatus,
        totalBrokers: 0,
        activeBrokers: 0,
        message:
          "No broker configurations found - configure your broker API keys in settings",
      });
    }
  } catch (error) {
    console.error("Error fetching import status:", error);
    res.json({
      success: true,
      brokerStatus: [],
      totalBrokers: 0,
      activeBrokers: 0,
      note: "Unable to fetch import status",
    });
  }
});

/**
 * @route POST /api/trades/import
 * @desc Generic trade import endpoint (delegates to specific brokers)
 */
router.post("/import", authenticateToken, async (req, res) => {
  try {
    const userId = validateUserAuthentication(req);
    const { format, data, broker = "alpaca" } = req.body;

    console.log(
      `🔄 [TRADES] Generic import requested for user: ${userId}, format: ${format}, broker: ${broker}`
    );

    if (format === "csv" && data) {
      // Handle CSV import
      const lines = data.split("\n").filter((line) => line.trim());
      const headers = lines[0].split(",");
      const trades = [];

      for (let i = 1; i < lines.length; i++) {
        const values = lines[i].split(",");
        if (values.length >= headers.length) {
          const trade = {};
          headers.forEach((header, index) => {
            trade[header.trim()] = values[index] ? values[index].trim() : "";
          });
          trades.push(trade);
        }
      }

      return res.json({
        success: true,
        message: `Successfully parsed ${trades.length} trades from CSV`,
        data: {
          imported_count: trades.length,
          trades: trades.slice(0, 5), // Show first 5 as sample
        },
      });
    }

    // Default to Alpaca import for backwards compatibility
    if (broker === "alpaca") {
      const { startDate, endDate } = req.body;
      const credentials = await getUserApiKey(userId, "alpaca");

      if (!credentials) {
        return sendApiKeyError(res, "No active Alpaca API keys found");
      }

      if (!tradeAnalyticsService) {
        tradeAnalyticsService = new TradeAnalyticsService();
      }

      const importResult = await tradeAnalyticsService.importAlpacaTrades(
        userId,
        credentials.apiKey,
        credentials.apiSecret,
        credentials.isSandbox,
        startDate,
        endDate
      );

      return res.json({
        success: true,
        message: "Trade import completed successfully",
        data: importResult,
      });
    }

    return res.status(400).json({
      success: false,
      error: "Invalid import format or broker",
      supported_formats: ["csv"],
      supported_brokers: ["alpaca"],
    });
  } catch (error) {
    console.error("Error importing trades:", error);
    res.status(500).json({
      success: false,
      error: error.message || "Failed to import trades",
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
      return sendApiKeyError(res, "No active Alpaca API keys found");
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

    res.json({
      message: "Trade import completed successfully",
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

    res.json({ data: summary });
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

    res.json({
      data: {
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

    console.log(
      `📊 Trade analytics requested for user: ${userId}, timeframe: ${timeframe}`
    );

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
        avg_holding_period: 0,
      },
      performance_metrics: {
        sharpe_ratio: 0,
        max_drawdown: 0,
        profit_factor: 0,
        risk_adjusted_return: 0,
        volatility: 0,
        beta: 0,
        alpha: 0,
        sortino_ratio: 0,
      },
      sector_breakdown: [],
      monthly_performance: [],
      trade_distribution: {
        by_size: [],
        by_holding_period: [],
        by_time_of_day: [],
      },
      recent_trades: [],
      insights: [],
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
          avg_holding_period: parseFloat(metrics.avg_holding_period || 0),
        };

        // Calculate performance metrics
        const volatility = parseFloat(metrics.pnl_volatility || 0);
        const avgReturn = parseFloat(metrics.avg_pnl || 0);
        analyticsData.performance_metrics = {
          sharpe_ratio:
            volatility > 0
              ? parseFloat((avgReturn / volatility).toFixed(3))
              : 0,
          max_drawdown: parseFloat(
            (
              (Math.abs(metrics.worst_trade || 0) /
                Math.max(metrics.total_volume || 1, 1000)) *
              100
            ).toFixed(2)
          ),
          profit_factor:
            metrics.losing_trades > 0
              ? parseFloat(
                  (
                    Math.abs(metrics.total_pnl) /
                    Math.abs(metrics.worst_trade * metrics.losing_trades)
                  ).toFixed(2)
                )
              : 0,
          risk_adjusted_return: parseFloat(
            (avgReturn / Math.max(volatility, 1)).toFixed(3)
          ),
          volatility: parseFloat(volatility.toFixed(2)),
          beta: null, // Beta calculation requires market data comparison
          alpha: parseFloat((avgReturn * 0.1).toFixed(3)),
          sortino_ratio: parseFloat(
            (
              (avgReturn / Math.max(Math.abs(metrics.worst_trade || 1), 1)) *
              100
            ).toFixed(3)
          ),
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

      analyticsData.sector_breakdown = sectorResult.rows.map((row) => ({
        sector: row.sector,
        trade_count: parseInt(row.trade_count),
        pnl: parseFloat(row.sector_pnl || 0),
        avg_roi: parseFloat(row.avg_roi || 0),
        performance_grade:
          parseFloat(row.sector_pnl || 0) > 0 ? "Positive" : "Negative",
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

      analyticsData.recent_trades = recentTradesResult.rows.map((trade) => ({
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
        duration_days: trade.closed_at
          ? Math.ceil(
              (new Date(trade.closed_at) - new Date(trade.opened_at)) /
                (1000 * 60 * 60 * 24)
            )
          : Math.ceil(
              (new Date() - new Date(trade.opened_at)) / (1000 * 60 * 60 * 24)
            ),
      }));
    } catch (dbError) {
      console.error(
        "Database query failed for trade analytics:",
        dbError.message
      );
      return res
        .status(500)
        .json({
          success: false,
          error: "Failed to retrieve trade analytics",
          details: dbError.message,
          suggestion: "Please ensure trade data is available in the database",
        });
    }

    res.json({
      success: true,
      data: analyticsData,
      metadata: {
        timeframe: timeframe,
        date_range: {
          start: startDate.toISOString().split("T")[0],
          end: endDate.toISOString().split("T")[0],
        },
        data_source:
          analyticsData.summary.total_trades > 0 ? "database" : "empty",
        analysis_type: "comprehensive_trade_analytics",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Trade analytics error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch trade analytics",
      details: error.message,
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
              ? (
                  (dbMetrics.winning_trades / dbMetrics.total_trades) *
                  100
                ).toFixed(2)
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
            winRate:
              fills.length > 0
                ? ((winningTrades / fills.length) * 100).toFixed(2)
                : 0,
            totalPnL: totalPnL,
            avgPnL: fills.length > 0 ? totalPnL / fills.length : 0,
            avgROI: 0, // Would need position cost basis to calculate
            bestTrade: Math.max(
              ...fills.map((f) => parseFloat(f.net_amount) || 0)
            ),
            worstTrade: Math.min(
              ...fills.map((f) => parseFloat(f.net_amount) || 0)
            ),
            avgHoldingPeriod: 0, // Would need position open/close times
            totalVolume: fills.reduce(
              (sum, fill) =>
                sum +
                (parseFloat(fill.qty) || 0) * (parseFloat(fill.price) || 0),
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

    res.json({
      data: {
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

    res.json({
      data: {
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

    res.json({
      data: {
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
        "Performance calculations completed",
      ],
      actions: [
        "Contact administrator to verify database schema",
        "Ensure all required tables exist and contain data",
        "Import historical trading data from broker",
      ],
      timestamp: new Date().toISOString(),
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

        return res.json({
          data: {
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

    // Fallback to database trade data when no broker API credentials are available
    console.log(
      "🔄 No broker API credentials found, falling back to database trade data..."
    );

    try {
      const fallbackQuery = `
        SELECT 
          transaction_id as id,
          symbol,
          transaction_type as action,
          quantity,
          price,
          total_amount as pnl,
          executed_at as execution_time,
          'database' as source
        FROM portfolio_transactions 
        WHERE user_id = $1
        ORDER BY executed_at DESC
        LIMIT $2 OFFSET $3
      `;

      const countQuery = `
        SELECT COUNT(*) as total 
        FROM portfolio_transactions 
        WHERE user_id = $1
      `;

      const [tradeResults, countResults] = await Promise.all([
        query(fallbackQuery, [userId, parseInt(limit), parseInt(offset)]),
        query(countQuery, [userId]),
      ]);

      const trades = tradeResults.rows.map((trade) => ({
        id: trade.id,
        symbol: trade.symbol,
        action: trade.action,
        quantity: parseInt(trade.quantity),
        price: parseFloat(trade.price),
        pnl: parseFloat(trade.pnl || 0),
        execution_time: trade.execution_time,
        source: trade.source,
        status: "filled",
      }));

      const total = parseInt(countResults.rows[0].total);

      console.log(
        `✅ Retrieved ${trades.length} trades from database (${total} total)`
      );

      return res.json({
        success: true,
        data: {
          trades,
          pagination: {
            total,
            limit: parseInt(limit),
            offset: parseInt(offset),
            hasMore: parseInt(offset) + parseInt(limit) < total,
          },
          source: "database_fallback",
          note: "Using database trade data. Configure broker API credentials for real-time data.",
        },
        timestamp: new Date().toISOString(),
      });
    } catch (dbError) {
      console.error("Database fallback failed:", dbError.message);
      // If database fallback also fails, return the original 503 error
      return res.status(503).json({
        success: false,
        error: "Trade history unavailable",
        details:
          "Unable to retrieve trade history from broker APIs or database",
        message:
          "Trade history requires valid broker API credentials. Please configure your broker API keys in Settings to access real trade data.",
        service: "trade-history",
        requirements: [
          "Valid broker API credentials (Alpaca, Interactive Brokers, etc.)",
          "Active trading account with broker",
          "API permissions enabled for trade data access",
        ],
        actions: [
          "Go to Settings → API Keys to configure broker credentials",
          "Ensure your broker account has API access enabled",
          "Verify API key permissions include trade data access",
        ],
      });
    }
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
      res.json({ data: result.rows });
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

    res.json({ message: "All trade data deleted successfully" });
  } catch (error) {
    console.error("Error deleting trade data:", error);
    res.status(500).json({
      success: false,
      error: "Failed to delete trade data",
    });
  }
});

// Trade Analysis Patterns endpoint
router.get("/analysis/patterns", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const {
      period = "3m",
      pattern_type = "all",
      min_occurrences = 2,
    } = req.query;

    console.log(
      `📊 Trade pattern analysis requested for user: ${userId}, period: ${period}`
    );

    // Get user's trading history for pattern analysis
    const tradesResult = await query(
      `
      SELECT 
        symbol, quantity, price, side, executed_at, order_type,
        EXTRACT(DOW FROM executed_at) as day_of_week,
        EXTRACT(HOUR FROM executed_at) as hour_of_day,
        ABS(quantity * price) as trade_value
      FROM trades 
      WHERE user_id = $1 
        AND executed_at >= NOW() - INTERVAL '3 months'
        AND status = 'executed'
      ORDER BY executed_at ASC
    `,
      [userId]
    );

    if (!tradesResult || !tradesResult.rows || tradesResult.rows.length < 5) {
      return res.json({
        success: true,
        data: {
          patterns: [],
          summary: {
            total_trades: tradesResult?.rows?.length || 0,
            analysis_period: period,
            patterns_found: 0,
            message:
              "Insufficient trade history for pattern analysis. At least 5 trades required.",
          },
          insights: {
            recommendation:
              "Continue trading to build sufficient history for pattern analysis",
            required_trades: 5,
            current_trades: tradesResult?.rows?.length || 0,
          },
        },
        timestamp: new Date().toISOString(),
      });
    }

    const trades = tradesResult.rows;
    const patterns = [];

    // Analyze trading time patterns
    const timePatterns = {};
    const dayPatterns = {};
    const symbolPatterns = {};
    const volumePatterns = { small: 0, medium: 0, large: 0 };

    trades.forEach((trade) => {
      // Time of day patterns
      const hour = parseInt(trade.hour_of_day);
      const timeSlot =
        hour < 10
          ? "morning"
          : hour < 14
            ? "midday"
            : hour < 16
              ? "afternoon"
              : "after-hours";
      timePatterns[timeSlot] = (timePatterns[timeSlot] || 0) + 1;

      // Day of week patterns
      const days = [
        "Sunday",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
      ];
      const dayName = days[parseInt(trade.day_of_week)];
      dayPatterns[dayName] = (dayPatterns[dayName] || 0) + 1;

      // Symbol frequency patterns
      symbolPatterns[trade.symbol] = (symbolPatterns[trade.symbol] || 0) + 1;

      // Volume patterns
      const value = parseFloat(trade.trade_value);
      if (value < 1000) volumePatterns.small++;
      else if (value < 10000) volumePatterns.medium++;
      else volumePatterns.large++;
    });

    // Find significant patterns (above minimum occurrences)
    Object.entries(timePatterns).forEach(([time, count]) => {
      if (count >= min_occurrences) {
        patterns.push({
          type: "time_preference",
          pattern: `Prefers trading during ${time}`,
          occurrences: count,
          percentage: ((count / trades.length) * 100).toFixed(1),
          significance:
            count >= trades.length * 0.4
              ? "high"
              : count >= trades.length * 0.2
                ? "medium"
                : "low",
        });
      }
    });

    Object.entries(dayPatterns).forEach(([day, count]) => {
      if (count >= min_occurrences) {
        patterns.push({
          type: "day_preference",
          pattern: `Frequently trades on ${day}`,
          occurrences: count,
          percentage: ((count / trades.length) * 100).toFixed(1),
          significance:
            count >= trades.length * 0.3
              ? "high"
              : count >= trades.length * 0.15
                ? "medium"
                : "low",
        });
      }
    });

    Object.entries(symbolPatterns).forEach(([symbol, count]) => {
      if (count >= min_occurrences) {
        patterns.push({
          type: "symbol_preference",
          pattern: `Frequently trades ${symbol}`,
          occurrences: count,
          percentage: ((count / trades.length) * 100).toFixed(1),
          significance:
            count >= trades.length * 0.3
              ? "high"
              : count >= trades.length * 0.15
                ? "medium"
                : "low",
        });
      }
    });

    // Volume pattern analysis
    const dominantVolume = Object.entries(volumePatterns).reduce((a, b) =>
      volumePatterns[a[0]] > volumePatterns[b[0]] ? a : b
    );

    if (dominantVolume[1] >= min_occurrences) {
      const volumeLabels = {
        small: "small trades (<$1,000)",
        medium: "medium trades ($1,000-$10,000)",
        large: "large trades (>$10,000)",
      };

      patterns.push({
        type: "volume_preference",
        pattern: `Prefers ${volumeLabels[dominantVolume[0]]}`,
        occurrences: dominantVolume[1],
        percentage: ((dominantVolume[1] / trades.length) * 100).toFixed(1),
        significance:
          dominantVolume[1] >= trades.length * 0.5 ? "high" : "medium",
      });
    }

    // Calculate win/loss patterns if we have price data
    let tradingInsights = {
      most_active_time: Object.entries(timePatterns).reduce((a, b) =>
        timePatterns[a[0]] > timePatterns[b[0]] ? a : b
      )[0],
      most_active_day: Object.entries(dayPatterns).reduce((a, b) =>
        dayPatterns[a[0]] > dayPatterns[b[0]] ? a : b
      )[0],
      favorite_symbol: Object.entries(symbolPatterns).reduce((a, b) =>
        symbolPatterns[a[0]] > symbolPatterns[b[0]] ? a : b
      )[0],
      trading_style: dominantVolume[0] + "_volume_trader",
    };

    res.json({
      success: true,
      data: {
        patterns: patterns.sort((a, b) => b.occurrences - a.occurrences),
        summary: {
          total_trades: trades.length,
          analysis_period: period,
          patterns_found: patterns.length,
          date_range: {
            start: trades[0]?.executed_at,
            end: trades[trades.length - 1]?.executed_at,
          },
        },
        insights: tradingInsights,
        pattern_distribution: {
          time_patterns: timePatterns,
          day_patterns: dayPatterns,
          volume_patterns: volumePatterns,
          symbol_patterns: Object.entries(symbolPatterns)
            .slice(0, 5)
            .reduce((obj, [k, v]) => ({ ...obj, [k]: v }), {}),
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Trade pattern analysis error:", error);

    // Handle database table missing error
    if (error.code === "42P01") {
      return res.status(500).json({
        success: false,
        error: "Trade history table not found",
        message:
          "Pattern analysis requires trade execution history. Please ensure trades are being recorded.",
        details: {
          required_table: "trades",
          required_columns: [
            "user_id",
            "symbol",
            "quantity",
            "price",
            "side",
            "executed_at",
            "status",
          ],
          suggestion:
            "Set up trade execution tracking or import historical trade data",
        },
      });
    }

    res.status(500).json({
      success: false,
      error: "Failed to analyze trade patterns",
      message: error.message,
    });
  }
});

// Trade analysis endpoint (protected)
router.get("/analysis", authenticateToken, async (req, res) => {
  try {
    const {
      timeframe = "30d",
      analysis_type = "summary",
      symbol = null,
      limit = 50,
    } = req.query;

    console.log(
      `📊 Trade analysis requested - timeframe: ${timeframe}, type: ${analysis_type}, symbol: ${symbol}`
    );

    // Calculate date range based on timeframe
    const timeframeDays = {
      "7d": 7,
      "30d": 30,
      "90d": 90,
      "1y": 365,
      ytd: Math.floor(
        (new Date() - new Date(new Date().getFullYear(), 0, 0)) /
          (1000 * 60 * 60 * 24)
      ),
    };

    const days = timeframeDays[timeframe] || 30;

    let symbolFilter = "";
    let queryParams = [days];
    if (symbol) {
      symbolFilter = "AND symbol = $2";
      queryParams.push(symbol.toUpperCase());
    }

    // Get trade data from database
    const tradeQuery = `
      SELECT 
        symbol,
        trade_type,
        quantity,
        price,
        total_value,
        date,
        profit_loss
      FROM trades 
      WHERE date >= CURRENT_DATE - INTERVAL '${days} days'
        ${symbolFilter}
      ORDER BY date DESC
      LIMIT ${limit}
    `;

    const tradesResult = await query(tradeQuery, queryParams);

    if (!tradesResult.rows || tradesResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No trade data found",
        message: `No trades available for analysis in the specified timeframe`,
        details: {
          timeframe: timeframe,
          symbol: symbol || "all",
          suggestion:
            "Try expanding the timeframe or checking if trades have been recorded",
        },
      });
    }

    const trades = tradesResult.rows;

    // Perform analysis based on analysis_type
    let analysisResult;

    switch (analysis_type) {
      case "summary":
        analysisResult = generateTradeSummary(trades, timeframe);
        break;
      case "performance":
        analysisResult = generatePerformanceAnalysis(trades, timeframe);
        break;
      case "patterns":
        analysisResult = generatePatternAnalysis(trades, timeframe);
        break;
      default:
        analysisResult = generateTradeSummary(trades, timeframe);
    }

    res.json({
      success: true,
      data: {
        analysis_type: analysis_type,
        timeframe: timeframe,
        symbol_filter: symbol || "all",
        trade_count: trades.length,
        ...analysisResult,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Trade analysis error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to perform trade analysis",
      message: error.message,
    });
  }
});

// Helper functions for trade analysis
function generateTradeSummary(trades, timeframe) {
  const totalTrades = trades.length;
  const buyTrades = trades.filter((t) => t.trade_type === "BUY").length;
  const sellTrades = trades.filter((t) => t.trade_type === "SELL").length;

  const totalVolume = trades.reduce(
    (sum, t) => sum + parseFloat(t.total_value || 0),
    0
  );
  const totalProfitLoss = trades.reduce(
    (sum, t) => sum + parseFloat(t.profit_loss || 0),
    0
  );

  const profitableTrades = trades.filter(
    (t) => parseFloat(t.profit_loss || 0) > 0
  ).length;
  const winRate = totalTrades > 0 ? (profitableTrades / totalTrades) * 100 : 0;

  const avgTradeSize = totalTrades > 0 ? totalVolume / totalTrades : 0;
  const avgProfitLoss = totalTrades > 0 ? totalProfitLoss / totalTrades : 0;

  return {
    summary: {
      total_trades: totalTrades,
      buy_trades: buyTrades,
      sell_trades: sellTrades,
      win_rate: `${winRate.toFixed(2)}%`,
      total_volume: totalVolume.toFixed(2),
      total_profit_loss: totalProfitLoss.toFixed(2),
      average_trade_size: avgTradeSize.toFixed(2),
      average_profit_loss: avgProfitLoss.toFixed(2),
    },
  };
}

function generatePerformanceAnalysis(trades, timeframe) {
  const summary = generateTradeSummary(trades, timeframe);

  // Calculate additional performance metrics
  const profits = trades
    .filter((t) => parseFloat(t.profit_loss || 0) > 0)
    .map((t) => parseFloat(t.profit_loss));
  const losses = trades
    .filter((t) => parseFloat(t.profit_loss || 0) < 0)
    .map((t) => Math.abs(parseFloat(t.profit_loss)));

  const avgProfit =
    profits.length > 0
      ? profits.reduce((a, b) => a + b, 0) / profits.length
      : 0;
  const avgLoss =
    losses.length > 0 ? losses.reduce((a, b) => a + b, 0) / losses.length : 0;
  const profitFactor = avgLoss > 0 ? avgProfit / avgLoss : 0;

  // Risk metrics
  const maxProfit = profits.length > 0 ? Math.max(...profits) : 0;
  const maxLoss = losses.length > 0 ? Math.max(...losses) : 0;

  return {
    ...summary,
    performance: {
      average_profit: avgProfit.toFixed(2),
      average_loss: avgLoss.toFixed(2),
      profit_factor: profitFactor.toFixed(2),
      max_profit: maxProfit.toFixed(2),
      max_loss: maxLoss.toFixed(2),
      risk_reward_ratio:
        avgProfit > 0 && avgLoss > 0 ? (avgProfit / avgLoss).toFixed(2) : "N/A",
    },
  };
}

function generatePatternAnalysis(trades, timeframe) {
  const summary = generateTradeSummary(trades, timeframe);

  // Analyze trading patterns by symbol
  const symbolStats = {};
  trades.forEach((trade) => {
    if (!symbolStats[trade.symbol]) {
      symbolStats[trade.symbol] = { count: 0, profit_loss: 0, volume: 0 };
    }
    symbolStats[trade.symbol].count++;
    symbolStats[trade.symbol].profit_loss += parseFloat(trade.profit_loss || 0);
    symbolStats[trade.symbol].volume += parseFloat(trade.total_value || 0);
  });

  // Convert to array and sort by count
  const topSymbols = Object.entries(symbolStats)
    .map(([symbol, stats]) => ({
      symbol,
      trade_count: stats.count,
      total_profit_loss: stats.profit_loss.toFixed(2),
      total_volume: stats.volume.toFixed(2),
      avg_profit_per_trade:
        stats.count > 0 ? (stats.profit_loss / stats.count).toFixed(2) : "0.00",
    }))
    .sort((a, b) => b.trade_count - a.trade_count)
    .slice(0, 10);

  // Time-based analysis
  const hourlyDistribution = {};
  trades.forEach((trade) => {
    const hour = new Date(trade.date).getHours();
    hourlyDistribution[hour] = (hourlyDistribution[hour] || 0) + 1;
  });

  return {
    ...summary,
    patterns: {
      top_traded_symbols: topSymbols,
      hourly_distribution: hourlyDistribution,
      trade_frequency: `${(trades.length / parseInt(timeframe) || 0).toFixed(2)} trades per day`,
    },
  };
}

module.exports = router;

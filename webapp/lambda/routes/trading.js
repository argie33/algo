const express = require("express");

const { authenticateToken } = require("../middleware/auth");
const { query } = require("../utils/database");

const router = express.Router();

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.success({status: "operational",
    service: "trading",
    timestamp: new Date().toISOString(),
    message: "Trading service is running",
  });
});

// Basic root endpoint (public)
router.get("/", (req, res) => {
  res.success({message: "Trading API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
  });
});

// Helper function to check if required tables exist
async function checkRequiredTables(tableNames) {
  const results = {};
  for (const tableName of tableNames) {
    try {
      const tableExistsResult = await query(
        `SELECT EXISTS (
          SELECT FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name = $1
        );`,
        [tableName]
      );
      results[tableName] = tableExistsResult.rows[0].exists;
    } catch (error) {
      console.error(`Error checking table ${tableName}:`, error.message);
      results[tableName] = false;
    }
  }
  return results;
}

// Debug endpoint to check trading tables status
router.get("/debug", async (req, res) => {
  console.log("[TRADING] Debug endpoint called");

  try {
    // Check all trading tables
    const requiredTables = [
      "buy_sell_daily",
      "buy_sell_weekly",
      "buy_sell_monthly",
      "market_data",
      "company_profile",
      "swing_trader",
    ];

    const tableStatus = await checkRequiredTables(requiredTables);

    // Get record counts for existing tables
    const recordCounts = {};
    for (const [tableName, exists] of Object.entries(tableStatus)) {
      if (exists) {
        try {
          const countResult = await query(
            `SELECT COUNT(*) as count FROM ${tableName}`
          );
          recordCounts[tableName] = parseInt(countResult.rows[0].count);
        } catch (error) {
          recordCounts[tableName] = { error: error.message };
        }
      } else {
        recordCounts[tableName] = "Table does not exist";
      }
    }

    res.success({status: "ok",
      timestamp: new Date().toISOString(),
      tables: tableStatus,
      recordCounts: recordCounts,
      endpoint: "trading",
    });
  } catch (error) {
    console.error("[TRADING] Error in debug endpoint:", error);
    return res.error("Failed to check trading tables", {
      message: error.message,
      timestamp: new Date().toISOString(),
    }, 500);
  }
});

// Get all trading signals (without timeframe requirement)
router.get("/signals", async (req, res) => {
  try {
    const { limit = 100, symbol, signal_type } = req.query;

    // Validate limit parameter
    const limitNum = parseInt(limit);
    if (isNaN(limitNum) || limitNum <= 0) {
      return res.error("Limit must be a positive number", 400);
    }
    if (limitNum > 500) {
      return res.error("Limit cannot exceed 500", 400);
    }

    // Build base query for all signal tables
    let whereClause = "WHERE 1=1";
    let params = [];
    let paramIndex = 1;

    if (symbol) {
      whereClause += ` AND symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    if (signal_type) {
      whereClause += ` AND signal_type = $${paramIndex}`;
      params.push(signal_type);
      paramIndex++;
    }

    // Query signals from multiple timeframes
    const signalsQuery = `
      (SELECT symbol, signal_type, price, date, 'daily' as timeframe FROM buy_sell_daily ${whereClause})
      UNION ALL
      (SELECT symbol, signal_type, price, date, 'weekly' as timeframe FROM buy_sell_weekly ${whereClause})
      UNION ALL  
      (SELECT symbol, signal_type, price, date, 'monthly' as timeframe FROM buy_sell_monthly ${whereClause})
      ORDER BY date DESC
      LIMIT $${paramIndex}
    `;

    params.push(limitNum);

    const result = await query(signalsQuery, params);

    // Add null checking for database availability 
    if (!result || !result.rows) {
      console.warn("Trading signals query returned null result, database may be unavailable");
      return res.error("Database temporarily unavailable", {
        message: "Trading signals temporarily unavailable - database connection issue",
        data: [],
        count: 0,
        timestamp: new Date().toISOString()
      }, 503);
    }

    res.success({data: result.rows || [],
      count: result.rows ? result.rows.length : 0,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching trading signals:", error);
    return res.error("Failed to fetch trading signals", 500, {
      message: error.message,
    });
  }
});

// Get buy/sell signals by timeframe
router.get("/signals/:timeframe", async (req, res) => {
  console.log("[TRADING] Received request for /signals/:timeframe", {
    params: req.params,
    query: req.query,
    path: req.path,
    method: req.method,
    time: new Date().toISOString(),
  });
  try {
    const { timeframe } = req.params;
    const {
      limit = 100,
      page = 1,
      symbol,
      signal_type,
      latest_only,
    } = req.query;
    const pageNum = Math.max(1, parseInt(page));
    const pageSize = Math.max(1, parseInt(limit));
    const offset = (pageNum - 1) * pageSize;

    // Validate timeframe
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      console.warn("[TRADING] Invalid timeframe:", timeframe);
      return res.error("Invalid timeframe. Must be daily, weekly, or monthly", 400);
    }

    const tableName = `buy_sell_${timeframe}`;

    // Defensive: Check if table exists before querying
    const tableExistsResult = await query(
      `SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );`,
      [tableName]
    );
    if (!tableExistsResult.rows[0].exists) {
      console.error(`[TRADING] Table does not exist: ${tableName}`);
      return res.error(`Table ${tableName} does not exist in the database.`, 500, {
        details: `Expected table ${tableName} for trading signals. Please check your database schema.`,
      });
    }

    // Build WHERE clause
    let whereClause = "";
    const queryParams = [];
    let paramCount = 0;

    const conditions = [];

    if (symbol) {
      paramCount++;
      conditions.push(`symbol = $${paramCount}`);
      queryParams.push(symbol.toUpperCase());
    }

    if (signal_type === "buy") {
      conditions.push("signal = 'Buy'");
    } else if (signal_type === "sell") {
      conditions.push("signal = 'Sell'");
    }

    if (conditions.length > 0) {
      whereClause = "WHERE " + conditions.join(" AND ");
    }

    // Build the main query - handle latest_only with window function
    let sqlQuery;
    if (latest_only === "true") {
      sqlQuery = `
        WITH ranked_signals AS (
          SELECT 
            bs.symbol,
            bs.date,
            bs.signal,
            bs.buylevel as price,
            bs.stoplevel,
            bs.inposition,
            md.price as current_price,
            cp.company_name,
            cp.sector,
            md.market_cap,
            km.trailing_pe,
            km.dividend_yield,
            CASE 
              WHEN bs.signal = 'Buy' AND md.price > bs.buylevel 
              THEN ((md.price - bs.buylevel) / bs.buylevel * 100)
              WHEN bs.signal = 'Sell' AND md.price < bs.buylevel 
              THEN ((bs.buylevel - md.price) / bs.buylevel * 100)
              ELSE 0
            END as performance_percent,
            ROW_NUMBER() OVER (PARTITION BY bs.symbol ORDER BY bs.date DESC) as rn
          FROM ${tableName} bs
          LEFT JOIN market_data md ON bs.symbol = md.symbol
          LEFT JOIN company_profile cp ON bs.symbol = cp.ticker
          LEFT JOIN key_metrics km ON bs.symbol = km.ticker
          ${whereClause}
        )
        SELECT * FROM ranked_signals 
        WHERE rn = 1
        ORDER BY date DESC, symbol ASC
        LIMIT $${queryParams.length + 1} OFFSET $${queryParams.length + 2}
      `;
    } else {
      sqlQuery = `
        SELECT 
          bs.symbol,
          bs.date,
          bs.signal,
          bs.buylevel as price,
          bs.stoplevel,
          bs.inposition,
          md.price as current_price,
          cp.company_name,
          cp.sector,
          md.market_cap,
          km.trailing_pe,
          km.dividend_yield,
          CASE 
            WHEN bs.signal = 'Buy' AND md.price > bs.buylevel 
            THEN ((md.price - bs.buylevel) / bs.buylevel * 100)
            WHEN bs.signal = 'Sell' AND md.price < bs.buylevel 
            THEN ((bs.buylevel - md.price) / bs.buylevel * 100)
            ELSE 0
          END as performance_percent
        FROM ${tableName} bs
        LEFT JOIN market_data md ON bs.symbol = md.symbol
        LEFT JOIN company_profile cp ON bs.symbol = cp.ticker
        LEFT JOIN key_metrics km ON bs.symbol = km.ticker
        ${whereClause}
        ORDER BY bs.date DESC, bs.symbol ASC
        LIMIT $${queryParams.length + 1} OFFSET $${queryParams.length + 2}
      `;
    }

    // Count query for pagination
    let countQuery;
    if (latest_only === "true") {
      countQuery = `
        WITH ranked_signals AS (
          SELECT bs.symbol,
            ROW_NUMBER() OVER (PARTITION BY bs.symbol ORDER BY bs.date DESC) as rn
          FROM ${tableName} bs
          ${whereClause}
        )
        SELECT COUNT(*) as total
        FROM ranked_signals 
        WHERE rn = 1
      `;
    } else {
      countQuery = `
        SELECT COUNT(*) as total
        FROM ${tableName} bs
        ${whereClause}
      `;
    }

    queryParams.push(pageSize, offset);

    console.log("[TRADING] Executing SQL:", sqlQuery, "Params:", queryParams);
    console.log(
      "[TRADING] Executing count SQL:",
      countQuery,
      "Params:",
      queryParams.slice(0, paramCount)
    );

    const [result, countResult] = await Promise.all([
      query(sqlQuery, queryParams),
      query(countQuery, queryParams.slice(0, paramCount)),
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / pageSize);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      console.warn("[TRADING] No data found for query:", {
        timeframe,
        params: req.query,
      });
      return res.success({
        data: [],
        timeframe,
        count: 0,
        pagination: {
          page: pageNum,
          limit: pageSize,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false,
        },
        metadata: {
          signal_type: signal_type || "all",
          symbol: symbol || null,
          message: "No trading signals found for the specified criteria",
        },
      });
    }

    console.log(
      "[TRADING] Query returned",
      result.rows.length,
      "rows out of",
      total,
      "total"
    );

    res.success({data: result.rows,
      timeframe,
      count: result.rows.length,
      pagination: {
        page: pageNum,
        limit: pageSize,
        total,
        totalPages,
        hasNext: pageNum < totalPages,
        hasPrev: pageNum > 1,
      },
      metadata: {
        signal_type: signal_type || "all",
        symbol: symbol || null,
      },
    });
  } catch (error) {
    console.error("[TRADING] Error fetching trading signals:", error);
    return res.error("Failed to fetch trading signals", 500);
  }
});

// Get signals summary
router.get("/summary/:timeframe", async (req, res) => {
  try {
    const { timeframe } = req.params;

    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.error("Invalid timeframe" , 400);
    }

    const tableName = `buy_sell_${timeframe}`;
    const sqlQuery = `
      SELECT 
        COUNT(*) as total_signals,
        COUNT(CASE WHEN signal = 'Buy' THEN 1 END) as buy_signals,
        COUNT(CASE WHEN signal = 'Sell' THEN 1 END) as sell_signals,
        COUNT(CASE WHEN signal = 'Buy' THEN 1 END) as strong_buy,
        COUNT(CASE WHEN signal = 'Sell' THEN 1 END) as strong_sell,
        COUNT(CASE WHEN signal != 'None' AND signal IS NOT NULL THEN 1 END) as active_signals
      FROM ${tableName}
      WHERE date >= CURRENT_DATE - INTERVAL '30 days'
    `;

    const result = await query(sqlQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.notFound("No data found for this query" );
    }

    res.success({data: result.rows[0],
      timeframe,
      period: "last_30_days",
    });
  } catch (error) {
    console.error("Error fetching signals summary:", error);
    return res.error("Failed to fetch signals summary", 500);
  }
});

// Get swing trading signals
router.get("/swing-signals", async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;

    const swingQuery = `
      SELECT 
        st.symbol,
        cp.company_name,
        st.signal,
        st.entry_price,
        st.stop_loss,
        st.target_price,
        st.risk_reward_ratio,
        st.date,
        md.price as current_price,
        CASE 
          WHEN st.signal = 'BUY' AND md.price >= st.target_price 
          THEN 'TARGET_HIT'
          WHEN st.signal = 'BUY' AND md.price <= st.stop_loss 
          THEN 'STOP_LOSS_HIT'
          WHEN st.signal = 'SELL' AND md.price <= st.target_price 
          THEN 'TARGET_HIT'
          WHEN st.signal = 'SELL' AND md.price >= st.stop_loss 
          THEN 'STOP_LOSS_HIT'
          ELSE 'ACTIVE'
        END as status
      FROM swing_trader st
      JOIN company_profile cp ON st.symbol = cp.ticker
      LEFT JOIN market_data md ON st.symbol = md.symbol
      ORDER BY st.date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM swing_trader
    `;

    const [swingResult, countResult] = await Promise.all([
      query(swingQuery, [limit, offset]),
      query(countQuery),
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (
      !swingResult ||
      !Array.isArray(swingResult.rows) ||
      swingResult.rows.length === 0
    ) {
      return res.notFound("No data found for this query" );
    }

    res.success({
      data: swingResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching swing signals:", error);
    return res.error("Failed to fetch swing signals" , 500);
  }
});

// Get technical indicators for a stock
router.get("/:ticker/technicals", async (req, res) => {
  try {
    const { ticker } = req.params;
    const timeframe = req.query.timeframe || "daily"; // daily, weekly, monthly

    let tableName = "latest_technicals_daily";
    if (timeframe === "weekly") tableName = "latest_technicals_weekly";
    if (timeframe === "monthly") tableName = "latest_technicals_monthly";

    const techQuery = `
      SELECT 
        symbol,
        date,
        sma_20,
        sma_50,
        sma_200,
        ema_12,
        ema_26,
        rsi_14,
        macd,
        macd_signal,
        macd_histogram,
        bb_upper,
        bb_middle,
        bb_lower,
        volume_sma
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `;

    const result = await query(techQuery, [ticker.toUpperCase()]);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.notFound("No data found for this query" );
    }

    res.success({
      ticker: ticker.toUpperCase(),
      timeframe,
      data: result.rows[0],
    });
  } catch (error) {
    console.error("Error fetching technical indicators:", error);
    return res.error("Failed to fetch technical indicators" , 500);
  }
});

// Get performance summary of recent signals
router.get("/performance", async (req, res) => {
  try {
    const days = parseInt(req.query.days) || 30;

    const performanceQuery = `
      SELECT 
        signal,
        COUNT(*) as total_signals,
        AVG(
          CASE 
            WHEN signal = 'BUY' AND md.price > bs.price 
            THEN ((md.price - bs.price) / bs.price * 100)
            WHEN signal = 'SELL' AND md.price < bs.price 
            THEN ((bs.price - md.price) / bs.price * 100)
            ELSE 0
          END
        ) as avg_performance,
        COUNT(
          CASE 
            WHEN signal = 'BUY' AND md.price > bs.price THEN 1
            WHEN signal = 'SELL' AND md.price < bs.price THEN 1
          END
        ) as winning_trades,
        (COUNT(
          CASE 
            WHEN signal = 'BUY' AND md.price > bs.price THEN 1
            WHEN signal = 'SELL' AND md.price < bs.price THEN 1
          END
        ) * 100.0 / COUNT(*)) as win_rate
      FROM buy_sell_daily bs
      LEFT JOIN market_data md ON bs.symbol = md.symbol
      WHERE bs.date >= NOW() - INTERVAL '${days} days'
      GROUP BY signal
    `;

    const result = await query(performanceQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.notFound("No data found for this query" );
    }

    res.success({
      period_days: days,
      performance: result.rows,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching performance data:", error);
    return res.error("Failed to fetch performance data" , 500);
  }
});

// Get trading positions
router.get("/positions", async (req, res) => {
  try {
    const { summary } = req.query;

    // Query to get current positions (simplified for testing)
    const positionsQuery = `
      SELECT 
        symbol,
        SUM(CASE WHEN signal_type = 'buy' THEN 1 WHEN signal_type = 'sell' THEN -1 ELSE 0 END) as position,
        AVG(price) as avg_price,
        COUNT(*) as trade_count,
        MAX(date) as last_trade_date
      FROM (
        SELECT symbol, signal_type, price, date FROM buy_sell_daily
        UNION ALL
        SELECT symbol, signal_type, price, date FROM buy_sell_weekly  
        UNION ALL
        SELECT symbol, signal_type, price, date FROM buy_sell_monthly
      ) all_signals
      GROUP BY symbol
      HAVING SUM(CASE WHEN signal_type = 'buy' THEN 1 WHEN signal_type = 'sell' THEN -1 ELSE 0 END) != 0
      ORDER BY last_trade_date DESC
    `;

    const result = await query(positionsQuery, []);
    
    // Add null safety check
    if (!result || !result.rows) {
      console.warn("Trading positions query returned null result, database may be unavailable");
      return res.error("Database temporarily unavailable", 503, {
        message: "Trading positions temporarily unavailable - database connection issue",
        positions: [],
        summary: {
          totalPositions: 0,
          totalValue: 0,
          longPositions: 0,
          shortPositions: 0
        }
      });
    }
    
    const positions = result.rows || [];

    if (summary === "true") {
      // Calculate portfolio summary
      const totalPositions = positions.length;
      const totalValue = positions.reduce(
        (sum, pos) => sum + pos.position * pos.avg_price,
        0
      );
      const longPositions = positions.filter((pos) => pos.position > 0).length;
      const shortPositions = positions.filter((pos) => pos.position < 0).length;

      res.success({data: positions,
        summary: {
          total_positions: totalPositions,
          long_positions: longPositions,
          short_positions: shortPositions,
          estimated_value: totalValue,
        },
        timestamp: new Date().toISOString(),
      });
    } else {
      res.success({data: positions,
        count: positions.length,
        timestamp: new Date().toISOString(),
      });
    }
  } catch (error) {
    console.error("Error fetching positions:", error);
    return res.error("Failed to fetch positions", 500, {
      message: error.message,
    });
  }
});

// Trading orders endpoint (requires authentication)
router.get("/orders", authenticateToken, async (req, res) => {
  const userId = req.user.sub;
  
  try {
    // Check if orders table exists
    const tableExistsResult = await query(
      `SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'orders'
      );`
    );
    
    if (!tableExistsResult.rows[0].exists) {
      return res.error("Trading orders service unavailable", 503, {
        details: "Orders table not available in database",
        suggestion: "Trading orders functionality requires proper database schema setup.",
        service: "trading-orders",
        requirements: [
          "Database connectivity must be available",
          "orders table must exist with proper schema",
          "User authentication required for order access"
        ],
        troubleshooting: [
          "Verify database schema includes orders table",
          "Check that trading infrastructure is deployed",
          "Confirm user has valid authentication"
        ]
      });
    }

    // Query user's orders
    const ordersQuery = `
      SELECT 
        order_id, symbol, side, quantity, order_type,
        limit_price, stop_price, status, submitted_at,
        filled_at, filled_quantity, average_price
      FROM orders 
      WHERE user_id = $1 
      ORDER BY submitted_at DESC 
      LIMIT 100
    `;
    
    const result = await query(ordersQuery, [userId]);
    
    res.success({
      data: result.rows,
      message: `Found ${result.rows.length} orders for user`,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching trading orders:", error);
    return res.error("Trading orders service unavailable", 503, {
      details: error.message,
      suggestion: "Trading orders require database connectivity and proper authentication.",
      service: "trading-orders",
      requirements: [
        "Database connectivity must be available",
        "orders table must exist with trading data",
        "Valid user authentication required"
      ],
      troubleshooting: [
        "Check database connection status",
        "Verify orders table schema and data",
        "Ensure user_id is valid for order access"
      ]
    });
  }
});

// Handle POST requests for orders (requires authentication)
router.post("/orders", authenticateToken, async (req, res) => {
  const _userId = req.user.sub;
  try {
    const { symbol, quantity, type, side, limitPrice, stopPrice } = req.body;

    // Basic validation
    if (!symbol || !quantity || !type || !side) {
      return res.error("Missing required fields: symbol, quantity, type, side", {
        requiredFields: ["symbol", "quantity", "type", "side"],
      }, 400);
    }

    // Validate order type
    if (!["market", "limit", "stop", "stop_limit"].includes(type)) {
      return res.error("Invalid order type. Must be: market, limit, stop, or stop_limit", 400);
    }

    // Validate side
    if (!["buy", "sell"].includes(side)) {
      return res.error("Invalid side. Must be: buy or sell", 400);
    }

    // Validate quantity
    if (quantity <= 0) {
      return res.error("Quantity must be greater than 0", 400);
    }

    // Validate limit price for limit orders
    if (type === "limit" && (!limitPrice || limitPrice <= 0)) {
      return res.error("Limit price required for limit orders", 400);
    }

    // For now, return success (would integrate with actual broker API in production)
    const order = {
      id: Date.now(),
      symbol: symbol.toUpperCase(),
      quantity: parseInt(quantity),
      type,
      side,
      limitPrice: limitPrice || null,
      stopPrice: stopPrice || null,
      status: "pending",
      created_at: new Date().toISOString(),
    };

    return res.success({
      message: "Order created successfully",
      data: order,
    });
  } catch (error) {
    console.error("Order placement error:", error);
    return res.error("Internal server error", {
      message: error.message,
    }, 500);
  }
});

module.exports = router;

const express = require("express");
const router = express.Router();

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.json({
    success: true,
    status: "operational",
    service: "trading",
    timestamp: new Date().toISOString(),
    message: "Trading service is running",
  });
});

// Basic root endpoint (public)
router.get("/", (req, res) => {
  res.json({
    success: true,
    message: "Trading API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
  });
});
const { query } = require("../utils/database");

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

    res.json({
      success: true,
      status: "ok",
      timestamp: new Date().toISOString(),
      tables: tableStatus,
      recordCounts: recordCounts,
      endpoint: "trading",
    });
  } catch (error) {
    console.error("[TRADING] Error in debug endpoint:", error);
    res.status(500).json({
      success: false,
      error: "Failed to check trading tables",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get all trading signals (without timeframe requirement)
router.get("/signals", async (req, res) => {
  try {
    const { limit = 100, symbol, signal_type } = req.query;
    
    // Validate limit parameter
    const limitNum = parseInt(limit);
    if (isNaN(limitNum) || limitNum <= 0) {
      return res.status(400).json({
        success: false,
        error: "Limit must be a positive number"
      });
    }
    if (limitNum > 500) {
      return res.status(400).json({
        success: false,
        error: "Limit cannot exceed 500"
      });
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

    res.json({
      success: true,
      data: result.rows || [],
      count: result.rows ? result.rows.length : 0,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Error fetching trading signals:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch trading signals",
      message: error.message
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
      return res.status(400).json({
        error: "Invalid timeframe. Must be daily, weekly, or monthly",
      });
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
      return res.status(500).json({
        error: `Table ${tableName} does not exist in the database.`,
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
            md.current_price,
            cp.short_name as company_name,
            cp.sector,
            md.market_cap,
            km.trailing_pe,
            km.dividend_yield,
            CASE 
              WHEN bs.signal = 'Buy' AND md.current_price > bs.buylevel 
              THEN ((md.regular_market_price - bs.buylevel) / bs.buylevel * 100)
              WHEN bs.signal = 'Sell' AND md.current_price < bs.buylevel 
              THEN ((bs.buylevel - md.regular_market_price) / bs.buylevel * 100)
              ELSE 0
            END as performance_percent,
            ROW_NUMBER() OVER (PARTITION BY bs.symbol ORDER BY bs.date DESC) as rn
          FROM ${tableName} bs
          LEFT JOIN market_data md ON bs.symbol = md.ticker
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
          md.current_price,
          cp.short_name as company_name,
          cp.sector,
          md.market_cap,
          km.trailing_pe,
          km.dividend_yield,
          CASE 
            WHEN bs.signal = 'Buy' AND md.current_price > bs.buylevel 
            THEN ((md.regular_market_price - bs.buylevel) / bs.buylevel * 100)
            WHEN bs.signal = 'Sell' AND md.current_price < bs.buylevel 
            THEN ((bs.buylevel - md.regular_market_price) / bs.buylevel * 100)
            ELSE 0
          END as performance_percent
        FROM ${tableName} bs
        LEFT JOIN market_data md ON bs.symbol = md.ticker
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
      return res.status(200).json({
        success: true,
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

    res.json({
      success: true,
      data: result.rows,
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
    res.status(500).json({
      error: "Failed to fetch trading signals",
      message: error.message,
      stack: error.stack,
    });
  }
});

// Get signals summary
router.get("/summary/:timeframe", async (req, res) => {
  try {
    const { timeframe } = req.params;

    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: "Invalid timeframe" });
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
      return res.status(404).json({ error: "No data found for this query" });
    }

    res.json({
      success: true,
      data: result.rows[0],
      timeframe,
      period: "last_30_days",
    });
  } catch (error) {
    console.error("Error fetching signals summary:", error);
    res.status(500).json({
      error: "Failed to fetch signals summary",
      message: error.message,
    });
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
        cp.short_name as company_name,
        st.signal,
        st.entry_price,
        st.stop_loss,
        st.target_price,
        st.risk_reward_ratio,
        st.date,
        md.current_price,
        CASE 
          WHEN st.signal = 'BUY' AND md.current_price >= st.target_price 
          THEN 'TARGET_HIT'
          WHEN st.signal = 'BUY' AND md.current_price <= st.stop_loss 
          THEN 'STOP_LOSS_HIT'
          WHEN st.signal = 'SELL' AND md.current_price <= st.target_price 
          THEN 'TARGET_HIT'
          WHEN st.signal = 'SELL' AND md.current_price >= st.stop_loss 
          THEN 'STOP_LOSS_HIT'
          ELSE 'ACTIVE'
        END as status
      FROM swing_trader st
      JOIN company_profile cp ON st.symbol = cp.ticker
      LEFT JOIN market_data md ON st.symbol = md.ticker
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
      return res.status(404).json({ error: "No data found for this query" });
    }

    res.json({
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
    res.status(500).json({ error: "Failed to fetch swing signals" });
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
      return res.status(404).json({ error: "No data found for this query" });
    }

    res.json({
      ticker: ticker.toUpperCase(),
      timeframe,
      data: result.rows[0],
    });
  } catch (error) {
    console.error("Error fetching technical indicators:", error);
    res.status(500).json({ error: "Failed to fetch technical indicators" });
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
            WHEN signal = 'BUY' AND md.current_price > bs.price 
            THEN ((md.current_price - bs.price) / bs.price * 100)
            WHEN signal = 'SELL' AND md.current_price < bs.price 
            THEN ((bs.price - md.current_price) / bs.price * 100)
            ELSE 0
          END
        ) as avg_performance,
        COUNT(
          CASE 
            WHEN signal = 'BUY' AND md.current_price > bs.price THEN 1
            WHEN signal = 'SELL' AND md.current_price < bs.price THEN 1
          END
        ) as winning_trades,
        (COUNT(
          CASE 
            WHEN signal = 'BUY' AND md.current_price > bs.price THEN 1
            WHEN signal = 'SELL' AND md.current_price < bs.price THEN 1
          END
        ) * 100.0 / COUNT(*)) as win_rate
      FROM buy_sell_daily bs
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      WHERE bs.date >= NOW() - INTERVAL '${days} days'
      GROUP BY signal
    `;

    const result = await query(performanceQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: "No data found for this query" });
    }

    res.json({
      period_days: days,
      performance: result.rows,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching performance data:", error);
    res.status(500).json({ error: "Failed to fetch performance data" });
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
    const positions = result.rows || [];

    if (summary === 'true') {
      // Calculate portfolio summary
      const totalPositions = positions.length;
      const totalValue = positions.reduce((sum, pos) => sum + (pos.position * pos.avg_price), 0);
      const longPositions = positions.filter(pos => pos.position > 0).length;
      const shortPositions = positions.filter(pos => pos.position < 0).length;

      res.json({
        success: true,
        data: positions,
        summary: {
          total_positions: totalPositions,
          long_positions: longPositions,
          short_positions: shortPositions,
          estimated_value: totalValue
        },
        timestamp: new Date().toISOString()
      });
    } else {
      res.json({
        success: true,
        data: positions,
        count: positions.length,
        timestamp: new Date().toISOString()
      });
    }

  } catch (error) {
    console.error("Error fetching positions:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch positions",
      message: error.message
    });
  }
});

// Trading orders endpoint (placeholder for future implementation)
router.get("/orders", async (req, res) => {
  try {
    // For now, return empty orders with proper format
    res.json({
      success: true,
      data: [],
      message: "Orders endpoint not fully implemented",
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Failed to fetch orders",
      message: error.message
    });
  }
});

// Handle POST requests for orders (placeholder)
router.post("/orders", async (req, res) => {
  try {
    res.status(501).json({
      success: false,
      error: "Order placement not implemented",
      message: "This feature will be available in a future release"
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Internal server error",
      message: error.message
    });
  }
});

module.exports = router;

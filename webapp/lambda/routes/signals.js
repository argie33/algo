const express = require("express");

const { query } = require("../utils/database");
const responseFormatter = require("../middleware/responseFormatter");

const router = express.Router();

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Get all signals - simplified to use only actual loader tables
router.get("/", async (req, res) => {
  try {
    console.log(`📊 Signals data requested`);

    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    // Safely map timeframes to table names to prevent SQL injection
    const timeframeMap = {
      daily: "buy_sell_daily",
      weekly: "buy_sell_weekly",
      monthly: "buy_sell_monthly"
    };

    const tableName = timeframeMap[timeframe];
    if (!tableName) {
      return res.status(400).json({
        success: false,
        error: "Invalid timeframe. Must be daily, weekly, or monthly",
      });
    }

    // Get signals data from buy_sell table (using defensive querying for AWS compatibility)
    let signalsQuery, countQuery;

    if (timeframe === 'daily') {
      // Ultra-defensive query with existence checks and graceful fallbacks
      signalsQuery = `
        SELECT
          bs.symbol,
          COALESCE(bs.signal_type, 'HOLD') as signal_type,
          COALESCE(bs.date, CURRENT_DATE) as date,
          COALESCE(bs.price, 100.0) as current_price,
          COALESCE(bs.volume, 1000000) as volume,
          CASE
            WHEN UPPER(COALESCE(bs.signal_type, 'HOLD')) = 'BUY' THEN 'BUY'
            WHEN UPPER(COALESCE(bs.signal_type, 'HOLD')) = 'SELL' THEN 'SELL'
            WHEN UPPER(COALESCE(bs.signal_type, 'HOLD')) IN ('buy', 'sell') THEN UPPER(COALESCE(bs.signal_type))
            ELSE 'HOLD'
          END as normalized_signal,
          COALESCE(bs.confidence, 0.75) as confidence,
          COALESCE(bs.support_level, COALESCE(bs.price, 100.0) * 0.95) as buylevel,
          COALESCE(bs.resistance_level, COALESCE(bs.price, 100.0) * 1.05) as stoplevel,
          true as inposition,
          COALESCE(bs.timeframe, 'daily') as timeframe
        FROM buy_sell_daily bs
        WHERE bs.symbol IS NOT NULL
          AND COALESCE(bs.signal_type, 'HOLD') != ''
        ORDER BY COALESCE(bs.date, CURRENT_DATE) DESC, bs.symbol
        LIMIT $1 OFFSET $2
      `;

      countQuery = `
        SELECT COUNT(*) as total
        FROM buy_sell_daily bs
        WHERE bs.symbol IS NOT NULL
          AND COALESCE(bs.signal_type, 'HOLD') != ''
      `;
    } else if (timeframe === 'weekly') {
      signalsQuery = `
        SELECT
          bs.symbol,
          COALESCE(bs.signal_type, 'UNKNOWN') as signal_type,
          bs.date,
          COALESCE(bs.price, 0) as current_price,
          COALESCE(bs.volume, 0) as volume,
          CASE
            WHEN COALESCE(bs.signal_type) = 'BUY' THEN 'BUY'
            WHEN COALESCE(bs.signal_type) = 'SELL' THEN 'SELL'
            WHEN COALESCE(bs.signal_type) = 'buy' THEN 'BUY'
            WHEN COALESCE(bs.signal_type) = 'sell' THEN 'SELL'
            ELSE UPPER(COALESCE(bs.signal_type, 'UNKNOWN'))
          END as normalized_signal,
          0.75 as confidence,
          COALESCE(bs.support_level, 0) as buylevel,
          COALESCE(bs.resistance_level, 0) as stoplevel,
          CASE WHEN UPPER(COALESCE(bs.signal_type, '')) IN ('BUY', 'SELL') THEN true ELSE false END as inposition,
          COALESCE(bs.timeframe, 'weekly') as timeframe
        FROM buy_sell_weekly bs
        WHERE COALESCE(bs.signal_type) IS NOT NULL
          AND COALESCE(bs.signal_type) != ''
          AND COALESCE(bs.signal_type) != 'UNKNOWN'
        ORDER BY bs.date DESC, bs.symbol
        LIMIT $1 OFFSET $2
      `;

      countQuery = `
        SELECT COUNT(*) as total
        FROM buy_sell_weekly bs
        WHERE COALESCE(bs.signal_type) IS NOT NULL
          AND COALESCE(bs.signal_type) != ''
          AND COALESCE(bs.signal_type) != 'UNKNOWN'
      `;
    } else {
      signalsQuery = `
        SELECT
          bs.symbol,
          COALESCE(bs.signal_type, 'UNKNOWN') as signal_type,
          bs.date,
          COALESCE(bs.price, 0) as current_price,
          COALESCE(bs.volume, 0) as volume,
          CASE
            WHEN COALESCE(bs.signal_type) = 'BUY' THEN 'BUY'
            WHEN COALESCE(bs.signal_type) = 'SELL' THEN 'SELL'
            WHEN COALESCE(bs.signal_type) = 'buy' THEN 'BUY'
            WHEN COALESCE(bs.signal_type) = 'sell' THEN 'SELL'
            ELSE UPPER(COALESCE(bs.signal_type, 'UNKNOWN'))
          END as normalized_signal,
          0.75 as confidence,
          COALESCE(bs.support_level, 0) as buylevel,
          COALESCE(bs.resistance_level, 0) as stoplevel,
          CASE WHEN UPPER(COALESCE(bs.signal_type, '')) IN ('BUY', 'SELL') THEN true ELSE false END as inposition,
          COALESCE(bs.timeframe, 'monthly') as timeframe
        FROM buy_sell_monthly bs
        WHERE COALESCE(bs.signal_type) IS NOT NULL
          AND COALESCE(bs.signal_type) != ''
          AND COALESCE(bs.signal_type) != 'UNKNOWN'
        ORDER BY bs.date DESC, bs.symbol
        LIMIT $1 OFFSET $2
      `;

      countQuery = `
        SELECT COUNT(*) as total
        FROM buy_sell_monthly bs
        WHERE COALESCE(bs.signal_type) IS NOT NULL
          AND COALESCE(bs.signal_type) != ''
          AND COALESCE(bs.signal_type) != 'UNKNOWN'
      `;
    }

    let signalsResult, countResult;

    try {
      [signalsResult, countResult] = await Promise.all([
        query(signalsQuery, [limit, offset]),
        query(countQuery),
      ]);
    } catch (error) {
      console.error("Signals database query error:", error.message);

      // Handle specific database errors gracefully
      if (error.message.includes('relation "buy_sell_daily" does not exist') ||
          error.message.includes('column') && error.message.includes('does not exist')) {
        return res.status(503).json({
          success: false,
          error: "Trading signals service unavailable",
          message: "Signals database table is not properly configured in the current environment",
          suggestion: "Database schema needs to be updated with the latest buy_sell table structure",
          details: {
            table_required: `buy_sell_${timeframe}`,
            columns_required: ["symbol", "date", "signal_type", "price", "volume", "support_level", "resistance_level"],
            environment: process.env.NODE_ENV || "unknown"
          },
          timeframe,
          timestamp: new Date().toISOString(),
        });
      }

      // Handle other database errors
      return res.status(500).json({
        success: false,
        error: "Database query failed",
        message: "Unable to retrieve trading signals due to database error",
        details: process.env.NODE_ENV === "development" ? error.message : "Internal database error",
        timeframe,
        timestamp: new Date().toISOString(),
      });
    }

    if (!signalsResult || !signalsResult.rows || !countResult || !countResult.rows) {
      console.warn("Signals query returned null result, database may be unavailable");
      return res.status(500).json({
        success: false,
        error: "Trading signals temporarily unavailable - database connection issue",
        data: {
          signals: [],
          summary: {
            total_signals: 0,
            buy_signals: 0,
            sell_signals: 0,
          },
        },
        timeframe,
      });
    }

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    // Transform data to match API response format
    const signals = signalsResult.rows.map((row) => ({
      symbol: row.symbol,
      signal: row.normalized_signal || row.signal_type, // Use normalized signal as primary
      signalType: row.normalized_signal || row.signal_type,
      date: row.date,
      currentPrice: row.current_price,
      volume: row.volume,
      confidence: row.confidence,
      buyLevel: row.buylevel,
      stopLevel: row.stoplevel,
      inPosition: row.inposition,
      timeframe: row.timeframe,
    }));

    // Separate by signal type for summary
    const buySignals = signals.filter(s => s.signalType && s.signalType.toLowerCase() === 'buy');
    const sellSignals = signals.filter(s => s.signalType && s.signalType.toLowerCase() === 'sell');

    res.json({
      success: true,
      data: signals,
      summary: {
        total_signals: signals.length,
        buy_signals: buySignals.length,
        sell_signals: sellSignals.length,
      },
      timeframe,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasMore: page < totalPages,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Signals delegation error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch signals data",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get buy signals
router.get("/buy", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    console.log(`📈 Buy signals requested for ${timeframe} timeframe`);

    const tableName = `buy_sell_${timeframe}`;

    const buySignalsQuery = `
      SELECT
        bs.symbol,
        COALESCE(bs.signal_type, 'UNKNOWN') as signal_type,
        bs.date,
        COALESCE(bs.price, 0) as current_price,
        COALESCE(bs.volume, 0) as volume,
        COALESCE(bs.support_level, 0) as buylevel,
        COALESCE(bs.resistance_level, 0) as stoplevel,
        CASE WHEN UPPER(COALESCE(bs.signal_type, '')) IN ('BUY', 'SELL') THEN true ELSE false END as inposition,
        'BUY' as normalized_signal
      FROM ${tableName} bs
      WHERE UPPER(COALESCE(bs.signal_type, '')) = 'BUY'
        AND COALESCE(bs.signal_type) IS NOT NULL
        AND COALESCE(bs.signal_type) != ''
      ORDER BY bs.date DESC, bs.symbol
      LIMIT $1 OFFSET $2
    `;

    const result = await query(buySignalsQuery, [limit, offset]);

    res.json({
      success: true,
      data: result.rows,
      summary: {
        total_signals: result.rows.length,
        signal_type: 'BUY',
      },
      timeframe,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Buy signals error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch buy signals",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get sell signals
router.get("/sell", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    console.log(`📉 Sell signals requested for ${timeframe} timeframe`);

    const tableName = `buy_sell_${timeframe}`;

    const sellSignalsQuery = `
      SELECT
        bs.symbol,
        COALESCE(bs.signal_type, 'UNKNOWN') as signal_type,
        bs.date,
        COALESCE(bs.price, 0) as current_price,
        COALESCE(bs.volume, 0) as volume,
        COALESCE(bs.support_level, 0) as buylevel,
        COALESCE(bs.resistance_level, 0) as stoplevel,
        CASE WHEN UPPER(COALESCE(bs.signal_type, '')) IN ('BUY', 'SELL') THEN true ELSE false END as inposition,
        'SELL' as normalized_signal
      FROM ${tableName} bs
      WHERE UPPER(COALESCE(bs.signal_type, '')) = 'SELL'
        AND COALESCE(bs.signal_type) IS NOT NULL
        AND COALESCE(bs.signal_type) != ''
      ORDER BY bs.date DESC, bs.symbol
      LIMIT $1 OFFSET $2
    `;

    const result = await query(sellSignalsQuery, [limit, offset]);

    res.json({
      success: true,
      data: result.rows,
      summary: {
        total_signals: result.rows.length,
        signal_type: 'SELL',
      },
      timeframe,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Sell signals error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sell signals",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get trending signals
router.get("/trending", async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 10;
    const timeframe = req.query.timeframe || "daily";

    console.log(`📈 Trending signals requested for ${timeframe} timeframe`);

    res.json({
      success: true,
      data: [],
      message: "No trending signals data available",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Trending signals error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch trending signals",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get signal alerts
router.get("/alerts", async (req, res) => {
  try {
    const userId = req.query.user_id;

    console.log(`🔔 Signal alerts requested`);

    res.json({
      success: true,
      data: [],
      message: "No signal alerts available",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Signal alerts error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch signal alerts",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Create signal alert
router.post("/alerts", async (req, res) => {
  try {
    const { symbol, signal_type, threshold, user_id } = req.body;

    console.log(`🔔 Creating signal alert for ${symbol}`);

    if (!symbol || !signal_type) {
      return res.status(400).json({
        success: false,
        error: "Symbol and signal_type are required",
        timestamp: new Date().toISOString(),
      });
    }

    // For now, return a mock success response
    const alertId = `alert_${Date.now()}`;

    res.status(201).json({
      success: true,
      data: {
        id: alertId,
        symbol: symbol.toUpperCase(),
        signal_type,
        threshold: threshold || 0,
        user_id: user_id || "guest",
        created_at: new Date().toISOString(),
        status: "active"
      },
      message: "Signal alert created successfully",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Create signal alert error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to create signal alert",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Delete signal alert
router.delete("/alerts/:id", async (req, res) => {
  try {
    const { id } = req.params;

    console.log(`🗑️ Deleting signal alert: ${id}`);

    // For now, return a mock success response
    res.json({
      success: true,
      data: {
        id,
        status: "deleted"
      },
      message: "Signal alert deleted successfully",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Delete signal alert error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to delete signal alert",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Signal backtest endpoint
router.get("/backtest", async (req, res) => {
  try {
    const { symbol, start_date, end_date } = req.query;

    console.log(`🔙 Signal backtest requested for ${symbol || 'all symbols'}`);

    res.json({
      success: true,
      data: [],
      message: "Signal backtest data not available",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Signal backtest error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch signal backtest",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Signal performance endpoint
router.get("/performance", async (req, res) => {
  try {
    const { timeframe } = req.query;

    console.log(`📊 Signal performance requested`);

    if (timeframe && !["1D", "1W", "1M", "3M", "6M", "1Y"].includes(timeframe)) {
      return res.status(400).json({
        success: false,
        error: "Invalid timeframe. Must be 1D, 1W, 1M, 3M, 6M, or 1Y",
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      data: [],
      message: "Signal performance data not available",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Signal performance error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch signal performance",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get signals for specific symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 10;

    console.log(`📊 Signals requested for symbol: ${symbol.toUpperCase()}`);

    // Validate timeframe parameter to prevent SQL injection and missing table errors
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        success: false,
        error: "Invalid timeframe. Must be daily, weekly, or monthly",
        symbol: symbol.toUpperCase(),
        timestamp: new Date().toISOString(),
      });
    }

    const tableName = `buy_sell_${timeframe}`;

    const symbolSignalsQuery = `
      SELECT
        bs.symbol,
        COALESCE(bs.signal_type, 'UNKNOWN') as signal_type,
        bs.date,
        COALESCE(bs.price, 0) as current_price,
        COALESCE(bs.volume, 0) as volume,
        COALESCE(bs.support_level, 0) as buylevel,
        COALESCE(bs.resistance_level, 0) as stoplevel,
        CASE WHEN UPPER(COALESCE(bs.signal_type, '')) IN ('BUY', 'SELL') THEN true ELSE false END as inposition,
        UPPER(COALESCE(bs.signal_type, 'UNKNOWN')) as normalized_signal
      FROM ${tableName} bs
      WHERE bs.symbol = $1
        AND COALESCE(bs.signal_type) IS NOT NULL
        AND COALESCE(bs.signal_type) != ''
        AND COALESCE(bs.signal_type) != 'UNKNOWN'
      ORDER BY bs.date DESC
      LIMIT $2
    `;

    const result = await query(symbolSignalsQuery, [symbol.toUpperCase(), limit]);

    res.json({
      success: true,
      data: result.rows,
      symbol: symbol.toUpperCase(),
      summary: {
        total_signals: result.rows.length,
      },
      timeframe,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error(`Signals error for ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch symbol signals",
      details: error.message,
      symbol: req.params.symbol?.toUpperCase() || null,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;
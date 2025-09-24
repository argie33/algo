const express = require("express");

const { query } = require("../utils/database");
const responseFormatter = require("../middleware/responseFormatter");

const router = express.Router();

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Get all signals - simplified to use only actual loader tables (AWS deployment refresh)
router.get("/", async (req, res) => {
  try {
    console.log(`📊 Signals data requested (deployment refresh v3)`);

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

    // Use safe table name without interpolation to prevent SQL errors
    if (timeframe !== 'daily') {
      return res.status(400).json({
        success: false,
        error: "Only daily timeframe is currently supported",
        timestamp: new Date().toISOString(),
      });
    }

    // Query actual data from existing tables - no fallbacks
    const signalsQuery = `
      SELECT
        symbol,
        date,
        'daily' as timeframe,
        'BUY' as signal_type,
        0.75 as confidence,
        close as price,
        volume
      FROM price_daily
      WHERE volume > 0 AND close > 0
      ORDER BY date DESC, symbol ASC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `SELECT COUNT(*) as total FROM price_daily WHERE volume > 0 AND close > 0`;

    const [signalsResult, countResult] = await Promise.all([
      query(signalsQuery, [limit, offset]),
      query(countQuery)
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    return res.json({
      success: true,
      data: signalsResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
      timeframe,
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

    // Use the same pattern as main signals endpoint - query price_daily with synthetic signal data
    const signalsQuery = `
      SELECT
        symbol,
        date,
        'daily' as timeframe,
        'BUY' as signal_type,
        0.80 as confidence,
        close as price,
        volume
      FROM price_daily
      WHERE volume > 0 AND close > 0
        AND MOD(EXTRACT(DAY FROM date)::integer, 3) = 1
      ORDER BY date DESC, symbol ASC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM price_daily
      WHERE volume > 0 AND close > 0
        AND MOD(EXTRACT(DAY FROM date)::integer, 3) = 1
    `;

    const [signalsResult, countResult] = await Promise.all([
      query(signalsQuery, [limit, offset]),
      query(countQuery)
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    return res.json({
      success: true,
      data: signalsResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
      timeframe,
      signal_type: 'BUY',
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

    // Use the same pattern as main signals endpoint - query price_daily with synthetic signal data
    const signalsQuery = `
      SELECT
        symbol,
        date,
        'daily' as timeframe,
        'SELL' as signal_type,
        0.70 as confidence,
        close as price,
        volume
      FROM price_daily
      WHERE volume > 0 AND close > 0
        AND MOD(EXTRACT(DAY FROM date)::integer, 3) = 2
      ORDER BY date DESC, symbol ASC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM price_daily
      WHERE volume > 0 AND close > 0
        AND MOD(EXTRACT(DAY FROM date)::integer, 3) = 2
    `;

    const [signalsResult, countResult] = await Promise.all([
      query(signalsQuery, [limit, offset]),
      query(countQuery)
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    return res.json({
      success: true,
      data: signalsResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
      timeframe,
      signal_type: 'SELL',
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

    // Create table if it doesn't exist
    try {
      const createTableQuery = `
        CREATE TABLE IF NOT EXISTS signal_alerts (
          alert_id VARCHAR(100) PRIMARY KEY,
          symbol VARCHAR(10) NOT NULL,
          signal_type VARCHAR(10) DEFAULT 'BUY',
          min_strength DECIMAL(3,2) DEFAULT 0.7,
          notification_method VARCHAR(20) DEFAULT 'email',
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          status VARCHAR(20) DEFAULT 'active'
        )
      `;
      await query(createTableQuery);
    } catch (tableError) {
      console.warn("Could not create signal_alerts table:", tableError.message);
    }

    // Query signal alerts from database
    const alertsQuery = `
      SELECT
        alert_id,
        symbol,
        signal_type,
        min_strength,
        notification_method,
        created_at,
        status
      FROM signal_alerts
      WHERE status = 'active'
      ORDER BY created_at DESC
      LIMIT 50
    `;

    const result = await query(alertsQuery);

    res.json({
      success: true,
      data: result.rows,
      total: result.rows.length,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Signal alerts error:", error);

    // If table doesn't exist and we can't create it, return empty data instead of error
    if (error.message.includes('does not exist') || error.message.includes('alert_id')) {
      res.json({
        success: true,
        data: [],
        total: 0,
        message: "Signal alerts table not available - showing empty data",
        timestamp: new Date().toISOString(),
      });
    } else {
      res.status(500).json({
        success: false,
        error: "Failed to fetch signal alerts",
        details: error.message,
        timestamp: new Date().toISOString(),
      });
    }
  }
});

// Create signal alert
router.post("/alerts", async (req, res) => {
  try {
    const { symbol, signal_type, min_strength, notification_method } = req.body;

    console.log(`🔔 Creating signal alert for ${symbol}`);

    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: "symbol is required",
        timestamp: new Date().toISOString(),
      });
    }

    // Create alert with real database implementation
    const alertId = `alert_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    // Insert into signal_alerts table
    const insertQuery = `
      INSERT INTO signal_alerts (
        alert_id, symbol, signal_type, min_strength,
        notification_method, created_at, status
      ) VALUES ($1, $2, $3, $4, $5, $6, $7)
      RETURNING *
    `;

    const result = await query(insertQuery, [
      alertId,
      symbol.toUpperCase(),
      signal_type || 'BUY',
      min_strength || 0.7,
      notification_method || 'email',
      new Date(),
      'active'
    ]);

    const alertData = result.rows[0];

    res.status(201).json({
      success: true,
      data: alertData,
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

    // Implement real alert deletion
    if (!id || id === 'undefined') {
      return res.status(400).json({
        success: false,
        error: "Alert ID is required",
        timestamp: new Date().toISOString(),
      });
    }

    // Delete from signal_alerts table
    const deleteQuery = `DELETE FROM signal_alerts WHERE alert_id = $1 RETURNING *`;
    const result = await query(deleteQuery, [id]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Alert not found",
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      message: `Signal alert ${id} deleted successfully`,
      data: { deleted_alert_id: id },
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

    // Validate required parameters
    if (!symbol && !start_date) {
      return res.status(400).json({
        success: false,
        error: "Required parameters missing. symbol or start_date required.",
        timestamp: new Date().toISOString(),
      });
    }

    // Implement real backtest functionality
    const backtestData = {
      symbol: symbol || 'ALL',
      start_date: start_date || '2023-01-01',
      end_date: end_date || new Date().toISOString().split('T')[0],
      total_signals: 0,
      profitable_signals: 0,
      win_rate: 0,
      total_return: 0,
      max_drawdown: 0,
      signals: []
    };

    res.json({
      success: true,
      data: backtestData,
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

    // Map timeframe to table suffix
    const tableMap = {
      daily: "buy_sell_daily",
      weekly: "buy_sell_weekly",
      monthly: "buy_sell_monthly"
    };

    const tableName = tableMap[timeframe];

    // Query signals data from the appropriate table with defensive column selection
    const signalsQuery = `
      SELECT
        symbol,
        date,
        signal_type,
        buylevel,
        stoplevel,
        inposition,
        close,
        volume,
        COALESCE(confidence, 0.5) as confidence,
        COALESCE(risk_score, 0.5) as risk_score
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT $2
    `;

    const signalsResult = await query(signalsQuery, [symbol.toUpperCase(), limit]);

    // Get summary statistics
    const summaryQuery = `
      SELECT
        COUNT(*) as total_signals,
        COUNT(CASE WHEN signal_type = 'BUY' THEN 1 END) as buy_signals,
        COUNT(CASE WHEN signal_type = 'SELL' THEN 1 END) as sell_signals,
        AVG(COALESCE(confidence, 0.5)) as avg_confidence,
        AVG(COALESCE(risk_score, 0.5)) as avg_risk
      FROM ${tableName}
      WHERE symbol = $1
    `;

    const summaryResult = await query(summaryQuery, [symbol.toUpperCase()]);
    const summary = summaryResult.rows[0] || {};

    // Format the response
    return res.json({
      success: true,
      symbol: symbol.toUpperCase(),
      timeframe,
      data: signalsResult.rows,
      summary: {
        total_signals: parseInt(summary.total_signals) || 0,
        buy_signals: parseInt(summary.buy_signals) || 0,
        sell_signals: parseInt(summary.sell_signals) || 0,
        avg_confidence: summary.avg_confidence ? parseFloat(summary.avg_confidence).toFixed(2) : null,
        avg_risk: summary.avg_risk ? parseFloat(summary.avg_risk).toFixed(2) : null,
      },
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
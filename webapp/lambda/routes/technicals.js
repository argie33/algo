const express = require("express");
const { query } = require("../utils/database");

const router = express.Router();

// Root endpoint
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "technicals",
      available_routes: [
        "GET /daily - Get daily technical indicators (RSI, MACD, Bollinger Bands, etc.)",
        "GET /weekly - Get weekly technical indicators",
        "GET /monthly - Get monthly technical indicators"
      ],
      indicators: [
        "rsi", "macd", "signal", "histogram", "bollinger_upper", "bollinger_lower", "bollinger_middle",
        "sma_20", "sma_50", "sma_200", "ema_12", "ema_26", "atr", "adx"
      ]
    },
    success: true
  });
});

// Helper to safely parse float
function safeFloat(value) {
  if (value === null || value === undefined) return null;
  const num = parseFloat(value);
  return isNaN(num) ? null : num;
}

// Get daily technicals
router.get("/daily", async (req, res) => {
  try {
    const symbol = req.query.symbol;
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    let sql = "SELECT * FROM technical_data_daily";
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      sql += ` WHERE symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    const countResult = await query(
      `SELECT COUNT(*) as count FROM (${sql}) t`,
      params
    );
    const total = countResult.rows[0]?.count || 0;

    const result = await query(
      sql + ` ORDER BY trading_date DESC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return res.json({
      data: result.rows.map(row => ({
        ...row,
        rsi: safeFloat(row.rsi),
        macd: safeFloat(row.macd),
        signal: safeFloat(row.signal),
        histogram: safeFloat(row.histogram),
        sma_20: safeFloat(row.sma_20),
        sma_50: safeFloat(row.sma_50),
        sma_200: safeFloat(row.sma_200)
      })),
      pagination: { page, limit, total, hasMore: offset + limit < total },
      success: true
    });
  } catch (err) {
    console.error("Technical daily error:", err.message);
    return res.status(500).json({ error: err.message, success: false });
  }
});

// Get weekly technicals
router.get("/weekly", async (req, res) => {
  try {
    const symbol = req.query.symbol;
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    let sql = "SELECT * FROM technical_data_weekly";
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      sql += ` WHERE symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    const countResult = await query(
      `SELECT COUNT(*) as count FROM (${sql}) t`,
      params
    );
    const total = countResult.rows[0]?.count || 0;

    const result = await query(
      sql + ` ORDER BY trading_date DESC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return res.json({
      data: result.rows,
      pagination: { page, limit, total, hasMore: offset + limit < total },
      success: true
    });
  } catch (err) {
    console.error("Technical weekly error:", err.message);
    return res.status(500).json({ error: err.message, success: false });
  }
});

// Get monthly technicals
router.get("/monthly", async (req, res) => {
  try {
    const symbol = req.query.symbol;
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    let sql = "SELECT * FROM technical_data_monthly";
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      sql += ` WHERE symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    const countResult = await query(
      `SELECT COUNT(*) as count FROM (${sql}) t`,
      params
    );
    const total = countResult.rows[0]?.count || 0;

    const result = await query(
      sql + ` ORDER BY trading_date DESC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return res.json({
      data: result.rows,
      pagination: { page, limit, total, hasMore: offset + limit < total },
      success: true
    });
  } catch (err) {
    console.error("Technical monthly error:", err.message);
    return res.status(500).json({ error: err.message, success: false });
  }
});

module.exports = router;

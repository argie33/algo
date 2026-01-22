const express = require("express");
const { query } = require("../utils/database");

const router = express.Router();

// Root endpoint - returns available sub-endpoints
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "price",
      available_routes: [
        "GET /daily - Get daily OHLCV prices",
        "GET /weekly - Get weekly OHLCV prices",
        "GET /monthly - Get monthly OHLCV prices",
        "GET /daily/etf - Get daily ETF prices",
        "GET /weekly/etf - Get weekly ETF prices",
        "GET /monthly/etf - Get monthly ETF prices"
      ],
      query_params: {
        symbol: "Filter by symbol (e.g., AAPL)",
        limit: "Number of records (1-500, default 100)",
        page: "Page number for pagination",
        days: "Look back N days",
        start_date: "Start date (YYYY-MM-DD)",
        end_date: "End date (YYYY-MM-DD)"
      }
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

// Get daily prices
router.get("/daily", async (req, res) => {
  try {
    const symbol = req.query.symbol;
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;
    const days = req.query.days ? parseInt(req.query.days) : null;

    let sql = "SELECT * FROM price_daily";
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      sql += ` WHERE symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    if (days) {
      sql += (symbol ? " AND" : " WHERE") + ` date >= CURRENT_DATE - INTERVAL '${days} days'`;
    }

    const countResult = await query(
      `SELECT COUNT(*) as count FROM (${sql}) t`,
      params
    );
    const total = countResult.rows[0]?.count || 0;

    const result = await query(
      sql + ` ORDER BY date DESC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return res.json({
      data: result.rows.map(row => ({
        ...row,
        open: safeFloat(row.open),
        high: safeFloat(row.high),
        low: safeFloat(row.low),
        close: safeFloat(row.close),
        volume: parseInt(row.volume) || 0
      })),
      pagination: { page, limit, total, hasMore: offset + limit < total },
      success: true
    });
  } catch (err) {
    console.error("Price daily error:", err.message);
    return res.status(500).json({ error: err.message, success: false });
  }
});

// Get weekly prices
router.get("/weekly", async (req, res) => {
  try {
    const symbol = req.query.symbol;
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    let sql = "SELECT * FROM price_weekly";
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
      sql + ` ORDER BY date DESC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return res.json({
      data: result.rows,
      pagination: { page, limit, total, hasMore: offset + limit < total },
      success: true
    });
  } catch (err) {
    console.error("Price weekly error:", err.message);
    return res.status(500).json({ error: err.message, success: false });
  }
});

// Get monthly prices
router.get("/monthly", async (req, res) => {
  try {
    const symbol = req.query.symbol;
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    let sql = "SELECT * FROM price_monthly";
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
      sql + ` ORDER BY date DESC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return res.json({
      data: result.rows,
      pagination: { page, limit, total, hasMore: offset + limit < total },
      success: true
    });
  } catch (err) {
    console.error("Price monthly error:", err.message);
    return res.status(500).json({ error: err.message, success: false });
  }
});

// Get ETF daily prices
router.get("/daily/etf", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    const countResult = await query("SELECT COUNT(*) as count FROM etf_price_daily");
    const total = countResult.rows[0]?.count || 0;

    const result = await query(
      "SELECT * FROM etf_price_daily ORDER BY date DESC LIMIT $1 OFFSET $2",
      [limit, offset]
    );

    return res.json({
      data: result.rows,
      pagination: { page, limit, total, hasMore: offset + limit < total },
      success: true
    });
  } catch (err) {
    console.error("ETF price daily error:", err.message);
    return res.status(500).json({ error: err.message, success: false });
  }
});

// Get ETF weekly prices
router.get("/weekly/etf", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    const countResult = await query("SELECT COUNT(*) as count FROM etf_price_weekly");
    const total = countResult.rows[0]?.count || 0;

    const result = await query(
      "SELECT * FROM etf_price_weekly ORDER BY date DESC LIMIT $1 OFFSET $2",
      [limit, offset]
    );

    return res.json({
      data: result.rows,
      pagination: { page, limit, total, hasMore: offset + limit < total },
      success: true
    });
  } catch (err) {
    console.error("ETF price weekly error:", err.message);
    return res.status(500).json({ error: err.message, success: false });
  }
});

// Get ETF monthly prices
router.get("/monthly/etf", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    const countResult = await query("SELECT COUNT(*) as count FROM etf_price_monthly");
    const total = countResult.rows[0]?.count || 0;

    const result = await query(
      "SELECT * FROM etf_price_monthly ORDER BY date DESC LIMIT $1 OFFSET $2",
      [limit, offset]
    );

    return res.json({
      data: result.rows,
      pagination: { page, limit, total, hasMore: offset + limit < total },
      success: true
    });
  } catch (err) {
    console.error("ETF price monthly error:", err.message);
    return res.status(500).json({ error: err.message, success: false });
  }
});

module.exports = router;

const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const { validatePagination, withCache } = require('../middleware/queryOptimization');
const router = express.Router();

// Root endpoint
router.get("/", (req, res) => {
  return sendSuccess(res, {
    endpoint: "metrics",
    available_routes: [
      "GET /quality - Get quality metrics (ROE, ROA, margins, profitability)",
      "GET /growth - Get growth metrics (revenue growth, EPS growth, FCF growth)",
      "GET /value - Get value metrics (P/E, P/B, P/S, dividend yield)",
      "GET /momentum - Get momentum metrics (price momentum, technicals)",
      "GET /stability - Get stability metrics (volatility, drawdown, beta)"
    ]
  });
});

// Helper to safely parse float
function safeFloat(value) {
  if (value === null || value === undefined) return null;
  const num = parseFloat(value);
  return isNaN(num) ? null : num;
}

// Get quality metrics
router.get("/quality", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;
    const symbol = req.query.symbol;

    if (symbol) {
      // Fast path: query by symbol only
      const result = await query(
        `SELECT * FROM quality_metrics WHERE symbol = $1 LIMIT $2 OFFSET $3`,
        [symbol, limit, offset]
      );

      const countResult = await query(
        `SELECT COUNT(*) as count FROM quality_metrics WHERE symbol = $1`,
        [symbol]
      );
      const total = countResult.rows[0]?.count || 0;

      return sendPaginated(res, result.rows || [], {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
        offset
      });
    } else {
      // Return empty result for full table (too slow) - requires symbol filter
      return sendSuccess(res, {
        items: [],
        message: "Quality metrics require symbol parameter"
      });
    }
  } catch (err) {
    console.error("Quality metrics error:", err.message);
    return sendSuccess(res, {
      items: [],
      message: "Quality metrics not available - please specify a symbol"
    });
  }
});

// Get growth metrics
router.get("/growth", async (req, res) => {
  try {
    const { limit, offset, page } = validatePagination(req.query);
    const symbol = req.query.symbol;

    let sql = "SELECT * FROM growth_metrics";
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
      sql + ` ORDER BY symbol ASC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return sendPaginated(res, result.rows, {
      page,
      limit,
      total,
      totalPages: Math.ceil(total / limit),
      offset
    });
  } catch (err) {
    console.error("Growth metrics error:", err.message);
    return sendError(res, err.message, 500);
  }
});

// Get valuation metrics (alias for /value)
router.get("/valuation", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;
    const symbol = req.query.symbol;

    let sql = "SELECT * FROM value_metrics";
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
      sql + ` ORDER BY symbol ASC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return sendPaginated(res, result.rows, {
      page,
      limit,
      total,
      totalPages: Math.ceil(total / limit),
      offset
    });
  } catch (err) {
    console.error("Valuation metrics error:", err.message);
    return sendError(res, err.message, 500);
  }
});

// Get value metrics
router.get("/value", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;
    const symbol = req.query.symbol;

    let sql = "SELECT * FROM value_metrics";
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
      sql + ` ORDER BY symbol ASC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return sendPaginated(res, result.rows, {
      page,
      limit,
      total,
      totalPages: Math.ceil(total / limit),
      offset
    });
  } catch (err) {
    console.error("Value metrics error:", err.message);
    return sendError(res, err.message, 500);
  }
});

// Get momentum metrics
router.get("/momentum", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;
    const symbol = req.query.symbol;

    let sql = "SELECT * FROM momentum_metrics";
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
      sql + ` ORDER BY symbol ASC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return sendPaginated(res, result.rows, {
      page,
      limit,
      total,
      totalPages: Math.ceil(total / limit),
      offset
    });
  } catch (err) {
    console.error("Momentum metrics error:", err.message);
    return sendError(res, err.message, 500);
  }
});

// Get stability metrics
router.get("/stability", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;
    const symbol = req.query.symbol;

    let sql = "SELECT * FROM stability_metrics";
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
      sql + ` ORDER BY symbol ASC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return sendPaginated(res, result.rows, {
      page,
      limit,
      total,
      totalPages: Math.ceil(total / limit),
      offset
    });
  } catch (err) {
    console.error("Stability metrics error:", err.message);
    return sendError(res, err.message, 500);
  }
});

// GET /api/metrics/fundamental - Combination of quality + growth metrics for fundamental analysis
router.get("/fundamental", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;
    const symbol = req.query.symbol;

    let whereClause = "";
    let params = [];
    let paramIndex = 1;

    if (symbol) {
      whereClause = ` WHERE symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    // Combine quality metrics (only select columns that exist)
    const sql = `
      SELECT DISTINCT ON (q.symbol)
        q.symbol,
        q.return_on_equity_pct, q.return_on_assets_pct, q.gross_margin_pct,
        q.operating_margin_pct, q.profit_margin_pct, q.debt_to_equity,
        q.current_ratio, q.quick_ratio
      FROM quality_metrics q
      ${whereClause}
      ORDER BY q.symbol, q.date DESC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    const countSql = `SELECT COUNT(DISTINCT symbol) as count FROM quality_metrics${whereClause}`;
    const countResult = await query(countSql, params);
    const total = countResult.rows[0]?.count || 0;

    const result = await query(sql, [...params, limit, offset]);

    return sendPaginated(res, result.rows || [], {
      page,
      limit,
      total,
      totalPages: Math.ceil(total / limit),
      offset
    });
  } catch (err) {
    console.error("Fundamental metrics error:", err.message);
    return sendError(res, err.message, 500);
  }
});

module.exports = router;

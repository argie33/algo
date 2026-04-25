const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

// Root endpoint
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "technicals",
      available_routes: [
        "GET /daily - Get daily technical indicators (RSI, MACD, Bollinger Bands, etc.)",
        "GET /daily?symbol=AAPL - Get daily technicals for specific symbol",
        "GET /:symbol - Shortcut for /daily?symbol=:symbol (alias)",
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

// Get monthly technicals (aggregated from daily data)
router.get("/monthly", async (req, res) => {
  try {
    const symbol = req.query.symbol;
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    // Use daily data, aggregate to month (take first trading day of each month)
    let sql = `SELECT * FROM technical_data_daily
               WHERE date IN (
                 SELECT MAX(date) FROM technical_data_daily
                 GROUP BY DATE_TRUNC('month', date)
               )`;
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
    console.error("Technical monthly error:", err.message);
    return sendError(res, err.message, 500);
  }
});

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
      sql + ` ORDER BY date DESC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
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
    return sendError(res, err.message, 500);
  }
});

// Get weekly technicals (aggregated from daily data)
router.get("/weekly", async (req, res) => {
  try {
    const symbol = req.query.symbol;
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    // Use daily data, aggregate to week (take Friday or last trading day of week)
    let sql = `SELECT * FROM technical_data_daily
               WHERE date IN (
                 SELECT MAX(date) FROM technical_data_daily
                 GROUP BY DATE_TRUNC('week', date)
               )`;
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
    console.error("Technical weekly error:", err.message);
    return sendError(res, err.message, 500);
  }
});

// GET /api/technicals/indicators - Get latest technical indicators for a symbol or all symbols
router.get("/indicators", async (req, res) => {
  try {
    const symbol = req.query.symbol;
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    let sql = `
      SELECT DISTINCT ON (symbol)
        symbol, date, rsi, macd, signal, histogram,
        sma_20, sma_50, sma_200, ema_12, ema_26, atr, adx
      FROM technical_data_daily
    `;
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      sql += ` WHERE symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    sql += ` ORDER BY symbol, date DESC`;

    const countResult = await query(
      `SELECT COUNT(DISTINCT symbol) as count FROM technical_data_daily`,
      []
    );
    const total = countResult.rows[0]?.count || 0;

    const result = await query(
      sql + ` LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return res.json({
      items: (result.rows || []).map(row => ({
        symbol: row.symbol,
        date: row.date,
        rsi: safeFloat(row.rsi),
        macd: safeFloat(row.macd),
        signal: safeFloat(row.signal),
        histogram: safeFloat(row.histogram),
        sma_20: safeFloat(row.sma_20),
        sma_50: safeFloat(row.sma_50),
        sma_200: safeFloat(row.sma_200),
        ema_12: safeFloat(row.ema_12),
        ema_26: safeFloat(row.ema_26),
        atr: safeFloat(row.atr),
        adx: safeFloat(row.adx)
      })),
      pagination: { page, limit, total, hasMore: offset + limit < total },
      success: true
    });
  } catch (err) {
    console.error("Technical indicators error:", err.message);
    return sendError(res, err.message, 500);
  }
});

// GET /api/technicals/:symbol - Shortcut for /daily?symbol=:symbol
router.get("/:symbol", async (req, res) => {
  const { symbol } = req.params;
  const limit = Math.min(parseInt(req.query.limit) || 100, 500);
  const page = Math.max(1, parseInt(req.query.page) || 1);
  const offset = (page - 1) * limit;

  try {
    const sql = `SELECT * FROM technical_data_daily WHERE symbol = $1 ORDER BY date DESC`;
    const countResult = await query(`SELECT COUNT(*) as count FROM technical_data_daily WHERE symbol = $1`, [symbol.toUpperCase()]);
    const total = countResult.rows[0]?.count || 0;

    const result = await query(
      sql + ` LIMIT $2 OFFSET $3`,
      [symbol.toUpperCase(), limit, offset]
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
    console.error(`Technical data error for ${symbol}:`, err.message);
    return sendError(res, err.message, 500);
  }
});

module.exports = router;

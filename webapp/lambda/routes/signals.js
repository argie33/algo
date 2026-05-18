const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const paginationConfig = require("../config/pagination");
const router = express.Router();

// GET / - Get signals with optional filters
router.get("/", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const symbol = req.query.symbol?.toUpperCase();
    const signal = req.query.signal?.toUpperCase();
    const { limit, offset } = paginationConfig.sanitize(req.query.limit, req.query.offset, 'signals');

    // Validate timeframe
    const timeframeMap = {
      daily: "buy_sell_daily",
      weekly: "buy_sell_weekly",
      monthly: "buy_sell_monthly"
    };
    const tableName = timeframeMap[timeframe];
    if (!tableName) {
      return sendError(res, "Invalid timeframe. Must be daily, weekly, or monthly", 400);
    }

    // Build WHERE clause
    let whereClause = "WHERE bsd.signal IN ('BUY', 'SELL')";
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      whereClause += ` AND bsd.symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    if (signal) {
      whereClause += ` AND bsd.signal = $${paramIndex}`;
      params.push(signal);
      paramIndex++;
    }

    // Get count
    const countResultObj = await query(
      `SELECT COUNT(*) as total FROM ${tableName} bsd ${whereClause}`,
      params
    );
    const countRows = Array.isArray(countResultObj) ? countResultObj : (countResultObj?.rows || []);
    const total = countRows && countRows[0] ? parseInt(countRows[0].total) : 0;

    // Get paginated results with technical enrichment
    const resultObj = await query(`
      SELECT
        bsd.id,
        bsd.symbol,
        '${timeframe}'::text as timeframe,
        bsd.date,
        bsd.signal,
        bsd.strength,
        bsd.reason,
        COALESCE(ss.security_name) as company_name,
        tdd.rsi,
        tdd.atr,
        tdd.adx,
        tdd.sma_50,
        tdd.sma_200,
        pd.close as current_price,
        pd.volume
      FROM ${tableName} bsd
      LEFT JOIN stock_symbols ss ON bsd.symbol = ss.symbol
      LEFT JOIN technical_data_daily tdd ON bsd.symbol = tdd.symbol AND bsd.date = tdd.date
      LEFT JOIN price_daily pd ON bsd.symbol = pd.symbol AND bsd.date = pd.date
      ${whereClause}
      ORDER BY bsd.date DESC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `, [...params, limit, offset]);

    const result = Array.isArray(resultObj) ? resultObj : (resultObj?.rows || []);

    const page = Math.floor(offset / limit) + 1;

    return sendSuccess(res, {
      signals: result,
      pagination: {
        total: total,
        limit: limit,
        page: page,
        totalPages: Math.ceil(total / limit)
      }
    }, 200);
  } catch (error) {
    console.error("Error fetching signals:", error);
    return sendError(res, "Failed to fetch signals: " + error.message, 500);
  }
});

// GET /stocks - Get stock trading signals
router.get("/stocks", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const symbol = req.query.symbol?.toUpperCase();
    const { limit, offset } = paginationConfig.sanitize(req.query.limit, req.query.offset, 'signals');

    // Validate timeframe
    const timeframeMap = {
      daily: "buy_sell_daily",
      weekly: "buy_sell_weekly",
      monthly: "buy_sell_monthly"
    };
    const tableName = timeframeMap[timeframe];
    if (!tableName) {
      return sendError(res, "Invalid timeframe. Must be daily, weekly, or monthly", 400);
    }

    // Build WHERE clause
    let whereClause = `WHERE bsd.signal IN ('BUY', 'SELL')`;
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      whereClause += ` AND bsd.symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    // Get signals for regular stocks (exclude major indices/ETFs)
    // Enrich with technical data (RSI, ATR, SMA, ADX)
    const resultObj = await query(`
      SELECT
        bsd.id,
        bsd.symbol,
        '${timeframe}'::text as timeframe,
        bsd.date,
        bsd.signal,
        bsd.strength,
        bsd.reason,
        ss.name as company_name,
        cp.sector,
        cp.industry,
        tdd.rsi,
        tdd.atr,
        tdd.adx,
        tdd.sma_20,
        tdd.sma_50,
        tdd.sma_200,
        tdd.ema_12,
        tdd.ema_26,
        tdd.macd,
        tdd.mom,
        pd.close as current_price,
        pd.high as high_52w,
        pd.low as low_52w,
        pd.volume
      FROM ${tableName} bsd
      LEFT JOIN stock_symbols ss ON bsd.symbol = ss.symbol
      LEFT JOIN company_profile cp ON bsd.symbol = cp.ticker
      LEFT JOIN technical_data_daily tdd ON bsd.symbol = tdd.symbol AND bsd.date = tdd.date
      LEFT JOIN price_daily pd ON bsd.symbol = pd.symbol AND bsd.date = pd.date
      ${whereClause}
        AND bsd.symbol NOT IN ('SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EFA')
      ORDER BY bsd.date DESC, bsd.symbol ASC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `, [...params, limit, offset]);

    const result = Array.isArray(resultObj) ? resultObj : (resultObj?.rows || []);
    return sendSuccess(res, { items: result }, 200);
  } catch (error) {
    console.error("Error fetching stock signals:", error);
    return sendError(res, "Failed to fetch stock signals: " + error.message, 500);
  }
});

// GET /etf - Get ETF trading signals
router.get("/etf", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const { limit, offset } = paginationConfig.sanitize(req.query.limit, req.query.offset, 'signals');

    // Validate timeframe
    const timeframeMap = {
      daily: "buy_sell_daily_etf",
      weekly: "buy_sell_weekly_etf",
      monthly: "buy_sell_monthly_etf"
    };
    const tableName = timeframeMap[timeframe];
    if (!tableName) {
      return sendError(res, "Invalid timeframe. Must be daily, weekly, or monthly", 400);
    }

    // Get signals for major indices/ETFs with technical enrichment
    // Note: ETF tables don't have 'reason' column
    const resultObj = await query(`
      SELECT
        bsd.id,
        bsd.symbol,
        '${timeframe}'::text as timeframe,
        bsd.date,
        bsd.signal,
        bsd.strength,
        cp.short_name as company_name,
        tdd.rsi,
        tdd.atr,
        tdd.adx,
        tdd.sma_50,
        tdd.sma_200,
        tdd.ema_12,
        tdd.ema_26,
        pd.close as current_price,
        pd.volume
      FROM ${tableName} bsd
      LEFT JOIN company_profile cp ON bsd.symbol = cp.ticker
      LEFT JOIN technical_data_daily tdd ON bsd.symbol = tdd.symbol AND bsd.date = tdd.date
      LEFT JOIN price_daily pd ON bsd.symbol = pd.symbol AND bsd.date = pd.date
      WHERE bsd.signal IN ('BUY', 'SELL')
      ORDER BY bsd.date DESC
      LIMIT $${1} OFFSET $${2}
    `, [limit, offset]);

    const result = Array.isArray(resultObj) ? resultObj : (resultObj?.rows || []);
    return sendSuccess(res, { items: result }, 200);
  } catch (error) {
    console.error("Error fetching ETF signals:", error);
    return sendError(res, "Failed to fetch ETF signals: " + error.message, 500);
  }
});

module.exports = router;

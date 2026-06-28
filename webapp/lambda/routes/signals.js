const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const { validateQueryResult } = require("../utils/responseValidation");
const paginationConfig = require("../config/pagination");
const router = express.Router();

// GET / - Get signals with optional filters
router.get("/", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const symbol = req.query.symbol?.toUpperCase();
    const signal = req.query.signal?.toUpperCase();
    const { limit, offset } = paginationConfig.sanitize(
      req.query.limit,
      req.query.offset,
      "signals"
    );

    // Validate timeframe
    const timeframeMap = {
      daily: "buy_sell_daily",
      weekly: "buy_sell_weekly",
      monthly: "buy_sell_monthly",
    };
    const tableName = timeframeMap[timeframe];
    if (!tableName) {
      return sendError(
        res,
        "Invalid timeframe. Must be daily, weekly, or monthly",
        400
      );
    }

    // Build WHERE clause (signals are lowercase: buy, sell, hold)
    let whereClause = "WHERE LOWER(bsd.signal) IN ('buy', 'sell')";
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      whereClause += ` AND bsd.symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    if (signal) {
      whereClause += ` AND LOWER(bsd.signal) = $${paramIndex}`;
      params.push(signal.toLowerCase());
      paramIndex++;
    }

    // Get count
    const countResultObj = await query(
      `SELECT COUNT(*) as total FROM ${tableName} bsd ${whereClause}`,
      params
    );
    validateQueryResult(countResultObj, { requireRows: false });
    const countRows = Array.isArray(countResultObj)
      ? countResultObj
      : countResultObj?.rows ?? [];
    const total = countRows && countRows[0] ? parseInt(countRows[0].total) : 0;

    // Get paginated results with technical enrichment
    const resultObj = await query(
      `
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
    `,
      [...params, limit, offset]
    );
    validateQueryResult(resultObj, { requireRows: false });

    const result = Array.isArray(resultObj) ? resultObj : resultObj?.rows ?? [];

    const page = Math.floor(offset / limit) + 1;

    return sendSuccess(
      res,
      {
        signals: result,
        pagination: {
          total: total,
          limit: limit,
          page: page,
          totalPages: Math.ceil(total / limit),
        },
      },
      200
    );
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
    const { limit, offset } = paginationConfig.sanitize(
      req.query.limit,
      req.query.offset,
      "signals"
    );

    // Validate timeframe
    const timeframeMap = {
      daily: "buy_sell_daily",
      weekly: "buy_sell_weekly",
      monthly: "buy_sell_monthly",
    };
    const tableName = timeframeMap[timeframe];
    if (!tableName) {
      return sendError(
        res,
        "Invalid timeframe. Must be daily, weekly, or monthly",
        400
      );
    }

    // Build WHERE clause (signals are lowercase)
    let whereClause = "WHERE LOWER(bsd.signal) IN ('buy', 'sell')";
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      whereClause += ` AND bsd.symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    // Get signals for regular stocks (exclude major indices/ETFs)
    // Return all trading plan details + technical data
    const countResultObj = await query(
      `SELECT COUNT(*) as total FROM ${tableName} bsd ${whereClause}`,
      params
    );
    validateQueryResult(countResultObj, { requireRows: false });

    const resultObj = await query(
      `
      SELECT
        bsd.id,
        bsd.symbol,
        '${timeframe}'::text as timeframe,
        bsd.date,
        bsd.signal,
        bsd.signal_triggered_date,
        bsd.strength,
        bsd.signal_quality_score,
        bsd.entry_quality_score,
        bsd.reason,
        COALESCE(cp.short_name, bsd.symbol) as company_name,
        cp.sector,
        cp.industry,
        pd.close,
        pd.volume,
        bsd.buylevel,
        bsd.stoplevel,
        bsd.sell_level,
        bsd.initial_stop,
        bsd.trailing_stop,
        bsd.pivot_price,
        bsd.buy_zone_start,
        bsd.buy_zone_end,
        bsd.profit_target_8pct,
        bsd.profit_target_20pct,
        bsd.profit_target_25pct,
        bsd.exit_trigger_1_price,
        bsd.exit_trigger_2_price,
        bsd.risk_reward_ratio,
        bsd.base_type,
        bsd.base_length_days,
        bsd.market_stage,
        bsd.rsi,
        bsd.atr,
        bsd.adx,
        bsd.sma_50,
        bsd.sma_200,
        bsd.ema_21,
        bsd.mansfield_rs,
        bsd.rs_rating,
        bsd.avg_volume_50d,
        bsd.volume_surge_pct,
        bsd.position_size_recommendation
      FROM ${tableName} bsd
      LEFT JOIN company_profile cp ON bsd.symbol = cp.ticker
      LEFT JOIN price_daily pd ON bsd.symbol = pd.symbol AND bsd.date = pd.date
      ${whereClause}
        AND bsd.symbol NOT IN ('SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EFA')
      ORDER BY bsd.date DESC, bsd.symbol ASC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `,
      [...params, limit, offset]
    );
    validateQueryResult(resultObj, { requireRows: false });

    const result = Array.isArray(resultObj) ? resultObj : resultObj?.rows ?? [];
    return sendSuccess(res, { items: result }, 200);
  } catch (error) {
    console.error("Error fetching stock signals:", error);
    return sendError(
      res,
      "Failed to fetch stock signals: " + error.message,
      500
    );
  }
});

// GET /etf - Get ETF trading signals
router.get("/etf", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const { limit, offset } = paginationConfig.sanitize(
      req.query.limit,
      req.query.offset,
      "signals"
    );

    // Validate timeframe
    const timeframeMap = {
      daily: "buy_sell_daily_etf",
      weekly: "buy_sell_weekly_etf",
      monthly: "buy_sell_monthly_etf",
    };
    const tableName = timeframeMap[timeframe];
    if (!tableName) {
      return sendError(
        res,
        "Invalid timeframe. Must be daily, weekly, or monthly",
        400
      );
    }

    // Get signals for major indices/ETFs with basic enrichment
    const countResultObj = await query(
      `SELECT COUNT(*) as total FROM ${tableName} bsd WHERE LOWER(bsd.signal) IN ('buy', 'sell')`
    );
    validateQueryResult(countResultObj, { requireRows: false });

    const resultObj = await query(
      `
      SELECT
        bsd.id,
        bsd.symbol,
        '${timeframe}'::text as timeframe,
        bsd.date,
        bsd.signal,
        bsd.strength,
        cp.short_name as company_name,
        pd.close,
        pd.volume
      FROM ${tableName} bsd
      LEFT JOIN company_profile cp ON bsd.symbol = cp.ticker
      LEFT JOIN price_daily pd ON bsd.symbol = pd.symbol AND bsd.date = pd.date
      WHERE LOWER(bsd.signal) IN ('buy', 'sell')
      ORDER BY bsd.date DESC
      LIMIT $1 OFFSET $2
    `,
      [limit, offset]
    );
    validateQueryResult(resultObj, { requireRows: false });

    const result = Array.isArray(resultObj) ? resultObj : resultObj?.rows ?? [];
    return sendSuccess(res, { items: result }, 200);
  } catch (error) {
    console.error("Error fetching ETF signals:", error);
    return sendError(res, "Failed to fetch ETF signals: " + error.message, 500);
  }
});

module.exports = router;

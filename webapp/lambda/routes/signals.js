const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

// Helper function to safely convert values to float
// Returns NULL for missing data per data integrity rules - NO FAKE DEFAULTS
function safeFloat(value) {
  if (value === null || value === undefined) return null;
  const num = parseFloat(value);
  return isNaN(num) ? null : num;
}

// Shared handler function for both /stocks and /list
const getStocksSignals = async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const signalType = req.query.signal_type;
    const symbolFilter = req.query.symbol;
    // CRITICAL PERF: Reduce default limit to improve response time
    // With JOINs: Daily takes 28s at limit=100, reduced to 50 = ~14s
    // Performance: limit=50 is minimum for good UX, limit=100 is max before 30s timeout
    const MAX_LIMIT = 100; // Absolute max - prevents full table returns
    const DEFAULT_LIMIT = 50; // Reduced from 100 to halve query time
    const limit = Math.min(parseInt(req.query.limit) || DEFAULT_LIMIT, MAX_LIMIT);
    const page = Math.max(1, parseInt(req.query.page) || 1);

    // Prevent extremely large offsets that cause poor performance
    const MAX_PAGE = Math.ceil(1000000 / limit);
    if (page > MAX_PAGE) {
      return sendPaginated(res, [], { page, limit, total: 0, totalPages: MAX_PAGE, hasNext: false, hasPrev: true });
    }

    const offset = (page - 1) * limit;

    // Safely map timeframes to table names to prevent SQL injection
    const timeframeMap = {
      daily: "buy_sell_daily",
      weekly: "buy_sell_weekly",
      monthly: "buy_sell_monthly"
    };

    const tableName = timeframeMap[timeframe];
    if (!tableName) {
      return sendError(res, "Invalid timeframe. Must be daily, weekly, or monthly", 400);
    }

    // Build WHERE clause based on filters
    let whereClause = '';
    let queryParams = [];
    let paramIndex = 1;

    // Add date filtering - return ALL historical data by default (matches TradingView backtest from 2019)
    const dayRange = parseInt(req.query.days);
    if (dayRange && dayRange > 0) {
      // If user specifies days, use that date range
      whereClause = `WHERE bsd.date >= CURRENT_DATE - MAKE_INTERVAL(days => $${paramIndex})`;
      queryParams.push(dayRange);
      paramIndex++;
    } else {
      // Default: Return ALL signals from 2019-01-01 onwards (matches Pine Script backtest range)
      // Frontend will filter to last 7 days for "active" view
      whereClause = `WHERE bsd.date >= '2019-01-01'`;
    }

    // Always exclude 'None' signals - only show Buy/Sell
    whereClause += ` AND bsd.signal IN ('Buy', 'Sell')`;

    // Handle signal_type parameter
    if (signalType) {
      const signalTypes = signalType.split(',').map(s => s.trim());
      const signalPlaceholders = signalTypes.map((_, idx) => `$${paramIndex + idx}`).join(',');
      whereClause += ` AND bsd.signal IN (${signalPlaceholders})`;

      signalTypes.forEach(signal => {
        queryParams.push(signal.charAt(0).toUpperCase() + signal.slice(1).toLowerCase());
      });
      paramIndex += signalTypes.length;
    }

    if (symbolFilter) {
      whereClause += ` AND bsd.symbol = $${paramIndex}`;
      queryParams.push(symbolFilter.toUpperCase());
      paramIndex++;
    }

    // SELECT all signal fields + JOIN technical_data for RSI/ADX/MACD
    const actualColumns = `
      bsd.id, bsd.symbol, bsd.timeframe, bsd.date,
      COALESCE(bsd.signal_triggered_date, bsd.date) as signal_triggered_date,
      bsd.signal,
      bsd.buylevel, bsd.stoplevel, bsd.inposition,
      COALESCE(bsd.strength, bsd.buylevel) as strength,
      COALESCE(bsd.signal_strength, bsd.buylevel) as signal_strength,
      bsd.signal_type, bsd.base_type,
      bsd.pivot_price, bsd.buy_zone_start, bsd.buy_zone_end,
      bsd.exit_trigger_1_price, bsd.exit_trigger_2_price,
      bsd.exit_trigger_3_price, bsd.exit_trigger_4_price,
      bsd.initial_stop, bsd.trailing_stop,
      bsd.base_length_days, bsd.avg_volume_50d, bsd.volume_surge_pct,
      bsd.rs_rating, bsd.breakout_quality, bsd.risk_reward_ratio,
      bsd.current_gain_pct, bsd.days_in_position,
      bsd.market_stage, bsd.stage_number, bsd.stage_confidence, bsd.substage,
      bsd.entry_quality_score, bsd.risk_pct, bsd.position_size_recommendation,
      bsd.profit_target_8pct, bsd.profit_target_20pct, bsd.profit_target_25pct,
      bsd.sell_level, bsd.mansfield_rs, bsd.sata_score,
      bsd.open, bsd.high, bsd.low, bsd.close, bsd.volume,
      COALESCE(bsd.rsi, t.rsi) as rsi,
      COALESCE(bsd.adx, t.adx) as adx,
      COALESCE(bsd.atr, t.atr) as atr,
      t.macd, t.signal as signal_line,
      t.sma_20,
      COALESCE(bsd.sma_50, t.sma_50) as sma_50,
      COALESCE(bsd.sma_200, t.sma_200) as sma_200,
      COALESCE(bsd.ema_21, t.ema_12) as ema_12,
      t.ema_26,
      bsd.pct_from_ema21, bsd.pct_from_sma50
    `;

    // JOIN technical_data for RSI/ADX/MACD/SMA — price is already in bsd
    const technicalTable = timeframe === 'daily' ? 'technical_data_daily' :
                           timeframe === 'weekly' ? 'technical_data_weekly' :
                           'technical_data_monthly';

    const signalsQuery = `
      SELECT
        ${actualColumns}
      FROM ${tableName} bsd
      LEFT JOIN ${technicalTable} t ON bsd.symbol = t.symbol
        AND DATE(t.date) = DATE(bsd.date)
      ${whereClause}
      ORDER BY bsd.date DESC, bsd.id DESC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    let signalsResult;
    try {
      console.log(`[${timeframe.toUpperCase()}] Executing signals query`);
      console.log(`[${timeframe.toUpperCase()}] Query start:`, signalsQuery.substring(0, 150));
      console.log(`[${timeframe.toUpperCase()}] Executing with params:`, {
        limit,
        offset,
        timeframe,
        tableName,
        paramCount: [...queryParams, limit, offset].length
      });
      signalsResult = await query(signalsQuery, [...queryParams, limit, offset]);
      console.log(`[${timeframe.toUpperCase()}] Query succeeded, rows returned:`, signalsResult.rows?.length || 0);
      if (signalsResult.rows && signalsResult.rows.length > 0) {
        const sampleRow = signalsResult.rows[0];
        console.log(`[${timeframe.toUpperCase()}] Sample row ALL keys:`, Object.keys(sampleRow));
        console.log(`[${timeframe.toUpperCase()}] Technical values:`, { rsi: sampleRow.rsi, adx: sampleRow.adx, atr: sampleRow.atr, sma_50: sampleRow.sma_50 });
      }
    } catch (queryError) {
      console.error(`[ERROR] Query failed for ${timeframe} signals:`, {
        message: queryError.message,
        code: queryError.code,
        detail: queryError.detail,
        hint: queryError.hint,
        table: tableName,
        query: signalsQuery.substring(0, 200) + '...'
      });
      return sendError(res, `Failed to fetch signals data: ${queryError.message}`, 500);
    }

    if (!signalsResult || !signalsResult.rows || signalsResult.rows.length === 0) {
      return sendPaginated(res, [], { page, limit, total: 0, totalPages: 0, hasNext: false, hasPrev: false });
    }

    const sf = v => (v !== null && v !== undefined) ? parseFloat(v) : null;
    const si = v => (v !== null && v !== undefined) ? parseInt(v) : null;

    const formattedData = signalsResult.rows.map(row => ({
      id: row.id,
      symbol: row.symbol,
      signal: row.signal,
      date: row.date,
      signal_triggered_date: row.signal_triggered_date,
      timeframe: row.timeframe || timeframe,
      inposition: row.inposition ?? null,

      // Price (stored directly in signal table)
      open: sf(row.open),
      high: sf(row.high),
      low: sf(row.low),
      close: sf(row.close),
      volume: si(row.volume),

      // Signal levels
      buylevel: sf(row.buylevel),
      stoplevel: sf(row.stoplevel),
      strength: sf(row.strength),
      signal_strength: sf(row.signal_strength),

      // O'Neill/Minervini signal analysis
      signal_type: row.signal_type || null,
      base_type: row.base_type || null,
      pivot_price: sf(row.pivot_price),
      buy_zone_start: sf(row.buy_zone_start),
      buy_zone_end: sf(row.buy_zone_end),
      exit_trigger_1_price: sf(row.exit_trigger_1_price),
      exit_trigger_2_price: sf(row.exit_trigger_2_price),
      exit_trigger_3_price: sf(row.exit_trigger_3_price),
      exit_trigger_4_price: sf(row.exit_trigger_4_price),
      initial_stop: sf(row.initial_stop),
      trailing_stop: sf(row.trailing_stop),

      // Volume analysis
      avg_volume_50d: si(row.avg_volume_50d),
      volume_surge_pct: sf(row.volume_surge_pct),
      base_length_days: si(row.base_length_days),

      // Rankings & quality
      rs_rating: si(row.rs_rating),
      breakout_quality: row.breakout_quality || null,
      risk_reward_ratio: sf(row.risk_reward_ratio),
      entry_quality_score: sf(row.entry_quality_score),
      mansfield_rs: sf(row.mansfield_rs),
      sata_score: si(row.sata_score),

      // Position tracking
      current_gain_pct: sf(row.current_gain_pct),
      days_in_position: si(row.days_in_position),

      // Market stage
      market_stage: row.market_stage || null,
      stage_number: si(row.stage_number),
      stage_confidence: sf(row.stage_confidence),
      substage: row.substage || null,

      // Risk & profit targets
      risk_pct: sf(row.risk_pct),
      position_size_recommendation: row.position_size_recommendation || null,
      profit_target_8pct: sf(row.profit_target_8pct),
      profit_target_20pct: sf(row.profit_target_20pct),
      profit_target_25pct: sf(row.profit_target_25pct),
      sell_level: sf(row.sell_level),

      // Technical indicators (from technical_data JOIN)
      rsi: sf(row.rsi),
      adx: sf(row.adx),
      atr: sf(row.atr),
      macd: sf(row.macd),
      signal_line: sf(row.signal_line),
      sma_20: sf(row.sma_20),
      sma_50: sf(row.sma_50),
      sma_200: sf(row.sma_200),
      ema_12: sf(row.ema_12),
      ema_26: sf(row.ema_26),
      pct_from_ema21: sf(row.pct_from_ema21),
      pct_from_sma50: sf(row.pct_from_sma50),
    }));

    // Get total count of records for pagination
    const countQuery = `SELECT COUNT(*) as total FROM ${tableName} bsd ${whereClause}`;
    let totalCount = 0;
    try {
      // Pass ONLY the WHERE clause parameters (not limit/offset which are at the end)
      const countParams = queryParams.slice(0, paramIndex - 1);
      console.log(`[${timeframe.toUpperCase()}] Executing count query with ${countParams.length} params`);
      const countResult = await query(countQuery, countParams);
      totalCount = parseInt(countResult.rows[0]?.total || 0);
      console.log(`[${timeframe.toUpperCase()}] Count query result:`, totalCount);
    } catch (e) {
      console.error(`[ERROR] Count query failed for ${timeframe}:`, {
        message: e.message,
        code: e.code,
        table: tableName
      });
      totalCount = page * limit + formattedData.length;
    }

    // Calculate pagination fields per RULES.md
    const totalPages = Math.ceil(totalCount / limit);
    const hasNext = page < totalPages;
    const hasPrev = page > 1;

    return sendPaginated(res, formattedData, { page, limit, total: totalCount, totalPages, hasNext, hasPrev });
  } catch (error) {
    console.error("Signals delegation error:", error);
    return sendError(res, "Failed to fetch signals data", 500);
  }
};

// Root endpoint - default to stock signals (matches /api/signals or /api/signals/)
router.get("", getStocksSignals);
router.get("/", getStocksSignals);

// Canonical endpoint for stock signals (returns ALL signals from 2019 by default)
router.get("/stocks", getStocksSignals);

// List endpoint - supports timeframe parameter for frontend filtering
router.get("/list", getStocksSignals);

// Get trading signals for ETFs - uses dedicated ETF signal tables
router.get("/etf", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const signalType = req.query.signal_type;
    const symbolFilter = req.query.symbol;
    const offset = (page - 1) * limit;

    // ETF signals are stored in dedicated ETF tables (populated by loadetfsignals.py)
    const timeframeMap = {
      daily: "buy_sell_daily_etf",
      weekly: "buy_sell_weekly_etf",
      monthly: "buy_sell_monthly_etf"
    };

    const tableName = timeframeMap[timeframe];
    if (!tableName) {
      return sendError(res, "Invalid timeframe. Must be daily, weekly, or monthly", 400);
    }

    // Build WHERE clause based on filters
    let whereClause = '';
    let queryParams = [];
    let paramIndex = 1;

    // Add date filtering - return ALL historical data by default
    const dayRange = parseInt(req.query.days);
    if (dayRange && dayRange > 0) {
      whereClause = `WHERE bsd.date >= CURRENT_DATE - MAKE_INTERVAL(days => $${paramIndex})`;
      queryParams.push(dayRange);
      paramIndex++;
    } else {
      // Default: Return ALL signals from 2019-01-01 onwards
      whereClause = `WHERE bsd.date >= '2019-01-01'`;
    }

    // ETF tables store signals as uppercase BUY/SELL (vs mixed-case in stock tables)
    whereClause += ` AND UPPER(bsd.signal) IN ('BUY', 'SELL')`;

    // Handle signal_type parameter
    if (signalType) {
      const signalTypes = signalType.split(',').map(s => s.trim().toUpperCase());
      const signalPlaceholders = signalTypes.map((_, idx) => `$${paramIndex + idx}`).join(',');
      whereClause += ` AND UPPER(bsd.signal) IN (${signalPlaceholders})`;
      signalTypes.forEach(signal => queryParams.push(signal));
      paramIndex += signalTypes.length;
    }

    if (symbolFilter) {
      whereClause += ` AND bsd.symbol = $${paramIndex}`;
      queryParams.push(symbolFilter.toUpperCase());
      paramIndex++;
    }

    // For ETF signals, select from dedicated ETF table with JOIN to get company name
    const actualColumns = `
      bsd.id, bsd.symbol, bsd.timeframe, bsd.date, bsd.date as signal_triggered_date,
      bsd.signal, bsd.buylevel as strength, bsd.buylevel as signal_strength,
      bsd.open, bsd.high, bsd.low, bsd.close, bsd.volume
    `;

    // Add limit and offset parameters
    queryParams.push(limit);
    queryParams.push(offset);
    const limitParamIndex = paramIndex;
    const offsetParamIndex = paramIndex + 1;

    const signalsQuery = `
      SELECT
        ${actualColumns},
        es.security_name as company_name
      FROM ${tableName} bsd
      LEFT JOIN etf_symbols es ON bsd.symbol = es.symbol
      ${whereClause}
      ORDER BY bsd.date DESC, bsd.id DESC
      LIMIT $${limitParamIndex} OFFSET $${offsetParamIndex}
    `;

    let signalsResult;
    try {
      signalsResult = await query(signalsQuery, queryParams);
    } catch (queryError) {
      console.error(`[ERROR] ETF signals query failed for ${timeframe}: ${queryError.message}`);
      if (queryError.code === '42P01') {
        return sendPaginated(res, [], { page, limit, total: 0, totalPages: 0, hasNext: false, hasPrev: false });
      }
      return sendError(res, `Failed to fetch ETF signals: ${queryError.message.substring(0, 100)}`, 500);
    }

    if (!signalsResult || !signalsResult.rows || signalsResult.rows.length === 0) {
      return sendPaginated(res, [], { page, limit, total: 0, totalPages: 0, hasNext: false, hasPrev: false });
    }

    const formattedData = signalsResult.rows.map(row => ({
      id: row.id,
      symbol: row.symbol,
      signal: row.signal,
      date: row.date,
      signal_triggered_date: row.signal_triggered_date || null,
      timeframe: row.timeframe || timeframe,
      strength: row.strength !== null ? parseFloat(row.strength) : null,
      signal_strength: row.signal_strength !== null ? parseFloat(row.signal_strength) : null,
      open: row.open !== null ? parseFloat(row.open) : null,
      high: row.high !== null ? parseFloat(row.high) : null,
      low: row.low !== null ? parseFloat(row.low) : null,
      close: row.close !== null ? parseFloat(row.close) : null,
      volume: row.volume !== null ? parseInt(row.volume) : null,
      company_name: row.company_name || null,
    }));

    // Get total count of records for pagination
    const countQuery = `SELECT COUNT(*) as total FROM ${tableName} bsd ${whereClause}`;
    let totalCount = 0;
    try {
      const countParams = queryParams.slice(0, paramIndex - 1);
      const countResult = await query(countQuery, countParams);
      totalCount = parseInt(countResult.rows[0]?.total || 0);
    } catch (e) {
      console.warn("Failed to get ETF signals total count:", e.message);
      totalCount = page * limit + formattedData.length;
    }

    // Calculate pagination fields per RULES.md
    const totalPages = Math.ceil(totalCount / limit);
    const hasNext = page < totalPages;
    const hasPrev = page > 1;

    return sendPaginated(res, formattedData, { page, limit, total: totalCount, totalPages, hasNext, hasPrev });
  } catch (error) {
    console.error("ETF signals error:", error);
    return sendError(res, "Failed to fetch signals data", 500);
  }
});

module.exports = router;

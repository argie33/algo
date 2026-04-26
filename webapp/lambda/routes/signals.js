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

    // Build columns - SELECT all available with consistent NULL handling
    const priceTable = timeframe === 'daily' ? 'price_daily' :
                       timeframe === 'weekly' ? 'price_weekly' :
                       'price_monthly';

    // Build dynamic SELECT based on what exists in each table
    let actualColumns;
    if (timeframe === 'daily') {
      actualColumns = `
        bsd.id, bsd.symbol, bsd.timeframe, bsd.date, bsd.date as signal_triggered_date,
        bsd.signal, bsd.buylevel as strength, bsd.buylevel as signal_strength,
        p.open, p.high, p.low, p.close, p.volume,
        t.rsi, t.adx, t.atr,
        t.macd, t.signal as signal_line,
        t.sma_20, t.sma_50, t.sma_200,
        t.ema_12, t.ema_26
      `;
    } else {
      actualColumns = `
        bsd.id, bsd.symbol, bsd.timeframe, bsd.date, bsd.date as signal_triggered_date,
        bsd.signal, bsd.buylevel as strength, bsd.buylevel as signal_strength,
        p.open, p.high, p.low, p.close, p.volume,
        t.rsi, t.adx, t.atr,
        t.macd, t.signal as signal_line,
        t.sma_20, t.sma_50, t.sma_200,
        t.ema_12, t.ema_26
      `;
    }

    // Determine technical table based on timeframe
    const technicalTable = timeframe === 'daily' ? 'technical_data_daily' :
                           timeframe === 'weekly' ? 'technical_data_weekly' :
                           'technical_data_monthly';

    // Query with price JOIN for the matching timeframe and technical JOIN
    const signalsQuery = `
      SELECT
        ${actualColumns}
      FROM ${tableName} bsd
      LEFT JOIN ${priceTable} p ON bsd.symbol = p.symbol
        AND DATE(p.date) = DATE(bsd.date)
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

    // Format response with ALL available data - COMPLETE ENRICHMENT
    const formattedData = signalsResult.rows.map(row => ({
      // Signal core
      id: row.id,
      symbol: row.symbol,
      signal: row.signal,
      date: row.date,
      signal_triggered_date: row.signal_triggered_date,
      timeframe: row.timeframe || timeframe,
      strength: row.strength !== null ? parseFloat(row.strength) : null,
      signal_strength: row.signal_strength !== null ? parseFloat(row.signal_strength) : null,

      // Price data (from daily table JOIN)
      open: row.open !== null ? parseFloat(row.open) : null,
      high: row.high !== null ? parseFloat(row.high) : null,
      low: row.low !== null ? parseFloat(row.low) : null,
      close: row.close !== null ? parseFloat(row.close) : null,
      volume: row.volume !== null ? parseInt(row.volume) : null,

      // Technical indicators (from technical_data_daily JOIN)
      rsi: row.rsi !== null ? parseFloat(row.rsi) : null,
      adx: row.adx !== null ? parseFloat(row.adx) : null,
      atr: row.atr !== null ? parseFloat(row.atr) : null,
      macd: row.macd !== null ? parseFloat(row.macd) : null,
      signal_line: row.signal_line !== null ? parseFloat(row.signal_line) : null,
      sma_20: row.sma_20 !== null ? parseFloat(row.sma_20) : null,
      sma_50: row.sma_50 !== null ? parseFloat(row.sma_50) : null,
      sma_200: row.sma_200 !== null ? parseFloat(row.sma_200) : null,
      ema_12: row.ema_12 !== null ? parseFloat(row.ema_12) : null,
      ema_26: row.ema_26 !== null ? parseFloat(row.ema_26) : null,
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
router.get("/", getStocksSignals);

// Canonical endpoint for stock signals (returns ALL signals from 2019 by default)
router.get("/stocks", getStocksSignals);

// Get trading signals for ETFs - SAME STRUCTURE AS STOCKS
router.get("/etf", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const signalType = req.query.signal_type;
    const symbolFilter = req.query.symbol;
    const offset = (page - 1) * limit;

    // Safely map timeframes to table names to prevent SQL injection
    // NOTE: ETF signals are in the SAME tables as stocks (buy_sell_daily/weekly/monthly)
    // Filtered by ETF symbol list below
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

    // For ETF signals, use same essential columns
    const actualColumns = `
      bsd.id, bsd.symbol, bsd.timeframe, bsd.date, bsd.date as signal_triggered_date,
      bsd.signal, bsd.buylevel as strength, bsd.buylevel as signal_strength
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
      INNER JOIN etf_symbols es ON bsd.symbol = es.symbol
      ${whereClause}
      ORDER BY bsd.date DESC, bsd.id DESC
      LIMIT $${limitParamIndex} OFFSET $${offsetParamIndex}
    `;

    let signalsResult;
    try {
      signalsResult = await query(signalsQuery, queryParams);
    } catch (queryError) {
      console.error(`[ERROR] ETF signals query failed for ${timeframe}: ${queryError.message}`);
      return sendError(res, `Failed to fetch ETF signals: ${queryError.message.substring(0, 100)}`, 500);
    }

    if (!signalsResult || !signalsResult.rows || signalsResult.rows.length === 0) {
      return sendPaginated(res, [], { page, limit, total: 0, totalPages: 0, hasNext: false, hasPrev: false });
    }

    // Format response - only map fields actually selected in the query (6 columns from ETF signals + company_name)
    const formattedData = signalsResult.rows.map(row => ({
      id: row.id,
      symbol: row.symbol,
      signal: row.signal,
      date: row.date,
      signal_triggered_date: row.signal_triggered_date || null,
      timeframe: row.timeframe || timeframe,
      company_name: row.company_name || null,
    }));

    // Get total count of records for pagination
    const countQuery = `SELECT COUNT(*) as total FROM ${tableName} bsd ${whereClause}`;
    let totalCount = 0;
    try {
      // Pass ONLY the WHERE clause parameters (not limit/offset which are at the end)
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

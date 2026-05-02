console.log('🔧 signalFilters.js module loading...');

const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");

const router = express.Router();
console.log('🔧 signalFilters router created');

/**
 * COMPREHENSIVE SIGNAL FILTERING ENDPOINT
 *
 * GET /api/signals/search - Search and filter all signals
 *
 * Query Parameters:
 *
 * BASIC FILTERS:
 * - type: 'swing' | 'range' | 'mean-reversion' (required)
 * - timeframe: 'daily' | 'weekly' | 'monthly' (default: daily)
 * - symbol: string (e.g., 'AAPL')
 * - signal: 'BUY' | 'SELL' (case-insensitive)
 *
 * DATE FILTERS:
 * - date: exact date (YYYY-MM-DD)
 * - from_date: range start (YYYY-MM-DD)
 * - to_date: range end (YYYY-MM-DD)
 * - days: last N days (e.g., 30 for last 30 days)
 * - today: 'true' to show only today's signals
 * - week: 'true' to show this week's signals
 * - month: 'true' to show this month's signals
 *
 * PRICE & VALUE FILTERS:
 * - min_price: minimum close price
 * - max_price: maximum close price
 * - min_volume: minimum volume
 * - max_volume: maximum volume
 *
 * TECHNICAL FILTERS (Range & Swing):
 * - min_rsi: minimum RSI value
 * - max_rsi: maximum RSI value
 * - min_atr: minimum ATR value
 * - min_adx: minimum ADX value (trend strength)
 *
 * RANGE-SPECIFIC FILTERS:
 * - min_range_position: 0-100 (position in range)
 * - max_range_position: 0-100
 * - min_range_height: minimum range height
 *
 * RISK/REWARD FILTERS (Swing):
 * - min_risk_reward: minimum risk/reward ratio
 *
 * PAGINATION & LIMITS:
 * - limit: results per page (default: 100, max: 50000)
 * - page: page number (default: 1)
 * - sort: 'date' | 'symbol' | 'price' | 'volume' (default: date DESC)
 * - sort_order: 'ASC' | 'DESC' (default: DESC)
 *
 * EXAMPLES:
 * /api/signals/search?type=swing&today=true
 * /api/signals/search?type=range&days=7&min_price=10&max_price=100
 * /api/signals/search?type=mean-reversion&signal=BUY&from_date=2026-04-01&to_date=2026-05-01
 */

const getSignalFilters = async (req, res) => {
  console.log('✅ SIGNALFILTERS: Request received for', req.path, 'with query:', req.query);
  try {
    const {
      type = 'swing',
      timeframe = 'daily',
      symbol,
      signal,
      base_type,
      date,
      from_date,
      to_date,
      days,
      today,
      week,
      month,
      min_price,
      max_price,
      min_volume,
      max_volume,
      min_rsi,
      max_rsi,
      min_atr,
      min_adx,
      min_range_position,
      max_range_position,
      min_range_height,
      min_risk_reward,
      limit = 100,
      page = 1,
      sort = 'date',
      sort_order = 'DESC'
    } = req.query;

    // Validate inputs
    if (!['swing', 'range', 'mean-reversion'].includes(type)) {
      return sendError(res, "Invalid type. Must be 'swing', 'range', or 'mean-reversion'", 400);
    }

    if (!['daily', 'weekly', 'monthly'].includes(timeframe)) {
      return sendError(res, "Invalid timeframe. Must be 'daily', 'weekly', or 'monthly'", 400);
    }

    const safeLimit = Math.min(parseInt(limit) || 100, 50000);
    const safePage = Math.max(1, parseInt(page) || 1);
    const offset = (safePage - 1) * safeLimit;

    // Map type to table
    const tableMap = {
      'swing': type === 'swing' ? `buy_sell_${timeframe}` : null,
      'range': 'range_signals_daily',
      'mean-reversion': 'mean_reversion_signals_daily'
    };

    const tableName = tableMap[type];
    if (!tableName) {
      return sendError(res, `Invalid combination of type and timeframe`, 400);
    }

    const tableAlias = 's';
    let whereConditions = [];
    let params = [];
    let paramIndex = 1;

    // DATE FILTERS
    if (today === 'true') {
      whereConditions.push(`DATE(${tableAlias}.date) = CURRENT_DATE`);
    } else if (week === 'true') {
      whereConditions.push(`DATE_TRUNC('week', ${tableAlias}.date) = DATE_TRUNC('week', CURRENT_DATE)`);
    } else if (month === 'true') {
      whereConditions.push(`DATE_TRUNC('month', ${tableAlias}.date) = DATE_TRUNC('month', CURRENT_DATE)`);
    } else if (date) {
      whereConditions.push(`DATE(${tableAlias}.date) = $${paramIndex}`);
      params.push(date);
      paramIndex++;
    } else {
      if (from_date) {
        whereConditions.push(`${tableAlias}.date >= $${paramIndex}`);
        params.push(from_date);
        paramIndex++;
      }
      if (to_date) {
        whereConditions.push(`${tableAlias}.date <= $${paramIndex}`);
        params.push(to_date);
        paramIndex++;
      }
      if (days) {
        whereConditions.push(`${tableAlias}.date >= CURRENT_DATE - MAKE_INTERVAL(days => $${paramIndex})`);
        params.push(parseInt(days));
        paramIndex++;
      }
    }

    // SYMBOL FILTER
    if (symbol) {
      whereConditions.push(`${tableAlias}.symbol = $${paramIndex}`);
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // SIGNAL FILTER
    if (signal) {
      const signalValue = signal.toUpperCase();
      whereConditions.push(`UPPER(${tableAlias}.signal) = $${paramIndex}`);
      params.push(signalValue);
      paramIndex++;
    }

    // BASE TYPE FILTER (Pattern type)
    if (base_type) {
      whereConditions.push(`${tableAlias}.base_type = $${paramIndex}`);
      params.push(base_type);
      paramIndex++;
    }

    // PRICE FILTERS
    if (min_price) {
      whereConditions.push(`${tableAlias}.close >= $${paramIndex}`);
      params.push(parseFloat(min_price));
      paramIndex++;
    }
    if (max_price) {
      whereConditions.push(`${tableAlias}.close <= $${paramIndex}`);
      params.push(parseFloat(max_price));
      paramIndex++;
    }

    // VOLUME FILTERS
    if (min_volume) {
      whereConditions.push(`${tableAlias}.volume >= $${paramIndex}`);
      params.push(parseInt(min_volume));
      paramIndex++;
    }
    if (max_volume) {
      whereConditions.push(`${tableAlias}.volume <= $${paramIndex}`);
      params.push(parseInt(max_volume));
      paramIndex++;
    }

    // TECHNICAL FILTERS
    if (min_rsi) {
      whereConditions.push(`${tableAlias}.rsi >= $${paramIndex}`);
      params.push(parseFloat(min_rsi));
      paramIndex++;
    }
    if (max_rsi) {
      whereConditions.push(`${tableAlias}.rsi <= $${paramIndex}`);
      params.push(parseFloat(max_rsi));
      paramIndex++;
    }
    if (min_atr) {
      whereConditions.push(`${tableAlias}.atr >= $${paramIndex}`);
      params.push(parseFloat(min_atr));
      paramIndex++;
    }
    if (min_adx) {
      whereConditions.push(`${tableAlias}.adx >= $${paramIndex}`);
      params.push(parseFloat(min_adx));
      paramIndex++;
    }

    // RANGE-SPECIFIC FILTERS
    if (type === 'range') {
      if (min_range_position !== undefined) {
        whereConditions.push(`${tableAlias}.range_position >= $${paramIndex}`);
        params.push(parseFloat(min_range_position));
        paramIndex++;
      }
      if (max_range_position !== undefined) {
        whereConditions.push(`${tableAlias}.range_position <= $${paramIndex}`);
        params.push(parseFloat(max_range_position));
        paramIndex++;
      }
      if (min_range_height) {
        whereConditions.push(`(${tableAlias}.range_high - ${tableAlias}.range_low) >= $${paramIndex}`);
        params.push(parseFloat(min_range_height));
        paramIndex++;
      }
    }

    // RISK/REWARD FILTERS (Swing)
    if (type === 'swing' && min_risk_reward) {
      whereConditions.push(`${tableAlias}.risk_reward_ratio >= $${paramIndex}`);
      params.push(parseFloat(min_risk_reward));
      paramIndex++;
    }

    // BUILD QUERY
    const whereClause = whereConditions.length > 0 ? `WHERE ${whereConditions.join(' AND ')}` : '';

    // SORTING
    const validSortFields = ['date', 'symbol', 'close', 'volume'];
    const sortField = validSortFields.includes(sort) ? sort : 'date';
    const sortDir = ['ASC', 'DESC'].includes(sort_order.toUpperCase()) ? sort_order.toUpperCase() : 'DESC';
    const orderBy = `ORDER BY ${tableAlias}.${sortField} ${sortDir}`;

    // COUNT QUERY
    const countQuery = `SELECT COUNT(*) as total FROM ${tableName} ${tableAlias} ${whereClause}`;
    const countResult = await query(countQuery, params);
    const total = parseInt(countResult.rows[0]?.total || 0);

    // DATA QUERY - Return ALL columns so frontend can display everything
    const dataQuery = `
      SELECT *
      FROM ${tableName} ${tableAlias}
      ${whereClause}
      ${orderBy}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    params.push(safeLimit, offset);
    console.log(`[SIGNALS FILTER] Query: ${dataQuery.substring(0, 100)}... Table: ${tableName}, Limit: ${safeLimit}`);
    const result = await query(dataQuery, params);
    console.log(`[SIGNALS FILTER] Result: ${result.rows.length} rows, ${result.rows[0] ? Object.keys(result.rows[0]).length : 0} fields per row`);

    return sendPaginated(res, result.rows, {
      limit: safeLimit,
      offset,
      total,
      page: safePage,
      totalPages: Math.ceil(total / safeLimit),
      hasNext: offset + safeLimit < total,
      hasPrev: safePage > 1
    });

  } catch (error) {
    console.error('Signal filter error:', error);
    return sendError(res, `Error filtering signals: ${error.message}`, 500);
  }
};

// Register the route
router.get('', getSignalFilters);
router.get('/', getSignalFilters);

module.exports = router;

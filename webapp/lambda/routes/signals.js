const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Helper function to safely convert values to float
// Returns NULL for missing data per data integrity rules - NO FAKE DEFAULTS
function safeFloat(value) {
  if (value === null || value === undefined) return null;
  const num = parseFloat(value);
  return isNaN(num) ? null : num;
}

// Root endpoint - returns available sub-endpoints
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "signals",
      documentation: "Trading signals API",
      available_routes: [
        "GET /stocks - Get all stock trading signals with flexible filtering",
        "  Query parameters: timeframe={daily|weekly|monthly}, symbol={SYMBOL}, limit={1-500}, page={1+}, days={days}, signal_type={Buy|Sell}",
        "GET /etf - Get all ETF trading signals",
        "  Query parameters: timeframe={daily|weekly|monthly}, symbols={SYMBOL,SYMBOL2}, limit={1-100}"
      ],
      examples: [
        "GET /api/signals/stocks?timeframe=daily&limit=100",
        "GET /api/signals/stocks?symbol=GOOGL&timeframe=weekly",
        "GET /api/signals/stocks?timeframe=monthly&signal_type=Buy&limit=50",
        "GET /api/signals/etf?timeframe=daily",
        "GET /api/signals/etf?timeframe=daily&symbols=SPY,QQQ"
      ]
    },
    success: true
  });
});

// Get all stock signals data - FRONTEND USES THIS
router.get("/stocks", async (req, res) => {
  try {
    console.log(`[DATA] Signals data requested (deployment refresh v3)`);

    const timeframe = req.query.timeframe || "daily";
    const signalType = req.query.signal_type;
    const symbolFilter = req.query.symbol;
    // Cap limit to prevent timeout on large result sets - queries take ~30s for 5000 rows
    const MAX_LIMIT = 500; // Prevent excessive database load
    const limit = Math.min(parseInt(req.query.limit) || 100, MAX_LIMIT);
    const page = Math.max(1, parseInt(req.query.page) || 1);

    // Prevent extremely large offsets that cause poor performance
    const MAX_PAGE = Math.ceil(1000000 / limit);
    if (page > MAX_PAGE) {
      return res.json({
        items: [],
        pagination: {
          page,
          limit,
          hasMore: false
        },
        success: true
      });
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
      return res.status(400).json({ error: "Invalid timeframe. Must be daily, weekly, or monthly", success: false });
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

    // Build actual columns based on REAL database schema (buy_sell_daily table)
    const actualColumns = `
      bsd.id, bsd.symbol, bsd.timeframe, bsd.date,
      bsd.signal_triggered_date,
      bsd.open, bsd.high, bsd.low, bsd.close, bsd.volume,
      bsd.signal, bsd.buylevel, bsd.stoplevel, bsd.selllevel, bsd.inposition,
      bsd.target_price, bsd.current_price,
      bsd.market_stage, bsd.stage_number, bsd.stage_confidence, bsd.substage,
      bsd.risk_reward_ratio, bsd.current_gain_loss_pct, bsd.risk_pct,
      bsd.position_size_recommendation, bsd.profit_target_20pct, bsd.profit_target_25pct,
      bsd.mansfield_rs, bsd.sata_score,
      bsd.rsi, bsd.adx, bsd.atr,
      bsd.pct_from_ema_21, bsd.pct_from_sma_50, bsd.pct_from_sma_200,
      bsd.entry_quality_score, bsd.daily_range_pct,
      bsd.volatility_profile, bsd.volume_analysis, bsd.volume_ratio,
      bsd.base_pivot_price, bsd.base_support_price, bsd.base_pattern,
      bsd.base_depth_pct, bsd.base_duration_days, bsd.base_tightness_score,
      bsd.is_base_on_base, bsd.base_quality_score,
      bsd.ma_filter_value, bsd.ma_filter_type, bsd.ma_filter_period,
      bsd.passes_minervini_template
    `;

    const tddJoin = ``;

    const signalsQuery = `
      SELECT
        ${actualColumns},
        COALESCE(cp.short_name, ss.security_name) as company_name,
        ss_scores.stability_score,
        eh.quarter as next_earnings_date,
        (eh.quarter - CURRENT_DATE)::INTEGER as days_to_earnings
      FROM ${tableName} bsd
      ${tddJoin}
      LEFT JOIN company_profile cp ON bsd.symbol = cp.ticker
      LEFT JOIN stock_symbols ss ON bsd.symbol = ss.symbol
      LEFT JOIN stock_scores ss_scores ON bsd.symbol = ss_scores.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) symbol, quarter
        FROM earnings_history
        WHERE quarter >= CURRENT_DATE
        ORDER BY symbol, quarter ASC
      ) eh ON bsd.symbol = eh.symbol
      ${whereClause}
      ORDER BY bsd.date DESC, bsd.id DESC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    let signalsResult;
    try {
      console.log(`[${timeframe.toUpperCase()}] Executing signals query with params:`, {
        limit,
        offset,
        timeframe,
        tableName,
        paramCount: [...queryParams, limit, offset].length
      });
      signalsResult = await query(signalsQuery, [...queryParams, limit, offset]);
      console.log(`[${timeframe.toUpperCase()}] Query succeeded, rows returned:`, signalsResult.rows?.length || 0);
    } catch (queryError) {
      console.error(`[ERROR] Query failed for ${timeframe} signals:`, {
        message: queryError.message,
        code: queryError.code,
        detail: queryError.detail,
        hint: queryError.hint,
        table: tableName,
        query: signalsQuery.substring(0, 200) + '...'
      });
      return res.status(500).json({
        error: "Failed to fetch signals data",
        debug: !process.env.NODE_ENV || process.env.NODE_ENV === 'development' ? queryError.message : undefined,
        success: false
      });
    }

    if (!signalsResult || !signalsResult.rows || signalsResult.rows.length === 0) {
      return res.json({
        items: [],
        pagination: { page, limit, hasMore: false },
        success: true
      });
    }

    // Summary statistics are calculated on frontend from items array per RULES.md
    const signalData = signalsResult.rows;

    // Format the response data - USE ACTUAL COLUMNS FROM buy_sell_daily TABLE
    const formattedData = signalsResult.rows.map(row => ({
      // Basic signal info
      id: row.id,
      symbol: row.symbol,
      signal: row.signal,
      date: row.date,
      signal_triggered_date: row.signal_triggered_date || null,
      timeframe: row.timeframe || timeframe,

      // Price data
      open: row.open !== null && row.open !== undefined ? parseFloat(row.open) : null,
      high: row.high !== null && row.high !== undefined ? parseFloat(row.high) : null,
      low: row.low !== null && row.low !== undefined ? parseFloat(row.low) : null,
      close: row.close !== null && row.close !== undefined ? parseFloat(row.close) : null,
      volume: row.volume !== null && row.volume !== undefined ? row.volume : null,
      daily_range_pct: row.daily_range_pct !== null ? parseFloat(row.daily_range_pct) : null,

      // Entry/Exit levels
      buylevel: row.buylevel !== null && row.buylevel !== undefined ? parseFloat(row.buylevel) : null,
      stoplevel: row.stoplevel !== null && row.stoplevel !== undefined ? parseFloat(row.stoplevel) : null,
      sell_level: row.selllevel !== null && row.selllevel !== undefined ? parseFloat(row.selllevel) : null,
      inposition: row.inposition || false,

      // Price targets
      target_price: row.target_price !== null ? parseFloat(row.target_price) : null,
      current_price: row.current_price !== null ? parseFloat(row.current_price) : null,

      // Market stage and structure
      market_stage: row.market_stage || null,
      stage_number: row.stage_number || null,
      stage_confidence: row.stage_confidence || null,
      substage: row.substage || null,
      volatility_profile: row.volatility_profile || null,
      passes_minervini_template: row.passes_minervini_template || false,

      // Risk/reward
      risk_reward_ratio: row.risk_reward_ratio !== null ? parseFloat(row.risk_reward_ratio) : null,
      current_gain_loss_pct: row.current_gain_loss_pct !== null ? parseFloat(row.current_gain_loss_pct) : null,
      risk_pct: row.risk_pct !== null ? parseFloat(row.risk_pct) : null,
      position_size_recommendation: row.position_size_recommendation !== null ? parseFloat(row.position_size_recommendation) : null,

      // Profit targets
      profit_target_20pct: row.profit_target_20pct !== null ? parseFloat(row.profit_target_20pct) : null,
      profit_target_25pct: row.profit_target_25pct !== null ? parseFloat(row.profit_target_25pct) : null,

      // Scores and ratings
      mansfield_rs: row.mansfield_rs !== null ? parseFloat(row.mansfield_rs) : null,
      sata_score: row.sata_score || null,
      entry_quality_score: row.entry_quality_score || null,
      base_quality_score: row.base_quality_score || null,
      base_tightness_score: row.base_tightness_score || null,

      // Technical indicators
      rsi: row.rsi !== null ? parseFloat(row.rsi) : null,
      adx: row.adx !== null ? parseFloat(row.adx) : null,
      atr: row.atr !== null ? parseFloat(row.atr) : null,
      pct_from_ema_21: row.pct_from_ema_21 !== null ? parseFloat(row.pct_from_ema_21) : null,
      pct_from_sma_50: row.pct_from_sma_50 !== null ? parseFloat(row.pct_from_sma_50) : null,
      pct_from_sma_200: row.pct_from_sma_200 !== null ? parseFloat(row.pct_from_sma_200) : null,

      // Volume analysis
      volume_ratio: row.volume_ratio !== null ? parseFloat(row.volume_ratio) : null,
      volume_analysis: row.volume_analysis || null,

      // Base pattern analysis
      base_pivot_price: row.base_pivot_price !== null ? parseFloat(row.base_pivot_price) : null,
      base_support_price: row.base_support_price !== null ? parseFloat(row.base_support_price) : null,
      base_pattern: row.base_pattern || null,
      base_depth_pct: row.base_depth_pct !== null ? parseFloat(row.base_depth_pct) : null,
      base_duration_days: row.base_duration_days || null,
      is_base_on_base: row.is_base_on_base || false,

      // Moving average filters
      ma_filter_value: row.ma_filter_value !== null ? parseFloat(row.ma_filter_value) : null,
      ma_filter_type: row.ma_filter_type || null,
      ma_filter_period: row.ma_filter_period || null,

      // Company and earnings information (from joined tables)
      company_name: row.company_name || null,
      stability_score: row.stability_score !== null && row.stability_score !== undefined ? parseFloat(row.stability_score) : null,
      next_earnings_date: row.next_earnings_date || null,
      days_to_earnings: row.days_to_earnings || null,
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

    return res.json({
      items: formattedData,
      pagination: { page, limit, total: totalCount, totalPages, hasNext, hasPrev },
      success: true
    });
  } catch (error) {
    console.error("Signals delegation error:", error);
    return res.status(500).json({ error: "Failed to fetch signals data", success: false });
  }
});

// Get trading signals for ETFs - SAME STRUCTURE AS STOCKS
router.get("/etf", async (req, res) => {
  try {
    const timeframe = req.query.timeframe || "daily";
    const limit = parseInt(req.query.limit) || 100;
    const page = Math.max(1, parseInt(req.query.page) || 1);

    // ETF signals tables not yet created in database
    // Return empty array with message for frontend
    console.log("[INFO] ETF signals endpoint called - tables not yet created");
    return res.json({
      items: [],
      pagination: {
        page,
        limit,
        total: 0,
        totalPages: 0,
        hasNext: false,
        hasPrev: false,
        message: "ETF signals data not yet loaded. Please check back later."
      },
      success: true
    });

    // Safely map timeframes to table names to prevent SQL injection
    const timeframeMap = {
      daily: "buy_sell_daily_etf",
      weekly: "buy_sell_weekly_etf",
      monthly: "buy_sell_monthly_etf"
    };

    const tableName = timeframeMap[timeframe];
    if (!tableName) {
      return res.status(400).json({ error: "Invalid timeframe. Must be daily, weekly, or monthly", success: false });
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

    // Build actual columns based on real data available
    const actualColumns = `
      bsd.id, bsd.symbol, bsd.timeframe, bsd.date,
      bsd.signal_triggered_date,
      bsd.open, bsd.high, bsd.low, bsd.close, bsd.volume,
      bsd.signal, bsd.buylevel, bsd.stoplevel, bsd.inposition,
      bsd.strength, bsd.signal_type, bsd.pivot_price,
      bsd.buy_zone_start, bsd.buy_zone_end,
      bsd.exit_trigger_1_price, bsd.exit_trigger_2_price,
      bsd.exit_trigger_3_condition, bsd.exit_trigger_3_price,
      bsd.exit_trigger_4_condition, bsd.exit_trigger_4_price,
      bsd.initial_stop, bsd.trailing_stop,
      bsd.base_type, bsd.base_length_days,
      bsd.avg_volume_50d, bsd.volume_surge_pct,
      bsd.rs_rating, bsd.breakout_quality,
      bsd.risk_reward_ratio, bsd.current_gain_pct, bsd.days_in_position,
      bsd.market_stage, bsd.stage_number, bsd.stage_confidence, bsd.substage,
      bsd.entry_quality_score, bsd.risk_pct, bsd.position_size_recommendation,
      bsd.profit_target_8pct, bsd.profit_target_20pct, bsd.profit_target_25pct,
      bsd.sell_level,
      bsd.mansfield_rs, bsd.sata_score,
      bsd.rsi,
      bsd.adx,
      bsd.atr,
      bsd.ema_21,
      bsd.sma_50,
      bsd.sma_200,
      bsd.pct_from_ema21,
      bsd.pct_from_sma50,
      bsd.entry_price
    `;

    const signalsQuery = `
      SELECT
        ${actualColumns},
        es.security_name as company_name
      FROM ${tableName} bsd
      LEFT JOIN etf_symbols es ON bsd.symbol = es.symbol
      ${whereClause}
      ORDER BY bsd.date DESC, bsd.id DESC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    let signalsResult;
    try {
      signalsResult = await query(signalsQuery, [...queryParams, limit, offset]);
    } catch (queryError) {
      console.error(`[ERROR] Query failed for ${timeframe} ETF signals:`, queryError.message);
      return res.status(500).json({ error: "Failed to fetch signals data", success: false });
    }

    if (!signalsResult || !signalsResult.rows || signalsResult.rows.length === 0) {
      return res.json({
        items: [],
        pagination: { page, limit, hasMore: false },
        success: true
      });
    }

    const signalData = signalsResult.rows;

    // Format the response data - ONLY include fields that exist in database
    const formattedData = signalsResult.rows.map(row => ({
      // Basic signal info - REAL DATA
      id: row.id,
      symbol: row.symbol,
      signal: row.signal,
      date: row.date,
      signal_triggered_date: row.signal_triggered_date || null,
      timeframe: row.timeframe || timeframe,

      // Price data - REAL DATA
      open: row.open !== null && row.open !== undefined ? parseFloat(row.open) : null,
      high: row.high !== null && row.high !== undefined ? parseFloat(row.high) : null,
      low: row.low !== null && row.low !== undefined ? parseFloat(row.low) : null,
      close: row.close !== null && row.close !== undefined ? parseFloat(row.close) : null,
      volume: row.volume !== null && row.volume !== undefined ? row.volume : null,

      // Entry/Exit levels - REAL DATA
      buylevel: row.buylevel !== null && row.buylevel !== undefined ? parseFloat(row.buylevel) : null,
      stoplevel: row.stoplevel !== null && row.stoplevel !== undefined ? parseFloat(row.stoplevel) : null,
      sell_level: row.sell_level !== null && row.sell_level !== undefined ? parseFloat(row.sell_level) : null,
      inposition: row.inposition || false,

      // Risk management - REAL DATA
      risk_reward_ratio: row.risk_reward_ratio !== null && row.risk_reward_ratio !== undefined ? parseFloat(row.risk_reward_ratio) : null,
      risk_pct: row.risk_pct !== null && row.risk_pct !== undefined ? parseFloat(row.risk_pct) : null,
      position_size_recommendation: row.position_size_recommendation !== null && row.position_size_recommendation !== undefined ? parseFloat(row.position_size_recommendation) : null,

      // Market stage and quality - REAL DATA
      market_stage: row.market_stage || null,
      stage_confidence: row.stage_confidence !== null && row.stage_confidence !== undefined ? parseFloat(row.stage_confidence) : null,
      substage: row.substage || null,
      sata_score: row.sata_score !== null && row.sata_score !== undefined ? parseInt(row.sata_score) : null,
      stage_number: row.stage_number !== null && row.stage_number !== undefined ? parseInt(row.stage_number) : null,
      mansfield_rs: row.mansfield_rs !== null && row.mansfield_rs !== undefined ? parseFloat(row.mansfield_rs) : null,
      rs_rating: row.rs_rating !== null && row.rs_rating !== undefined ? parseInt(row.rs_rating) : null,
      strength: row.strength !== null && row.strength !== undefined ? parseFloat(row.strength) : null,

      // Setup fundamentals - REAL DATA
      pivot_price: row.pivot_price !== null && row.pivot_price !== undefined ? parseFloat(row.pivot_price) : null,
      buy_zone_start: row.buy_zone_start !== null && row.buy_zone_start !== undefined ? parseFloat(row.buy_zone_start) : null,
      buy_zone_end: row.buy_zone_end !== null && row.buy_zone_end !== undefined ? parseFloat(row.buy_zone_end) : null,
      initial_stop: row.initial_stop !== null && row.initial_stop !== undefined ? parseFloat(row.initial_stop) : null,
      trailing_stop: row.trailing_stop !== null && row.trailing_stop !== undefined ? parseFloat(row.trailing_stop) : null,
      base_type: row.base_type || null,
      base_length_days: row.base_length_days !== null && row.base_length_days !== undefined ? parseInt(row.base_length_days) : null,

      // Exit triggers - REAL DATA
      exit_trigger_1_price: row.exit_trigger_1_price !== null && row.exit_trigger_1_price !== undefined ? parseFloat(row.exit_trigger_1_price) : null,
      exit_trigger_2_price: row.exit_trigger_2_price !== null && row.exit_trigger_2_price !== undefined ? parseFloat(row.exit_trigger_2_price) : null,
      exit_trigger_3_price: row.exit_trigger_3_price !== null && row.exit_trigger_3_price !== undefined ? parseFloat(row.exit_trigger_3_price) : null,
      exit_trigger_3_condition: row.exit_trigger_3_condition || null,
      exit_trigger_4_price: row.exit_trigger_4_price !== null && row.exit_trigger_4_price !== undefined ? parseFloat(row.exit_trigger_4_price) : null,
      exit_trigger_4_condition: row.exit_trigger_4_condition || null,

      // Volume analysis - REAL DATA
      volume_ratio: row.avg_volume_50d && row.volume ? parseFloat((row.volume / row.avg_volume_50d).toFixed(2)) : null,
      avg_volume_50d: row.avg_volume_50d !== null && row.avg_volume_50d !== undefined ? row.avg_volume_50d : null,
      volume_surge_pct: row.volume_surge_pct !== null && row.volume_surge_pct !== undefined ? parseFloat(row.volume_surge_pct) : null,

      // Technical indicators - FROM buy_sell_daily_etf (REAL DATA ONLY)
      rsi: row.rsi !== null && row.rsi !== undefined ? parseFloat(row.rsi) : null,
      adx: row.adx !== null && row.adx !== undefined ? parseFloat(row.adx) : null,
      atr: row.atr !== null && row.atr !== undefined ? parseFloat(row.atr) : null,
      sma_50: row.sma_50 !== null && row.sma_50 !== undefined ? parseFloat(row.sma_50) : null,
      sma_200: row.sma_200 !== null && row.sma_200 !== undefined ? parseFloat(row.sma_200) : null,
      ema_21: row.ema_21 !== null && row.ema_21 !== undefined ? parseFloat(row.ema_21) : null,
      pct_from_ema_21: row.pct_from_ema21 !== null && row.pct_from_ema21 !== undefined ? parseFloat(row.pct_from_ema21) : null,
      pct_from_sma_50: row.pct_from_sma50 !== null && row.pct_from_sma50 !== undefined ? parseFloat(row.pct_from_sma50) : null,
      pct_from_sma_200: row.sma_200 && row.close ? parseFloat(((row.close - row.sma_200) / row.sma_200 * 100).toFixed(2)) : null,
      entry_price: row.entry_price !== null && row.entry_price !== undefined ? parseFloat(row.entry_price) : null,
      daily_range_pct: (row.high && row.low) ? parseFloat(((row.high - row.low) / row.low * 100).toFixed(2)) : null,

      // Quality metrics - REAL DATA
      entry_quality_score: row.entry_quality_score !== null && row.entry_quality_score !== undefined ? parseInt(row.entry_quality_score) : null,
      breakout_quality: row.breakout_quality || null,
      signal_type: row.signal_type || null,
      current_gain_loss_pct: row.current_gain_pct !== null && row.current_gain_pct !== undefined ? parseFloat(row.current_gain_pct) : null,

      // ETF information
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

    return res.json({
      items: formattedData,
      pagination: { page, limit, total: totalCount, totalPages, hasNext, hasPrev },
      success: true
    });
  } catch (error) {
    console.error("ETF signals error:", error);
    return res.status(500).json({ error: "Failed to fetch signals data", success: false });
  }
});

module.exports = router;

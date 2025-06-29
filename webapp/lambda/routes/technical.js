const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Basic ping endpoint
router.get('/ping', (req, res) => {
  res.json({
    status: 'ok',
    endpoint: 'technical',
    timestamp: new Date().toISOString()
  });
});

// Main technical data endpoint - timeframe-based (daily, weekly, monthly)
router.get('/:timeframe', async (req, res) => {
  const { timeframe } = req.params;
  const { page = 1, limit = 50, symbol, start_date, end_date, rsi_min, rsi_max, macd_min, macd_max, sma_min, sma_max } = req.query;

  // Validate timeframe
  const validTimeframes = ['daily', 'weekly', 'monthly'];
  if (!validTimeframes.includes(timeframe)) {
    return res.status(400).json({ error: 'Invalid timeframe. Use daily, weekly, or monthly.' });
  }

  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

    const offset = (parseInt(page) - 1) * parseInt(limit);
    const maxLimit = Math.min(parseInt(limit), 200);

    // Build WHERE clause
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    // Symbol filter
    if (symbol && symbol.trim()) {
      whereClause += ` AND symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    } else {
      // console.log('[DEBUG] No symbol filter provided');
    }

    // Date filters
    if (start_date) {
      whereClause += ` AND date >= $${paramIndex}`;
      params.push(start_date);
      paramIndex++;
      // console.log(`[DEBUG] Start date filter: ${req.query.start_date}`);
    }

    if (end_date) {
      whereClause += ` AND date <= $${paramIndex}`;
      params.push(end_date);
      paramIndex++;
      // console.log(`[DEBUG] End date filter: ${req.query.end_date}`);
    }

    // Technical indicator filters
    if (rsi_min !== undefined && rsi_min !== '') {
      whereClause += ` AND rsi >= $${paramIndex}`;
      params.push(parseFloat(rsi_min));
      paramIndex++;
      // console.log(`[DEBUG] Indicator min filter: ${indicator} >= ${indicatorMin}`);
    }

    if (rsi_max !== undefined && rsi_max !== '') {
      whereClause += ` AND rsi <= $${paramIndex}`;
      params.push(parseFloat(rsi_max));
      paramIndex++;
    }

    if (macd_min !== undefined && macd_min !== '') {
      whereClause += ` AND macd >= $${paramIndex}`;
      params.push(parseFloat(macd_min));
      paramIndex++;
    }

    if (macd_max !== undefined && macd_max !== '') {
      whereClause += ` AND macd <= $${paramIndex}`;
      params.push(parseFloat(macd_max));
      paramIndex++;
    }

    if (sma_min !== undefined && sma_min !== '') {
      whereClause += ` AND sma_20 >= $${paramIndex}`;
      params.push(parseFloat(sma_min));
      paramIndex++;
    }

    if (sma_max !== undefined && sma_max !== '') {
      whereClause += ` AND sma_20 <= $${paramIndex}`;
      params.push(parseFloat(sma_max));
      paramIndex++;
    }

    // console.log('[DEBUG] Using whereClause:', whereClause, 'params:', params);

    // Determine table name based on timeframe
    const tableName = `technical_data_${timeframe}`;
    // console.log('[DEBUG] Using tableName:', tableName);

    // Check if table exists
    const tableExists = await db.query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );
    `, [tableName]);

    if (!tableExists.rows[0].exists) {
      return res.status(404).json({ 
        error: `Technical data table for ${timeframe} timeframe not found`,
        availableTimeframes: validTimeframes
      });
    }

    // Get total count
    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName}
      ${whereClause}
    `;
    const countResult = await db.query(countQuery, params);
    const total = parseInt(countResult.rows[0].total);

    // Get technical data
    const dataQuery = `
      SELECT 
        symbol,
        date,
        open,
        high,
        low,
        close,
        volume,
        rsi,
        macd,
        macd_signal,
        macd_histogram,
        sma_20,
        sma_50,
        ema_12,
        ema_26,
        bollinger_upper,
        bollinger_lower,
        bollinger_middle,
        stochastic_k,
        stochastic_d,
        williams_r,
        cci,
        adx,
        atr,
        obv,
        mfi,
        roc,
        momentum,
        kst,
        tsi,
        ultimate_oscillator,
        aroon_up,
        aroon_down,
        aroon_oscillator,
        chaikin_money_flow,
        money_flow_index,
        on_balance_volume,
        price_volume_trend,
        accumulation_distribution,
        coppock_curve,
        detrended_price_oscillator,
        ease_of_movement,
        force_index,
        ichimoku_conversion,
        ichimoku_base,
        ichimoku_span_a,
        ichimoku_span_b,
        ichimoku_lagging,
        klinger_oscillator,
        know_sure_thing,
        mass_index,
        median_price,
        mid_point,
        mid_price,
        parabolic_sar,
        percentage_price_oscillator,
        percentage_volume_oscillator,
        pivot_points_high,
        pivot_points_low,
        pivot_points_close,
        pivot_points_pp,
        pivot_points_r1,
        pivot_points_r2,
        pivot_points_r3,
        pivot_points_s1,
        pivot_points_s2,
        pivot_points_s3,
        price_oscillator,
        price_volume_oscillator,
        rate_of_change,
        relative_strength_index,
        relative_vigor_index,
        standard_deviation,
        stochastic_fast,
        stochastic_slow,
        stochastic_rsi,
        triple_exponential_average,
        triple_exponential_moving_average,
        true_strength_index,
        ultimate_oscillator,
        volume_price_trend,
        volume_weighted_average_price,
        volume_weighted_moving_average,
        williams_alligator_jaw,
        williams_alligator_teeth,
        williams_alligator_lips,
        williams_fractal_bearish,
        williams_fractal_bullish,
        zero_lag_exponential_moving_average
      FROM ${tableName}
      ${whereClause}
      ORDER BY date DESC, symbol ASC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    // console.log('[DEBUG] Executing queries with limit:', limit, 'offset:', offset);
    // console.log('[DEBUG] Final SQL Query:', dataQuery);
    // console.log('[DEBUG] Query Parameters:', [...params, limit, offset]);

    const dataResult = await db.query(dataQuery, [...params, maxLimit, offset]);

    // console.log('[DEBUG] Query results - data:', dataResult.rows.length, 'total:', countResult.rows[0].total);
    
    if (dataResult.rows.length > 0) {
      // console.log('[DEBUG] Sample data row:', dataResult.rows[0]);
    }

    res.json({
      data: dataResult.rows,
      pagination: {
        page: parseInt(page),
        limit: maxLimit,
        total,
        pages: Math.ceil(total / maxLimit)
      },
      filters: {
        timeframe,
        symbol: symbol || null,
        start_date: start_date || null,
        end_date: end_date || null,
        rsi_range: rsi_min && rsi_max ? [rsi_min, rsi_max] : null,
        macd_range: macd_min && macd_max ? [macd_min, macd_max] : null,
        sma_range: sma_min && sma_max ? [sma_min, sma_max] : null
      },
      metadata: {
        table: tableName,
        timeframe,
        totalRecords: total,
        showingRecords: dataResult.rows.length,
        availableIndicators: [
          'rsi', 'macd', 'sma_20', 'sma_50', 'ema_12', 'ema_26',
          'bollinger_upper', 'bollinger_lower', 'stochastic_k', 'stochastic_d',
          'williams_r', 'cci', 'adx', 'atr', 'obv', 'mfi', 'roc', 'momentum'
        ]
      }
    });
  } catch (error) {
    console.error('Error fetching technical data:', error);
    res.status(500).json({ error: 'Failed to fetch technical data' });
  }
});

// Technical summary endpoint
router.get('/:timeframe/summary', async (req, res) => {
  const { timeframe } = req.params;
  
  // console.log(`Technical summary endpoint called for timeframe: ${timeframe}`);

  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

    const tableName = `technical_data_${timeframe}`;

    // Check if table exists
    const tableExists = await db.query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );
    `, [tableName]);

    if (!tableExists.rows[0].exists) {
      return res.status(404).json({ 
        error: `Technical data table for ${timeframe} timeframe not found` 
      });
    }

    // Get summary statistics
    const summaryQuery = `
      SELECT 
        COUNT(*) as total_records,
        COUNT(DISTINCT symbol) as unique_symbols,
        MIN(date) as earliest_date,
        MAX(date) as latest_date,
        AVG(rsi) as avg_rsi,
        AVG(macd) as avg_macd,
        AVG(sma_20) as avg_sma_20,
        AVG(volume) as avg_volume
      FROM ${tableName}
      WHERE rsi IS NOT NULL OR macd IS NOT NULL
    `;

    const summaryResult = await db.query(summaryQuery);
    const summary = summaryResult.rows[0];

    // Get top symbols by record count
    const topSymbolsQuery = `
      SELECT symbol, COUNT(*) as record_count
      FROM ${tableName}
      GROUP BY symbol
      ORDER BY record_count DESC
      LIMIT 10
    `;

    const topSymbolsResult = await db.query(topSymbolsQuery);

    res.json({
      timeframe,
      summary: {
        totalRecords: parseInt(summary.total_records),
        uniqueSymbols: parseInt(summary.unique_symbols),
        dateRange: {
          earliest: summary.earliest_date,
          latest: summary.latest_date
        },
        averages: {
          rsi: summary.avg_rsi ? parseFloat(summary.avg_rsi).toFixed(2) : null,
          macd: summary.avg_macd ? parseFloat(summary.avg_macd).toFixed(4) : null,
          sma20: summary.avg_sma_20 ? parseFloat(summary.avg_sma_20).toFixed(2) : null,
          volume: summary.avg_volume ? parseInt(summary.avg_volume) : null
        }
      },
      topSymbols: topSymbolsResult.rows.map(row => ({
        symbol: row.symbol,
        recordCount: parseInt(row.record_count)
      }))
    });
  } catch (error) {
    console.error('Error fetching technical summary:', error);
    res.status(500).json({ error: 'Failed to fetch technical summary' });
  }
});

// Root technical endpoint - defaults to daily data
router.get('/', async (req, res) => {
  try {
    // Only fetch the latest technicals for each symbol (overview)
    const timeframe = req.query.timeframe || 'daily';
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        error: 'Unsupported timeframe',
        message: `Supported timeframes: ${validTimeframes.join(', ')}, got: ${timeframe}`
      });
    }
    const tableName = `technical_data_${timeframe}`;
    // Subquery to get latest date per symbol
    const latestQuery = `
      SELECT t1.* FROM ${tableName} t1
      INNER JOIN (
        SELECT symbol, MAX(date) AS max_date
        FROM ${tableName}
        GROUP BY symbol
      ) t2 ON t1.symbol = t2.symbol AND t1.date = t2.max_date
      LEFT JOIN stock_symbols ss ON t1.symbol = ss.symbol
      ORDER BY t1.symbol ASC
      LIMIT 500
    `;
    const result = await query(latestQuery);
    res.json({
      success: true,
      data: result.rows,
      count: result.rows.length,
      metadata: {
        timeframe,
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    console.error('Error in technical overview endpoint:', error);
    res.status(500).json({
      error: 'Failed to fetch technical overview',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;

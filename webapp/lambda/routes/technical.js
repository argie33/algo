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
  try {
    const { timeframe } = req.params;
    console.log(`[DEBUG] Technical data endpoint called for timeframe: ${timeframe}, params:`, req.query);
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      console.log(`[DEBUG] Invalid timeframe: ${timeframe}`);
      return res.status(400).json({
        error: 'Unsupported timeframe',
        message: `Supported timeframes: ${validTimeframes.join(', ')}, got: ${timeframe}`,
        availableTimeframes: validTimeframes
      });
    }
    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 25, 100);
    const offset = (page - 1) * limit;
    const symbol = req.query.symbol;
    console.log(`[DEBUG] Pagination: page=${page}, limit=${limit}, offset=${offset}`);
    const tableName = `technical_data_${timeframe}`;
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;
    if (symbol) {
      console.log(`[DEBUG] Symbol filter provided: ${symbol}`);
      whereClause += ` AND t.symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    } else {
      console.log('[DEBUG] No symbol filter provided');
    }
    if (req.query.start_date) {
      console.log(`[DEBUG] Start date filter: ${req.query.start_date}`);
      whereClause += ` AND t.date >= $${paramIndex}`;
      params.push(req.query.start_date);
      paramIndex++;
    }
    if (req.query.end_date) {
      console.log(`[DEBUG] End date filter: ${req.query.end_date}`);
      whereClause += ` AND t.date <= $${paramIndex}`;
      params.push(req.query.end_date);
      paramIndex++;
    }
    const indicator = req.query.indicator;
    const indicatorMin = req.query.indicatorMin;
    const indicatorMax = req.query.indicatorMax;
    const allowedIndicators = [
      'rsi','macd','macd_signal','macd_hist','adx','atr','mfi','roc','mom','sma_10','sma_20','sma_50','sma_150','sma_200','ema_4','ema_9','ema_21','bbands_upper','bbands_middle','bbands_lower','ad','cmf','td_sequential','td_combo','marketwatch','dm','pivot_high','pivot_low','pivot_high_triggered','pivot_low_triggered'
    ];
    if (indicator && allowedIndicators.includes(indicator)) {
      if (indicatorMin !== undefined && indicatorMin !== '') {
        console.log(`[DEBUG] Indicator min filter: ${indicator} >= ${indicatorMin}`);
        whereClause += ` AND t.${indicator} >= $${paramIndex}`;
        params.push(Number(indicatorMin));
        paramIndex++;
      }
      if (indicatorMax !== undefined && indicatorMax !== '') {
        console.log(`[DEBUG] Indicator max filter: ${indicator} <= ${indicatorMax}`);
        whereClause += ` AND t.${indicator} <= $${paramIndex}`;
        params.push(Number(indicatorMax));
        paramIndex++;
      }
    }
    let sortBy = req.query.sortBy || 'date';
    let sortOrder = req.query.sortOrder === 'asc' ? 'ASC' : 'DESC';
    const allowedSorts = [
      'symbol','date','rsi','macd','macd_signal','macd_hist','adx','atr','mfi','roc','mom','sma_10','sma_20','sma_50','sma_150','sma_200','ema_4','ema_9','ema_21','bbands_upper','bbands_middle','bbands_lower','ad','cmf','td_sequential','td_combo','marketwatch','dm','pivot_high','pivot_low','pivot_high_triggered','pivot_low_triggered'
    ];
    if (!allowedSorts.includes(sortBy)) sortBy = 'date';
    console.log('[DEBUG] Using whereClause:', whereClause, 'params:', params);
    console.log('[DEBUG] Using tableName:', tableName);
    // Detect if no filters are present (only pagination/sorting)
    let dataQuery, countQuery;
    // If no filters, return only the latest record per symbol (alphabetical, paginated)
    const noFilters = !symbol && !req.query.start_date && !req.query.end_date && !indicator;
    if (noFilters) {
      dataQuery = `
        SELECT 
          t.symbol,
          t.date,
          t.rsi,
          t.macd,
          t.macd_signal,
          t.macd_hist,
          t.mom,
          t.roc,
          t.adx,
          t.atr,
          t.ad,
          t.cmf,
          t.mfi,
          t.td_sequential,
          t.td_combo,
          t.marketwatch,
          t.dm,
          t.sma_10,
          t.sma_20,
          t.sma_50,
          t.sma_150,
          t.sma_200,
          t.ema_4,
          t.ema_9,
          t.ema_21,
          t.bbands_lower,
          t.bbands_middle,
          t.bbands_upper,
          t.pivot_high,
          t.pivot_low,
          t.pivot_high_triggered,
          t.pivot_low_triggered,
          ss.security_name as company_name
        FROM ${tableName} t
        LEFT JOIN stock_symbols ss ON t.symbol = ss.symbol
        INNER JOIN (
          SELECT symbol, MAX(date) as max_date
          FROM ${tableName}
          GROUP BY symbol
        ) latest ON t.symbol = latest.symbol AND t.date = latest.max_date
        ORDER BY t.symbol ASC
        LIMIT $1 OFFSET $2
      `;
      countQuery = `
        SELECT COUNT(*) as total
        FROM (
          SELECT symbol, MAX(date) as max_date
          FROM ${tableName}
          GROUP BY symbol
        ) sub
      `;
      params.length = 0; // no filters, so params is empty
    } else {
      dataQuery = `
        SELECT 
          t.symbol,
          t.date,
          t.rsi,
          t.macd,
          t.macd_signal,
          t.macd_hist,
          t.mom,
          t.roc,
          t.adx,
          t.atr,
          t.ad,
          t.cmf,
          t.mfi,
          t.td_sequential,
          t.td_combo,
          t.marketwatch,
          t.dm,
          t.sma_10,
          t.sma_20,
          t.sma_50,
          t.sma_150,
          t.sma_200,
          t.ema_4,
          t.ema_9,
          t.ema_21,
          t.bbands_lower,
          t.bbands_middle,
          t.bbands_upper,
          t.pivot_high,
          t.pivot_low,
          t.pivot_high_triggered,
          t.pivot_low_triggered,
          ss.security_name as company_name
        FROM ${tableName} t
        LEFT JOIN stock_symbols ss ON t.symbol = ss.symbol
        ${whereClause}
        ORDER BY t.${sortBy} ${sortOrder}, t.symbol ASC
        LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
      `;
      countQuery = `
        SELECT COUNT(*) as total
        FROM ${tableName} t
        ${whereClause}
      `;
    }
    // console.log('[DEBUG] Executing queries with limit:', limit, 'offset:', offset);
    // console.log('[DEBUG] Final SQL Query:', dataQuery);
    // console.log('[DEBUG] Query Parameters:', [...params, limit, offset]);
    let dataResult, countResult;
    if (noFilters) {
      [dataResult, countResult] = await Promise.all([
        query(dataQuery, [limit, offset]),
        query(countQuery)
      ]);
    } else {
      [dataResult, countResult] = await Promise.all([
        query(dataQuery, [...params, limit, offset]),
        query(countQuery, params)
      ]);
    }
    // console.log('[DEBUG] Query results - data:', dataResult.rows.length, 'total:', countResult.rows[0].total);
    if (dataResult.rows && dataResult.rows.length > 0) {
      console.log('[DEBUG] Sample data row:', dataResult.rows[0]);
    } else {
      console.warn('[DEBUG] No technical data found for query:', dataQuery, 'params:', [...params, limit, offset]);
    }
    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);
    function sanitizeRow(row) {
      const indicators = [
        'rsi','macd','macd_signal','macd_hist','adx','atr','mfi','roc','mom','sma_10','sma_20','sma_50','sma_150','sma_200','ema_4','ema_9','ema_21','bbands_upper','bbands_middle','bbands_lower','ad','cmf','td_sequential','td_combo','marketwatch','dm','pivot_high','pivot_low','pivot_high_triggered','pivot_low_triggered'
      ];
      const sanitized = { ...row };
      indicators.forEach(key => {
        if (sanitized[key] === undefined || sanitized[key] === null || isNaN(sanitized[key])) {
          sanitized[key] = null;
        } else {
          sanitized[key] = Number(sanitized[key]);
        }
      });
      return sanitized;
    }
    res.json({
      success: true,
      data: dataResult.rows.map(sanitizeRow),
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      },
      metadata: {
        timeframe,
        symbol: symbol || 'all',
        count: dataResult.rows.length,
        start_date: req.query.start_date || null,
        end_date: req.query.end_date || null,
        timestamp: new Date().toISOString(),
        queryDebug: {
          sql: dataQuery,
          params: [...params, limit, offset]
        },
        warning: dataResult.rows.length === 0 ? 'No technical data found for the given query. Check your database and query parameters.' : undefined
      }
    });
  } catch (error) {
    console.error('[DEBUG] Error in technical endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to fetch technical data',
      details: error.message,
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

// Technical summary endpoint
router.get('/:timeframe/summary', async (req, res) => {
  try {
    const { timeframe } = req.params;
    console.log(`Technical summary endpoint called for timeframe: ${timeframe}`);
    
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        error: 'Unsupported timeframe',
        message: `Supported timeframes: ${validTimeframes.join(', ')}, got: ${timeframe}`,
        availableTimeframes: validTimeframes
      });
    }

    const tableName = `technical_data_${timeframe}`;
    
    const summaryQuery = `
      SELECT 
        COUNT(*) as total_records,
        COUNT(DISTINCT symbol) as unique_symbols,
        MAX(date) as latest_date,
        MIN(date) as earliest_date,
        COUNT(CASE WHEN rsi > 70 THEN 1 END) as overbought_count,
        COUNT(CASE WHEN rsi < 30 THEN 1 END) as oversold_count,
        COUNT(CASE WHEN macd > macd_signal THEN 1 END) as macd_bullish_count,
        AVG(rsi) as avg_rsi,
        AVG(sma_20) as avg_sma_20
      FROM ${tableName}
      WHERE date = (SELECT MAX(date) FROM ${tableName})
    `;

    const result = await query(summaryQuery);
    const summary = result.rows[0];

    res.json({
      success: true,
      data: {
        timeframe,
        summary: {
          total_records: parseInt(summary.total_records),
          unique_symbols: parseInt(summary.unique_symbols),
          latest_date: summary.latest_date,
          earliest_date: summary.earliest_date,
          market_conditions: {
            overbought_stocks: parseInt(summary.overbought_count),
            oversold_stocks: parseInt(summary.oversold_count),
            macd_bullish_stocks: parseInt(summary.macd_bullish_count),
            average_rsi: parseFloat(summary.avg_rsi || 0).toFixed(2),
            average_sma_20: parseFloat(summary.avg_sma_20 || 0).toFixed(2)
          }
        }
      },
      metadata: {
        timestamp: new Date().toISOString()
      }
    });

  } catch (error) {
    console.error('Error fetching technical summary:', error);
    res.status(500).json({ 
      error: 'Failed to fetch technical summary', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
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

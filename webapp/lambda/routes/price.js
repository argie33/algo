const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Basic ping endpoint
router.get('/ping', (req, res) => {
  res.json({
    status: 'ok',
    endpoint: 'price',
    timestamp: new Date().toISOString()
  });
});

// Main price history endpoint - timeframe-based (daily, weekly, monthly)
router.get('/history/:timeframe', async (req, res) => {
  const { timeframe } = req.params;
  const { page = 1, limit = 50, symbol, start_date, end_date } = req.query;

  // Validate timeframe
  const validTimeframes = ['daily', 'weekly', 'monthly'];
  if (!validTimeframes.includes(timeframe)) {
    return res.status(400).json({ error: 'Invalid timeframe. Use daily, weekly, or monthly.' });
  }

  try {
    const offset = (parseInt(page) - 1) * parseInt(limit);
    const maxLimit = Math.min(parseInt(limit), 200);

    // Build WHERE clause
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    // Symbol filter (required)
    if (!symbol || !symbol.trim()) {
      return res.status(400).json({ error: 'Symbol parameter is required' });
    }
    
    whereClause += ` AND symbol = $${paramIndex}`;
    params.push(symbol.toUpperCase());
    paramIndex++;

    // Date filters
    if (start_date) {
      whereClause += ` AND date >= $${paramIndex}`;
      params.push(start_date);
      paramIndex++;
    }

    if (end_date) {
      whereClause += ` AND date <= $${paramIndex}`;
      params.push(end_date);
      paramIndex++;
    }

    // Determine table name based on timeframe
    const tableName = `price_${timeframe}`;

    // Check if table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      )`, [tableName]);

    if (!tableExists.rows[0].exists) {
      return res.status(404).json({ 
        error: `Price data table for ${timeframe} timeframe not found`,
        availableTimeframes: validTimeframes
      });
    }

    // Get total count for pagination
    const countQuery = `
      SELECT COUNT(*) as total 
      FROM ${tableName} 
      ${whereClause}
    `;

    const countResult = await query(countQuery, params);
    const total = parseInt(countResult.rows[0].total);

    // Main data query with pagination
    const dataQuery = `
      SELECT 
        symbol,
        date,
        open,
        high,
        low,
        close,
        volume,
        adj_close,
        stock_splits,
        dividends
      FROM ${tableName}
      ${whereClause}
      ORDER BY date DESC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    params.push(maxLimit, offset);
    const dataResult = await query(dataQuery, params);

    // Calculate some basic statistics for the response
    const prices = dataResult.rows.map(row => parseFloat(row.close));
    const volumes = dataResult.rows.map(row => parseInt(row.volume));
    
    const stats = prices.length > 0 ? {
      avgPrice: (prices.reduce((a, b) => a + b, 0) / prices.length).toFixed(2),
      minPrice: Math.min(...prices).toFixed(2),
      maxPrice: Math.max(...prices).toFixed(2),
      avgVolume: Math.round(volumes.reduce((a, b) => a + b, 0) / volumes.length),
      totalRecords: total
    } : null;

    // Format response
    const response = {
      success: true,
      data: dataResult.rows.map(row => ({
        symbol: row.symbol,
        date: row.date,
        open: parseFloat(row.open),
        high: parseFloat(row.high),
        low: parseFloat(row.low),
        close: parseFloat(row.close),
        volume: parseInt(row.volume),
        adjustedClose: row.adj_close ? parseFloat(row.adj_close) : null,
        splitFactor: row.stock_splits ? parseFloat(row.stock_splits) : null,
        dividend: row.dividends ? parseFloat(row.dividends) : null
      })),
      pagination: {
        page: parseInt(page),
        limit: maxLimit,
        total: total,
        totalPages: Math.ceil(total / maxLimit),
        hasNextPage: offset + maxLimit < total,
        hasPreviousPage: page > 1
      },
      statistics: stats,
      metadata: {
        symbol: symbol.toUpperCase(),
        timeframe: timeframe,
        dateRange: {
          from: start_date || 'earliest',
          to: end_date || 'latest'
        },
        generatedAt: new Date().toISOString()
      }
    };

    console.log(`📊 Price history query successful: ${symbol} ${timeframe} - ${dataResult.rows.length} records`);
    res.json(response);

  } catch (error) {
    console.error('❌ Price history query error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch price history data',
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

// Get available symbols for a timeframe
router.get('/symbols/:timeframe', async (req, res) => {
  const { timeframe } = req.params;
  const { search, limit = 100 } = req.query;

  // Validate timeframe
  const validTimeframes = ['daily', 'weekly', 'monthly'];
  if (!validTimeframes.includes(timeframe)) {
    return res.status(400).json({ error: 'Invalid timeframe. Use daily, weekly, or monthly.' });
  }

  try {
    const tableName = `price_${timeframe}`;
    const maxLimit = Math.min(parseInt(limit), 500);

    let whereClause = '';
    const params = [];
    let paramIndex = 1;

    // Add search filter if provided
    if (search && search.trim()) {
      whereClause = `WHERE symbol ILIKE $${paramIndex}`;
      params.push(`%${search.toUpperCase()}%`);
      paramIndex++;
    }

    const symbolQuery = `
      SELECT 
        symbol,
        COUNT(*) as record_count,
        MIN(date) as earliest_date,
        MAX(date) as latest_date,
        MAX(close) as max_close,
        MIN(close) as min_close
      FROM ${tableName}
      ${whereClause}
      GROUP BY symbol
      ORDER BY symbol
      LIMIT $${paramIndex}
    `;

    params.push(maxLimit);
    const result = await query(symbolQuery, params);

    res.json({
      success: true,
      data: result.rows.map(row => ({
        symbol: row.symbol,
        recordCount: parseInt(row.record_count),
        dateRange: {
          earliest: row.earliest_date,
          latest: row.latest_date
        },
        priceRange: {
          min: parseFloat(row.min_close),
          max: parseFloat(row.max_close)
        }
      })),
      metadata: {
        timeframe: timeframe,
        totalSymbols: result.rows.length,
        searchTerm: search || null
      }
    });

  } catch (error) {
    console.error('❌ Symbols query error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch available symbols',
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

// Get latest price for a symbol
router.get('/latest/:symbol', async (req, res) => {
  const { symbol } = req.params;
  const { timeframe = 'daily' } = req.query;

  try {
    const tableName = `price_${timeframe}`;
    
    const latestQuery = `
      SELECT 
        symbol,
        date,
        open,
        high,
        low,
        close,
        volume,
        adjusted_close
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `;

    const result = await query(latestQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No price data found for symbol ${symbol.toUpperCase()} in ${timeframe} timeframe`
      });
    }

    const latestData = result.rows[0];

    res.json({
      success: true,
      data: {
        symbol: latestData.symbol,
        date: latestData.date,
        open: parseFloat(latestData.open),
        high: parseFloat(latestData.high),
        low: parseFloat(latestData.low),
        close: parseFloat(latestData.close),
        volume: parseInt(latestData.volume),
        adjustedClose: latestData.adjusted_close ? parseFloat(latestData.adjusted_close) : null
      },
      metadata: {
        timeframe: timeframe,
        generatedAt: new Date().toISOString()
      }
    });

  } catch (error) {
    console.error('❌ Latest price query error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch latest price data',
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

module.exports = router;
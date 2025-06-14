const express = require('express');
const router = express.Router();
const { query } = require('../utils/database');

// Get technical data by timeframe
router.get('/:timeframe', async (req, res) => {
  try {
    const { timeframe } = req.params;
    const { limit = 50, symbol, sortBy = 'date', sortOrder = 'desc' } = req.query;

    // Validate timeframe
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `technical_data_${timeframe}`;
    
    // Build WHERE clause
    let whereClause = '';
    const queryParams = [];
    let paramCount = 0;

    if (symbol) {
      paramCount++;
      whereClause = `WHERE symbol = $${paramCount}`;
      queryParams.push(symbol);
    }
    
    // Validate sort column
    const validSortColumns = ['symbol', 'date', 'rsi', 'macd', 'adx', 'mfi'];
    const sortColumn = validSortColumns.includes(sortBy) ? sortBy : 'date';
    const order = sortOrder.toLowerCase() === 'asc' ? 'ASC' : 'DESC';

    const sqlQuery = `
      SELECT 
        symbol,
        date,
        rsi,
        macd,
        macd_signal,
        macd_hist,
        mom,
        roc,
        adx,
        atr,
        ad,
        cmf,
        mfi,
        td_sequential,
        td_combo,
        marketwatch,
        dm,
        sma_10,
        sma_20,
        sma_50,
        sma_150,
        sma_200,
        ema_4,
        ema_9,
        ema_21,
        bbands_lower,
        bbands_middle,
        bbands_upper,
        pivot_high,
        pivot_low,
        fetched_at
        sma_150,
        sma_200,
        ema_4,
        ema_9,
        ema_21,
        bbands_lower,
        bbands_middle,
        bbands_upper,
        pivot_high,
        pivot_low
      FROM ${tableName}
      ${whereClause}
      ORDER BY ${sortColumn} ${order}
      LIMIT $${queryParams.length + 1}
    `;

    queryParams.push(parseInt(limit));

    const result = await query(sqlQuery, queryParams);

    res.json({
      success: true,
      data: result.rows,
      timeframe,
      count: result.rows.length,
      metadata: {
        limit: parseInt(limit),
        sortBy: sortColumn,
        sortOrder: order,
        symbol: symbol || null
      }
    });

  } catch (error) {
    console.error('Error fetching technical data:', error);
    res.status(500).json({ 
      error: 'Failed to fetch technical data',
      message: error.message 
    });
  }
});

// Get technical summary for a specific symbol
router.get('/:timeframe/:symbol', async (req, res) => {
  try {
    const { timeframe, symbol } = req.params;
    
    // Validate timeframe
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `technical_data_${timeframe}`;
      const sqlQuery = `
      SELECT 
        symbol,
        date,
        rsi,
        macd,
        macd_signal,
        macd_hist,
        adx,
        mfi,
        sma_20,
        sma_50,
        sma_200,
        bbands_lower,
        bbands_middle,
        bbands_upper,
        fetched_at
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 30
    `;

    const result = await query(sqlQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({ 
        error: 'No technical data found for this symbol',
        symbol,
        timeframe 
      });
    }

    res.json({
      success: true,
      data: result.rows,
      symbol: symbol.toUpperCase(),
      timeframe,
      count: result.rows.length
    });

  } catch (error) {
    console.error('Error fetching technical data for symbol:', error);
    res.status(500).json({ 
      error: 'Failed to fetch technical data for symbol',
      message: error.message 
    });
  }
});

module.exports = router;

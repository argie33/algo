const express = require('express');
const router = express.Router();
const { query } = require('../utils/database');

// Get technical data by timeframe
router.get('/:timeframe', async (req, res) => {
  try {
    const { timeframe } = req.params;
    const { limit = 50, symbol, page = 1 } = req.query;

    // Validate timeframe
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `technical_data_${timeframe}`;
    const offset = (parseInt(page) - 1) * parseInt(limit);
    
    let sqlQuery;
    let queryParams;

    if (symbol) {
      // If symbol specified, get historical data for that symbol with pagination
      sqlQuery = `
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
          pivot_low
        FROM ${tableName}
        WHERE symbol = $1
        ORDER BY date DESC
        LIMIT $2 OFFSET $3
      `;
      
      queryParams = [symbol.toUpperCase(), parseInt(limit), offset];
      
    } else {
      // If no symbol specified, get LATEST data for each symbol (much more efficient)
      sqlQuery = `
        WITH latest_dates AS (
          SELECT symbol, MAX(date) as latest_date
          FROM ${tableName}
          GROUP BY symbol
        )
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
          t.pivot_low
        FROM ${tableName} t
        JOIN latest_dates ld ON t.symbol = ld.symbol AND t.date = ld.latest_date
        ORDER BY t.symbol
        LIMIT $1 OFFSET $2
      `;
      
      queryParams = [parseInt(limit), offset];
    }

    const result = await query(sqlQuery, queryParams);

    res.json({
      success: true,
      data: result.rows,
      timeframe,
      count: result.rows.length,
      metadata: {
        limit: parseInt(limit),
        page: parseInt(page),
        symbol: symbol || null,
        hasSymbolFilter: !!symbol
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
        mom,
        roc,
        atr,
        ad,
        cmf,
        td_sequential,
        td_combo,
        marketwatch,
        dm,
        sma_10,
        sma_150,
        ema_4,
        ema_9,
        ema_21,
        pivot_high,
        pivot_low
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

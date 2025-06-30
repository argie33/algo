const express = require('express');
const router = express.Router();
const { query } = require('../utils/database');

// Get buy/sell signals by timeframe
router.get('/signals/:timeframe', async (req, res) => {
  try {
    const { timeframe } = req.params;
    const { limit = 100, page = 1, symbol, signal_type } = req.query;
    const pageNum = Math.max(1, parseInt(page));
    const pageSize = Math.max(1, parseInt(limit));
    const offset = (pageNum - 1) * pageSize;

    // Validate timeframe
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `buy_sell_${timeframe}`;
    
    // Build WHERE clause
    let whereClause = '';
    const queryParams = [];
    let paramCount = 0;

    const conditions = [];
    
    if (symbol) {
      paramCount++;
      conditions.push(`symbol = $${paramCount}`);
      queryParams.push(symbol.toUpperCase());
    }    if (signal_type === 'buy') {
      conditions.push("signal = 'Buy'");
    } else if (signal_type === 'sell') {
      conditions.push("signal = 'Sell'");
    }

    if (conditions.length > 0) {
      whereClause = 'WHERE ' + conditions.join(' AND ');
    }

    // Main data query with pagination
    const sqlQuery = `
      SELECT 
        bs.symbol,
        bs.date,
        bs.signal,
        bs.buylevel as price,
        bs.stoplevel,
        bs.inposition,
        md.regular_market_price as current_price,
        cp.short_name as company_name,
        cp.sector,
        md.market_cap,
        md.trailing_pe,
        md.dividend_yield,
        CASE 
          WHEN bs.signal = 'Buy' AND md.regular_market_price > bs.buylevel 
          THEN ((md.regular_market_price - bs.buylevel) / bs.buylevel * 100)
          WHEN bs.signal = 'Sell' AND md.regular_market_price < bs.buylevel 
          THEN ((bs.buylevel - md.regular_market_price) / bs.buylevel * 100)
          ELSE 0
        END as performance_percent
      FROM ${tableName} bs
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      LEFT JOIN company_profile cp ON bs.symbol = cp.ticker
      ${whereClause}
      ORDER BY bs.date DESC, bs.symbol ASC
      LIMIT $${queryParams.length + 1} OFFSET $${queryParams.length + 2}
    `;

    // Count query for pagination
    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName} bs
      ${whereClause}
    `;

    queryParams.push(pageSize, offset);

    const [result, countResult] = await Promise.all([
      query(sqlQuery, queryParams),
      query(countQuery, queryParams.slice(0, paramCount))
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / pageSize);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      success: true,
      data: result.rows,
      timeframe,
      count: result.rows.length,
      pagination: {
        page: pageNum,
        limit: pageSize,
        total,
        totalPages,
        hasNext: pageNum < totalPages,
        hasPrev: pageNum > 1
      },
      metadata: {
        signal_type: signal_type || 'all',
        symbol: symbol || null
      }
    });

  } catch (error) {
    console.error('Error fetching trading signals:', error);
    res.status(500).json({ 
      error: 'Failed to fetch trading signals',
      message: error.message 
    });
  }
});

// Get signals summary
router.get('/summary/:timeframe', async (req, res) => {
  try {
    const { timeframe } = req.params;
    
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe' });
    }

    const tableName = `buy_sell_${timeframe}`;
      const sqlQuery = `
      SELECT 
        COUNT(*) as total_signals,
        COUNT(CASE WHEN signal = 'Buy' THEN 1 END) as buy_signals,
        COUNT(CASE WHEN signal = 'Sell' THEN 1 END) as sell_signals,
        COUNT(CASE WHEN signal = 'Buy' THEN 1 END) as strong_buy,
        COUNT(CASE WHEN signal = 'Sell' THEN 1 END) as strong_sell,
        COUNT(CASE WHEN signal != 'None' AND signal IS NOT NULL THEN 1 END) as active_signals
      FROM ${tableName}
      WHERE date >= CURRENT_DATE - INTERVAL '30 days'
    `;

    const result = await query(sqlQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      success: true,
      data: result.rows[0],
      timeframe,
      period: 'last_30_days'
    });

  } catch (error) {
    console.error('Error fetching signals summary:', error);
    res.status(500).json({ 
      error: 'Failed to fetch signals summary',
      message: error.message 
    });  }
});

// Get swing trading signals
router.get('/swing-signals', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;

    const swingQuery = `
      SELECT 
        st.symbol,
        cp.short_name as company_name,
        st.signal,
        st.entry_price,
        st.stop_loss,
        st.target_price,
        st.risk_reward_ratio,
        st.date,
        md.regular_market_price as current_price,
        CASE 
          WHEN st.signal = 'BUY' AND md.regular_market_price >= st.target_price 
          THEN 'TARGET_HIT'
          WHEN st.signal = 'BUY' AND md.regular_market_price <= st.stop_loss 
          THEN 'STOP_LOSS_HIT'
          WHEN st.signal = 'SELL' AND md.regular_market_price <= st.target_price 
          THEN 'TARGET_HIT'
          WHEN st.signal = 'SELL' AND md.regular_market_price >= st.stop_loss 
          THEN 'STOP_LOSS_HIT'
          ELSE 'ACTIVE'
        END as status
      FROM swing_trader st
      JOIN company_profile cp ON st.symbol = cp.ticker
      LEFT JOIN market_data md ON st.symbol = md.ticker
      ORDER BY st.date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM swing_trader
    `;

    const [swingResult, countResult] = await Promise.all([
      query(swingQuery, [limit, offset]),
      query(countQuery)
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (!swingResult || !Array.isArray(swingResult.rows) || swingResult.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: swingResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      }
    });

  } catch (error) {
    console.error('Error fetching swing signals:', error);
    res.status(500).json({ error: 'Failed to fetch swing signals' });
  }
});

// Get technical indicators for a stock
router.get('/:ticker/technicals', async (req, res) => {
  try {
    const { ticker } = req.params;
    const timeframe = req.query.timeframe || 'daily'; // daily, weekly, monthly

    let tableName = 'latest_technicals_daily';
    if (timeframe === 'weekly') tableName = 'latest_technicals_weekly';
    if (timeframe === 'monthly') tableName = 'latest_technicals_monthly';

    const techQuery = `
      SELECT 
        symbol,
        date,
        sma_20,
        sma_50,
        sma_200,
        ema_12,
        ema_26,
        rsi_14,
        macd,
        macd_signal,
        macd_histogram,
        bb_upper,
        bb_middle,
        bb_lower,
        volume_sma
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `;

    const result = await query(techQuery, [ticker.toUpperCase()]);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      ticker: ticker.toUpperCase(),
      timeframe,
      data: result.rows[0]
    });

  } catch (error) {
    console.error('Error fetching technical indicators:', error);
    res.status(500).json({ error: 'Failed to fetch technical indicators' });
  }
});

// Get performance summary of recent signals
router.get('/performance', async (req, res) => {
  try {
    const days = parseInt(req.query.days) || 30;

    const performanceQuery = `
      SELECT 
        signal,
        COUNT(*) as total_signals,
        AVG(
          CASE 
            WHEN signal = 'BUY' AND md.regular_market_price > bs.price 
            THEN ((md.regular_market_price - bs.price) / bs.price * 100)
            WHEN signal = 'SELL' AND md.regular_market_price < bs.price 
            THEN ((bs.price - md.regular_market_price) / bs.price * 100)
            ELSE 0
          END
        ) as avg_performance,
        COUNT(
          CASE 
            WHEN signal = 'BUY' AND md.regular_market_price > bs.price THEN 1
            WHEN signal = 'SELL' AND md.regular_market_price < bs.price THEN 1
          END
        ) as winning_trades,
        (COUNT(
          CASE 
            WHEN signal = 'BUY' AND md.regular_market_price > bs.price THEN 1
            WHEN signal = 'SELL' AND md.regular_market_price < bs.price THEN 1
          END
        ) * 100.0 / COUNT(*)) as win_rate
      FROM latest_buy_sell_daily bs
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      WHERE bs.date >= NOW() - INTERVAL '${days} days'
      GROUP BY signal
    `;

    const result = await query(performanceQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      period_days: days,
      performance: result.rows,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching performance data:', error);
    res.status(500).json({ error: 'Failed to fetch performance data' });
  }
});

module.exports = router;

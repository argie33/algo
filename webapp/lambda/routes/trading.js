const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Get latest buy/sell signals
router.get('/signals', async (req, res) => {
  try {
    const timeframe = req.query.timeframe || 'daily'; // daily, weekly, monthly
    const signal = req.query.signal || 'all'; // buy, sell, all
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;

    let tableName = 'latest_buy_sell_daily';
    if (timeframe === 'weekly') tableName = 'latest_buy_sell_weekly';
    if (timeframe === 'monthly') tableName = 'latest_buy_sell_monthly';

    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramCount = 0;

    if (signal === 'buy') {
      whereClause += ` AND signal = 'BUY'`;
    } else if (signal === 'sell') {
      whereClause += ` AND signal = 'SELL'`;
    }

    const signalsQuery = `
      SELECT 
        bs.symbol,
        cp.short_name as company_name,
        bs.signal,
        bs.date,
        bs.price,
        md.regular_market_price as current_price,
        CASE 
          WHEN bs.signal = 'BUY' AND md.regular_market_price > bs.price 
          THEN ((md.regular_market_price - bs.price) / bs.price * 100)
          WHEN bs.signal = 'SELL' AND md.regular_market_price < bs.price 
          THEN ((bs.price - md.regular_market_price) / bs.price * 100)
          ELSE 0
        END as performance_percent
      FROM ${tableName} bs
      JOIN company_profile cp ON bs.symbol = cp.ticker
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      ${whereClause}
      ORDER BY bs.date DESC
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName} bs
      ${whereClause}
    `;

    const [signalsResult, countResult] = await Promise.all([
      query(signalsQuery, params),
      query(countQuery, params.slice(0, -2))
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.json({
      data: signalsResult.rows,
      timeframe,
      signal,
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
    console.error('Error fetching trading signals:', error);
    res.status(500).json({ error: 'Failed to fetch trading signals' });
  }
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

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Technical data not found' });
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

/**
 * Swing Trading Algo API Routes
 *
 * Endpoints:
 * - GET /api/algo/status - Current algo status
 * - GET /api/algo/evaluate - Run signal evaluation
 * - GET /api/algo/positions - Get active positions
 * - GET /api/algo/trades - Get trade history
 * - GET /api/algo/config - Get current configuration
 * - POST /api/algo/config/:key - Update configuration (admin only)
 */

const express = require('express');
const { getPool } = require('../utils/database');

const router = express.Router();

/**
 * GET /api/algo/status
 * Current algo system status
 */
router.get('/status', async (req, res) => {
  try {
    const pool = getPool();

    // Get latest portfolio snapshot
    const snapshotResult = await pool.query(`
      SELECT
        snapshot_date,
        total_portfolio_value,
        position_count,
        unrealized_pnl_pct,
        daily_return_pct,
        market_health_status
      FROM algo_portfolio_snapshots
      ORDER BY snapshot_date DESC
      LIMIT 1
    `);

    const snapshot = snapshotResult.rows[0] || {
      position_count: 0,
      unrealized_pnl_pct: 0,
      daily_return_pct: 0
    };

    // Get active positions count
    const posResult = await pool.query(`
      SELECT COUNT(*) as open_count, SUM(position_value) as total_value
      FROM algo_positions
      WHERE status = 'open'
    `);

    const positions = posResult.rows[0] || { open_count: 0, total_value: 0 };

    // Get market health
    const healthResult = await pool.query(`
      SELECT market_trend, market_stage, distribution_days_4w, vix_level
      FROM market_health_daily
      ORDER BY date DESC
      LIMIT 1
    `);

    const health = healthResult.rows[0] || {
      market_trend: 'unknown',
      market_stage: 1,
      distribution_days_4w: 0,
      vix_level: 0
    };

    return res.json({
      success: true,
      data: {
        algo_enabled: true,
        execution_mode: 'paper',
        status: 'operational',
        portfolio: {
          total_value: snapshot.total_portfolio_value || 0,
          position_count: positions.open_count,
          total_position_value: positions.total_value || 0,
          unrealized_pnl_pct: snapshot.unrealized_pnl_pct || 0,
          daily_return_pct: snapshot.daily_return_pct || 0
        },
        market: {
          trend: health.market_trend,
          stage: health.market_stage,
          distribution_days: health.distribution_days_4w || 0,
          vix: health.vix_level || 0
        },
        timestamp: new Date()
      },
      timestamp: new Date()
    });
  } catch (error) {
    console.error('Error in /algo/status:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date()
    });
  }
});

/**
 * GET /api/algo/evaluate
 * Run signal evaluation (latest date with buy signals)
 */
router.get('/evaluate', async (req, res) => {
  try {
    const pool = getPool();

    // Get latest buy signals
    const signalResult = await pool.query(`
      SELECT symbol, date, signal, entry_price
      FROM buy_sell_daily
      WHERE signal = 'BUY'
      ORDER BY date DESC, symbol
      LIMIT 50
    `);

    const signals = signalResult.rows;

    // For each signal, get evaluation status
    const evaluated = [];
    for (const sig of signals) {
      // Check trend template
      const trendResult = await pool.query(`
        SELECT minervini_trend_score, percent_from_52w_low, percent_from_52w_high
        FROM trend_template_data
        WHERE symbol = $1 AND date = $2
        LIMIT 1
      `, [sig.symbol, sig.date]);

      // Check completeness
      const completeResult = await pool.query(`
        SELECT composite_completeness_pct
        FROM data_completeness_scores
        WHERE symbol = $1
        LIMIT 1
      `, [sig.symbol]);

      // Check SQS
      const sqsResult = await pool.query(`
        SELECT composite_sqs
        FROM signal_quality_scores
        WHERE symbol = $1 AND date = $2
        LIMIT 1
      `, [sig.symbol, sig.date]);

      const trend = trendResult.rows[0];
      const completeness = completeResult.rows[0];
      const sqs = sqsResult.rows[0];

      // Determine if passes all tiers
      const passes = {
        tier1: completeness && completeness.composite_completeness_pct >= 70,
        tier3: trend && trend.minervini_trend_score >= 8,
        tier4: sqs && sqs.composite_sqs >= 60
      };

      evaluated.push({
        symbol: sig.symbol,
        date: sig.date,
        entry_price: sig.entry_price,
        trend_score: trend ? trend.minervini_trend_score : 0,
        pct_from_52w_low: trend ? trend.percent_from_52w_low : 0,
        completeness_pct: completeness ? completeness.composite_completeness_pct : 0,
        sqs: sqs ? sqs.composite_sqs : 0,
        tier1_pass: passes.tier1,
        tier3_pass: passes.tier3,
        tier4_pass: passes.tier4,
        all_tiers_pass: passes.tier1 && passes.tier3 && passes.tier4
      });
    }

    // Sort by SQS, select top 12
    const qualified = evaluated.filter(e => e.all_tiers_pass).sort((a, b) => b.sqs - a.sqs).slice(0, 12);

    return res.json({
      success: true,
      data: {
        total_buy_signals: signals.length,
        qualified_for_trading: qualified.length,
        signals: evaluated,
        top_qualified: qualified
      },
      timestamp: new Date()
    });
  } catch (error) {
    console.error('Error in /algo/evaluate:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date()
    });
  }
});

/**
 * GET /api/algo/positions
 * Get active positions
 */
router.get('/positions', async (req, res) => {
  try {
    const pool = getPool();

    const result = await pool.query(`
      SELECT
        position_id,
        symbol,
        quantity,
        avg_entry_price,
        current_price,
        position_value,
        unrealized_pnl,
        unrealized_pnl_pct,
        status,
        stage_in_exit_plan,
        days_since_entry
      FROM algo_positions
      WHERE status = 'open'
      ORDER BY position_value DESC
    `);

    return res.json({
      success: true,
      items: result.rows.map(row => ({
        ...row,
        avg_entry_price: parseFloat(row.avg_entry_price),
        current_price: parseFloat(row.current_price),
        position_value: parseFloat(row.position_value),
        unrealized_pnl: parseFloat(row.unrealized_pnl),
        unrealized_pnl_pct: parseFloat(row.unrealized_pnl_pct)
      })),
      pagination: {
        total: result.rows.length,
        count: result.rows.length
      },
      timestamp: new Date()
    });
  } catch (error) {
    console.error('Error in /algo/positions:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date()
    });
  }
});

/**
 * GET /api/algo/trades
 * Get trade history
 */
router.get('/trades', async (req, res) => {
  try {
    const pool = getPool();
    const limit = parseInt(req.query.limit) || 50;
    const offset = parseInt(req.query.offset) || 0;

    const result = await pool.query(`
      SELECT
        trade_id,
        symbol,
        signal_date,
        trade_date,
        entry_price,
        entry_quantity,
        status,
        exit_date,
        exit_price,
        exit_r_multiple,
        profit_loss_pct,
        trade_duration_days
      FROM algo_trades
      ORDER BY trade_date DESC
      LIMIT $1 OFFSET $2
    `, [limit, offset]);

    const countResult = await pool.query('SELECT COUNT(*) as total FROM algo_trades');

    return res.json({
      success: true,
      items: result.rows.map(row => ({
        ...row,
        entry_price: parseFloat(row.entry_price),
        exit_price: row.exit_price ? parseFloat(row.exit_price) : null,
        profit_loss_pct: parseFloat(row.profit_loss_pct || 0)
      })),
      pagination: {
        total: parseInt(countResult.rows[0].total),
        limit,
        offset,
        page: Math.floor(offset / limit) + 1,
        totalPages: Math.ceil(parseInt(countResult.rows[0].total) / limit)
      },
      timestamp: new Date()
    });
  } catch (error) {
    console.error('Error in /algo/trades:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date()
    });
  }
});

/**
 * GET /api/algo/config
 * Get current configuration
 */
router.get('/config', async (req, res) => {
  try {
    const pool = getPool();

    const result = await pool.query(`
      SELECT key, value, value_type, description
      FROM algo_config
      ORDER BY key
    `);

    const config = {};
    result.rows.forEach(row => {
      let parsedValue = row.value;
      if (row.value_type === 'int') {
        parsedValue = parseInt(row.value);
      } else if (row.value_type === 'float') {
        parsedValue = parseFloat(row.value);
      } else if (row.value_type === 'bool') {
        parsedValue = ['true', '1', 'yes'].includes(row.value.toLowerCase());
      }
      config[row.key] = {
        value: parsedValue,
        type: row.value_type,
        description: row.description
      };
    });

    return res.json({
      success: true,
      data: config,
      timestamp: new Date()
    });
  } catch (error) {
    console.error('Error in /algo/config:', error);
    return res.status(500).json({
      success: false,
      error: error.message,
      timestamp: new Date()
    });
  }
});

module.exports = router;

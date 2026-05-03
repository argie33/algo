const express = require('express');
const { query } = require('../utils/database');
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const { authenticateToken } = require('../middleware/auth');
const logger = require('../utils/logger');

const router = express.Router();
const requireAuth = authenticateToken;

/**
 * GET /api/research/backtests
 * List all backtest runs with pagination
 */
router.get('/', async (req, res, next) => {
  try {
    const {
      strategy_name,
      limit = 50,
      offset = 0,
      sort_by = 'run_timestamp',
      order = 'DESC'
    } = req.query;

    const allowed_sorts = ['run_timestamp', 'total_signals', 'win_rate', 'expectancy_per_trade', 'sharpe'];
    const sort_col = allowed_sorts.includes(sort_by) ? sort_by : 'run_timestamp';
    const sort_order = order.toUpperCase() === 'ASC' ? 'ASC' : 'DESC';

    let q = `
      SELECT
        br.run_id, br.run_name, br.run_timestamp,
        br.strategy_name, br.strategy_method,
        br.date_start, br.date_end,
        br.total_signals, br.winning_trades, br.losing_trades, br.scratch_trades,
        br.win_rate, br.avg_win_pct, br.avg_loss_pct, br.win_loss_ratio,
        br.expectancy_per_trade, br.total_return_pct, br.max_drawdown_pct,
        br.sharpe, br.sortino, br.profit_factor,
        br.notes, br.status
      FROM backtest_runs br
    `;

    const params = [];
    let paramCount = 0;

    if (strategy_name) {
      paramCount++;
      q += ` WHERE br.strategy_name = $${paramCount}`;
      params.push(strategy_name);
    }

    q += ` ORDER BY br.${sort_col} ${sort_order}`;
    q += ` LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}`;

    // Parallelize data and count queries
    let countQ = 'SELECT COUNT(*) as total FROM backtest_runs br';
    if (strategy_name) {
      countQ += ` WHERE br.strategy_name = $1`;
    }

    const [result, countResult] = await Promise.all([
      query(q, [...params, parseInt(limit), parseInt(offset)]),
      query(countQ, strategy_name ? [strategy_name] : [])
    ]);
    const total = countResult.rows[0].total;

    return sendPaginated(res, result.rows, {
      limit: parseInt(limit),
      offset: parseInt(offset),
      total,
      page: Math.floor(parseInt(offset) / parseInt(limit)) + 1,
      totalPages: Math.ceil(total / parseInt(limit)),
      hasNext: parseInt(offset) + parseInt(limit) < total,
      hasPrev: parseInt(offset) > 0
    });
  } catch (error) {
    logger.error("Error fetching backtests", error);
    return sendError(res, 500, "Failed to fetch backtests", "DB_ERROR");
  }
});

/**
 * GET /api/research/backtests/:run_id
 * Get detailed backtest run with trades
 */
router.get('/:run_id', async (req, res, next) => {
  try {
    const { run_id } = req.params;
    const { limit = 100, offset = 0 } = req.query;

    // Get run details
    const runQ = `
      SELECT * FROM backtest_runs WHERE run_id = $1
    `;
    const runResult = await query(runQ, [run_id]);

    if (runResult.rows.length === 0) {
      return sendError(res, 404, 'Backtest run not found', 'NOT_FOUND');
    }

    const run = runResult.rows[0];

    // Parallelize trades and trade count queries
    const tradesQ = `
      SELECT
        bt.trade_id, bt.run_id, bt.symbol, bt.signal_date, bt.exit_date,
        bt.signal_type, bt.entry_price, bt.exit_price, bt.return_pct,
        bt.outcome, bt.exit_reason, bt.mfe_pct, bt.mae_pct, bt.days_held
      FROM backtest_trades bt
      WHERE bt.run_id = $1
      ORDER BY bt.signal_date DESC
      LIMIT $2 OFFSET $3
    `;
    const tradeCountQ = `SELECT COUNT(*) as total FROM backtest_trades WHERE run_id = $1`;

    const [tradesResult, tradeCountResult] = await Promise.all([
      query(tradesQ, [run_id, parseInt(limit), parseInt(offset)]),
      query(tradeCountQ, [run_id])
    ]);
    const tradeTotal = tradeCountResult.rows[0].total;

    res.json({
      success: true,
      run,
      trades: tradesResult.rows,
      trade_pagination: {
        limit: parseInt(limit),
        offset: parseInt(offset),
        total: tradeTotal,
        page: Math.floor(parseInt(offset) / parseInt(limit)) + 1,
        totalPages: Math.ceil(tradeTotal / parseInt(limit)),
        hasNext: parseInt(offset) + parseInt(limit) < tradeTotal,
        hasPrev: parseInt(offset) > 0
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    logger.error("Error fetching backtest run", error);
    return sendError(res, 500, "Failed to fetch backtest run", "DB_ERROR");
  }
});

/**
 * POST /api/research/backtests
 * Create a new backtest run record (used by backtest.py)
 */
router.post('/', requireAuth, async (req, res, next) => {
  try {
    const {
      run_name,
      strategy_name,
      strategy_method,
      parameters,
      date_start,
      date_end,
      total_signals,
      winning_trades,
      losing_trades,
      scratch_trades,
      win_rate,
      avg_win_pct,
      avg_loss_pct,
      win_loss_ratio,
      expectancy_per_trade,
      total_return_pct,
      max_drawdown_pct,
      sharpe,
      sortino,
      profit_factor,
      equity_curve,
      notes
    } = req.body;

    const insertQ = `
      INSERT INTO backtest_runs (
        run_name, strategy_name, strategy_method, parameters,
        date_start, date_end,
        total_signals, winning_trades, losing_trades, scratch_trades,
        win_rate, avg_win_pct, avg_loss_pct, win_loss_ratio,
        expectancy_per_trade, total_return_pct, max_drawdown_pct,
        sharpe, sortino, profit_factor, equity_curve, notes, status
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23)
      RETURNING run_id
    `;

    const result = await query(insertQ, [
      run_name, strategy_name, strategy_method, JSON.stringify(parameters),
      date_start, date_end,
      total_signals, winning_trades, losing_trades, scratch_trades,
      win_rate, avg_win_pct, avg_loss_pct, win_loss_ratio,
      expectancy_per_trade, total_return_pct, max_drawdown_pct,
      sharpe, sortino, profit_factor, JSON.stringify(equity_curve), notes, 'completed'
    ]);

    return sendSuccess(res, {
      run_id: result.rows[0].run_id
    }, "Backtest created successfully", 201);
  } catch (error) {
    logger.error("Error creating backtest", error);
    return sendError(res, 500, "Failed to create backtest", "DB_ERROR");
  }
});

module.exports = router;

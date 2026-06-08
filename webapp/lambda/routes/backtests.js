const express = require('express');
const { query } = require('../utils/database');
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const { authenticateToken } = require('../middleware/auth');
const logger = require('../utils/logger');
const paginationConfig = require('../config/pagination');
const { validateQueryResult, validateAndCoerceRows, extractCount } = require('../utils/responseValidation');

const router = express.Router();
const requireAuth = authenticateToken;

/**
 * GET /api/research/backtests
 * List all backtest runs with pagination
 */
router.get('/', requireAuth, async (req, res, next) => {
  try {
    const {
      strategy_name,
      limit = 50,
      offset = 0,
      sort_by = 'run_timestamp',
      order = 'DESC'
    } = req.query;

    const allowed_sorts = ['run_timestamp', 'total_signals', 'win_rate', 'expectancy_per_trade', 'sharpe_annualized'];
    const sort_col = allowed_sorts.includes(sort_by) ? sort_by : 'run_timestamp';
    const sort_order = order.toUpperCase() === 'ASC' ? 'ASC' : 'DESC';

    let q = `
      SELECT
        br.run_id, br.run_name, br.run_timestamp,
        br.strategy_name, br.start_date, br.end_date,
        br.num_trades, br.num_winning_trades, br.num_losing_trades,
        br.win_rate, br.avg_win, br.avg_loss,
        br.total_return, br.max_drawdown,
        br.sharpe_ratio AS sharpe, br.sortino_ratio, br.profit_factor
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
    validateQueryResult(result, { requireRows: false });
    const total = extractCount(countResult, 'total');

    const validated = validateAndCoerceRows(result, {
      run_id: { type: 'int', required: true },
      run_name: { type: 'string', required: true },
      run_timestamp: { type: 'date' },
      strategy_name: { type: 'string', required: true },
      start_date: { type: 'date' },
      end_date: { type: 'date' },
      num_trades: { type: 'int' },
      num_winning_trades: { type: 'int' },
      num_losing_trades: { type: 'int' },
      win_rate: { type: 'float' },
      avg_win: { type: 'float' },
      avg_loss: { type: 'float' },
      total_return: { type: 'float' },
      max_drawdown: { type: 'float' },
      sharpe: { type: 'float' },
      sortino_ratio: { type: 'float' },
      profit_factor: { type: 'float' }
    });

    return sendPaginated(res, validated, {
      limit: parseInt(limit),
      offset: parseInt(offset),
      total,
      page: Math.floor(parseInt(offset) / parseInt(limit)) + 1,
      totalPages: Math.ceil(total / parseInt(limit)),
      hasNext: parseInt(offset) + parseInt(limit) < total,
      hasPrev: parseInt(offset) > 0
    });
  } catch (error) {
    console.error("Error fetching backtests", error);
    return sendError(res, "Failed to fetch backtests", 500);
  }
});

/**
 * GET /api/research/backtests/:run_id
 * Get detailed backtest run with trades
 */
router.get('/:run_id', requireAuth, async (req, res, next) => {
  try {
    const { run_id } = req.params;
    const { limit, offset } = paginationConfig.sanitize(req.query.limit, req.query.offset, 'trades');

    // Get run details
    const runQ = `
      SELECT * FROM backtest_runs WHERE run_id = $1
    `;
    const runResult = await query(runQ, [run_id]);

    if (runResult.rows.length === 0) {
      return sendError(res, 'Backtest run not found', 404);
    }

    const run = runResult.rows[0];

    // Parallelize trades and trade count queries
    const tradesQ = `
      SELECT
        bt.id as trade_id, bt.run_id, bt.symbol,
        bt.entry_date, bt.exit_date,
        bt.entry_price, bt.exit_price,
        bt.profit_loss_pct as return_pct,
        bt.trade_outcome as outcome,
        bt.exit_reason,
        bt.holding_days as days_held,
        bt.quantity, bt.profit_loss
      FROM backtest_trades bt
      WHERE bt.run_id = $1
      ORDER BY bt.entry_date DESC
      LIMIT $2 OFFSET $3
    `;
    const tradeCountQ = `SELECT COUNT(*) as total FROM backtest_trades WHERE run_id = $1`;

    const [tradesResult, tradeCountResult] = await Promise.all([
      query(tradesQ, [run_id, parseInt(limit), parseInt(offset)]),
      query(tradeCountQ, [run_id])
    ]);
    validateQueryResult(tradesResult, { requireRows: false });
    const tradeTotal = extractCount(tradeCountResult, 'total');

    const validatedTrades = validateAndCoerceRows(tradesResult, {
      trade_id: { type: 'int', required: true },
      run_id: { type: 'int', required: true },
      symbol: { type: 'string', required: true },
      entry_date: { type: 'date' },
      exit_date: { type: 'date' },
      entry_price: { type: 'float' },
      exit_price: { type: 'float' },
      return_pct: { type: 'float' },
      outcome: { type: 'string' },
      exit_reason: { type: 'string' },
      days_held: { type: 'int' },
      quantity: { type: 'float' },
      profit_loss: { type: 'float' }
    });

    return sendSuccess(res, {
      run,
      trades: validatedTrades,
      trade_pagination: {
        limit: parseInt(limit),
        offset: parseInt(offset),
        total: tradeTotal,
        page: Math.floor(parseInt(offset) / parseInt(limit)) + 1,
        totalPages: Math.ceil(tradeTotal / parseInt(limit)),
        hasNext: parseInt(offset) + parseInt(limit) < tradeTotal,
        hasPrev: parseInt(offset) > 0
      }
    });
  } catch (error) {
    console.error("Error fetching backtest run", error);
    return sendError(res, "Failed to fetch backtest run: " + error.message, 500);
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
      date_start,
      date_end,
      total_signals,
      total_trades,
      winning_trades,
      losing_trades,
      win_rate,
      avg_win_pct,
      avg_loss_pct,
      avg_hold_days,
      expectancy_per_trade,
      total_return_pct,
      max_drawdown_pct,
      sharpe,
      sortino,
      calmar_ratio,
      profit_factor,
      notes
    } = req.body;

    // INPUT VALIDATION
    if (!run_name || !strategy_name) {
      return sendError(res, "run_name and strategy_name are required", 400);
    }

    // Validate string lengths
    if (run_name.length > 255) {
      return sendError(res, "run_name must be <= 255 characters", 400);
    }
    if (strategy_name.length > 100) {
      return sendError(res, "strategy_name must be <= 100 characters", 400);
    }

    // Validate dates
    if (date_start && date_end) {
      const start = new Date(date_start);
      const end = new Date(date_end);
      if (isNaN(start.getTime()) || isNaN(end.getTime())) {
        return sendError(res, "date_start and date_end must be valid dates", 400);
      }
      if (start > end) {
        return sendError(res, "date_start must be before date_end", 400);
      }
    }

    // Validate numeric fields are non-negative
    const numericFields = {
      total_signals: [total_signals, 0, 1000000],
      total_trades: [total_trades, 0, 1000000],
      winning_trades: [winning_trades, 0, total_trades || 1000000],
      losing_trades: [losing_trades, 0, total_trades || 1000000],
      win_rate: [win_rate, 0, 100],
      avg_win_pct: [avg_win_pct, -100, 100],
      avg_loss_pct: [avg_loss_pct, -100, 100],
      avg_hold_days: [avg_hold_days, 0, 10000],
      expectancy_per_trade: [expectancy_per_trade, -100000, 100000],
      total_return_pct: [total_return_pct, -100000, 100000],
      max_drawdown_pct: [max_drawdown_pct, 0, 100],
      sharpe: [sharpe, -100, 100],
      sortino: [sortino, -100, 100],
      calmar_ratio: [calmar_ratio, -100, 100],
      profit_factor: [profit_factor, 0, 100]
    };

    for (const [field, [value, min, max]] of Object.entries(numericFields)) {
      if (value !== null && value !== undefined && value !== '') {
        const num = parseFloat(value);
        if (isNaN(num) || num < min || num > max) {
          return sendError(res, `${field} must be a number between ${min} and ${max}`, 400);
        }
      }
    }

    // Validate notes length
    if (notes && notes.length > 5000) {
      return sendError(res, "notes must be <= 5000 characters", 400);
    }

    const insertQ = `
      INSERT INTO backtest_runs (
        run_name, strategy_name,
        date_start, date_end,
        total_signals, total_trades, winning_trades, losing_trades,
        win_rate, avg_win_pct, avg_loss_pct, avg_hold_days,
        expectancy_per_trade, total_return_pct, max_drawdown_pct,
        sharpe_annualized, sortino_annualized, calmar_ratio, profit_factor, notes
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
      RETURNING run_id
    `;

    const result = await query(insertQ, [
      run_name, strategy_name,
      date_start, date_end,
      total_signals, total_trades, winning_trades, losing_trades,
      win_rate, avg_win_pct, avg_loss_pct, avg_hold_days,
      expectancy_per_trade, total_return_pct, max_drawdown_pct,
      sharpe, sortino, calmar_ratio, profit_factor, notes
    ]);

    return sendSuccess(res, {
      run_id: result.rows[0].run_id
    }, "Backtest created successfully", 201);
  } catch (error) {
    logger.error("Error creating backtest", error);
    return sendError(res, "Failed to create backtest: " + error.message, 500);
  }
});

module.exports = router;

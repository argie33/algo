/**
 * Performance Metrics Endpoint
 *
 * Returns daily/weekly/monthly performance statistics:
 * - Sharpe ratio, max drawdown, win rate, Profit Factor, Calmar ratio
 * - Updated daily from algo_trades table
 */

const express = require("express");

const { sendSuccess, sendError } = require("../utils/apiResponse");
const { authenticateToken } = require("../middleware/auth");
const {
  validateQueryResult,
  validateAndCoerceRow,
} = require("../utils/responseValidation");
const logger = require("../utils/logger");
const { query } = require("../utils/database");

const router = express.Router();
router.use(authenticateToken);

async function getPerformanceMetrics(req, res) {
  try {
    const { period = "week" } = req.query;

    // PHASE 1 FIX: Fetch pre-computed metrics from algo_performance_daily
    // Period-specific queries will be added as new pre-computed tables if needed
    // For now, fetch all-time metrics from algo_performance_daily (O(1) lookup)
    const result = await query(`
      SELECT
        total_trades, num_wins as win_count, num_losses as loss_count,
        CASE WHEN total_trades > 0 THEN ROUND(100.0 * num_wins / total_trades, 2) ELSE 0 END as win_rate_pct,
        gross_win_dollars as gross_profit,
        gross_loss_dollars as gross_loss,
        profit_factor,
        total_pnl_dollars as total_pnl,
        CASE WHEN total_trades > 0 THEN ROUND(total_pnl_dollars / total_trades, 2) ELSE 0 END as avg_pnl_per_trade,
        CASE WHEN avg_win_pct IS NOT NULL THEN ROUND(avg_win_pct / 100, 4) ELSE NULL END as avg_return_pct,
        avg_win,
        avg_loss,
        avg_win_pct,
        avg_loss_pct,
        avg_hold_days,
        avg_r as avg_r_multiple,
        rolling_sharpe_252d as sharpe_ratio,
        max_drawdown_pct as max_drawdown,
        calmar_ratio,
        biggest_win,
        biggest_loss,
        best_trade_r,
        worst_trade_r
      FROM algo_performance_daily
      WHERE report_date = CURRENT_DATE
      ORDER BY report_date DESC LIMIT 1
    `);

    validateQueryResult(result, { requireRows: false });

    if (result.rows.length === 0) {
      logger.warn("No performance data available for today");
      return sendSuccess(res, {
        period,
        summary: {
          total_trades: 0,
          win_count: 0,
          loss_count: 0,
          breakeven_count: 0,
          win_rate_pct: 0,
        },
        profitability: {
          gross_profit: 0,
          gross_loss: 0,
          profit_factor: 0,
          total_pnl: 0,
          avg_pnl_per_trade: 0,
          avg_return_pct: 0,
          biggest_win: 0,
          biggest_loss: 0,
        },
        trade_quality: {
          avg_win: 0,
          avg_loss: 0,
          avg_win_pct: 0,
          avg_loss_pct: 0,
          avg_hold_days: 0,
          avg_r_multiple: 0,
          best_trade_r: 0,
          worst_trade_r: 0,
        },
        risk_metrics: {
          sharpe_ratio: 0,
          max_drawdown: 0,
          calmar_ratio: 0,
        },
      });
    }

    const metrics = validateAndCoerceRow(result.rows[0], {
      total_trades: { type: "int", required: false },
      win_count: { type: "int", required: false },
      loss_count: { type: "int", required: false },
      win_rate_pct: { type: "float", required: false },
      gross_profit: { type: "float", required: false },
      gross_loss: { type: "float", required: false },
      profit_factor: { type: "float", required: false },
      total_pnl: { type: "float", required: false },
      avg_pnl_per_trade: { type: "float", required: false },
      avg_return_pct: { type: "float", required: false },
      avg_win: { type: "float", required: false },
      avg_loss: { type: "float", required: false },
      avg_win_pct: { type: "float", required: false },
      avg_loss_pct: { type: "float", required: false },
      avg_hold_days: { type: "float", required: false },
      avg_r_multiple: { type: "float", required: false },
      sharpe_ratio: { type: "float", required: false },
      max_drawdown: { type: "float", required: false },
      calmar_ratio: { type: "float", required: false },
      biggest_win: { type: "float", required: false },
      biggest_loss: { type: "float", required: false },
      best_trade_r: { type: "float", required: false },
      worst_trade_r: { type: "float", required: false },
    });

    // CRITICAL: Validate essential performance metrics are present
    const criticalMetrics = [
      "win_rate_pct",
      "total_pnl",
      "sharpe_ratio",
      "max_drawdown",
      "profit_factor",
    ];
    const missingCritical = criticalMetrics.filter(
      (m) => metrics[m] === null || metrics[m] === undefined
    );
    if (missingCritical.length > 0) {
      logger.error(
        `CRITICAL: Performance metrics incomplete. Missing: ${missingCritical.join(", ")}`
      );
      return sendError(
        res,
        `Performance metrics unavailable (incomplete data: ${missingCritical.join(", ")}). ` +
          "Ensure algo has completed at least one full trading cycle with closed trades.",
        503
      );
    }

    const response = {
      period,
      summary: {
        total_trades:
          metrics.total_trades !== null && metrics.total_trades !== undefined
            ? metrics.total_trades
            : null,
        win_count:
          metrics.win_count !== null && metrics.win_count !== undefined
            ? metrics.win_count
            : null,
        loss_count:
          metrics.loss_count !== null && metrics.loss_count !== undefined
            ? metrics.loss_count
            : null,
        breakeven_count:
          (metrics.total_trades !== null && metrics.total_trades !== undefined
            ? metrics.total_trades
            : 0) -
          (metrics.win_count !== null && metrics.win_count !== undefined
            ? metrics.win_count
            : 0) -
          (metrics.loss_count !== null && metrics.loss_count !== undefined
            ? metrics.loss_count
            : 0),
        win_rate_pct:
          metrics.win_rate_pct !== null && metrics.win_rate_pct !== undefined
            ? metrics.win_rate_pct
            : null,
      },
      profitability: {
        gross_profit:
          metrics.gross_profit !== null && metrics.gross_profit !== undefined
            ? metrics.gross_profit
            : null,
        gross_loss:
          metrics.gross_loss !== null && metrics.gross_loss !== undefined
            ? metrics.gross_loss
            : null,
        profit_factor:
          metrics.profit_factor !== null && metrics.profit_factor !== undefined
            ? metrics.profit_factor
            : null,
        total_pnl:
          metrics.total_pnl !== null && metrics.total_pnl !== undefined
            ? metrics.total_pnl
            : null,
        avg_pnl_per_trade:
          metrics.avg_pnl_per_trade !== null &&
          metrics.avg_pnl_per_trade !== undefined
            ? metrics.avg_pnl_per_trade
            : null,
        avg_return_pct:
          metrics.avg_return_pct !== null &&
          metrics.avg_return_pct !== undefined
            ? metrics.avg_return_pct
            : null,
        biggest_win:
          metrics.biggest_win !== null && metrics.biggest_win !== undefined
            ? metrics.biggest_win
            : null,
        biggest_loss:
          metrics.biggest_loss !== null && metrics.biggest_loss !== undefined
            ? metrics.biggest_loss
            : null,
      },
      trade_quality: {
        avg_win:
          metrics.avg_win !== null && metrics.avg_win !== undefined
            ? metrics.avg_win
            : null,
        avg_loss:
          metrics.avg_loss !== null && metrics.avg_loss !== undefined
            ? metrics.avg_loss
            : null,
        avg_win_pct:
          metrics.avg_win_pct !== null && metrics.avg_win_pct !== undefined
            ? metrics.avg_win_pct
            : null,
        avg_loss_pct:
          metrics.avg_loss_pct !== null && metrics.avg_loss_pct !== undefined
            ? metrics.avg_loss_pct
            : null,
        avg_hold_days:
          metrics.avg_hold_days !== null && metrics.avg_hold_days !== undefined
            ? metrics.avg_hold_days
            : null,
        avg_r_multiple:
          metrics.avg_r_multiple !== null &&
          metrics.avg_r_multiple !== undefined
            ? metrics.avg_r_multiple
            : null,
        best_trade_r:
          metrics.best_trade_r !== null && metrics.best_trade_r !== undefined
            ? metrics.best_trade_r
            : null,
        worst_trade_r:
          metrics.worst_trade_r !== null && metrics.worst_trade_r !== undefined
            ? metrics.worst_trade_r
            : null,
      },
      risk_metrics: {
        sharpe_ratio:
          metrics.sharpe_ratio !== null && metrics.sharpe_ratio !== undefined
            ? metrics.sharpe_ratio
            : null,
        max_drawdown:
          metrics.max_drawdown !== null && metrics.max_drawdown !== undefined
            ? metrics.max_drawdown
            : null,
        calmar_ratio:
          metrics.calmar_ratio !== null && metrics.calmar_ratio !== undefined
            ? metrics.calmar_ratio
            : null,
      },
    };

    return sendSuccess(res, response);
  } catch (error) {
    logger.error("Error fetching performance metrics:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(res, "Failed to fetch performance metrics", 500);
  }
}

async function getRecentTrades(req, res) {
  try {
    const { limit = 20 } = req.query;

    const tradesQuery = `
      SELECT
        trade_id, symbol, trade_date AS entry_date, entry_price, exit_date, exit_price,
        profit_loss_dollars, profit_loss_pct, trade_duration_days,
        exit_r_multiple, status
      FROM algo_trades
      WHERE status = 'closed'
      ORDER BY exit_date DESC
      LIMIT $1
    `;

    const result = await query(tradesQuery, [parseInt(limit)]);
    validateQueryResult(result, { requireRows: false });

    const trades = result.rows.map((row) => ({
      trade_id: row.trade_id,
      symbol: row.symbol,
      entry_date: row.entry_date,
      entry_price: parseFloat(row.entry_price),
      exit_date: row.exit_date,
      exit_price: parseFloat(row.exit_price),
      pnl_dollars: parseFloat(row.profit_loss_dollars),
      pnl_pct: parseFloat(row.profit_loss_pct),
      duration_days: row.trade_duration_days,
      r_multiple: parseFloat(row.exit_r_multiple),
      status: row.status,
    }));

    return sendSuccess(res, trades);
  } catch (error) {
    logger.error("Error fetching recent trades:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(res, "Failed to fetch recent trades", 500);
  }
}

// Register routes
router.get("/", getPerformanceMetrics); // Root endpoint defaults to metrics
router.get("/metrics", getPerformanceMetrics);
router.get("/trades", getRecentTrades);

module.exports = router;

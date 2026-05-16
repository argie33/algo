/**
 * Performance Metrics Endpoint
 *
 * Returns daily/weekly/monthly performance statistics:
 * - Sharpe ratio, max drawdown, win rate, Profit Factor, Calmar ratio
 * - Updated daily from algo_trades table
 */

const express = require('express');

const router = express.Router();
const { query } = require('../utils/database');

async function getPerformanceMetrics(req, res) {
  try {
    const { period = 'week' } = req.query;

    let dateFilter = '';
    switch (period) {
      case 'day':
        dateFilter = "AND exit_date >= CURRENT_DATE";
        break;
      case 'week':
        dateFilter = "AND exit_date >= CURRENT_DATE - INTERVAL '7 days'";
        break;
      case 'month':
        dateFilter = "AND exit_date >= CURRENT_DATE - INTERVAL '30 days'";
        break;
      default:
        dateFilter = '';
    }

    const metricsQuery = `
      SELECT
        COUNT(*) as total_trades,
        SUM(CASE WHEN profit_loss_dollars > 0 THEN 1 ELSE 0 END) as win_count,
        SUM(CASE WHEN profit_loss_dollars < 0 THEN 1 ELSE 0 END) as loss_count,
        SUM(CASE WHEN profit_loss_dollars = 0 THEN 1 ELSE 0 END) as breakeven_count,
        ROUND(100.0 * SUM(CASE WHEN profit_loss_dollars > 0 THEN 1 ELSE 0 END) / COUNT(*), 2) as win_rate_pct,
        ROUND(SUM(CASE WHEN profit_loss_dollars > 0 THEN profit_loss_dollars ELSE 0 END), 2) as gross_profit,
        ROUND(ABS(SUM(CASE WHEN profit_loss_dollars < 0 THEN profit_loss_dollars ELSE 0 END)), 2) as gross_loss,
        ROUND(SUM(profit_loss_dollars), 2) as total_pnl,
        ROUND(AVG(profit_loss_dollars), 2) as avg_pnl_per_trade,
        ROUND(AVG(profit_loss_pct), 4) as avg_return_pct,
        ROUND(AVG(CASE WHEN profit_loss_dollars > 0 THEN profit_loss_dollars ELSE NULL END), 2) as avg_win,
        ROUND(AVG(CASE WHEN profit_loss_dollars < 0 THEN profit_loss_dollars ELSE NULL END), 2) as avg_loss,
        ROUND(AVG(CASE WHEN profit_loss_dollars > 0 THEN profit_loss_pct ELSE NULL END), 4) as avg_win_pct,
        ROUND(AVG(CASE WHEN profit_loss_dollars < 0 THEN profit_loss_pct ELSE NULL END), 4) as avg_loss_pct,
        ROUND(AVG(trade_duration_days), 1) as avg_hold_days,
        ROUND(AVG(exit_r_multiple), 2) as avg_r_multiple,
        MAX(exit_r_multiple) as best_trade_r,
        MIN(exit_r_multiple) as worst_trade_r,
        MIN(profit_loss_dollars) as biggest_loss,
        MAX(profit_loss_dollars) as biggest_win
      FROM algo_trades
      WHERE status = 'closed' AND exit_date IS NOT NULL
      ${dateFilter}
    `;

    const result = await query(metricsQuery);
    const metrics = result.rows[0] || {};

    const gross_profit = parseFloat(metrics.gross_profit) || 0;
    const gross_loss = parseFloat(metrics.gross_loss) || 0;
    const profit_factor = gross_loss > 0 ? (gross_profit / gross_loss).toFixed(2) : '0.00';

    const sharpeQuery = `
      SELECT
        ROUND(
          AVG(profit_loss_pct) / NULLIF(STDDEV(profit_loss_pct), 0) * SQRT(252),
          2
        ) as sharpe_ratio
      FROM algo_trades
      WHERE status = 'closed' AND exit_date IS NOT NULL AND profit_loss_pct IS NOT NULL
      ${dateFilter}
    `;

    const sharpeResult = await query(sharpeQuery);
    const sharpe_ratio = sharpeResult.rows[0]?.sharpe_ratio || 0;

    const ddQuery = `
      SELECT
        SUM(profit_loss_dollars) as cumulative_pnl
      FROM algo_trades
      WHERE status = 'closed' AND exit_date IS NOT NULL
      ${dateFilter}
      ORDER BY exit_date ASC
    `;

    const ddResult = await query(ddQuery);
    let max_drawdown = 0;
    let peak = 0;
    let cumulative = 0;

    if (ddResult.rows.length > 0) {
      ddResult.rows.forEach(row => {
        cumulative += row.cumulative_pnl || 0;
        if (cumulative > peak) peak = cumulative;
        const dd = peak - cumulative;
        if (dd > max_drawdown) max_drawdown = dd;
      });
    }

    const total_pnl = parseFloat(metrics.total_pnl) || 0;
    const calmar_ratio = max_drawdown > 0 ? (total_pnl / max_drawdown).toFixed(2) : '0.00';

    const response = {
      period,
      timestamp: new Date().toISOString(),
      summary: {
        total_trades: parseInt(metrics.total_trades) || 0,
        win_count: parseInt(metrics.win_count) || 0,
        loss_count: parseInt(metrics.loss_count) || 0,
        breakeven_count: parseInt(metrics.breakeven_count) || 0,
        win_rate_pct: parseFloat(metrics.win_rate_pct) || 0,
      },
      profitability: {
        gross_profit: parseFloat(metrics.gross_profit) || 0,
        gross_loss: parseFloat(metrics.gross_loss) || 0,
        profit_factor: parseFloat(profit_factor),
        total_pnl: parseFloat(metrics.total_pnl) || 0,
        avg_pnl_per_trade: parseFloat(metrics.avg_pnl_per_trade) || 0,
        avg_return_pct: parseFloat(metrics.avg_return_pct) || 0,
        biggest_win: parseFloat(metrics.biggest_win) || 0,
        biggest_loss: parseFloat(metrics.biggest_loss) || 0,
      },
      trade_quality: {
        avg_win: parseFloat(metrics.avg_win) || 0,
        avg_loss: parseFloat(metrics.avg_loss) || 0,
        avg_win_pct: parseFloat(metrics.avg_win_pct) || 0,
        avg_loss_pct: parseFloat(metrics.avg_loss_pct) || 0,
        avg_hold_days: parseFloat(metrics.avg_hold_days) || 0,
        avg_r_multiple: parseFloat(metrics.avg_r_multiple) || 0,
        best_trade_r: parseFloat(metrics.best_trade_r) || 0,
        worst_trade_r: parseFloat(metrics.worst_trade_r) || 0,
      },
      risk_metrics: {
        sharpe_ratio: parseFloat(sharpe_ratio),
        max_drawdown: parseFloat(max_drawdown).toFixed(2),
        calmar_ratio: parseFloat(calmar_ratio),
      },
    };

    res.json(response);
  } catch (error) {
    console.error('Error fetching performance metrics:', error);
    res.status(500).json({
      error: 'Failed to fetch performance metrics',
      details: error.message,
    });
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

    const trades = result.rows.map(row => ({
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

    res.json({
      success: true,
      count: trades.length,
      trades,
    });
  } catch (error) {
    console.error('Error fetching recent trades:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch recent trades',
      details: error.message,
    });
  }
}

// Register routes
router.get('/metrics', getPerformanceMetrics);
router.get('/trades', getRecentTrades);

module.exports = router;

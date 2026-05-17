const express = require('express');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const { authenticateToken } = require('../middleware/auth');
const { query } = require('../utils/database');

const router = express.Router();

// GET /api/metrics - Get system metrics (alias to /api/algo/metrics or combined stats)
router.get('/', authenticateToken, async (req, res) => {
  try {
    const { period = 'day' } = req.query;

    // Try to get algo performance metrics
    let metricsQuery = `
      SELECT
        COUNT(*) as total_trades,
        SUM(CASE WHEN profit_loss_dollars > 0 THEN 1 ELSE 0 END) as winning_trades,
        SUM(CASE WHEN profit_loss_dollars < 0 THEN 1 ELSE 0 END) as losing_trades,
        ROUND(100.0 * SUM(CASE WHEN profit_loss_dollars > 0 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as win_rate_pct,
        ROUND(SUM(profit_loss_dollars), 2) as total_pnl,
        ROUND(MAX(profit_loss_dollars), 2) as biggest_win,
        ROUND(MIN(profit_loss_dollars), 2) as biggest_loss
      FROM algo_trades
      WHERE status = 'closed' AND exit_date IS NOT NULL
    `;

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
        return sendError(res, "Invalid period. Use: day, week, month, or all", 400);
    }

    metricsQuery += dateFilter;

    const result = await query(metricsQuery);
    const metrics = result.rows[0] || {
      total_trades: 0,
      winning_trades: 0,
      losing_trades: 0,
      win_rate_pct: 0,
      total_pnl: 0,
      biggest_win: 0,
      biggest_loss: 0
    };

    return sendSuccess(res, {
      period,
      metrics: {
        total_trades: parseInt(metrics.total_trades) || 0,
        winning_trades: parseInt(metrics.winning_trades) || 0,
        losing_trades: parseInt(metrics.losing_trades) || 0,
        win_rate_pct: parseFloat(metrics.win_rate_pct) || 0,
        total_pnl: parseFloat(metrics.total_pnl) || 0,
        biggest_win: parseFloat(metrics.biggest_win) || 0,
        biggest_loss: parseFloat(metrics.biggest_loss) || 0
      }
    });
  } catch (error) {
    console.error('Error fetching metrics:', error);
    return sendError(res, 'Failed to fetch metrics', 500);
  }
});

// GET /api/metrics/system - Get system-level metrics (uptime, health, etc.)
router.get('/system', authenticateToken, async (req, res) => {
  try {
    return sendSuccess(res, {
      uptime_seconds: process.uptime(),
      memory_used_mb: (process.memoryUsage().heapUsed / 1024 / 1024).toFixed(2),
      memory_total_mb: (process.memoryUsage().heapTotal / 1024 / 1024).toFixed(2),
      cpu_usage_pct: (process.cpuUsage().user / 1000000).toFixed(2),
      status: 'healthy',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching system metrics:', error);
    return sendError(res, 'Failed to fetch system metrics', 500);
  }
});

module.exports = router;

const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const router = express.Router();

// GET / - Get portfolio overview
router.get("/", async (req, res) => {
  try {
    // Get algorithm positions - correct column names from algo_positions schema
    const positionsObj = await query(`
      SELECT
        symbol,
        created_at as entry_date,
        quantity,
        avg_entry_price as entry_price,
        current_price,
        unrealized_pnl as pnl,
        unrealized_pnl_pct as pnl_percent,
        status
      FROM algo_positions
      WHERE closed_at IS NULL
      ORDER BY created_at DESC
      LIMIT 50
    `);

    const positions = Array.isArray(positionsObj) ? positionsObj : (positionsObj?.rows || []);

    // Get portfolio summary from positions
    const totalValue = positions.reduce((sum, p) => sum + (p.current_price * p.quantity || 0), 0);
    const totalPnL = positions.reduce((sum, p) => sum + (p.pnl || 0), 0);

    const summary = {
      total_positions: positions.length,
      total_value: totalValue,
      cash_available: 0,
      daily_pnl: totalPnL,
      daily_pnl_percent: totalValue > 0 ? ((totalPnL / totalValue) * 100) : 0
    };

    sendSuccess(res, {
      summary,
      positions,
      latest_snapshot: null
    }, 200);
  } catch (error) {
    sendError(res, `Failed to retrieve portfolio: ${error.message}`, 500);
  }
});

// GET /holdings - Get current holdings
router.get("/holdings", async (req, res) => {
  try {
    const holdingsObj = await query(`
      SELECT
        symbol,
        quantity,
        avg_entry_price as average_cost,
        current_price,
        (quantity * current_price) as value,
        unrealized_pnl as gain_loss,
        unrealized_pnl_pct as gain_loss_percent
      FROM algo_positions
      WHERE closed_at IS NULL AND quantity > 0
      ORDER BY (quantity * current_price) DESC
    `);

    const holdings = Array.isArray(holdingsObj) ? holdingsObj : (holdingsObj?.rows || []);
    sendSuccess(res, holdings, 200);
  } catch (error) {
    sendError(res, `Failed to retrieve holdings: ${error.message}`, 500);
  }
});

// GET /performance - Get portfolio performance
router.get("/performance", async (req, res) => {
  try {
    const performanceObj = await query(`
      SELECT
        DATE(trade_date) as metric_date,
        COUNT(*) as total_trades,
        SUM(CASE WHEN profit_loss_dollars > 0 THEN 1 ELSE 0 END) as winning_trades,
        COUNT(*) - SUM(CASE WHEN profit_loss_dollars > 0 THEN 1 ELSE 0 END) as losing_trades,
        ROUND(AVG(profit_loss_pct)::numeric, 2) as avg_return_pct,
        MAX(CASE WHEN profit_loss_dollars > 0 THEN profit_loss_dollars ELSE 0 END) as best_trade,
        MIN(CASE WHEN profit_loss_dollars < 0 THEN profit_loss_dollars ELSE 0 END) as worst_trade,
        ROUND(SUM(profit_loss_dollars)::numeric, 2) as daily_pnl
      FROM algo_trades
      WHERE status = 'closed'
      GROUP BY DATE(trade_date)
      ORDER BY DATE(trade_date) DESC
      LIMIT 90
    `);

    const performance = Array.isArray(performanceObj) ? performanceObj : (performanceObj?.rows || []);
    sendSuccess(res, performance, 200);
  } catch (error) {
    sendError(res, `Failed to retrieve performance: ${error.message}`, 500);
  }
});

module.exports = router;

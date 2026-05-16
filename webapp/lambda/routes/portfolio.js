const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const router = express.Router();

// GET / - Get portfolio overview
router.get("/", async (req, res) => {
  try {
    // Get algorithm positions - correct column names from algo_positions schema
    const positions = await query(`
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
    const holdings = await query(`
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

    sendSuccess(res, holdings, 200);
  } catch (error) {
    sendError(res, `Failed to retrieve holdings: ${error.message}`, 500);
  }
});

// GET /performance - Get portfolio performance
router.get("/performance", async (req, res) => {
  try {
    const performance = await query(`
      SELECT 
        metric_date,
        total_return,
        annual_return,
        sharpe_ratio,
        max_drawdown,
        win_rate,
        profit_factor
      FROM portfolio_performance
      ORDER BY metric_date DESC
      LIMIT 90
    `).catch(() => []);

    sendSuccess(res, performance, 200);
  } catch (error) {
    sendSuccess(res, [], 200);
  }
});

module.exports = router;

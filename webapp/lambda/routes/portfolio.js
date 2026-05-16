const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const router = express.Router();

// GET / - Get portfolio overview
router.get("/", async (req, res) => {
  try {
    // Get algorithm positions (empty but valid response)
    const positions = await query(`
      SELECT 
        symbol,
        entry_date,
        quantity,
        entry_price,
        current_price,
        pnl,
        pnl_percent,
        status
      FROM algo_positions
      WHERE status IN ('open', 'pending')
      ORDER BY entry_date DESC
      LIMIT 50
    `).catch(() => []);

    // Get portfolio snapshot if available
    const snapshot = await query(`
      SELECT
        total_portfolio_value,
        total_cash,
        total_equity,
        realized_pnl_today,
        daily_return_pct,
        snapshot_date
      FROM algo_portfolio_snapshots
      ORDER BY snapshot_date DESC
      LIMIT 1
    `).catch(() => []);

    // Calculate summary stats
    const summary = {
      total_positions: positions.length,
      total_value: snapshot.length > 0 ? snapshot[0].total_portfolio_value : 0,
      cash_available: snapshot.length > 0 ? snapshot[0].total_cash : 0,
      daily_pnl: snapshot.length > 0 ? snapshot[0].realized_pnl_today : 0,
      daily_pnl_percent: snapshot.length > 0 ? snapshot[0].daily_return_pct : 0
    };

    sendSuccess(res, {
      summary,
      positions,
      latest_snapshot: snapshot.length > 0 ? snapshot[0] : null
    }, 200);
  } catch (error) {
    // Return empty but valid portfolio on error
    sendSuccess(res, {
      summary: {
        total_positions: 0,
        total_value: 0,
        cash_available: 0,
        daily_pnl: 0,
        daily_pnl_percent: 0
      },
      positions: [],
      latest_snapshot: null
    }, 200);
  }
});

// GET /holdings - Get current holdings
router.get("/holdings", async (req, res) => {
  try {
    const holdings = await query(`
      SELECT 
        symbol,
        quantity,
        average_cost,
        current_price,
        value,
        gain_loss,
        gain_loss_percent,
        sector,
        industry
      FROM portfolio_holdings ph
      LEFT JOIN company_profile cp ON ph.symbol = cp.symbol
      WHERE quantity > 0
      ORDER BY value DESC
    `).catch(() => []);

    sendSuccess(res, holdings, 200);
  } catch (error) {
    sendSuccess(res, [], 200);
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

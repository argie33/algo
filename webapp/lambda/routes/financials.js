/**
 * Financials API Routes
 *
 * Endpoints:
 * - GET /api/financials/:ticker/balance-sheet - Balance sheet data
 * - GET /api/financials/:ticker/income-statement - Income statement
 * - GET /api/financials/:ticker/cash-flow - Cash flow statement
 * - GET /api/financials/:ticker/key-metrics - Key financial metrics
 */

const express = require('express');
const { getPool } = require('../utils/database');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');

const router = express.Router();

/**
 * GET /api/financials/:ticker/balance-sheet
 * Balance sheet data (annual or quarterly)
 */
router.get('/:ticker/balance-sheet', async (req, res) => {
  try {
    const { ticker } = req.params;
    const period = req.query.period || 'annual';

    if (!ticker) {
      return sendError(res, 'Missing ticker parameter', 400);
    }

    const pool = getPool();
    const table = period === 'quarterly' ? 'quarterly_balance_sheet' : 'annual_balance_sheet';

    const result = await pool.query(`
      SELECT *
      FROM ${table}
      WHERE symbol = $1
      ORDER BY fiscal_year DESC ${period === 'quarterly' ? ', fiscal_quarter DESC' : ''}
      LIMIT 20
    `, [ticker.toUpperCase()]);

    return sendSuccess(res, {
      ticker: ticker.toUpperCase(),
      period: period,
      data: result.rows || []
    });

  } catch (error) {
    logger.error('Error fetching balance sheet:', { error: error.message });
    return sendError(res, `Failed to fetch balance sheet: ${error.message}`, 500);
  }
});

/**
 * GET /api/financials/:ticker/income-statement
 * Income statement data
 */
router.get('/:ticker/income-statement', async (req, res) => {
  try {
    const { ticker } = req.params;
    const period = req.query.period || 'annual';

    if (!ticker) {
      return sendError(res, 'Missing ticker parameter', 400);
    }

    const pool = getPool();
    const table = period === 'quarterly' ? 'quarterly_income_statement' : 'annual_income_statement';

    const result = await pool.query(`
      SELECT *
      FROM ${table}
      WHERE symbol = $1
      ORDER BY fiscal_year DESC ${period === 'quarterly' ? ', fiscal_quarter DESC' : ''}
      LIMIT 20
    `, [ticker.toUpperCase()]);

    return sendSuccess(res, {
      ticker: ticker.toUpperCase(),
      period: period,
      data: result.rows || []
    });

  } catch (error) {
    logger.error('Error fetching income statement:', { error: error.message });
    return sendError(res, `Failed to fetch income statement: ${error.message}`, 500);
  }
});

/**
 * GET /api/financials/:ticker/cash-flow
 * Cash flow statement data
 */
router.get('/:ticker/cash-flow', async (req, res) => {
  try {
    const { ticker } = req.params;
    const period = req.query.period || 'annual';

    if (!ticker) {
      return sendError(res, 'Missing ticker parameter', 400);
    }

    const pool = getPool();
    const table = period === 'quarterly' ? 'quarterly_cash_flow' : 'annual_cash_flow';

    const result = await pool.query(`
      SELECT *
      FROM ${table}
      WHERE symbol = $1
      ORDER BY fiscal_year DESC ${period === 'quarterly' ? ', fiscal_quarter DESC' : ''}
      LIMIT 20
    `, [ticker.toUpperCase()]);

    return sendSuccess(res, {
      ticker: ticker.toUpperCase(),
      period: period,
      data: result.rows || []
    });

  } catch (error) {
    logger.error('Error fetching cash flow:', { error: error.message });
    return sendError(res, `Failed to fetch cash flow: ${error.message}`, 500);
  }
});

/**
 * GET /api/financials/:ticker/key-metrics
 * Key financial metrics
 */
router.get('/:ticker/key-metrics', async (req, res) => {
  try {
    const { ticker } = req.params;

    if (!ticker) {
      return sendError(res, 'Missing ticker parameter', 400);
    }

    const pool = getPool();

    const result = await pool.query(`
      SELECT
        symbol,
        market_cap,
        held_percent_insiders,
        held_percent_institutions
      FROM key_metrics
      WHERE symbol = $1
    `, [ticker.toUpperCase()]);

    if (result.rows.length === 0) {
      return sendSuccess(res, { ticker: ticker.toUpperCase(), data: {} });
    }

    return sendSuccess(res, {
      ticker: ticker.toUpperCase(),
      data: result.rows[0]
    });

  } catch (error) {
    logger.error('Error fetching key metrics:', { error: error.message });
    return sendError(res, `Failed to fetch key metrics: ${error.message}`, 500);
  }
});

module.exports = router;

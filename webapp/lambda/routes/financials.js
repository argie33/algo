const express = require("express");

let query;
try {
  ({ query } = require("../utils/database"));
} catch (error) {
  console.log("Database service not available in financials routes:", error.message);
  query = null;
}

const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

router.get("/:symbol/balance-sheet", async (req, res) => {
  const { symbol } = req.params;
  let { period = "annual" } = req.query;
  const upperSymbol = symbol.toUpperCase();

  try {
    console.log(`📊 [FINANCIALS] Fetching balance sheet for ${upperSymbol} (${period})`);

    const validTables = {
      'annual': 'annual_balance_sheet',
      'quarterly': 'quarterly_balance_sheet'
    };

    let tableName = validTables[period] || validTables['annual'];
    let result = await query(`
      SELECT *
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY fiscal_year DESC
      LIMIT 20
    `, [upperSymbol]);

    // Fallback to quarterly if annual is empty
    if ((!result.rows || result.rows.length === 0) && period === 'annual') {
      console.log(`No annual data found, falling back to quarterly for ${upperSymbol}`);
      tableName = 'quarterly_balance_sheet';
      period = 'quarterly';
      result = await query(`
        SELECT *
        FROM ${tableName}
        WHERE symbol = $1
        ORDER BY fiscal_year DESC, fiscal_quarter DESC
        LIMIT 20
      `, [upperSymbol]);
    }

    const transformedData = (result.rows || []).map(row => {
      const data = { symbol: row.symbol, fiscal_year: row.fiscal_year };
      Object.entries(row).forEach(([key, value]) => {
        if (!['symbol', 'fiscal_year', 'fiscal_quarter'].includes(key)) {
          data[key] = value;
        }
      });
      return data;
    });

    return sendSuccess(res, {
      symbol: upperSymbol,
      period: period,
      financialData: transformedData
    });
  } catch (error) {
    console.error("Balance sheet error:", error);
    return sendError(res, `Failed to fetch balance sheet: ${error.message}`, 500);
  }
});

router.get("/:symbol/income-statement", async (req, res) => {
  const { symbol } = req.params;
  const { period = "annual" } = req.query;
  const upperSymbol = symbol.toUpperCase();

  try {
    console.log(`📊 [FINANCIALS] Fetching income statement for ${upperSymbol} (${period})`);
    const validTables = {
      'annual': 'annual_income_statement',
      'quarterly': 'quarterly_income_statement'
    };
    const tableName = validTables[period] || validTables['annual'];
    const result = await query(`
      SELECT *
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY fiscal_year DESC
      LIMIT 20
    `, [upperSymbol]);

    const transformedData = (result.rows || []).map(row => {
      const data = { symbol: row.symbol, fiscal_year: row.fiscal_year };
      Object.entries(row).forEach(([key, value]) => {
        if (!['symbol', 'fiscal_year', 'fiscal_quarter'].includes(key)) {
          data[key] = value;
        }
      });
      return data;
    });

    return sendSuccess(res, {
      symbol: upperSymbol,
      period: period,
      financialData: transformedData
    });
  } catch (error) {
    console.error("Income statement error:", error);
    return sendError(res, `Failed to fetch income statement: ${error.message}`, 500);
  }
});

router.get("/:symbol/cash-flow", async (req, res) => {
  const { symbol } = req.params;
  const { period = "annual" } = req.query;
  const upperSymbol = symbol.toUpperCase();

  try {
    console.log(`📊 [FINANCIALS] Fetching cash flow for ${upperSymbol} (${period})`);
    const validTables = {
      'annual': 'annual_cash_flow',
      'quarterly': 'quarterly_cash_flow'
    };
    const tableName = validTables[period] || validTables['annual'];
    const result = await query(`
      SELECT *
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY fiscal_year DESC
      LIMIT 20
    `, [upperSymbol]);

    const transformedData = (result.rows || []).map(row => {
      const data = { symbol: row.symbol, fiscal_year: row.fiscal_year };
      Object.entries(row).forEach(([key, value]) => {
        if (!['symbol', 'fiscal_year', 'fiscal_quarter'].includes(key)) {
          data[key] = value;
        }
      });
      return data;
    });

    return sendSuccess(res, {
      symbol: upperSymbol,
      period: period,
      financialData: transformedData
    });
  } catch (error) {
    console.error("Cash flow error:", error);
    return sendSuccess(res, {
      symbol: upperSymbol,
      period: period,
      financialData: []
    });
  }
});

router.get("/:symbol/key-metrics", async (req, res) => {
  const { symbol } = req.params;
  const upperSymbol = symbol.toUpperCase();

  try {
    console.log(`📊 [FINANCIALS] Fetching key metrics for ${upperSymbol}`);
    const [mainResult, vmResult, qmResult] = await Promise.all([
      query(`
        SELECT cp.ticker, cp.short_name, cp.long_name, cp.sector, cp.industry,
               cp.exchange, km.market_cap, km.held_percent_insiders, km.held_percent_institutions
        FROM company_profile cp
        LEFT JOIN key_metrics km ON cp.ticker = km.ticker
        WHERE cp.ticker = $1 LIMIT 1
      `, [upperSymbol]),
      query(`
        SELECT DISTINCT ON (symbol)
          trailing_pe, forward_pe, price_to_book, price_to_sales_ttm,
          peg_ratio, ev_to_revenue, ev_to_ebitda, dividend_yield, payout_ratio
        FROM value_metrics WHERE symbol = $1 ORDER BY symbol, date DESC
      `, [upperSymbol]),
      query(`
        SELECT DISTINCT ON (symbol)
          debt_to_equity, current_ratio, quick_ratio, return_on_equity_pct,
          return_on_assets_pct, gross_margin_pct, operating_margin_pct, profit_margin_pct
        FROM quality_metrics WHERE symbol = $1 ORDER BY symbol, date DESC
      `, [upperSymbol])
    ]);

    const cp = mainResult.rows[0] || {};
    const vm = vmResult.rows[0] || {};
    const qm = qmResult.rows[0] || {};

    return sendSuccess(res, {
      symbol: upperSymbol,
      name: cp.short_name || null,
      sector: cp.sector || null,
      industry: cp.industry || null,
      exchange: cp.exchange || null,
      market_cap: cp.market_cap || null,
      insider_ownership: cp.held_percent_insiders || null,
      institutional_ownership: cp.held_percent_institutions || null,
      pe_ratio: vm.trailing_pe || vm.forward_pe || null,
      forward_pe: vm.forward_pe || null,
      pb_ratio: vm.price_to_book || null,
      ps_ratio: vm.price_to_sales_ttm || null,
      peg_ratio: vm.peg_ratio || null,
      ev_to_revenue: vm.ev_to_revenue || null,
      ev_to_ebitda: vm.ev_to_ebitda || null,
      dividend_yield: vm.dividend_yield || null,
      payout_ratio: vm.payout_ratio || null,
      debt_to_equity: qm.debt_to_equity || null,
      current_ratio: qm.current_ratio || null,
      quick_ratio: qm.quick_ratio || null,
      roe: qm.return_on_equity_pct || null,
      roa: qm.return_on_assets_pct || null,
      gross_margin: qm.gross_margin_pct || null,
      operating_margin: qm.operating_margin_pct || null,
      profit_margin: qm.profit_margin_pct || null,
    });
  } catch (error) {
    console.error("Key metrics error:", error);
    return sendSuccess(res, { symbol: upperSymbol });
  }
});

router.get("/all", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = parseInt(req.query.offset) || 0;

    const result = await query(`
      SELECT ticker as symbol, short_name as name, sector, industry
      FROM key_metrics
      ORDER BY ticker ASC
      LIMIT $1 OFFSET $2
    `, [limit, offset]);

    const countResult = await query(`SELECT COUNT(DISTINCT ticker) as total FROM key_metrics`);
    const total = parseInt(countResult.rows[0]?.total || 0);

    return sendPaginated(res, result.rows || [], {
      limit,
      offset,
      total,
      page: Math.max(1, Math.ceil((offset / limit) + 1))
    });
  } catch (error) {
    console.error("All financials error:", error);
    return sendPaginated(res, [], { limit: 50, offset: 0, total: 0, page: 1 });
  }
});

module.exports = router;

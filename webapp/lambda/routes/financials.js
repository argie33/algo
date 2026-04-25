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

router.get("/", async (req, res) => {
  return sendSuccess(res, {
    message: "Financials API - Ready",
    status: "operational",
    endpoints: [
      "/:symbol/balance-sheet?period=annual|quarterly",
      "/:symbol/income-statement?period=annual|quarterly",
      "/:symbol/cash-flow?period=annual|quarterly",
      "/:symbol/key-metrics"
    ],
  });
});

router.get("/:symbol/balance-sheet", async (req, res) => {
  const { symbol } = req.params;
  const { period = "annual" } = req.query;
  const upperSymbol = symbol.toUpperCase();

  try {
    console.log(`📊 [FINANCIALS] Fetching balance sheet for ${upperSymbol} (${period})`);
    const tableName = period === 'quarterly' ? 'quarterly_balance_sheet' : 'annual_balance_sheet';
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
    console.error("Balance sheet error:", error);
    return sendSuccess(res, {
      symbol: upperSymbol,
      period: period,
      financialData: []
    });
  }
});

router.get("/:symbol/income-statement", async (req, res) => {
  const { symbol } = req.params;
  const { period = "annual" } = req.query;
  const upperSymbol = symbol.toUpperCase();

  try {
    console.log(`📊 [FINANCIALS] Fetching income statement for ${upperSymbol} (${period})`);
    const tableName = period === 'quarterly' ? 'quarterly_income_statement' : 'annual_income_statement';
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
    return sendSuccess(res, {
      symbol: upperSymbol,
      period: period,
      financialData: []
    });
  }
});

router.get("/:symbol/cash-flow", async (req, res) => {
  const { symbol } = req.params;
  const { period = "annual" } = req.query;
  const upperSymbol = symbol.toUpperCase();

  try {
    console.log(`📊 [FINANCIALS] Fetching cash flow for ${upperSymbol} (${period})`);
    const tableName = period === 'quarterly' ? 'quarterly_cash_flow' : 'annual_cash_flow';
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
    const result = await query(`
      SELECT ticker, short_name, long_name, sector, industry, market_cap,
             employees, website, currency_code, exchange,
             held_percent_insiders, held_percent_institutions
      FROM key_metrics
      WHERE ticker = $1
      LIMIT 1
    `, [upperSymbol]);

    const metricsData = {};
    if (result.rows && result.rows.length > 0) {
      const row = result.rows[0];
      metricsData['Company Info'] = {
        title: 'Company Information',
        metrics: {
          'Name': row.short_name,
          'Full Name': row.long_name,
          'Sector': row.sector,
          'Industry': row.industry,
          'Exchange': row.exchange,
          'Website': row.website,
          'Employees': row.employees,
          'Currency': row.currency_code
        }
      };
      metricsData['Valuation'] = {
        title: 'Valuation Metrics',
        metrics: {
          'Market Cap': row.market_cap
        }
      };
      metricsData['Ownership'] = {
        title: 'Ownership',
        metrics: {
          'Insider Ownership %': row.held_percent_insiders,
          'Institutional Ownership %': row.held_percent_institutions
        }
      };
    }

    return sendSuccess(res, {
      symbol: upperSymbol,
      metricsData: metricsData
    });
  } catch (error) {
    console.error("Key metrics error:", error);
    return sendSuccess(res, {
      symbol: upperSymbol,
      metricsData: {}
    });
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

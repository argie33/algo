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
    // Try quarterly_balance_sheet first (populated by loader); fall back to value_metrics + quality_metrics
    let bsResult = { rows: [] };
    try {
      bsResult = await query(`
        SELECT *
        FROM quarterly_balance_sheet
        WHERE symbol = $1
        ORDER BY fiscal_year DESC, fiscal_quarter DESC
        LIMIT 20
      `, [upperSymbol]);
    } catch (e) {
      // Table doesn't exist yet — use fallback metrics
    }

    let transformedData = (bsResult.rows || []).map(row => {
      const data = { symbol: row.symbol, fiscal_year: row.fiscal_year, fiscal_quarter: row.fiscal_quarter };
      Object.entries(row).forEach(([key, value]) => {
        if (!['id', 'created_at', 'updated_at', 'fetched_at'].includes(key)) {
          data[key] = value;
        }
      });
      return data;
    });

    // Fallback: if no balance sheet data, use value_metrics + quality_metrics
    if (transformedData.length === 0) {
      const [vmResult, qmResult] = await Promise.all([
        query(`
          SELECT DISTINCT ON (symbol)
            symbol, trailing_pe, forward_pe, price_to_book, price_to_sales_ttm,
            peg_ratio, ev_to_revenue, ev_to_ebitda, dividend_yield, payout_ratio, date
          FROM value_metrics WHERE symbol = $1 ORDER BY symbol, date DESC
        `, [upperSymbol]),
        query(`
          SELECT DISTINCT ON (symbol)
            symbol, return_on_equity_pct, return_on_assets_pct, return_on_invested_capital_pct,
            gross_margin_pct, operating_margin_pct, profit_margin_pct,
            debt_to_equity, current_ratio, quick_ratio, earnings_beat_rate, date
          FROM quality_metrics WHERE symbol = $1 ORDER BY symbol, date DESC
        `, [upperSymbol])
      ]);

      const vm = vmResult.rows[0] || {};
      const qm = qmResult.rows[0] || {};
      const year = vm.date ? new Date(vm.date).getFullYear() : new Date().getFullYear();

      transformedData = [{
        symbol: upperSymbol,
        fiscal_year: year,
        fiscal_quarter: null,
        trailing_pe: vm.trailing_pe,
        forward_pe: vm.forward_pe,
        price_to_book: vm.price_to_book,
        price_to_sales_ttm: vm.price_to_sales_ttm,
        peg_ratio: vm.peg_ratio,
        ev_to_revenue: vm.ev_to_revenue,
        ev_to_ebitda: vm.ev_to_ebitda,
        dividend_yield: vm.dividend_yield,
        payout_ratio: vm.payout_ratio,
        return_on_equity_pct: qm.return_on_equity_pct,
        return_on_assets_pct: qm.return_on_assets_pct,
        return_on_invested_capital_pct: qm.return_on_invested_capital_pct,
        gross_margin_pct: qm.gross_margin_pct,
        operating_margin_pct: qm.operating_margin_pct,
        profit_margin_pct: qm.profit_margin_pct,
        debt_to_equity: qm.debt_to_equity,
        current_ratio: qm.current_ratio,
        quick_ratio: qm.quick_ratio,
        earnings_beat_rate: qm.earnings_beat_rate,
      }].filter(row => Object.values(row).some(v => v !== null && v !== undefined && !['symbol','fiscal_year','fiscal_quarter'].includes(v)));
    }

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
    // Try quarterly_income_statement first (populated by loader)
    let quarterlyRows = [];
    try {
      const quarterlyResult = await query(`
        SELECT symbol, fiscal_year, fiscal_quarter, date,
               revenue, cost_of_revenue, gross_profit, operating_expenses,
               operating_income, net_income
        FROM quarterly_income_statement
        WHERE symbol = $1
        ORDER BY fiscal_year DESC, fiscal_quarter DESC
        LIMIT 20
      `, [upperSymbol]);
      quarterlyRows = quarterlyResult.rows || [];
    } catch (e) {
      // Table doesn't exist yet — fall through to TTM
    }

    if (quarterlyRows.length > 0) {
      return sendSuccess(res, { symbol: upperSymbol, period, financialData: quarterlyRows });
    }

    // Fallback: pivot ttm_income_statement from long to wide format
    const result = await query(`
      SELECT date, item_name, value
      FROM ttm_income_statement
      WHERE symbol = $1
      ORDER BY date DESC
    `, [upperSymbol]);

    const byDate = {};
    for (const row of (result.rows || [])) {
      const dateKey = row.date ? new Date(row.date).toISOString().slice(0, 10) : 'TTM';
      if (!byDate[dateKey]) byDate[dateKey] = { symbol: upperSymbol, fiscal_year: row.date ? new Date(row.date).getFullYear() : null, fiscal_quarter: null, date: dateKey };
      const colName = row.item_name ? row.item_name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/_+$/, '') : 'unknown';
      byDate[dateKey][colName] = row.value;
    }
    const transformedData = Object.values(byDate).sort((a, b) => (b.fiscal_year || 0) - (a.fiscal_year || 0));

    return sendSuccess(res, { symbol: upperSymbol, period, financialData: transformedData });
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
    // Try quarterly_cash_flow first (populated by loader)
    let quarterlyRows = [];
    try {
      const quarterlyResult = await query(`
        SELECT symbol, fiscal_year, fiscal_quarter, date,
               operating_cash_flow, investing_cash_flow, financing_cash_flow,
               capital_expenditures, free_cash_flow
        FROM quarterly_cash_flow
        WHERE symbol = $1
        ORDER BY fiscal_year DESC, fiscal_quarter DESC
        LIMIT 20
      `, [upperSymbol]);
      quarterlyRows = quarterlyResult.rows || [];
    } catch (e) {
      // Table doesn't exist yet — fall through to TTM
    }

    if (quarterlyRows.length > 0) {
      return sendSuccess(res, { symbol: upperSymbol, period, financialData: quarterlyRows });
    }

    // Fallback: pivot ttm_cash_flow from long to wide format
    const result = await query(`
      SELECT date, item_name, value
      FROM ttm_cash_flow
      WHERE symbol = $1
      ORDER BY date DESC
    `, [upperSymbol]);

    const byDate = {};
    for (const row of (result.rows || [])) {
      const dateKey = row.date ? new Date(row.date).toISOString().slice(0, 10) : 'TTM';
      if (!byDate[dateKey]) byDate[dateKey] = { symbol: upperSymbol, fiscal_year: row.date ? new Date(row.date).getFullYear() : null, fiscal_quarter: null, date: dateKey };
      const colName = row.item_name ? row.item_name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/_+$/, '') : 'unknown';
      byDate[dateKey][colName] = row.value;
    }
    const transformedData = Object.values(byDate).sort((a, b) => (b.fiscal_year || 0) - (a.fiscal_year || 0));

    return sendSuccess(res, { symbol: upperSymbol, period, financialData: transformedData });
  } catch (error) {
    console.error("Cash flow error:", error);
    return sendSuccess(res, { symbol: upperSymbol, period, financialData: [] });
  }
});

router.get("/:symbol/key-metrics", async (req, res) => {
  const { symbol } = req.params;
  const upperSymbol = symbol.toUpperCase();

  try {
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

    // Return flat data object for FinancialData.jsx compatibility
    const flatData = {
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
    };

    return sendSuccess(res, flatData);
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

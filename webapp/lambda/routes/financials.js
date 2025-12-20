const express = require("express");

let query;
try {
  ({ query } = require("../utils/database"));
} catch (error) {
  console.log("Database service not available in financials routes:", error.message);
  query = null;
}

const router = express.Router();

// Root endpoint - provides overview of available financial endpoints
router.get("/", async (req, res) => {
  res.json({
    data: {
      message: "Financials API - Ready",
      status: "operational",
      endpoints: [
        "/:symbol/balance-sheet?period=annual|quarterly - Get balance sheet",
        "/:symbol/income-statement?period=annual|quarterly - Get income statement",
        "/:symbol/cash-flow?period=annual|quarterly - Get cash flow statement",
        "/:symbol/key-metrics - Get key financial metrics",
      ],
    },
    success: true
  });
});

// GET /api/financials/:symbol/balance-sheet - Get balance sheet
router.get("/:symbol/balance-sheet", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { period = "annual" } = req.query;
    const upperSymbol = symbol.toUpperCase();

    console.log(`📊 [FINANCIALS] Fetching balance sheet for ${upperSymbol} (${period})`);

    const tableName = period === 'quarterly' ? 'quarterly_balance_sheet' : 'annual_balance_sheet';
    // Query normalized format and transform to object for each date
    const result = await query(`
      SELECT
        symbol,
        date,
        json_object_agg(item_name, value) as metrics
      FROM ${tableName}
      WHERE symbol = $1
      GROUP BY symbol, date
      ORDER BY date DESC
      LIMIT 20
    `, [upperSymbol]);

    // Transform results to flat objects with camelCase keys
    const transformedData = (result.rows || []).map(row => ({
      symbol: row.symbol,
      date: row.date,
      ...row.metrics
    }));

    res.json({
      data: {
        symbol: upperSymbol,
        period: period,
        financialData: transformedData
      },
      success: true
    });
  } catch (error) {
    console.error("Balance sheet error:", error);
    res.status(500).json({
      error: "Failed to fetch balance sheet",
      success: false
    });
  }
});

// GET /api/financials/:symbol/income-statement - Get income statement
router.get("/:symbol/income-statement", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { period = "annual" } = req.query;
    const upperSymbol = symbol.toUpperCase();

    console.log(`📊 [FINANCIALS] Fetching income statement for ${upperSymbol} (${period})`);

    const tableName = period === 'quarterly' ? 'quarterly_income_statement' : 'annual_income_statement';
    // Query normalized format and transform to object for each date
    const result = await query(`
      SELECT
        symbol,
        date,
        json_object_agg(item_name, value) as metrics
      FROM ${tableName}
      WHERE symbol = $1
      GROUP BY symbol, date
      ORDER BY date DESC
      LIMIT 20
    `, [upperSymbol]);

    // Transform results to flat objects
    const transformedData = (result.rows || []).map(row => ({
      symbol: row.symbol,
      date: row.date,
      ...row.metrics
    }));

    res.json({
      data: {
        symbol: upperSymbol,
        period: period,
        financialData: transformedData
      },
      success: true
    });
  } catch (error) {
    console.error("Income statement error:", error);
    res.status(500).json({
      error: "Failed to fetch income statement",
      success: false
    });
  }
});

// GET /api/financials/:symbol/cash-flow - Get cash flow statement
router.get("/:symbol/cash-flow", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { period = "annual" } = req.query;
    const upperSymbol = symbol.toUpperCase();

    console.log(`📊 [FINANCIALS] Fetching cash flow for ${upperSymbol} (${period})`);

    const tableName = period === 'quarterly' ? 'quarterly_cash_flow' : 'annual_cash_flow';
    // Query normalized format and transform to object for each date
    const result = await query(`
      SELECT
        symbol,
        date,
        json_object_agg(item_name, value) as metrics
      FROM ${tableName}
      WHERE symbol = $1
      GROUP BY symbol, date
      ORDER BY date DESC
      LIMIT 20
    `, [upperSymbol]);

    // Transform results to flat objects
    const transformedData = (result.rows || []).map(row => ({
      symbol: row.symbol,
      date: row.date,
      ...row.metrics
    }));

    res.json({
      data: {
        symbol: upperSymbol,
        period: period,
        financialData: transformedData
      },
      success: true
    });
  } catch (error) {
    console.error("Cash flow error:", error);
    res.status(500).json({
      error: "Failed to fetch cash flow",
      success: false
    });
  }
});

// GET /api/financials/:symbol/key-metrics - Get key financial metrics
router.get("/:symbol/key-metrics", async (req, res) => {
  try {
    const { symbol } = req.params;
    const upperSymbol = symbol.toUpperCase();

    console.log(`📊 [FINANCIALS] Fetching key metrics for ${upperSymbol}`);

    const result = await query(`
      SELECT
        ticker,
        trailing_pe, forward_pe, price_to_sales_ttm, price_to_book, peg_ratio,
        ev_to_revenue, ev_to_ebitda,
        profit_margin_pct, gross_margin_pct, ebitda_margin_pct, operating_margin_pct,
        return_on_assets_pct, return_on_equity_pct,
        eps_trailing, eps_forward, eps_current_year, earnings_growth_pct,
        debt_to_equity, current_ratio, quick_ratio, total_debt, total_cash, free_cashflow,
        revenue_growth_pct,
        dividend_rate, dividend_yield, five_year_avg_dividend_yield, payout_ratio,
        held_percent_institutions, held_percent_insiders, float_shares
      FROM key_metrics
      WHERE ticker = $1
      LIMIT 100
    `, [upperSymbol]);

    const rows = result.rows || [];

    // Transform flat metrics into categorized structure for frontend display
    const metricsData = {};

    if (rows.length > 0) {
      const row = rows[0]; // Get the first (most recent) metrics record

      // Categorize metrics by type
      metricsData['Valuation'] = {
        title: 'Valuation Metrics',
        metrics: {
          'P/E Ratio (Trailing)': row.trailing_pe,
          'P/E Ratio (Forward)': row.forward_pe,
          'Price-to-Sales': row.price_to_sales_ttm,
          'Price-to-Book': row.price_to_book,
          'PEG Ratio': row.peg_ratio,
          'EV/Revenue': row.ev_to_revenue,
          'EV/EBITDA': row.ev_to_ebitda,
        }
      };

      metricsData['Profitability'] = {
        title: 'Profitability Metrics',
        metrics: {
          'Profit Margin': row.profit_margin_pct,
          'Gross Margin': row.gross_margin_pct,
          'EBITDA Margin': row.ebitda_margin_pct,
          'Operating Margin': row.operating_margin_pct,
          'Return on Assets': row.return_on_assets_pct,
          'Return on Equity': row.return_on_equity_pct,
        }
      };

      metricsData['Earnings'] = {
        title: 'Earnings Metrics',
        metrics: {
          'EPS (Trailing)': row.eps_trailing,
          'EPS (Forward)': row.eps_forward,
          'EPS (Current Year)': row.eps_current_year,
          'Earnings Growth %': row.earnings_growth_pct,
        }
      };

      metricsData['Financial Health'] = {
        title: 'Financial Health',
        metrics: {
          'Debt-to-Equity': row.debt_to_equity,
          'Current Ratio': row.current_ratio,
          'Quick Ratio': row.quick_ratio,
          'Total Debt': row.total_debt,
          'Total Cash': row.total_cash,
          'Free Cash Flow': row.free_cashflow,
        }
      };

      metricsData['Growth'] = {
        title: 'Growth Metrics',
        metrics: {
          'Revenue Growth %': row.revenue_growth_pct,
          'Earnings Growth %': row.earnings_growth_pct,
        }
      };

      metricsData['Dividend'] = {
        title: 'Dividend Information',
        metrics: {
          'Dividend Rate': row.dividend_rate,
          'Dividend Yield %': row.dividend_yield,
          '5Y Avg Dividend Yield %': row.five_year_avg_dividend_yield,
          'Payout Ratio': row.payout_ratio,
        }
      };

      metricsData['Ownership'] = {
        title: 'Ownership',
        metrics: {
          'Institutional Ownership %': row.held_percent_institutions,
          'Insider Ownership %': row.held_percent_insiders,
          'Float Shares': row.float_shares,
        }
      };
    }

    res.json({
      data: {
        symbol: upperSymbol,
        metricsData: metricsData
      },
      success: true
    });
  } catch (error) {
    console.error("Key metrics error:", error);
    res.status(500).json({
      error: "Failed to fetch key metrics",
      success: false
    });
  }
});

module.exports = router;

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

    // Query key_metrics for valuation and basic metrics
    const keyMetricsResult = await query(`
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
        AND (trailing_pe IS NOT NULL OR earnings_growth_pct IS NOT NULL)
      ORDER BY updated_at DESC, created_at DESC
      LIMIT 1
    `, [upperSymbol]);

    // Query quality_metrics for comprehensive quality indicators
    const qualityMetricsResult = await query(`
      SELECT
        return_on_equity_pct, return_on_assets_pct, return_on_invested_capital_pct,
        gross_margin_pct, operating_margin_pct, profit_margin_pct,
        fcf_to_net_income, operating_cf_to_net_income,
        debt_to_equity, current_ratio, quick_ratio, earnings_surprise_avg,
        eps_growth_stability, payout_ratio, roe_stability_index,
        earnings_beat_rate, estimate_revision_direction, consecutive_positive_quarters,
        surprise_consistency, earnings_growth_4q_avg
      FROM quality_metrics
      WHERE symbol = $1
        AND (return_on_equity_pct IS NOT NULL OR earnings_beat_rate IS NOT NULL)
      ORDER BY date DESC
      LIMIT 1
    `, [upperSymbol]);

    // Query growth_metrics for comprehensive growth analysis
    const growthMetricsResult = await query(`
      SELECT
        revenue_growth_3y_cagr, eps_growth_3y_cagr, operating_income_growth_yoy,
        roe_trend, sustainable_growth_rate, fcf_growth_yoy, net_income_growth_yoy,
        gross_margin_trend, operating_margin_trend, net_margin_trend,
        quarterly_growth_momentum, asset_growth_yoy, ocf_growth_yoy, revenue_growth_yoy
      FROM growth_metrics
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `, [upperSymbol]);

    // Query momentum_metrics for price and trend analysis
    const momentumMetricsResult = await query(`
      SELECT
        current_price, momentum_1m, momentum_3m, momentum_6m, momentum_12m,
        price_vs_sma_50, price_vs_sma_200, price_vs_52w_high
      FROM momentum_metrics
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `, [upperSymbol]);

    // Query stability_metrics for risk analysis
    const stabilityMetricsResult = await query(`
      SELECT
        volatility_12m, downside_volatility, max_drawdown_52w, beta,
        volume_consistency, turnover_velocity, volatility_volume_ratio, daily_spread
      FROM stability_metrics
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `, [upperSymbol]);

    // Query sentiment_metrics for market sentiment
    const sentimentMetricsResult = await query(`
      SELECT
        sentiment_score, bullish_count, bearish_count, neutral_count
      FROM sentiment_metrics
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `, [upperSymbol]);

    // Query positioning_metrics for ownership and positioning
    const positioningMetricsResult = await query(`
      SELECT
        institutional_ownership_pct, top_10_institutions_pct, institutional_holders_count,
        insider_ownership_pct, short_ratio, short_interest_pct, ad_rating,
        short_percent_of_float
      FROM positioning_metrics
      WHERE symbol = $1
      ORDER BY updated_at DESC
      LIMIT 1
    `, [upperSymbol]);

    // Query relative_performance_metrics for performance comparison
    const relativePerformanceResult = await query(`
      SELECT
        alpha, tracking_error, active_return, information_ratio, rel_volatility
      FROM relative_performance_metrics
      WHERE symbol = $1
      LIMIT 1
    `, [upperSymbol]);

    const keyRows = keyMetricsResult.rows || [];
    const qualityRows = qualityMetricsResult.rows || [];
    const growthRows = growthMetricsResult.rows || [];
    const momentumRows = momentumMetricsResult.rows || [];
    const stabilityRows = stabilityMetricsResult.rows || [];
    const sentimentRows = sentimentMetricsResult.rows || [];
    const positioningRows = positioningMetricsResult.rows || [];
    const relPerfRows = relativePerformanceResult.rows || [];

    // Transform flat metrics into categorized structure for frontend display
    const metricsData = {};

    if (keyRows.length > 0) {
      const row = keyRows[0];
      const quality = qualityRows.length > 0 ? qualityRows[0] : {};
      const growth = growthRows.length > 0 ? growthRows[0] : {};
      const momentum = momentumRows.length > 0 ? momentumRows[0] : {};
      const stability = stabilityRows.length > 0 ? stabilityRows[0] : {};
      const sentiment = sentimentRows.length > 0 ? sentimentRows[0] : {};
      const positioning = positioningRows.length > 0 ? positioningRows[0] : {};
      const relPerf = relPerfRows.length > 0 ? relPerfRows[0] : {};

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
          'Return on Equity (ROE)': quality.return_on_equity_pct || row.return_on_equity_pct,
          'ROE Stability Index': quality.roe_stability_index,
          'Return on Assets (ROA)': quality.return_on_assets_pct || row.return_on_assets_pct,
          'Return on Invested Capital (ROIC)': quality.return_on_invested_capital_pct,
          'Gross Margin %': quality.gross_margin_pct || row.gross_margin_pct,
          'Operating Margin %': quality.operating_margin_pct || row.operating_margin_pct,
          'Profit Margin %': quality.profit_margin_pct || row.profit_margin_pct,
          'EBITDA Margin %': row.ebitda_margin_pct,
        }
      };

      metricsData['Cash Flow'] = {
        title: 'Cash Flow Metrics',
        metrics: {
          'Operating CF / Net Income': quality.operating_cf_to_net_income,
          'FCF / Net Income': quality.fcf_to_net_income,
          'Free Cash Flow': row.free_cashflow,
        }
      };

      metricsData['Earnings'] = {
        title: 'Earnings Metrics',
        metrics: {
          'EPS (Trailing)': row.eps_trailing,
          'EPS (Forward)': row.eps_forward,
          'EPS (Current Year)': row.eps_current_year,
          'Earnings Growth %': row.earnings_growth_pct,
          'Earnings Growth (4Q Avg)': quality.earnings_growth_4q_avg,
          'EPS Growth Stability': quality.eps_growth_stability,
          'Earnings Beat Rate %': quality.earnings_beat_rate,
          'Earnings Surprise Avg': quality.earnings_surprise_avg,
          'Consecutive Positive Quarters': quality.consecutive_positive_quarters,
          'Surprise Consistency %': quality.surprise_consistency,
          'Estimate Revision Direction': quality.estimate_revision_direction,
        }
      };

      metricsData['Financial Health'] = {
        title: 'Financial Health',
        metrics: {
          'Debt-to-Equity': quality.debt_to_equity || row.debt_to_equity,
          'Current Ratio': quality.current_ratio || row.current_ratio,
          'Quick Ratio': quality.quick_ratio || row.quick_ratio,
          'Total Debt': row.total_debt,
          'Total Cash': row.total_cash,
          'Payout Ratio': quality.payout_ratio || row.payout_ratio,
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
        title: 'Ownership & Positioning',
        metrics: {
          'Institutional Ownership %': positioning.institutional_ownership_pct || row.held_percent_institutions,
          'Top 10 Institutions %': positioning.top_10_institutions_pct,
          'Institutional Holders Count': positioning.institutional_holders_count,
          'Insider Ownership %': positioning.insider_ownership_pct || row.held_percent_insiders,
          'Short Ratio': positioning.short_ratio,
          'Short Interest %': positioning.short_interest_pct,
          'Short % of Float': positioning.short_percent_of_float,
          'A/D Rating': positioning.ad_rating,
          'Float Shares': row.float_shares,
        }
      };

      metricsData['Growth Trends'] = {
        title: 'Long-term Growth Trends',
        metrics: {
          '3Y Revenue CAGR %': growth.revenue_growth_3y_cagr,
          '3Y EPS CAGR %': growth.eps_growth_3y_cagr,
          'Operating Income Growth YoY %': growth.operating_income_growth_yoy,
          'FCF Growth YoY %': growth.fcf_growth_yoy,
          'Net Income Growth YoY %': growth.net_income_growth_yoy,
          'OCF Growth YoY %': growth.ocf_growth_yoy,
          'Revenue Growth YoY %': growth.revenue_growth_yoy,
          'Asset Growth YoY %': growth.asset_growth_yoy,
          'ROE Trend': growth.roe_trend,
          'Sustainable Growth Rate %': growth.sustainable_growth_rate,
          'Gross Margin Trend': growth.gross_margin_trend,
          'Operating Margin Trend': growth.operating_margin_trend,
          'Net Margin Trend': growth.net_margin_trend,
          'Quarterly Growth Momentum': growth.quarterly_growth_momentum,
        }
      };

      metricsData['Momentum & Technical'] = {
        title: 'Price Momentum & Technical Analysis',
        metrics: {
          'Current Price': momentum.current_price,
          '1M Momentum %': momentum.momentum_1m,
          '3M Momentum %': momentum.momentum_3m,
          '6M Momentum %': momentum.momentum_6m,
          '12M Momentum %': momentum.momentum_12m,
          'Price vs SMA 50 %': momentum.price_vs_sma_50,
          'Price vs SMA 200 %': momentum.price_vs_sma_200,
          'Price vs 52W High %': momentum.price_vs_52w_high,
        }
      };

      metricsData['Risk & Volatility'] = {
        title: 'Risk & Volatility Metrics',
        metrics: {
          '12M Volatility %': stability.volatility_12m,
          'Downside Volatility %': stability.downside_volatility,
          'Max Drawdown 52W %': stability.max_drawdown_52w,
          'Beta': stability.beta,
          'Volume Consistency': stability.volume_consistency,
          'Turnover Velocity': stability.turnover_velocity,
          'Volatility / Volume Ratio': stability.volatility_volume_ratio,
          'Daily Spread %': stability.daily_spread,
        }
      };

      metricsData['Market Sentiment'] = {
        title: 'Market Sentiment & Positioning',
        metrics: {
          'Sentiment Score': sentiment.sentiment_score,
          'Bullish Count': sentiment.bullish_count,
          'Bearish Count': sentiment.bearish_count,
          'Neutral Count': sentiment.neutral_count,
        }
      };

      metricsData['Relative Performance'] = {
        title: 'Relative Performance vs Benchmark',
        metrics: {
          'Alpha': relPerf.alpha,
          'Tracking Error': relPerf.tracking_error,
          'Active Return %': relPerf.active_return,
          'Information Ratio': relPerf.information_ratio,
          'Relative Volatility': relPerf.rel_volatility,
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

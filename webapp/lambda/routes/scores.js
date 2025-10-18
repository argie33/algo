const express = require("express");

const { query } = require("../utils/database");
const responseFormatter = require("../middleware/responseFormatter");

const router = express.Router();

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Basic ping endpoint
router.get("/ping", (req, res) => {
  res.json({
    status: "ok",
    endpoint: "scores",
    timestamp: new Date().toISOString(),
  });
});

// Get comprehensive scores for stocks as a list with proper field names
router.get("/", async (req, res) => {
  try {
    if (process.env.NODE_ENV !== 'test') {
      console.log("📊 Stock Scores List endpoint called - using real stock_scores table");
    }

    const search = req.query.search || '';

    // Query stock scores with proper field names from loadstockscores.py
    // JOIN with company_profile to get company names
    // JOIN with positioning_metrics to get positioning components
    let stocksQuery = `
      SELECT
        ss.symbol,
        cp.short_name as company_name,
        cp.sector,
        ss.composite_score,
        ss.momentum_score,
        ss.value_score,
        ss.quality_score,
        ss.growth_score,
        ss.positioning_score,
        ss.sentiment_score,
        ss.risk_score,
        ss.rsi,
        ss.macd,
        ss.sma_20,
        ss.sma_50,
        ss.current_price,
        ss.price_change_1d,
        ss.price_change_5d,
        ss.price_change_30d,
        ss.volatility_30d,
        ss.market_cap,
        ss.pe_ratio,
        ss.volume_avg_30d,
        ss.score_date,
        ss.last_updated,
        ss.acc_dist_rating,
        -- Momentum components (5-component breakdown)
        ss.momentum_short_term,
        ss.momentum_medium_term,
        ss.momentum_long_term,
        ss.momentum_relative_strength,
        ss.momentum_consistency,
        ss.roc_10d,
        ss.roc_20d,
        ss.roc_60d,
        ss.roc_120d,
        ss.mansfield_rs,
        -- Raw valuation inputs from key_metrics
        km.trailing_pe as stock_pe,
        km.price_to_book as stock_pb,
        km.price_to_sales_ttm as stock_ps,
        km.ev_to_ebitda as stock_ev_ebitda,
        km.free_cashflow::NUMERIC / NULLIF(md.market_cap, 0) * 100 as stock_fcf_yield,
        km.dividend_yield as stock_dividend_yield,
        km.earnings_growth_pct,
        -- Sector benchmarks
        sb.pe_ratio as sector_pe,
        sb.price_to_book as sector_pb,
        sb.price_to_sales as sector_ps,
        sb.ev_to_ebitda as sector_ev_ebitda,
        sb.fcf_yield as sector_fcf_yield,
        sb.dividend_yield as sector_dividend_yield,
        -- Market benchmarks (calculated on-the-fly from all stocks)
        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY trailing_pe) FROM key_metrics WHERE trailing_pe > 0) as market_pe,
        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_to_book) FROM key_metrics WHERE price_to_book > 0) as market_pb,
        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_to_sales_ttm) FROM key_metrics WHERE price_to_sales_ttm > 0) as market_ps,
        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km2.free_cashflow::NUMERIC / NULLIF(md2.market_cap, 0) * 100) FROM key_metrics km2 INNER JOIN market_data md2 ON km2.ticker = md2.ticker WHERE km2.free_cashflow > 0 AND md2.market_cap > 0) as market_fcf_yield,
        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dividend_yield) FROM key_metrics WHERE dividend_yield > 0) as market_dividend_yield,
        pm.institutional_ownership,
        pm.insider_ownership,
        pm.short_percent_of_float,
        pm.short_ratio,
        pm.institution_count,
        -- Quality INPUT metrics from quality_metrics table (13 professional quality inputs)
        qm.return_on_equity_pct,
        qm.return_on_assets_pct,
        qm.gross_margin_pct,
        qm.operating_margin_pct,
        qm.profit_margin_pct,
        qm.fcf_to_net_income,
        qm.operating_cf_to_net_income,
        qm.debt_to_equity,
        qm.current_ratio,
        qm.quick_ratio,
        qm.earnings_surprise_avg,
        qm.eps_growth_stability,
        qm.payout_ratio,
        -- Growth INPUT metrics from growth_metrics table (12 professional growth inputs)
        gm.revenue_growth_3y_cagr,
        gm.eps_growth_3y_cagr,
        gm.operating_income_growth_yoy,
        gm.roe_trend,
        gm.sustainable_growth_rate,
        gm.fcf_growth_yoy,
        gm.net_income_growth_yoy,
        gm.gross_margin_trend,
        gm.operating_margin_trend,
        gm.net_margin_trend,
        gm.quarterly_growth_momentum,
        gm.asset_growth_yoy,
        -- Raw momentum INPUT metrics from momentum_metrics table (dual momentum)
        mm.momentum_12m_1,
        mm.momentum_6m,
        mm.momentum_3m,
        mm.risk_adjusted_momentum,
        mm.price_vs_sma_50,
        mm.price_vs_sma_200,
        mm.price_vs_52w_high,
        mm.high_52w,
        mm.sma_50,
        mm.sma_200,
        mm.volatility_12m,
        -- Risk INPUT metrics from risk_metrics table
        rm.volatility_12m_pct,
        rm.volatility_risk_component,
        rm.max_drawdown_52w_pct,
        rm.beta
      FROM stock_scores ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol,
          institutional_ownership,
          insider_ownership,
          short_percent_of_float,
          short_ratio,
          institution_count
        FROM positioning_metrics
        ORDER BY symbol, date DESC
      ) pm ON ss.symbol = pm.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (ticker)
          ticker,
          trailing_pe,
          price_to_book,
          price_to_sales_ttm,
          ev_to_ebitda,
          earnings_growth_pct,
          free_cashflow,
          dividend_yield
        FROM key_metrics
        ORDER BY ticker
      ) km ON ss.symbol = km.ticker
      LEFT JOIN sector_benchmarks sb ON cp.sector = sb.sector
      LEFT JOIN (
        SELECT DISTINCT ON (ticker)
          ticker,
          market_cap
        FROM market_data
        ORDER BY ticker
      ) md ON ss.symbol = md.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol,
          return_on_equity_pct,
          return_on_assets_pct,
          gross_margin_pct,
          operating_margin_pct,
          profit_margin_pct,
          fcf_to_net_income,
          operating_cf_to_net_income,
          debt_to_equity,
          current_ratio,
          quick_ratio,
          earnings_surprise_avg,
          eps_growth_stability,
          payout_ratio
        FROM quality_metrics
        ORDER BY symbol, date DESC
      ) qm ON ss.symbol = qm.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol,
          revenue_growth_3y_cagr,
          eps_growth_3y_cagr,
          operating_income_growth_yoy,
          roe_trend,
          sustainable_growth_rate,
          fcf_growth_yoy,
          net_income_growth_yoy,
          gross_margin_trend,
          operating_margin_trend,
          net_margin_trend,
          quarterly_growth_momentum,
          asset_growth_yoy
        FROM growth_metrics
        ORDER BY symbol, date DESC
      ) gm ON ss.symbol = gm.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol,
          momentum_12m_1,
          momentum_6m,
          momentum_3m,
          risk_adjusted_momentum,
          price_vs_sma_50,
          price_vs_sma_200,
          price_vs_52w_high,
          high_52w,
          sma_50,
          sma_200,
          volatility_12m
        FROM momentum_metrics
        ORDER BY symbol, date DESC
      ) mm ON ss.symbol = mm.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol,
          volatility_12m_pct,
          volatility_risk_component,
          max_drawdown_52w_pct,
          beta
        FROM risk_metrics
        ORDER BY symbol, date DESC
      ) rm ON ss.symbol = rm.symbol
    `;

    const queryParams = [];
    let paramIndex = 1;

    // Add search filter if provided
    if (search) {
      stocksQuery += ` WHERE ss.symbol ILIKE $${paramIndex}`;
      queryParams.push(`%${search.toUpperCase()}%`);
      paramIndex++;
    }

    stocksQuery += ` ORDER BY ss.composite_score DESC`;
    // No LIMIT or OFFSET - return all results for frontend filtering

    const stocksResult = await query(stocksQuery, queryParams);

    if (!stocksResult || !stocksResult.rows) {
      return res.status(500).json({
        success: false,
        error: "Database query returned null result",
        timestamp: new Date().toISOString(),
      });
    }

    // Handle empty results gracefully
    if (stocksResult.rows.length === 0) {
      return res.json({
        success: true,
        data: { stocks: [], viewType: "list" },
        summary: {
          totalStocks: 0,
          averageScore: 0,
          topScore: 0,
          scoreRange: "0 - 0"
        },
        metadata: {
          dataSource: "stock_scores_real_table",
          searchTerm: search || null,
          lastUpdated: null,
          factorAnalysis: "seven_factor_scoring_system"
        },
        timestamp: new Date().toISOString(),
      });
    }

    // Map results to flat format matching frontend expectations
    const stocksList = stocksResult.rows.map(row => ({
      symbol: row.symbol,
      company_name: row.company_name,
      sector: row.sector,
      composite_score: parseFloat(row.composite_score) || 0,
      momentum_score: parseFloat(row.momentum_score) || 0,
      value_score: parseFloat(row.value_score) || 0,
      quality_score: parseFloat(row.quality_score) || 0,
      growth_score: parseFloat(row.growth_score),
      positioning_score: parseFloat(row.positioning_score) || 0,
      sentiment_score: parseFloat(row.sentiment_score) || 0,
      risk_score: parseFloat(row.risk_score) || null,
      current_price: parseFloat(row.current_price) || 0,
      price_change_1d: parseFloat(row.price_change_1d) || 0,
      price_change_5d: parseFloat(row.price_change_5d) || 0,
      price_change_30d: parseFloat(row.price_change_30d) || 0,
      volatility_30d: parseFloat(row.volatility_30d) || 0,
      market_cap: parseInt(row.market_cap) || 0,
      volume_avg_30d: parseInt(row.volume_avg_30d) || 0,
      pe_ratio: parseFloat(row.pe_ratio) || null,
      rsi: parseFloat(row.rsi) || 0,
      sma_20: parseFloat(row.sma_20) || 0,
      sma_50: parseFloat(row.sma_50) || 0,
      macd: parseFloat(row.macd) || null,
      last_updated: row.last_updated,
      score_date: row.score_date,
      // Momentum component breakdown (5-component system)
      momentum_components: {
        short_term: parseFloat(row.momentum_short_term) || null,
        medium_term: parseFloat(row.momentum_medium_term) || null,
        longer_term: parseFloat(row.momentum_long_term) || null,
        relative_strength: parseFloat(row.momentum_relative_strength) || null,
        consistency: parseFloat(row.momentum_consistency) || null,
        roc_10d: parseFloat(row.roc_10d) || null,
        roc_20d: parseFloat(row.roc_20d) || null,
        roc_60d: parseFloat(row.roc_60d) || null,
        roc_120d: parseFloat(row.roc_120d) || null,
        mansfield_rs: parseFloat(row.mansfield_rs) || null
      },
      // Add positioning components for frontend chart display
      positioning_components: {
        institutional_ownership: parseFloat(row.institutional_ownership) || null,
        insider_ownership: parseFloat(row.insider_ownership) || null,
        short_percent_of_float: parseFloat(row.short_percent_of_float) || null,
        short_ratio: parseFloat(row.short_ratio) || null,
        days_to_cover: parseFloat(row.short_ratio) || null, // days_to_cover is same as short_ratio
        institution_count: parseInt(row.institution_count) || null,
        acc_dist_rating: parseFloat(row.acc_dist_rating) || null
      },
      // Add raw valuation inputs for frontend display
      value_inputs: {
        stock_pe: parseFloat(row.stock_pe) || null,
        stock_pb: parseFloat(row.stock_pb) || null,
        stock_ps: parseFloat(row.stock_ps) || null,
        stock_ev_ebitda: parseFloat(row.stock_ev_ebitda) || null,
        stock_fcf_yield: parseFloat(row.stock_fcf_yield) || null,
        stock_dividend_yield: parseFloat(row.stock_dividend_yield) || null,
        sector_pe: parseFloat(row.sector_pe) || null,
        sector_pb: parseFloat(row.sector_pb) || null,
        sector_ps: parseFloat(row.sector_ps) || null,
        sector_ev_ebitda: parseFloat(row.sector_ev_ebitda) || null,
        sector_fcf_yield: parseFloat(row.sector_fcf_yield) || null,
        sector_dividend_yield: parseFloat(row.sector_dividend_yield) || null,
        market_pe: parseFloat(row.market_pe) || null,
        market_pb: parseFloat(row.market_pb) || null,
        market_ps: parseFloat(row.market_ps) || null,
        market_fcf_yield: parseFloat(row.market_fcf_yield) || null,
        market_dividend_yield: parseFloat(row.market_dividend_yield) || null,
        earnings_growth_pct: parseFloat(row.earnings_growth_pct) || null,
        peg_ratio: (row.stock_pe && row.earnings_growth_pct && row.earnings_growth_pct > 0)
          ? parseFloat((row.stock_pe / row.earnings_growth_pct).toFixed(2))
          : null
      },
      // Add quality INPUT metrics for frontend display (13 professional quality inputs)
      quality_inputs: {
        return_on_equity_pct: parseFloat(row.return_on_equity_pct) || null,
        return_on_assets_pct: parseFloat(row.return_on_assets_pct) || null,
        gross_margin_pct: parseFloat(row.gross_margin_pct) || null,
        operating_margin_pct: parseFloat(row.operating_margin_pct) || null,
        profit_margin_pct: parseFloat(row.profit_margin_pct) || null,
        fcf_to_net_income: parseFloat(row.fcf_to_net_income) || null,
        operating_cf_to_net_income: parseFloat(row.operating_cf_to_net_income) || null,
        debt_to_equity: parseFloat(row.debt_to_equity) || null,
        current_ratio: parseFloat(row.current_ratio) || null,
        quick_ratio: parseFloat(row.quick_ratio) || null,
        earnings_surprise_avg: parseFloat(row.earnings_surprise_avg) || null,
        eps_growth_stability: parseFloat(row.eps_growth_stability) || null,
        payout_ratio: parseFloat(row.payout_ratio) || null
      },
      // Add growth INPUT metrics for frontend display (12 professional growth inputs)
      growth_inputs: {
        revenue_growth_3y_cagr: parseFloat(row.revenue_growth_3y_cagr) || null,
        eps_growth_3y_cagr: parseFloat(row.eps_growth_3y_cagr) || null,
        operating_income_growth_yoy: parseFloat(row.operating_income_growth_yoy) || null,
        roe_trend: parseFloat(row.roe_trend) || null,
        sustainable_growth_rate: parseFloat(row.sustainable_growth_rate) || null,
        fcf_growth_yoy: parseFloat(row.fcf_growth_yoy) || null,
        net_income_growth_yoy: parseFloat(row.net_income_growth_yoy) || null,
        gross_margin_trend: parseFloat(row.gross_margin_trend) || null,
        operating_margin_trend: parseFloat(row.operating_margin_trend) || null,
        net_margin_trend: parseFloat(row.net_margin_trend) || null,
        quarterly_growth_momentum: parseFloat(row.quarterly_growth_momentum) || null,
        asset_growth_yoy: parseFloat(row.asset_growth_yoy) || null
      },
      // Add raw momentum INPUT metrics for professional momentum display (dual momentum)
      // Use momentum_metrics table data if available, otherwise fallback to stock_scores columns
      momentum_inputs: {
        // Relative Momentum (vs other stocks)
        momentum_12m_1: parseFloat(row.momentum_12m_1) || null,
        momentum_6m: parseFloat(row.momentum_6m) || parseFloat(row.momentum_medium_term) || null,
        momentum_3m: parseFloat(row.momentum_3m) || null,
        risk_adjusted_momentum: parseFloat(row.risk_adjusted_momentum) || null,
        // Absolute Momentum (vs itself)
        price_vs_sma_50: parseFloat(row.price_vs_sma_50) || null,
        price_vs_sma_200: parseFloat(row.price_vs_sma_200) || null,
        price_vs_52w_high: parseFloat(row.price_vs_52w_high) || null,
        // Supporting data
        high_52w: parseFloat(row.high_52w) || null,
        sma_50: parseFloat(row.sma_50) || null,
        sma_200: parseFloat(row.sma_200) || null,
        volatility_12m: parseFloat(row.volatility_12m) || null,
        // Fallback for legacy display
        fallbacks: {
          momentum_medium_term: parseFloat(row.momentum_medium_term)?.toFixed(2) || null,
          roc_252d: parseFloat(row.roc_252d)?.toFixed(2) || undefined,
          momentum_score: parseFloat(row.momentum_score)?.toFixed(2) || null
        }
      },
      // Add raw risk INPUT metrics for Risk Factor Analysis display
      risk_inputs: {
        volatility_12m_pct: parseFloat(row.volatility_12m_pct) || null,
        volatility_risk_component: parseFloat(row.volatility_risk_component) || null,
        max_drawdown_52w_pct: parseFloat(row.max_drawdown_52w_pct) || null,
        beta: parseFloat(row.beta) || null
      }
    }));

    // Return all results - no pagination needed for small dataset
    res.json({
      success: true,
      data: {
        stocks: stocksList,
        viewType: "list"
      },
      summary: {
        totalStocks: stocksList.length,
        averageScore: stocksList.length > 0
          ? Math.round(stocksList.reduce((sum, s) => sum + s.composite_score, 0) / stocksList.length * 100) / 100
          : 0,
        topScore: stocksList.length > 0 ? stocksList[0].composite_score : 0,
        scoreRange: stocksList.length > 0 ?
          `${stocksList[stocksList.length - 1].composite_score} - ${stocksList[0].composite_score}` : "0 - 0"
      },
      metadata: {
        dataSource: "stock_scores_real_table",
        searchTerm: search || null,
        lastUpdated: stocksList.length > 0 ? stocksList[0].lastUpdated : null,
        factorAnalysis: "seven_factor_scoring_system"
      },
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error("Stock scores list error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch stock scores",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get detailed scores for specific symbol with six factor analysis
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    if (process.env.NODE_ENV !== 'test') {
      console.log(`📊 Detailed scores requested for symbol: ${symbol.toUpperCase()} - using real table`);
    }

    const symbolQuery = `
      SELECT
        ss.symbol,
        cp.short_name as company_name,
        cp.sector,
        ss.composite_score,
        ss.momentum_score,
        ss.value_score,
        ss.quality_score,
        ss.growth_score,
        ss.positioning_score,
        ss.sentiment_score,
        ss.risk_score,
        ss.rsi,
        ss.macd,
        ss.sma_20,
        ss.sma_50,
        ss.current_price,
        ss.price_change_1d,
        ss.price_change_5d,
        ss.price_change_30d,
        ss.volatility_30d,
        ss.market_cap,
        ss.pe_ratio,
        ss.volume_avg_30d,
        ss.score_date,
        ss.last_updated,
        ss.acc_dist_rating,
        -- Momentum components (5-component breakdown)
        ss.momentum_short_term,
        ss.momentum_medium_term,
        ss.momentum_long_term,
        ss.momentum_relative_strength,
        ss.momentum_consistency,
        ss.roc_10d,
        ss.roc_20d,
        ss.roc_60d,
        ss.roc_120d,
        ss.mansfield_rs,
        -- Raw valuation inputs from key_metrics
        km.trailing_pe as stock_pe,
        km.price_to_book as stock_pb,
        km.price_to_sales_ttm as stock_ps,
        km.ev_to_ebitda as stock_ev_ebitda,
        km.free_cashflow::NUMERIC / NULLIF(md.market_cap, 0) * 100 as stock_fcf_yield,
        km.dividend_yield as stock_dividend_yield,
        km.earnings_growth_pct,
        -- Sector benchmarks
        sb.pe_ratio as sector_pe,
        sb.price_to_book as sector_pb,
        sb.price_to_sales as sector_ps,
        sb.ev_to_ebitda as sector_ev_ebitda,
        sb.fcf_yield as sector_fcf_yield,
        sb.dividend_yield as sector_dividend_yield,
        -- Market benchmarks (calculated on-the-fly from all stocks)
        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY trailing_pe) FROM key_metrics WHERE trailing_pe > 0) as market_pe,
        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_to_book) FROM key_metrics WHERE price_to_book > 0) as market_pb,
        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_to_sales_ttm) FROM key_metrics WHERE price_to_sales_ttm > 0) as market_ps,
        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km2.free_cashflow::NUMERIC / NULLIF(md2.market_cap, 0) * 100) FROM key_metrics km2 INNER JOIN market_data md2 ON km2.ticker = md2.ticker WHERE km2.free_cashflow > 0 AND md2.market_cap > 0) as market_fcf_yield,
        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dividend_yield) FROM key_metrics WHERE dividend_yield > 0) as market_dividend_yield,
        -- Add positioning components from positioning_metrics table
        pm.institutional_ownership,
        pm.insider_ownership,
        pm.short_percent_of_float,
        pm.short_ratio,
        pm.institution_count,
        -- Quality INPUT metrics from quality_metrics table (13 professional quality inputs)
        qm.return_on_equity_pct,
        qm.return_on_assets_pct,
        qm.gross_margin_pct,
        qm.operating_margin_pct,
        qm.profit_margin_pct,
        qm.fcf_to_net_income,
        qm.operating_cf_to_net_income,
        qm.debt_to_equity,
        qm.current_ratio,
        qm.quick_ratio,
        qm.earnings_surprise_avg,
        qm.eps_growth_stability,
        qm.payout_ratio,
        -- Growth INPUT metrics from growth_metrics table (12 professional growth inputs)
        gm.revenue_growth_3y_cagr,
        gm.eps_growth_3y_cagr,
        gm.operating_income_growth_yoy,
        gm.roe_trend,
        gm.sustainable_growth_rate,
        gm.fcf_growth_yoy,
        gm.net_income_growth_yoy,
        gm.gross_margin_trend,
        gm.operating_margin_trend,
        gm.net_margin_trend,
        gm.quarterly_growth_momentum,
        gm.asset_growth_yoy,
        -- Raw momentum INPUT metrics from momentum_metrics table (dual momentum)
        mm.momentum_12m_1,
        mm.momentum_6m,
        mm.momentum_3m,
        mm.risk_adjusted_momentum,
        mm.price_vs_sma_50,
        mm.price_vs_sma_200,
        mm.price_vs_52w_high,
        mm.high_52w,
        mm.sma_50,
        mm.sma_200,
        mm.volatility_12m,
        -- Risk INPUT metrics from risk_metrics table
        rm.volatility_12m_pct,
        rm.volatility_risk_component,
        rm.max_drawdown_52w_pct,
        rm.beta
      FROM stock_scores ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol,
          institutional_ownership,
          insider_ownership,
          short_percent_of_float,
          short_ratio,
          institution_count
        FROM positioning_metrics
        ORDER BY symbol, date DESC
      ) pm ON ss.symbol = pm.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (ticker)
          ticker,
          trailing_pe,
          price_to_book,
          price_to_sales_ttm,
          ev_to_ebitda,
          earnings_growth_pct,
          free_cashflow,
          dividend_yield
        FROM key_metrics
        ORDER BY ticker
      ) km ON ss.symbol = km.ticker
      LEFT JOIN sector_benchmarks sb ON cp.sector = sb.sector
      LEFT JOIN (
        SELECT DISTINCT ON (ticker)
          ticker,
          market_cap
        FROM market_data
        ORDER BY ticker
      ) md ON ss.symbol = md.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol,
          return_on_equity_pct,
          return_on_assets_pct,
          gross_margin_pct,
          operating_margin_pct,
          profit_margin_pct,
          fcf_to_net_income,
          operating_cf_to_net_income,
          debt_to_equity,
          current_ratio,
          quick_ratio,
          earnings_surprise_avg,
          eps_growth_stability,
          payout_ratio
        FROM quality_metrics
        ORDER BY symbol, date DESC
      ) qm ON ss.symbol = qm.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol,
          revenue_growth_3y_cagr,
          eps_growth_3y_cagr,
          operating_income_growth_yoy,
          roe_trend,
          sustainable_growth_rate,
          fcf_growth_yoy,
          net_income_growth_yoy,
          gross_margin_trend,
          operating_margin_trend,
          net_margin_trend,
          quarterly_growth_momentum,
          asset_growth_yoy
        FROM growth_metrics
        ORDER BY symbol, date DESC
      ) gm ON ss.symbol = gm.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol,
          momentum_12m_1,
          momentum_6m,
          momentum_3m,
          risk_adjusted_momentum,
          price_vs_sma_50,
          price_vs_sma_200,
          price_vs_52w_high,
          high_52w,
          sma_50,
          sma_200,
          volatility_12m
        FROM momentum_metrics
        ORDER BY symbol, date DESC
      ) mm ON ss.symbol = mm.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol,
          volatility_12m_pct,
          volatility_risk_component,
          max_drawdown_52w_pct,
          beta
        FROM risk_metrics
        ORDER BY symbol, date DESC
      ) rm ON ss.symbol = rm.symbol
      WHERE ss.symbol = $1
    `;

    const result = await query(symbolQuery, [symbol.toUpperCase()]);

    if (!result || !result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Symbol not found in stock_scores table",
        symbol: symbol.toUpperCase(),
        timestamp: new Date().toISOString(),
      });
    }

    const row = result.rows[0];

    res.json({
      success: true,
      data: {
        symbol: row.symbol,
        companyName: row.company_name,
        sector: row.sector,
        compositeScore: parseFloat(row.composite_score) || 0,
        currentPrice: parseFloat(row.current_price) || 0,
        priceChange1d: parseFloat(row.price_change_1d) || 0,
        volume: parseInt(row.volume_avg_30d) || 0,
        marketCap: parseInt(row.market_cap) || 0,
        peRatio: parseFloat(row.pe_ratio) || null,
        lastUpdated: row.last_updated,
        scoreDate: row.score_date,
        // Nested factors object for tests
        factors: {
          momentum: {
            score: parseFloat(row.momentum_score) || 0,
            components: {
              short_term: parseFloat(row.momentum_short_term) || null,
              medium_term: parseFloat(row.momentum_medium_term) || null,
              longer_term: parseFloat(row.momentum_long_term) || null,
              relative_strength: parseFloat(row.momentum_relative_strength) || null,
              consistency: parseFloat(row.momentum_consistency) || null,
              rsi: parseFloat(row.rsi) || 0,
              roc_10d: parseFloat(row.roc_10d) || null,
              roc_60d: parseFloat(row.roc_60d) || null,
              roc_120d: parseFloat(row.roc_120d) || null,
              mansfield_rs: parseFloat(row.mansfield_rs) || null
            },
            inputs: {
              // Relative Momentum (vs other stocks)
              momentum_12m_1: parseFloat(row.momentum_12m_1) || null,
              momentum_6m: parseFloat(row.momentum_6m) || parseFloat(row.momentum_medium_term) || null,
              momentum_3m: parseFloat(row.momentum_3m) || null,
              risk_adjusted_momentum: parseFloat(row.risk_adjusted_momentum) || null,
              // Absolute Momentum (vs itself)
              price_vs_sma_50: parseFloat(row.price_vs_sma_50) || null,
              price_vs_sma_200: parseFloat(row.price_vs_sma_200) || null,
              price_vs_52w_high: parseFloat(row.price_vs_52w_high) || null,
              // Supporting data
              high_52w: parseFloat(row.high_52w) || null,
              sma_50: parseFloat(row.sma_50) || null,
              sma_200: parseFloat(row.sma_200) || null,
              volatility_12m: parseFloat(row.volatility_12m) || null,
              // Fallback for legacy display
              fallbacks: {
                momentum_medium_term: parseFloat(row.momentum_medium_term)?.toFixed(2) || null,
                roc_252d: parseFloat(row.roc_252d)?.toFixed(2) || undefined,
                momentum_score: parseFloat(row.momentum_score)?.toFixed(2) || null
              }
            }
          },
          value: {
            score: parseFloat(row.value_score) || 0,
            inputs: {
              stock_pe: parseFloat(row.stock_pe) || null,
              stock_pb: parseFloat(row.stock_pb) || null,
              stock_ps: parseFloat(row.stock_ps) || null,
              stock_ev_ebitda: parseFloat(row.stock_ev_ebitda) || null,
              stock_fcf_yield: parseFloat(row.stock_fcf_yield) || null,
              stock_dividend_yield: parseFloat(row.stock_dividend_yield) || null,
              sector_pe: parseFloat(row.sector_pe) || null,
              sector_pb: parseFloat(row.sector_pb) || null,
              sector_ps: parseFloat(row.sector_ps) || null,
              sector_ev_ebitda: parseFloat(row.sector_ev_ebitda) || null,
              sector_fcf_yield: parseFloat(row.sector_fcf_yield) || null,
              sector_dividend_yield: parseFloat(row.sector_dividend_yield) || null,
              market_pe: parseFloat(row.market_pe) || null,
              market_pb: parseFloat(row.market_pb) || null,
              market_ps: parseFloat(row.market_ps) || null,
              market_fcf_yield: parseFloat(row.market_fcf_yield) || null,
              market_dividend_yield: parseFloat(row.market_dividend_yield) || null,
              earnings_growth_pct: parseFloat(row.earnings_growth_pct) || null,
              peg_ratio: (row.stock_pe && row.earnings_growth_pct && row.earnings_growth_pct > 0)
                ? parseFloat((row.stock_pe / row.earnings_growth_pct).toFixed(2))
                : null
            }
          },
          quality: {
            score: parseFloat(row.quality_score) || 0,
            inputs: {
              return_on_equity_pct: parseFloat(row.return_on_equity_pct) || null,
              return_on_assets_pct: parseFloat(row.return_on_assets_pct) || null,
              gross_margin_pct: parseFloat(row.gross_margin_pct) || null,
              operating_margin_pct: parseFloat(row.operating_margin_pct) || null,
              profit_margin_pct: parseFloat(row.profit_margin_pct) || null,
              fcf_to_net_income: parseFloat(row.fcf_to_net_income) || null,
              operating_cf_to_net_income: parseFloat(row.operating_cf_to_net_income) || null,
              debt_to_equity: parseFloat(row.debt_to_equity) || null,
              current_ratio: parseFloat(row.current_ratio) || null,
              quick_ratio: parseFloat(row.quick_ratio) || null,
              earnings_surprise_avg: parseFloat(row.earnings_surprise_avg) || null,
              eps_growth_stability: parseFloat(row.eps_growth_stability) || null,
              payout_ratio: parseFloat(row.payout_ratio) || null
            }
          },
          growth: {
            score: parseFloat(row.growth_score) || 0,
            inputs: {
              revenue_growth_3y_cagr: parseFloat(row.revenue_growth_3y_cagr) || null,
              eps_growth_3y_cagr: parseFloat(row.eps_growth_3y_cagr) || null,
              operating_income_growth_yoy: parseFloat(row.operating_income_growth_yoy) || null,
              roe_trend: parseFloat(row.roe_trend) || null,
              sustainable_growth_rate: parseFloat(row.sustainable_growth_rate) || null,
              fcf_growth_yoy: parseFloat(row.fcf_growth_yoy) || null,
              net_income_growth_yoy: parseFloat(row.net_income_growth_yoy) || null,
              gross_margin_trend: parseFloat(row.gross_margin_trend) || null,
              operating_margin_trend: parseFloat(row.operating_margin_trend) || null,
              net_margin_trend: parseFloat(row.net_margin_trend) || null,
              quarterly_growth_momentum: parseFloat(row.quarterly_growth_momentum) || null,
              asset_growth_yoy: parseFloat(row.asset_growth_yoy) || null
            }
          },
          positioning: {
            score: parseFloat(row.positioning_score) || 0,
            components: {
              institutional_ownership: parseFloat(row.institutional_ownership) || null,
              insider_ownership: parseFloat(row.insider_ownership) || null,
              short_percent_of_float: parseFloat(row.short_percent_of_float) || null,
              short_ratio: parseFloat(row.short_ratio) || null,
              days_to_cover: parseFloat(row.short_ratio) || null,
              institution_count: parseInt(row.institution_count) || null,
              acc_dist_rating: parseFloat(row.acc_dist_rating) || null
            }
          },
          sentiment: {
            score: parseFloat(row.sentiment_score) || 0,
            components: {}
          },
          risk: {
            score: parseFloat(row.risk_score) || null,
            inputs: {
              volatility_12m_pct: parseFloat(row.volatility_12m_pct) || null,
              volatility_risk_component: parseFloat(row.volatility_risk_component) || null,
              max_drawdown_52w_pct: parseFloat(row.max_drawdown_52w_pct) || null,
              beta: parseFloat(row.beta) || null
            }
          }
        },
        // Nested performance object for tests
        performance: {
          priceChange1d: parseFloat(row.price_change_1d) || 0,
          priceChange5d: parseFloat(row.price_change_5d) || 0,
          priceChange30d: parseFloat(row.price_change_30d) || 0,
          volatility30d: parseFloat(row.volatility_30d) || 0
        },
        // Keep snake_case versions for backward compatibility with frontend
        company_name: row.company_name,
        composite_score: parseFloat(row.composite_score) || 0,
        momentum_score: parseFloat(row.momentum_score) || 0,
        value_score: parseFloat(row.value_score) || 0,
        quality_score: parseFloat(row.quality_score) || 0,
        growth_score: parseFloat(row.growth_score) || 0,
        positioning_score: parseFloat(row.positioning_score) || 0,
        sentiment_score: parseFloat(row.sentiment_score) || 0,
        risk_score: parseFloat(row.risk_score) || null,
        current_price: parseFloat(row.current_price) || 0,
        price_change_1d: parseFloat(row.price_change_1d) || 0,
        price_change_5d: parseFloat(row.price_change_5d) || 0,
        price_change_30d: parseFloat(row.price_change_30d) || 0,
        volatility_30d: parseFloat(row.volatility_30d) || 0,
        market_cap: parseInt(row.market_cap) || 0,
        volume_avg_30d: parseInt(row.volume_avg_30d) || 0,
        pe_ratio: parseFloat(row.pe_ratio) || null,
        rsi: parseFloat(row.rsi) || 0,
        sma_20: parseFloat(row.sma_20) || 0,
        sma_50: parseFloat(row.sma_50) || 0,
        macd: parseFloat(row.macd) || null,
        last_updated: row.last_updated,
        score_date: row.score_date,
        // Risk inputs for frontend display (Risk Factor Analysis)
        risk_inputs: {
          volatility_12m_pct: parseFloat(row.volatility_12m_pct) || null,
          volatility_risk_component: parseFloat(row.volatility_risk_component) || null,
          max_drawdown_52w_pct: parseFloat(row.max_drawdown_52w_pct) || null,
          beta: parseFloat(row.beta) || null
        }
      },
      metadata: {
        dataSource: "stock_scores_real_table",
        factorAnalysis: "seven_factor_scoring_system",
        calculationMethod: "loadstockscores_algorithm"
      },
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error(`Detailed scores error for symbol ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch detailed symbol scores",
      details: error.message,
      symbol: req.params.symbol?.toUpperCase() || null,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;
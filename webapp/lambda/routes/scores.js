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
        -- Sector benchmarks (only columns that exist in sector_benchmarks table)
        sb.pe_ratio as sector_pe,
        sb.price_to_book as sector_pb,
        sb.ev_to_ebitda as sector_ev_ebitda,
        sb.debt_to_equity as sector_debt_to_equity,
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
    // NO FALLBACK OPERATORS - Return NULL for missing data, don't mask with default values
    const stocksList = stocksResult.rows.map(row => ({
      symbol: row.symbol,
      company_name: row.company_name,
      sector: row.sector,
      composite_score: row.composite_score == null ? null : parseFloat(row.composite_score),
      momentum_score: row.momentum_score == null ? null : parseFloat(row.momentum_score),
      value_score: row.value_score == null ? null : parseFloat(row.value_score),
      quality_score: row.quality_score == null ? null : parseFloat(row.quality_score),
      growth_score: row.growth_score == null ? null : parseFloat(row.growth_score),
      positioning_score: row.positioning_score == null ? null : parseFloat(row.positioning_score),
      sentiment_score: row.sentiment_score == null ? null : parseFloat(row.sentiment_score),
      risk_score: row.risk_score == null ? null : parseFloat(row.risk_score),
      current_price: row.current_price == null ? null : parseFloat(row.current_price),
      price_change_1d: row.price_change_1d == null ? null : parseFloat(row.price_change_1d),
      price_change_5d: row.price_change_5d == null ? null : parseFloat(row.price_change_5d),
      price_change_30d: row.price_change_30d == null ? null : parseFloat(row.price_change_30d),
      volatility_30d: row.volatility_30d == null ? null : parseFloat(row.volatility_30d),
      market_cap: row.market_cap == null ? null : parseInt(row.market_cap),
      volume_avg_30d: row.volume_avg_30d == null ? null : parseInt(row.volume_avg_30d),
      pe_ratio: row.pe_ratio == null ? null : parseFloat(row.pe_ratio),
      rsi: row.rsi == null ? null : parseFloat(row.rsi),
      sma_20: row.sma_20 == null ? null : parseFloat(row.sma_20),
      sma_50: row.sma_50 == null ? null : parseFloat(row.sma_50),
      macd: row.macd == null ? null : parseFloat(row.macd),
      last_updated: row.last_updated,
      score_date: row.score_date,
      // Momentum component breakdown (5-component system) - NO FALLBACKS
      momentum_components: {
        short_term: row.momentum_short_term == null ? null : parseFloat(row.momentum_short_term),
        medium_term: row.momentum_medium_term == null ? null : parseFloat(row.momentum_medium_term),
        longer_term: row.momentum_long_term == null ? null : parseFloat(row.momentum_long_term),
        relative_strength: row.momentum_relative_strength == null ? null : parseFloat(row.momentum_relative_strength),
        consistency: row.momentum_consistency == null ? null : parseFloat(row.momentum_consistency),
        roc_10d: row.roc_10d == null ? null : parseFloat(row.roc_10d),
        roc_20d: row.roc_20d == null ? null : parseFloat(row.roc_20d),
        roc_60d: row.roc_60d == null ? null : parseFloat(row.roc_60d),
        roc_120d: row.roc_120d == null ? null : parseFloat(row.roc_120d),
        mansfield_rs: row.mansfield_rs == null ? null : parseFloat(row.mansfield_rs)
      },
      // Add positioning components for frontend chart display - NO FALLBACKS
      positioning_components: {
        institutional_ownership: row.institutional_ownership == null ? null : parseFloat(row.institutional_ownership),
        insider_ownership: row.insider_ownership == null ? null : parseFloat(row.insider_ownership),
        short_percent_of_float: row.short_percent_of_float == null ? null : parseFloat(row.short_percent_of_float),
        short_ratio: row.short_ratio == null ? null : parseFloat(row.short_ratio),
        days_to_cover: row.short_ratio == null ? null : parseFloat(row.short_ratio), // days_to_cover is same as short_ratio
        institution_count: row.institution_count == null ? null : parseInt(row.institution_count),
        acc_dist_rating: row.acc_dist_rating == null ? null : parseFloat(row.acc_dist_rating)
      },
      // Add raw valuation inputs for frontend display
      value_inputs: {
        stock_pe: row.stock_pe == null ? null : parseFloat(row.stock_pe),
        stock_pb: row.stock_pb == null ? null : parseFloat(row.stock_pb),
        stock_ps: row.stock_ps == null ? null : parseFloat(row.stock_ps),
        stock_ev_ebitda: row.stock_ev_ebitda == null ? null : parseFloat(row.stock_ev_ebitda),
        stock_fcf_yield: row.stock_fcf_yield == null ? null : parseFloat(row.stock_fcf_yield),
        stock_dividend_yield: row.stock_dividend_yield == null ? null : parseFloat(row.stock_dividend_yield),
        sector_pe: row.sector_pe == null ? null : parseFloat(row.sector_pe),
        sector_pb: row.sector_pb == null ? null : parseFloat(row.sector_pb),
        sector_ev_ebitda: row.sector_ev_ebitda == null ? null : parseFloat(row.sector_ev_ebitda),
        sector_debt_to_equity: row.sector_debt_to_equity == null ? null : parseFloat(row.sector_debt_to_equity),
        market_pe: row.market_pe == null ? null : parseFloat(row.market_pe),
        market_pb: row.market_pb == null ? null : parseFloat(row.market_pb),
        market_ps: row.market_ps == null ? null : parseFloat(row.market_ps),
        market_fcf_yield: row.market_fcf_yield == null ? null : parseFloat(row.market_fcf_yield),
        market_dividend_yield: row.market_dividend_yield == null ? null : parseFloat(row.market_dividend_yield),
        earnings_growth_pct: row.earnings_growth_pct == null ? null : parseFloat(row.earnings_growth_pct),
        peg_ratio: (row.stock_pe && row.earnings_growth_pct && row.earnings_growth_pct > 0)
          ? parseFloat((row.stock_pe / row.earnings_growth_pct).toFixed(2))
          : null
      },
      // Add quality INPUT metrics for frontend display (13 professional quality inputs)
      quality_inputs: {
        return_on_equity_pct: row.return_on_equity_pct == null ? null : parseFloat(row.return_on_equity_pct),
        return_on_assets_pct: row.return_on_assets_pct == null ? null : parseFloat(row.return_on_assets_pct),
        gross_margin_pct: row.gross_margin_pct == null ? null : parseFloat(row.gross_margin_pct),
        operating_margin_pct: row.operating_margin_pct == null ? null : parseFloat(row.operating_margin_pct),
        profit_margin_pct: row.profit_margin_pct == null ? null : parseFloat(row.profit_margin_pct),
        fcf_to_net_income: row.fcf_to_net_income == null ? null : parseFloat(row.fcf_to_net_income),
        operating_cf_to_net_income: row.operating_cf_to_net_income == null ? null : parseFloat(row.operating_cf_to_net_income),
        debt_to_equity: row.debt_to_equity == null ? null : parseFloat(row.debt_to_equity),
        current_ratio: row.current_ratio == null ? null : parseFloat(row.current_ratio),
        quick_ratio: row.quick_ratio == null ? null : parseFloat(row.quick_ratio),
        earnings_surprise_avg: row.earnings_surprise_avg == null ? null : parseFloat(row.earnings_surprise_avg),
        eps_growth_stability: row.eps_growth_stability == null ? null : parseFloat(row.eps_growth_stability),
        payout_ratio: row.payout_ratio == null ? null : parseFloat(row.payout_ratio)
      },
      // Add growth INPUT metrics for frontend display (12 professional growth inputs) - NO FALLBACKS
      growth_inputs: {
        revenue_growth_3y_cagr: row.revenue_growth_3y_cagr == null ? null : parseFloat(row.revenue_growth_3y_cagr),
        eps_growth_3y_cagr: row.eps_growth_3y_cagr == null ? null : parseFloat(row.eps_growth_3y_cagr),
        operating_income_growth_yoy: row.operating_income_growth_yoy == null ? null : parseFloat(row.operating_income_growth_yoy),
        roe_trend: row.roe_trend == null ? null : parseFloat(row.roe_trend),
        sustainable_growth_rate: row.sustainable_growth_rate == null ? null : parseFloat(row.sustainable_growth_rate),
        fcf_growth_yoy: row.fcf_growth_yoy == null ? null : parseFloat(row.fcf_growth_yoy),
        net_income_growth_yoy: row.net_income_growth_yoy == null ? null : parseFloat(row.net_income_growth_yoy),
        gross_margin_trend: row.gross_margin_trend == null ? null : parseFloat(row.gross_margin_trend),
        operating_margin_trend: row.operating_margin_trend == null ? null : parseFloat(row.operating_margin_trend),
        net_margin_trend: row.net_margin_trend == null ? null : parseFloat(row.net_margin_trend),
        quarterly_growth_momentum: row.quarterly_growth_momentum == null ? null : parseFloat(row.quarterly_growth_momentum),
        asset_growth_yoy: row.asset_growth_yoy == null ? null : parseFloat(row.asset_growth_yoy)
      },
      // Add raw momentum INPUT metrics for professional momentum display (dual momentum) - NO FALLBACKS
      momentum_inputs: {
        // Relative Momentum (vs other stocks)
        momentum_12m_1: row.momentum_12m_1 == null ? null : parseFloat(row.momentum_12m_1),
        momentum_6m: row.momentum_6m == null ? null : parseFloat(row.momentum_6m),
        momentum_3m: row.momentum_3m == null ? null : parseFloat(row.momentum_3m),
        risk_adjusted_momentum: row.risk_adjusted_momentum == null ? null : parseFloat(row.risk_adjusted_momentum),
        // Absolute Momentum (vs itself)
        price_vs_sma_50: row.price_vs_sma_50 == null ? null : parseFloat(row.price_vs_sma_50),
        price_vs_sma_200: row.price_vs_sma_200 == null ? null : parseFloat(row.price_vs_sma_200),
        price_vs_52w_high: row.price_vs_52w_high == null ? null : parseFloat(row.price_vs_52w_high),
        // Supporting data
        high_52w: row.high_52w == null ? null : parseFloat(row.high_52w),
        sma_50: row.sma_50 == null ? null : parseFloat(row.sma_50),
        sma_200: row.sma_200 == null ? null : parseFloat(row.sma_200),
        volatility_12m: row.volatility_12m == null ? null : parseFloat(row.volatility_12m),
        // Fallback for legacy display
        fallbacks: {
          momentum_medium_term: row.momentum_medium_term == null ? null : parseFloat(row.momentum_medium_term)?.toFixed(2),
          roc_252d: row.roc_252d == null ? null : parseFloat(row.roc_252d)?.toFixed(2),
          momentum_score: row.momentum_score == null ? null : parseFloat(row.momentum_score)?.toFixed(2)
        }
      },
      // Add raw risk INPUT metrics for Risk Factor Analysis display - NO FALLBACKS
      risk_inputs: {
        volatility_12m_pct: row.volatility_12m_pct == null ? null : parseFloat(row.volatility_12m_pct),
        volatility_risk_component: row.volatility_risk_component == null ? null : parseFloat(row.volatility_risk_component),
        max_drawdown_52w_pct: row.max_drawdown_52w_pct == null ? null : parseFloat(row.max_drawdown_52w_pct),
        beta: row.beta == null ? null : parseFloat(row.beta)
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
        -- Sector benchmarks (only columns that exist in sector_benchmarks table)
        sb.pe_ratio as sector_pe,
        sb.price_to_book as sector_pb,
        sb.ev_to_ebitda as sector_ev_ebitda,
        sb.debt_to_equity as sector_debt_to_equity,
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
        compositeScore: row.composite_score == null ? null : parseFloat(row.composite_score),
        currentPrice: row.current_price == null ? null : parseFloat(row.current_price),
        priceChange1d: row.price_change_1d == null ? null : parseFloat(row.price_change_1d),
        volume: row.volume_avg_30d == null ? null : parseInt(row.volume_avg_30d),
        marketCap: row.market_cap == null ? null : parseInt(row.market_cap),
        peRatio: row.pe_ratio == null ? null : parseFloat(row.pe_ratio),
        lastUpdated: row.last_updated,
        scoreDate: row.score_date,
        // Nested factors object for tests
        factors: {
          momentum: {
            score: row.momentum_score == null ? null : parseFloat(row.momentum_score),
            components: {
              short_term: row.momentum_short_term == null ? null : parseFloat(row.momentum_short_term),
              medium_term: row.momentum_medium_term == null ? null : parseFloat(row.momentum_medium_term),
              longer_term: row.momentum_long_term == null ? null : parseFloat(row.momentum_long_term),
              relative_strength: row.momentum_relative_strength == null ? null : parseFloat(row.momentum_relative_strength),
              consistency: row.momentum_consistency == null ? null : parseFloat(row.momentum_consistency),
              rsi: row.rsi == null ? null : parseFloat(row.rsi),
              roc_10d: row.roc_10d == null ? null : parseFloat(row.roc_10d),
              roc_60d: row.roc_60d == null ? null : parseFloat(row.roc_60d),
              roc_120d: row.roc_120d == null ? null : parseFloat(row.roc_120d),
              mansfield_rs: row.mansfield_rs == null ? null : parseFloat(row.mansfield_rs)
            },
            inputs: {
              // Relative Momentum (vs other stocks)
              momentum_12m_1: row.momentum_12m_1 == null ? null : parseFloat(row.momentum_12m_1),
              momentum_6m: row.momentum_6m == null ? null : parseFloat(row.momentum_6m),
              momentum_3m: row.momentum_3m == null ? null : parseFloat(row.momentum_3m),
              risk_adjusted_momentum: row.risk_adjusted_momentum == null ? null : parseFloat(row.risk_adjusted_momentum),
              // Absolute Momentum (vs itself)
              price_vs_sma_50: row.price_vs_sma_50 == null ? null : parseFloat(row.price_vs_sma_50),
              price_vs_sma_200: row.price_vs_sma_200 == null ? null : parseFloat(row.price_vs_sma_200),
              price_vs_52w_high: row.price_vs_52w_high == null ? null : parseFloat(row.price_vs_52w_high),
              // Supporting data
              high_52w: row.high_52w == null ? null : parseFloat(row.high_52w),
              sma_50: row.sma_50 == null ? null : parseFloat(row.sma_50),
              sma_200: row.sma_200 == null ? null : parseFloat(row.sma_200),
              volatility_12m: row.volatility_12m == null ? null : parseFloat(row.volatility_12m),
              // Fallback for legacy display
              fallbacks: {
                momentum_medium_term: row.momentum_medium_term == null ? null : parseFloat(row.momentum_medium_term)?.toFixed(2),
                roc_252d: row.roc_252d == null ? null : parseFloat(row.roc_252d)?.toFixed(2),
                momentum_score: row.momentum_score == null ? null : parseFloat(row.momentum_score)?.toFixed(2)
              }
            }
          },
          value: {
            score: row.value_score == null ? null : parseFloat(row.value_score),
            inputs: {
              stock_pe: row.stock_pe == null ? null : parseFloat(row.stock_pe),
              stock_pb: row.stock_pb == null ? null : parseFloat(row.stock_pb),
              stock_ps: row.stock_ps == null ? null : parseFloat(row.stock_ps),
              stock_ev_ebitda: row.stock_ev_ebitda == null ? null : parseFloat(row.stock_ev_ebitda),
              stock_fcf_yield: row.stock_fcf_yield == null ? null : parseFloat(row.stock_fcf_yield),
              stock_dividend_yield: row.stock_dividend_yield == null ? null : parseFloat(row.stock_dividend_yield),
              sector_pe: row.sector_pe == null ? null : parseFloat(row.sector_pe),
              sector_pb: row.sector_pb == null ? null : parseFloat(row.sector_pb),
              sector_ps: row.sector_ps == null ? null : parseFloat(row.sector_ps),
              sector_ev_ebitda: row.sector_ev_ebitda == null ? null : parseFloat(row.sector_ev_ebitda),
              sector_fcf_yield: row.sector_fcf_yield == null ? null : parseFloat(row.sector_fcf_yield),
              sector_dividend_yield: row.sector_dividend_yield == null ? null : parseFloat(row.sector_dividend_yield),
              market_pe: row.market_pe == null ? null : parseFloat(row.market_pe),
              market_pb: row.market_pb == null ? null : parseFloat(row.market_pb),
              market_ps: row.market_ps == null ? null : parseFloat(row.market_ps),
              market_fcf_yield: row.market_fcf_yield == null ? null : parseFloat(row.market_fcf_yield),
              market_dividend_yield: row.market_dividend_yield == null ? null : parseFloat(row.market_dividend_yield),
              earnings_growth_pct: row.earnings_growth_pct == null ? null : parseFloat(row.earnings_growth_pct),
              peg_ratio: (row.stock_pe && row.earnings_growth_pct && row.earnings_growth_pct > 0)
                ? parseFloat((row.stock_pe / row.earnings_growth_pct).toFixed(2))
                : null
            }
          },
          quality: {
            score: row.quality_score == null ? null : parseFloat(row.quality_score),
            inputs: {
              return_on_equity_pct: row.return_on_equity_pct == null ? null : parseFloat(row.return_on_equity_pct),
              return_on_assets_pct: row.return_on_assets_pct == null ? null : parseFloat(row.return_on_assets_pct),
              gross_margin_pct: row.gross_margin_pct == null ? null : parseFloat(row.gross_margin_pct),
              operating_margin_pct: row.operating_margin_pct == null ? null : parseFloat(row.operating_margin_pct),
              profit_margin_pct: row.profit_margin_pct == null ? null : parseFloat(row.profit_margin_pct),
              fcf_to_net_income: row.fcf_to_net_income == null ? null : parseFloat(row.fcf_to_net_income),
              operating_cf_to_net_income: row.operating_cf_to_net_income == null ? null : parseFloat(row.operating_cf_to_net_income),
              debt_to_equity: row.debt_to_equity == null ? null : parseFloat(row.debt_to_equity),
              current_ratio: row.current_ratio == null ? null : parseFloat(row.current_ratio),
              quick_ratio: row.quick_ratio == null ? null : parseFloat(row.quick_ratio),
              earnings_surprise_avg: row.earnings_surprise_avg == null ? null : parseFloat(row.earnings_surprise_avg),
              eps_growth_stability: row.eps_growth_stability == null ? null : parseFloat(row.eps_growth_stability),
              payout_ratio: row.payout_ratio == null ? null : parseFloat(row.payout_ratio)
            }
          },
          growth: {
            score: row.growth_score == null ? null : parseFloat(row.growth_score),
            inputs: {
              revenue_growth_3y_cagr: row.revenue_growth_3y_cagr == null ? null : parseFloat(row.revenue_growth_3y_cagr),
              eps_growth_3y_cagr: row.eps_growth_3y_cagr == null ? null : parseFloat(row.eps_growth_3y_cagr),
              operating_income_growth_yoy: row.operating_income_growth_yoy == null ? null : parseFloat(row.operating_income_growth_yoy),
              roe_trend: row.roe_trend == null ? null : parseFloat(row.roe_trend),
              sustainable_growth_rate: row.sustainable_growth_rate == null ? null : parseFloat(row.sustainable_growth_rate),
              fcf_growth_yoy: row.fcf_growth_yoy == null ? null : parseFloat(row.fcf_growth_yoy),
              net_income_growth_yoy: row.net_income_growth_yoy == null ? null : parseFloat(row.net_income_growth_yoy),
              gross_margin_trend: row.gross_margin_trend == null ? null : parseFloat(row.gross_margin_trend),
              operating_margin_trend: row.operating_margin_trend == null ? null : parseFloat(row.operating_margin_trend),
              net_margin_trend: row.net_margin_trend == null ? null : parseFloat(row.net_margin_trend),
              quarterly_growth_momentum: row.quarterly_growth_momentum == null ? null : parseFloat(row.quarterly_growth_momentum),
              asset_growth_yoy: row.asset_growth_yoy == null ? null : parseFloat(row.asset_growth_yoy)
            }
          },
          positioning: {
            score: row.positioning_score == null ? null : parseFloat(row.positioning_score),
            components: {
              institutional_ownership: row.institutional_ownership == null ? null : parseFloat(row.institutional_ownership),
              insider_ownership: row.insider_ownership == null ? null : parseFloat(row.insider_ownership),
              short_percent_of_float: row.short_percent_of_float == null ? null : parseFloat(row.short_percent_of_float),
              short_ratio: row.short_ratio == null ? null : parseFloat(row.short_ratio),
              days_to_cover: row.short_ratio == null ? null : parseFloat(row.short_ratio),
              institution_count: row.institution_count == null ? null : parseInt(row.institution_count),
              acc_dist_rating: row.acc_dist_rating == null ? null : parseFloat(row.acc_dist_rating)
            }
          },
          sentiment: {
            score: row.sentiment_score == null ? null : parseFloat(row.sentiment_score),
            components: {}
          },
          consistency: {
            score: row.consistency_score == null ? null : parseFloat(row.consistency_score),
            inputs: {
              volatility_12m_pct: row.volatility_12m_pct == null ? null : parseFloat(row.volatility_12m_pct),
              downside_volatility_pct: row.volatility_risk_component == null ? null : parseFloat(row.volatility_risk_component),
              max_drawdown_52w_pct: row.max_drawdown_52w_pct == null ? null : parseFloat(row.max_drawdown_52w_pct),
              beta: row.beta == null ? null : parseFloat(row.beta)
            }
          }
        },
        // Nested performance object for tests
        performance: {
          priceChange1d: row.price_change_1d == null ? null : parseFloat(row.price_change_1d),
          priceChange5d: row.price_change_5d == null ? null : parseFloat(row.price_change_5d),
          priceChange30d: row.price_change_30d == null ? null : parseFloat(row.price_change_30d),
          volatility30d: row.volatility_30d == null ? null : parseFloat(row.volatility_30d)
        },
        // Keep snake_case versions for backward compatibility with frontend
        company_name: row.company_name,
        composite_score: row.composite_score == null ? null : parseFloat(row.composite_score),
        momentum_score: row.momentum_score == null ? null : parseFloat(row.momentum_score),
        value_score: row.value_score == null ? null : parseFloat(row.value_score),
        quality_score: row.quality_score == null ? null : parseFloat(row.quality_score),
        growth_score: row.growth_score == null ? null : parseFloat(row.growth_score),
        positioning_score: row.positioning_score == null ? null : parseFloat(row.positioning_score),
        sentiment_score: row.sentiment_score == null ? null : parseFloat(row.sentiment_score),
        consistency_score: row.consistency_score == null ? null : parseFloat(row.consistency_score),
        current_price: row.current_price == null ? null : parseFloat(row.current_price),
        price_change_1d: row.price_change_1d == null ? null : parseFloat(row.price_change_1d),
        price_change_5d: row.price_change_5d == null ? null : parseFloat(row.price_change_5d),
        price_change_30d: row.price_change_30d == null ? null : parseFloat(row.price_change_30d),
        volatility_30d: row.volatility_30d == null ? null : parseFloat(row.volatility_30d),
        market_cap: row.market_cap == null ? null : parseInt(row.market_cap),
        volume_avg_30d: row.volume_avg_30d == null ? null : parseInt(row.volume_avg_30d),
        pe_ratio: row.pe_ratio == null ? null : parseFloat(row.pe_ratio),
        rsi: row.rsi == null ? null : parseFloat(row.rsi),
        sma_20: row.sma_20 == null ? null : parseFloat(row.sma_20),
        sma_50: row.sma_50 == null ? null : parseFloat(row.sma_50),
        macd: row.macd == null ? null : parseFloat(row.macd),
        last_updated: row.last_updated,
        score_date: row.score_date,
        // Consistency inputs for frontend display (Consistency Factor Analysis)
        consistency_inputs: {
          volatility_12m_pct: row.volatility_12m_pct == null ? null : parseFloat(row.volatility_12m_pct),
          volatility_risk_component: row.volatility_risk_component == null ? null : parseFloat(row.volatility_risk_component),
          max_drawdown_52w_pct: row.max_drawdown_52w_pct == null ? null : parseFloat(row.max_drawdown_52w_pct),
          beta: row.beta == null ? null : parseFloat(row.beta)
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
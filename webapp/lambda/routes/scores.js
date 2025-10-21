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

    // Query ONLY stock_scores table - simple and fast
    // All metrics are already calculated and stored in stock_scores
    let stocksQuery = `
      SELECT
        symbol,
        NULL::TEXT as company_name,
        NULL::TEXT as sector,
        composite_score,
        momentum_score,
        value_score,
        quality_score,
        growth_score,
        positioning_score,
        sentiment_score,
        stability_score,
        rsi,
        macd,
        sma_20,
        sma_50,
        current_price,
        price_change_1d,
        price_change_5d,
        price_change_30d,
        volatility_30d,
        market_cap,
        pe_ratio,
        volume_avg_30d,
        score_date,
        last_updated,
        acc_dist_rating,
        -- Momentum components (5-component breakdown)
        momentum_short_term,
        momentum_medium_term,
        momentum_long_term,
        momentum_relative_strength,
        momentum_consistency,
        roc_10d,
        roc_20d,
        roc_60d,
        roc_120d,
        mansfield_rs,
        -- Raw valuation inputs (stored in stock_scores)
        pe_ratio as stock_pe,
        pb_ratio as stock_pb,
        ps_ratio as stock_ps,
        ev_ebitda as stock_ev_ebitda,
        fcf_yield as stock_fcf_yield,
        dividend_yield as stock_dividend_yield,
        earnings_growth_pct,
        -- Sector benchmarks - defaults to NULL (requires separate lookup if needed)
        NULL::NUMERIC as sector_pe,
        NULL::NUMERIC as sector_pb,
        NULL::NUMERIC as sector_ev_ebitda,
        NULL::NUMERIC as sector_debt_to_equity,
        -- Market benchmarks - defaults to NULL (pre-calculate if needed)
        NULL::NUMERIC as market_pe,
        NULL::NUMERIC as market_pb,
        NULL::NUMERIC as market_ps,
        NULL::NUMERIC as market_fcf_yield,
        NULL::NUMERIC as market_dividend_yield,
        -- Positioning metrics
        institutional_ownership,
        insider_ownership,
        short_percent_of_float,
        short_ratio,
        institution_count,
        -- Quality INPUT metrics
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
        payout_ratio,
        -- Growth INPUT metrics
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
        asset_growth_yoy,
        -- Raw momentum INPUT metrics
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
        volatility_12m,
        -- Risk INPUT metrics
        volatility_12m_pct,
        volatility_risk_component,
        max_drawdown_52w_pct,
        beta
      FROM stock_scores
    `;

    const queryParams = [];
    let paramIndex = 1;

    // Add search filter if provided
    if (search) {
      stocksQuery += ` WHERE ss.symbol ILIKE $${paramIndex}`;
      queryParams.push(`%${search.toUpperCase()}%`);
      paramIndex++;
    }

    stocksQuery += ` ORDER BY ss.composite_score DESC NULLS LAST`;
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
      stability_score: row.stability_score == null ? null : parseFloat(row.stability_score),
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
      },
      // RENAMED: stability_inputs for frontend display (Stability Factor Analysis)
      // Maps risk_metrics fields to expected frontend structure
      stability_inputs: {
        volatility_12m_pct: row.volatility_12m_pct == null ? null : parseFloat(row.volatility_12m_pct),
        downside_volatility_pct: row.volatility_risk_component == null ? null : parseFloat(row.volatility_risk_component),
        max_drawdown_52w_pct: row.max_drawdown_52w_pct == null ? null : parseFloat(row.max_drawdown_52w_pct),
        beta: row.beta == null ? null : parseFloat(row.beta),
        liquidity_risk: null  // TODO: Add liquidity risk calculation from quality_metrics
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
        symbol,
        NULL::TEXT as company_name,
        NULL::TEXT as sector,
        composite_score,
        momentum_score,
        value_score,
        quality_score,
        growth_score,
        positioning_score,
        sentiment_score,
        stability_score,
        rsi,
        macd,
        sma_20,
        sma_50,
        current_price,
        price_change_1d,
        price_change_5d,
        price_change_30d,
        volatility_30d,
        market_cap,
        pe_ratio,
        volume_avg_30d,
        score_date,
        last_updated,
        acc_dist_rating,
        momentum_short_term,
        momentum_medium_term,
        momentum_long_term,
        momentum_relative_strength,
        momentum_consistency,
        roc_10d,
        roc_20d,
        roc_60d,
        roc_120d,
        mansfield_rs,
        pe_ratio as stock_pe,
        pb_ratio as stock_pb,
        ps_ratio as stock_ps,
        ev_ebitda as stock_ev_ebitda,
        fcf_yield as stock_fcf_yield,
        dividend_yield as stock_dividend_yield,
        earnings_growth_pct,
        NULL::NUMERIC as sector_pe,
        NULL::NUMERIC as sector_pb,
        NULL::NUMERIC as sector_ev_ebitda,
        NULL::NUMERIC as sector_debt_to_equity,
        NULL::NUMERIC as market_pe,
        NULL::NUMERIC as market_pb,
        NULL::NUMERIC as market_ps,
        NULL::NUMERIC as market_fcf_yield,
        NULL::NUMERIC as market_dividend_yield,
        institutional_ownership,
        insider_ownership,
        short_percent_of_float,
        short_ratio,
        institution_count,
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
        payout_ratio,
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
        asset_growth_yoy,
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
        volatility_12m,
        volatility_12m_pct,
        volatility_risk_component,
        max_drawdown_52w_pct,
        beta
      FROM stock_scores
      WHERE symbol = $1
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
          stability: {
            score: row.stability_score == null ? null : parseFloat(row.stability_score),
            inputs: {
              volatility_12m_pct: row.volatility_12m_pct == null ? null : parseFloat(row.volatility_12m_pct),
              volatility_risk_component: row.volatility_risk_component == null ? null : parseFloat(row.volatility_risk_component),
              max_drawdown_52w_pct: row.max_drawdown_52w_pct == null ? null : parseFloat(row.max_drawdown_52w_pct),
              debt_to_equity: row.debt_to_equity == null ? null : parseFloat(row.debt_to_equity),
              current_ratio: row.current_ratio == null ? null : parseFloat(row.current_ratio),
              eps_growth_stability: row.eps_growth_stability == null ? null : parseFloat(row.eps_growth_stability)
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
        stability_score: row.stability_score == null ? null : parseFloat(row.stability_score),
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
        // Stability inputs for frontend display (Stability Factor Analysis)
        stability_inputs: {
          volatility_12m_pct: row.volatility_12m_pct == null ? null : parseFloat(row.volatility_12m_pct),
          downside_volatility_pct: row.volatility_risk_component == null ? null : parseFloat(row.volatility_risk_component),
          max_drawdown_52w_pct: row.max_drawdown_52w_pct == null ? null : parseFloat(row.max_drawdown_52w_pct),
          beta: row.beta == null ? null : parseFloat(row.beta),
          liquidity_risk: null  // TODO: Add liquidity risk calculation from quality_metrics
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
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
// NOTE: IMPORTANT - This route must be defined BEFORE /:symbol route
// so that /overview matches this handler instead of being treated as a symbol
router.get("/", async (req, res) => {
  try {
    if (process.env.NODE_ENV !== 'test') {
      console.log("📊 Stock Scores List endpoint called - using real stock_scores table");
    }

    const search = req.query.search || '';
    const limit = Math.min(parseInt(req.query.limit) || 50, 500); // Default 50, max 500
    const offset = Math.max(parseInt(req.query.offset) || 0, 0); // Default 0

    // Query stock_scores with LEFT JOINs to metric tables
    // Fetches scores and detailed metrics from actual metric tables
    // CRITICAL FIX: Filter time-series tables to use LATEST data for each symbol
    // (quality_metrics, growth_metrics, positioning_metrics, risk_metrics have multiple rows per symbol by date)
    let stocksQuery = `
      SELECT
        ss.symbol,
        cp.display_name as company_name,
        cp.sector,
        ss.composite_score,
        ss.momentum_score,
        ss.value_score,
        ss.quality_score,
        ss.growth_score,
        ss.positioning_score,
        ss.sentiment_score,
        ss.stability_score,
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
        -- Momentum components
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
        -- Valuation metrics from value_inputs JSONB column (populated by loadvaluemetrics.py)
        ss.pe_ratio as stock_pe,
        CAST(ss.value_inputs->>'stock_pb' AS NUMERIC) as stock_pb,
        CAST(ss.value_inputs->>'stock_ps' AS NUMERIC) as stock_ps,
        CAST(ss.value_inputs->>'stock_ev_ebitda' AS NUMERIC) as stock_ev_ebitda,
        CAST(ss.value_inputs->>'fcf_yield' AS NUMERIC) as stock_fcf_yield,
        CAST(ss.value_inputs->>'dividend_yield' AS NUMERIC) as stock_dividend_yield,
        gm.eps_growth_3y_cagr as earnings_growth_pct,
        -- Sector benchmarks from value_inputs (median values for stock's sector)
        CAST(ss.value_inputs->>'sector_pe' AS NUMERIC) as sector_pe,
        CAST(ss.value_inputs->>'sector_pb' AS NUMERIC) as sector_pb,
        CAST(ss.value_inputs->>'sector_ps' AS NUMERIC) as sector_ps,
        CAST(ss.value_inputs->>'sector_ev_ebitda' AS NUMERIC) as sector_ev_ebitda,
        CAST(ss.value_inputs->>'sector_fcf_yield' AS NUMERIC) as sector_fcf_yield,
        CAST(ss.value_inputs->>'sector_dividend_yield' AS NUMERIC) as sector_dividend_yield,
        NULL::NUMERIC as sector_debt_to_equity,
        -- Market benchmarks from value_inputs (median values across all stocks)
        CAST(ss.value_inputs->>'market_pe' AS NUMERIC) as market_pe,
        CAST(ss.value_inputs->>'market_pb' AS NUMERIC) as market_pb,
        CAST(ss.value_inputs->>'market_ps' AS NUMERIC) as market_ps,
        CAST(ss.value_inputs->>'market_fcf_yield' AS NUMERIC) as market_fcf_yield,
        CAST(ss.value_inputs->>'market_dividend_yield' AS NUMERIC) as market_dividend_yield,
        -- Positioning metrics (from latest date)
        pos.institutional_ownership_pct,
        pos.insider_ownership_pct,
        pos.short_interest_pct,
        pos.short_ratio,
        pos.institutional_holders_count,
        -- Quality metrics from quality_metrics table (from latest date)
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
        -- Growth metrics from growth_metrics table (from latest date)
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
        -- Momentum detailed metrics
        NULL::NUMERIC as momentum_12m_1,
        NULL::NUMERIC as momentum_6m,
        NULL::NUMERIC as momentum_3m,
        NULL::NUMERIC as risk_adjusted_momentum,
        NULL::NUMERIC as price_vs_sma_50,
        NULL::NUMERIC as price_vs_sma_200,
        NULL::NUMERIC as price_vs_52w_high,
        NULL::NUMERIC as high_52w,
        NULL::NUMERIC as volatility_12m,
        -- Risk metrics from risk_metrics table (from latest date)
        rm.volatility_12m_pct,
        NULL::NUMERIC as volatility_risk_component,
        NULL::NUMERIC as max_drawdown_52w_pct,
        rm.beta
      FROM stock_scores ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      -- CRITICAL: Time-series tables have multiple dates per symbol
      -- Use LATERAL joins to get ONLY the latest date for each symbol
      -- This ensures frontend displays exactly one row per symbol
      LEFT JOIN LATERAL (
        SELECT * FROM quality_metrics
        WHERE symbol = ss.symbol
        ORDER BY date DESC LIMIT 1
      ) qm ON true
      LEFT JOIN LATERAL (
        SELECT * FROM growth_metrics
        WHERE symbol = ss.symbol
        ORDER BY date DESC LIMIT 1
      ) gm ON true
      LEFT JOIN LATERAL (
        SELECT * FROM positioning_metrics
        WHERE symbol = ss.symbol
        ORDER BY date DESC LIMIT 1
      ) pos ON true
      LEFT JOIN LATERAL (
        SELECT * FROM risk_metrics
        WHERE symbol = ss.symbol
        ORDER BY date DESC LIMIT 1
      ) rm ON true
    `;

    const queryParams = [];
    let paramIndex = 1;

    // Add search filter if provided
    if (search) {
      stocksQuery += ` WHERE ss.symbol ILIKE $${paramIndex}`;
      queryParams.push(`%${search.toUpperCase()}%`);
      paramIndex++;
    }

    // Sort by composite score (DISTINCT ON is no longer needed since LATERAL joins guarantee one row per symbol)
    stocksQuery += ` ORDER BY ss.composite_score DESC NULLS LAST, ss.symbol`;

    // Get total count for pagination (with same search filter)
    let countQuery = `SELECT COUNT(*) as total FROM stock_scores ss`;
    const countParams = [];
    let countParamIndex = 1;

    if (search) {
      countQuery += ` WHERE ss.symbol ILIKE $${countParamIndex}`;
      countParams.push(`%${search.toUpperCase()}%`);
    }

    const countResult = await query(countQuery, countParams);
    const totalStocks = parseInt(countResult.rows[0]?.total || 0);

    // Add LIMIT and OFFSET for pagination
    stocksQuery += ` LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`;
    queryParams.push(limit, offset);

    let stocksResult;
    try {
      stocksResult = await query(stocksQuery, queryParams);
    } catch (dbError) {
      console.error("Stocks query error:", dbError);
      return res.status(500).json({
        success: false,
        error: "Failed to fetch stock scores",
        details: dbError.message,
        timestamp: new Date().toISOString(),
      });
    }

    if (!stocksResult || !stocksResult.rows) {
      console.error("Stocks query returned null or empty rows:", {
        result: stocksResult,
        query: stocksQuery.substring(0, 200) + "...",
      });
      return res.status(500).json({
        success: false,
        error: "Database query returned null result",
        details: "No data available from stocks table",
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
        institutional_ownership: row.institutional_ownership_pct == null ? null : parseFloat(row.institutional_ownership_pct),
        insider_ownership: row.insider_ownership_pct == null ? null : parseFloat(row.insider_ownership_pct),
        short_percent_of_float: row.short_interest_pct == null ? null : parseFloat(row.short_interest_pct),
        short_ratio: row.short_ratio == null ? null : parseFloat(row.short_ratio),
        days_to_cover: row.short_ratio == null ? null : parseFloat(row.short_ratio), // days_to_cover is same as short_ratio
        institution_count: row.institutional_holders_count == null ? null : parseInt(row.institutional_holders_count),
        acc_dist_rating: row.acc_dist_rating == null ? null : parseFloat(row.acc_dist_rating)
      },
      // Add raw valuation inputs for frontend display (extracted from value_inputs JSONB column)
      value_inputs: {
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

    // Return paginated results with pagination metadata
    const currentPage = Math.floor(offset / limit) + 1;
    const totalPages = Math.ceil(totalStocks / limit);
    const pageStocks = stocksList.length;

    res.json({
      success: true,
      data: {
        stocks: stocksList,
        viewType: "list"
      },
      summary: {
        totalStocks: totalStocks, // Total across ALL pages (not just this page)
        pageStocks: pageStocks, // Stocks on current page
        averageScore: stocksList.length > 0
          ? Math.round(stocksList.reduce((sum, s) => sum + (s.composite_score || 0), 0) / stocksList.length * 100) / 100
          : 0,
        topScore: stocksList.length > 0 ? stocksList[0].composite_score : 0,
        scoreRange: stocksList.length > 0 ?
          `${stocksList[stocksList.length - 1].composite_score} - ${stocksList[0].composite_score}` : "0 - 0"
      },
      pagination: {
        limit,
        offset,
        currentPage,
        pageSize: limit,
        totalPages,
        totalRecords: totalStocks,
        hasNextPage: offset + limit < totalStocks,
        hasPrevPage: offset > 0,
        pageStart: offset + 1,
        pageEnd: Math.min(offset + limit, totalStocks)
      },
      metadata: {
        dataSource: "stock_scores_real_table",
        searchTerm: search || null,
        lastUpdated: stocksList.length > 0 ? stocksList[0].lastUpdated : null,
        factorAnalysis: "seven_factor_scoring_system",
        paginationEnabled: true
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
        NULL::TEXT as company_name,
        NULL::TEXT as sector,
        ss.composite_score,
        ss.momentum_score,
        ss.value_score,
        ss.quality_score,
        ss.growth_score,
        ss.positioning_score,
        ss.sentiment_score,
        ss.stability_score,
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
        ss.pe_ratio as stock_pe,
        (ss.value_inputs->>'stock_pb')::NUMERIC as stock_pb,
        (ss.value_inputs->>'stock_ps')::NUMERIC as stock_ps,
        (ss.value_inputs->>'stock_ev_ebitda')::NUMERIC as stock_ev_ebitda,
        (ss.value_inputs->>'fcf_yield')::NUMERIC as stock_fcf_yield,
        (ss.value_inputs->>'dividend_yield')::NUMERIC as stock_dividend_yield,
        (ss.value_inputs->>'earnings_growth_pct')::NUMERIC as earnings_growth_pct,
        (ss.value_inputs->>'sector_pe')::NUMERIC as sector_pe,
        (ss.value_inputs->>'sector_pb')::NUMERIC as sector_pb,
        (ss.value_inputs->>'sector_ps')::NUMERIC as sector_ps,
        (ss.value_inputs->>'sector_ev_ebitda')::NUMERIC as sector_ev_ebitda,
        (ss.value_inputs->>'sector_fcf_yield')::NUMERIC as sector_fcf_yield,
        (ss.value_inputs->>'sector_dividend_yield')::NUMERIC as sector_dividend_yield,
        NULL::NUMERIC as sector_debt_to_equity,
        (ss.value_inputs->>'market_pe')::NUMERIC as market_pe,
        (ss.value_inputs->>'market_pb')::NUMERIC as market_pb,
        (ss.value_inputs->>'market_ps')::NUMERIC as market_ps,
        (ss.value_inputs->>'market_fcf_yield')::NUMERIC as market_fcf_yield,
        (ss.value_inputs->>'market_dividend_yield')::NUMERIC as market_dividend_yield,
        NULL::NUMERIC as institutional_ownership,
        NULL::NUMERIC as insider_ownership,
        NULL::NUMERIC as short_percent_of_float,
        NULL::NUMERIC as short_ratio,
        NULL::INTEGER as institution_count,
        NULL::NUMERIC as return_on_equity_pct,
        NULL::NUMERIC as return_on_assets_pct,
        NULL::NUMERIC as gross_margin_pct,
        NULL::NUMERIC as operating_margin_pct,
        NULL::NUMERIC as profit_margin_pct,
        NULL::NUMERIC as fcf_to_net_income,
        NULL::NUMERIC as operating_cf_to_net_income,
        NULL::NUMERIC as debt_to_equity,
        NULL::NUMERIC as current_ratio,
        NULL::NUMERIC as quick_ratio,
        NULL::NUMERIC as earnings_surprise_avg,
        NULL::NUMERIC as eps_growth_stability,
        NULL::NUMERIC as payout_ratio,
        NULL::NUMERIC as revenue_growth_3y_cagr,
        NULL::NUMERIC as eps_growth_3y_cagr,
        NULL::NUMERIC as operating_income_growth_yoy,
        NULL::NUMERIC as roe_trend,
        NULL::NUMERIC as sustainable_growth_rate,
        NULL::NUMERIC as fcf_growth_yoy,
        NULL::NUMERIC as net_income_growth_yoy,
        NULL::NUMERIC as gross_margin_trend,
        NULL::NUMERIC as operating_margin_trend,
        NULL::NUMERIC as net_margin_trend,
        NULL::NUMERIC as quarterly_growth_momentum,
        NULL::NUMERIC as asset_growth_yoy,
        NULL::NUMERIC as momentum_12m_1,
        NULL::NUMERIC as momentum_6m,
        NULL::NUMERIC as momentum_3m,
        NULL::NUMERIC as risk_adjusted_momentum,
        NULL::NUMERIC as price_vs_sma_50,
        NULL::NUMERIC as price_vs_sma_200,
        NULL::NUMERIC as price_vs_52w_high,
        NULL::NUMERIC as high_52w,
        ss.sma_50,
        NULL::NUMERIC as sma_200,
        NULL::NUMERIC as volatility_12m,
        NULL::NUMERIC as volatility_12m_pct,
        NULL::NUMERIC as volatility_risk_component,
        NULL::NUMERIC as max_drawdown_52w_pct,
        NULL::NUMERIC as beta
      FROM stock_scores ss
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
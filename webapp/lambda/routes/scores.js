const express = require("express");

const { query } = require("../utils/database");
const {
  sendSuccess,
  sendError,
  sendPaginated,
} = require("../utils/apiResponse");
const { validateQueryResult } = require("../utils/responseValidation");
const {
  requireNumericField,
  isDataError,
} = require("../utils/strictValidation");
const router = express.Router();

// GET / - Get stock scores with optional filters
router.get("/", async (req, res) => {
  try {
    const {
      limit = 50,
      page = 1,
      symbol,
      sort = "composite_score",
      sort_order = "DESC",
    } = req.query;
    // Explicit NaN checks for pagination parameters
    const limitVal = parseInt(limit, 10);
    const pageVal = parseInt(page, 10);
    const limitNum = Math.min(!isNaN(limitVal) ? limitVal : 50, 1000);
    const pageNum = Math.max(!isNaN(pageVal) ? pageVal : 1, 1);
    const offset = (pageNum - 1) * limitNum;

    // Build WHERE clause - exclude ETFs using stock_symbols table
    let whereClause = "WHERE (sy.etf IS NULL OR sy.etf != 'Y')";
    const params = [];

    if (symbol) {
      whereClause += " AND ss.symbol = $1";
      params.push(symbol.toUpperCase());
    }

    // Validate sort field
    const validSortFields = [
      "composite_score",
      "momentum_score",
      "value_score",
      "quality_score",
      "growth_score",
      "stability_score",
      "symbol",
    ];
    const sortField = validSortFields.includes(sort) ? sort : "composite_score";
    const sortDir = ["ASC", "DESC"].includes(
      (sort_order || "DESC").toUpperCase()
    )
      ? sort_order.toUpperCase()
      : "DESC";

    // Combined query to get both count and data in a single pass
    // This reduces database round-trips and improves Lambda performance
    const paramIndex = params.length + 1;
    const resultObj = await query(
      `
      SELECT
        ss.symbol,
        ss.composite_score,
        ss.momentum_score,
        ss.value_score,
        ss.quality_score,
        ss.growth_score,
        ss.stability_score,
        COUNT(*) OVER() as total_count
      FROM stock_scores ss
      LEFT JOIN stock_symbols sy ON sy.symbol = ss.symbol
      ${whereClause}
      ORDER BY ss.${sortField} ${sortDir}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `,
      [...params, limitNum, offset]
    );
    validateQueryResult(resultObj, { requireRows: false });

    const scores = resultObj?.rows ?? [];
    const total = scores.length > 0 ? parseInt(scores[0].total_count) : 0;
    const totalPages = Math.ceil(total / limitNum);

    return sendPaginated(
      res,
      scores.map((row) => ({
        symbol: row.symbol,
        composite_score: row.composite_score,
        momentum_score: row.momentum_score,
        value_score: row.value_score,
        quality_score: row.quality_score,
        growth_score: row.growth_score,
        stability_score: row.stability_score,
      })),
      {
        page: pageNum,
        limit: limitNum,
        offset,
        total,
        totalPages,
        hasNext: pageNum < totalPages,
        hasPrev: pageNum > 1,
      }
    );
  } catch (error) {
    console.error("Error fetching scores:", error.message);
    return sendError(
      res,
      `Failed to fetch scores: ${error.message.substring(0, 100)}`,
      500
    );
  }
});

// GET /stockscores - Returns composite stock scores with multi-factor rankings
router.get("/stockscores", async (req, res) => {
  try {
    const {
      limit = 50,
      page = 1,
      offset,
      symbol,
      sortBy = "composite_score",
      sortOrder = "DESC",
    } = req.query;

    const parsedLimit = parseInt(limit);
    const limitNum = Math.min(!isNaN(parsedLimit) ? parsedLimit : 50, 5000);
    const parsedOffset = parseInt(offset);
    const parsedPage = parseInt(page);
    const pageNum = offset
      ? Math.max((!isNaN(parsedOffset) ? parsedOffset : 0) / limitNum + 1, 1)
      : Math.max(!isNaN(parsedPage) ? parsedPage : 1, 1);
    const offsetNum = offset
      ? Math.max(!isNaN(parsedOffset) ? parsedOffset : 0, 0)
      : (pageNum - 1) * limitNum;

    // Build WHERE clause - only show stocks with good data coverage, exclude ETFs
    let whereClause =
      "WHERE sc.composite_score > 0 AND (ss.etf IS NULL OR ss.etf != 'Y')";
    const params = [];

    if (symbol) {
      whereClause += " AND sc.symbol = $" + (params.length + 1);
      params.push(symbol.toUpperCase());
    }

    // Validate sort field
    const validSortFields = [
      "composite_score",
      "momentum_score",
      "quality_score",
      "value_score",
      "growth_score",
      "positioning_score",
      "stability_score",
      "symbol",
    ];
    const sortField = validSortFields.includes(sortBy)
      ? sortBy
      : "composite_score";
    const sortDir = ["ASC", "DESC"].includes(
      (sortOrder || "DESC").toUpperCase()
    )
      ? sortOrder.toUpperCase()
      : "DESC";

    // Get total count
    const countResult = await query(
      `SELECT COUNT(*) as total FROM stock_scores sc LEFT JOIN stock_symbols ss ON ss.symbol = sc.symbol ${whereClause}`,
      params
    );
    validateQueryResult(countResult, { requireRows: false });
    // Count fallback affects pagination - must be actual count or error
    const totalValidation = requireNumericField(
      countResult?.rows[0]?.total,
      "total_count",
      { min: 0, allowZero: true }
    );
    const total = isDataError(totalValidation) ? 0 : totalValidation;

    // Get paginated results - Optimized: removed slow price_daily join with window function
    const paramIndex = params.length + 1;
    const resultObj = await query(
      `
      SELECT
        sc.symbol,
        ss.security_name as company_name,
        cp.sector,
        cp.industry,
        sc.composite_score,
        sc.momentum_score,
        sc.quality_score,
        sc.value_score,
        sc.growth_score,
        sc.positioning_score,
        sc.stability_score,
        NULL::numeric as price,
        NULL::numeric as change_pct,
        km.market_cap,
        vm.pe_ratio,
        vm.pb_ratio,
        qm.roe,
        qm.debt_to_equity
      FROM stock_scores sc
      LEFT JOIN stock_symbols ss ON ss.symbol = sc.symbol
      LEFT JOIN company_profile cp ON cp.ticker = sc.symbol
      LEFT JOIN key_metrics km ON km.symbol = sc.symbol
      LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
      LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
      ${whereClause}
      ORDER BY sc.${sortField} ${sortDir}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `,
      [...params, limitNum, offsetNum]
    );
    validateQueryResult(resultObj, { requireRows: false });

    const scores = (resultObj?.rows ?? []).map((row) => {
      // Validate composite score - used for grading and sorting, cannot default to 0
      const compositeValidation = requireNumericField(
        row.composite_score,
        "composite_score",
        { min: 0, max: 100, allowZero: true }
      );

      // GOVERNANCE: missing/invalid composite_score must never present as a real
      // grade. Defaulting to "F" here would show a stock with no score data as
      // if it had been evaluated and failed the worst possible grade.
      let grade = null;

      if (!isDataError(compositeValidation)) {
        const compositeScore = compositeValidation;
        if (compositeScore >= 90) grade = "A+";
        else if (compositeScore >= 80) grade = "A";
        else if (compositeScore >= 70) grade = "B";
        else if (compositeScore >= 60) grade = "C";
        else if (compositeScore >= 50) grade = "D";
        else grade = "F";
      }

      // Validate all component scores - these drive investment decisions
      const momentumValidation = requireNumericField(
        row.momentum_score,
        "momentum_score"
      );
      const qualityValidation = requireNumericField(
        row.quality_score,
        "quality_score"
      );
      const valueValidation = requireNumericField(
        row.value_score,
        "value_score"
      );
      const growthValidation = requireNumericField(
        row.growth_score,
        "growth_score"
      );
      const positioningValidation = requireNumericField(
        row.positioning_score,
        "positioning_score"
      );
      const stabilityValidation = requireNumericField(
        row.stability_score,
        "stability_score"
      );

      return {
        symbol: row.symbol,
        company_name: row.company_name,
        sector: row.sector,
        industry: row.industry,
        composite_score: !isDataError(compositeValidation)
          ? compositeValidation
          : null,
        momentum_score: !isDataError(momentumValidation)
          ? momentumValidation
          : null,
        quality_score: !isDataError(qualityValidation)
          ? qualityValidation
          : null,
        value_score: !isDataError(valueValidation) ? valueValidation : null,
        growth_score: !isDataError(growthValidation) ? growthValidation : null,
        positioning_score: !isDataError(positioningValidation)
          ? positioningValidation
          : null,
        stability_score: !isDataError(stabilityValidation)
          ? stabilityValidation
          : null,
        grade: grade,
        price: row.price,
        change_pct: row.change_pct,
        market_cap: row.market_cap,
        pe_ratio: row.pe_ratio,
        pb_ratio: row.pb_ratio,
        roe: row.roe,
        debt_to_equity: row.debt_to_equity,
      };
    });

    const totalPages = Math.ceil(total / limitNum);

    return sendPaginated(res, scores, {
      page: pageNum,
      limit: limitNum,
      total,
      totalPages,
      offset: offsetNum,
      hasNext: pageNum < totalPages,
      hasPrev: pageNum > 1,
    });
  } catch (error) {
    console.error("Error fetching stockscores:", error.message);
    return sendError(
      res,
      `Failed to fetch scores: ${error.message.substring(0, 100)}`,
      500
    );
  }
});

// GET /details/:symbol - Get stock with full factor inputs (for dashboard expansion)
router.get("/details/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const upperSymbol = symbol.toUpperCase();

    // Fetch all metric data for the symbol
    const [scoresRes, qualityRes, growthRes, momentumRes, valueRes, positioningRes, stabilityRes] = await Promise.all([
      query("SELECT * FROM stock_scores WHERE symbol = $1", [upperSymbol]),
      query("SELECT * FROM quality_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1", [upperSymbol]),
      query("SELECT * FROM growth_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1", [upperSymbol]),
      query("SELECT * FROM momentum_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1", [upperSymbol]),
      query("SELECT * FROM value_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1", [upperSymbol]),
      query("SELECT * FROM positioning_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1", [upperSymbol]),
      query("SELECT * FROM stability_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1", [upperSymbol]),
    ]);

    const score = scoresRes?.rows?.[0];
    if (!score) {
      return sendError(res, `No scores found for symbol ${symbol}`, 404);
    }

    // Build factor inputs with database column names mapped to frontend names
    const mapQualityInputs = (row) => ({
      return_on_equity_pct: row?.roe,
      return_on_assets_pct: row?.roa,
      return_on_invested_capital_pct: row?.roic_pct,
      gross_margin_pct: row?.gross_margin,
      operating_margin_pct: row?.operating_margin,
      profit_margin_pct: row?.net_margin,
      ebitda_margin_pct: row?.ebitda_margin,
      fcf_to_net_income: row?.fcf_to_net_income,
      operating_cf_to_net_income: row?.ocf_to_net_income,
      debt_to_equity: row?.debt_to_equity,
      current_ratio: row?.current_ratio,
      quick_ratio: row?.quick_ratio,
      earnings_surprise_avg: row?.earnings_surprise_avg,
      eps_growth_stability: row?.eps_growth_stability,
      earnings_beat_rate: row?.earnings_beat_rate,
      consecutive_positive_quarters: row?.consecutive_positive_quarters,
      estimate_revision_direction: row?.estimate_revision_direction,
      revision_activity_30d: row?.revision_activity_30d,
      estimate_momentum_60d: row?.estimate_momentum_60d,
      estimate_momentum_90d: row?.estimate_momentum_90d,
      revision_trend_score: row?.revision_trend_score,
      payout_ratio: row?.payout_ratio,
      free_cashflow: row?.free_cash_flow,
      operating_cashflow: row?.operating_cash_flow,
      total_debt: row?.total_debt,
      total_cash: row?.total_cash,
      cash_per_share: row?.cash_per_share,
      earnings_growth_pct: row?.earnings_growth_yoy,
      revenue_growth_pct: row?.revenue_growth_yoy,
      earnings_growth_4q_avg: row?.earnings_growth_4q_avg,
    });

    const mapGrowthInputs = (row) => ({
      revenue_growth_1y_pct: row?.revenue_growth_1y,
      eps_growth_1y_pct: row?.eps_growth_1y,
      revenue_growth_3y_cagr: row?.revenue_growth_3y,
      eps_growth_3y_cagr: row?.eps_growth_3y,
      revenue_growth_5y_cagr: row?.revenue_growth_5y,
      eps_growth_5y_cagr: row?.eps_growth_5y,
      net_income_growth_yoy: row?.net_income_growth_yoy,
      operating_income_growth_yoy: row?.operating_income_growth_yoy,
      gross_margin_trend: row?.gross_margin_trend,
      operating_margin_trend: row?.operating_margin_trend,
      net_margin_trend: row?.net_margin_trend,
      roe_trend: row?.roe_trend,
      sustainable_growth_rate: row?.sustainable_growth_rate,
      quarterly_growth_momentum: row?.quarterly_growth_momentum,
      fcf_growth_yoy: row?.fcf_growth_yoy,
      ocf_growth_yoy: row?.ocf_growth_yoy,
      asset_growth_yoy: row?.asset_growth_yoy,
    });

    const mapMomentumInputs = (row) => ({
      // Map momentum data to expected schema
      momentum_3m: row?.momentum_3m,
      momentum_6m: row?.momentum_6m,
      momentum_12_3: null, // Would be calculated from momentum_12m and momentum_3m
      price_vs_sma_50: row?.price_vs_sma_50,
      price_vs_sma_200: row?.price_vs_sma_200,
      price_vs_52w_high: null, // Not in momentum_metrics, would need price_daily
      rsi: row?.rsi_14,
      macd: row?.macd_line,
      current_price: null, // Not in momentum_metrics
    });

    const mapValueInputs = (row) => ({
      stock_pe: row?.pe_ratio,
      stock_forward_pe: row?.forward_pe,
      stock_pb: row?.pb_ratio,
      stock_ps: row?.ps_ratio,
      peg_ratio: row?.peg_ratio,
      stock_ev_ebitda: row?.ev_ebitda,
      stock_ev_revenue: row?.ev_revenue,
      fcf_yield: row?.fcf_yield,
      stock_dividend_yield: row?.dividend_yield,
    });

    const mapPositioningInputs = (row) => ({
      institutional_ownership_pct: row?.institutional_ownership_pct,
      top_10_institutions_pct: row?.top_10_institutions_pct,
      insider_ownership_pct: row?.insider_ownership_pct,
      short_interest_pct: row?.short_interest_pct,
      short_interest_trend: row?.short_interest_trend,
    });

    const mapStabilityInputs = (row) => ({
      volatility_30d: row?.volatility_30d,
      volatility_60d: row?.volatility_60d,
      volatility_252d: row?.volatility_252d,
      beta: row?.beta,
      dividend_yield: row?.dividend_yield,
      payout_ratio: row?.payout_ratio,
    });

    const result = {
      ...score,
      quality_inputs: mapQualityInputs(qualityRes?.rows?.[0]),
      growth_inputs: mapGrowthInputs(growthRes?.rows?.[0]),
      momentum_inputs: mapMomentumInputs(momentumRes?.rows?.[0]),
      value_inputs: mapValueInputs(valueRes?.rows?.[0]),
      positioning_inputs: mapPositioningInputs(positioningRes?.rows?.[0]),
      stability_inputs: mapStabilityInputs(stabilityRes?.rows?.[0]),
    };

    return sendSuccess(res, result);
  } catch (error) {
    console.error("Error fetching stock details:", error.message);
    return sendError(res, `Failed to fetch stock details: ${error.message.substring(0, 100)}`, 500);
  }
});

// GET /:symbol - Get score for specific symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;

    const result = await query(`SELECT * FROM stock_scores WHERE symbol = $1`, [
      symbol.toUpperCase(),
    ]);
    validateQueryResult(result, { requireRows: false });

    if (!result?.rows || result.rows.length === 0) {
      return sendError(res, `No scores found for symbol ${symbol}`, 404);
    }

    return sendSuccess(res, result.rows[0]);
  } catch (error) {
    console.error("Error fetching score:", error.message);
    return sendError(res, `Failed to fetch score: ${error.message}`, 500);
  }
});

module.exports = router;

const express = require("express");

const { query } = require("../utils/database");
const {
  sendSuccess,
  sendError,
  sendPaginated,
  sendPlaceholder,
} = require("../utils/apiResponse");
const logger = require("../utils/logger");
const {
  validateQueryResult,
  extractCount,
} = require("../utils/responseValidation");
const router = express.Router();

// Helper function to get industries ranked by composite score with performance metrics
async function fetchIndustries(req, res) {
  try {
    // Ensure limit and page parameters have explicit defaults
    const limit = req.query.limit !== undefined ? req.query.limit : 500;
    const page = req.query.page !== undefined ? req.query.page : 1;

    // Explicit NaN checks for pagination parameters
    const limitVal = parseInt(limit, 10);
    const pageVal = parseInt(page, 10);
    const limitNum = Math.min(
      Math.max(!isNaN(limitVal) ? limitVal : 500, 1),
      5000
    );
    const pageNum = Math.max(!isNaN(pageVal) ? pageVal : 1, 1);
    const offset = (pageNum - 1) * limitNum;

    // Validate offset is a valid number
    if (!Number.isInteger(offset) || offset < 0) {
      return sendError(res, "Invalid pagination offset calculated", 400);
    }

    // Debug logging
    console.log("[INDUSTRIES] Query parameters:", {
      limit: limitNum,
      offset: offset,
      offsetType: typeof offset,
      page: pageNum,
      limitType: typeof limitNum,
    });

    // Ensure parameters are explicit numbers before query
    if (!Number.isInteger(limitNum) || limitNum < 1) {
      return sendError(res, "Invalid limit parameter: must be positive integer", 400);
    }
    if (!Number.isInteger(offset) || offset < 0) {
      return sendError(res, "Invalid offset parameter: must be non-negative integer", 400);
    }

    // Parallelize data and count queries
    const params = [parseInt(limitNum, 10), parseInt(offset, 10)];
    console.log("[INDUSTRIES_QUERY] Executing with params:", params);

    // Mock data for local testing - remove this block in production
    if (process.env.NODE_ENV === 'development' || process.env.USE_MOCK_DATA === 'true') {
      console.log("[INDUSTRIES] Using mock data for local testing");
      const mockIndustries = [
        {
          industry: 'Software',
          sector: 'Information Technology',
          current_rank: 1,
          overall_rank: 1,
          rank_1w_ago: 2,
          rank_4w_ago: 3,
          stock_count: 150,
          composite_score: 82.5,
          momentum_score: 85.0,
          value_score: 75.0,
          quality_score: 88.0,
          growth_score: 90.0,
          stability_score: 78.0,
          perf_1d: 2.3,
          perf_5d: 5.1,
          perf_20d: 8.5,
          avg_trailing_pe: 22.5,
          avg_forward_pe: 18.2,
          pe_percentile: 72.0
        },
        {
          industry: 'Healthcare',
          sector: 'Healthcare',
          current_rank: 2,
          overall_rank: 2,
          rank_1w_ago: 1,
          rank_4w_ago: 2,
          stock_count: 95,
          composite_score: 78.2,
          momentum_score: 72.0,
          value_score: 82.0,
          quality_score: 85.0,
          growth_score: 75.0,
          stability_score: 84.0,
          perf_1d: 1.1,
          perf_5d: 2.8,
          perf_20d: 4.2,
          avg_trailing_pe: 18.5,
          avg_forward_pe: 16.8,
          pe_percentile: 45.0
        },
        {
          industry: 'Financials',
          sector: 'Financials',
          current_rank: 3,
          overall_rank: 3,
          rank_1w_ago: 3,
          rank_4w_ago: 4,
          stock_count: 72,
          composite_score: 71.5,
          momentum_score: 68.0,
          value_score: 78.0,
          quality_score: 72.0,
          growth_score: 68.0,
          stability_score: 75.0,
          perf_1d: 0.8,
          perf_5d: 1.5,
          perf_20d: 2.1,
          avg_trailing_pe: 12.3,
          avg_forward_pe: 11.5,
          pe_percentile: 28.0
        }
      ];

      const mockResult = {
        rows: mockIndustries,
        rowCount: mockIndustries.length
      };

      const sf = (v) => (v !== null && v !== undefined ? parseFloat(v) : null);

      const industries = mockIndustries.map((row, idx) => {
        const composite = sf(row.composite_score);
        const perf20d = sf(row.perf_20d);

        return {
          industry: row.industry,
          sector: row.sector,
          current_rank: row.current_rank,
          overall_rank: row.overall_rank,
          rank_12w_ago: row.rank_4w_ago,
          stock_count: row.stock_count,
          composite_score: composite,
          momentum_score: sf(row.momentum_score),
          value_score: sf(row.value_score),
          quality_score: sf(row.quality_score),
          growth_score: sf(row.growth_score),
          stability_score: sf(row.stability_score),
          performance_1d: sf(row.perf_1d),
          performance_5d: sf(row.perf_5d),
          performance_20d: perf20d,
          current_momentum: composite >= 75 ? 'Strong' : composite >= 60 ? 'Moderate' : 'Weak',
          current_trend: perf20d > 2 ? 'Uptrend' : perf20d < -2 ? 'Downtrend' : 'Sideways',
          pe: {
            trailing: sf(row.avg_trailing_pe),
            percentile: sf(row.pe_percentile)
          }
        };
      });

      const totalPages = Math.ceil(mockIndustries.length / limitNum);
      return sendPaginated(res, industries, {
        page: pageNum,
        limit: limitNum,
        offset: offset,
        total: mockIndustries.length,
        totalPages: totalPages,
        hasNext: pageNum < totalPages,
        hasPrev: pageNum > 1
      });
    }

    const [result, countResult] = await Promise.all([
      query(
        `
      WITH recent_prices AS (
        SELECT symbol, date, close,
          ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '60 days'
      ),
      symbol_perf AS (
        SELECT
          symbol,
          MAX(close) FILTER (WHERE rn = 1) as close_now,
          MAX(close) FILTER (WHERE rn = 2) as close_1d,
          MAX(close) FILTER (WHERE rn = 6) as close_5d,
          MAX(close) FILTER (WHERE rn = 21) as close_20d
        FROM recent_prices
        GROUP BY symbol
      ),
      industry_scores AS (
        SELECT
          cp.industry,
          cp.sector,
          COUNT(DISTINCT cp.ticker) as stock_count,
          AVG(ss.composite_score) as composite_score,
          AVG(ss.momentum_score) as momentum_score,
          AVG(ss.value_score) as value_score,
          AVG(ss.quality_score) as quality_score,
          AVG(ss.growth_score) as growth_score,
          AVG(ss.stability_score) as stability_score,
          AVG(CASE WHEN sp.close_1d > 0 THEN (sp.close_now - sp.close_1d) / sp.close_1d * 100 END) as perf_1d,
          AVG(CASE WHEN sp.close_5d > 0 THEN (sp.close_now - sp.close_5d) / sp.close_5d * 100 END) as perf_5d,
          AVG(CASE WHEN sp.close_20d > 0 THEN (sp.close_now - sp.close_20d) / sp.close_20d * 100 END) as perf_20d
        FROM company_profile cp
        LEFT JOIN symbol_perf sp ON cp.ticker = sp.symbol
        LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
        WHERE cp.industry IS NOT NULL AND TRIM(cp.industry) != ''
        GROUP BY cp.industry, cp.sector
      ),
      ranked AS (
        SELECT *,
          RANK() OVER (ORDER BY composite_score DESC NULLS LAST) as current_rank
        FROM industry_scores
      ),
      industry_pe AS (
        SELECT
          cp.industry,
          AVG(vm.pe_ratio) FILTER (WHERE vm.pe_ratio > 0 AND vm.pe_ratio < 200) AS avg_trailing_pe,
          AVG(vm.pb_ratio) FILTER (WHERE vm.pb_ratio > 0 AND vm.pb_ratio < 200) AS avg_forward_pe
        FROM value_metrics vm
        JOIN company_profile cp ON vm.symbol = cp.ticker
        WHERE cp.industry IS NOT NULL
        GROUP BY cp.industry
      ),
      industry_pe_ranked AS (
        SELECT *,
          PERCENT_RANK() OVER (ORDER BY avg_trailing_pe ASC NULLS LAST) * 100 AS pe_percentile
        FROM industry_pe
      )
      SELECT r.*, ipe.avg_trailing_pe, ipe.avg_forward_pe, ipe.pe_percentile, NULL::integer as rank_12w_ago
      FROM ranked r
      LEFT JOIN industry_pe_ranked ipe ON ipe.industry = r.industry
      ORDER BY r.current_rank, r.stock_count DESC
      LIMIT $1 OFFSET $2
    `,
        params
      ),
      query(
        `SELECT COUNT(DISTINCT industry) as count FROM company_profile WHERE industry IS NOT NULL`
      ),
    ]);
    validateQueryResult(result, { requireRows: false });
    const total = extractCount(countResult, "count");

    const sf = (v) => (v !== null && v !== undefined ? parseFloat(v) : null);

    const industries = (result?.rows ?? []).map((row, idx) => {
      const composite = sf(row.composite_score);
      const perf20d = sf(row.perf_20d);
      const momentumLabel =
        composite !== null && composite >= 60
          ? "Strong"
          : composite !== null && composite >= 45
            ? "Moderate"
            : "Weak";
      const trendLabel =
        perf20d !== null
          ? perf20d > 2
            ? "Uptrend"
            : perf20d < -2
              ? "Downtrend"
              : "Sideways"
          : "Sideways";

      return {
        industry: row.industry,
        sector: row.sector,
        current_rank: (() => {
          const v = parseInt(row.current_rank, 10);
          return !isNaN(v) ? v : idx + 1 + offset;
        })(),
        rank_12w_ago: (() => {
          const v = parseInt(row.rank_12w_ago, 10);
          return !isNaN(v) ? v : null;
        })(),
        overall_rank: (() => {
          const v = parseInt(row.current_rank, 10);
          return !isNaN(v) ? v : idx + 1 + offset;
        })(),
        stock_count: (() => {
          if (row.stock_count == null) {
            throw new Error(
              `Missing stock_count for industry ${row.industry}`
            );
          }
          const v = parseInt(row.stock_count, 10);
          if (isNaN(v)) {
            throw new Error(
              `Invalid stock_count for industry ${row.industry}: ${row.stock_count}`
            );
          }
          return v;
        })(),
        composite_score: composite,
        momentum_score: sf(row.momentum_score),
        value_score: sf(row.value_score),
        quality_score: sf(row.quality_score),
        growth_score: sf(row.growth_score),
        stability_score: sf(row.stability_score),
        performance_1d: sf(row.perf_1d),
        performance_5d: sf(row.perf_5d),
        performance_20d: perf20d,
        current_momentum: momentumLabel,
        current_trend: trendLabel,
        pe: {
          trailing: sf(row.avg_trailing_pe),
          forward: sf(row.avg_forward_pe),
          percentile: sf(row.pe_percentile),
        },
      };
    });

    const totalPages = Math.ceil(total / limitNum);
    return sendPaginated(res, industries, {
      page: pageNum,
      limit: limitNum,
      offset: offset,
      total,
      totalPages,
      hasNext: pageNum < totalPages,
      hasPrev: pageNum > 1,
    });
  } catch (error) {
    console.error("Error fetching industries:", {
      message: error.message,
      code: error.code,
      stack: error.stack?.split('\n')[0],
      type: error.constructor.name,
    });
    return sendError(
      res,
      `Failed to fetch industries: ${error.message.substring(0, 100)}`,
      500
    );
  }
}

// GET / - Get all industries
router.get("/", fetchIndustries);

// GET /industries - Alias for backward compatibility
router.get("/industries", fetchIndustries);

// GET /trends-batch - MUST be before /:industry so it isn't captured as industry name
router.get("/trends-batch", async (req, res) => {
  try {
    const { industries: industriesList, days = 90 } = req.query;
    if (!industriesList) {
      return sendError(
        res,
        "industries parameter required (comma-separated)",
        400
      );
    }

    const industries = industriesList
      .split(",")
      .map((i) => i.trim())
      .filter((i) => i.length > 0);
    // Explicit NaN check for days parameter
    const daysVal = parseInt(days, 10);
    const daysNum = Math.min(!isNaN(daysVal) ? daysVal : 90, 365);

    if (industries.length === 0) {
      return sendSuccess(res, {});
    }

    const placeholders = industries
      .map((_, i) => `LOWER(TRIM(cp.industry)) = LOWER(TRIM($${i + 1}))`)
      .join(" OR ");
    const result = await query(
      `
      WITH prices AS (
        SELECT
          cp.industry,
          DATE(pd.date) as date,
          AVG(CAST(pd.close AS FLOAT)) as avg_price,
          COUNT(DISTINCT pd.symbol) as stock_count
        FROM price_daily pd
        JOIN company_profile cp ON pd.symbol = cp.ticker
        WHERE (${placeholders})
          AND pd.date >= CURRENT_DATE - INTERVAL '${daysNum} days'
        GROUP BY cp.industry, DATE(pd.date)
        ORDER BY cp.industry, date ASC
      )
      SELECT industry, date, avg_price, stock_count,
        ((avg_price / NULLIF(FIRST_VALUE(avg_price) OVER (PARTITION BY industry ORDER BY date), 0)) - 1) * 100 AS daily_strength_score
      FROM prices
      ORDER BY industry, date ASC
    `,
      industries
    );
    validateQueryResult(result, { requireRows: false });

    const grouped = {};
    (result?.rows ?? []).forEach((row) => {
      if (!grouped[row.industry]) {
        grouped[row.industry] = [];
      }
      // Explicit NaN checks for price and strength score
      const avgPriceVal =
        row.avg_price !== null && row.avg_price !== undefined
          ? parseFloat(row.avg_price)
          : null;
      const strengthScoreVal =
        row.daily_strength_score !== null &&
        row.daily_strength_score !== undefined
          ? parseFloat(row.daily_strength_score)
          : null;
      const avgPrice =
        avgPriceVal !== null && !isNaN(avgPriceVal) ? avgPriceVal : null;
      const strengthScore =
        strengthScoreVal !== null && !isNaN(strengthScoreVal)
          ? strengthScoreVal
          : null;
      if (avgPrice === null || strengthScore === null) {
        logger.warn(
          `Industry trend data incomplete for ${row.industry}: avgPrice=${avgPrice}, strengthScore=${strengthScore}`
        );
        return;
      }
      const stockCountVal = parseInt(row.stock_count, 10);
      grouped[row.industry].push({
        date: row.date,
        avgPrice: avgPrice,
        stockCount:
          row.stock_count !== null &&
          row.stock_count !== undefined &&
          !isNaN(stockCountVal)
            ? stockCountVal
            : null,
        dailyStrengthScore: strengthScore,
      });
    });

    return sendSuccess(res, grouped, 200);
  } catch (error) {
    console.error("Error fetching industry trends batch:", error);
    return sendError(
      res,
      "Failed to fetch industry trends: " + error.message,
      500
    );
  }
});

// GET /:industry - Get specific industry details
router.get("/:industry", async (req, res) => {
  try {
    const { industry } = req.params;
    if (!industry || industry.length === 0) {
      return sendError(res, "Industry name required", 400);
    }

    // Query industry details with performance metrics
    const result = await query(
      `
      SELECT
        cp.industry as industry_name,
        COUNT(DISTINCT cp.ticker) as stock_count,
        AVG(ss.composite_score) as composite_score,
        AVG(ss.momentum_score) as momentum_score,
        AVG(ss.value_score) as value_score,
        AVG(ss.quality_score) as quality_score,
        AVG(ss.growth_score) as growth_score,
        AVG(ss.stability_score) as stability_score
      FROM company_profile cp
      LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
      WHERE LOWER(TRIM(cp.industry)) = LOWER(TRIM($1))
      GROUP BY cp.industry
    `,
      [industry]
    );
    validateQueryResult(result, { requireRows: false });

    if (result.rows.length === 0) {
      return sendError(res, `Industry not found: ${industry}`, 404);
    }

    const row = result.rows[0];
    // Explicit NaN checks for numeric fields
    const stockCountVal = parseInt(row.stock_count, 10);
    const compositeVal = parseFloat(row.composite_score);
    const momentumVal = parseFloat(row.momentum_score);
    const valueVal = parseFloat(row.value_score);
    const qualityVal = parseFloat(row.quality_score);
    const growthVal = parseFloat(row.growth_score);
    const stabilityVal = parseFloat(row.stability_score);

    const industryData = {
      industry_name: row.industry_name,
      stock_count:
        row.stock_count !== null &&
        row.stock_count !== undefined &&
        !isNaN(stockCountVal)
          ? stockCountVal
          : null,
      composite_score:
        row.composite_score !== null &&
        row.composite_score !== undefined &&
        !isNaN(compositeVal)
          ? compositeVal
          : null,
      momentum_score:
        row.momentum_score !== null &&
        row.momentum_score !== undefined &&
        !isNaN(momentumVal)
          ? momentumVal
          : null,
      value_score:
        row.value_score !== null &&
        row.value_score !== undefined &&
        !isNaN(valueVal)
          ? valueVal
          : null,
      quality_score:
        row.quality_score !== null &&
        row.quality_score !== undefined &&
        !isNaN(qualityVal)
          ? qualityVal
          : null,
      growth_score:
        row.growth_score !== null &&
        row.growth_score !== undefined &&
        !isNaN(growthVal)
          ? growthVal
          : null,
      stability_score:
        row.stability_score !== null &&
        row.stability_score !== undefined &&
        !isNaN(stabilityVal)
          ? stabilityVal
          : null,
    };

    return sendSuccess(res, industryData);
  } catch (error) {
    console.error("Error fetching industry:", error);
    return sendError(
      res,
      `Failed to fetch industry: ${error.message.substring(0, 100)}`,
      500
    );
  }
});

// GET /:industry/trend - Industry trend (proper REST structure)
router.get("/:industry/trend", async (req, res) => {
  try {
    const { industry } = req.params;
    const { days = 90 } = req.query;
    // Explicit NaN check for days parameter
    const daysVal = parseInt(days, 10);
    const daysNum = Math.min(!isNaN(daysVal) ? daysVal : 90, 365);

    const result = await query(
      `
      WITH prices AS (
        SELECT
          DATE(pd.date) as date,
          AVG(CAST(pd.close AS FLOAT)) as avg_price,
          COUNT(DISTINCT pd.symbol) as stock_count
        FROM price_daily pd
        JOIN company_profile cp ON pd.symbol = cp.ticker
        WHERE LOWER(TRIM(cp.industry)) = LOWER(TRIM($1))
          AND pd.date >= CURRENT_DATE - INTERVAL '${daysNum} days'
        GROUP BY DATE(pd.date)
        ORDER BY date ASC
      )
      SELECT date, avg_price, stock_count,
        ((avg_price / NULLIF(FIRST_VALUE(avg_price) OVER (ORDER BY date), 0)) - 1) * 100 AS daily_strength_score
      FROM prices
      ORDER BY date ASC
    `,
      [industry]
    );
    validateQueryResult(result, { requireRows: false });

    if (!result?.rows || result.rows.length === 0) {
      return sendPlaceholder(
        res,
        `No trend data available for industry: ${industry}`,
        503,
        "object"
      );
    }

    const validTrendData = result.rows
      .map((row) => {
        // Explicit NaN checks for price and strength score
        const avgPriceVal =
          row.avg_price !== null && row.avg_price !== undefined
            ? parseFloat(row.avg_price)
            : null;
        const strengthScoreVal =
          row.daily_strength_score !== null &&
          row.daily_strength_score !== undefined
            ? parseFloat(row.daily_strength_score)
            : null;
        const avgPrice =
          avgPriceVal !== null && !isNaN(avgPriceVal) ? avgPriceVal : null;
        const strengthScore =
          strengthScoreVal !== null && !isNaN(strengthScoreVal)
            ? strengthScoreVal
            : null;
        if (avgPrice === null || strengthScore === null) {
          logger.warn(
            `Industry trend data incomplete for ${industry}: avgPrice=${avgPrice}, strengthScore=${strengthScore}`
          );
          return null;
        }
        const stockCountVal = parseInt(row.stock_count, 10);
        return {
          date: row.date,
          avgPrice: avgPrice,
          stockCount:
            row.stock_count !== null &&
            row.stock_count !== undefined &&
            !isNaN(stockCountVal)
              ? stockCountVal
              : null,
          dailyStrengthScore: strengthScore,
        };
      })
      .filter(Boolean);

    return sendSuccess(res, {
      industry,
      trendData: validTrendData,
    });
  } catch (error) {
    console.error("Error fetching industry trend:", error.message);
    return sendError(
      res,
      `Failed to fetch industry trend: ${error.message.substring(0, 100)}`,
      500
    );
  }
});

// GET /trend/industry/:industryName - Get industry trend data (for SectorAnalysis charts)
router.get("/trend/industry/:industryName", async (req, res) => {
  try {
    const { industryName } = req.params;
    const { days = 90 } = req.query;
    // Explicit NaN check for days parameter
    const daysVal = parseInt(days, 10);
    const daysNum = Math.min(!isNaN(daysVal) ? daysVal : 90, 365);

    const result = await query(
      `
      WITH prices AS (
        SELECT
          DATE(pd.date) as date,
          AVG(CAST(pd.close AS FLOAT)) as avg_price,
          COUNT(DISTINCT pd.symbol) as stock_count
        FROM price_daily pd
        JOIN company_profile cp ON pd.symbol = cp.ticker
        WHERE LOWER(TRIM(cp.industry)) = LOWER(TRIM($1))
          AND pd.date >= CURRENT_DATE - INTERVAL '${daysNum} days'
        GROUP BY DATE(pd.date)
        ORDER BY date ASC
      )
      SELECT date, avg_price, stock_count,
        ((avg_price / NULLIF(FIRST_VALUE(avg_price) OVER (ORDER BY date), 0)) - 1) * 100 AS daily_strength_score
      FROM prices
      ORDER BY date ASC
    `,
      [industryName]
    );
    validateQueryResult(result, { requireRows: false });

    if (!result?.rows || result.rows.length === 0) {
      return sendError(
        res,
        `No trend data found for industry: ${industryName}`,
        404
      );
    }

    const validTrendData = result.rows
      .map((row) => {
        // Explicit NaN checks for price and strength score
        const avgPriceVal =
          row.avg_price !== null && row.avg_price !== undefined
            ? parseFloat(row.avg_price)
            : null;
        const strengthScoreVal =
          row.daily_strength_score !== null &&
          row.daily_strength_score !== undefined
            ? parseFloat(row.daily_strength_score)
            : null;
        const avgPrice =
          avgPriceVal !== null && !isNaN(avgPriceVal) ? avgPriceVal : null;
        const strengthScore =
          strengthScoreVal !== null && !isNaN(strengthScoreVal)
            ? strengthScoreVal
            : null;
        if (avgPrice === null || strengthScore === null) {
          logger.warn(
            `Industry trend data incomplete for ${industryName}: avgPrice=${avgPrice}, strengthScore=${strengthScore}`
          );
          return null;
        }
        const stockCountVal = parseInt(row.stock_count, 10);
        return {
          date: row.date,
          avgPrice: avgPrice,
          stockCount:
            row.stock_count !== null &&
            row.stock_count !== undefined &&
            !isNaN(stockCountVal)
              ? stockCountVal
              : null,
          dailyStrengthScore: strengthScore,
        };
      })
      .filter(Boolean);

    return sendSuccess(res, {
      industry: industryName,
      trendData: validTrendData,
    });
  } catch (error) {
    console.error("Error fetching industry trend:", error.message);
    return sendError(
      res,
      `Failed to fetch industry trend: ${error.message.substring(0, 100)}`,
      500
    );
  }
});

module.exports = router;

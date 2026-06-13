const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated, sendPlaceholder } = require("../utils/apiResponse");
const logger = require('../utils/logger');
const { validateQueryResult, validateAndCoerceRows, extractCount } = require('../utils/responseValidation');
const router = express.Router();

// Helper function to get industries ranked by composite score with performance metrics
async function fetchIndustries(req, res) {
  try {
    const { limit = 500, page = 1 } = req.query;
    const limitNum = Math.min(Math.max(parseInt(limit) || 500, 1), 5000);
    const pageNum = Math.max(parseInt(page) || 1, 1);
    const offset = (pageNum - 1) * limitNum;

    // Parallelize data and count queries
    const [result, countResult] = await Promise.all([
      query(`
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
    `, [limitNum, offset]),
      query(`SELECT COUNT(DISTINCT industry) as count FROM company_profile WHERE industry IS NOT NULL`)
    ]);
    validateQueryResult(result, { requireRows: false });
    const total = extractCount(countResult, 'count');

    const sf = v => (v !== null && v !== undefined) ? parseFloat(v) : null;

    const industries = (result?.rows || []).map((row, idx) => {
      const composite = sf(row.composite_score);
      const perf20d = sf(row.perf_20d);
      const momentumLabel = composite !== null && composite >= 60 ? 'Strong' : composite !== null && composite >= 45 ? 'Moderate' : 'Weak';
      const trendLabel = perf20d !== null ? (perf20d > 2 ? 'Uptrend' : perf20d < -2 ? 'Downtrend' : 'Sideways') : 'Sideways';

      return {
        industry: row.industry,
        sector: row.sector,
        current_rank: parseInt(row.current_rank) || idx + 1 + offset,
        rank_12w_ago: parseInt(row.rank_12w_ago) || null,
        overall_rank: parseInt(row.current_rank) || idx + 1 + offset,
        stock_count: parseInt(row.stock_count || 0),
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
    return sendPaginated(res, industries, {page: pageNum, limit: limitNum, total, totalPages, hasNext: pageNum < totalPages, hasPrev: pageNum > 1});
  } catch (error) {
    console.error("Error fetching industries:", error.message);
    return sendError(res, `Failed to fetch industries: ${error.message.substring(0, 100)}`, 500);
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
      return sendError(res, 'industries parameter required (comma-separated)', 400);
    }

    const industries = industriesList.split(',').map(i => i.trim()).filter(i => i.length > 0);
    const daysNum = Math.min(parseInt(days) || 90, 365);

    if (industries.length === 0) {
      return sendSuccess(res, {});
    }

    const placeholders = industries.map((_, i) => `LOWER(TRIM(cp.industry)) = LOWER(TRIM($${i + 1}))`).join(' OR ');
    const result = await query(`
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
    `, industries);
    validateQueryResult(result, { requireRows: false });

    const grouped = {};
    (result?.rows || []).forEach(row => {
      if (!grouped[row.industry]) {
        grouped[row.industry] = [];
      }
      grouped[row.industry].push({
        date: row.date,
        avgPrice: parseFloat(row.avg_price) || 0,
        stockCount: parseInt(row.stock_count) || 0,
        dailyStrengthScore: parseFloat(row.daily_strength_score) || 0
      });
    });

    return sendSuccess(res, grouped, 200);
  } catch (error) {
    console.error("Error fetching industry trends batch:", error);
    return sendError(res, "Failed to fetch industry trends: " + error.message, 500);
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
    const result = await query(`
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
    `, [industry]);
    validateQueryResult(result, { requireRows: false });

    if (result.rows.length === 0) {
      return sendError(res, `Industry not found: ${industry}`, 404);
    }

    const row = result.rows[0];
    const industryData = {
      industry_name: row.industry_name,
      stock_count: parseInt(row.stock_count || 0),
      composite_score: row.composite_score ? parseFloat(row.composite_score) : null,
      momentum_score: row.momentum_score ? parseFloat(row.momentum_score) : null,
      value_score: row.value_score ? parseFloat(row.value_score) : null,
      quality_score: row.quality_score ? parseFloat(row.quality_score) : null,
      growth_score: row.growth_score ? parseFloat(row.growth_score) : null,
      stability_score: row.stability_score ? parseFloat(row.stability_score) : null,
    };

    return sendSuccess(res, industryData);
  } catch (error) {
    console.error("Error fetching industry:", error);
    return sendError(res, `Failed to fetch industry: ${error.message.substring(0, 100)}`, 500);
  }
});

// GET /:industry/trend - Industry trend (proper REST structure)
router.get("/:industry/trend", async (req, res) => {
  try {
    const { industry } = req.params;
    const { days = 90 } = req.query;
    const daysNum = Math.min(parseInt(days) || 90, 365);

    const result = await query(`
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
    `, [industry]);
    validateQueryResult(result, { requireRows: false });

    if (!result?.rows || result.rows.length === 0) {
      return sendPlaceholder(res, `No trend data available for industry: ${industry}`, 200, 'object');
    }

    return sendSuccess(res, {
      industry,
      trendData: result.rows.map(row => ({
        date: row.date,
        avgPrice: parseFloat(row.avg_price) || 0,
        stockCount: parseInt(row.stock_count) || 0,
        dailyStrengthScore: parseFloat(row.daily_strength_score) || 0
      }))
    });
  } catch (error) {
    console.error("Error fetching industry trend:", error.message);
    return sendError(res, `Failed to fetch industry trend: ${error.message.substring(0, 100)}`, 500);
  }
});

// GET /trend/industry/:industryName - Get industry trend data (for SectorAnalysis charts)
router.get("/trend/industry/:industryName", async (req, res) => {
  try {
    const { industryName } = req.params;
    const { days = 90 } = req.query;
    const daysNum = Math.min(parseInt(days) || 90, 365);

    const result = await query(`
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
    `, [industryName]);
    validateQueryResult(result, { requireRows: false });

    if (!result?.rows || result.rows.length === 0) {
      return sendError(res, `No trend data found for industry: ${industryName}`, 404);
    }

    const trendData = result.rows.map(row => ({
      date: row.date,
      avgPrice: parseFloat(row.avg_price) || 0,
      stockCount: parseInt(row.stock_count) || 0,
      dailyStrengthScore: parseFloat(row.daily_strength_score) || 0
    }));

    return sendSuccess(res, { industry: industryName, trendData });
  } catch (error) {
    console.error("Error fetching industry trend:", error.message);
    return sendError(res, `Failed to fetch industry trend: ${error.message.substring(0, 100)}`, 500);
  }
});

module.exports = router;

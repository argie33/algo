const express = require("express");

let query, safeFloat, safeInt, safeFixed;
try {
  ({ query, safeFloat, safeInt, safeFixed } = require("../utils/database"));
} catch (error) {
  console.log("Database service not available in industries routes:", error.message);
  query = null;
  // Provide fallback functions if database module fails
  safeFloat = (val) => val !== null && val !== undefined ? parseFloat(val) : null;
  safeInt = (val) => val !== null && val !== undefined ? parseInt(val) : null;
  safeFixed = (val, decimals) => {
    if (val === null || val === undefined) return null;
    const num = parseFloat(val);
    return isNaN(num) ? null : num.toFixed(decimals || 2);
  };
}

const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Root endpoint - returns available sub-endpoints
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "industries",
      available_routes: [
        "/industries - All industry data with rankings and performance",
        "/trend/industry/:name - Industry trend data (251 data points)"
      ]
    },
    success: true
  });
});

// Apply authentication to all routes except health and root
router.use((req, res, next) => {
  // Skip auth for public endpoints - industries are PUBLIC DATA
  const publicEndpoints = ["/", "/industries"];
  const trendPattern = /^\/trend\//;

  if (publicEndpoints.includes(req.path) || trendPattern.test(req.path)) {
    return next();
  }
  // Apply auth to all other routes
  return authenticateToken(req, res, next);
});

/**
 * GET /industries
 * Get current industry data with historical rankings for display
 * Used by SectorAnalysis frontend component
 */
router.get("/industries", async (req, res) => {
  try {
    if (!query) {
      return res.status(500).json({
        error: "Database service temporarily unavailable",
        success: false
      });
    }

    const { limit = 500, sortBy = "current_rank" } = req.query;
    console.log(`🏭 Fetching industries with history (limit: ${limit})`);

    // Get latest industry rankings with real performance data from industry_performance table
    // Data integrity: Return actual performance values from database, not NULL fallbacks
    // Join with company_profile to get sector information for each industry and P/E metrics
    const industriesQuery = `
      SELECT
        ir.industry,
        cp.sector,
        ir.current_rank,
        ir.rank_1w_ago,
        ir.rank_4w_ago,
        ir.rank_12w_ago,
        ir.momentum_score as current_momentum,
        CASE
          WHEN ir.momentum_score > 20 THEN 'Strong Uptrend'
          WHEN ir.momentum_score > 10 THEN 'Uptrend'
          WHEN ir.momentum_score > -5 THEN 'Neutral'
          WHEN ir.momentum_score > -10 THEN 'Downtrend'
          WHEN ir.momentum_score IS NOT NULL THEN 'Strong Downtrend'
          ELSE NULL
        END as current_trend,
        ip.performance_1d as performance_1d,
        ip.performance_5d as performance_5d,
        ip.performance_20d as performance_20d,
        COALESCE(ip.date, ir.date_recorded) as last_updated,
        pe.trailing_pe,
        pe.forward_pe,
        pe.pe_min,
        pe.pe_p25,
        pe.pe_median,
        pe.pe_p75,
        pe.pe_p90,
        pe.pe_max
      FROM (
        SELECT DISTINCT ON (industry)
          industry, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago,
          momentum_score, date_recorded
        FROM industry_ranking
        WHERE industry IS NOT NULL AND TRIM(industry) != '' AND LOWER(industry) != 'benchmark'
        ORDER BY industry, date_recorded DESC
      ) ir
      LEFT JOIN (
        SELECT DISTINCT ON (industry)
          industry, momentum_score
        FROM industry_ranking
        WHERE industry IS NOT NULL AND TRIM(industry) != '' AND LOWER(industry) != 'benchmark' AND momentum_score IS NOT NULL
        ORDER BY industry, date_recorded DESC
      ) im ON ir.industry = im.industry
      LEFT JOIN (
        SELECT DISTINCT ON (industry)
          industry, sector
        FROM company_profile
        WHERE industry IS NOT NULL
          AND quote_type = 'EQUITY'
          AND ticker NOT LIKE '%$%'
        ORDER BY industry
      ) cp ON ir.industry = cp.industry
      LEFT JOIN (
        SELECT DISTINCT ON (industry)
          industry, performance_1d, performance_5d, performance_20d, date
        FROM industry_performance
        WHERE industry IS NOT NULL
        ORDER BY industry, date DESC
      ) ip ON ir.industry = ip.industry
      LEFT JOIN (
        SELECT
          cp.industry,
          ROUND(AVG(CASE WHEN km.trailing_pe > 0 AND km.trailing_pe < 200 THEN km.trailing_pe END)::numeric, 2) as trailing_pe,
          ROUND(AVG(CASE WHEN km.forward_pe > 0 AND km.forward_pe < 200 THEN km.forward_pe END)::numeric, 2) as forward_pe,
          MIN(CASE WHEN km.trailing_pe > 0 AND km.trailing_pe < 200 THEN km.trailing_pe END) as pe_min,
          PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY CASE WHEN km.trailing_pe > 0 AND km.trailing_pe < 200 THEN km.trailing_pe END) as pe_p25,
          PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY CASE WHEN km.trailing_pe > 0 AND km.trailing_pe < 200 THEN km.trailing_pe END) as pe_median,
          PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY CASE WHEN km.trailing_pe > 0 AND km.trailing_pe < 200 THEN km.trailing_pe END) as pe_p75,
          PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY CASE WHEN km.trailing_pe > 0 AND km.trailing_pe < 200 THEN km.trailing_pe END) as pe_p90,
          MAX(CASE WHEN km.trailing_pe > 0 AND km.trailing_pe < 200 THEN km.trailing_pe END) as pe_max
        FROM company_profile cp
        LEFT JOIN key_metrics km ON cp.ticker = km.ticker
        WHERE cp.industry IS NOT NULL
          AND TRIM(cp.industry) != ''
          AND cp.quote_type = 'EQUITY'
          AND cp.ticker NOT LIKE '%$%'
        GROUP BY cp.industry
      ) pe ON ir.industry = pe.industry
      LIMIT $1
    `;

    let result;
    try {
      result = await query(industriesQuery, [parseInt(limit)]);
    } catch (e) {
      console.warn("Industries table not available:", e.message);
      result = { rows: [] };
    }

    console.log(`✅ Industries query returned: ${result?.rows?.length || 0} rows`);

    const industries = (result?.rows || [])
      .filter(row => row.industry && row.industry.trim() !== '')  // Filter out empty industry names
      .map(row => ({
        industry: row.industry,
        sector: row.sector,
        current_rank: row.current_rank,
        rank_1w_ago: row.rank_1w_ago,
        rank_4w_ago: row.rank_4w_ago,
        rank_12w_ago: row.rank_12w_ago,
        current_momentum: row.current_momentum !== null ? parseFloat(row.current_momentum) : null,
        current_trend: row.current_trend,
        performance_1d: row.performance_1d !== null ? parseFloat(row.performance_1d) : null,
        performance_5d: row.performance_5d !== null ? parseFloat(row.performance_5d) : null,
        performance_20d: row.performance_20d !== null ? parseFloat(row.performance_20d) : null,
        last_updated: row.last_updated,
        pe: row.trailing_pe || row.forward_pe ? {
          trailing: row.trailing_pe !== null ? parseFloat(row.trailing_pe) : null,
          forward: row.forward_pe !== null ? parseFloat(row.forward_pe) : null,
          historical: {
            min: row.pe_min !== null ? parseFloat(row.pe_min) : null,
            p25: row.pe_p25 !== null ? parseFloat(row.pe_p25) : null,
            median: row.pe_median !== null ? parseFloat(row.pe_median) : null,
            p75: row.pe_p75 !== null ? parseFloat(row.pe_p75) : null,
            p90: row.pe_p90 !== null ? parseFloat(row.pe_p90) : null,
            max: row.pe_max !== null ? parseFloat(row.pe_max) : null
          },
          percentile: row.trailing_pe && row.pe_max && row.pe_min ? Math.round(((row.trailing_pe - row.pe_min) / (row.pe_max - row.pe_min)) * 100) : null
        } : null
      }));

    // Return industries data - standardized format per RULES.md
    // List endpoints use {items, pagination, success}
    const total = industries.length;
    const limitNum = Math.min(parseInt(limit, 10) || 500, 1000);
    const pageNum = 1;
    const totalPages = Math.ceil(total / limitNum);
    const hasNext = false;
    const hasPrev = false;

    return res.json({
      items: industries,
      pagination: {
        page: pageNum,
        limit: limitNum,
        total: total,
        totalPages,
        hasNext,
        hasPrev
      },
      success: true
    });
  } catch (error) {
    console.error('❌ Error in /api/industries/industries:', error.message);
    return res.status(500).json({
      error: "Request failed",
      success: false
    });
  }
});

/**
 * GET /trend/industry/:industryName
 * Get historical ranking progression for industries to identify trends
 */
router.get("/trend/industry/:industryName", async (req, res) => {
  try {
    if (!query) {
      return res.status(500).json({
        error: "Database service unavailable",
        success: false
      });
    }

    const { industryName } = req.params;

    // Get recent historical rankings for this industry (last 1 year), ordered by date_recorded
    // Calculate moving averages of momentum score directly in SQL
    const trendData = await query(
      `SELECT
        ir.date_recorded as date,
        ir.current_rank as rank,
        ir.momentum_score as daily_strength_score,
        NULL as trend,
        TO_CHAR(ir.date_recorded, 'MM/DD') as label,
        ROUND(AVG(ir.momentum_score) OVER (ORDER BY ir.date_recorded ROWS BETWEEN 9 PRECEDING AND CURRENT ROW)::numeric, 4) as ma_10,
        ROUND(AVG(ir.momentum_score) OVER (ORDER BY ir.date_recorded ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)::numeric, 4) as ma_20
      FROM industry_ranking ir
      WHERE LOWER(ir.industry) = LOWER($1)
      AND ir.date_recorded >= CURRENT_DATE - INTERVAL '365 days'
      ORDER BY ir.date_recorded ASC`,
      [industryName]
    );

    if (!trendData.rows.length) {
      return res.status(404).json({
        error: "Industry not found or no trend data available",
        success: false
      });
    }

    res.json({
      data: {
        industry: industryName,
        trendData: trendData.rows.map(row => ({
          date: row.date,
          rank: row.rank,
          dailyStrengthScore: row.daily_strength_score,
          trend: row.trend,
          label: row.label,
          ma_10: row.ma_10 !== null && row.ma_10 !== undefined ? parseFloat(row.ma_10) : null,
          ma_20: row.ma_20 !== null && row.ma_20 !== undefined ? parseFloat(row.ma_20) : null
        }))
      },
      success: true
    });
  } catch (error) {
    console.error("Industry trend endpoint error:", error.message);
    res.status(500).json({
      error: "Failed to fetch industry trend data",
      success: false,
      details: error.message
    });
  }
});

module.exports = router;

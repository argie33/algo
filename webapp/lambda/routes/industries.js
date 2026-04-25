const express = require("express");
const { getMarketDataPath } = require("../utils/market-data-path");

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

const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
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
      return res.status(503).json({
        error: "Database service unavailable",
        success: false
      });
    }

    const { limit = 500 } = req.query;

    // Query from database directly - real data
    const industriesQuery = `
      SELECT
        ir.industry,
        ir.current_rank,
        ir.rank_1w_ago,
        ir.rank_4w_ago,
        ir.rank_12w_ago,
        ir.momentum_score,
        ir.daily_strength_score,
        ir.trend,
        ir.date_recorded as last_updated
      FROM (
        SELECT DISTINCT ON (industry)
          industry, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago,
          momentum_score, daily_strength_score, trend, date_recorded
        FROM industry_ranking
        WHERE industry IS NOT NULL
          AND TRIM(industry) != ''
        ORDER BY industry, date_recorded DESC
      ) ir
      LIMIT $1
    `;

    const result = await query(industriesQuery, [Math.min(parseInt(limit) || 500, 1000)]);
    const industries = (result?.rows || []).map(row => ({
      industry: row.industry,
      current_rank: row.current_rank,
      rank_1w_ago: row.rank_1w_ago,
      rank_4w_ago: row.rank_4w_ago,
      rank_12w_ago: row.rank_12w_ago,
      momentum_score: row.momentum_score !== null ? safeFloat(row.momentum_score) : null,
      daily_strength_score: row.daily_strength_score !== null ? safeFloat(row.daily_strength_score) : null,
      trend: row.trend,
      last_updated: row.last_updated
    }));

    const total = industries.length;
    const limitNum = Math.min(parseInt(limit, 10) || 500, 1000);
    const pageNum = 1;
    const totalPages = Math.ceil(total / limitNum);

    return res.json({
      items: industries,
      pagination: {
        page: pageNum,
        limit: limitNum,
        total: total,
        totalPages,
        hasNext: false,
        hasPrev: false
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

// Fresh Industries Data Endpoint - From comprehensive data
router.get("/fresh-data", async (req, res) => {
  try {
    const fs = require("fs");

    const comprehensivePath = getMarketDataPath();

    if (fs.existsSync(comprehensivePath)) {
      const comprehensiveData = JSON.parse(fs.readFileSync(comprehensivePath, "utf-8"));

      const industries = Object.values(comprehensiveData.industries || {});
      const sorted = industries.sort((a, b) => b.changePercent - a.changePercent);

      return res.json({
        data: sorted,
        timestamp: comprehensiveData.timestamp,
        source: "fresh-industries",
        message: "Fresh industry ranking data",
        success: true
      });
    }

    return res.status(404).json({
      error: "Fresh data not available",
      success: false
    });
  } catch (error) {
    console.error("Fresh industries error:", error.message);
    return res.status(500).json({
      error: "Failed to fetch fresh industries",
      details: error.message,
      success: false
    });
  }
});

module.exports = router;

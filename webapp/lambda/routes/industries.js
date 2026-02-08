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
    // Use fresh-data from JSON file - ensures all pages have up-to-date data
    const fs = require("fs");
    const { limit = 500 } = req.query;
    const comprehensivePath = "/tmp/comprehensive_market_data.json";

    if (fs.existsSync(comprehensivePath)) {
      const data = JSON.parse(fs.readFileSync(comprehensivePath, "utf-8"));

      // Convert fresh industry data to expected format
      const industriesData = data.industries ? Object.values(data.industries) : [];
      const industries = industriesData.slice(0, parseInt(limit)).map(industry => ({
        industry: industry.name,
        symbol: industry.symbol,
        price: industry.price,
        changePercent: industry.changePercent,
        change: industry.change,
        rank: industry.rank,
        date: industry.date,
        timestamp: data.timestamp,
        source: "fresh-data"
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
    }

    // Fallback: return empty result if fresh-data not available
    return res.json({
      items: [],
      pagination: { page: 1, limit: parseInt(limit), total: 0, totalPages: 0, hasNext: false, hasPrev: false },
      success: false
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

    const comprehensivePath = "/tmp/comprehensive_market_data.json";

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

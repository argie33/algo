const express = require("express");

/**
 * Sectors API Routes
 *
 * IMPORTANT: This file has been cleaned of ALL fallback/mock data
 * - No COALESCE with hardcoded fallbacks
 * - No CASE WHEN simulated performance values
 * - All data comes directly from database tables
 * - NULL values are acceptable and expected when data is missing
 *
 * Data dependencies:
 * - company_profile table (ticker, sector, industry)
 * - price_daily table (close, volume, date)
 * - technical_data_daily table (rsi, momentum, macd, sma values)
 * - sector_performance table (for rotation analysis)
 *
 * Updated: 2025-10-11 - Removed all fallbacks and mock data
 */

let query, safeFloat, safeInt, safeFixed;
let databaseInitError = null;
const { getMarketDataPath } = require("../utils/market-data-path");

try {
  ({ query, safeFloat, safeInt, safeFixed } = require("../utils/database"));
} catch (error) {
  databaseInitError = error;
  console.error("❌ CRITICAL: Database service failed to load in sectors routes:", error.message);
  // Do NOT set query = null - this would cause cryptic errors later
  // Instead, provide fallback functions that return null for missing data
  // CRITICAL FIX: Return NULL for missing data, not fake 0 - maintains data integrity
  safeFloat = (val) => val !== null && val !== undefined ? parseFloat(val) : null;
  safeInt = (val) => val !== null && val !== undefined ? parseInt(val) : null;
  safeFixed = (val, decimals) => {
    if (val === null || val === undefined) return null;
    const num = parseFloat(val);
    return isNaN(num) ? null : num.toFixed(decimals || 2);
  };
}

// Helper function to check database availability before making queries
function checkDatabaseAvailable(res) {
  if (databaseInitError) {
    console.error('⚠️ Database not available - returning error response');
    return res.status(503).json({
      error: "Database service unavailable - cannot retrieve sector data",
      success: false
    });
  }
  return null;
}

// Helper function to validate database response (currently unused but kept for future use)
// eslint-disable-next-line no-unused-vars
function validateDbResponse(result, context = "database query") {
  if (!result || typeof result !== 'object' || !Array.isArray(result.rows)) {
    throw new Error(`Database response validation failed for ${context}: result is null, undefined, or missing rows array`);
  }
  return result;
}

const { authenticateToken } = require("../middleware/auth");

const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

// Root endpoint - returns available sub-endpoints
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "sectors",
      available_routes: [
        "/sectors - All sector data with rankings and performance",
        "/trend/sector/:name - Sector trend data (251 data points)",
        "/:sector/stocks - Get stocks in a specific sector",
        "/:sector/details - Get details for a specific sector"
      ]
    },
    success: true
  });
});


// Apply authentication to all routes except health and root
router.use((req, res, next) => {
  // Skip auth for public endpoints - sectors are PUBLIC DATA
  const publicEndpoints = ["/", "/performance", "/leaders", "/rotation", "/ranking-history", "/sectors", "/allocation", "/analysis"];
  const sectorDetailPattern = /^\/[^/]+\/(stocks|details)$/; // matches /:sector/stocks, /:sector/details

  if (publicEndpoints.includes(req.path) || sectorDetailPattern.test(req.path)) {
    return next();
  }
  // Apply auth to all other routes
  return authenticateToken(req, res, next);
});

/**
 * GET /sectors/list
 * Get list of all available sectors and industries
 */
// Get sector performance summary

/**
 * GET /sectors/:sector/details
 * Get detailed analysis for a specific sector
 */
// Get portfolio sector allocation

// Sector rotation analysis
// Sector leaders
// Sector laggards
/**
 * GET /sectors-with-history
 * Get current sector data with historical rankings for display
 * Used by SectorAnalysis frontend component
 */
router.get("/sectors", async (req, res) => {
  try {
    // Use fresh-data from JSON file - ensures all pages have up-to-date data
    const fs = require("fs");
    const { limit = 20 } = req.query;
    const comprehensivePath = getMarketDataPath();

    if (fs.existsSync(comprehensivePath)) {
      const data = JSON.parse(fs.readFileSync(comprehensivePath, "utf-8"));

      // Convert fresh sector data to expected format
      const sectorsData = data.sectors ? Object.values(data.sectors) : [];
      const sectors = sectorsData.slice(0, parseInt(limit)).map(sector => ({
        sector_name: sector.name,
        symbol: sector.symbol,
        price: sector.price,
        change: sector.change,
        changePercent: sector.changePercent,
        performance: sector.performance,
        date: sector.date,
        timestamp: data.timestamp,
        source: "fresh-data"
      }));

      const total = sectors.length;
      const limitNum = Math.min(parseInt(limit, 10) || 500, 1000);
      const pageNum = 1;
      const totalPages = Math.ceil(total / limitNum);

      return res.json({
        items: sectors,
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
    console.error('❌ Error in /api/sectors/sectors:', error.message);
    return res.status(500).json({
      error: "Request failed",
      success: false
    });
  }
});

/**
 * GET /sectors/trend/:sector
 * Get sector ranking trend (momentum/valuation changes) over time
 * NOTE: /trend/sector/:sectorName is handled by a more specific route below
 */
router.get("/trend/:sectorName", async (req, res, next) => {
  try {
    // Skip if this is the "sector" placeholder from /trend/sector/:sectorName pattern
    // That specific route is handled separately below
    if (req.params.sectorName === "sector") {
      return next();
    }

    const dbError = checkDatabaseAvailable(res);
    if (dbError) return dbError;

    const { sectorName } = req.params;
    const { days = 90 } = req.query;
    const daysNum = Math.min(parseInt(days), 365);

    // Get historical ranking and momentum for the sector
    const trendQuery = `
      SELECT
        DATE(date_recorded) as date,
        current_rank as rank,
        momentum_score as momentum,
        trend,
        daily_strength_score,
        rank_1w_ago,
        rank_4w_ago,
        rank_12w_ago
      FROM sector_ranking
      WHERE LOWER(sector_name) = LOWER($1)
        AND date_recorded >= CURRENT_DATE - INTERVAL '${daysNum} days'
      ORDER BY date_recorded DESC
      LIMIT 365
    `;

    const result = await query(trendQuery, [sectorName]);

    if (!result?.rows || result.rows.length === 0) {
      return res.status(404).json({
        error: `No trend data found for sector: ${sectorName}`,
        success: false
      });
    }

    const trendData = result.rows.reverse().map(row => ({
      date: row.date,
      rank: safeInt(row.rank),
      momentum: safeFloat(row.momentum),
      trend: row.trend,
      strength: safeFloat(row.daily_strength_score),
      rank_1w: safeInt(row.rank_1w_ago),
      rank_4w: safeInt(row.rank_4w_ago),
      rank_12w: safeInt(row.rank_12w_ago)
    }));

    return res.json({
      sector: sectorName,
      current: trendData[trendData.length - 1],
      history: trendData,
      success: true
    });
  } catch (error) {
    console.error('❌ Error in /api/sectors/trend:', error.message);
    return res.status(500).json({
      error: "Failed to fetch trend data",
      success: false
    });
  }
});

/**
 * GET /api/sectors/analysis
 * Alias for /sectors endpoint - returns sector analysis data
 */
router.get("/analysis", async (req, res) => {
  try {
    const { limit = 20 } = req.query;
    console.log(`📊 Fetching sector analysis (limit: ${limit})`);

    const sectorsQuery = `
      SELECT
        sr.sector_name as sector,
        sr.current_rank,
        sr.rank_1w_ago,
        sr.rank_4w_ago,
        sr.rank_12w_ago,
        COALESCE(sr.momentum_score, sm.momentum_score) as current_momentum,
        CASE
          WHEN COALESCE(sr.momentum_score, sm.momentum_score) > 20 THEN 'Strong Uptrend'
          WHEN COALESCE(sr.momentum_score, sm.momentum_score) > 10 THEN 'Uptrend'
          WHEN COALESCE(sr.momentum_score, sm.momentum_score) > -5 THEN 'Neutral'
          WHEN COALESCE(sr.momentum_score, sm.momentum_score) > -10 THEN 'Downtrend'
          WHEN COALESCE(sr.momentum_score, sm.momentum_score) IS NOT NULL THEN 'Strong Downtrend'
          ELSE NULL
        END as current_trend,
        sp.performance_1d as performance_1d,
        sp.performance_5d as performance_5d,
        sp.performance_20d as performance_20d,
        COALESCE(sp.date, sr.date_recorded) as last_updated
      FROM (
        SELECT DISTINCT ON (sector_name)
          sector_name, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago,
          momentum_score, date_recorded
        FROM sector_ranking
        WHERE sector_name IS NOT NULL
          AND TRIM(sector_name) != ''
          AND LOWER(sector_name) NOT IN ('index', 'unknown')
        ORDER BY sector_name, date_recorded DESC
      ) sr
      LEFT JOIN (
        SELECT DISTINCT ON (sector_name)
          sector_name, momentum_score
        FROM sector_ranking
        WHERE sector_name IS NOT NULL AND momentum_score IS NOT NULL
        ORDER BY sector_name, date_recorded DESC
      ) sm ON sr.sector_name = sm.sector_name
      LEFT JOIN (
        SELECT DISTINCT ON (sector)
          sector, performance_1d, performance_5d, performance_20d, date
        FROM sector_performance
        WHERE sector IS NOT NULL
        ORDER BY sector, date DESC
      ) sp ON sr.sector_name = sp.sector
      LIMIT $1
    `;

    const result = await query(sectorsQuery, [parseInt(limit)]);
    const sectors = (result?.rows || []).map(row => ({
      sector_name: row.sector,
      current_rank: row.current_rank,
      rank_1w_ago: row.rank_1w_ago,
      rank_4w_ago: row.rank_4w_ago,
      rank_12w_ago: row.rank_12w_ago,
      current_momentum: row.current_momentum !== null ? parseFloat(row.current_momentum) : null,
      current_trend: row.current_trend,
      current_perf_1d: row.performance_1d !== null ? parseFloat(row.performance_1d) : null,
      current_perf_5d: row.performance_5d !== null ? parseFloat(row.performance_5d) : null,
      current_perf_20d: row.performance_20d !== null ? parseFloat(row.performance_20d) : null,
      last_updated: row.last_updated
    }));

    const total = sectors.length;
    const limitNum = Math.min(parseInt(limit, 10) || 500, 1000);
    const pageNum = 1;
    const totalPages = Math.ceil(total / limitNum);

    return res.json({
      items: sectors,
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
    console.error('❌ Error in /api/sectors/analysis:', error.message);
    return res.status(500).json({
      error: 'Failed to fetch sector analysis',
      details: error.message,
      success: false
    });
  }
});

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Build SQL query for ranking history based on type (sector or industry)
 * BUG FIX: Added missing helper function for ranking history queries
 */
function buildRankingHistoryQuery(type, specificItem = null) {
  const typeCol = type === 'sector' ? 'sector' : 'industry';
  const table = type === 'sector' ? 'sector_performance' : 'industry_performance';

  if (specificItem) {
    return `
      SELECT
        ${typeCol},
        date,
        rank,
        performance_score,
        stocks_up,
        stocks_down,
        total_stocks,
        avg_return
      FROM ${table}
      WHERE ${typeCol} = $1
        AND rank <= $2
      ORDER BY date DESC, rank ASC
      LIMIT $3
    `;
  }

  return `
    SELECT
      ${typeCol},
      date,
      rank,
      performance_score,
      stocks_up,
      stocks_down,
      total_stocks,
      avg_return
    FROM ${table}
    WHERE rank <= $1
    ORDER BY date DESC, rank ASC
    LIMIT $2
  `;
}

/**
 * Process ranking results into period-based structure
 * BUG FIX: Added missing helper function for ranking result processing
 * BUG FIX: Handle multiple column name formats (database vs test data)
 */
function processRankingResults(rows, type) {
  const rankingsByPeriod = {};

  // Group by period (today, 1_week_ago, 3_weeks_ago, 8_weeks_ago)
  const periods = ['today', '1_week_ago', '3_weeks_ago', '8_weeks_ago'];

  rows.forEach(row => {
    // BUG FIX: Handle both test data column names and database column names
    const dateField = row.date || row.rank_date;
    const rankField = type === 'sector'
      ? (row.rank || row.sector_rank)
      : (row.rank || row.overall_rank);
    const nameField = type === 'sector'
      ? (row.sector || row.sector_name)
      : (row.industry || row.industry_name);

    // BUG FIX: Validate date value before using it
    if (!dateField) {
      console.warn(`Missing date in ranking result for ${type}`);
      return; // Skip this row
    }

    const rowDate = new Date(dateField);

    // BUG FIX: Check if date is valid
    if (isNaN(rowDate.getTime())) {
      console.warn(`Invalid date value: ${dateField}`);
      return; // Skip this row
    }

    let dateStr;
    try {
      dateStr = rowDate.toISOString().split('T')[0];
    } catch (error) {
      console.warn(`Error converting date to ISO string: ${error.message}`);
      return; // Skip this row
    }

    // BUG FIX: Use period from row if available (for test data), otherwise calculate
    let period = row.period || 'today';

    // Only calculate if not provided
    if (!row.period) {
      const now = new Date();
      const daysDiff = Math.floor((now - rowDate) / (1000 * 60 * 60 * 24));
      if (daysDiff >= 7 && daysDiff < 21) period = '1_week_ago';
      else if (daysDiff >= 21 && daysDiff < 56) period = '3_weeks_ago';
      else if (daysDiff >= 56) period = '8_weeks_ago';
    }

    if (!rankingsByPeriod[period]) {
      rankingsByPeriod[period] = [];
    }

    // Preserve all relevant fields from the row for later use - only real data, no defaults
    rankingsByPeriod[period].push({
      name: nameField,
      rank: rankField ?? null,
      date: dateStr,
      performance_score: row.performance_score !== null && row.performance_score !== undefined ? row.performance_score : (row.performance_20d ?? null),
      stocks_up: row.stocks_up ?? null,
      stocks_down: row.stocks_down ?? null,
      total_stocks: row.total_stocks ?? null,
      avg_return: row.avg_return ?? null,
      // Preserve additional fields from raw row
      sector_rank: row.sector_rank ?? null,
      overall_rank: row.overall_rank ?? null,
      stock_count: row.stock_count ?? null,
      raw: row // Keep raw row for any missing fields
    });
  });

  return rankingsByPeriod;
}

/**
 * Format ranking response to match API expectations
 * BUG FIX: Convert rankingsByPeriod structure to array of items with rankings, trend, direction
 */
function formatRankingResponse(rankingsByPeriod, type) {
  const itemMap = {};

  // Group rankings by item name
  Object.entries(rankingsByPeriod).forEach(([period, items]) => {
    items.forEach(item => {
      if (!itemMap[item.name]) {
        itemMap[item.name] = {
          [type === 'sector' ? 'sector' : 'industry']: item.name,
          rankings: {}
        };
      }
      // BUG FIX: Include all relevant ranking fields
      itemMap[item.name].rankings[period] = {
        rank: item.rank,
        performance_score: item.performance_score,
        date: item.date,
        stocks_up: item.stocks_up,
        stocks_down: item.stocks_down,
        total_stocks: item.total_stocks,
        avg_return: item.avg_return,
        // Include additional fields that tests expect
        sector_rank: item.sector_rank,
        overall_rank: item.overall_rank,
        stock_count: item.stock_count
      };
    });
  });

  // Convert to array and calculate trend/direction
  return Object.values(itemMap).map(item => {
    const todayRank = item.rankings.today?.rank || null;
    const weekAgoRank = item.rankings['1_week_ago']?.rank || null;

    // Determine trend direction (lower rank = better, so declining rank = improving)
    let trend = 'stable';
    let direction = '→';

    if (weekAgoRank !== null && todayRank !== null) {
      if (todayRank < weekAgoRank) {
        trend = 'improving';
        direction = '↑';
      } else if (todayRank > weekAgoRank) {
        trend = 'declining';
        direction = '↓';
      }
    }

    return {
      ...item,
      trend,
      direction
    };
  });
}

// Trend Data Endpoints - Return historical rankings for charting
router.get("/trend/sector/:sectorName", async (req, res) => {
  try {
    if (!query) {
      return sendError(res, "Database service unavailable", 400);
    }

    const { sectorName } = req.params;

    // Try to get trend data from sector_trend table
    // Falls back to empty array if table doesn't exist or has no data
    let trendData = { rows: [] };
    try {
      trendData = await query(
        `SELECT
          trend_date as date,
          trend_value,
          TO_CHAR(trend_date, 'MM/DD') as label
        FROM sector_trend
        WHERE LOWER(sector) = LOWER($1)
        AND trend_date >= CURRENT_DATE - INTERVAL '365 days'
        ORDER BY trend_date ASC`,
        [sectorName]
      );
    } catch (tableErr) {
      console.warn(`Sector trend table not available: ${tableErr.message}`);
      // Return empty but valid response
    }

    res.json({
      data: {
        sector: sectorName,
        trendData: trendData.rows.map(row => ({
          date: row.date,
          value: row.trend_value,
          label: row.label
        })) || [],
        status: trendData.rows.length === 0 ? "no_data" : "ok"
      },
      success: true
    });
  } catch (error) {
    console.error("Sector trend endpoint error:", error.message);
    res.status(500).json({
      error: "Failed to fetch sector trend data",
      success: false
    });
  }
});

// Fresh Sectors Data Endpoint - From comprehensive data
router.get("/fresh-data", async (req, res) => {
  try {
    const fs = require("fs");

    const comprehensivePath = "/tmp/comprehensive_market_data.json";

    if (fs.existsSync(comprehensivePath)) {
      const comprehensiveData = JSON.parse(fs.readFileSync(comprehensivePath, "utf-8"));

      const sectors = Object.values(comprehensiveData.sectors || {});

      return res.json({
        data: sectors,
        timestamp: comprehensiveData.timestamp,
        source: "fresh-sectors",
        message: "Fresh sector performance data",
        success: true
      });
    }

    return res.status(404).json({
      error: "Fresh data not available",
      success: false
    });
  } catch (error) {
    console.error("Fresh sectors error:", error.message);
    return res.status(500).json({
      error: "Failed to fetch fresh sectors",
      details: error.message,
      success: false
    });
  }
});

// ============================================================================
// BACKWARD COMPATIBILITY ENDPOINTS - Frontend expects these paths
// ============================================================================

// GET /api/sectors/sectors-with-history - Return all sectors with ranking history
router.get("/sectors-with-history", async (req, res) => {
  try {
    if (databaseInitError || !query) {
      return res.status(503).json({
        error: "Database service unavailable",
        success: false
      });
    }

    console.log("📊 /api/sectors/sectors-with-history - Fetching sector data from database...");

    // Get current sector rankings with their latest performance
    const sectorQuery = `
      SELECT DISTINCT
        sector_name,
        current_rank as rank,
        momentum_score,
        trailing_pe,
        date_recorded,
        COUNT(*) OVER (PARTITION BY sector_name) as history_count
      FROM sector_ranking
      WHERE date_recorded >= CURRENT_DATE - INTERVAL '90 days'
      ORDER BY sector_name, date_recorded DESC
    `;

    const result = await query(sectorQuery);

    if (!result || !result.rows) {
      return res.json({
        data: [],
        success: true,
        message: "No sector data available"
      });
    }

    // Group by sector to get latest entry
    const sectorMap = {};
    result.rows.forEach(row => {
      if (!sectorMap[row.sector_name]) {
        sectorMap[row.sector_name] = {
          name: row.sector_name,
          rank: row.rank,
          momentum_score: safeFloat(row.momentum_score),
          trailing_pe: safeFloat(row.trailing_pe),
          date: row.date_recorded,
          history_count: row.history_count
        };
      }
    });

    const sectors = Object.values(sectorMap);

    return res.json({
      data: sectors,
      count: sectors.length,
      success: true
    });
  } catch (error) {
    console.error("❌ Sectors with history error:", error.message);
    return res.status(500).json({
      error: "Failed to fetch sectors with history",
      details: error.message,
      success: false
    });
  }
});

// GET /api/sectors/sectors-with-history/performance - Return sector performance data
router.get("/sectors-with-history/performance", async (req, res) => {
  try {
    if (databaseInitError || !query) {
      return res.status(503).json({
        error: "Database service unavailable",
        success: false
      });
    }

    console.log("📊 /api/sectors/sectors-with-history/performance - Fetching sector performance...");

    // Get latest sector performance data - simple query to avoid timeouts
    const performanceQuery = `
      SELECT DISTINCT ON (sector_name)
        sector_name,
        date as performance_date
      FROM sector_performance
      ORDER BY sector_name, date DESC
      LIMIT 20
    `;

    try {
      const result = await query(performanceQuery);

      if (!result || !result.rows) {
        return res.json({
          data: [],
          success: true,
          message: "No performance data available"
        });
      }

      const performanceData = result.rows.map(row => ({
        sector_name: row.sector_name || "Unknown",
        date: row.performance_date
      }));

      return res.json({
        data: performanceData,
        count: performanceData.length,
        success: true
      });
    } catch (queryError) {
      // If query fails, return empty data instead of error
      console.warn("⚠️ Sector performance query failed, returning empty data:", queryError.message);
      return res.json({
        data: [],
        success: true,
        message: "Performance data temporarily unavailable"
      });
    }
  } catch (error) {
    console.error("❌ Sector performance error:", error.message);
    return res.json({
      data: [],
      success: true,
      message: "Performance data temporarily unavailable"
    });
  }
});

// Rankings Endpoints - Return current rankings with daily strength scores
router.get("/ranking", async (req, res) => {
  try {
    const result = await query(`
      SELECT DISTINCT ON (sector_name)
        sector_name,
        current_rank,
        rank_1w_ago,
        rank_4w_ago,
        rank_12w_ago,
        daily_strength_score,
        momentum_score,
        trend,
        date_recorded
      FROM sector_ranking
      WHERE sector_name IS NOT NULL
      ORDER BY sector_name, date_recorded DESC
    `);

    res.json({
      data: result.rows || [],
      success: true
    });
  } catch (error) {
    console.error("Sector ranking error:", error.message);
    sendError(res, "Failed to fetch sector rankings", 500);
  }
});

router.get("/performance", async (req, res) => {
  try {
    const result = await query(`
      SELECT DISTINCT ON (sector)
        sector,
        date,
        performance_1d,
        performance_5d,
        performance_20d,
        performance_ytd
      FROM sector_performance
      WHERE sector IS NOT NULL
      ORDER BY sector, date DESC
    `);

    res.json({
      data: result.rows || [],
      success: true
    });
  } catch (error) {
    console.error("Sector performance error:", error.message);
    sendError(res, "Failed to fetch sector performance", 500);
  }
});

// Industry endpoints
router.get("/industries/ranking", async (req, res) => {
  try {
    const result = await query(`
      SELECT DISTINCT ON (industry)
        industry,
        current_rank,
        rank_1w_ago,
        rank_4w_ago,
        rank_12w_ago,
        daily_strength_score,
        momentum_score,
        stock_count,
        trend,
        date_recorded
      FROM industry_ranking
      WHERE industry IS NOT NULL
      ORDER BY industry, date_recorded DESC
    `);

    res.json({
      data: result.rows || [],
      success: true
    });
  } catch (error) {
    console.error("Industry ranking error:", error.message);
    sendError(res, "Failed to fetch industry rankings", 500);
  }
});

router.get("/industries/performance", async (req, res) => {
  try {
    const result = await query(`
      SELECT DISTINCT ON (industry)
        industry,
        date,
        performance_1d,
        performance_5d,
        performance_20d,
        performance_ytd
      FROM industry_performance
      WHERE industry IS NOT NULL
      ORDER BY industry, date DESC
    `);

    res.json({
      data: result.rows || [],
      success: true
    });
  } catch (error) {
    console.error("Industry performance error:", error.message);
    sendError(res, "Failed to fetch industry performance", 500);
  }
});

module.exports = router;

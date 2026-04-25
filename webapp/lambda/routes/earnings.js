const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");
const { getMarketDataPath } = require("../utils/market-data-path");

const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

// Root endpoint - returns reference/documentation only
router.get("/", (req, res) => {
  res.json({
    data: {
      endpoint: "earnings",
      description: "Earnings data API - financial metrics and estimates",
      available_routes: [
        {
          path: "/info",
          method: "GET",
          description: "Get earnings estimates data",
          query_params: ["symbol", "limit", "page"]
        },
        {
          path: "/data",
          method: "GET",
          description: "Get all earnings history data",
          query_params: ["symbol", "limit", "page"]
        },
        {
          path: "/calendar",
          method: "GET",
          description: "Calendar view of earnings with reported status",
          query_params: ["period", "startDate", "endDate", "symbol", "limit"]
        }
      ]
    },
    success: true
  });
});

// ============================================================
// Named endpoints (must come BEFORE /:symbol route)
// ============================================================

// GET /api/earnings/info - Get earnings estimates and history combined
router.get("/info", async (req, res) => {
  try {
    const symbol = req.query.symbol;
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    let sql = "SELECT * FROM earnings_estimates";
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      sql += ` WHERE symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    const countResult = await query(
      `SELECT COUNT(*) as count FROM (${sql}) t`,
      params
    );
    const total = countResult.rows[0]?.count || 0;

    const result = await query(
      sql + ` ORDER BY symbol, period DESC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return res.json({
      data: {
        estimates: result.rows || [],
        pagination: { page, limit, total, hasMore: offset + limit < total }
      },
      success: true
    });
  } catch (err) {
    console.error("Earnings info error:", err.message);
    return sendError(res, err.message, 500);
  }
});

// GET /api/earnings/data - Get all earnings history data
router.get("/data", async (req, res) => {
  try {
    const symbol = req.query.symbol;
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    let sql = "SELECT * FROM earnings_history";
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      sql += ` WHERE symbol = $${paramIndex}`;
      params.push(symbol);
      paramIndex++;
    }

    const countResult = await query(
      `SELECT COUNT(*) as count FROM (${sql}) t`,
      params
    );
    const total = countResult.rows[0]?.count || 0;

    const result = await query(
      sql + ` ORDER BY symbol, quarter DESC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      [...params, limit, offset]
    );

    return res.json({
      data: result.rows || [],
      pagination: { page, limit, total, hasMore: offset + limit < total },
      success: true
    });
  } catch (err) {
    console.error("Earnings data error:", err.message);
    return sendError(res, err.message, 500);
  }
});

// GET /api/earnings/calendar - Earnings calendar view with filters
router.get("/calendar", async (req, res) => {
  try {
    const { period = "past", startDate, endDate, symbol, limit = 100 } = req.query;

    const params = [];
    let whereClause = " WHERE eh.quarter IS NOT NULL ";

    if (period === "past") {
      whereClause += " AND eh.quarter <= CURRENT_DATE ";
    } else if (period === "upcoming") {
      whereClause += " AND eh.quarter > CURRENT_DATE ";
    } else if (startDate || endDate) {
      if (startDate) {
        params.push(startDate);
        whereClause += ` AND eh.quarter >= $${params.length} `;
      }
      if (endDate) {
        params.push(endDate);
        whereClause += ` AND eh.quarter <= $${params.length} `;
      }
    }

    if (symbol) {
      params.push(symbol.toUpperCase());
      whereClause += ` AND eh.symbol = $${params.length} `;
    }

    const limitNum = Math.min(parseInt(limit) || 100, 1000);
    params.push(limitNum);

    const query_str = `
      SELECT DISTINCT ON (eh.symbol, eh.quarter)
        eh.symbol,
        eh.quarter as date,
        EXTRACT(QUARTER FROM eh.quarter) as quarter,
        EXTRACT(YEAR FROM eh.quarter) as year,
        'Earnings Report' as title,
        eh.created_at as fetched_at,
        COALESCE(cp.short_name, eh.symbol) as company_name,
        cp.sector
      FROM earnings_history eh
      LEFT JOIN company_profile cp ON eh.symbol = cp.ticker
      ${whereClause}
      ORDER BY eh.symbol ASC, eh.quarter DESC, eh.created_at DESC
      LIMIT $${params.length}
    `;

    const result = await query(query_str, params);

    const calendar = result.rows.map(row => ({
      symbol: row.symbol,
      company_name: row.company_name || row.symbol,
      sector: row.sector,
      date: row.date,
      quarter: parseInt(row.quarter),
      year: parseInt(row.year),
      title: row.title,
      fetched_at: row.fetched_at
    }));

    const pageNum = 1;
    const totalPages = Math.ceil(calendar.length / limitNum);

    res.json({
      items: calendar,
      pagination: {
        page: pageNum,
        limit: limitNum,
        total: calendar.length,
        totalPages,
        hasNext: false,
        hasPrev: false
      },
      success: true
    });
  } catch (error) {
    console.error("Error fetching earnings calendar:", error);
    res.status(500).json({
      error: "Failed to fetch earnings calendar",
      success: false
    });
  }
});

// GET /api/earnings/sp500-trend - S&P 500 earnings trend over time
router.get("/sp500-trend", async (req, res) => {
  try {
    // Count stocks reporting in latest quarter from earnings_history
    const stockCountQuery = `
      SELECT COUNT(DISTINCT symbol) as stock_count
      FROM earnings_history
      WHERE quarter >= DATE_TRUNC('quarter', CURRENT_DATE - INTERVAL '1 month')
        AND quarter <= DATE_TRUNC('quarter', CURRENT_DATE)
    `;

    const stockCountResult = await query(stockCountQuery);
    const latestStockCount = stockCountResult.rows[0]?.stock_count || 0;

    res.json({
      data: {
        timeSeries: [],
        summary: {
          trend: "neutral",
          changePercent: "0.00",
          latestEarnings: null,
          latestDate: null,
          latestStockCount,
          forecastPeriods: 0,
          isStale: false,
          dataWarning: "⚠️ Economic data table not available - using earnings_history count only"
        }
      },
      success: true
    });
  } catch (error) {
    console.error("Error fetching S&P 500 earnings trend:", error);
    res.status(500).json({
      error: "Failed to fetch S&P 500 earnings trend",
      success: false
    });
  }
});

// GET /api/earnings/estimate-momentum - Top stocks with rising/falling estimates
router.get("/estimate-momentum", async (req, res) => {
  try {
    const { limit = 20, period = '0q' } = req.query;

    // Use earnings_estimates table which has the data we loaded
    const estimatesQuery = `
      SELECT
        ee.symbol,
        ee.period,
        ee.avg_estimate,
        cp.short_name as company_name,
        cp.sector,
        COUNT(*) OVER (PARTITION BY ee.symbol) as estimate_count
      FROM earnings_estimates ee
      LEFT JOIN company_profile cp ON ee.symbol = cp.ticker
      WHERE ee.avg_estimate IS NOT NULL
        AND ee.period = $1
      ORDER BY ee.symbol
      LIMIT $2
    `;

    const result = await query(estimatesQuery, [period, parseInt(limit)]);

    // Return empty data if no estimates available
    res.json({
      data: {
        rising: result.rows.slice(0, parseInt(limit)/2).map(row => ({
          symbol: row.symbol,
          company_name: row.company_name || row.symbol,
          sector: row.sector,
          period: row.period,
          current_estimate: parseFloat(row.avg_estimate),
          estimate_60d_ago: null,
          pct_change: 0,
          up_last_7d: 0,
          down_last_7d: 0,
          up_last_30d: 0,
          down_last_30d: 0,
          net_revisions_7d: 0,
          net_revisions: 0
        })),
        falling: [],
        summary: {
          total_rising: Math.min(result.rows.length, parseInt(limit)/2),
          total_falling: 0,
          avg_rise: 0,
          avg_fall: 0,
          dataWarning: "Estimate trends table not available - showing available estimates only"
        }
      },
      success: true
    });
  } catch (error) {
    console.error("Error fetching estimate momentum:", error);
    res.status(500).json({
      error: "Failed to fetch estimate momentum",
      details: error.message,
      success: false
    });
  }
});

// GET /api/earnings/sector-trend - Sector earnings growth and estimate outlook
router.get("/sector-trend", async (req, res) => {
  try {
    // Query 1: Earnings Growth (Historical Quarterly EPS by Sector)
    const earningsGrowthQuery = `
      WITH quarterly_sector_eps AS (
        SELECT
          DATE_TRUNC('quarter', eh.quarter) as quarter_date,
          TO_CHAR(eh.quarter, 'YYYY-"Q"Q') as quarter_label,
          cp.sector,
          COUNT(DISTINCT eh.symbol) as stock_count,
          AVG(eh.eps_actual) as avg_eps
        FROM earnings_history eh
        INNER JOIN company_profile cp ON eh.symbol = cp.ticker
        WHERE eh.quarter >= '2020-01-01'
          AND cp.sector IS NOT NULL
          AND eh.eps_actual IS NOT NULL
          AND eh.eps_actual > -500
          AND eh.eps_actual < 500
        GROUP BY DATE_TRUNC('quarter', eh.quarter), TO_CHAR(eh.quarter, 'YYYY-"Q"Q'), cp.sector
        HAVING COUNT(DISTINCT eh.symbol) >= 2
      )
      SELECT
        qse.quarter_label,
        qse.sector,
        ROUND(qse.avg_eps::numeric, 2) as avg_eps,
        qse.stock_count
      FROM quarterly_sector_eps qse
      ORDER BY qse.quarter_date ASC, qse.sector
    `;

    const growthResult = await query(earningsGrowthQuery);

    // Transform earnings growth to time series format
    const timeSeriesMap = new Map();
    growthResult.rows.forEach(row => {
      if (!timeSeriesMap.has(row.quarter_label)) {
        timeSeriesMap.set(row.quarter_label, { quarter: row.quarter_label });
      }
      timeSeriesMap.get(row.quarter_label)[row.sector] = parseFloat(row.avg_eps);
    });

    const earningsGrowthTimeSeries = Array.from(timeSeriesMap.values());

    // Calculate growth summary - Compare earliest vs latest quarters (proper YoY growth)
    const sectorQuarterlyEps = new Map();
    growthResult.rows.forEach(row => {
      if (!sectorQuarterlyEps.has(row.sector)) {
        sectorQuarterlyEps.set(row.sector, { quarters: [], stockCount: row.stock_count });
      }
      const stats = sectorQuarterlyEps.get(row.sector);
      stats.quarters.push({
        quarter: row.quarter_label,
        eps: parseFloat(row.avg_eps)
      });
    });

    const sectorGrowthValues = Array.from(sectorQuarterlyEps.entries()).map(([name, stats]) => {
      let growth = 0;

      if (stats.quarters.length >= 2) {
        const oldest = stats.quarters[0].eps;
        const newest = stats.quarters[stats.quarters.length - 1].eps;

        if (oldest > 0 && newest !== null) {
          growth = ((newest - oldest) / Math.abs(oldest)) * 100;
        } else if (oldest < 0 && newest !== null) {
          growth = newest - oldest;
        }
      }

      return {
        name,
        growth: isFinite(growth) ? parseFloat(growth.toFixed(2)) : 0,
        stockCount: stats.stockCount,
        quartersTracked: stats.quarters.length
      };
    });

    const bestGrowth = sectorGrowthValues.length > 0
      ? sectorGrowthValues.reduce((a, b) => a.growth > b.growth ? a : b)
      : { name: 'N/A', growth: 0, stockCount: 0 };

    const worstGrowth = sectorGrowthValues.length > 0
      ? sectorGrowthValues.reduce((a, b) => a.growth < b.growth ? a : b)
      : { name: 'N/A', growth: 0, stockCount: 0 };

    res.json({
      data: {
        earningsGrowth: {
          timeSeries: earningsGrowthTimeSeries,
          summary: {
            bestGrowth,
            worstGrowth
          }
        },
        estimateOutlook: {
          sectors: [],
          summary: {
            mostOptimistic: { name: 'N/A', change: 0 },
            leastOptimistic: { name: 'N/A', change: 0 }
          }
        },
        dataQuality: {
          earningsHistory: {
            totalQuarters: earningsGrowthTimeSeries.length,
            totalSectors: sectorGrowthValues.length,
            dataSource: "earnings_history table"
          },
          estimateOutlook: {
            totalSectors: 0,
            sectorsWithForwardEstimates: 0,
            dataWarning: "⚠️ Estimate data not available"
          }
        }
      },
      success: true
    });
  } catch (error) {
    console.error("Error fetching sector trend:", error);
    res.status(500).json({
      error: "Failed to fetch sector trend",
      success: false
    });
  }
});

// Fresh Earnings Data Endpoint - From comprehensive data
router.get("/fresh-data", async (req, res) => {
  try {
    const fs = require("fs");

    const comprehensivePath = getMarketDataPath();

    if (fs.existsSync(comprehensivePath)) {
      const comprehensiveData = JSON.parse(fs.readFileSync(comprehensivePath, "utf-8"));

      // Format major stocks as earnings-related data
      const majorStocks = Object.values(comprehensiveData.major_stocks || {});

      return res.json({
        data: majorStocks,
        timestamp: comprehensiveData.timestamp,
        source: "fresh-earnings",
        message: "Fresh earnings data from major stocks",
        success: true
      });
    }

    return res.status(404).json({
      error: "Fresh data not available",
      success: false
    });
  } catch (error) {
    console.error("Fresh earnings error:", error.message);
    return res.status(500).json({
      error: "Failed to fetch fresh earnings",
      details: error.message,
      success: false
    });
  }
});

module.exports = router;

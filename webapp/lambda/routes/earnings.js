const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Root endpoint - returns reference/documentation only
router.get("/", (req, res) => {
  res.json({
    data: {
      endpoint: "earnings",
      description: "Earnings data API - financial metrics and estimates",
      available_routes: [
        {
          path: "/calendar",
          method: "GET",
          description: "Calendar view of earnings with reported status",
          query_params: ["period", "startDate", "endDate", "symbol", "limit"]
        },
        {
          path: "/info",
          method: "GET",
          description: "Combined earnings info - estimates, history, and surprises ranked by magnitude",
          query_params: ["symbol", "limit", "minSurprise"]
        }
      ]
    },
    success: true
  });
});

// ============================================================
// Named endpoints (must come BEFORE /:symbol route)
// ============================================================

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
        cp.short_name as company_name,
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

// GET /api/earnings/info - Combined earnings info (history + surprises)
router.get("/info", async (req, res) => {
  try {
    const { symbol, limit = 50 } = req.query;

    console.log(`\n📊 /api/earnings/info request:`);
    console.log(`   symbol: "${symbol}"`);
    console.log(`   limit: ${limit}`);

    // Fetch history
    let historyQuery = `
      SELECT
        eh.symbol,
        eh.quarter,
        eh.eps_actual,
        eh.eps_estimate,
        eh.eps_difference,
        eh.surprise_percent,
        eh.created_at,
        cp.short_name as company_name,
        cp.sector
      FROM earnings_history eh
      LEFT JOIN company_profile cp ON eh.symbol = cp.ticker
      WHERE 1=1
    `;
    const historyParams = [];

    if (symbol) {
      historyQuery += ` AND eh.symbol = $${historyParams.length + 1}`;
      historyParams.push(symbol.toUpperCase());
    }

    historyQuery += ` ORDER BY eh.symbol ASC, eh.quarter DESC LIMIT $${historyParams.length + 1}`;
    historyParams.push(Math.min(parseInt(limit) || 50, 500));

    console.log(`   History Query:`, historyQuery.replace(/\n/g, ' '));

    // Fetch surprises
    let surpriseQuery = `
      SELECT
        eh.symbol,
        eh.quarter as date,
        EXTRACT(QUARTER FROM eh.quarter) as quarter,
        EXTRACT(YEAR FROM eh.quarter) as year,
        eh.eps_actual,
        eh.eps_estimate,
        eh.surprise_percent,
        cp.short_name as company_name,
        cp.sector
      FROM earnings_history eh
      LEFT JOIN company_profile cp ON eh.symbol = cp.ticker
      WHERE eh.eps_actual IS NOT NULL
        AND eh.surprise_percent IS NOT NULL
        AND ABS(eh.surprise_percent) >= $1
    `;

    const surpriseParams = [parseFloat(req.query.minSurprise || 0)];

    if (symbol) {
      surpriseQuery += ` AND eh.symbol = $${surpriseParams.length + 1}`;
      surpriseParams.push(symbol.toUpperCase());
    }

    surpriseQuery += ` ORDER BY ABS(eh.surprise_percent) DESC LIMIT $${surpriseParams.length + 1}`;
    surpriseParams.push(Math.min(parseInt(limit) || 50, 500));

    console.log(`   Surprise Query:`, surpriseQuery.replace(/\n/g, ' '));

    const [historyResult, surpriseResult] = await Promise.all([
      query(historyQuery, historyParams),
      query(surpriseQuery, surpriseParams)
    ]);

    console.log(`   History returned: ${historyResult.rows.length}`);
    console.log(`   Surprises returned: ${surpriseResult.rows.length}`);

    // Format history
    const history = (historyResult.rows || []).map(row => ({
      symbol: row.symbol,
      company_name: row.company_name || row.symbol,
      sector: row.sector,
      quarter: row.quarter,
      eps_actual: row.eps_actual ? parseFloat(row.eps_actual) : null,
      eps_estimate: row.eps_estimate ? parseFloat(row.eps_estimate) : null,
      eps_difference: row.eps_difference ? parseFloat(row.eps_difference) : null,
      surprise_percent: row.surprise_percent ? parseFloat(row.surprise_percent) : null,
      fetched_at: row.created_at
    }));

    // Format surprises
    const surprises = (surpriseResult.rows || []).map(row => ({
      symbol: row.symbol,
      company_name: row.company_name || row.symbol,
      sector: row.sector,
      date: row.date,
      quarter: parseInt(row.quarter),
      year: parseInt(row.year),
      earnings: {
        actual: row.eps_actual ? parseFloat(row.eps_actual) : null,
        estimate: row.eps_estimate ? parseFloat(row.eps_estimate) : null,
        surprise_percent: row.surprise_percent ? parseFloat(row.surprise_percent) : null
      }
    }));

    res.json({
      data: {
        estimates: [],
        history,
        surprises
      },
      success: true
    });
  } catch (error) {
    console.error("Error fetching combined earnings data:", error);
    res.status(500).json({
      error: "Failed to fetch earnings data",
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

    // Get stocks with biggest estimate increases
    const risingQuery = `
      SELECT
        t.symbol,
        t.period,
        t.current_estimate,
        t.estimate_60d_ago,
        ROUND((t.current_estimate - t.estimate_60d_ago) / NULLIF(t.estimate_60d_ago, 0) * 100, 2) as pct_change,
        r.up_last_7d,
        r.down_last_7d,
        r.up_last_30d,
        r.down_last_30d,
        cp.short_name as company_name,
        cp.sector
      FROM earnings_estimate_trends t
      LEFT JOIN earnings_estimate_revisions r
        ON t.symbol = r.symbol AND t.period = r.period AND t.snapshot_date = r.snapshot_date
      LEFT JOIN company_profile cp ON t.symbol = cp.ticker
      WHERE t.estimate_60d_ago IS NOT NULL
        AND t.estimate_60d_ago != 0
        AND ABS(t.estimate_60d_ago) > 0.10
        AND t.current_estimate > t.estimate_60d_ago
        AND t.period = $1
      ORDER BY pct_change DESC
      LIMIT $2
    `;

    // Get stocks with biggest estimate decreases
    const fallingQuery = `
      SELECT
        t.symbol,
        t.period,
        t.current_estimate,
        t.estimate_60d_ago,
        ROUND((t.current_estimate - t.estimate_60d_ago) / NULLIF(t.estimate_60d_ago, 0) * 100, 2) as pct_change,
        r.up_last_7d,
        r.down_last_7d,
        r.up_last_30d,
        r.down_last_30d,
        cp.short_name as company_name,
        cp.sector
      FROM earnings_estimate_trends t
      LEFT JOIN earnings_estimate_revisions r
        ON t.symbol = r.symbol AND t.period = r.period AND t.snapshot_date = r.snapshot_date
      LEFT JOIN company_profile cp ON t.symbol = cp.ticker
      WHERE t.estimate_60d_ago IS NOT NULL
        AND t.estimate_60d_ago != 0
        AND ABS(t.estimate_60d_ago) > 0.10
        AND t.current_estimate < t.estimate_60d_ago
        AND t.period = $1
      ORDER BY pct_change ASC
      LIMIT $2
    `;

    let risingResult, fallingResult;
    try {
      [risingResult, fallingResult] = await Promise.all([
        query(risingQuery, [period, parseInt(limit)]),
        query(fallingQuery, [period, parseInt(limit)])
      ]);
    } catch (queryError) {
      // Earnings estimate trends table doesn't exist - return empty data
      console.log(`[INFO] Earnings estimate trends not available: ${queryError.message.substring(0, 100)}`);
      return res.json({
        data: { rising: [], falling: [], summary: { avg_rise: 0, avg_fall: 0, total_rising: 0, total_falling: 0 } },
        success: true
      });
    }

    const rising = risingResult.rows.map(row => ({
      symbol: row.symbol,
      company_name: row.company_name || row.symbol,
      sector: row.sector,
      period: row.period,
      current_estimate: parseFloat(row.current_estimate),
      estimate_60d_ago: parseFloat(row.estimate_60d_ago),
      pct_change: parseFloat(row.pct_change),
      up_last_7d: row.up_last_7d || 0,
      down_last_7d: row.down_last_7d || 0,
      up_last_30d: row.up_last_30d || 0,
      down_last_30d: row.down_last_30d || 0,
      net_revisions_7d: (row.up_last_7d || 0) - (row.down_last_7d || 0),
      net_revisions: (row.up_last_30d || 0) - (row.down_last_30d || 0)
    }));

    const falling = fallingResult.rows.map(row => ({
      symbol: row.symbol,
      company_name: row.company_name || row.symbol,
      sector: row.sector,
      period: row.period,
      current_estimate: parseFloat(row.current_estimate),
      estimate_60d_ago: parseFloat(row.estimate_60d_ago),
      pct_change: parseFloat(row.pct_change),
      up_last_7d: row.up_last_7d || 0,
      down_last_7d: row.down_last_7d || 0,
      up_last_30d: row.up_last_30d || 0,
      down_last_30d: row.down_last_30d || 0,
      net_revisions_7d: (row.up_last_7d || 0) - (row.down_last_7d || 0),
      net_revisions: (row.up_last_30d || 0) - (row.down_last_30d || 0)
    }));

    // Calculate averages, filtering out null values
    const validRising = rising.filter(s => s.pct_change !== null);
    const validFalling = falling.filter(s => s.pct_change !== null);

    const avgRise = validRising.length > 0 ? (validRising.reduce((sum, s) => sum + s.pct_change, 0) / validRising.length).toFixed(2) : 0;
    const avgFall = validFalling.length > 0 ? (validFalling.reduce((sum, s) => sum + s.pct_change, 0) / validFalling.length).toFixed(2) : 0;

    res.json({
      data: {
        rising,
        falling,
        summary: {
          total_rising: rising.length,
          total_falling: falling.length,
          avg_rise: parseFloat(avgRise),
          avg_fall: parseFloat(avgFall)
        }
      },
      success: true
    });
  } catch (error) {
    console.error("Error fetching estimate momentum:", error);
    res.status(500).json({
      error: "Failed to fetch estimate momentum",
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

    const comprehensivePath = "/tmp/comprehensive_market_data.json";

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

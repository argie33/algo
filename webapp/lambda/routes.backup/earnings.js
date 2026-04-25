const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");
const { getMarketDataPath } = require("../utils/market-data-path");
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

router.get("/", (req, res) => {
  return sendSuccess(res, {
    endpoint: "earnings",
    description: "Earnings data API - historical earnings and surprises",
    available_routes: [
      { path: "/info", method: "GET", params: ["symbol", "limit", "page"] },
      { path: "/data", method: "GET", params: ["symbol", "limit", "page"] },
      { path: "/calendar", method: "GET", params: ["period", "startDate", "endDate", "symbol"] }
    ]
  });
});

// ============================================================
// Named endpoints (must come BEFORE /:symbol route)
// ============================================================

router.get("/info", async (req, res) => {
  try {
    const { symbol, limit = 50 } = req.query;
    const limitNum = Math.min(parseInt(limit), 500);

    if (symbol) {
      const result = await query(
        "SELECT * FROM earnings_history WHERE symbol = $1 ORDER BY quarter DESC LIMIT $2",
        [symbol.toUpperCase(), limitNum]
      );
      return sendSuccess(res, { earnings: result.rows || [] });
    }

    const result = await query(
      `SELECT DISTINCT ON (symbol) symbol, quarter, eps_actual, eps_estimate
       FROM earnings_history ORDER BY symbol, quarter DESC LIMIT $1`,
      [limitNum]
    );
    return sendSuccess(res, { earnings: result.rows || [] });
  } catch (err) {
    return sendError(res, `Failed to fetch earnings: ${err.message}`, 500);
  }
});

router.get("/data", async (req, res) => {
  try {
    const { symbol, limit = 100, page = 1 } = req.query;
    const limitNum = Math.min(parseInt(limit), 500);
    const pageNum = Math.max(1, parseInt(page));
    const offset = (pageNum - 1) * limitNum;

    let sql = "SELECT * FROM earnings_history";
    let countSql = "SELECT COUNT(*) as count FROM earnings_history";
    const params = [];

    if (symbol) {
      sql += ` WHERE symbol = $1`;
      countSql += ` WHERE symbol = $1`;
      params.push(symbol.toUpperCase());
    }

    const countResult = await query(countSql, symbol ? [params[0]] : []);
    const total = countResult.rows[0]?.count || 0;

    const result = await query(
      sql + ` ORDER BY symbol, quarter DESC LIMIT $${params.length + 1} OFFSET $${params.length + 2}`,
      [...params, limitNum, offset]
    );

    return sendPaginated(res, result.rows || [], {
      limit: limitNum,
      offset,
      total,
      page: pageNum,
      totalPages: Math.ceil(total / limitNum)
    });
  } catch (err) {
    return sendError(res, `Failed to fetch earnings data: ${err.message}`, 500);
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

    return sendPaginated(res, calendar, {
      limit: limitNum,
      offset: 0,
      total: calendar.length,
      page: 1,
      totalPages: Math.ceil(calendar.length / limitNum)
    });
  } catch (error) {
    return sendError(res, `Failed to fetch earnings calendar: ${error.message}`, 500);
  }
});

router.get("/sp500-trend", async (req, res) => {
  try {
    const result = await query(
      `SELECT COUNT(DISTINCT symbol) as stock_count FROM earnings_history
       WHERE quarter::date >= (CURRENT_DATE - INTERVAL '3 months')::date`
    );
    return sendSuccess(res, {
      stocks_reporting: parseInt(result.rows[0]?.stock_count || 0),
      note: "Stocks with earnings reports in last 3 months"
    });
  } catch (error) {
    return sendError(res, `Failed to fetch earnings summary: ${error.message}`, 500);
  }
});

router.get("/estimate-momentum", async (req, res) => {
  return sendSuccess(res, {
    note: "Estimate momentum tracking requires earnings estimate revisions data (not currently available from yfinance)",
    suggestion: "Use earnings_history table to analyze actual earnings surprises instead"
  });
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

    return sendSuccess(res, {
      timeSeries: earningsGrowthTimeSeries,
      bestGrowth,
      worstGrowth,
      totalQuarters: earningsGrowthTimeSeries.length,
      totalSectors: sectorGrowthValues.length
    });
  } catch (error) {
    return sendError(res, `Failed to fetch sector trend: ${error.message}`, 500);
  }
});

router.get("/fresh-data", async (req, res) => {
  try {
    const fs = require("fs");
    const comprehensivePath = getMarketDataPath();

    if (fs.existsSync(comprehensivePath)) {
      const comprehensiveData = JSON.parse(fs.readFileSync(comprehensivePath, "utf-8"));
      const majorStocks = Object.values(comprehensiveData.major_stocks || {});
      return sendSuccess(res, { stocks: majorStocks, timestamp: comprehensiveData.timestamp });
    }

    return sendError(res, "Fresh data not available", 404);
  } catch (error) {
    return sendError(res, `Failed to fetch fresh earnings: ${error.message}`, 500);
  }
});

module.exports = router;

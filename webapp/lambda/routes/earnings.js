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
    const { period = "upcoming", startDate, endDate, symbol, limit = 100 } = req.query;

    // Determine date range based on period
    let dateCondition = "";
    const params = [];

    if (period === "past") {
      dateCondition = " AND ce.start_date <= CURRENT_DATE ";
    } else if (period === "upcoming") {
      dateCondition = " AND ce.start_date > CURRENT_DATE ";
    } else if (startDate || endDate) {
      if (startDate) {
        dateCondition += ` AND ce.start_date >= $${params.length + 1}`;
        params.push(startDate);
      }
      if (endDate) {
        dateCondition += ` AND ce.start_date <= $${params.length + 1}`;
        params.push(endDate);
      }
    }

    if (symbol) {
      dateCondition += ` AND ce.symbol = $${params.length + 1}`;
      params.push(symbol.toUpperCase());
    }

    const query_str = `
      SELECT DISTINCT ON (ce.symbol, ce.start_date)
        ce.symbol,
        ce.start_date as date,
        EXTRACT(QUARTER FROM ce.start_date) as quarter,
        EXTRACT(YEAR FROM ce.start_date) as year,
        ce.title,
        ce.fetched_at,
        cp.short_name as company_name,
        cp.sector
      FROM calendar_events ce
      LEFT JOIN company_profile cp ON ce.symbol = cp.ticker
      WHERE ce.event_type = 'earnings'
      ${dateCondition}
      ORDER BY ce.symbol ASC, ce.start_date DESC, ce.fetched_at DESC
      LIMIT $${params.length + 1}
    `;
    params.push(Math.min(parseInt(limit) || 100, 1000));

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

    const limitNum = Math.min(parseInt(limit) || 100, 1000);
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

// GET /api/earnings/info - Combined earnings info (estimates + history + surprises)
router.get("/info", async (req, res) => {
  try {
    const { symbol, limit = 50 } = req.query;

    console.log(`\n📊 /api/earnings/info request:`);
    console.log(`   symbol: "${symbol}"`);
    console.log(`   limit: ${limit}`);

    // Fetch estimates
    let estimateQuery = `
      SELECT
        ee.symbol,
        ee.period,
        ee.avg_estimate,
        ee.low_estimate,
        ee.high_estimate,
        ee.year_ago_eps,
        ee.growth,
        ee.number_of_analysts,
        cp.short_name as company_name,
        cp.sector
      FROM earnings_estimates ee
      LEFT JOIN company_profile cp ON ee.symbol = cp.ticker
      WHERE 1=1
    `;
    const estimateParams = [];

    if (symbol) {
      estimateQuery += ` AND ee.symbol = $${estimateParams.length + 1}`;
      estimateParams.push(symbol.toUpperCase());
    }

    estimateQuery += ` ORDER BY ee.symbol ASC, ee.period DESC LIMIT $${estimateParams.length + 1}`;
    estimateParams.push(Math.min(parseInt(limit) || 50, 500));

    console.log(`   Estimate Query (${estimateParams.length} params):`, estimateQuery.replace(/\n/g, ' '));
    console.log(`   Estimate Params:`, estimateParams);

    // Fetch history
    let historyQuery = `
      SELECT symbol, quarter, eps_actual, eps_estimate, eps_difference, surprise_percent, fetched_at FROM earnings_history
    `;
    const historyParams = [];

    if (symbol) {
      historyQuery += ` WHERE symbol = $${historyParams.length + 1}`;
      historyParams.push(symbol.toUpperCase());
    }

    historyQuery += ` ORDER BY quarter DESC LIMIT $${historyParams.length + 1}`;
    historyParams.push(Math.min(parseInt(limit) || 50, 500));

    console.log(`   History Query (${historyParams.length} params):`, historyQuery.replace(/\n/g, ' '));
    console.log(`   History Params:`, historyParams);

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

    console.log(`   Surprise Query (${surpriseParams.length} params):`, surpriseQuery.replace(/\n/g, ' '));
    console.log(`   Surprise Params:`, surpriseParams);

    const [estimatesResult, historyResult, surpriseResult] = await Promise.all([
      query(estimateQuery, estimateParams),
      query(historyQuery, historyParams),
      query(surpriseQuery, surpriseParams)
    ]);

    console.log(`   Estimates returned: ${estimatesResult.rows.length}`);
    console.log(`   History returned: ${historyResult.rows.length}`);
    console.log(`   Surprises returned: ${surpriseResult.rows.length}`);

    // Format estimates
    const estimates = (estimatesResult.rows || []).map(row => ({
      symbol: row.symbol,
      company_name: row.company_name || row.symbol,
      sector: row.sector,
      period: row.period,
      eps: {
        average_estimate: row.avg_estimate ? parseFloat(row.avg_estimate) : null,
        low_estimate: row.low_estimate ? parseFloat(row.low_estimate) : null,
        high_estimate: row.high_estimate ? parseFloat(row.high_estimate) : null,
        year_ago: row.year_ago_eps ? parseFloat(row.year_ago_eps) : null,
        growth_percent: row.growth ? parseFloat(row.growth) : null
      },
      number_of_analysts: row.number_of_analysts
    }));

    // Format history
    const history = (historyResult.rows || []).map(row => ({
      symbol: row.symbol,
      quarter: row.quarter,
      eps_actual: row.eps_actual ? parseFloat(row.eps_actual) : null,
      eps_estimate: row.eps_estimate ? parseFloat(row.eps_estimate) : null,
      eps_difference: row.eps_difference ? parseFloat(row.eps_difference) : null,
      surprise_percent: row.surprise_percent ? parseFloat(row.surprise_percent) : null,
      fetched_at: row.fetched_at
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
        estimates,
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
    const { years = 10 } = req.query;

    // Fetch S&P 500 EPS data (SP500_EPS - 12-month trailing earnings)
    const earningsQuery = `
      SELECT
        date,
        value as earnings_per_share
      FROM economic_data
      WHERE series_id = 'SP500_EPS'
        AND date >= CURRENT_DATE - INTERVAL '${parseInt(years)} years'
      ORDER BY date ASC
    `;

    const earningsResult = await query(earningsQuery);

    // Calculate trend metrics
    const earnings = earningsResult.rows;
    let trend = "neutral";
    let changePercent = 0;

    if (earnings.length >= 2) {
      const latest = parseFloat(earnings[earnings.length - 1].earnings_per_share);
      const yearAgo = earnings.find(row => {
        const date = new Date(row.date);
        const oneYearAgo = new Date();
        oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);
        return Math.abs(date - oneYearAgo) < 90 * 24 * 60 * 60 * 1000;
      });

      if (yearAgo) {
        const previous = parseFloat(yearAgo.earnings_per_share);
        changePercent = ((latest - previous) / previous) * 100;
        trend = changePercent > 5 ? "increasing" : changePercent < -5 ? "decreasing" : "neutral";
      }
    }

    // Format as timeSeries for chart
    const timeSeries = earnings.map(row => ({
      quarter: new Date(row.date).toLocaleDateString('en-US', { year: 'numeric', month: 'short' }),
      value: parseFloat(row.earnings_per_share),
      isForecast: false,
      stockCount: null
    }));

    const latestDate = earnings.length > 0 ? new Date(earnings[earnings.length - 1].date) : null;
    const isStale = latestDate && (new Date() - latestDate) > 90 * 24 * 60 * 60 * 1000; // Over 90 days old

    res.json({
      data: {
        timeSeries,
        summary: {
          trend,
          changePercent: changePercent.toFixed(2),
          latestEarnings: earnings.length > 0 ? parseFloat(earnings[earnings.length - 1].earnings_per_share) : null,
          latestDate: earnings.length > 0 ? earnings[earnings.length - 1].date : null,
          isStale: isStale,
          dataWarning: isStale ? "⚠️ Data is older than 90 days - please refresh economic data" : null
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

    // Query 2: Estimate Outlook (Forward-Looking Estimates by Sector)
    const estimateOutlookQuery = `
      WITH estimate_by_period AS (
        SELECT
          cp.sector,
          ee.period,
          COUNT(DISTINCT ee.symbol) as stock_count,
          AVG(ee.avg_estimate) as avg_estimate
        FROM earnings_estimates ee
        INNER JOIN company_profile cp ON ee.symbol = cp.ticker
        WHERE cp.sector IS NOT NULL
          AND ee.avg_estimate IS NOT NULL
        GROUP BY cp.sector, ee.period
        HAVING COUNT(DISTINCT ee.symbol) >= 2
      )
      SELECT
        sector,
        MAX(CASE WHEN period = '0q' THEN avg_estimate END) as current_quarter,
        MAX(CASE WHEN period = '+1q' THEN avg_estimate END) as next_quarter,
        MAX(CASE WHEN period = '0y' THEN avg_estimate END) as current_year,
        MAX(CASE WHEN period = '+1y' THEN avg_estimate END) as next_year,
        MAX(CASE WHEN period = '0q' THEN stock_count END) as stock_count,
        CASE
          WHEN MAX(CASE WHEN period = '0q' THEN avg_estimate END) IS NOT NULL
            AND MAX(CASE WHEN period = '+1q' THEN avg_estimate END) IS NOT NULL
          THEN ((MAX(CASE WHEN period = '+1q' THEN avg_estimate END) -
                 MAX(CASE WHEN period = '0q' THEN avg_estimate END)) /
                 NULLIF(MAX(CASE WHEN period = '0q' THEN avg_estimate END), 0) * 100)
          ELSE NULL
        END as qoq_change_pct,
        CASE
          WHEN MAX(CASE WHEN period = '0y' THEN avg_estimate END) IS NOT NULL
            AND MAX(CASE WHEN period = '+1y' THEN avg_estimate END) IS NOT NULL
          THEN ((MAX(CASE WHEN period = '+1y' THEN avg_estimate END) -
                 MAX(CASE WHEN period = '0y' THEN avg_estimate END)) /
                 NULLIF(MAX(CASE WHEN period = '0y' THEN avg_estimate END), 0) * 100)
          ELSE NULL
        END as yoy_change_pct
      FROM estimate_by_period
      GROUP BY sector
      ORDER BY sector
    `;

    const [growthResult, outlookResult] = await Promise.all([
      query(earningsGrowthQuery),
      query(estimateOutlookQuery)
    ]);

    // Transform earnings growth to time series format
    const timeSeriesMap = new Map();
    growthResult.rows.forEach(row => {
      if (!timeSeriesMap.has(row.quarter_label)) {
        timeSeriesMap.set(row.quarter_label, { quarter: row.quarter_label });
      }
      timeSeriesMap.get(row.quarter_label)[row.sector] = parseFloat(row.avg_eps);
    });

    const earningsGrowthTimeSeries = Array.from(timeSeriesMap.values());

    // Calculate growth summary (best/worst growth)
    const sectorGrowthStats = new Map();
    growthResult.rows.forEach(row => {
      if (!sectorGrowthStats.has(row.sector)) {
        sectorGrowthStats.set(row.sector, { totalEps: 0, count: 0, stockCount: 0 });
      }
      const stats = sectorGrowthStats.get(row.sector);
      stats.totalEps += parseFloat(row.avg_eps);
      stats.count += 1;
      stats.stockCount = row.stock_count;
    });

    const sectorGrowthValues = Array.from(sectorGrowthStats.entries()).map(([name, stats]) => ({
      name,
      growth: ((stats.totalEps / stats.count) / (stats.totalEps / stats.count - 0.5)) * 100 || 0,
      stockCount: stats.stockCount
    }));

    const bestGrowth = sectorGrowthValues.length > 0
      ? sectorGrowthValues.reduce((a, b) => a.growth > b.growth ? a : b)
      : { name: 'N/A', growth: 0, stockCount: 0 };

    const worstGrowth = sectorGrowthValues.length > 0
      ? sectorGrowthValues.reduce((a, b) => a.growth < b.growth ? a : b)
      : { name: 'N/A', growth: 0, stockCount: 0 };

    // Transform estimate outlook
    const estimateOutlookSectors = outlookResult.rows.map(row => ({
      name: row.sector,
      stockCount: row.stock_count || 0,
      currentQuarter: row.current_quarter ? parseFloat(row.current_quarter) : 0,
      nextQuarter: row.next_quarter ? parseFloat(row.next_quarter) : 0,
      currentYear: row.current_year ? parseFloat(row.current_year) : 0,
      nextYear: row.next_year ? parseFloat(row.next_year) : 0,
      qoqChange: row.qoq_change_pct ? parseFloat(row.qoq_change_pct) : 0,
      yoyChange: row.yoy_change_pct ? parseFloat(row.yoy_change_pct) : 0
    }));

    // Find most/least optimistic
    const mostOptimistic = estimateOutlookSectors.length > 0
      ? estimateOutlookSectors.reduce((a, b) => a.qoqChange > b.qoqChange ? a : b)
      : { name: 'N/A', change: 0 };

    const leastOptimistic = estimateOutlookSectors.length > 0
      ? estimateOutlookSectors.reduce((a, b) => a.qoqChange < b.qoqChange ? a : b)
      : { name: 'N/A', change: 0 };

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
          sectors: estimateOutlookSectors,
          summary: {
            mostOptimistic: { name: mostOptimistic.name, change: mostOptimistic.qoqChange },
            leastOptimistic: { name: leastOptimistic.name, change: leastOptimistic.qoqChange }
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

module.exports = router;

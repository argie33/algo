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
        value as earnings_per_share,
        series_id
      FROM economic_data
      WHERE series_id = 'SP500_EPS'
        AND date >= CURRENT_DATE - INTERVAL '${parseInt(years)} years'
      ORDER BY date ASC
    `;

    // Fetch S&P 500 price for P/E calculation
    const priceQuery = `
      SELECT
        date,
        value as price
      FROM economic_data
      WHERE series_id = 'SP500'
        AND date >= CURRENT_DATE - INTERVAL '${parseInt(years)} years'
      ORDER BY date ASC
    `;

    const [earningsResult, priceResult] = await Promise.all([
      query(earningsQuery),
      query(priceQuery)
    ]);

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
        return Math.abs(date - oneYearAgo) < 90 * 24 * 60 * 60 * 1000; // Within 90 days
      });

      if (yearAgo) {
        const previous = parseFloat(yearAgo.earnings_per_share);
        changePercent = ((latest - previous) / previous) * 100;
        trend = changePercent > 5 ? "increasing" : changePercent < -5 ? "decreasing" : "neutral";
      }
    }

    res.json({
      data: {
        earnings: earnings.map(row => ({
          date: row.date,
          value: parseFloat(row.earnings_per_share)
        })),
        price: priceResult.rows.map(row => ({
          date: row.date,
          value: parseFloat(row.price)
        })),
        summary: {
          trend,
          changePercent: changePercent.toFixed(2),
          latestEarnings: earnings.length > 0 ? parseFloat(earnings[earnings.length - 1].earnings_per_share) : null,
          latestDate: earnings.length > 0 ? earnings[earnings.length - 1].date : null
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

    const [risingResult, fallingResult] = await Promise.all([
      query(risingQuery, [period, parseInt(limit)]),
      query(fallingQuery, [period, parseInt(limit)])
    ]);

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

// GET /api/earnings/sector-trend - Average estimate change by sector over time
router.get("/sector-trend", async (req, res) => {
  try {
    const {
      period = '0q',
      timeRange = '90d',
      topSectors = 8,
      minStocks = 5
    } = req.query;

    // Convert timeRange to SQL interval (must be injected directly, not parameterized)
    const intervalMap = {
      '30d': '30 days',
      '60d': '60 days',
      '90d': '90 days',
      '180d': '180 days',
      '1y': '1 year'
    };
    const sqlInterval = intervalMap[timeRange] || '90 days';

    // Build query with interval injected (INTERVAL cannot be parameterized in PostgreSQL)
    const sectorTrendQuery = `
      WITH sector_estimates AS (
        -- Join earnings estimates with company sectors, calculate % change per stock
        SELECT
          t.snapshot_date,
          cp.sector,
          t.symbol,
          CASE
            WHEN t.estimate_60d_ago IS NOT NULL
              AND t.estimate_60d_ago != 0
              AND ABS(t.estimate_60d_ago) > 0.10
            THEN (t.current_estimate - t.estimate_60d_ago) / NULLIF(t.estimate_60d_ago, 0) * 100
            ELSE NULL
          END as pct_change
        FROM earnings_estimate_trends t
        INNER JOIN company_profile cp ON t.symbol = cp.ticker
        WHERE t.period = $1
          AND t.snapshot_date >= CURRENT_DATE - INTERVAL '${sqlInterval}'
          AND cp.sector IS NOT NULL
          AND t.estimate_60d_ago IS NOT NULL
          AND ABS(t.estimate_60d_ago) > 0.10
      ),
      sector_daily_avg AS (
        -- Average by sector and date, filter outliers
        SELECT
          snapshot_date,
          sector,
          COUNT(DISTINCT symbol) as stock_count,
          AVG(pct_change) as avg_change
        FROM sector_estimates
        WHERE pct_change IS NOT NULL
          AND ABS(pct_change) <= 200
        GROUP BY snapshot_date, sector
        HAVING COUNT(DISTINCT symbol) >= $2
      ),
      top_sectors AS (
        -- Get sectors with most data coverage
        SELECT sector
        FROM sector_daily_avg
        GROUP BY sector
        ORDER BY COUNT(*) DESC, AVG(stock_count) DESC
        LIMIT $3
      )
      SELECT
        sda.snapshot_date::TEXT as date,
        sda.sector,
        ROUND(sda.avg_change::numeric, 2) as avg_change,
        sda.stock_count
      FROM sector_daily_avg sda
      INNER JOIN top_sectors ts ON sda.sector = ts.sector
      ORDER BY sda.snapshot_date ASC, sda.sector ASC
    `;

    const result = await query(sectorTrendQuery, [
      period,
      parseInt(minStocks),
      parseInt(topSectors)
    ]);

    // Transform rows into time series format (pivot by date)
    const timeSeriesMap = new Map();
    const sectorStats = new Map();
    const dateRange = { start: null, end: null };

    result.rows.forEach(row => {
      const dateKey = row.date;

      if (!timeSeriesMap.has(dateKey)) {
        timeSeriesMap.set(dateKey, { date: dateKey });
      }

      timeSeriesMap.get(dateKey)[row.sector] = parseFloat(row.avg_change);

      // Track stats for summary and date range
      if (!sectorStats.has(row.sector)) {
        sectorStats.set(row.sector, {
          totalChange: 0,
          count: 0,
          totalStockCount: 0
        });
      }

      const stats = sectorStats.get(row.sector);
      stats.totalChange += parseFloat(row.avg_change);
      stats.count += 1;
      stats.totalStockCount += row.stock_count;

      // Update date range
      if (!dateRange.start || dateKey < dateRange.start) {
        dateRange.start = dateKey;
      }
      if (!dateRange.end || dateKey > dateRange.end) {
        dateRange.end = dateKey;
      }
    });

    // Convert map to array and sort by date
    const timeSeries = Array.from(timeSeriesMap.entries())
      .sort((a, b) => new Date(a[0]) - new Date(b[0]))
      .map(([, data]) => data);

    // Calculate sector statistics for summary
    const sectorAverages = Array.from(sectorStats.entries()).map(([name, stats]) => ({
      name,
      avgChange: parseFloat((stats.totalChange / stats.count).toFixed(2)),
      stockCount: Math.round(stats.totalStockCount / stats.count)
    }));

    // Find best and worst sectors
    const bestSector = sectorAverages.length > 0
      ? sectorAverages.reduce((max, s) => s.avgChange > max.avgChange ? s : max)
      : { name: 'N/A', avgChange: 0, stockCount: 0 };

    const worstSector = sectorAverages.length > 0
      ? sectorAverages.reduce((min, s) => s.avgChange < min.avgChange ? s : min)
      : { name: 'N/A', avgChange: 0, stockCount: 0 };

    res.json({
      data: {
        timeSeries,
        summary: {
          bestSector,
          worstSector,
          totalSectors: sectorStats.size,
          dateRange
        },
        metadata: {
          period,
          timeRange,
          minStocks,
          topSectors: Math.min(parseInt(topSectors), sectorStats.size)
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

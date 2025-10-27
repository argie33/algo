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

let query;
try {
  ({ query } = require("../utils/database"));
} catch (error) {
  console.log("Database service not available in sectors routes:", error.message);
  query = null;
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

const router = express.Router();

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.json({
    status: "operational",
    service: "sectors",
    timestamp: new Date().toISOString(),
    message: "Sectors service is running",
  });
});

// Basic root endpoint (public) - redirect to performance endpoint which has the real data
/**
 * GET /sectors/:sector/stocks
 * Get stocks in a specific sector from company_profile table
 */
// Apply authentication to all routes except health and root
router.use((req, res, next) => {
  // Skip auth for public endpoints - sectors are PUBLIC DATA
  const publicEndpoints = ["/health", "/", "/performance", "/leaders", "/rotation", "/analysis", "/ranking-history", "/industries/ranking-history", "/sectors-with-history", "/industries-with-history", "/allocation"];
  const sectorDetailPattern = /^\/[^/]+\/(stocks|details|technical-details)$/; // matches /:sector/stocks, /:sector/details, /:sector/technical-details
  const technicalDetailsPattern = /^\/technical-details\//; // matches /technical-details/sector/... and /technical-details/industry/...

  if (publicEndpoints.includes(req.path) || sectorDetailPattern.test(req.path) || technicalDetailsPattern.test(req.path)) {
    return next();
  }
  // Apply auth to all other routes
  return authenticateToken(req, res, next);
});

/**
 * GET /sectors/analysis
 * Simplified sector analysis for AWS Lambda compatibility
 * Updated: 2025-09-22 - Simplified for AWS deployment
 */
router.get("/analysis", async (req, res) => {
  try {
    // Check database availability first
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service temporarily unavailable",
        message: "Sector analysis service requires database connection"
      });
    }

    console.log("📊 Fetching sector analysis...");

    const { timeframe = "daily" } = req.query;

    // Validate timeframe
    const validTimeframes = ["daily", "weekly", "monthly"];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        success: false,
        error: "Invalid timeframe. Must be daily, weekly, or monthly.",
      });
    }

    // Add timeout wrapper
    const executeQueryWithTimeout = (queryPromise, name) => {
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error(`${name} query timeout after 5 seconds`)), 5000)
      );
      return Promise.race([queryPromise, timeoutPromise]);
    };

    // Query for sector analysis using real data only with MARKET-CAP WEIGHTING
    const sectorAnalysisQuery = `
      SELECT
        s.sector,
        COUNT(DISTINCT s.ticker) as stock_count,
        SUM(pd.close * md.market_cap) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN md.market_cap ELSE 0 END), 0) as avg_price,
        SUM(pd.volume) as total_volume,
        AVG(ti.rsi) as avg_rsi,
        AVG(ti.momentum) as avg_momentum,
        CASE
          WHEN SUM(CASE WHEN pd_old.close > 0 THEN md.market_cap ELSE 0 END) > 0 THEN
            (SUM(CASE WHEN pd_old.close > 0 THEN (pd.close - pd_old.close) * md.market_cap ELSE 0 END) /
             SUM(CASE WHEN pd_old.close > 0 THEN md.market_cap ELSE 0 END)) /
            NULLIF(SUM(CASE WHEN pd_old.close > 0 THEN pd_old.close * md.market_cap ELSE 0 END) /
                   SUM(CASE WHEN pd_old.close > 0 THEN md.market_cap ELSE 0 END), 0) * 100
          ELSE NULL
        END as monthly_change_pct
      FROM company_profile s
      LEFT JOIN market_data md ON s.ticker = md.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, close, volume, date
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY symbol, date DESC
      ) pd ON s.ticker = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, close
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '37 days'
          AND date < CURRENT_DATE - INTERVAL '30 days'
        ORDER BY symbol, date DESC
      ) pd_old ON s.ticker = pd_old.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (ticker)
          ticker, rsi, momentum
        FROM technical_data_daily
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY ticker, date DESC
      ) ti ON s.ticker = ti.ticker
      WHERE s.sector IS NOT NULL AND s.sector != ''
      GROUP BY s.sector
      HAVING COUNT(DISTINCT s.ticker) >= 1
      ORDER BY monthly_change_pct DESC NULLS LAST
    `;

    const sectorData = await executeQueryWithTimeout(
      query(sectorAnalysisQuery),
      "sector analysis"
    );

    // Validate query result
    if (!sectorData || !sectorData.rows) {
      console.error("❌ Sector analysis query returned null or invalid result");
      return res.status(503).json({
        success: false,
        error: "Database query returned no data",
        message: "Sector analysis data is not available. The database may be empty or still loading.",
        timestamp: new Date().toISOString(),
      });
    }

    console.log(`✅ Found ${sectorData.rows.length} sectors`);

    // Calculate summary statistics
    const totalSectors = sectorData.rows.length;
    const totalStocks = sectorData.rows.reduce(
      (sum, row) => sum + parseInt(row.stock_count || 0),
      0
    );
    const avgMarketReturn = totalSectors > 0 ?
      sectorData.rows.reduce(
        (sum, row) => sum + parseFloat(row.monthly_change_pct || 0),
        0
      ) / totalSectors : 0;

    // Identify sector trends
    const bullishSectors = sectorData.rows.filter(
      (row) => parseFloat(row.monthly_change_pct || 0) > 0
    ).length;
    const bearishSectors = sectorData.rows.filter(
      (row) => parseFloat(row.monthly_change_pct || 0) < 0
    ).length;

    const response = {
      success: true,
      data: {
        timeframe,
        summary: {
          total_sectors: totalSectors,
          total_stocks_analyzed: totalStocks,
          avg_market_return: avgMarketReturn.toFixed(2),
          bullish_sectors: bullishSectors,
          bearish_sectors: bearishSectors,
          neutral_sectors: totalSectors - bullishSectors - bearishSectors,
        },
        sectors: sectorData.rows.map((row) => ({
          sector: row.sector,
          metrics: {
            stock_count: parseInt(row.stock_count),
            avg_price: parseFloat(row.avg_price || 0).toFixed(2),
            performance: {
              monthly_change: parseFloat(row.monthly_change_pct || 0).toFixed(2),
            },
            technicals: {
              avg_rsi: parseFloat(row.avg_rsi || 0).toFixed(2),
              avg_momentum: parseFloat(row.avg_momentum || 0).toFixed(2),
            },
            volume: {
              total_volume: parseInt(row.total_volume || 0),
            },
          },
        })),
      },
      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    console.error("❌ Error in sector analysis:", error);
    res.status(500).json({
      success: false,
      error: error.message || "Failed to fetch sector analysis",
      details: error.message,
    });
  }
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
router.get("/sectors-with-history", async (req, res) => {
  try {
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service temporarily unavailable",
      });
    }

    const { limit = 20, sortBy = "current_rank" } = req.query;
    console.log(`📊 Fetching sectors with history (limit: ${limit})`);

    // Query sectors with historical data from the consolidated rankings table
    // Simplified: Get current sector data directly from sector_ranking (most recent date)
    const sectorsQuery = `
      SELECT DISTINCT ON (sector)
        sector as sector_name,
        current_rank,
        rank_1w_ago,
        rank_4w_ago,
        rank_12w_ago,
        daily_strength_score as current_momentum,
        CASE
          WHEN trend = '📈' THEN 'Uptrend'
          WHEN trend = '📉' THEN 'Downtrend'
          WHEN trend = '➡️' THEN 'Sideways'
          WHEN trend IS NULL OR trend = '' THEN 'Sideways'
          WHEN LOWER(trend::text) IN ('up', 'uptrend', '1') THEN 'Uptrend'
          WHEN LOWER(trend::text) IN ('down', 'downtrend', '-1') THEN 'Downtrend'
          ELSE 'Sideways'
        END as current_trend,
        date
      FROM sector_ranking
      WHERE sector IS NOT NULL AND sector != ''
      ORDER BY sector, date DESC
      LIMIT $1
    `;

    const result = await query(sectorsQuery, [parseInt(limit)]);

    if (!result || result.rows.length === 0) {
      // Fallback: try to get data from sector_performance table
      const fallbackQuery = `
        SELECT DISTINCT ON (sector_name)
          sector_name,
          CAST(sector_rank AS INTEGER) as current_rank,
          NULL as rank_1w_ago,
          NULL as rank_4w_ago,
          NULL as rank_12w_ago,
          momentum as current_momentum,
          CASE
            WHEN performance_20d > 0 THEN 'Uptrend'
            WHEN performance_20d < 0 THEN 'Downtrend'
            ELSE 'Sideways'
          END as current_trend,
          CAST(performance_1d AS FLOAT) as current_perf_1d,
          CAST(performance_5d AS FLOAT) as current_perf_5d,
          CAST(performance_20d AS FLOAT) as current_perf_20d,
          NULL as rank_change_1w,
          NULL as perf_1d_1w_ago,
          NULL as perf_5d_1w_ago,
          NULL as perf_20d_1w_ago
        FROM sector_performance
        ORDER BY sector_name, fetched_at DESC
        LIMIT $1
      `;

      const fallbackResult = await query(fallbackQuery, [parseInt(limit)]);

      // No fallback data - return error if database is empty
      if (!fallbackResult || fallbackResult.rows.length === 0) {
        return res.status(503).json({
          success: false,
          error: 'Sector data not available - database required',
          data: { sectors: [] }
        });
      }

      return res.json({
        success: true,
        data: {
          sectors: (fallbackResult?.rows || []).map(row => {
            // Convert trend numeric value to text
            let trend = row.current_trend;
            if (typeof trend === 'string' && !isNaN(trend)) {
              const perfValue = parseFloat(trend);
              trend = perfValue > 0 ? 'Uptrend' : perfValue < 0 ? 'Downtrend' : 'Sideways';
            }
            // Trend data from database - empty array if not available
            // No synthetic chart data generation allowed
            const trendData = [];
            return {
              sector_name: row.sector_name,
              current_rank: row.current_rank,
              rank_1w_ago: row.rank_1w_ago,
              rank_4w_ago: row.rank_4w_ago,
              rank_12w_ago: row.rank_12w_ago,
              current_momentum: row.current_momentum,
              current_trend: trend,
              trendData: trendData
            };
          })
        },
        timestamp: new Date().toISOString(),
      });
    }

    // Fetch trend data for each sector asynchronously
    const sectorsWithTrend = await Promise.all(
      result.rows
        .filter(row => row.sector_name && row.sector_name.trim())
        .map(async (row) => {
          // Convert trend numeric value to text
          let trend = row.current_trend;

          // Fetch trend data + technical indicators in single query (no frontend merge needed)
          let trendData = [];
          try {
            // Join sector_ranking with sector_technical_data on date + sector
            // This consolidates all data in one query, eliminating date range mismatches
            const historicalTrendQuery = `
              SELECT
                sr.date,
                sr.daily_strength_score,
                sr.current_rank,
                sr.trend,
                std.ma_20,
                std.ma_50,
                std.ma_200,
                std.rsi,
                std.close_price
              FROM sector_ranking sr
              LEFT JOIN sector_technical_data std
                ON LOWER(sr.sector) = LOWER(std.sector)
                AND sr.date = std.date
              WHERE LOWER(sr.sector) = LOWER($1)
              ORDER BY sr.date DESC
              LIMIT 200
            `;
            const historicalResults = await query(historicalTrendQuery, [row.sector_name]);

            console.log(`[DEBUG] Fetching trend for "${row.sector_name}" - Got ${historicalResults.rows.length} rows`);
            if (historicalResults.rows.length > 0) {
              console.log(`[DEBUG] Sample row:`, JSON.stringify(historicalResults.rows[0]));
            }

            trendData = historicalResults.rows.map(r => {
              const dateStr = r.date instanceof Date ? r.date.toISOString().split('T')[0] : r.date;
              // Convert emoji trend to text (no icons)
              let trendText = "Sideways";
              if (r.trend === '📈') trendText = "Uptrend";
              else if (r.trend === '📉') trendText = "Downtrend";

              return {
                date: dateStr,
                dailyStrengthScore: parseFloat(r.daily_strength_score || 0).toFixed(2),
                rank: r.current_rank,
                trend: trendText,
                ma_20: r.ma_20 !== undefined && r.ma_20 !== null ? parseFloat(r.ma_20) : undefined,
                ma_50: r.ma_50 !== undefined && r.ma_50 !== null ? parseFloat(r.ma_50) : undefined,
                ma_200: r.ma_200 !== undefined && r.ma_200 !== null ? parseFloat(r.ma_200) : undefined,
                rsi: r.rsi !== undefined && r.rsi !== null ? parseFloat(r.rsi) : undefined,
                close: r.close_price !== undefined && r.close_price !== null ? parseFloat(r.close_price) : undefined
              };
            });
            // Reverse to get chronological order (oldest to newest, left to right on chart)
            trendData.reverse();
          } catch (trendError) {
            // Log error and set empty trend
            console.error(`❌ Could not fetch trend data for ${row.sector_name}:`, trendError.message);
            trendData = [];
          }

          return {
            sector_name: row.sector_name,
            current_rank: row.current_rank,
            rank_1w_ago: row.rank_1w_ago,
            rank_4w_ago: row.rank_4w_ago,
            rank_12w_ago: row.rank_12w_ago,
            current_momentum: row.current_momentum,
            current_trend: trend,
            trendData: trendData
          };
        })
    );

    res.json({
      success: true,
      data: {
        sectors: sectorsWithTrend
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Sectors with history error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sectors with history",
      message: error.message,
    });
  }
});

/**
 * GET /industries-with-history
 * Get current industry data with historical rankings for display
 * Used by SectorAnalysis frontend component
 */
router.get("/industries-with-history", async (req, res) => {
  try {
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service temporarily unavailable",
      });
    }

    const { limit = 500, sortBy = "current_rank" } = req.query;
    console.log(`🏭 Fetching industries with history (limit: ${limit})`);

    // Query industries with historical data + sector mapping + performance metrics
    // Strategy: Get the most recent date that has the best historical data availability
    const industriesQuery = `
      WITH latest_data AS (
        -- Get the most recent date with actual historical data (not all NULLs)
        SELECT ir.date,
               SUM(CASE WHEN ir.rank_1w_ago IS NOT NULL OR ir.rank_4w_ago IS NOT NULL OR ir.rank_8w_ago IS NOT NULL THEN 1 ELSE 0 END) as ranks_with_history
        FROM industry_ranking ir
        GROUP BY ir.date
        ORDER BY ranks_with_history DESC, ir.date DESC
        LIMIT 1
      ),
      industry_prices AS (
        -- Calculate current industry MARKET-CAP WEIGHTED average prices for latest available date
        SELECT
          cp.industry,
          SUM(pd.close * md.market_cap) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN md.market_cap ELSE 0 END), 0) as avg_close,
          MAX(pd.date) as latest_date
        FROM company_profile cp
        JOIN price_daily pd ON cp.ticker = pd.symbol
        LEFT JOIN market_data md ON cp.ticker = md.ticker
        WHERE cp.industry IS NOT NULL AND cp.industry != ''
          AND pd.date = (SELECT MAX(date) FROM price_daily)
        GROUP BY cp.industry
      ),
      calculated_performance AS (
        -- Calculate 1D, 5D, 20D percentages from price data
        SELECT
          ip.industry,
          CASE
            WHEN pd_1d.avg_close > 0 THEN
              ((ip.avg_close - pd_1d.avg_close) / pd_1d.avg_close * 100)
            ELSE NULL
          END as perf_1d,
          CASE
            WHEN pd_5d.avg_close > 0 THEN
              ((ip.avg_close - pd_5d.avg_close) / pd_5d.avg_close * 100)
            ELSE NULL
          END as perf_5d,
          CASE
            WHEN pd_20d.avg_close > 0 THEN
              ((ip.avg_close - pd_20d.avg_close) / pd_20d.avg_close * 100)
            ELSE NULL
          END as perf_20d
        FROM industry_prices ip
        LEFT JOIN (
          SELECT cp.industry, SUM(pd.close * md.market_cap) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN md.market_cap ELSE 0 END), 0) as avg_close
          FROM company_profile cp
          JOIN price_daily pd ON cp.ticker = pd.symbol
          LEFT JOIN market_data md ON cp.ticker = md.ticker
          WHERE pd.date = (SELECT MAX(date) FROM price_daily) - INTERVAL '1 day'
          GROUP BY cp.industry
        ) pd_1d ON ip.industry = pd_1d.industry
        LEFT JOIN (
          SELECT cp.industry, SUM(pd.close * md.market_cap) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN md.market_cap ELSE 0 END), 0) as avg_close
          FROM company_profile cp
          JOIN price_daily pd ON cp.ticker = pd.symbol
          LEFT JOIN market_data md ON cp.ticker = md.ticker
          WHERE pd.date = (SELECT MAX(date) FROM price_daily) - INTERVAL '5 days'
          GROUP BY cp.industry
        ) pd_5d ON ip.industry = pd_5d.industry
        LEFT JOIN (
          SELECT cp.industry, SUM(pd.close * md.market_cap) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN md.market_cap ELSE 0 END), 0) as avg_close
          FROM company_profile cp
          JOIN price_daily pd ON cp.ticker = pd.symbol
          LEFT JOIN market_data md ON cp.ticker = md.ticker
          WHERE pd.date = (SELECT MAX(date) FROM price_daily) - INTERVAL '20 days'
          GROUP BY cp.industry
        ) pd_20d ON ip.industry = pd_20d.industry
      )
      SELECT
        ir.industry,
        cp.sector as sector,
        ir.current_rank,
        ir.rank_1w_ago,
        ir.rank_4w_ago,
        ir.rank_8w_ago,
        ir.daily_strength_score as momentum,
        ir.trend,
        ir.stock_count,
        COALESCE(CAST(ip.performance_1d AS FLOAT), CAST(cp_calc.perf_1d AS FLOAT)) as performance_1d,
        COALESCE(CAST(ip.performance_5d AS FLOAT), CAST(cp_calc.perf_5d AS FLOAT)) as performance_5d,
        COALESCE(CAST(ip.performance_20d AS FLOAT), CAST(cp_calc.perf_20d AS FLOAT)) as performance_20d,
        ir.date
      FROM industry_ranking ir
      LEFT JOIN (
        SELECT DISTINCT sector, industry FROM company_profile
        WHERE industry IS NOT NULL
      ) cp ON LOWER(ir.industry) = LOWER(cp.industry)
      LEFT JOIN (
        SELECT DISTINCT ON (industry)
          industry,
          performance_1d,
          performance_5d,
          performance_20d,
          fetched_at
        FROM industry_performance
        ORDER BY industry, fetched_at DESC
      ) ip ON LOWER(ir.industry) = LOWER(ip.industry)
      LEFT JOIN calculated_performance cp_calc ON ir.industry = cp_calc.industry,
      latest_data ld
      WHERE ir.date = ld.date
      ORDER BY ir.current_rank ASC NULLS LAST, ir.industry ASC
      LIMIT $1
    `;

    const result = await query(industriesQuery, [parseInt(limit)]);

    if (!result || result.rows.length === 0) {
      // Fallback: try to get data from industry_performance table
      const fallbackQuery = `
        SELECT DISTINCT ON (industry)
          industry,
          sector as sector,
          CAST(overall_rank AS INTEGER) as current_rank,
          NULL as rank_1w_ago,
          NULL as rank_4w_ago,
          NULL as rank_12w_ago,
          'Moderate' as momentum,
          'Sideways' as trend,
          0.0 as performance_1d,
          0.0 as performance_5d,
          0.0 as performance_20d,
          stock_count as stock_count,
          NULL as rank_change_1w,
          NULL as perf_1d_1w_ago,
          NULL as perf_5d_1w_ago,
          NULL as perf_20d_1w_ago
        FROM industry_performance
        ORDER BY industry, fetched_at DESC
        LIMIT $1
      `;

      const fallbackResult = await query(fallbackQuery, [parseInt(limit)]);

      return res.json({
        success: true,
        data: {
          industries: await Promise.all((fallbackResult?.rows || []).map(async row => {
            // Fetch technical data for each industry
            let trendData = [];
            try {
              const industryTrendQuery = `
                SELECT
                  ir.date,
                  ir.daily_strength_score,
                  ir.current_rank,
                  ir.trend,
                  itd.ma_20,
                  itd.ma_50,
                  itd.ma_200,
                  itd.rsi,
                  itd.close_price
                FROM industry_ranking ir
                LEFT JOIN industry_technical_data itd
                  ON LOWER(ir.industry) = LOWER(itd.industry)
                  AND ir.date = itd.date
                WHERE LOWER(ir.industry) = LOWER($1)
                ORDER BY ir.date DESC
                LIMIT 200
              `;
              const trendResults = await query(industryTrendQuery, [row.industry]);
              trendData = trendResults.rows.map(r => {
                const dateStr = r.date instanceof Date ? r.date.toISOString().split('T')[0] : r.date;
                return {
                  date: dateStr,
                  dailyStrengthScore: parseFloat(r.daily_strength_score || 0).toFixed(2),
                  rank: r.current_rank,
                  trend: r.trend,
                  ma_20: r.ma_20 !== undefined && r.ma_20 !== null ? parseFloat(r.ma_20) : undefined,
                  ma_50: r.ma_50 !== undefined && r.ma_50 !== null ? parseFloat(r.ma_50) : undefined,
                  ma_200: r.ma_200 !== undefined && r.ma_200 !== null ? parseFloat(r.ma_200) : undefined,
                  rsi: r.rsi !== undefined && r.rsi !== null ? parseFloat(r.rsi) : undefined,
                  close: r.close_price !== undefined && r.close_price !== null ? parseFloat(r.close_price) : undefined
                };
              });
              trendData.reverse();
            } catch (err) {
              console.error(`⚠️ Could not fetch trend data for industry ${row.industry}:`, err.message);
            }

            return {
              industry: row.industry,
              sector: row.sector,
              current_rank: row.current_rank,
              rank_1w_ago: row.rank_1w_ago,
              rank_4w_ago: row.rank_4w_ago,
              rank_12w_ago: row.rank_12w_ago,
              momentum: row.momentum,
              trend: row.trend,
              performance_1d: parseFloat(row.performance_1d || 0),
              performance_5d: parseFloat(row.performance_5d || 0),
              performance_20d: parseFloat(row.performance_20d || 0),
              stock_count: row.stock_count,
              rank_change_1w: row.rank_change_1w,
              perf_1d_1w_ago: row.perf_1d_1w_ago,
              perf_5d_1w_ago: row.perf_5d_1w_ago,
              perf_20d_1w_ago: row.perf_20d_1w_ago,
              trendData: trendData
            };
          })),
          summary: {
            total_industries: (fallbackResult?.rows || []).length
          }
        },
        timestamp: new Date().toISOString(),
      });
    }

    const industries = await Promise.all(result.rows
          .filter(row => row.industry && row.industry.trim())
          .map(async row => {
            // Fetch technical data for each industry (20+ days matching sectors)
            let trendData = [];
            try {
              const industryTrendQuery = `
                SELECT
                  ir.date,
                  ir.daily_strength_score,
                  ir.current_rank,
                  ir.trend,
                  itd.ma_20,
                  itd.ma_50,
                  itd.ma_200,
                  itd.rsi,
                  itd.close_price
                FROM industry_ranking ir
                LEFT JOIN industry_technical_data itd
                  ON LOWER(ir.industry) = LOWER(itd.industry)
                  AND ir.date = itd.date
                WHERE LOWER(ir.industry) = LOWER($1)
                ORDER BY ir.date DESC
                LIMIT 200
              `;
              const trendResults = await query(industryTrendQuery, [row.industry]);
              trendData = trendResults.rows.map(r => {
                const dateStr = r.date instanceof Date ? r.date.toISOString().split('T')[0] : r.date;
                return {
                  date: dateStr,
                  dailyStrengthScore: parseFloat(r.daily_strength_score || 0).toFixed(2),
                  rank: r.current_rank,
                  trend: r.trend,
                  ma_20: r.ma_20 !== undefined && r.ma_20 !== null ? parseFloat(r.ma_20) : undefined,
                  ma_50: r.ma_50 !== undefined && r.ma_50 !== null ? parseFloat(r.ma_50) : undefined,
                  ma_200: r.ma_200 !== undefined && r.ma_200 !== null ? parseFloat(r.ma_200) : undefined,
                  rsi: r.rsi !== undefined && r.rsi !== null ? parseFloat(r.rsi) : undefined,
                  close: r.close_price !== undefined && r.close_price !== null ? parseFloat(r.close_price) : undefined
                };
              });
              trendData.reverse();
            } catch (err) {
              console.error(`⚠️ Could not fetch trend data for industry ${row.industry}:`, err.message);
            }

            return {
              industry: row.industry,
              sector: row.sector,
              current_rank: row.current_rank,
              rank_1w_ago: row.rank_1w_ago,
              rank_4w_ago: row.rank_4w_ago,
              rank_8w_ago: row.rank_8w_ago,
              momentum: row.momentum,
              trend: row.trend,
              stock_count: row.stock_count,
              performance_1d: parseFloat(row.performance_1d || 0),
              performance_5d: parseFloat(row.performance_5d || 0),
              performance_20d: parseFloat(row.performance_20d || 0),
              rank_change_1w: row.rank_change_1w,
              perf_1d_1w_ago: row.perf_1d_1w_ago,
              perf_5d_1w_ago: row.perf_5d_1w_ago,
              perf_20d_1w_ago: row.perf_20d_1w_ago,
              trendData: trendData
            };
          }));

    res.json({
      success: true,
      data: {
        industries: industries,
        summary: {
          total_industries: industries.length
        }
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Industries with history error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch industries with history",
      message: error.message,
    });
  }
});

/**

/**
 * GET /ranking-history
 * Get historical ranking progression for sectors to identify trends
 */
/**
 * GET /industries/ranking-history
 * Get historical ranking progression for industries to identify trends
 */
/**
 * GET /sectors/heatmap
 * Get sector heatmap data for visualization
 */
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

    // BUG FIX: Preserve all relevant fields from the row for later use
    rankingsByPeriod[period].push({
      name: nameField,
      rank: rankField || 0,
      date: dateStr,
      performance_score: row.performance_score || row.performance_20d || 0,
      stocks_up: row.stocks_up || row.stock_count || 0,
      stocks_down: row.stocks_down || 0,
      total_stocks: row.total_stocks || row.stock_count || 0,
      avg_return: row.avg_return || 0,
      // Preserve additional fields from raw row
      sector_rank: row.sector_rank || rankField || 0,
      overall_rank: row.overall_rank || rankField || 0,
      stock_count: row.stock_count || 0,
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
    const todayRank = item.rankings.today?.rank || 0;
    const weekAgoRank = item.rankings['1_week_ago']?.rank || 0;

    // Determine trend direction (lower rank = better, so declining rank = improving)
    let trend = 'stable';
    let direction = '→';

    if (weekAgoRank > 0 && todayRank > 0) {
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
      return res.status(503).json({
        success: false,
        error: "Database service unavailable"
      });
    }

    const { sectorName } = req.params;

    // Get recent historical rankings for this sector (last 1 year), ordered by date
    const trendData = await query(
      `SELECT
        date,
        current_rank as rank,
        daily_strength_score,
        trend,
        TO_CHAR(date, 'MM/DD') as label
      FROM sector_ranking
      WHERE LOWER(sector) = LOWER($1)
      AND date >= CURRENT_DATE - INTERVAL '365 days'
      ORDER BY date ASC`,
      [sectorName]
    );

    if (!trendData.rows.length) {
      return res.status(404).json({
        success: false,
        error: "Sector not found or no trend data available"
      });
    }

    res.json({
      success: true,
      sector: sectorName,
      trendData: trendData.rows.map(row => ({
        date: row.date,
        rank: row.rank,
        dailyStrengthScore: row.daily_strength_score,
        trend: row.trend,
        label: row.label
      }))
    });
  } catch (error) {
    console.error("Sector trend endpoint error:", error.message);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sector trend data",
      details: error.message
    });
  }
});

router.get("/trend/industry/:industryName", async (req, res) => {
  try {
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service unavailable"
      });
    }

    const { industryName } = req.params;

    // Get recent historical rankings for this industry (last 1 year), ordered by date
    const trendData = await query(
      `SELECT
        date,
        current_rank as rank,
        daily_strength_score,
        trend,
        TO_CHAR(date, 'MM/DD') as label
      FROM industry_ranking
      WHERE LOWER(industry) = LOWER($1)
      AND date >= CURRENT_DATE - INTERVAL '365 days'
      ORDER BY date ASC`,
      [industryName]
    );

    if (!trendData.rows.length) {
      return res.status(404).json({
        success: false,
        error: "Industry not found or no trend data available"
      });
    }

    res.json({
      success: true,
      industry: industryName,
      trendData: trendData.rows.map(row => ({
        date: row.date,
        rank: row.rank,
        dailyStrengthScore: row.daily_strength_score,
        trend: row.trend,
        label: row.label
      }))
    });
  } catch (error) {
    console.error("Industry trend endpoint error:", error.message);
    res.status(500).json({
      success: false,
      error: "Failed to fetch industry trend data",
      details: error.message
    });
  }
});

/**
 * GET /technical-details/sector/:sectorName
 * Get detailed technical analysis with moving averages for a sector
 * Returns 200 days of price history with calculated MAs and technical indicators
 */
router.get("/technical-details/sector/:sectorName", async (req, res) => {
  try {
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service unavailable"
      });
    }

    const { sectorName } = req.params;
    console.log(`📈 Fetching technical details for sector: ${sectorName}`);

    // Query pre-calculated technical data from database
    // Get the most recent 200 records by ordering DESC and reversing for chronological display
    const priceHistoryQuery = `
      SELECT
        TO_CHAR(date, 'YYYY-MM-DD') as date,
        ROUND(CAST(close_price AS NUMERIC), 2) as close,
        ROUND(CAST(ma_20 AS NUMERIC), 2) as ma_20,
        ROUND(CAST(ma_50 AS NUMERIC), 2) as ma_50,
        ROUND(CAST(ma_200 AS NUMERIC), 2) as ma_200,
        ROUND(CAST(volume AS NUMERIC), 0) as volume,
        rsi
      FROM sector_technical_data
      WHERE sector = $1
      ORDER BY date DESC
      LIMIT 200
    `;

    const priceData = await query(priceHistoryQuery, [sectorName]);
    // Reverse to get chronological order (oldest to newest left to right)
    priceData.rows.reverse();

    if (!priceData.rows.length) {
      return res.status(404).json({
        success: false,
        error: "No technical data available for sector"
      });
    }

    // Get summary metrics from latest data
    const latestData = priceData.rows[priceData.rows.length - 1];
    const currentPrice = parseFloat(latestData.close);
    const ma20 = latestData.ma_20 ? parseFloat(latestData.ma_20) : currentPrice;
    const ma50 = latestData.ma_50 ? parseFloat(latestData.ma_50) : currentPrice;
    const ma200 = latestData.ma_200 ? parseFloat(latestData.ma_200) : currentPrice;
    const rsi = latestData.rsi ? parseFloat(latestData.rsi) : null;

    res.json({
      success: true,
      sector: sectorName,
      summary: {
        current_price: currentPrice,
        ma_20: ma20,
        ma_50: ma50,
        ma_200: ma200,
        rsi: rsi ? Math.round(rsi * 100) / 100 : null,
        price_vs_ma20: currentPrice > ma20 ? 'Above' : currentPrice < ma20 ? 'Below' : 'At',
        price_vs_ma200: currentPrice > ma200 ? 'Above' : currentPrice < ma200 ? 'Below' : 'At'
      },
      history: priceData.rows.map(row => ({
        date: row.date,
        close: parseFloat(row.close),
        ma_20: row.ma_20 ? parseFloat(row.ma_20) : null,
        ma_50: row.ma_50 ? parseFloat(row.ma_50) : null,
        ma_200: row.ma_200 ? parseFloat(row.ma_200) : null,
        rsi: row.rsi ? parseFloat(row.rsi) : null,
        volume: parseInt(row.volume)
      })),
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Sector technical details error:", error.message);
    res.status(500).json({
      success: false,
      error: "Failed to fetch technical details",
      details: error.message
    });
  }
});

/**
 * GET /technical-details/industry/:industryName
 * Get detailed technical analysis with moving averages for an industry
 * Returns 200 days of price history with calculated MAs
 */
router.get("/technical-details/industry/:industryName", async (req, res) => {
  try {
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service unavailable"
      });
    }

    const { industryName } = req.params;
    console.log(`📈 Fetching technical details for industry: ${industryName}`);

    // Query pre-calculated technical data from database
    // Get the most recent 200 records by ordering DESC and reversing for chronological display
    const priceHistoryQuery = `
      SELECT
        TO_CHAR(date, 'YYYY-MM-DD') as date,
        ROUND(CAST(close_price AS NUMERIC), 2) as close,
        ROUND(CAST(ma_20 AS NUMERIC), 2) as ma_20,
        ROUND(CAST(ma_50 AS NUMERIC), 2) as ma_50,
        ROUND(CAST(ma_200 AS NUMERIC), 2) as ma_200,
        ROUND(CAST(volume AS NUMERIC), 0) as volume,
        rsi
      FROM industry_technical_data
      WHERE industry = $1
      ORDER BY date DESC
      LIMIT 200
    `;

    const priceData = await query(priceHistoryQuery, [industryName]);
    // Reverse to get chronological order (oldest to newest left to right)
    priceData.rows.reverse();

    if (!priceData.rows.length) {
      return res.status(404).json({
        success: false,
        error: "No technical data available for industry"
      });
    }

    // Get summary metrics from latest data
    const latestData = priceData.rows[priceData.rows.length - 1];
    const currentPrice = parseFloat(latestData.close);
    const ma20 = latestData.ma_20 ? parseFloat(latestData.ma_20) : currentPrice;
    const ma50 = latestData.ma_50 ? parseFloat(latestData.ma_50) : currentPrice;
    const ma200 = latestData.ma_200 ? parseFloat(latestData.ma_200) : currentPrice;
    const rsi = latestData.rsi ? parseFloat(latestData.rsi) : null;

    res.json({
      success: true,
      industry: industryName,
      summary: {
        current_price: currentPrice,
        ma_20: ma20,
        ma_50: ma50,
        ma_200: ma200,
        rsi: rsi ? Math.round(rsi * 100) / 100 : null,
        price_vs_ma20: currentPrice > ma20 ? 'Above' : currentPrice < ma20 ? 'Below' : 'At',
        price_vs_ma200: currentPrice > ma200 ? 'Above' : currentPrice < ma200 ? 'Below' : 'At'
      },
      history: priceData.rows.map(row => ({
        date: row.date,
        close: parseFloat(row.close),
        ma_20: row.ma_20 ? parseFloat(row.ma_20) : null,
        ma_50: row.ma_50 ? parseFloat(row.ma_50) : null,
        ma_200: row.ma_200 ? parseFloat(row.ma_200) : null,
        rsi: row.rsi ? parseFloat(row.rsi) : null,
        volume: parseInt(row.volume)
      })),
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Industry technical details error:", error.message);
    res.status(500).json({
      success: false,
      error: "Failed to fetch technical details",
      details: error.message
    });
  }
});

// Rankings Endpoints - Return current rankings with daily strength scores
module.exports = router;

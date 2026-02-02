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
    // Check database availability first - FAIL HARD if unavailable
    const dbError = checkDatabaseAvailable(res);
    if (dbError) return dbError;

    const { limit = 20, sortBy = "current_rank" } = req.query;
    console.log(`📊 Fetching sectors with history (limit: ${limit})`);

    // Get latest sector rankings from sector_ranking table with P/E metrics
    // Data integrity: Return NULL for performance data when not available (not fake 0 values)
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
        COALESCE(sp.date, sr.date_recorded) as last_updated,
        pe.trailing_pe,
        pe.forward_pe,
        pe.pe_min,
        pe.pe_p25,
        pe.pe_median,
        pe.pe_p75,
        pe.pe_p90,
        pe.pe_max
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
      LEFT JOIN (
        SELECT
          cp.sector,
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
        WHERE cp.sector IS NOT NULL
          AND TRIM(cp.sector) != ''
          AND cp.quote_type = 'EQUITY'
          AND cp.ticker NOT LIKE '%$%'
        GROUP BY cp.sector
      ) pe ON sr.sector_name = pe.sector
      LIMIT $1
    `;

    const result = await query(sectorsQuery, [parseInt(limit)]);

    console.log(`✅ Sectors query returned: ${result?.rows?.length || 0} rows`);

    // Return sector data immediately - no async operations needed
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

    // Return sectors data - standardized format per RULES.md
    // List endpoints use {items, pagination, success}
    const total = sectors.length;
    const limitNum = Math.min(parseInt(limit, 10) || 500, 1000);
    const pageNum = 1;
    const totalPages = Math.ceil(total / limitNum);
    const hasNext = false;
    const hasPrev = false;

    return res.json({
      items: sectors,
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
    console.error('❌ Error in /api/sectors/sectors:', error.message);
    return res.status(500).json({
      error: "Request failed",
      success: false
    });
  }
});

// ============================================================
// COMMENTED OUT: Old complex trend fetching code that was causing hangs
// ============================================================
/*
    const historicalTrendQuery = `
              SELECT
                sr.date,
                sr.daily_strength_score,
                sr.current_rank,
                sr.trend
              FROM sector_ranking sr
              WHERE LOWER(sr.sector) = LOWER($1)
              ORDER BY sr.date DESC
              LIMIT 200
            `;
            const historicalResults = await query(historicalTrendQuery, [row.sector_name]);

            console.log(`[DEBUG] Fetching trend for "${row.sector_name}" - Got ${historicalResults.rows.length} rows`);
            if (historicalResults.rows.length > 0) {
              console.log(`[DEBUG] Sample row:`, JSON.stringify(historicalResults.rows[0]));
            }

            // Calculate SMA and RSI based on daily_strength_score
            trendData = historicalResults.rows.map((r, idx, arr) => {
              const dateStr = r.date instanceof Date ? r.date.toISOString().split('T')[0] : r.date;
              const dss = safeFloat(r.daily_strength_score);

              // Calculate MA_5 (average of last 5 values) - only when we have 5+ points
              let ma_5 = undefined;
              if (idx >= 4) {
                const ma5Values = arr.slice(idx - 4, idx + 1).map(x => safeFloat(x.daily_strength_score));
                ma_5 = ma5Values.reduce((a, b) => a + b, 0) / ma5Values.length;
              }

              // Calculate MA_10 (average of last 10 values) - only when we have 10+ points
              let ma_10 = undefined;
              if (idx >= 9) {
                const ma10Values = arr.slice(idx - 9, idx + 1).map(x => safeFloat(x.daily_strength_score));
                ma_10 = ma10Values.reduce((a, b) => a + b, 0) / ma10Values.length;
              }

              // Calculate MA_20 (average of last 20 values) - only when we have 20+ points
              let ma_20 = undefined;
              if (idx >= 19) {
                const ma20Values = arr.slice(idx - 19, idx + 1).map(x => safeFloat(x.daily_strength_score));
                ma_20 = ma20Values.reduce((a, b) => a + b, 0) / ma20Values.length;
              }

              // Calculate RSI(14) based on daily_strength_score
              let rsi = undefined;
              const rsiPeriod = 14;
              if (idx >= rsiPeriod - 1) {
                const rsiValues = arr.slice(idx - rsiPeriod + 1, idx + 1).map(x => safeFloat(x.daily_strength_score));
                let gains = 0, losses = 0;
                for (let i = 1; i < rsiValues.length; i++) {
                  const diff = rsiValues[i] - rsiValues[i - 1];
                  if (diff > 0) gains += diff;
                  else losses += Math.abs(diff);
                }
                const avgGain = gains / rsiPeriod;
                const avgLoss = losses / rsiPeriod;
                const rs = avgLoss !== 0 ? avgGain / avgLoss : avgGain > 0 ? 100 : 0;
                rsi = 100 - (100 / (1 + rs));
              }

              // Convert emoji trend to text
              let trendText = "Sideways";
              if (r.trend === '📈') trendText = "Uptrend";
              else if (r.trend === '📉') trendText = "Downtrend";

              return {
                date: dateStr,
                dailyStrengthScore: safeFloat(r.daily_strength_score).toFixed(2),
                rank: r.current_rank,
                trend: trendText,
                ma_5: ma_5 !== undefined ? parseFloat(ma_5.toFixed(2)) : undefined,
                ma_10: ma_10 !== undefined ? parseFloat(ma_10.toFixed(2)) : undefined,
                ma_20: ma_20 !== undefined ? parseFloat(ma_20.toFixed(2)) : undefined,
                rsi: rsi !== undefined ? parseFloat(rsi.toFixed(2)) : undefined
              };
            });
            // Reverse to get chronological order (ASC) since query returned DESC
            trendData = trendData.reverse();
          } catch (trendError) {
            // Log error and set empty trend
            console.error(`❌ Could not fetch trend data for ${row.sector_name}:`, trendError.message);
            trendData = [];
          }

          return {
            sector_name: row.sector,
            current_rank: row.current_rank,
            rank_1w_ago: row.rank_1w_ago,
            rank_4w_ago: row.rank_4w_ago,
            rank_12w_ago: row.rank_12w_ago,
            current_momentum: row.current_momentum,
            current_trend: trend,
            current_perf_1d: row.current_perf_1d,
            current_perf_5d: row.current_perf_5d,
            current_perf_20d: row.current_perf_20d,
            trendData: trendData
          };
        })
    );

    res.json({
      data: {
        sectors: sectorsWithTrend
      },
      success: true
    });
  } catch (error) {
    console.error("Sectors with history error:", error);
    res.status(500).json({
      error: "Failed to fetch sectors with history",
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

// ============================================================
// OLD COMPLEX QUERY - COMMENTED OUT
// ============================================================
/*
    // Query industries with historical data + sector mapping + performance metrics
    // Strategy: Get the most recent date that has the best historical data availability
    const OLD_industriesQuery = `
      WITH latest_data AS (
        -- Get the most recent date with actual historical data (not all NULLs)
        SELECT date,
               SUM(CASE WHEN rank_1w_ago IS NOT NULL OR rank_4w_ago IS NOT NULL OR rank_12w_ago IS NOT NULL THEN 1 ELSE 0 END) as ranks_with_history
        FROM industry_ranking
        GROUP BY date_recorded
        ORDER BY ranks_with_history DESC, date DESC
        LIMIT 1
      ),
      industry_prices AS (
        -- Calculate current industry MARKET-CAP WEIGHTED average prices for latest available date
        -- Use key_metrics enterprise_value as market_cap (market_data table doesn't exist)
        SELECT
          cp.industry,
          SUM(pd.close * COALESCE(km.enterprise_value, 1)) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN COALESCE(km.enterprise_value, 1) ELSE 0 END), 0) as avg_close,
          MAX(pd.date) as latest_date
        FROM company_profile cp
        JOIN price_daily pd ON cp.ticker = pd.symbol
        LEFT JOIN key_metrics km ON cp.ticker = km.ticker
        WHERE cp.industry IS NOT NULL AND cp.industry != ''
          AND cp.quote_type = 'EQUITY'
          AND cp.ticker NOT LIKE '%$%'
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
          SELECT cp.industry, SUM(pd.close * COALESCE(km.enterprise_value, 1)) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN COALESCE(km.enterprise_value, 1) ELSE 0 END), 0) as avg_close
          FROM company_profile cp
          JOIN price_daily pd ON cp.ticker = pd.symbol
          LEFT JOIN key_metrics km ON cp.ticker = km.ticker
          WHERE cp.quote_type = 'EQUITY'
            AND cp.ticker NOT LIKE '%$%'
            AND pd.date = (SELECT MAX(date) FROM price_daily) - INTERVAL '1 day'
          GROUP BY cp.industry
        ) pd_1d ON ip.industry = pd_1d.industry
        LEFT JOIN (
          SELECT cp.industry, SUM(pd.close * COALESCE(km.enterprise_value, 1)) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN COALESCE(km.enterprise_value, 1) ELSE 0 END), 0) as avg_close
          FROM company_profile cp
          JOIN price_daily pd ON cp.ticker = pd.symbol
          LEFT JOIN key_metrics km ON cp.ticker = km.ticker
          WHERE cp.quote_type = 'EQUITY'
            AND cp.ticker NOT LIKE '%$%'
            AND pd.date = (SELECT MAX(date) FROM price_daily) - INTERVAL '5 days'
          GROUP BY cp.industry
        ) pd_5d ON ip.industry = pd_5d.industry
        LEFT JOIN (
          SELECT cp.industry, SUM(pd.close * COALESCE(km.enterprise_value, 1)) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN COALESCE(km.enterprise_value, 1) ELSE 0 END), 0) as avg_close
          FROM company_profile cp
          JOIN price_daily pd ON cp.ticker = pd.symbol
          LEFT JOIN key_metrics km ON cp.ticker = km.ticker
          WHERE cp.quote_type = 'EQUITY'
            AND cp.ticker NOT LIKE '%$%'
            AND pd.date = (SELECT MAX(date) FROM price_daily) - INTERVAL '20 days'
          GROUP BY cp.industry
        ) pd_20d ON ip.industry = pd_20d.industry
      )
      SELECT
        ir.industry,
        cp.sector as sector,
        ir.current_rank,
        ir.rank_1w_ago,
        ir.rank_4w_ago,
        ir.rank_12w_ago as rank_8w_ago,
        ir.momentum_score as momentum,
        ir.performance_1w as trend,
        0 as stock_count,
        ir.performance_1m as performance_1d,
        ir.performance_3m as performance_5d,
        ir.performance_ytd as performance_20d,
        ir.date_recorded
      FROM industry_ranking ir
      LEFT JOIN (
        SELECT DISTINCT sector, industry FROM company_profile
        WHERE industry IS NOT NULL
          AND quote_type = 'EQUITY'
          AND ticker NOT LIKE '%$%'
      ) cp ON LOWER(ir.industry) = LOWER(cp.industry)
      LEFT JOIN (
        SELECT DISTINCT ON (industry)
          industry,
          performance_1m as performance_1d,
          performance_3m as performance_5d,
          performance_ytd as performance_20d,
          date_recorded as fetched_at
        FROM industry_ranking
      ) ip ON ir.industry = ip.industry AND ir.date_recorded = ip.fetched_at
      WHERE ir.date_recorded = (SELECT MAX(date_recorded) FROM industry_ranking)
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
        FROM (SELECT NULL::text as industry LIMIT 0) ip_empty
        ORDER BY industry DESC
        LIMIT $1
      `;

      let fallbackResult = { rows: [] };
      try {
        fallbackResult = await query(fallbackQuery, [parseInt(limit)]);
      } catch (e) {
        console.warn("Fallback query failed, returning empty data");
      }

      return res.json({
          industries: await Promise.all((fallbackResult?.rows || []).map(async row => {
            // Fetch technical data for each industry
            let trendData = [];
            try {
              // Fetch raw data from industry_ranking table
              // Note: daily_strength_score doesn't exist in industry_ranking table
              const industryTrendQuery = `
                SELECT
                  ir.date_recorded,
                  ir.current_rank,
                  ir.momentum_score
                FROM industry_ranking ir
                WHERE LOWER(ir.industry) = LOWER($1)
                ORDER BY ir.date_recorded DESC
                LIMIT 200
              `;
              const trendResults = await query(industryTrendQuery, [row.industry]);

              // Build trend data from ranking history - daily_strength_score not available
              trendData = trendResults.rows.map((r, idx, arr) => {
                const dateStr = r.date_recorded instanceof Date ? r.date_recorded.toISOString().split('T')[0] : r.date_recorded;

                // Convert momentum_score to trend indicator (positive = uptrend, negative = downtrend)
                let trendText = "Sideways";
                if (r.momentum_score > 50) trendText = "Uptrend";
                else if (r.momentum_score < 50) trendText = "Downtrend";

                return {
                  date: dateStr,
                  dailyStrengthScore: null,
                  rank: r.current_rank,
                  trend: trendText,
                  ma_5: undefined,
                  ma_10: undefined,
                  ma_20: undefined,
                  rsi: undefined
                };
              });
              // Reverse to get chronological order (ASC) since query returned DESC
              trendData = trendData.reverse();
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
              performance_1d: safeFloat(row.performance_1d),
              performance_5d: safeFloat(row.performance_5d),
              performance_20d: safeFloat(row.performance_20d),
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
        }
      });
    }

    const industries = await Promise.all(result.rows
          .filter(row => row.industry && row.industry.trim())
          .map(async row => {
            // Fetch technical data for each industry (20+ days matching sectors)
            let trendData = [];
            try {
              // Fetch raw data from industry_ranking table
              // Note: daily_strength_score doesn't exist in industry_ranking table
              const industryTrendQuery = `
                SELECT
                  ir.date_recorded,
                  ir.current_rank,
                  ir.momentum_score
                FROM industry_ranking ir
                WHERE LOWER(ir.industry) = LOWER($1)
                ORDER BY ir.date_recorded DESC
                LIMIT 200
              `;
              const trendResults = await query(industryTrendQuery, [row.industry]);

              // Build trend data from ranking history - daily_strength_score not available
              trendData = trendResults.rows.map((r, idx, arr) => {
                const dateStr = r.date_recorded instanceof Date ? r.date_recorded.toISOString().split('T')[0] : r.date_recorded;

                // Convert momentum_score to trend indicator (positive = uptrend, negative = downtrend)
                let trendText = "Sideways";
                if (r.momentum_score > 50) trendText = "Uptrend";
                else if (r.momentum_score < 50) trendText = "Downtrend";

                return {
                  date: dateStr,
                  dailyStrengthScore: null,
                  rank: r.current_rank,
                  trend: trendText,
                  ma_5: undefined,
                  ma_10: undefined,
                  ma_20: undefined,
                  rsi: undefined
                };
              });
              // Reverse to get chronological order (ASC) since query returned DESC
              trendData = trendData.reverse();
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
              performance_1d: safeFloat(row.performance_1d),
              performance_5d: safeFloat(row.performance_5d),
              performance_20d: safeFloat(row.performance_20d),
              rank_change_1w: row.rank_change_1w,
              perf_1d_1w_ago: row.perf_1d_1w_ago,
              perf_5d_1w_ago: row.perf_5d_1w_ago,
              perf_20d_1w_ago: row.perf_20d_1w_ago,
              trendData: trendData
            };
          }));

    res.json({
      data: {
        industries: industries,
        summary: {
          total_industries: industries.length
        }
      },
      success: true
    });
  } catch (error) {
    console.error("Industries with history error:", error);
    res.status(500).json({
      error: "Failed to fetch sectors with history",
      success: false
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
      return res.status(500).json({ error: "Database service unavailable" , success: false});
    }

    const { sectorName } = req.params;

    // Get recent historical rankings for this sector (last 1 year), ordered by date_recorded
    // Calculate moving averages of momentum score directly in SQL
    const trendData = await query(
      `SELECT
        sr.date_recorded as date,
        sr.current_rank as rank,
        sr.momentum_score as daily_strength_score,
        CASE
          WHEN sr.momentum_score > 20 THEN 'Strong Uptrend'
          WHEN sr.momentum_score > 10 THEN 'Uptrend'
          WHEN sr.momentum_score > -5 THEN 'Neutral'
          WHEN sr.momentum_score > -10 THEN 'Downtrend'
          WHEN sr.momentum_score IS NOT NULL THEN 'Strong Downtrend'
          ELSE NULL
        END as trend,
        TO_CHAR(sr.date_recorded, 'MM/DD') as label,
        ROUND(AVG(sr.momentum_score) OVER (ORDER BY sr.date_recorded ROWS BETWEEN 9 PRECEDING AND CURRENT ROW)::numeric, 4) as ma_10,
        ROUND(AVG(sr.momentum_score) OVER (ORDER BY sr.date_recorded ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)::numeric, 4) as ma_20
      FROM sector_ranking sr
      WHERE LOWER(sr.sector_name) = LOWER($1)
      AND sr.date_recorded >= CURRENT_DATE - INTERVAL '365 days'
      ORDER BY sr.date_recorded ASC`,
      [sectorName]
    );

    if (!trendData.rows.length) {
      return res.status(404).json({
        error: "Sector not found or no trend data available",
        success: false
      });
    }

    res.json({
      data: {
        sector: sectorName,
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
    console.error("Sector trend endpoint error:", error.message);
    res.status(500).json({
      error: "Failed to fetch sector trend data",
      success: false
    });
  }
});


// Rankings Endpoints - Return current rankings with daily strength scores
module.exports = router;

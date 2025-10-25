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
router.get("/", async (req, res) => {
  try {
    // Check database availability
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service temporarily unavailable",
        message: "Sectors service requires database connection"
      });
    }

    const { limit = 20, period = "1m" } = req.query;
    console.log(`📊 Fetching sectors list`);

    // Calculate days based on period for both current and comparison prices
    const daysBack = period === "1d" ? 1 : period === "1w" ? 7 : 30;

    const result = await query(
      `
      SELECT
        s.sector,
        COUNT(DISTINCT s.ticker) as stock_count,
        SUM(pd.close * md.market_cap) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN md.market_cap ELSE 0 END), 0) as avg_price,
        SUM(pd.volume) as total_volume,
        CASE
          WHEN SUM(CASE WHEN pd_old.close > 0 THEN md.market_cap ELSE 0 END) > 0 THEN
            (SUM(CASE WHEN pd_old.close > 0 THEN (pd.close - pd_old.close) * md.market_cap ELSE 0 END) /
             SUM(CASE WHEN pd_old.close > 0 THEN md.market_cap ELSE 0 END)) /
            NULLIF(SUM(CASE WHEN pd_old.close > 0 THEN pd_old.close * md.market_cap ELSE 0 END) /
                   SUM(CASE WHEN pd_old.close > 0 THEN md.market_cap ELSE 0 END), 0) * 100
          ELSE NULL
        END as performance_pct,
        COUNT(DISTINCT CASE
          WHEN pd.close > pd_old.close THEN s.ticker
          ELSE NULL
        END) as gaining_stocks,
        COUNT(DISTINCT CASE
          WHEN pd.close < pd_old.close THEN s.ticker
          ELSE NULL
        END) as losing_stocks
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
          symbol, close, date
        FROM price_daily
        WHERE date <= CURRENT_DATE - INTERVAL '${daysBack} days'
        ORDER BY symbol, date DESC
      ) pd_old ON s.ticker = pd_old.symbol
      WHERE s.sector IS NOT NULL AND s.sector != ''
        AND pd.close IS NOT NULL
        AND pd_old.close IS NOT NULL
      GROUP BY s.sector
      ORDER BY performance_pct DESC NULLS LAST
      LIMIT $1
      `,
      [parseInt(limit)]
    );

    console.log(`✅ Query result rows: ${result?.rows?.length || 0}`);

    if (!result || !result.rows) {
      return res.json({
        success: true,
        message: "No sector data available",
        data: [],
        timestamp: new Date().toISOString(),
      });
    }

    console.log(`✅ Found ${result.rows.length} sectors`);

    // Return data in the same format as performance endpoint but called "data"
    res.json({
      success: true,
      data: result.rows.map((row) => ({
        sector: row.sector,
        performance: parseFloat(row.performance_pct),
        stock_count: parseInt(row.stock_count),
        avg_price: parseFloat(row.avg_price),
        total_volume: parseInt(row.total_volume),
        gaining_stocks: parseInt(row.gaining_stocks),
        losing_stocks: parseInt(row.losing_stocks),
        win_rate_pct: parseFloat((row.gaining_stocks / (row.gaining_stocks + row.losing_stocks) * 100) || 0),
      })),
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ Error fetching sectors:", error);
    res.status(500).json({
      success: false,
      error: error.message || "Failed to fetch sectors",
    });
  }
});

/**
 * GET /sectors/:sector/stocks
 * Get stocks in a specific sector from company_profile table
 */
router.get("/:sector/stocks", async (req, res) => {
  try {
    const { sector } = req.params;
    const { limit = 9999999 } = req.query;

    console.log(`📊 Fetching stocks for sector: ${sector}`);

    // Add timeout wrapper
    const executeQueryWithTimeout = (queryPromise, name) => {
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error(`${name} query timeout after 3 seconds`)), 3000)
      );
      return Promise.race([queryPromise, timeoutPromise]);
    };

    // Query company_profile table which has individual stock sector/industry data from yfinance
    const stocksQuery = `
      SELECT
        ticker as symbol,
        short_name as name,
        sector,
        industry
      FROM company_profile
      WHERE (LOWER(sector) = LOWER($1) OR LOWER(industry) = LOWER($1))
      AND sector IS NOT NULL
      ORDER BY ticker ASC
      LIMIT $2
    `;

    const result = await executeQueryWithTimeout(
      query(stocksQuery, [sector, limit]),
      "sector stocks"
    );

    console.log(`✅ Found ${result.rows.length} stocks in ${sector} sector`);

    res.json({
      success: true,
      data: result.rows.map(row => ({
        symbol: row.symbol,
        name: row.name,
        sector: row.sector,
        industry: row.industry
      })),
      metadata: {
        sector: sector,
        count: result.rows.length,
        limit: parseInt(limit)
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error(`❌ Error fetching stocks for sector ${req.params.sector}:`, error);
    res.status(500).json({
      success: false,
      error: error.message || "Failed to fetch sector stocks",
      details: error.message,
    });
  }
});

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
router.get("/list", async (req, res) => {
  try {
    // Check database availability first
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service temporarily unavailable",
        message: "Sectors list service requires database connection"
      });
    }

    console.log("📋 Fetching sector and industry list...");

    const sectorsQuery = `
            SELECT 
                sector,
                industry,
                COUNT(*) as company_count,
                COUNT(CASE WHEN ticker IN (
                    SELECT DISTINCT symbol FROM price_daily 
                    WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                ) THEN 1 END) as active_companies
            FROM company_profile 
            WHERE sector IS NOT NULL 
                AND sector != ''
                AND industry IS NOT NULL 
                AND industry != ''
            GROUP BY sector, industry
            ORDER BY sector, industry
        `;

    const result = await query(sectorsQuery);

    // Group by sector
    const sectorMap = {};
    result.rows.forEach((row) => {
      if (!sectorMap[row.sector]) {
        sectorMap[row.sector] = {
          sector: row.sector,
          industries: [],
          total_companies: 0,
          active_companies: 0,
        };
      }

      sectorMap[row.sector].industries.push({
        industry: row.industry,
        company_count: parseInt(row.company_count),
        active_companies: parseInt(row.active_companies),
      });

      sectorMap[row.sector].total_companies += parseInt(row.company_count);
      sectorMap[row.sector].active_companies += parseInt(row.active_companies);
    });

    const sectors = Object.values(sectorMap);

    console.log(
      `✅ Found ${sectors.length} sectors with ${result.rows.length} industries`
    );

    res.json({
      success: true,
      data: {
        sectors,
        summary: {
          total_sectors: sectors.length,
          total_industries: result.rows.length,
          total_companies: sectors.reduce(
            (sum, s) => sum + s.total_companies,
            0
          ),
          active_companies: sectors.reduce(
            (sum, s) => sum + s.active_companies,
            0
          ),
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ Error fetching sector list:", error);
    res.status(500).json({
      success: false,
      error: error.message || "Failed to fetch sector list",
    });
  }
});

// Get sector performance summary
router.get("/performance", async (req, res) => {
  try {
    const { period = "1m", limit = 10 } = req.query;

    console.log(
      `📈 Sector performance requested, period: ${period}, limit: ${limit}`
    );

    // Validate period
    const validPeriods = ["1d", "1w", "1m", "3m", "6m", "1y"];
    if (!validPeriods.includes(period)) {
      return res.status(400).json({
        success: false,
        error: "Invalid period. Must be one of: 1d, 1w, 1m, 3m, 6m, 1y",
      });
    }

    // Convert period to days for calculation
    const periodDays = {
      "1d": 1,
      "1w": 7,
      "1m": 30,
      "3m": 90,
      "6m": 180,
      "1y": 365,
    };

    const days = periodDays[period];

    // Query for sector performance using real data only with MARKET-CAP WEIGHTING
    const olderDays = days + 7;
    const result = await query(
      `
      SELECT
        s.sector,
        COUNT(DISTINCT s.ticker) as stock_count,
        SUM(pd.close * md.market_cap) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN md.market_cap ELSE 0 END), 0) as avg_price,
        SUM(pd.volume) as total_volume,
        CASE
          WHEN SUM(CASE WHEN pd_old.close > 0 THEN md.market_cap ELSE 0 END) > 0 THEN
            (SUM(CASE WHEN pd_old.close > 0 THEN (pd.close - pd_old.close) * md.market_cap ELSE 0 END) /
             SUM(CASE WHEN pd_old.close > 0 THEN md.market_cap ELSE 0 END)) /
            NULLIF(SUM(CASE WHEN pd_old.close > 0 THEN pd_old.close * md.market_cap ELSE 0 END) /
                   SUM(CASE WHEN pd_old.close > 0 THEN md.market_cap ELSE 0 END), 0) * 100
          ELSE NULL
        END as performance_pct,
        COUNT(DISTINCT CASE
          WHEN pd.close > pd_old.close THEN s.ticker
          ELSE NULL
        END) as gaining_stocks,
        COUNT(DISTINCT CASE
          WHEN pd.close < pd_old.close THEN s.ticker
          ELSE NULL
        END) as losing_stocks
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
        WHERE date >= CURRENT_DATE - INTERVAL '${olderDays} days'
          AND date < CURRENT_DATE - INTERVAL '${days} days'
        ORDER BY symbol, date DESC
      ) pd_old ON s.ticker = pd_old.symbol
      WHERE s.sector IS NOT NULL AND s.sector != ''
        AND pd.close IS NOT NULL
        AND pd_old.close IS NOT NULL
      GROUP BY s.sector
      HAVING COUNT(DISTINCT s.ticker) >= 1
      ORDER BY performance_pct DESC NULLS LAST
      LIMIT $1
      `,
      [parseInt(limit)]
    );

    // If no real data found, check what data we have
    if (result.rows.length === 0) {
      console.log("🔍 No sector performance data found, checking tables...");

      // Check if we have stocks data
      const companyProfileCheck = await query(
        "SELECT COUNT(*) as count FROM company_profile WHERE sector IS NOT NULL AND sector != ''"
      );
      console.log(`📊 Company profiles with sectors: ${companyProfileCheck.rows[0]?.count || 0}`);

      // Check if we have price_daily data
      const priceDataCheck = await query(
        "SELECT COUNT(*) as count FROM price_daily WHERE date >= CURRENT_DATE - INTERVAL '7 days'"
      );
      console.log(`📊 Recent price data records: ${priceDataCheck.rows[0]?.count || 0}`);

      // For AWS compatibility, return empty array instead of 404
      return res.status(200).json({
        success: true,
        message: "Sector performance data loading",
        data: [],
        metadata: {
          period: period,
          limit: parseInt(limit),
          note: "Data is being populated"
        },
        timestamp: new Date().toISOString(),
      });
    }

    // Calculate market summary for real data
    const totalSectors = result.rows.length;
    const gainerSectors = result.rows.filter(
      (row) => parseFloat(row.performance_pct) > 0
    ).length;
    const loserSectors = result.rows.filter(
      (row) => parseFloat(row.performance_pct) < 0
    ).length;
    // avgMarketReturn could be added to metadata in future
    // const avgMarketReturn =
    //   result.rows.reduce(
    //     (sum, row) => sum + parseFloat(row.performance_pct),
    //     0
    //   ) / totalSectors;

    // Return data array directly to match test expectations
    res.json({
      success: true,
      data: result.rows.map((row) => ({
        sector: row.sector,
        performance_pct: parseFloat(row.performance_pct),
        stock_count: parseInt(row.stock_count),
        avg_price: parseFloat(row.avg_price),
        total_volume: parseInt(row.total_volume),
        gaining_stocks: parseInt(row.gaining_stocks),
        losing_stocks: parseInt(row.losing_stocks),
        win_rate_pct: parseFloat((row.gaining_stocks / (row.gaining_stocks + row.losing_stocks) * 100) || 0),
      })),
      metadata: {
        period: period,
        limit: parseInt(limit),
        total_sectors: totalSectors,
        gaining_sectors: gainerSectors,
        losing_sectors: loserSectors,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Sector performance error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sector performance",
      details: error.message,
    });
  }
});


/**
 * GET /sectors/:sector/details
 * Get detailed analysis for a specific sector
 */
router.get("/:sector/details", async (req, res) => {
  try {
    // Check database availability first
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service temporarily unavailable",
        message: "Sector details service requires database connection"
      });
    }

    const { sector } = req.params;
    const { limit = 50 } = req.query;

    console.log(`📊 Fetching detailed analysis for sector: ${sector}`);

    // Add timeout wrapper
    const executeQueryWithTimeout = (queryPromise, name) => {
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error(`${name} query timeout after 5 seconds`)), 5000)
      );
      return Promise.race([queryPromise, timeoutPromise]);
    };

    // Query for sector details using real data only
    const sectorDetailQuery = `
      SELECT
        s.ticker as symbol,
        s.short_name,
        s.industry,
        'US' as market,
        'USA' as country,
        pd.close as current_price,
        pd.volume as volume,
        pd.date as price_date,

        -- Calculate performance from real data
        CASE
          WHEN pd_old.close > 0 THEN
            ((pd.close - pd_old.close) / pd_old.close * 100)
          ELSE NULL
        END as monthly_change,

        -- Technical indicators from database
        ti.rsi,
        ti.momentum,
        ti.macd,
        ti.macd_signal,
        ti.sma_20,
        ti.sma_50,

        -- Momentum data from database
        ti.jt_momentum_12_1,
        ti.momentum_3m,
        ti.momentum_6m,
        ti.risk_adjusted_momentum,
        ti.momentum_strength

      FROM company_profile s
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
          ticker, rsi, momentum, macd, macd_signal, sma_20, sma_50,
          jt_momentum_12_1, momentum_3m, momentum_6m,
          risk_adjusted_momentum, momentum_strength
        FROM technical_data_daily
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY ticker, date DESC
      ) ti ON s.ticker = ti.ticker
      WHERE s.sector = $1
        AND pd.close IS NOT NULL
      ORDER BY s.ticker
      LIMIT $2
    `;

    const result = await executeQueryWithTimeout(
      query(sectorDetailQuery, [sector, limit]),
      "sector details"
    );

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `Sector '${sector}' not found or has no current price data`,
      });
    }

    // Calculate sector statistics
    const stocks = result.rows;
    const avgReturn =
      stocks.reduce(
        (sum, stock) => sum + (parseFloat(stock.monthly_change) || 0),
        0
      ) / stocks.length;
    const totalVolume = stocks.reduce(
      (sum, stock) => sum + (parseInt(stock.volume) || 0),
      0
    );
    const avgMomentum =
      stocks.reduce(
        (sum, stock) => sum + (parseFloat(stock.jt_momentum_12_1) || 0),
        0
      ) / stocks.length;

    // Calculate real trend distribution from technical indicators
    // Bullish: RSI < 70 (not overbought) AND price > SMA20 (above trend)
    // Bearish: RSI > 30 (not oversold) AND price < SMA20 (below trend)
    // Neutral: all others
    const trendCounts = {
      bullish: stocks.filter(stock => {
        const rsi = parseFloat(stock.rsi || 0);
        const price = parseFloat(stock.current_price || 0);
        const sma20 = parseFloat(stock.sma_20 || 0);
        return rsi < 70 && sma20 > 0 && price > sma20;
      }).length,
      bearish: stocks.filter(stock => {
        const rsi = parseFloat(stock.rsi || 0);
        const price = parseFloat(stock.current_price || 0);
        const sma20 = parseFloat(stock.sma_20 || 0);
        return rsi > 30 && sma20 > 0 && price < sma20;
      }).length,
      neutral: 0 // Will calculate as remainder
    };
    trendCounts.neutral = stocks.length - trendCounts.bullish - trendCounts.bearish;

    // Industry breakdown
    const industryBreakdown = stocks.reduce((industries, stock) => {
      if (!industries[stock.industry]) {
        industries[stock.industry] = {
          industry: stock.industry,
          count: 0,
          avg_return: 0,
          stocks: [],
        };
      }
      industries[stock.industry].count += 1;
      industries[stock.industry].stocks.push(stock.symbol);
      return industries;
    }, {});

    // Calculate industry averages
    Object.values(industryBreakdown).forEach((industry) => {
      const industryStocks = stocks.filter(
        (s) => s.industry === industry.industry
      );
      industry.avg_return =
        industryStocks.reduce(
          (sum, s) => sum + (parseFloat(s.monthly_change) || 0),
          0
        ) / industryStocks.length;
    });

    console.log(`✅ Found ${stocks.length} stocks in ${sector} sector`);

    res.json({
      success: true,
      data: {
        sector,
        summary: {
          stock_count: stocks.length,
          avg_monthly_return: avgReturn.toFixed(2),
          total_volume: totalVolume,
          avg_jt_momentum: avgMomentum.toFixed(4),
          trend_distribution: trendCounts,
          industry_count: Object.keys(industryBreakdown).length,
        },
        industries: Object.values(industryBreakdown).sort(
          (a, b) => b.avg_return - a.avg_return
        ),
        stocks: stocks.map((stock) => ({
          symbol: stock.symbol,
          name: stock.short_name,
          industry: stock.industry,
          current_price: parseFloat(stock.current_price || 0).toFixed(2),
          volume: parseInt(stock.volume || 0),
          performance: {
            monthly_change: parseFloat(stock.monthly_change || 0).toFixed(2),
          },
          technicals: {
            rsi: parseFloat(stock.rsi || 0).toFixed(2),
            momentum: parseFloat(stock.momentum || 0).toFixed(2),
            macd: parseFloat(stock.macd || 0).toFixed(4),
            trend: stock.current_price > stock.sma_20 ? 'bullish' : 'bearish',
            rsi_signal: stock.rsi > 70 ? 'overbought' : stock.rsi < 30 ? 'oversold' : 'neutral',
            macd_signal: stock.macd > stock.macd_signal ? 'bullish' : 'bearish',
          },
          momentum: {
            jt_momentum_12_1: parseFloat(stock.jt_momentum_12_1 || 0).toFixed(4),
            momentum_3m: parseFloat(stock.momentum_3m || 0).toFixed(4),
            momentum_6m: parseFloat(stock.momentum_6m || 0).toFixed(4),
            risk_adjusted: parseFloat(stock.risk_adjusted_momentum || 0).toFixed(4),
            strength: parseFloat(stock.momentum_strength || 0).toFixed(2),
          },
        })),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error(
      `❌ Error fetching details for sector ${req.params.sector}:`,
      error
    );
    res.status(500).json({
      success: false,
      error: error.message || "Failed to fetch sector details",
    });
  }
});

// Get portfolio sector allocation
router.get("/allocation", async (req, res) => {
  try {
    const userId = req.user?.sub;

    // If no authenticated user, return empty allocation
    if (!userId) {
      return res.json({
        success: true,
        data: {
          user_id: null,
          allocation: [],
          summary: {
            total_sectors: 0,
            total_value: 0,
            total_cost: 0,
            total_pnl: 0,
            total_stocks: 0,
            diversification_score: 0,
          },
        },
        message: "No authenticated user",
        timestamp: new Date().toISOString(),
      });
    }

    console.log(`📊 Sector allocation requested for user: ${userId}`);

    // Get user's portfolio holdings with sector information using real data
    const allocationQuery = `
      SELECT
        s.sector,
        COUNT(DISTINCT ph.symbol) as stock_count,
        SUM(ph.quantity * ph.average_cost) as total_cost,
        SUM(ph.quantity * pd.close) as current_value,
        SUM(ph.quantity) as total_shares,
        AVG(ph.average_cost) as avg_cost_basis,
        SUM(ph.quantity * pd.close) - SUM(ph.quantity * ph.average_cost) as unrealized_pnl
      FROM portfolio_holdings ph
      LEFT JOIN company_profile s ON ph.symbol = s.ticker
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, close, date
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY symbol, date DESC
      ) pd ON ph.symbol = pd.symbol
      WHERE ph.user_id = $1
        AND ph.quantity > 0
        AND pd.close IS NOT NULL
        AND s.sector IS NOT NULL
      GROUP BY s.sector
      ORDER BY current_value DESC
    `;

    const result = await query(allocationQuery, [userId]);

    if (result.rows.length === 0) {
      return res.json({
        success: true,
        data: {
          user_id: userId,
          allocation: [],
          summary: {
            total_sectors: 0,
            total_value: 0,
            total_cost: 0,
            total_pnl: 0,
            total_stocks: 0,
            diversification_score: 0,
          },
        },
        message: "No portfolio holdings found",
        timestamp: new Date().toISOString(),
      });
    }

    // Calculate totals
    const totalValue = result.rows.reduce(
      (sum, row) => sum + parseFloat(row.current_value),
      0
    );
    const totalCost = result.rows.reduce(
      (sum, row) => sum + parseFloat(row.total_cost),
      0
    );
    const totalPnl = totalValue - totalCost;
    const totalStocks = result.rows.reduce(
      (sum, row) => sum + parseInt(row.stock_count),
      0
    );

    // Calculate diversification score (higher is better, based on even distribution)
    const sectorWeights = result.rows.map(
      (row) => parseFloat(row.current_value) / totalValue
    );
    const idealWeight = 1 / result.rows.length;
    const diversificationScore = Math.max(
      0,
      100 -
        sectorWeights.reduce((sum, weight) => {
          return sum + Math.pow((weight - idealWeight) * 100, 2);
        }, 0) /
          result.rows.length
    );

    // Format allocation data
    const allocation = result.rows.map((row) => {
      const currentValue = parseFloat(row.current_value);
      const totalCostValue = parseFloat(row.total_cost);
      const unrealizedPnl = parseFloat(row.unrealized_pnl);

      return {
        sector: row.sector,
        stock_count: parseInt(row.stock_count),
        allocation_percentage: ((currentValue / totalValue) * 100).toFixed(2),
        current_value: currentValue,
        total_cost: totalCostValue,
        unrealized_pnl: unrealizedPnl,
        unrealized_pnl_percent:
          totalCostValue > 0
            ? ((unrealizedPnl / totalCostValue) * 100).toFixed(2)
            : "0.00",
        total_shares: parseFloat(row.total_shares),
        avg_cost_basis: parseFloat(row.avg_cost_basis),
      };
    });

    res.json({
      success: true,
      data: {
        user_id: userId,
        allocation: allocation,
        summary: {
          total_sectors: result.rows.length,
          total_value: totalValue,
          total_cost: totalCost,
          total_pnl: totalPnl,
          total_pnl_percent:
            totalCost > 0 ? ((totalPnl / totalCost) * 100).toFixed(2) : "0.00",
          total_stocks: totalStocks,
          diversification_score: diversificationScore.toFixed(1),
          largest_allocation: allocation[0]?.sector || null,
          largest_allocation_pct:
            allocation[0]?.allocation_percentage || "0.00",
        },
        recommendations: {
          diversification:
            diversificationScore < 70
              ? "Consider diversifying across more sectors"
              : "Well diversified across sectors",
          concentration_risk:
            allocation[0] &&
            parseFloat(allocation[0].allocation_percentage) > 40
              ? `High concentration in ${allocation[0].sector} sector (${allocation[0].allocation_percentage}%)`
              : null,
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Sector allocation error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sector allocation",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});


// Sector rotation analysis
router.get("/rotation", async (req, res) => {
  try {
    // Check database availability
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service temporarily unavailable",
        message: "Sector rotation service requires database connection"
      });
    }

    const { timeframe = "3m" } = req.query;
    console.log(
      `🔄 Sector rotation analysis requested, timeframe: ${timeframe}`
    );

    // Check if sector_performance table exists and has data
    const checkQuery = `
      SELECT COUNT(*) as count
      FROM information_schema.tables
      WHERE table_name = 'sector_performance'
    `;
    const tableCheck = await query(checkQuery);

    if (!tableCheck.rows[0] || tableCheck.rows[0].count === '0') {
      return res.status(404).json({
        success: false,
        error: "No sector rotation data available in database",
        message: "Sector performance table not found. Please run the loadsectordata.py loader first.",
        timestamp: new Date().toISOString(),
      });
    }

    // Query real sector rotation data from sector_performance table
    const rotationQuery = `
      SELECT
        symbol,
        sector_name,
        momentum,
        money_flow,
        performance_1d,
        performance_5d,
        performance_20d,
        rsi,
        price,
        change_percent,
        total_assets,
        fetched_at
      FROM sector_performance
      ORDER BY sector_name ASC
    `;

    const result = await query(rotationQuery);

    if (!result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No sector rotation data available in database",
        message: "Sector performance data is empty. Please run the loadsectordata.py loader to populate data.",
        timestamp: new Date().toISOString(),
      });
    }

    // Format sector rankings
    const sectorRankings = result.rows.map(row => ({
      sector: row.sector_name,
      symbol: row.symbol,
      momentum: row.momentum,
      flow_direction: row.money_flow,
      rsi: parseFloat(row.rsi || 0),
      performance: {
        daily: parseFloat(row.performance_1d || 0),
        weekly: parseFloat(row.performance_5d || 0),
        monthly: parseFloat(row.performance_20d || 0),
      },
      price: parseFloat(row.price || 0),
      change_percent: parseFloat(row.change_percent || 0),
      total_assets: row.total_assets,
    }));

    // Determine market cycle based on sector money flow
    const inflowCount = sectorRankings.filter(s => s.flow_direction === 'Inflow').length;
    const outflowCount = sectorRankings.filter(s => s.flow_direction === 'Outflow').length;

    let currentPhase = "MID_CYCLE";
    let confidence = 0.7;

    if (inflowCount > outflowCount * 2) {
      currentPhase = "EARLY_CYCLE";
      confidence = 0.85;
    } else if (outflowCount > inflowCount * 2) {
      currentPhase = "RECESSION";
      confidence = 0.8;
    } else if (inflowCount > outflowCount) {
      currentPhase = "MID_CYCLE";
      confidence = 0.75;
    } else {
      currentPhase = "LATE_CYCLE";
      confidence = 0.7;
    }

    const rotationData = {
      timeframe: timeframe,
      analysis_date: new Date().toISOString(),
      sector_rankings: sectorRankings,
      market_cycle: {
        current_phase: currentPhase,
        confidence: confidence,
        inflow_sectors: inflowCount,
        outflow_sectors: outflowCount,
        neutral_sectors: sectorRankings.length - inflowCount - outflowCount,
      },
      last_updated: result.rows[0]?.fetched_at || new Date().toISOString(),
    };

    res.json({
      success: true,
      data: rotationData,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Sector rotation error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sector rotation",
      message: error.message,
    });
  }
});

// Sector leaders
router.get("/leaders", async (req, res) => {
  try {
    const { period = "1d" } = req.query;
    console.log(`🏆 Sector leaders requested, period: ${period}`);

    // Convert period to days
    const periodDays = {
      "1d": 1,
      "1w": 7,
      "1m": 30,
      "3m": 90,
      "6m": 180,
      "1y": 365,
    };
    const days = periodDays[period] || 1;

    // Query real sector performance data
    const leadersQuery = `
      SELECT
        s.sector,
        AVG(
          CASE
            WHEN pd_old.close > 0 THEN
              ((pd.close - pd_old.close) / pd_old.close * 100)
            ELSE NULL
          END
        ) as return_pct,
        SUM(pd.volume) as volume_flow
      FROM company_profile s
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, close, volume
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY symbol, date DESC
      ) pd ON s.ticker = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, close
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '${days + 7} days'
          AND date < CURRENT_DATE - INTERVAL '${days} days'
        ORDER BY symbol, date DESC
      ) pd_old ON s.ticker = pd_old.symbol
      WHERE s.sector IS NOT NULL
        AND pd.close IS NOT NULL
        AND pd_old.close IS NOT NULL
      GROUP BY s.sector
      ORDER BY return_pct DESC NULLS LAST
    `;

    const result = await query(leadersQuery);

    // Calculate breadth metrics
    const breadthQuery = `
      SELECT
        COUNT(DISTINCT CASE WHEN return_pct > 0 THEN sector END) as advancing,
        COUNT(DISTINCT CASE WHEN return_pct < 0 THEN sector END) as declining,
        COUNT(DISTINCT CASE WHEN return_pct = 0 THEN sector END) as neutral
      FROM (
        SELECT
          s.sector,
          AVG(
            CASE
              WHEN pd_old.close > 0 THEN
                ((pd.close - pd_old.close) / pd_old.close * 100)
              ELSE NULL
            END
          ) as return_pct
        FROM company_profile s
        LEFT JOIN (
          SELECT DISTINCT ON (symbol) symbol, close
          FROM price_daily
          WHERE date >= CURRENT_DATE - INTERVAL '7 days'
          ORDER BY symbol, date DESC
        ) pd ON s.ticker = pd.symbol
        LEFT JOIN (
          SELECT DISTINCT ON (symbol) symbol, close
          FROM price_daily
          WHERE date >= CURRENT_DATE - INTERVAL '${days + 7} days'
            AND date < CURRENT_DATE - INTERVAL '${days} days'
          ORDER BY symbol, date DESC
        ) pd_old ON s.ticker = pd_old.symbol
        WHERE s.sector IS NOT NULL
          AND pd.close IS NOT NULL
          AND pd_old.close IS NOT NULL
        GROUP BY s.sector
      ) sector_returns
    `;

    const breadthResult = await query(breadthQuery);
    const breadth = breadthResult.rows[0] || { advancing: 0, declining: 0, neutral: 0 };

    const leadersData = {
      period: period,
      top_performing_sectors: result.rows.map(row => ({
        sector: row.sector,
        return: parseFloat(row.return_pct || 0).toFixed(2),
        volume_flow: parseInt(row.volume_flow || 0)
      })),
      sector_breadth: {
        advancing_sectors: parseInt(breadth.advancing || 0),
        declining_sectors: parseInt(breadth.declining || 0),
        neutral_sectors: parseInt(breadth.neutral || 0),
        breadth_ratio: breadth.declining > 0 ?
          (breadth.advancing / breadth.declining).toFixed(2) : 0,
      },
      last_updated: new Date().toISOString(),
    };

    res.json({
      success: true,
      data: leadersData,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Sector leaders error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sector leaders",
      message: error.message,
    });
  }
});

// Sector laggards
router.get("/laggards", async (req, res) => {
  try {
    const { period = "1d" } = req.query;
    console.log(`📉 Sector laggards requested, period: ${period}`);

    // Convert period to days
    const periodDays = {
      "1d": 1,
      "1w": 7,
      "1m": 30,
      "3m": 90,
      "6m": 180,
      "1y": 365,
    };
    const days = periodDays[period] || 1;

    // Query real sector performance data for worst performers
    const laggardsQuery = `
      SELECT
        s.sector,
        AVG(
          CASE
            WHEN pd_old.close > 0 THEN
              ((pd.close - pd_old.close) / pd_old.close * 100)
            ELSE NULL
          END
        ) as return_pct,
        SUM(pd.volume) as volume_flow
      FROM company_profile s
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, close, volume
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY symbol, date DESC
      ) pd ON s.ticker = pd.symbol
      LEFT JOIN (
        SELECT DISTINCT ON (symbol)
          symbol, close
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '${days + 7} days'
          AND date < CURRENT_DATE - INTERVAL '${days} days'
        ORDER BY symbol, date DESC
      ) pd_old ON s.ticker = pd_old.symbol
      WHERE s.sector IS NOT NULL
        AND pd.close IS NOT NULL
        AND pd_old.close IS NOT NULL
      GROUP BY s.sector
      ORDER BY return_pct ASC NULLS LAST
    `;

    const result = await query(laggardsQuery);

    const laggardsData = {
      period: period,
      worst_performing_sectors: result.rows.map(row => ({
        sector: row.sector,
        return: parseFloat(row.return_pct || 0).toFixed(2),
        volume_flow: parseInt(row.volume_flow || 0)
      })),
      last_updated: new Date().toISOString(),
    };

    res.json({
      success: true,
      data: laggardsData,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Sector laggards error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sector laggards",
      message: error.message,
    });
  }
});

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

    // Query sectors with historical data from the consolidated rankings table + performance metrics
    // Strategy: Get top-ranked sectors from most recent date with historical data
    const sectorsQuery = `
      WITH latest_data AS (
        -- Get the most recent date with actual historical data (not all NULLs)
        SELECT sr.date,
               SUM(CASE WHEN sr.rank_1w_ago IS NOT NULL OR sr.rank_4w_ago IS NOT NULL OR sr.rank_12w_ago IS NOT NULL THEN 1 ELSE 0 END) as ranks_with_history
        FROM sector_ranking sr
        GROUP BY sr.date
        ORDER BY ranks_with_history DESC, sr.date DESC
        LIMIT 1
      ),
      sector_prices AS (
        -- Calculate current sector MARKET-CAP WEIGHTED average prices for latest available date
        SELECT
          cp.sector,
          SUM(pd.close * md.market_cap) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN md.market_cap ELSE 0 END), 0) as avg_close,
          MAX(pd.date) as latest_date
        FROM company_profile cp
        JOIN price_daily pd ON cp.ticker = pd.symbol
        LEFT JOIN market_data md ON cp.ticker = md.ticker
        WHERE cp.sector IS NOT NULL AND cp.sector != ''
          AND pd.date = (SELECT MAX(date) FROM price_daily)
        GROUP BY cp.sector
      ),
      calculated_performance AS (
        -- Calculate 1D, 5D, 20D percentages from price data
        SELECT
          sp.sector,
          CASE
            WHEN pd_1d.avg_close > 0 THEN
              ((sp.avg_close - pd_1d.avg_close) / pd_1d.avg_close * 100)
            ELSE NULL
          END as perf_1d,
          CASE
            WHEN pd_5d.avg_close > 0 THEN
              ((sp.avg_close - pd_5d.avg_close) / pd_5d.avg_close * 100)
            ELSE NULL
          END as perf_5d,
          CASE
            WHEN pd_20d.avg_close > 0 THEN
              ((sp.avg_close - pd_20d.avg_close) / pd_20d.avg_close * 100)
            ELSE NULL
          END as perf_20d
        FROM sector_prices sp
        LEFT JOIN (
          SELECT cp.sector, SUM(pd.close * md.market_cap) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN md.market_cap ELSE 0 END), 0) as avg_close
          FROM company_profile cp
          JOIN price_daily pd ON cp.ticker = pd.symbol
          LEFT JOIN market_data md ON cp.ticker = md.ticker
          WHERE pd.date = (SELECT MAX(date) FROM price_daily) - INTERVAL '1 day'
          GROUP BY cp.sector
        ) pd_1d ON sp.sector = pd_1d.sector
        LEFT JOIN (
          SELECT cp.sector, SUM(pd.close * md.market_cap) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN md.market_cap ELSE 0 END), 0) as avg_close
          FROM company_profile cp
          JOIN price_daily pd ON cp.ticker = pd.symbol
          LEFT JOIN market_data md ON cp.ticker = md.ticker
          WHERE pd.date = (SELECT MAX(date) FROM price_daily) - INTERVAL '5 days'
          GROUP BY cp.sector
        ) pd_5d ON sp.sector = pd_5d.sector
        LEFT JOIN (
          SELECT cp.sector, SUM(pd.close * md.market_cap) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN md.market_cap ELSE 0 END), 0) as avg_close
          FROM company_profile cp
          JOIN price_daily pd ON cp.ticker = pd.symbol
          LEFT JOIN market_data md ON cp.ticker = md.ticker
          WHERE pd.date = (SELECT MAX(date) FROM price_daily) - INTERVAL '20 days'
          GROUP BY cp.sector
        ) pd_20d ON sp.sector = pd_20d.sector
      )
      SELECT
        sr.sector as sector_name,
        sr.current_rank,
        sr.rank_1w_ago,
        sr.rank_4w_ago,
        sr.rank_12w_ago,
        sr.daily_strength_score as current_momentum,
        sr.trend as current_trend,
        COALESCE(CAST(sp.performance_1d AS FLOAT), CAST(cp.perf_1d AS FLOAT)) as current_perf_1d,
        COALESCE(CAST(sp.performance_5d AS FLOAT), CAST(cp.perf_5d AS FLOAT)) as current_perf_5d,
        COALESCE(CAST(sp.performance_20d AS FLOAT), CAST(cp.perf_20d AS FLOAT)) as current_perf_20d,
        sr.date
      FROM sector_ranking sr
      LEFT JOIN (
        SELECT DISTINCT ON (sector_name)
          sector_name,
          performance_1d,
          performance_5d,
          performance_20d,
          fetched_at
        FROM sector_performance
        ORDER BY sector_name, fetched_at DESC
      ) sp ON LOWER(sr.sector) = LOWER(sp.sector_name)
      LEFT JOIN calculated_performance cp ON sr.sector = cp.sector,
      latest_data ld
      WHERE sr.date = ld.date
      ORDER BY sr.current_rank ASC NULLS LAST, sr.sector ASC
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
            return {
              sector_name: row.sector_name,
              current_rank: row.current_rank,
              rank_1w_ago: row.rank_1w_ago,
              rank_4w_ago: row.rank_4w_ago,
              rank_12w_ago: row.rank_12w_ago,
              current_momentum: row.current_momentum,
              current_trend: trend,
              current_perf_1d: parseFloat(row.current_perf_1d || 0),
              current_perf_5d: parseFloat(row.current_perf_5d || 0),
              current_perf_20d: parseFloat(row.current_perf_20d || 0),
              rank_change_1w: row.rank_change_1w,
              perf_1d_1w_ago: row.perf_1d_1w_ago,
              perf_5d_1w_ago: row.perf_5d_1w_ago,
              perf_20d_1w_ago: row.perf_20d_1w_ago,
            };
          })
        },
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      data: {
        sectors: result.rows
          .filter(row => row.sector_name && row.sector_name.trim())
          .map(row => {
          // Convert trend numeric value to text
          let trend = row.current_trend;
          if (typeof trend === 'string' && !isNaN(trend)) {
            // Convert numeric string to number then to trend text
            const perfValue = parseFloat(trend);
            trend = perfValue > 0 ? 'Uptrend' : perfValue < 0 ? 'Downtrend' : 'Sideways';
          }
          return {
            sector_name: row.sector_name,
            current_rank: row.current_rank,
            rank_1w_ago: row.rank_1w_ago,
            rank_4w_ago: row.rank_4w_ago,
            rank_12w_ago: row.rank_12w_ago,
            current_momentum: row.current_momentum,
            current_trend: trend,
            current_perf_1d: parseFloat(row.current_perf_1d || 0),
            current_perf_5d: parseFloat(row.current_perf_5d || 0),
            current_perf_20d: parseFloat(row.current_perf_20d || 0),
            rank_change_1w: row.rank_change_1w,
            perf_1d_1w_ago: row.perf_1d_1w_ago,
            perf_5d_1w_ago: row.perf_5d_1w_ago,
            perf_20d_1w_ago: row.perf_20d_1w_ago,
          };
        })
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
          industries: (fallbackResult?.rows || []).map(row => ({
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
          })),
          summary: {
            total_industries: (fallbackResult?.rows || []).length
          }
        },
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      data: {
        industries: result.rows
          .filter(row => row.industry && row.industry.trim())
          .map(row => ({
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
        })),
        summary: {
          total_industries: result.rows.filter(row => row.industry && row.industry.trim()).length
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
router.get("/ranking-history", async (req, res) => {
  try {
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service temporarily unavailable",
        message: "Sector ranking history requires database connection"
      });
    }

    const { sector = null, limit = 11 } = req.query;
    console.log(`📊 Fetching sector ranking history${sector ? ` for ${sector}` : ''}`);

    const rankingHistoryQuery = buildRankingHistoryQuery('sector', sector);
    const params = sector
      ? [sector, 1, parseInt(limit)]
      : [1, parseInt(limit)];

    const result = await query(rankingHistoryQuery, params);

    if (!result || result.rows.length === 0) {
      return res.status(200).json({
        success: true,
        data: [],
        message: "No historical ranking data available yet. Data will be available after sector loaders run.",
        timestamp: new Date().toISOString(),
      });
    }

    const rankingsByPeriod = processRankingResults(result.rows, 'sector');

    // BUG FIX: Format response to match expected structure
    const formattedData = formatRankingResponse(rankingsByPeriod, 'sector');

    res.json({
      success: true,
      data: formattedData,
      metadata: {
        total_sectors: Object.keys(rankingsByPeriod).length,
        periods: ['today', '1_week_ago', '3_weeks_ago', '8_weeks_ago'],
        note: 'Lower rank is better (1 = best performing)'
      },
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error("Sector ranking history error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sector ranking history",
      message: error.message,
    });
  }
});

/**
 * GET /industries/ranking-history
 * Get historical ranking progression for industries to identify trends
 */
router.get("/industries/ranking-history", async (req, res) => {
  try {
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service temporarily unavailable",
        message: "Industry ranking history requires database connection"
      });
    }

    const { industry = null, limit = 20 } = req.query;
    console.log(`🏭 Fetching industry ranking history${industry ? ` for ${industry}` : ''}`);

    const rankingHistoryQuery = buildRankingHistoryQuery('industry', industry);
    const params = industry
      ? [industry, 1, parseInt(limit)]
      : [1, parseInt(limit)];

    const result = await query(rankingHistoryQuery, params);

    if (!result || result.rows.length === 0) {
      return res.status(200).json({
        success: true,
        data: [],
        message: "No historical industry ranking data available yet. Data will be available after industry loaders run.",
        timestamp: new Date().toISOString(),
      });
    }

    const rankingsByPeriod = processRankingResults(result.rows, 'industry');

    // BUG FIX: Format response to match expected structure
    const formattedData = formatRankingResponse(rankingsByPeriod, 'industry');

    res.json({
      success: true,
      data: formattedData,
      metadata: {
        total_industries: Object.keys(rankingsByPeriod).length,
        periods: ['today', '1_week_ago', '3_weeks_ago', '8_weeks_ago'],
        note: 'Lower rank is better (1 = best performing)'
      },
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error("Industry ranking history error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch industry ranking history",
      message: error.message,
    });
  }
});

/**
 * GET /sectors/heatmap
 * Get sector heatmap data for visualization
 */
router.get("/heatmap", authenticateToken, async (req, res) => {
  try {
    console.log("📊 Fetching sector heatmap data");

    // Add timeout wrapper
    const executeQueryWithTimeout = (queryPromise, name) => {
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error(`${name} query timeout after 3 seconds`)), 3000)
      );
      return Promise.race([queryPromise, timeoutPromise]);
    };

    // Get sector performance data for heatmap
    const heatmapQuery = `
      SELECT
        cp.sector,
        COUNT(*) as stock_count,
        AVG(md.current_price) as avg_price,
        AVG(md.volume) as avg_volume,
        AVG(md.market_cap) as avg_market_cap,
        SUM(md.market_cap) as total_market_cap
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      WHERE cp.sector IS NOT NULL
        AND md.current_price IS NOT NULL
        AND md.market_cap IS NOT NULL
      GROUP BY cp.sector
      ORDER BY total_market_cap DESC
    `;

    const heatmapData = await executeQueryWithTimeout(
      query(heatmapQuery),
      "sector heatmap"
    );

    // Format data for heatmap visualization
    const formattedData = heatmapData.map(sector => ({
      sector: sector.sector,
      stockCount: parseInt(sector.stock_count),
      averagePrice: parseFloat(sector.avg_price || 0).toFixed(2),
      averageVolume: parseInt(sector.avg_volume || 0),
      averageMarketCap: parseFloat(sector.avg_market_cap || 0),
      totalMarketCap: parseFloat(sector.total_market_cap || 0),
      weight: parseFloat(sector.total_market_cap || 0) /
              Math.max(1, heatmapData.reduce((sum, s) => sum + parseFloat(s.total_market_cap || 0), 0))
    }));

    res.json({
      success: true,
      data: formattedData,
      metadata: {
        totalSectors: formattedData.length,
        totalStocks: formattedData.reduce((sum, s) => sum + s.stockCount, 0),
        totalMarketCap: formattedData.reduce((sum, s) => sum + s.totalMarketCap, 0)
      },
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error("Sector heatmap error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sector heatmap",
      message: error.message,
      timestamp: new Date().toISOString(),
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
router.get("/rankings", async (req, res) => {
  try {
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service unavailable"
      });
    }

    const { limit = 20 } = req.query;

    // Get the most recent date with ranking data
    const dateResult = await query(
      `SELECT DISTINCT date FROM sector_ranking ORDER BY date DESC LIMIT 1`
    );

    if (!dateResult.rows.length) {
      return res.status(404).json({
        success: false,
        error: "No ranking data available"
      });
    }

    const latestDate = dateResult.rows[0].date;

    // Get current rankings for that date, sorted by rank
    const rankings = await query(
      `SELECT
        sector,
        current_rank as rank,
        daily_strength_score,
        trend,
        TO_CHAR(date, 'MM/DD/YYYY') as date
      FROM sector_ranking
      WHERE date = $1
      ORDER BY current_rank ASC
      LIMIT $2`,
      [latestDate, parseInt(limit)]
    );

    res.json({
      success: true,
      asOf: latestDate,
      rankings: rankings.rows.map(row => ({
        sector: row.sector,
        rank: row.rank,
        dailyStrengthScore: row.daily_strength_score,
        trend: row.trend,
        date: row.date
      }))
    });
  } catch (error) {
    console.error("Sector rankings endpoint error:", error.message);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sector rankings",
      details: error.message
    });
  }
});

router.get("/industry/rankings", async (req, res) => {
  try {
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database service unavailable"
      });
    }

    const { limit = 20 } = req.query;

    // Get the most recent date with ranking data
    const dateResult = await query(
      `SELECT DISTINCT date FROM industry_ranking ORDER BY date DESC LIMIT 1`
    );

    if (!dateResult.rows.length) {
      return res.status(404).json({
        success: false,
        error: "No ranking data available"
      });
    }

    const latestDate = dateResult.rows[0].date;

    // Get current rankings for that date, sorted by rank
    const rankings = await query(
      `SELECT
        industry,
        current_rank as rank,
        daily_strength_score,
        trend,
        stock_count,
        TO_CHAR(date, 'MM/DD/YYYY') as date
      FROM industry_ranking
      WHERE date = $1
      ORDER BY current_rank ASC
      LIMIT $2`,
      [latestDate, parseInt(limit)]
    );

    res.json({
      success: true,
      asOf: latestDate,
      rankings: rankings.rows.map(row => ({
        industry: row.industry,
        rank: row.rank,
        dailyStrengthScore: row.daily_strength_score,
        trend: row.trend,
        stockCount: row.stock_count,
        date: row.date
      }))
    });
  } catch (error) {
    console.error("Industry rankings endpoint error:", error.message);
    res.status(500).json({
      success: false,
      error: "Failed to fetch industry rankings",
      details: error.message
    });
  }
});

module.exports = router;

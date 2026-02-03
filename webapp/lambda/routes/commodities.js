const express = require("express");

/**
 * Commodities API Routes
 *
 * IMPORTANT: This file has been cleaned of ALL fallback/mock data
 * - No COALESCE with hardcoded fallbacks
 * - No CASE WHEN simulated performance values
 * - All data comes directly from database tables
 * - NULL values are acceptable and expected when data is missing
 *
 * Data dependencies:
 * - commodity_prices table (current market data)
 * - commodity_price_history table (historical OHLCV)
 * - cot_data table (Commitment of Traders - CRITICAL FEATURE)
 * - commodity_seasonality table (monthly patterns)
 * - commodity_correlations table (price correlations)
 * - commodity_categories table (metadata)
 *
 * Updated: 2026-02-01 - Initial implementation
 */

let query, safeFloat, safeInt, safeFixed;
let databaseInitError = null;

try {
  ({ query, safeFloat, safeInt, safeFixed } = require("../utils/database"));
} catch (error) {
  databaseInitError = error;
  console.error("❌ CRITICAL: Database service failed to load in commodities routes:", error.message);
  // Provide fallback functions that return null for missing data
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
      error: "Database service unavailable - cannot retrieve commodities data",
      success: false
    });
  }
  return null;
}

const router = express.Router();

// Root endpoint - returns available sub-endpoints
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "commodities",
      description: "Commodities market data and COT analysis",
      available_routes: [
        "/categories - Commodity categories and performance",
        "/prices - Current commodity prices with filtering",
        "/market-summary - Market overview and leaders",
        "/cot/:symbol - Commitment of Traders analysis",
        "/seasonality/:symbol - Seasonal patterns by month",
        "/correlations - Price correlations between commodities"
      ]
    },
    success: true
  });
});

/**
 * GET /commodities/categories
 * Get commodity categories with aggregate performance data
 */
router.get("/categories", async (req, res) => {
  const dbError = checkDatabaseAvailable(res);
  if (dbError) return dbError;

  try {
    const result = await query(`
      SELECT
        cc.category,
        COUNT(DISTINCT cc.symbol) as commodity_count,
        AVG(CAST(cp.change_percent AS FLOAT)) as avg_change_1d,
        MAX(CAST(cp.price AS FLOAT)) as highest_price,
        MIN(CAST(cp.price AS FLOAT)) as lowest_price
      FROM commodity_categories cc
      LEFT JOIN commodity_prices cp ON cc.symbol = cp.symbol
      GROUP BY cc.category
      ORDER BY cc.category
    `);

    const categories = result.rows.map(row => ({
      category: row.category,
      name: row.category.charAt(0).toUpperCase() + row.category.slice(1),
      commodityCount: safeInt(row.commodity_count),
      avgChange1d: safeFixed(row.avg_change_1d, 2),
      highestPrice: safeFloat(row.highest_price),
      lowestPrice: safeFloat(row.lowest_price)
    }));

    return res.json({
      data: categories,
      success: true
    });
  } catch (error) {
    console.error("❌ Error fetching commodity categories:", error.message);
    return res.status(500).json({
      error: "Failed to fetch commodity categories",
      success: false
    });
  }
});

/**
 * GET /commodities/prices
 * Get current commodity prices with optional category filter
 * Query parameters: ?category=energy&limit=50
 */
router.get("/prices", async (req, res) => {
  const dbError = checkDatabaseAvailable(res);
  if (dbError) return dbError;

  const { category, limit = 50 } = req.query;

  try {
    let sql = `
      SELECT
        cp.symbol,
        cp.name,
        CAST(cp.price AS FLOAT) as price,
        CAST(cp.change_amount AS FLOAT) as change_amount,
        CAST(cp.change_percent AS FLOAT) as change_percent,
        CAST(cp.volume AS FLOAT) as volume,
        CAST(cp.high_52w AS FLOAT) as high_52w,
        CAST(cp.low_52w AS FLOAT) as low_52w,
        cc.category,
        cc.unit,
        cc.exchange,
        cp.updated_at
      FROM commodity_prices cp
      LEFT JOIN commodity_categories cc ON cp.symbol = cc.symbol
    `;

    const params = [];
    if (category && category !== 'all') {
      sql += ` WHERE cc.category = $1`;
      params.push(category);
    }

    sql += ` ORDER BY cp.updated_at DESC LIMIT $${params.length + 1}`;
    params.push(parseInt(limit) || 50);

    const result = await query(sql, params);

    const prices = result.rows.map(row => ({
      symbol: row.symbol,
      name: row.name,
      price: safeFloat(row.price),
      change: safeFloat(row.change_amount),
      changePercent: safeFixed(row.change_percent, 2),
      volume: safeInt(row.volume),
      high52w: safeFloat(row.high_52w),
      low52w: safeFloat(row.low_52w),
      category: row.category,
      unit: row.unit,
      exchange: row.exchange,
      updatedAt: row.updated_at
    }));

    return res.json({
      data: prices,
      success: true
    });
  } catch (error) {
    console.error("❌ Error fetching commodity prices:", error.message);
    return res.status(500).json({
      error: "Failed to fetch commodity prices",
      success: false
    });
  }
});

/**
 * GET /commodities/market-summary
 * Get market overview with top gainers/losers and sector performance
 */
router.get("/market-summary", async (req, res) => {
  const dbError = checkDatabaseAvailable(res);
  if (dbError) return dbError;

  try {
    // Get all prices for gainers/losers
    const pricesResult = await query(`
      SELECT
        cp.symbol,
        cp.name,
        CAST(cp.change_percent AS FLOAT) as change_percent,
        CAST(cp.price AS FLOAT) as price,
        cc.category
      FROM commodity_prices cp
      LEFT JOIN commodity_categories cc ON cp.symbol = cc.symbol
      ORDER BY cp.updated_at DESC
    `);

    const prices = pricesResult.rows;
    const totalVolume = await query(`
      SELECT SUM(CAST(volume AS FLOAT)) as total
      FROM commodity_prices
    `);

    // Get top gainers and losers
    const gainers = prices
      .sort((a, b) => (parseFloat(b.change_percent) || 0) - (parseFloat(a.change_percent) || 0))
      .slice(0, 5);

    const losers = prices
      .sort((a, b) => (parseFloat(a.change_percent) || 0) - (parseFloat(b.change_percent) || 0))
      .slice(0, 5);

    // Get category aggregates
    const categoryResult = await query(`
      SELECT
        cc.category,
        AVG(CAST(cp.change_percent AS FLOAT)) as avg_change_1d,
        COUNT(DISTINCT cc.symbol) as count
      FROM commodity_categories cc
      LEFT JOIN commodity_prices cp ON cc.symbol = cp.symbol
      GROUP BY cc.category
    `);

    const sectors = categoryResult.rows.map(row => ({
      name: row.category.charAt(0).toUpperCase() + row.category.slice(1),
      category: row.category,
      change1d: safeFixed(row.avg_change_1d, 2),
      trend: (parseFloat(row.avg_change_1d) || 0) >= 0 ? "up" : "down"
    }));

    return res.json({
      data: {
        overview: {
          activeContracts: prices.length,
          totalVolume: safeInt(totalVolume.rows[0]?.total)
        },
        topGainers: gainers.map(p => ({
          symbol: p.symbol,
          name: p.name,
          change: safeFixed(p.change_percent, 2),
          price: safeFloat(p.price)
        })),
        topLosers: losers.map(p => ({
          symbol: p.symbol,
          name: p.name,
          change: safeFixed(p.change_percent, 2),
          price: safeFloat(p.price)
        })),
        sectors: sectors
      },
      success: true
    });
  } catch (error) {
    console.error("❌ Error fetching market summary:", error.message);
    return res.status(500).json({
      error: "Failed to fetch market summary",
      success: false
    });
  }
});

/**
 * GET /commodities/cot/:symbol
 * Get Commitment of Traders analysis for a specific commodity
 * CRITICAL FEATURE: Shows commercial vs speculator positioning
 */
router.get("/cot/:symbol", async (req, res) => {
  const dbError = checkDatabaseAvailable(res);
  if (dbError) return dbError;

  const { symbol } = req.params;

  try {
    const result = await query(`
      SELECT
        symbol,
        report_date,
        CAST(commercial_long AS FLOAT) as commercial_long,
        CAST(commercial_short AS FLOAT) as commercial_short,
        CAST(commercial_net AS FLOAT) as commercial_net,
        CAST(non_commercial_long AS FLOAT) as non_commercial_long,
        CAST(non_commercial_short AS FLOAT) as non_commercial_short,
        CAST(non_commercial_net AS FLOAT) as non_commercial_net,
        CAST(open_interest AS FLOAT) as open_interest
      FROM cot_data
      WHERE symbol = $1
      ORDER BY report_date DESC
      LIMIT 52
    `, [symbol]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        error: `No COT data available for symbol: ${symbol}`,
        success: false
      });
    }

    const cotHistory = result.rows
      .reverse() // Oldest to newest for chart
      .map(row => ({
        reportDate: row.report_date,
        commercial: {
          long: safeInt(row.commercial_long),
          short: safeInt(row.commercial_short),
          net: safeInt(row.commercial_net)
        },
        nonCommercial: {
          long: safeInt(row.non_commercial_long),
          short: safeInt(row.non_commercial_short),
          net: safeInt(row.non_commercial_net)
        },
        openInterest: safeInt(row.open_interest)
      }));

    // Calculate sentiment based on latest report
    const latest = result.rows[0];
    const commercialNet = parseFloat(latest.commercial_net) || 0;
    const nonCommercialNet = parseFloat(latest.non_commercial_net) || 0;

    // Sentiment: positive net = bullish, negative = bearish
    const commercialSentiment = commercialNet > 0 ? "bullish" : commercialNet < 0 ? "bearish" : "neutral";
    const speculatorSentiment = nonCommercialNet > 0 ? "bullish" : nonCommercialNet < 0 ? "bearish" : "neutral";

    // Divergence: when commercial and speculator sentiments differ
    const divergence = commercialSentiment !== speculatorSentiment ? "divergent" : "aligned";

    // Get commodity name
    const nameResult = await query(
      `SELECT name FROM commodity_prices WHERE symbol = $1 LIMIT 1`,
      [symbol]
    );

    return res.json({
      data: {
        symbol: symbol,
        commodityName: nameResult.rows[0]?.name || symbol,
        latestReportDate: latest.report_date,
        cotHistory: cotHistory,
        analysis: {
          commercialSentiment: commercialSentiment,
          speculatorSentiment: speculatorSentiment,
          divergence: divergence,
          latestCommercialNet: safeInt(latest.commercial_net),
          latestSpeculatorNet: safeInt(latest.non_commercial_net)
        }
      },
      success: true
    });
  } catch (error) {
    console.error("❌ Error fetching COT data:", error.message);
    return res.status(500).json({
      error: "Failed to fetch COT data",
      success: false
    });
  }
});

/**
 * GET /commodities/seasonality/:symbol
 * Get seasonal patterns by month for a commodity
 */
router.get("/seasonality/:symbol", async (req, res) => {
  const dbError = checkDatabaseAvailable(res);
  if (dbError) return dbError;

  const { symbol } = req.params;

  try {
    const result = await query(`
      SELECT
        symbol,
        month,
        CAST(avg_return AS FLOAT) as avg_return,
        CAST(win_rate AS FLOAT) as win_rate,
        CAST(volatility AS FLOAT) as volatility,
        CAST(years_data AS INTEGER) as years_data
      FROM commodity_seasonality
      WHERE symbol = $1
      ORDER BY month ASC
    `, [symbol]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        error: `No seasonality data available for symbol: ${symbol}`,
        success: false
      });
    }

    const monthNames = [
      "January", "February", "March", "April", "May", "June",
      "July", "August", "September", "October", "November", "December"
    ];

    // Get commodity name
    const nameResult = await query(
      `SELECT name FROM commodity_prices WHERE symbol = $1 LIMIT 1`,
      [symbol]
    );

    const seasonality = result.rows.map(row => ({
      month: safeInt(row.month),
      monthName: monthNames[safeInt(row.month) - 1],
      avgReturn: safeFixed(row.avg_return, 4),
      winRate: safeFixed(row.win_rate, 1),
      volatility: safeFixed(row.volatility, 4),
      yearsData: safeInt(row.years_data)
    }));

    return res.json({
      data: {
        symbol: symbol,
        commodityName: nameResult.rows[0]?.name || symbol,
        seasonality: seasonality
      },
      success: true
    });
  } catch (error) {
    console.error("❌ Error fetching seasonality data:", error.message);
    return res.status(500).json({
      error: "Failed to fetch seasonality data",
      success: false
    });
  }
});

/**
 * GET /commodities/correlations
 * Get correlation data between commodity pairs
 * Query parameters: ?min_correlation=0.5&timeframe=90d
 */
router.get("/correlations", async (req, res) => {
  const dbError = checkDatabaseAvailable(res);
  if (dbError) return dbError;

  const { minCorrelation = 0.5, timeframe = "90d" } = req.query;
  const minCorrValue = Math.abs(parseFloat(minCorrelation) || 0.5);

  try {
    let correlationField = "correlation_90d"; // Default
    if (timeframe === "30d") correlationField = "correlation_30d";
    if (timeframe === "1y") correlationField = "correlation_1y";

    const sql = `
      SELECT
        symbol1,
        symbol2,
        cp1.name as name1,
        cp2.name as name2,
        CAST(${correlationField} AS FLOAT) as coefficient
      FROM commodity_correlations cc
      LEFT JOIN commodity_prices cp1 ON cc.symbol1 = cp1.symbol
      LEFT JOIN commodity_prices cp2 ON cc.symbol2 = cp2.symbol
      WHERE ABS(CAST(${correlationField} AS FLOAT)) >= $1
      ORDER BY ABS(CAST(${correlationField} AS FLOAT)) DESC
      LIMIT 50
    `;

    const result = await query(sql, [minCorrValue]);

    const correlations = result.rows.map(row => {
      const coeff = parseFloat(row.coefficient) || 0;
      let strength = "weak";
      if (Math.abs(coeff) > 0.7) strength = "strong";
      else if (Math.abs(coeff) > 0.5) strength = "moderate";

      return {
        symbol1: row.symbol1,
        symbol2: row.symbol2,
        name1: row.name1,
        name2: row.name2,
        pair: `${row.name1} vs ${row.name2}`,
        coefficient: safeFixed(row.coefficient, 2),
        strength: strength
      };
    });

    return res.json({
      data: {
        timeframe: timeframe,
        minCorrelation: minCorrelation,
        correlations: correlations
      },
      success: true
    });
  } catch (error) {
    console.error("❌ Error fetching correlations:", error.message);
    return res.status(500).json({
      error: "Failed to fetch correlations",
      success: false
    });
  }
});

module.exports = router;

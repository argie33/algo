/**
 * Market Indicators Endpoints - Fixed Version
 * Uses correct database tables and column names
 */

const express = require("express");

let query;
try {
  ({ query } = require("../utils/database"));
} catch (error) {
  console.log("Database service not available:", error.message);
  query = null;
}

const router = express.Router();

/**
 * GET /api/market/yield-curve
 * Returns 10Y-2Y treasury spread (recession indicator)
 * Data source: price_daily table (^TNX, ^IRX symbols)
 */
router.get("/yield-curve", async (req, res) => {
  console.log("📈 Yield Curve endpoint called");

  try {
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database connection not available",
        timestamp: new Date().toISOString()
      });
    }

    // Query price_daily for latest treasury yields
    const result = await query(`
      SELECT
        MAX(CASE WHEN symbol = '^TNX' THEN close END) as tnx_10y,
        MAX(CASE WHEN symbol = '^IRX' THEN close END) as irx_2y,
        MAX(date) as date
      FROM price_daily
      WHERE symbol IN ('^TNX', '^IRX')
        AND close IS NOT NULL
        AND date = (SELECT MAX(date) FROM price_daily WHERE symbol IN ('^TNX', '^IRX'))
    `);

    if (!result || !result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No yield curve data available",
        message: "Treasury yield data (^TNX, ^IRX) not found in database",
        timestamp: new Date().toISOString(),
      });
    }

    const data = result.rows[0];
    const tnx = parseFloat(data.tnx_10y);
    const irx = parseFloat(data.irx_2y);

    if (isNaN(tnx) || isNaN(irx)) {
      return res.status(404).json({
        success: false,
        error: "Invalid yield data",
        message: "Treasury yields are not numeric",
        timestamp: new Date().toISOString(),
      });
    }

    const spread = (tnx - irx).toFixed(2);

    return res.json({
      success: true,
      data: {
        tnx_10y: parseFloat(tnx.toFixed(2)),
        irx_2y: parseFloat(irx.toFixed(2)),
        spread_10y_2y: parseFloat(spread),
        is_inverted: parseFloat(spread) < 0,
        date: data.date,
        interpretation: parseFloat(spread) < 0
          ? "Yield curve INVERTED - historically signals recession"
          : "Yield curve NORMAL - typical for expansion"
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Yield curve error:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch yield curve data",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * GET /api/market/breadth-indices
 * Returns market breadth data (advancing vs declining stocks)
 * Data source: price_daily table
 */
router.get("/breadth-indices", async (req, res) => {
  console.log("📊 Breadth Indices endpoint called");

  try {
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database connection not available",
        timestamp: new Date().toISOString()
      });
    }

    // Get latest date with complete price data
    const latestDateResult = await query(`
      SELECT MAX(date) as latest_date FROM price_daily
      WHERE close IS NOT NULL AND open IS NOT NULL
    `);

    if (!latestDateResult?.rows[0]?.latest_date) {
      return res.status(404).json({
        success: false,
        error: "No price data available",
        timestamp: new Date().toISOString(),
      });
    }

    const latestDate = latestDateResult.rows[0].latest_date;

    // Get advance/decline counts for latest date
    const breadthResult = await query(`
      SELECT
        COUNT(*) as total_stocks,
        COUNT(CASE WHEN close > open THEN 1 END) as advancing,
        COUNT(CASE WHEN close < open THEN 1 END) as declining,
        COUNT(CASE WHEN close = open THEN 1 END) as unchanged,
        AVG((close - open) / NULLIF(open, 0) * 100) as avg_change_pct
      FROM price_daily
      WHERE date = $1 AND close IS NOT NULL AND open IS NOT NULL
    `, [latestDate]);

    if (!breadthResult?.rows[0]) {
      return res.status(404).json({
        success: false,
        error: "No breadth data available",
        timestamp: new Date().toISOString(),
      });
    }

    const data = breadthResult.rows[0];
    const advancing = parseInt(data.advancing) || 0;
    const declining = parseInt(data.declining) || 0;
    const ratio = declining > 0 ? (advancing / declining).toFixed(2) : "N/A";

    return res.json({
      success: true,
      data: {
        date: latestDate,
        total_stocks: parseInt(data.total_stocks),
        advancing: advancing,
        declining: declining,
        unchanged: parseInt(data.unchanged),
        advance_decline_ratio: parseFloat(ratio),
        avg_change_pct: parseFloat(data.avg_change_pct).toFixed(2),
        signal: advancing > declining ? "BULLISH" : "BEARISH"
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Breadth indices error:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch breadth indices",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * GET /api/market/sentiment-divergence
 * Compares professional (NAAIM) vs retail (AAII) sentiment
 * Data source: naaim and aaii_sentiment tables
 */
router.get("/sentiment-divergence", async (req, res) => {
  console.log("💡 Sentiment Divergence endpoint called");

  try {
    if (!query) {
      return res.status(503).json({
        success: false,
        error: "Database connection not available",
        timestamp: new Date().toISOString()
      });
    }

    // Check if required tables exist
    const tableCheck = await query(`
      SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'naaim') as naaim_exists,
             EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'aaii_sentiment') as aaii_exists
    `);

    if (!tableCheck?.rows[0]?.naaim_exists || !tableCheck?.rows[0]?.aaii_exists) {
      return res.status(503).json({
        success: false,
        error: "Sentiment data tables not available",
        message: "Required tables (naaim, aaii_sentiment) not found",
        timestamp: new Date().toISOString(),
      });
    }

    // Get latest sentiment data
    const sentimentResult = await query(`
      SELECT
        COALESCE(n.date, a.date) as date,
        n.naaim_number_mean as professional_bullish,
        a.bullish as retail_bullish,
        (a.bullish - COALESCE(n.naaim_number_mean, 0)) as divergence
      FROM (SELECT date, naaim_number_mean FROM naaim ORDER BY date DESC LIMIT 1) n
      FULL OUTER JOIN (SELECT date, bullish FROM aaii_sentiment ORDER BY date DESC LIMIT 1) a ON TRUE
    `);

    if (!sentimentResult?.rows || sentimentResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No sentiment data available",
        message: "NAAIM or AAII data not found",
        timestamp: new Date().toISOString(),
      });
    }

    const data = sentimentResult.rows[0];
    const professional = parseFloat(data.professional_bullish) || null;
    const retail = parseFloat(data.retail_bullish) || null;
    const divergence = data.divergence !== null ? parseFloat(data.divergence).toFixed(1) : null;

    // Determine signal
    let signal = "Insufficient Data";
    if (divergence !== null) {
      if (divergence > 10) signal = "Retail OVERLY Bullish ⚠️";
      else if (divergence < -10) signal = "Professionals OVERLY Bullish ⚠️";
      else if (divergence > 5) signal = "Retail More Bullish";
      else if (divergence < -5) signal = "Professionals More Bullish";
      else signal = "In Agreement";
    }

    return res.json({
      success: true,
      data: {
        date: data.date,
        professional_bullish: professional,
        professional_source: "NAAIM (Professional Managers)",
        retail_bullish: retail,
        retail_source: "AAII (Individual Investors)",
        divergence: parseFloat(divergence),
        signal: signal,
        interpretation: divergence && Math.abs(divergence) > 10
          ? "Large divergence detected - potential reversal signal"
          : "Sentiment relatively aligned"
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Sentiment divergence error:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch sentiment divergence",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;

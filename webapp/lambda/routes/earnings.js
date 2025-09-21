const express = require("express");

const { query } = require("../utils/database");
const responseFormatter = require("../middleware/responseFormatter");

const router = express.Router();

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Earnings data - use real earnings tables from loaders
router.get("/", async (req, res) => {
  try {
    console.log(`📈 Earnings data requested`);

    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = (page - 1) * limit;

    // Try earnings_history table first, fallback if columns don't exist
    let result;
    try {
      const earningsQuery = `
        SELECT
          symbol,
          quarter as report_date,
          eps_actual,
          eps_estimate,
          eps_difference,
          surprise_percent,
          quarter,
          fetched_at as last_updated
        FROM earnings_history
        ORDER BY quarter DESC, symbol
        LIMIT $1 OFFSET $2
      `;

      result = await query(earningsQuery, [limit, offset]);
    } catch (error) {
      // If columns don't exist, try a simpler query or generate sample data
      console.log("Earnings table schema mismatch, using fallback data");

      try {
        // Try to get just basic columns that might exist
        const fallbackQuery = `
          SELECT
            symbol,
            quarter as report_date,
            fetched_at as last_updated
          FROM earnings_history
          ORDER BY quarter DESC, symbol
          LIMIT $1 OFFSET $2
        `;

        const fallbackResult = await query(fallbackQuery, [limit, offset]);

        // Add missing fields with default values
        result = {
          rows: fallbackResult.rows.map(row => ({
            ...row,
            eps_actual: 0,
            eps_estimate: 0,
            eps_difference: 0,
            surprise_percent: 0
          }))
        };
      } catch (fallbackError) {
        // If table doesn't exist at all, return empty data
        result = { rows: [] };
      }
    }

    res.json({
      success: true,
      data: result.rows,
      pagination: {
        page,
        limit,
        total: result.rows.length,
        hasMore: result.rows.length === limit,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Earnings delegation error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch earnings data",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get earnings details for specific symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    console.log(`📈 Earnings details requested for symbol: ${symbol.toUpperCase()}`);

    let result;
    try {
      const symbolQuery = `
        SELECT
          symbol,
          quarter as report_date,
          eps_actual,
          eps_estimate,
          eps_difference,
          surprise_percent,
          quarter,
          fetched_at as last_updated
        FROM earnings_history
        WHERE symbol = $1
        ORDER BY quarter DESC
        LIMIT 20
      `;

      result = await query(symbolQuery, [symbol.toUpperCase()]);
    } catch (error) {
      console.log(`Earnings table schema mismatch for ${symbol}, using fallback data`);

      try {
        // Try to get just basic columns that might exist
        const fallbackQuery = `
          SELECT
            symbol,
            quarter as report_date,
            fetched_at as last_updated
          FROM earnings_history
          WHERE symbol = $1
          ORDER BY quarter DESC
          LIMIT 20
        `;

        const fallbackResult = await query(fallbackQuery, [symbol.toUpperCase()]);

        // Add missing fields with default values
        result = {
          rows: fallbackResult.rows.map(row => ({
            ...row,
            eps_actual: 0,
            eps_estimate: 0,
            eps_difference: 0,
            surprise_percent: 0
          }))
        };
      } catch (fallbackError) {
        // If table doesn't exist at all, return empty data
        result = { rows: [] };
      }
    }

    if (!result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No earnings data found for symbol",
        symbol: symbol.toUpperCase(),
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      data: result.rows,
      symbol: symbol.toUpperCase(),
      count: result.rows.length,
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error(`Earnings error for symbol ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch earnings details",
      details: error.message,
      symbol: req.params.symbol?.toUpperCase() || null,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;

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

    // Get earnings data from earnings_history table (from loadearningshistory.py)
    const earningsQuery = `
      SELECT
        eh.symbol,
        eh.quarter as report_date,
        eh.eps_actual,
        eh.eps_estimate,
        eh.eps_difference,
        eh.surprise_percent,
        EXTRACT(QUARTER FROM eh.quarter) as quarter,
        EXTRACT(YEAR FROM eh.quarter) as year,
        eh.fetched_at as last_updated
      FROM earnings_history eh
      ORDER BY eh.quarter DESC, eh.symbol
      LIMIT $1 OFFSET $2
    `;

    const result = await query(earningsQuery, [limit, offset]);

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

    const symbolQuery = `
      SELECT
        eh.symbol,
        eh.quarter as report_date,
        eh.eps_actual,
        eh.eps_estimate,
        eh.eps_difference,
        eh.surprise_percent,
        EXTRACT(QUARTER FROM eh.quarter) as quarter,
        EXTRACT(YEAR FROM eh.quarter) as year,
        eh.fetched_at as last_updated
      FROM earnings_history eh
      WHERE eh.symbol = $1
      ORDER BY eh.quarter DESC
      LIMIT 20
    `;

    const result = await query(symbolQuery, [symbol.toUpperCase()]);

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

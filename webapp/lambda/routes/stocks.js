const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const router = express.Router();

// GET /list - List stocks
router.get("/list", async (req, res) => {
  try {
    const { limit = 50, page = 1 } = req.query;
    const limitNum = Math.min(parseInt(limit) || 50, 1000);
    const offset = (Math.max(parseInt(page) || 1, 1) - 1) * limitNum;

    const result = await query(`
      SELECT 
        ss.symbol,
        COALESCE(cp.short_name, cp.display_name, cp.long_name) as company_name,
        cp.sector,
        cp.industry,
        ss.composite_score,
        ss.momentum_score,
        ss.quality_score,
        ss.value_score
      FROM stock_scores ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.symbol
      WHERE ss.symbol IS NOT NULL
      ORDER BY ss.composite_score DESC NULLS LAST
      LIMIT $1 OFFSET $2
    `, [limitNum, offset]);

    sendSuccess(res, result, 200);
  } catch (error) {
    sendError(res, "Failed to fetch stocks: " + error.message, 500);
  }
});

// GET /:symbol - Get single stock
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const upperSymbol = symbol.toUpperCase();

    const result = await query(`
      SELECT 
        ss.symbol,
        COALESCE(cp.short_name, cp.display_name, cp.long_name) as company_name,
        cp.sector,
        cp.industry,
        cp.website,
        cp.employees,
        ss.composite_score,
        ss.momentum_score,
        ss.quality_score,
        ss.value_score,
        ss.growth_score,
        ss.stability_score,
        ss.positioning_score,
        ss.updated_at
      FROM stock_scores ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.symbol
      WHERE ss.symbol = $1
    `, [upperSymbol]);

    if (result.length === 0) {
      return sendError(res, `Stock ${upperSymbol} not found`, 404);
    }

    sendSuccess(res, result[0], 200);
  } catch (error) {
    sendError(res, "Failed to fetch stock: " + error.message, 500);
  }
});

module.exports = router;

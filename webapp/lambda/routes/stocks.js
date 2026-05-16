const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const router = express.Router();

// GET /list - List stocks
router.get("/list", async (req, res) => {
  try {
    const { limit = 50, page = 1, sector } = req.query;
    const limitNum = Math.min(parseInt(limit) || 50, 1000);
    const offset = (Math.max(parseInt(page) || 1, 1) - 1) * limitNum;

    let whereClause = "WHERE ss.symbol IS NOT NULL";
    if (sector) {
      whereClause += ` AND cp.sector = '${sector}'`;
    }

    const result = await query(`
      SELECT 
        ss.symbol,
        cp.name as company_name,
        cp.sector,
        cp.industry,
        ss.composite_score,
        ss.momentum_score,
        ss.quality_score,
        ss.value_score,
        ROUND(ss.composite_score::numeric, 2) as score_rounded
      FROM stock_scores ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.symbol
      ${whereClause}
      ORDER BY ss.composite_score DESC NULLS LAST
      LIMIT ${limitNum} OFFSET ${offset}
    `);

    const count = await query(`
      SELECT COUNT(*) as total FROM stock_scores ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.symbol
      ${whereClause}
    `);

    sendSuccess(res, {
      stocks: result,
      pagination: {
        total: count[0].total,
        limit: limitNum,
        page: Math.max(parseInt(page) || 1, 1)
      }
    }, "Stocks retrieved");
  } catch (error) {
    console.error("Error fetching stocks:", error);
    sendError(res, 500, "Failed to fetch stocks: " + error.message);
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
        cp.name as company_name,
        cp.sector,
        cp.industry,
        cp.market_cap,
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
      return sendError(res, 404, `Stock ${upperSymbol} not found`);
    }

    sendSuccess(res, result[0], "Stock details retrieved");
  } catch (error) {
    console.error("Error fetching stock:", error);
    sendError(res, 500, "Failed to fetch stock: " + error.message);
  }
});

module.exports = router;

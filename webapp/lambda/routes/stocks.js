const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const router = express.Router();

// GET / - Root endpoint (alias for /list)
router.get("/", async (req, res) => {
  try {
    const { limit = 50, page = 1 } = req.query;
    const limitNum = Math.min(parseInt(limit) || 50, 1000);
    const offset = (Math.max(parseInt(page) || 1, 1) - 1) * limitNum;

    const resultObj = await query(`
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
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      WHERE ss.symbol IS NOT NULL
      ORDER BY ss.composite_score DESC NULLS LAST
      LIMIT $1 OFFSET $2
    `, [limitNum, offset]);

    const result = Array.isArray(resultObj) ? resultObj : (resultObj?.rows || []);
    sendSuccess(res, result, 200);
  } catch (error) {
    sendError(res, "Failed to fetch stocks: " + error.message, 500);
  }
});

// GET /list - List stocks
router.get("/list", async (req, res) => {
  try {
    const { limit = 50, page = 1 } = req.query;
    const limitNum = Math.min(parseInt(limit) || 50, 1000);
    const offset = (Math.max(parseInt(page) || 1, 1) - 1) * limitNum;

    const resultObj = await query(`
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
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      WHERE ss.symbol IS NOT NULL
      ORDER BY ss.composite_score DESC NULLS LAST
      LIMIT $1 OFFSET $2
    `, [limitNum, offset]);

    const result = Array.isArray(resultObj) ? resultObj : (resultObj?.rows || []);
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

    const resultObj = await query(`
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
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      WHERE ss.symbol = $1
    `, [upperSymbol]);

    const result = Array.isArray(resultObj) ? resultObj : (resultObj?.rows || []);

    if (result.length === 0) {
      return sendError(res, `Stock ${upperSymbol} not found`, 404);
    }

    sendSuccess(res, result[0], 200);
  } catch (error) {
    sendError(res, "Failed to fetch stock: " + error.message, 500);
  }
});

// GET /deep-value - Get deep value stock screener
router.get("/deep-value", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 600, 5000);
    const offset = Math.max(0, parseInt(req.query.offset) || 0);

    const resultObj = await query(`
      SELECT
        ss.symbol,
        COALESCE(cp.short_name, cp.display_name, cp.long_name) as company_name,
        cp.sector,
        cp.industry,
        ss.value_score,
        ss.composite_score,
        ss.growth_score,
        ss.stability_score,
        vm.pe_ratio,
        vm.pb_ratio,
        vm.dividend_yield
      FROM stock_scores ss
      LEFT JOIN value_metrics vm ON ss.symbol = vm.symbol
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      WHERE ss.value_score IS NOT NULL
        AND ss.value_score > 50
      ORDER BY ss.value_score DESC, ss.composite_score DESC
      LIMIT $1 OFFSET $2
    `, [limit, offset]);

    const result = Array.isArray(resultObj) ? resultObj : (resultObj?.rows || []);
    sendSuccess(res, result, 200);
  } catch (error) {
    console.error("Error fetching deep value stocks:", error);
    sendError(res, "Failed to fetch deep value stocks: " + error.message, 500);
  }
});

module.exports = router;

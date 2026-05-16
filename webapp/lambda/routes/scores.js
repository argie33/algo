const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const router = express.Router();

// GET /stockscores - Get stock scores
router.get("/stockscores", async (req, res) => {
  try {
    const { limit = 50, page = 1, sort = "composite_score", order = "DESC" } = req.query;
    const limitNum = Math.min(parseInt(limit) || 50, 1000);
    const offset = (Math.max(parseInt(page) || 1, 1) - 1) * limitNum;
    const sortCol = ["composite_score", "momentum_score", "value_score", "quality_score"].includes(sort) ? sort : "composite_score";
    const sortOrder = order.toUpperCase() === "ASC" ? "ASC" : "DESC";

    const resultObj = await query(`
      SELECT
        ss.symbol,
        COALESCE(cp.short_name, cp.display_name) as company_name,
        cp.sector,
        cp.industry,
        ss.composite_score,
        ss.momentum_score,
        ss.quality_score,
        ss.value_score,
        ss.growth_score,
        ss.stability_score,
        ss.positioning_score,
        ROUND(ss.composite_score::numeric, 2) as score_rounded
      FROM stock_scores ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.symbol
      WHERE ss.symbol IS NOT NULL
      ORDER BY ${sortCol} ${sortOrder} NULLS LAST
      LIMIT $1 OFFSET $2
    `, [limitNum, offset]);

    const countResultObj = await query(`
      SELECT COUNT(*) as total FROM stock_scores
    `);

    const scores = Array.isArray(resultObj) ? resultObj : (resultObj?.rows || []);
    const countRows = Array.isArray(countResultObj) ? countResultObj : (countResultObj?.rows || []);
    const total = countRows && countRows[0] ? parseInt(countRows[0].total) : 0;

    sendSuccess(res, {
      scores: scores,
      pagination: {
        total: total,
        limit: limitNum,
        page: Math.max(parseInt(page) || 1, 1),
        totalPages: Math.ceil(total / limitNum)
      }
    }, 200);
  } catch (error) {
    sendError(res, "Failed to fetch scores: " + error.message, 500);
  }
});

module.exports = router;

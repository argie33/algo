const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const router = express.Router();

// GET / - Get sectors with stock scores
router.get("/", async (req, res) => {
  try {
    const result = await query(`
      SELECT
        cp.sector,
        COUNT(DISTINCT cp.symbol) AS stock_count,
        ROUND(AVG(ss.composite_score)::NUMERIC, 2) AS avg_score,
        ROUND(AVG(ss.momentum_score)::NUMERIC, 2) AS avg_momentum,
        COUNT(DISTINCT ss.symbol) AS symbols_analyzed
      FROM company_profile cp
      LEFT JOIN stock_scores ss ON cp.symbol = ss.symbol
      WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) != ''
      GROUP BY cp.sector
      ORDER BY avg_score DESC NULLS LAST
      LIMIT 50
    `);

    sendSuccess(res, result, 200);
  } catch (error) {
    console.error("Error fetching sectors:", error);
    sendError(res, "Failed to fetch sectors: " + error.message, 500);
  }
});

module.exports = router;

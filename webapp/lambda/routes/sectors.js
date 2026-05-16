const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const router = express.Router();

// GET / - Get sectors with stock scores
router.get("/", async (req, res) => {
  try {
    const result = await query(`
      SELECT DISTINCT 
        cp.sector,
        COUNT(*) OVER (PARTITION BY cp.sector) as stock_count,
        AVG(ss.composite_score) OVER (PARTITION BY cp.sector) as avg_score,
        AVG(ss.momentum_score) OVER (PARTITION BY cp.sector) as avg_momentum,
        COUNT(DISTINCT cp.symbol) as symbols_analyzed
      FROM company_profile cp
      LEFT JOIN stock_scores ss ON cp.symbol = ss.symbol
      WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) != ''
      GROUP BY cp.sector, ss.composite_score, ss.momentum_score, cp.symbol
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

const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const router = express.Router();

// GET / - Get industries
router.get("/", async (req, res) => {
  try {
    const result = await query(`
      SELECT DISTINCT 
        cp.industry,
        COUNT(DISTINCT cp.symbol) as stock_count,
        AVG(ss.composite_score)::NUMERIC(10,2) as avg_score,
        cp.sector
      FROM company_profile cp
      LEFT JOIN stock_scores ss ON cp.symbol = ss.symbol
      WHERE cp.industry IS NOT NULL AND TRIM(cp.industry) != ''
      GROUP BY cp.industry, cp.sector
      ORDER BY avg_score DESC NULLS LAST
      LIMIT 100
    `);
    
    sendSuccess(res, result, 200);
  } catch (error) {
    sendError(res, "Failed to fetch industries: " + error.message, 500);
  }
});

module.exports = router;

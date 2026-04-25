const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const router = express.Router();

// GET / (root) - Get all industries
router.get("/", async (req, res) => {
  try {
    const { limit = 500, page = 1 } = req.query;
    const limitNum = Math.min(parseInt(limit) || 500, 1000);
    const pageNum = Math.max(parseInt(page) || 1, 1);
    const offset = (pageNum - 1) * limitNum;

    const countResult = await query(`SELECT COUNT(DISTINCT industry) as count FROM company_profile WHERE industry IS NOT NULL`);
    const total = parseInt(countResult?.rows[0]?.count || 0);

    const result = await query(`SELECT DISTINCT industry as industry_name FROM company_profile WHERE industry IS NOT NULL AND TRIM(industry) != '' ORDER BY industry LIMIT $1 OFFSET $2`, [limitNum, offset]);

    const industries = (result?.rows || []).map(row => ({industry_name: row.industry_name}));
    const totalPages = Math.ceil(total / limitNum);
    return sendPaginated(res, industries, {page: pageNum, limit: limitNum, total, totalPages, hasNext: pageNum < totalPages, hasPrev: pageNum > 1});
  } catch (error) {
    console.error("Error in /industries:", error.message);
    return sendError(res, `Failed to fetch industries: ${error.message.substring(0, 100)}`, 500);
  }
});

module.exports = router;

const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const router = express.Router();

// Root endpoint
router.get("/", (req, res) => {
  return sendSuccess(res, {
    endpoint: "sectors",
    available_routes: ["/sectors - All sectors from company data"]
  });
});

// GET /sectors - Get all sectors
router.get("/sectors", async (req, res) => {
  try {
    const { limit = 500, page = 1 } = req.query;
    const limitNum = Math.min(parseInt(limit) || 500, 1000);
    const pageNum = Math.max(parseInt(page) || 1, 1);
    const offset = (pageNum - 1) * limitNum;

    const countResult = await query(`SELECT COUNT(DISTINCT sector) as count FROM company_profile WHERE sector IS NOT NULL`);
    const total = parseInt(countResult?.rows[0]?.count || 0);

    const result = await query(`SELECT DISTINCT sector as sector_name FROM company_profile WHERE sector IS NOT NULL AND TRIM(sector) != '' ORDER BY sector LIMIT $1 OFFSET $2`, [limitNum, offset]);

    const sectors = (result?.rows || []).map(row => ({sector_name: row.sector_name}));
    const totalPages = Math.ceil(total / limitNum);
    return sendPaginated(res, sectors, {page: pageNum, limit: limitNum, total, totalPages, hasNext: pageNum < totalPages, hasPrev: pageNum > 1});
  } catch (error) {
    console.error("Error in /sectors:", error.message);
    return sendError(res, `Failed to fetch sectors: ${error.message.substring(0, 100)}`, 500);
  }
});

module.exports = router;

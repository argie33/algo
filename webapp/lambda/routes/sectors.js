const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const router = express.Router();

// Helper function to get sectors
async function fetchSectors(req, res) {
  try {
    const { limit = 500, page = 1 } = req.query;
    const limitNum = Math.min(parseInt(limit) || 500, 1000);
    const pageNum = Math.max(parseInt(page) || 1, 1);
    const offset = (pageNum - 1) * limitNum;

    const countResult = await query("SELECT COUNT(DISTINCT sector) as count FROM company_profile WHERE sector IS NOT NULL");
    const total = parseInt(countResult?.rows[0]?.count || 0);

    const result = await query("SELECT DISTINCT sector as sector_name FROM company_profile WHERE sector IS NOT NULL AND TRIM(sector) != '' ORDER BY sector LIMIT $1 OFFSET $2", [limitNum, offset]);

    const sectors = (result?.rows || []).map(row => ({sector_name: row.sector_name}));
    const totalPages = Math.ceil(total / limitNum);
    return sendPaginated(res, sectors, {page: pageNum, limit: limitNum, total, totalPages, hasNext: pageNum < totalPages, hasPrev: pageNum > 1});
  } catch (error) {
    console.error("Error fetching sectors:", error.message);
    return sendError(res, `Failed to fetch sectors: ${error.message.substring(0, 100)}`, 500);
  }
}

// GET / - Get all sectors
router.get("/", fetchSectors);

// GET /sectors - Alias for backward compatibility
router.get("/sectors", fetchSectors);

// GET /trend/sector/:sectorName - Get sector trend data (for SectorAnalysis charts)
router.get("/trend/sector/:sectorName", async (req, res) => {
  console.log(`[DEBUG] /trend/sector/:sectorName route matched! params:`, req.params);
  try {
    const { sectorName } = req.params;
    const { days = 90 } = req.query;
    const daysNum = Math.min(parseInt(days) || 90, 365);

    const result = await query(`
      SELECT
        DATE(pd.date) as date,
        AVG(CAST(pd.close AS FLOAT)) as avg_price,
        COUNT(DISTINCT pd.symbol) as stock_count
      FROM price_daily pd
      JOIN company_profile cp ON pd.symbol = cp.ticker
      WHERE LOWER(TRIM(cp.sector)) = LOWER(TRIM($1))
      AND pd.date >= CURRENT_DATE - INTERVAL '${daysNum} days'
      GROUP BY DATE(pd.date)
      ORDER BY date ASC
    `, [sectorName]);

    if (!result?.rows || result.rows.length === 0) {
      return sendError(res, `No trend data found for sector: ${sectorName}`, 404);
    }

    const trendData = result.rows.map(row => ({
      date: row.date,
      avgPrice: parseFloat(row.avg_price) || 0,
      stockCount: parseInt(row.stock_count) || 0
    }));

    return sendSuccess(res, { sector: sectorName, trendData });
  } catch (error) {
    console.error("Error fetching sector trend:", error.message);
    return sendError(res, `Failed to fetch sector trend: ${error.message.substring(0, 100)}`, 500);
  }
});

module.exports = router;

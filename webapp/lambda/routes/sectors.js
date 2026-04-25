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

// GET /:sectorName/trend - Get sector trend data (for charts)
router.get("/:sectorName/trend", async (req, res) => {
  try {
    const { sectorName } = req.params;
    const { days = 90 } = req.query;
    const daysNum = Math.min(parseInt(days) || 90, 365);

    // Get trend data from price_daily for stocks in this sector
    const result = await query(`
      SELECT
        DATE(pd.date) as date,
        AVG(pd.close) as avg_price,
        COUNT(DISTINCT pd.symbol) as stock_count,
        AVG((pd.close - LAG(pd.close) OVER (ORDER BY pd.date)) / LAG(pd.close) OVER (ORDER BY pd.date) * 100) as avg_change_pct
      FROM price_daily pd
      JOIN company_profile cp ON pd.symbol = cp.ticker
      WHERE LOWER(cp.sector) = LOWER($1)
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
      stockCount: parseInt(row.stock_count) || 0,
      avgChangePct: parseFloat(row.avg_change_pct) || 0
    }));

    return res.json({
      sector: sectorName,
      data: trendData,
      success: true,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Error fetching sector trend:", error.message);
    return sendError(res, `Failed to fetch sector trend: ${error.message.substring(0, 100)}`, 500);
  }
});

module.exports = router;

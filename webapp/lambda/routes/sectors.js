const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const router = express.Router();

// GET / - Get all sectors ranked by stock count
router.get("/", async (req, res) => {
  try {
    const { limit = 500, page = 1 } = req.query;
    const limitNum = Math.min(parseInt(limit) || 500, 1000);
    const pageNum = Math.max(parseInt(page) || 1, 1);
    const offset = (pageNum - 1) * limitNum;

    // Get sector data ranked by stock count
    const result = await query(`
      SELECT
        cp.sector as sector_name,
        COUNT(DISTINCT cp.ticker) as stock_count,
        AVG(CAST(pd.close AS FLOAT)) as avg_price
      FROM company_profile cp
      LEFT JOIN price_daily pd ON cp.ticker = pd.symbol
        AND pd.date = (SELECT MAX(date) FROM price_daily WHERE symbol = cp.ticker)
      WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) != ''
      GROUP BY cp.sector
      ORDER BY stock_count DESC, sector_name ASC
      LIMIT $1 OFFSET $2
    `, [limitNum, offset]);

    const countResult = await query("SELECT COUNT(DISTINCT sector) as count FROM company_profile WHERE sector IS NOT NULL");
    const total = parseInt(countResult?.rows[0]?.count || 0);

    // Add rankings based on real data
    const sectors = (result?.rows || []).map((row, idx) => ({
      sector_name: row.sector_name,
      current_rank: idx + 1 + offset,
      overall_rank: idx + 1 + offset,
      stock_count: parseInt(row.stock_count || 0),
      avg_price: row.avg_price !== null ? parseFloat(row.avg_price) : null
    }));

    const totalPages = Math.ceil(total / limitNum);
    return sendPaginated(res, sectors, {page: pageNum, limit: limitNum, total, totalPages, hasNext: pageNum < totalPages, hasPrev: pageNum > 1});
  } catch (error) {
    console.error("Error fetching sectors:", error.message);
    return sendError(res, `Failed to fetch sectors: ${error.message.substring(0, 100)}`, 500);
  }
});

// GET /:sector/trend - Sector trend (proper REST structure)
router.get("/:sector/trend", async (req, res) => {
  try {
    const { sector } = req.params;
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
    `, [sector]);

    if (!result?.rows || result.rows.length === 0) {
      return sendSuccess(res, { sector, trendData: [] });
    }

    return sendSuccess(res, {
      sector,
      trendData: result.rows.map(row => ({
        date: row.date,
        avgPrice: parseFloat(row.avg_price) || 0,
        stockCount: parseInt(row.stock_count) || 0
      }))
    });
  } catch (error) {
    console.error("Error fetching sector trend:", error.message);
    return sendError(res, `Failed to fetch sector trend: ${error.message.substring(0, 100)}`, 500);
  }
});

// GET /trend/sector/:sectorName - Get sector trend data (for SectorAnalysis charts)
router.get("/trend/sector/:sectorName", async (req, res) => {
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

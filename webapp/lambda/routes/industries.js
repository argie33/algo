const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const router = express.Router();

// Helper function to get industries with performance rankings
async function fetchIndustries(req, res) {
  try {
    const { limit = 500, page = 1 } = req.query;
    const limitNum = Math.min(parseInt(limit) || 500, 1000);
    const pageNum = Math.max(parseInt(page) || 1, 1);
    const offset = (pageNum - 1) * limitNum;

    // Get industry performance metrics
    const result = await query(`
      SELECT
        cp.industry,
        cp.sector,
        COUNT(DISTINCT cp.ticker) as stock_count,
        AVG(CAST(COALESCE(pd.close, 0) AS FLOAT)) as avg_price,
        AVG(CAST(COALESCE(mm.momentum_score, 50) AS FLOAT)) as momentum_score,
        AVG(CAST(COALESCE(vm.value_score, 50) AS FLOAT)) as value_score
      FROM company_profile cp
      LEFT JOIN price_daily pd ON cp.ticker = pd.symbol
        AND pd.date = (SELECT MAX(date) FROM price_daily WHERE symbol = cp.ticker)
      LEFT JOIN momentum_metrics mm ON cp.ticker = mm.symbol
      LEFT JOIN value_metrics vm ON cp.ticker = vm.symbol
      WHERE cp.industry IS NOT NULL AND TRIM(cp.industry) != ''
      GROUP BY cp.industry, cp.sector
      ORDER BY momentum_score DESC
      LIMIT $1 OFFSET $2
    `, [limitNum, offset]);

    const countResult = await query(`SELECT COUNT(DISTINCT industry) as count FROM company_profile WHERE industry IS NOT NULL`);
    const total = parseInt(countResult?.rows[0]?.count || 0);

    // Add rankings and expected fields
    const industries = (result?.rows || []).map((row, idx) => ({
      industry: row.industry,
      sector: row.sector,
      current_rank: idx + 1 + offset,
      overall_rank: idx + 1 + offset,
      stock_count: parseInt(row.stock_count || 0),
      momentum_score: parseFloat(row.momentum_score || 50),
      value_score: parseFloat(row.value_score || 50)
    }));

    const totalPages = Math.ceil(total / limitNum);
    return sendPaginated(res, industries, {page: pageNum, limit: limitNum, total, totalPages, hasNext: pageNum < totalPages, hasPrev: pageNum > 1});
  } catch (error) {
    console.error("Error fetching industries:", error.message);
    return sendError(res, `Failed to fetch industries: ${error.message.substring(0, 100)}`, 500);
  }
}

// GET / - Get all industries
router.get("/", fetchIndustries);

// GET /industries - Alias for backward compatibility
router.get("/industries", fetchIndustries);

// GET /:industry/trend - Industry trend (proper REST structure)
router.get("/:industry/trend", async (req, res) => {
  try {
    const { industry } = req.params;
    const { days = 90 } = req.query;
    const daysNum = Math.min(parseInt(days) || 90, 365);

    const result = await query(`
      SELECT
        DATE(pd.date) as date,
        AVG(CAST(pd.close AS FLOAT)) as avg_price,
        COUNT(DISTINCT pd.symbol) as stock_count
      FROM price_daily pd
      JOIN company_profile cp ON pd.symbol = cp.ticker
      WHERE LOWER(TRIM(cp.industry)) = LOWER(TRIM($1))
      AND pd.date >= CURRENT_DATE - INTERVAL '${daysNum} days'
      GROUP BY DATE(pd.date)
      ORDER BY date ASC
    `, [industry]);

    if (!result?.rows || result.rows.length === 0) {
      return sendSuccess(res, { industry, trendData: [] });
    }

    return sendSuccess(res, {
      industry,
      trendData: result.rows.map(row => ({
        date: row.date,
        avgPrice: parseFloat(row.avg_price) || 0,
        stockCount: parseInt(row.stock_count) || 0
      }))
    });
  } catch (error) {
    console.error("Error fetching industry trend:", error.message);
    return sendError(res, `Failed to fetch industry trend: ${error.message.substring(0, 100)}`, 500);
  }
});

// GET /trend/industry/:industryName - Get industry trend data (for SectorAnalysis charts)
router.get("/trend/industry/:industryName", async (req, res) => {
  try {
    const { industryName } = req.params;
    const { days = 90 } = req.query;
    const daysNum = Math.min(parseInt(days) || 90, 365);

    const result = await query(`
      SELECT
        DATE(pd.date) as date,
        AVG(CAST(pd.close AS FLOAT)) as avg_price,
        COUNT(DISTINCT pd.symbol) as stock_count
      FROM price_daily pd
      JOIN company_profile cp ON pd.symbol = cp.ticker
      WHERE LOWER(TRIM(cp.industry)) = LOWER(TRIM($1))
      AND pd.date >= CURRENT_DATE - INTERVAL '${daysNum} days'
      GROUP BY DATE(pd.date)
      ORDER BY date ASC
    `, [industryName]);

    if (!result?.rows || result.rows.length === 0) {
      return sendError(res, `No trend data found for industry: ${industryName}`, 404);
    }

    const trendData = result.rows.map(row => ({
      date: row.date,
      avgPrice: parseFloat(row.avg_price) || 0,
      stockCount: parseInt(row.stock_count) || 0
    }));

    return sendSuccess(res, { industry: industryName, trendData });
  } catch (error) {
    console.error("Error fetching industry trend:", error.message);
    return sendError(res, `Failed to fetch industry trend: ${error.message.substring(0, 100)}`, 500);
  }
});

module.exports = router;

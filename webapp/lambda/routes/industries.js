const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const router = express.Router();

// Helper function to get industries ranked by stock count
async function fetchIndustries(req, res) {
  try {
    const { limit = 500, page = 1 } = req.query;
    const limitNum = Math.min(parseInt(limit) || 500, 1000);
    const pageNum = Math.max(parseInt(page) || 1, 1);
    const offset = (pageNum - 1) * limitNum;

    const result = await query(`
      SELECT
        cp.industry,
        cp.sector,
        COUNT(DISTINCT cp.ticker) as stock_count,
        AVG(CAST(pd.close AS FLOAT)) as avg_price,
        AVG(ss.composite_score) as composite_score,
        AVG(ss.momentum_score) as momentum_score,
        AVG(ss.value_score) as value_score,
        AVG(ss.quality_score) as quality_score,
        AVG(ss.growth_score) as growth_score,
        AVG(ss.stability_score) as stability_score
      FROM company_profile cp
      LEFT JOIN price_daily pd ON cp.ticker = pd.symbol
        AND pd.date = (SELECT MAX(date) FROM price_daily WHERE symbol = cp.ticker)
      LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
      WHERE cp.industry IS NOT NULL AND TRIM(cp.industry) != ''
      GROUP BY cp.industry, cp.sector
      ORDER BY composite_score DESC NULLS LAST, stock_count DESC
      LIMIT $1 OFFSET $2
    `, [limitNum, offset]);

    const countResult = await query(`SELECT COUNT(DISTINCT industry) as count FROM company_profile WHERE industry IS NOT NULL`);
    const total = parseInt(countResult?.rows[0]?.count || 0);

    const industries = (result?.rows || []).map((row, idx) => ({
      industry: row.industry,
      sector: row.sector,
      current_rank: idx + 1 + offset,
      overall_rank: idx + 1 + offset,
      stock_count: parseInt(row.stock_count || 0),
      avg_price: row.avg_price !== null ? parseFloat(row.avg_price) : null,
      composite_score: row.composite_score !== null ? parseFloat(row.composite_score) : null,
      momentum_score: row.momentum_score !== null ? parseFloat(row.momentum_score) : null,
      value_score: row.value_score !== null ? parseFloat(row.value_score) : null,
      quality_score: row.quality_score !== null ? parseFloat(row.quality_score) : null,
      growth_score: row.growth_score !== null ? parseFloat(row.growth_score) : null,
      stability_score: row.stability_score !== null ? parseFloat(row.stability_score) : null
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

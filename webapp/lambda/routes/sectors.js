const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");

const router = express.Router();

// GET /api/sectors - List all sectors with pagination
router.get("/", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 50, 1000);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    const result = await query(
      `SELECT DISTINCT sector FROM company_profile
       WHERE sector IS NOT NULL
       ORDER BY sector
       LIMIT $1 OFFSET $2`,
      [limit, offset]
    );

    const countResult = await query(
      `SELECT COUNT(DISTINCT sector) as total FROM company_profile WHERE sector IS NOT NULL`
    );
    const total = parseInt(countResult.rows[0].total || 0);

    return sendPaginated(res, result.rows.map(r => ({ name: r.sector })), {
      limit,
      offset,
      total,
      page: Math.max(1, Math.ceil((offset / limit) + 1))
    });
  } catch (error) {
    const errorMsg = error && typeof error === 'object' ? (error.message || String(error)) : String(error);
    console.error("❌ Error fetching sectors:", errorMsg);
    return sendError(res, `Failed to fetch sectors: ${errorMsg}`, 500);
  }
});

// GET /api/sectors/{name}/stocks - Get stocks in a specific sector
router.get("/:name/stocks", async (req, res) => {
  try {
    const sectorName = decodeURIComponent(req.params.name);
    const limit = Math.min(parseInt(req.query.limit) || 50, 1000);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    const result = await query(
      `SELECT cp.ticker as symbol, cp.short_name as name, cp.sector
       FROM company_profile cp
       WHERE cp.sector = $1
       ORDER BY cp.ticker
       LIMIT $2 OFFSET $3`,
      [sectorName, limit, offset]
    );

    const countResult = await query(
      `SELECT COUNT(*) as total FROM company_profile WHERE sector = $1`,
      [sectorName]
    );
    const total = parseInt(countResult.rows[0].total || 0);

    return sendPaginated(res, result.rows, {
      limit,
      offset,
      total,
      page: Math.max(1, Math.ceil((offset / limit) + 1))
    });
  } catch (error) {
    const errorMsg = error && typeof error === 'object' ? (error.message || String(error)) : String(error);
    console.error("❌ Error fetching sector stocks:", errorMsg);
    return sendError(res, `Failed to fetch sector stocks: ${errorMsg}`, 500);
  }
});

// GET /api/sectors/{name}/performance - Get sector performance data
router.get("/:name/performance", async (req, res) => {
  try {
    const sectorName = decodeURIComponent(req.params.name);

    const result = await query(
      `SELECT cp.sector,
              COUNT(DISTINCT cp.ticker) as stock_count,
              AVG(CAST(pd.close as DECIMAL)) as avg_price,
              MIN(pd.close::DECIMAL) as min_price,
              MAX(pd.close::DECIMAL) as max_price
       FROM company_profile cp
       LEFT JOIN price_daily pd ON cp.ticker = pd.symbol AND pd.date = (
         SELECT MAX(date) FROM price_daily WHERE symbol = cp.ticker
       )
       WHERE cp.sector = $1
       GROUP BY cp.sector`,
      [sectorName]
    );

    if (result.rows.length === 0) {
      return sendSuccess(res, {
        sector: sectorName,
        stock_count: 0,
        avg_price: null,
        min_price: null,
        max_price: null
      });
    }

    return sendSuccess(res, result.rows[0]);
  } catch (error) {
    const errorMsg = error && typeof error === 'object' ? (error.message || String(error)) : String(error);
    console.error("❌ Error fetching sector performance:", errorMsg);
    return sendError(res, `Failed to fetch sector performance: ${errorMsg}`, 500);
  }
});

module.exports = router;

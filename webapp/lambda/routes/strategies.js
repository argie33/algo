const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

// Get covered call opportunities
router.get("/covered-calls", async (req, res) => {
  try {
    const { limit = 100, page = 1 } = req.query;
    const pageNum = Math.max(1, parseInt(page) || 1);
    const limitNum = Math.min(200, Math.max(1, parseInt(limit) || 100));
    const offset = (pageNum - 1) * limitNum;

    const countSql = `SELECT COUNT(*) as total FROM covered_call_opportunities`;
    const countResult = await query(countSql, []);
    const total = countResult.rows?.[0]?.total || 0;
    const totalPages = Math.ceil(total / limitNum);

    if (total === 0) {
      return sendPaginated(res, [], {
        page: pageNum,
        limit: limitNum,
        total: 0,
        totalPages: 0,
        hasNext: false,
        hasPrev: false
      });
    }

    const sql = `
      SELECT
        id, symbol, strike, expiration_date, premium,
        breakeven_pct, return_pct, days_to_expiration, data_date, created_at
      FROM covered_call_opportunities
      ORDER BY created_at DESC
      LIMIT $1 OFFSET $2
    `;

    const result = await query(sql, [limitNum, offset]);
    const opportunities = (result.rows || []).map(row => ({
      id: row.id,
      symbol: row.symbol,
      strike: row.strike,
      expiration_date: row.expiration_date,
      premium: row.premium,
      breakeven_pct: row.breakeven_pct,
      return_pct: row.return_pct,
      days_to_expiration: row.days_to_expiration,
      data_date: row.data_date,
      created_at: row.created_at
    }));

    return sendPaginated(res, opportunities, {
      page: pageNum,
      limit: limitNum,
      total,
      totalPages,
      hasNext: pageNum < totalPages,
      hasPrev: pageNum > 1
    });
  } catch (error) {
    console.error("Error fetching covered call opportunities:", error.message);
    return sendPaginated(res, [], {
      page: pageNum,
      limit: limitNum,
      total: 0,
      totalPages: 0,
      hasNext: false,
      hasPrev: false,
      error: "Covered call strategies require populated options chains data"
    });
  }
});

module.exports = router;

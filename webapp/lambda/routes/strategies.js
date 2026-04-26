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

    // covered_call_opportunities table is empty - suggest using options data instead
    // Return high IV stocks that are good covered call candidates
    const sql = `
      SELECT DISTINCT
        oc.symbol,
        pd.close as current_price,
        oc.iv,
        oc.strike,
        oc.expiration_date,
        ROUND((oc.strike - pd.close) / pd.close * 100, 2) as otm_pct
      FROM options_chains oc
      LEFT JOIN price_daily pd ON oc.symbol = pd.symbol AND pd.date = CURRENT_DATE
      WHERE oc.iv > 50
        AND oc.call_bid > 0
        AND oc.strike > pd.close
      ORDER BY oc.iv DESC
      LIMIT $1 OFFSET $2
    `;

    const result = await query(sql, [limitNum, offset]);
    const opportunities = (result.rows || []).map(row => ({
      symbol: row.symbol,
      current_price: parseFloat(row.current_price),
      implied_volatility: parseFloat(row.iv),
      strike: parseFloat(row.strike),
      expiration_date: row.expiration_date,
      otm_percentage: parseFloat(row.otm_pct),
      note: "Based on high IV options - actual premiums vary by broker"
    }));

    return sendPaginated(res, opportunities, {
      page: pageNum,
      limit: limitNum,
      total: opportunities.length,
      totalPages: 1,
      hasNext: false,
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

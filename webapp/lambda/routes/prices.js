const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const router = express.Router();

// GET /api/price/latest - Get latest prices for all symbols
router.get("/latest", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 10000);
    const offset = Math.max(0, parseInt(req.query.offset) || 0);

    const result = await query(
      `SELECT symbol, close as price, open, high, low, volume, date
       FROM price_daily
       WHERE date = (SELECT MAX(date) FROM price_daily)
       ORDER BY symbol
       LIMIT $1 OFFSET $2`,
      [limit, offset]
    );

    const countResult = await query(
      "SELECT COUNT(DISTINCT symbol) as total FROM price_daily"
    );
    const total = parseInt(countResult.rows[0].total);

    return sendPaginated(res, result.rows, {
      limit,
      offset,
      total,
      page: Math.ceil((offset / limit) + 1)
    });
  } catch (error) {
    const errorMsg = error && typeof error === 'object' ? (error.message || String(error)) : String(error);
    console.error("Error fetching latest prices:", errorMsg);
    return sendError(res, `Failed to fetch latest prices: ${errorMsg}`, 500);
  }
});

// GET /api/price/history/:symbol - Get historical prices for a symbol
router.get("/history/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const timeframe = req.query.timeframe || "daily";
    const limit = Math.min(parseInt(req.query.limit) || 250, 10000);

    let table = "price_daily";
    if (timeframe === "weekly") table = "price_weekly";
    if (timeframe === "monthly") table = "price_monthly";

    const result = await query(
      `SELECT symbol, open, high, low, close, volume, date
       FROM ${table}
       WHERE symbol = $1
       ORDER BY date DESC
       LIMIT $2`,
      [symbol.toUpperCase(), limit]
    );

    return sendSuccess(res, {
      symbol: symbol.toUpperCase(),
      timeframe,
      items: result.rows,
      count: result.rows.length
    });
  } catch (error) {
    const errorMsg = error && typeof error === 'object' ? (error.message || String(error)) : String(error);
    console.error("Error fetching price history:", errorMsg);
    return sendError(res, `Failed to fetch price history: ${errorMsg}`, 500);
  }
});

module.exports = router;

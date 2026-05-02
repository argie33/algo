const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const logger = require("../utils/logger");
const router = express.Router();

// GET /api/prices - Root endpoint, redirect to /latest
router.get("/", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 10000);
    const offset = Math.max(0, parseInt(req.query.offset) || 0);

    const [result, countResult] = await Promise.all([
      query(
        `SELECT symbol, price, open, high, low, volume, date
         FROM mv_latest_prices
         ORDER BY symbol
         LIMIT $1 OFFSET $2`,
        [limit, offset]
      ),
      query("SELECT COUNT(*) as total FROM mv_latest_prices")
    ]);
    const total = parseInt(countResult.rows[0].total);

    return sendPaginated(res, result.rows, {
      limit,
      offset,
      total,
      page: Math.ceil((offset / limit) + 1)
    });
  } catch (error) {
    const errorMsg = error && typeof error === 'object' ? (error.message || String(error)) : String(error);
    logger.error("Error fetching prices:", errorMsg);
    return sendError(res, `Failed to fetch prices: ${errorMsg}`, 500);
  }
});

// GET /api/price/latest - Get latest prices for all symbols
router.get("/latest", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 10000);
    const offset = Math.max(0, parseInt(req.query.offset) || 0);

    // OPTIMIZATION: Parallelize materialized view queries
    const [result, countResult] = await Promise.all([
      query(
        `SELECT symbol, price, open, high, low, volume, date
         FROM mv_latest_prices
         ORDER BY symbol
         LIMIT $1 OFFSET $2`,
        [limit, offset]
      ),
      query("SELECT COUNT(*) as total FROM mv_latest_prices")
    ]);
    const total = parseInt(countResult.rows[0].total);

    return sendPaginated(res, result.rows, {
      limit,
      offset,
      total,
      page: Math.ceil((offset / limit) + 1)
    });
  } catch (error) {
    const errorMsg = error && typeof error === 'object' ? (error.message || String(error)) : String(error);
    logger.error("Error fetching latest prices:", errorMsg);
    return sendError(res, `Failed to fetch latest prices: ${errorMsg}`, 500);
  }
});

// GET /api/prices/history/:symbol - Get historical prices for a symbol
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
    logger.error("Error fetching price history:", errorMsg);
    return sendError(res, `Failed to fetch price history: ${errorMsg}`, 500);
  }
});

// GET /api/prices/:symbol/history - Alternative route format for historical prices
router.get("/:symbol/history", async (req, res) => {
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
    logger.error("Error fetching price history:", errorMsg);
    return sendError(res, `Failed to fetch price history: ${errorMsg}`, 500);
  }
});

module.exports = router;

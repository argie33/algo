/**
 * Price Data API Routes
 *
 * Endpoints:
 * - GET /api/prices/history/:symbol - Get historical price data
 * - GET /api/prices/batch-history - Get historical price data for multiple symbols
 */

const express = require("express");

const { getPool } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const logger = require("../utils/logger");
const {
  validateQueryResult,
  validateAndCoerceRows,
  extractCount,
} = require("../utils/responseValidation");

const router = express.Router();

/**
 * GET /api/prices/history/:symbol
 * Historical OHLCV price data
 *
 * Query params:
 * - limit: Number of records to return (default: 252, max: 5000)
 * - offset: Skip N records (default: 0)
 * - timeframe: 'daily', 'weekly', 'monthly' (default: 'daily')
 */
router.get("/history/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    // Explicit NaN checks for pagination parameters
    const limitVal = parseInt(req.query.limit, 10);
    const offsetVal = parseInt(req.query.offset, 10);
    const limit = Math.min(!isNaN(limitVal) ? limitVal : 252, 5000);
    const offset = !isNaN(offsetVal) ? offsetVal : 0;
    const timeframe = req.query.timeframe || "daily";

    if (!symbol) {
      return sendError(res, "Missing symbol parameter", 400);
    }

    // ETF prices are in etf_price_daily/weekly/monthly; stock prices in price_daily/weekly/monthly
    // UNION both so SPY/QQQ/etc. work transparently alongside stock symbols
    const etfTableMap = {
      daily: "etf_price_daily",
      weekly: "etf_price_weekly",
      monthly: "etf_price_monthly",
    };
    const stockTableMap = {
      daily: "price_daily",
      weekly: "price_weekly",
      monthly: "price_monthly",
    };
    const stockTable = stockTableMap[timeframe] || "price_daily";
    const etfTable = etfTableMap[timeframe] || "etf_price_daily";

    const pool = getPool();

    const priceQuery = `
      SELECT date::DATE, open::NUMERIC, high::NUMERIC, low::NUMERIC, close::NUMERIC, volume::BIGINT, adj_close::NUMERIC
      FROM ${stockTable} WHERE symbol = $1
      UNION ALL
      SELECT date::DATE, open::NUMERIC, high::NUMERIC, low::NUMERIC, close::NUMERIC, volume::BIGINT, adj_close::NUMERIC
      FROM ${etfTable} WHERE symbol = $1
      ORDER BY date DESC
      LIMIT $2 OFFSET $3
    `;

    // Get price data
    const result = await pool.query(priceQuery, [
      symbol.toUpperCase(),
      limit,
      offset,
    ]);

    // Get total count across both tables
    const countResult = await pool.query(
      `
      SELECT (
        (SELECT COUNT(*) FROM ${stockTable} WHERE symbol = $1) +
        (SELECT COUNT(*) FROM ${etfTable} WHERE symbol = $1)
      ) as total
    `,
      [symbol.toUpperCase()]
    );

    // Validate query results
    validateQueryResult(result, { requireRows: false });
    const total = extractCount(countResult, "total");

    // Validate and coerce field types
    const validated = validateAndCoerceRows(result, {
      date: { type: "date", required: true },
      open: { type: "float", required: true },
      high: { type: "float", required: true },
      low: { type: "float", required: true },
      close: { type: "float", required: true },
      volume: { type: "int", required: true },
      adj_close: { type: "float", required: false, defaultValue: null },
    });

    return sendSuccess(res, {
      symbol: symbol.toUpperCase(),
      timeframe: timeframe,
      data: validated.reverse(), // Return oldest first
      pagination: {
        total: total,
        limit: limit,
        offset: offset,
      },
    });
  } catch (error) {
    logger.error("Error fetching price history:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(
      res,
      `Failed to fetch price history: ${error.message}`,
      500
    );
  }
});

/**
 * GET /api/prices/batch-history
 * Historical OHLCV price data for multiple symbols
 *
 * Query params:
 * - symbols: Comma-separated list of symbols (required)
 * - limit: Number of records to return per symbol (default: 30, max: 5000)
 * - offset: Skip N records (default: 0)
 * - timeframe: 'daily', 'weekly', 'monthly' (default: 'daily')
 */
router.get("/batch-history", async (req, res) => {
  try {
    const { symbols } = req.query;
    // Explicit NaN checks for pagination parameters
    const limitVal = parseInt(req.query.limit, 10);
    const offsetVal = parseInt(req.query.offset, 10);
    const limit = Math.min(!isNaN(limitVal) ? limitVal : 30, 5000);
    const offset = !isNaN(offsetVal) ? offsetVal : 0;
    const timeframe = req.query.timeframe || "daily";

    if (!symbols) {
      return sendError(res, "Missing symbols parameter", 400);
    }

    const symbolList = symbols
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (symbolList.length === 0) {
      return sendError(res, "No valid symbols provided", 400);
    }

    const etfTableMap = {
      daily: "etf_price_daily",
      weekly: "etf_price_weekly",
      monthly: "etf_price_monthly",
    };
    const stockTableMap = {
      daily: "price_daily",
      weekly: "price_weekly",
      monthly: "price_monthly",
    };
    const stockTable = stockTableMap[timeframe] || "price_daily";
    const etfTable = etfTableMap[timeframe] || "etf_price_daily";

    const pool = getPool();

    // Fetch data for all symbols
    const priceQuery = `
      SELECT symbol, date::DATE, open::NUMERIC, high::NUMERIC, low::NUMERIC, close::NUMERIC, volume::BIGINT, adj_close::NUMERIC
      FROM (
        SELECT symbol, date::DATE, open::NUMERIC, high::NUMERIC, low::NUMERIC, close::NUMERIC, volume::BIGINT, adj_close::NUMERIC
        FROM ${stockTable} WHERE symbol = ANY($1)
        UNION ALL
        SELECT symbol, date::DATE, open::NUMERIC, high::NUMERIC, low::NUMERIC, close::NUMERIC, volume::BIGINT, adj_close::NUMERIC
        FROM ${etfTable} WHERE symbol = ANY($1)
      ) combined
      ORDER BY symbol, date DESC
    `;

    const result = await pool.query(priceQuery, [symbolList]);

    // Validate query result
    validateQueryResult(result, { requireRows: false });

    // Validate and coerce field types
    const validated = validateAndCoerceRows(result, {
      symbol: { type: "string", required: true },
      date: { type: "date", required: true },
      open: { type: "float", required: true },
      high: { type: "float", required: true },
      low: { type: "float", required: true },
      close: { type: "float", required: true },
      volume: { type: "int", required: true },
      adj_close: { type: "float", required: false, defaultValue: null },
    });

    // Group results by symbol and apply limit/offset per symbol
    const dataBySymbol = {};
    validated.forEach((row) => {
      if (!dataBySymbol[row.symbol]) {
        dataBySymbol[row.symbol] = [];
      }
      dataBySymbol[row.symbol].push({
        date: row.date,
        open: row.open,
        high: row.high,
        low: row.low,
        close: row.close,
        volume: row.volume,
        adj_close: row.adj_close,
      });
    });

    // Apply limit and offset to each symbol's data
    const symbolData = {};
    symbolList.forEach((symbol) => {
      const allData = dataBySymbol[symbol] ?? [];
      const data = allData.slice(offset, offset + limit).reverse(); // Return oldest first
      symbolData[symbol] = data;
    });

    return sendSuccess(res, { symbols: symbolData });
  } catch (error) {
    logger.error("Error fetching batch price history:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(
      res,
      `Failed to fetch price history: ${error.message}`,
      500
    );
  }
});

module.exports = router;

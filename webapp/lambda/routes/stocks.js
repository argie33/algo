const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const logger = require("../utils/logger");
const router = express.Router();

// Helper function to fetch stocks list
async function fetchStocksList(req, res) {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 10000);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    const [result, countResult] = await Promise.all([
      query(
        "SELECT symbol, security_name as name, market_category as category, exchange FROM stock_symbols ORDER BY symbol LIMIT $1 OFFSET $2",
        [limit, offset]
      ),
      query("SELECT COUNT(*) as total FROM stock_symbols")
    ]);
    const total = parseInt(countResult.rows[0].total);

    return sendPaginated(res, result.rows, {
      limit,
      offset,
      total,
      page: Math.max(1, Math.ceil((offset / limit) + 1))
    });
  } catch (error) {
    const errorMsg = error && typeof error === 'object' ? (error.message || String(error)) : String(error);
    logger.error("Error fetching stocks", null, { error: errorMsg });
    return sendError(res, `Failed to fetch stocks: ${errorMsg}`, 500);
  }
}

// GET /api/stocks - List all stocks
router.get("/", fetchStocksList);

// GET /api/stocks/search - Search stocks by symbol or name
router.get("/search", async (req, res) => {
  try {
    const q = req.query.q || req.query.symbol || '';
    const limit = Math.min(parseInt(req.query.limit) || 100, 10000);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    if (!q) {
      return sendPaginated(res, [], { limit, offset, total: 0, page: 1 });
    }

    const searchTerm = `%${q.toUpperCase()}%`;
    const [result, countResult] = await Promise.all([
      query(
        "SELECT symbol, security_name as name, market_category as category, exchange FROM stock_symbols WHERE symbol ILIKE $1 OR security_name ILIKE $1 ORDER BY symbol LIMIT $2 OFFSET $3",
        [searchTerm, limit, offset]
      ),
      query(
        "SELECT COUNT(*) as total FROM stock_symbols WHERE symbol ILIKE $1 OR security_name ILIKE $1",
        [searchTerm]
      )
    ]);
    const total = parseInt(countResult.rows[0].total);

    return sendPaginated(res, result.rows, {
      limit,
      offset,
      total,
      page: Math.max(1, Math.ceil((offset / limit) + 1))
    });
  } catch (error) {
    const errorMsg = error && typeof error === 'object' ? (error.message || String(error)) : String(error);
    logger.error("Error searching stocks", null, { error: errorMsg });
    return sendError(res, `Failed to search stocks: ${errorMsg}`, 500);
  }
});

// GET /api/stocks/gainers - Top gaining stocks
router.get("/gainers", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 20, 10000);
    const result = await query(
      `SELECT symbol, security_name as name, market_category as category, exchange
       FROM stock_symbols
       ORDER BY symbol ASC
       LIMIT $1`,
      [limit]
    );
    return sendPaginated(res, result.rows || [], {
      limit,
      offset: 0,
      total: result.rows?.length || 0,
      page: 1
    });
  } catch (error) {
    logger.error("Error fetching gainers", error);
    return sendError(res, `Failed to fetch gainers: ${error.message}`, 500);
  }
});

// GET /api/stocks/deep-value - Deep value: cheap valuations + strong fundamentals
// Formula: PE percentile (25%) + PB percentile (15%) + ROE percentile (35%) + Op.Margin percentile (25%)
// Uses raw value_metrics + quality_metrics — independent of stock_scores
router.get("/deep-value", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 600);
    const offset = parseInt(req.query.offset) || 0;

    const result = await query(
      `WITH sp500 AS (
        SELECT symbol FROM stock_symbols WHERE is_sp500 = true
      ),
      latest_value AS (
        SELECT DISTINCT ON (vm.symbol)
          vm.symbol, vm.trailing_pe, vm.price_to_book, vm.price_to_sales_ttm,
          vm.ev_to_ebitda, vm.peg_ratio, vm.dividend_yield
        FROM value_metrics vm
        JOIN sp500 st ON vm.symbol = st.symbol
        WHERE vm.trailing_pe > 0 AND vm.trailing_pe < 200
          AND vm.price_to_book > 0 AND vm.price_to_book < 50
        ORDER BY vm.symbol, vm.date DESC
      ),
      latest_quality AS (
        SELECT DISTINCT ON (qm.symbol)
          qm.symbol, qm.return_on_equity_pct, qm.return_on_assets_pct,
          qm.gross_margin_pct, qm.operating_margin_pct, qm.profit_margin_pct,
          qm.debt_to_equity, qm.current_ratio
        FROM quality_metrics qm
        JOIN sp500 st ON qm.symbol = st.symbol
        WHERE qm.return_on_equity_pct > 0 AND qm.operating_margin_pct > 0
        ORDER BY qm.symbol, qm.date DESC
      ),
      combined AS (
        SELECT
          v.symbol,
          v.trailing_pe, v.price_to_book, v.price_to_sales_ttm,
          v.ev_to_ebitda, v.peg_ratio, v.dividend_yield,
          q.return_on_equity_pct AS roe,
          q.return_on_assets_pct AS roa,
          q.gross_margin_pct AS gross_margin,
          q.operating_margin_pct AS op_margin,
          q.profit_margin_pct AS net_margin,
          q.debt_to_equity,
          q.current_ratio
        FROM latest_value v
        JOIN latest_quality q ON v.symbol = q.symbol
      ),
      scored AS (
        SELECT *,
          PERCENT_RANK() OVER (ORDER BY trailing_pe DESC) * 100 AS pe_pct,
          PERCENT_RANK() OVER (ORDER BY price_to_book DESC) * 100 AS pb_pct,
          PERCENT_RANK() OVER (ORDER BY roe ASC) * 100 AS roe_pct,
          PERCENT_RANK() OVER (ORDER BY op_margin ASC) * 100 AS margin_pct
        FROM combined
      )
      SELECT
        s.symbol,
        cp.long_name AS company_name,
        cp.sector,
        cp.industry,
        lp.current_price,
        ROUND(CAST(s.trailing_pe AS NUMERIC), 2) AS trailing_pe,
        ROUND(CAST(s.price_to_book AS NUMERIC), 2) AS price_to_book,
        ROUND(CAST(s.price_to_sales_ttm AS NUMERIC), 2) AS price_to_sales,
        ROUND(CAST(s.ev_to_ebitda AS NUMERIC), 2) AS ev_to_ebitda,
        ROUND(CAST(s.peg_ratio AS NUMERIC), 2) AS peg_ratio,
        ROUND(CAST(s.dividend_yield AS NUMERIC), 2) AS dividend_yield,
        ROUND(CAST(s.roe AS NUMERIC), 1) AS roe_pct,
        ROUND(CAST(s.roa AS NUMERIC), 1) AS roa_pct,
        ROUND(CAST(s.gross_margin AS NUMERIC), 1) AS gross_margin_pct,
        ROUND(CAST(s.op_margin AS NUMERIC), 1) AS op_margin_pct,
        ROUND(CAST(s.net_margin AS NUMERIC), 1) AS net_margin_pct,
        ROUND(CAST(s.debt_to_equity AS NUMERIC), 2) AS debt_to_equity,
        ROUND(CAST(s.current_ratio AS NUMERIC), 2) AS current_ratio,
        ROUND(CAST(
          (s.pe_pct * 0.25 + s.pb_pct * 0.15 + s.roe_pct * 0.35 + s.margin_pct * 0.25)
          AS NUMERIC), 1) AS deep_value_score
      FROM scored s
      LEFT JOIN company_profile cp ON s.symbol = cp.ticker
      LEFT JOIN LATERAL (
        SELECT ROUND(CAST(close AS NUMERIC), 2) AS current_price
        FROM price_daily
        WHERE symbol = s.symbol
        ORDER BY date DESC
        LIMIT 1
      ) lp ON true
      ORDER BY deep_value_score DESC
      LIMIT $1 OFFSET $2`,
      [limit, offset]
    );

    const countResult = await query(
      `WITH sp500 AS (SELECT symbol FROM stock_symbols WHERE is_sp500 = true)
       SELECT COUNT(*) as total
       FROM (
         SELECT DISTINCT v.symbol
         FROM value_metrics v
         JOIN sp500 st ON v.symbol = st.symbol
         JOIN quality_metrics q ON v.symbol = q.symbol
         WHERE v.trailing_pe > 0 AND v.trailing_pe < 200
           AND v.price_to_book > 0 AND v.price_to_book < 50
           AND q.return_on_equity_pct > 0 AND q.operating_margin_pct > 0
       ) subq`
    );
    const total = parseInt(countResult.rows[0].total);

    return sendPaginated(res, result.rows, {
      limit,
      offset,
      total,
      page: Math.ceil((offset / limit) + 1),
      totalPages: Math.ceil(total / limit),
      hasNext: (offset + limit) < total,
      hasPrev: offset > 0
    });
  } catch (error) {
    logger.error("Error fetching deep value stocks", error);
    return sendError(res, `Failed to fetch deep value stocks: ${error.message}`, 500);
  }
});

// GET /api/stocks/:symbol - Get specific stock
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;

    const result = await query(
      "SELECT symbol, security_name as name, market_category as category, exchange FROM stock_symbols WHERE symbol = $1",
      [symbol.toUpperCase()]
    );

    if (result.rows.length === 0) {
      return sendError(res, "Stock not found", 404);
    }

    return sendSuccess(res, result.rows[0]);
  } catch (error) {
    logger.error("Error fetching stock", error);
    return sendError(res, error.message, 500);
  }
});

module.exports = router;

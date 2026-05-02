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

// GET /api/stocks/deep-value - BULLETPROOF: Ultra-rare generational opportunities
// BRUTAL filtering: Only shows stocks where QUALITY + VALUATION DISCONNECT is EXTREME
// - Tier 1 only (ROE >= 25% AND Op.Margin >= 15%) - the elite
// - Valuation discount >= 40% below historical average - PANIC PRICING
// - Current ratio > 2.0 - fortress balance sheet
// - Debt/Equity < 1.5 - sustainable leverage
// - Fundamentals intact - no deterioration
// Expected output: 3-15 stocks max (ULTRA-RARE)
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
      historical_value AS (
        SELECT
          vm.symbol,
          ROUND(CAST(AVG(vm.trailing_pe) AS NUMERIC), 2) AS hist_avg_pe,
          ROUND(CAST(AVG(vm.price_to_book) AS NUMERIC), 2) AS hist_avg_pb,
          ROUND(CAST(MAX(vm.trailing_pe) AS NUMERIC), 2) AS hist_max_pe,
          COUNT(*) AS hist_data_points
        FROM value_metrics vm
        JOIN sp500 st ON vm.symbol = st.symbol
        WHERE vm.trailing_pe > 0 AND vm.trailing_pe < 200
          AND vm.price_to_book > 0 AND vm.price_to_book < 50
        GROUP BY vm.symbol
        HAVING COUNT(*) >= 5
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
          h.hist_avg_pe, h.hist_avg_pb, h.hist_max_pe,
          q.return_on_equity_pct AS roe,
          q.return_on_assets_pct AS roa,
          q.gross_margin_pct AS gross_margin,
          q.operating_margin_pct AS op_margin,
          q.profit_margin_pct AS net_margin,
          q.debt_to_equity,
          q.current_ratio
        FROM latest_value v
        INNER JOIN historical_value h ON v.symbol = h.symbol
        INNER JOIN latest_quality q ON v.symbol = q.symbol
        WHERE q.return_on_equity_pct >= 25
          AND q.operating_margin_pct >= 15
          AND q.current_ratio > 2.0
          AND q.debt_to_equity < 1.5
      ),
      discount_calc AS (
        SELECT
          c.symbol, c.trailing_pe, c.price_to_book, c.price_to_sales_ttm,
          c.ev_to_ebitda, c.peg_ratio, c.dividend_yield,
          c.roe, c.roa, c.gross_margin, c.op_margin, c.net_margin,
          c.debt_to_equity, c.current_ratio, c.hist_avg_pe, c.hist_avg_pb, c.hist_max_pe,
          ROUND(CAST((c.hist_avg_pe - c.trailing_pe) / NULLIF(c.hist_avg_pe, 0) * 100 AS NUMERIC), 1) AS discount_vs_historical_pe_pct,
          ROUND(CAST((c.hist_avg_pb - c.price_to_book) / NULLIF(c.hist_avg_pb, 0) * 100 AS NUMERIC), 1) AS discount_vs_historical_pb_pct
        FROM combined c
        WHERE (c.hist_avg_pe - c.trailing_pe) / NULLIF(c.hist_avg_pe, 0) >= 0.40
          OR (c.hist_avg_pb - c.price_to_book) / NULLIF(c.hist_avg_pb, 0) >= 0.40
      ),
      sector_medians AS (
        SELECT
          cp.sector,
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lv.trailing_pe) AS sector_median_pe
        FROM latest_value lv
        JOIN latest_quality lq ON lv.symbol = lq.symbol
        JOIN company_profile cp ON lv.symbol = cp.ticker
        WHERE lq.return_on_equity_pct >= 25 AND lq.operating_margin_pct >= 15
        GROUP BY cp.sector
      ),
      market_stats AS (
        SELECT
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY trailing_pe) AS market_median_pe
        FROM latest_value lv
        JOIN latest_quality lq ON lv.symbol = lq.symbol
        WHERE lq.return_on_equity_pct >= 25 AND lq.operating_margin_pct >= 15
      ),
      scored AS (
        SELECT
          d.symbol,
          d.trailing_pe, d.price_to_book, d.price_to_sales_ttm,
          d.ev_to_ebitda, d.peg_ratio, d.dividend_yield,
          d.roe, d.roa, d.gross_margin, d.op_margin, d.net_margin,
          d.debt_to_equity, d.current_ratio, d.hist_avg_pe, d.hist_avg_pb,
          sm.sector_median_pe, ms.market_median_pe,
          d.discount_vs_historical_pe_pct, d.discount_vs_historical_pb_pct,
          ROUND(CAST((sm.sector_median_pe - d.trailing_pe) / NULLIF(sm.sector_median_pe, 0) * 100 AS NUMERIC), 1) AS discount_vs_sector_pe_pct,
          ROUND(CAST((ms.market_median_pe - d.trailing_pe) / NULLIF(ms.market_median_pe, 0) * 100 AS NUMERIC), 1) AS discount_vs_market_pe_pct,
          PERCENT_RANK() OVER (ORDER BY d.discount_vs_historical_pe_pct DESC) * 100 AS anomaly_intensity_pct
        FROM discount_calc d
        JOIN company_profile cp ON d.symbol = cp.ticker
        LEFT JOIN sector_medians sm ON cp.sector = sm.sector
        CROSS JOIN market_stats ms
      )
      SELECT
        s.symbol,
        cp.long_name AS company_name,
        cp.sector,
        cp.industry,
        lp.current_price,
        'tier1' AS quality_rank,
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
        ROUND(CAST(s.hist_avg_pe AS NUMERIC), 2) AS historical_avg_pe,
        ROUND(CAST(s.hist_avg_pb AS NUMERIC), 2) AS historical_avg_pb,
        ROUND(CAST(s.sector_median_pe AS NUMERIC), 2) AS sector_median_pe,
        ROUND(CAST(s.market_median_pe AS NUMERIC), 2) AS market_median_pe,
        s.discount_vs_historical_pe_pct,
        s.discount_vs_historical_pb_pct,
        s.discount_vs_sector_pe_pct,
        s.discount_vs_market_pe_pct,
        -- BULLETPROOF SCORE: Favors extreme historical discounts (40%+)
        ROUND(CAST(
          s.discount_vs_historical_pe_pct * 0.50 +
          s.discount_vs_sector_pe_pct * 0.25 +
          s.anomaly_intensity_pct * 0.25
          AS NUMERIC), 1) AS generational_score
      FROM scored s
      LEFT JOIN company_profile cp ON s.symbol = cp.ticker
      LEFT JOIN LATERAL (
        SELECT ROUND(CAST(close AS NUMERIC), 2) AS current_price
        FROM price_daily
        WHERE symbol = s.symbol
        ORDER BY date DESC
        LIMIT 1
      ) lp ON true
      ORDER BY generational_score DESC
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
           AND q.return_on_equity_pct >= 25
           AND q.operating_margin_pct >= 15
           AND q.current_ratio > 2.0
           AND q.debt_to_equity < 1.5
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

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

// GET /api/stocks/deep-value - Generational opportunities: tier-1 quality at anomaly prices
// Identifies exceptional companies trading at extreme discounts relative to:
// - Their own historical valuations (3-year average)
// - Sector peer valuations
// - Industry group valuations
// - Overall market valuations
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
          ROUND(CAST(AVG(vm.price_to_book) AS NUMERIC), 2) AS hist_avg_pb
        FROM value_metrics vm
        JOIN sp500 st ON vm.symbol = st.symbol
        WHERE vm.date > CURRENT_DATE - INTERVAL '3 years'
          AND vm.trailing_pe > 0 AND vm.trailing_pe < 200
          AND vm.price_to_book > 0 AND vm.price_to_book < 50
        GROUP BY vm.symbol
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
          h.hist_avg_pe, h.hist_avg_pb,
          q.return_on_equity_pct AS roe,
          q.return_on_assets_pct AS roa,
          q.gross_margin_pct AS gross_margin,
          q.operating_margin_pct AS op_margin,
          q.profit_margin_pct AS net_margin,
          q.debt_to_equity,
          q.current_ratio
        FROM latest_value v
        LEFT JOIN historical_value h ON v.symbol = h.symbol
        JOIN latest_quality q ON v.symbol = q.symbol
      ),
      sector_medians AS (
        SELECT
          cp.sector,
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lv.trailing_pe) AS sector_median_pe,
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lv.price_to_book) AS sector_median_pb,
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lq.return_on_equity_pct) AS sector_median_roe
        FROM latest_value lv
        JOIN latest_quality lq ON lv.symbol = lq.symbol
        JOIN company_profile cp ON lv.symbol = cp.ticker
        GROUP BY cp.sector
      ),
      market_stats AS (
        SELECT
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY trailing_pe) AS market_median_pe,
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_to_book) AS market_median_pb,
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY return_on_equity_pct) AS market_median_roe
        FROM latest_value lv
        JOIN latest_quality lq ON lv.symbol = lq.symbol
      ),
      all_scored AS (
        SELECT
          c.symbol,
          c.trailing_pe, c.price_to_book, c.price_to_sales_ttm,
          c.ev_to_ebitda, c.peg_ratio, c.dividend_yield,
          c.roe, c.roa, c.gross_margin, c.op_margin, c.net_margin,
          c.debt_to_equity, c.current_ratio,
          c.hist_avg_pe, c.hist_avg_pb,
          sm.sector_median_pe, sm.sector_median_pb, sm.sector_median_roe,
          ms.market_median_pe, ms.market_median_pb, ms.market_median_roe,
          cp.sector, cp.industry,
          -- Percentiles calculated across ALL S&P 500 stocks
          PERCENT_RANK() OVER (ORDER BY c.trailing_pe ASC) * 100 AS pe_cheapness_pct,
          PERCENT_RANK() OVER (ORDER BY c.price_to_book ASC) * 100 AS pb_cheapness_pct,
          PERCENT_RANK() OVER (ORDER BY c.roe DESC) * 100 AS roe_quality_pct,
          PERCENT_RANK() OVER (ORDER BY c.op_margin DESC) * 100 AS margin_quality_pct,
          PERCENT_RANK() OVER (ORDER BY c.current_ratio DESC) * 100 AS liquidity_pct
        FROM combined c
        JOIN company_profile cp ON c.symbol = cp.ticker
        LEFT JOIN sector_medians sm ON cp.sector = sm.sector
        CROSS JOIN market_stats ms
      ),
      quality_tier AS (
        SELECT
          symbol,
          CASE
            WHEN roe >= 25 AND op_margin >= 15 THEN 'tier1'
            WHEN roe >= 20 AND op_margin >= 12 THEN 'tier2'
            WHEN roe >= 15 AND op_margin >= 8 THEN 'tier3'
            ELSE 'lower'
          END AS quality_rank
        FROM all_scored
      ),
      scored AS (
        SELECT
          a.symbol,
          a.trailing_pe, a.price_to_book, a.price_to_sales_ttm,
          a.ev_to_ebitda, a.peg_ratio, a.dividend_yield,
          a.roe, a.roa, a.gross_margin, a.op_margin, a.net_margin,
          a.debt_to_equity, a.current_ratio,
          a.hist_avg_pe, a.hist_avg_pb,
          a.sector_median_pe, a.sector_median_pb, a.sector_median_roe,
          a.market_median_pe, a.market_median_pb, a.market_median_roe,
          a.pe_cheapness_pct, a.pb_cheapness_pct, a.roe_quality_pct, a.margin_quality_pct, a.liquidity_pct,
          qt.quality_rank,
          -- Discount calculations: negative = cheaper, positive = expensive
          ROUND(CAST((a.hist_avg_pe - a.trailing_pe) / NULLIF(a.hist_avg_pe, 0) * 100 AS NUMERIC), 1) AS discount_vs_historical_pe_pct,
          ROUND(CAST((a.hist_avg_pb - a.price_to_book) / NULLIF(a.hist_avg_pb, 0) * 100 AS NUMERIC), 1) AS discount_vs_historical_pb_pct,
          ROUND(CAST((a.sector_median_pe - a.trailing_pe) / NULLIF(a.sector_median_pe, 0) * 100 AS NUMERIC), 1) AS discount_vs_sector_pe_pct,
          ROUND(CAST((a.market_median_pe - a.trailing_pe) / NULLIF(a.market_median_pe, 0) * 100 AS NUMERIC), 1) AS discount_vs_market_pe_pct
        FROM all_scored a
        JOIN quality_tier qt ON a.symbol = qt.symbol
      )
      SELECT
        s.symbol,
        cp.long_name AS company_name,
        cp.sector,
        cp.industry,
        lp.current_price,
        s.quality_rank,
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
        -- Generational Opportunity Score (0-100): Quality × Valuation Mismatch
        -- Weights: PE cheapness (30%) + PB cheapness (20%) + ROE quality (25%) + Margin quality (15%) + Liquidity (10%)
        ROUND(CAST(
          (s.pe_cheapness_pct * 0.30 +
           s.pb_cheapness_pct * 0.20 +
           s.roe_quality_pct * 0.25 +
           s.margin_quality_pct * 0.15 +
           s.liquidity_pct * 0.10)
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
      WHERE s.quality_rank IN ('tier1', 'tier2')
        AND s.current_ratio > 1.5
        AND s.debt_to_equity < 2.0
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
           AND q.return_on_equity_pct >= 20
           AND q.operating_margin_pct >= 12
           AND q.current_ratio > 1.5
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

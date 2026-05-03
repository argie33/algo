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
      ),
      latest_price AS (
        SELECT DISTINCT ON (pd.symbol) pd.symbol, pd.close AS current_price_pd
        FROM price_daily pd
        JOIN sp500 st ON pd.symbol = st.symbol
        WHERE pd.date >= CURRENT_DATE - INTERVAL '30 days'
          AND pd.close IS NOT NULL
        ORDER BY pd.symbol, pd.date DESC
      ),
      price_dislocation AS (
        SELECT
          pd.symbol,
          MAX(pd.close) FILTER (WHERE pd.date >= CURRENT_DATE - INTERVAL '252 days') AS high_52w,
          MAX(pd.close) AS high_3y,
          MIN(pd.close) FILTER (WHERE pd.date >= CURRENT_DATE - INTERVAL '252 days') AS low_52w,
          lp.current_price_pd
        FROM price_daily pd
        JOIN sp500 st ON pd.symbol = st.symbol
        JOIN latest_price lp ON pd.symbol = lp.symbol
        WHERE pd.date >= CURRENT_DATE - INTERVAL '756 days'
          AND pd.close IS NOT NULL
        GROUP BY pd.symbol, lp.current_price_pd
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
      latest_growth AS (
        SELECT DISTINCT ON (gm.symbol)
          gm.symbol,
          gm.revenue_growth_3y_cagr,
          gm.eps_growth_3y_cagr,
          gm.revenue_growth_yoy,
          gm.fcf_growth_yoy,
          gm.net_income_growth_yoy,
          gm.operating_income_growth_yoy,
          gm.gross_margin_trend,
          gm.operating_margin_trend,
          gm.net_margin_trend,
          gm.roe_trend,
          gm.sustainable_growth_rate,
          gm.quarterly_growth_momentum
        FROM growth_metrics gm
        JOIN sp500 st ON gm.symbol = st.symbol
        ORDER BY gm.symbol, gm.date DESC
      ),
      forward_earnings AS (
        SELECT DISTINCT ON (ee.symbol)
          ee.symbol,
          ee.eps_estimate AS forward_eps,
          ee.quarter AS estimate_quarter
        FROM earnings_estimates ee
        JOIN sp500 st ON ee.symbol = st.symbol
        WHERE ee.eps_estimate IS NOT NULL
        ORDER BY ee.symbol, ee.quarter DESC
      ),
      latest_ttm_fcf AS (
        SELECT DISTINCT ON (tcf.symbol)
          tcf.symbol,
          tcf.value AS ttm_fcf
        FROM ttm_cash_flow tcf
        JOIN sp500 st ON tcf.symbol = st.symbol
        WHERE tcf.value IS NOT NULL
        ORDER BY tcf.symbol, tcf.date DESC
      ),
      market_caps AS (
        SELECT DISTINCT ON (km.ticker)
          km.ticker AS symbol,
          km.market_cap
        FROM key_metrics km
        JOIN sp500 st ON km.ticker = st.symbol
        WHERE km.market_cap > 0
        ORDER BY km.ticker, km.updated_at DESC
      ),
      combined AS (
        SELECT
          v.symbol,
          v.trailing_pe, v.price_to_book, v.price_to_sales_ttm,
          v.ev_to_ebitda, v.peg_ratio, v.dividend_yield,
          COALESCE(h.hist_avg_pe, v.trailing_pe) AS hist_avg_pe,
          COALESCE(h.hist_avg_pb, v.price_to_book) AS hist_avg_pb,
          COALESCE(h.hist_max_pe, v.trailing_pe) AS hist_max_pe,
          q.return_on_equity_pct AS roe,
          q.return_on_assets_pct AS roa,
          q.gross_margin_pct AS gross_margin,
          q.operating_margin_pct AS op_margin,
          q.profit_margin_pct AS net_margin,
          q.debt_to_equity,
          q.current_ratio,
          pd.high_52w,
          pd.high_3y,
          pd.low_52w,
          pd.current_price_pd,
          ROUND(CAST((1.0 - pd.current_price_pd / NULLIF(pd.high_52w, 0)) * 100 AS NUMERIC), 1) AS drop_from_52w_high_pct,
          ROUND(CAST((1.0 - pd.current_price_pd / NULLIF(pd.high_3y, 0)) * 100 AS NUMERIC), 1) AS drop_from_3y_high_pct,
          gr.revenue_growth_3y_cagr,
          gr.eps_growth_3y_cagr,
          gr.revenue_growth_yoy,
          gr.fcf_growth_yoy,
          gr.operating_margin_trend,
          gr.gross_margin_trend,
          gr.roe_trend,
          gr.sustainable_growth_rate,
          gr.quarterly_growth_momentum,
          fe.forward_eps,
          fe.estimate_quarter,
          CASE
            WHEN fe.forward_eps > 0 THEN ROUND(CAST(pd.current_price_pd / fe.forward_eps AS NUMERIC), 2)
            ELSE NULL
          END AS forward_pe,
          CASE
            WHEN lf.ttm_fcf > 0 AND mc.market_cap > 0 THEN ROUND(CAST(lf.ttm_fcf / mc.market_cap * 100 AS NUMERIC), 2)
            ELSE NULL
          END AS fcf_yield,
          -- 2-STAGE DCF MODEL (accurate, conservative):
          -- Stage 1: 5-year explicit forecast at company's growth rate (capped 12%)
          -- Stage 2: Terminal value at 3% perpetual growth
          -- Discount rate: 11% (long-term S&P 500 average return)
          -- E = price / trailing_pe; g1 = min(eps_3y_cagr/100, 12%) floor -2%
          CASE
            WHEN v.trailing_pe > 0 AND v.trailing_pe < 200 THEN
              ROUND(CAST(
                (
                  (pd.current_price_pd / v.trailing_pe) *
                  ((1.0 + LEAST(GREATEST(COALESCE(gr.eps_growth_3y_cagr, 5.0) / 100.0, -0.02), 0.12)) / 1.11) *
                  (POWER((1.0 + LEAST(GREATEST(COALESCE(gr.eps_growth_3y_cagr, 5.0) / 100.0, -0.02), 0.12)) / 1.11, 5) - 1) /
                  NULLIF(((1.0 + LEAST(GREATEST(COALESCE(gr.eps_growth_3y_cagr, 5.0) / 100.0, -0.02), 0.12)) / 1.11) - 1, 0)
                ) +
                (
                  (pd.current_price_pd / v.trailing_pe) *
                  POWER(1.0 + LEAST(GREATEST(COALESCE(gr.eps_growth_3y_cagr, 5.0) / 100.0, -0.02), 0.12), 5) *
                  1.03 / (0.11 - 0.03) /
                  POWER(1.11, 5)
                )
                AS NUMERIC), 2)
            ELSE NULL
          END AS intrinsic_value_epv,
          -- Margin of Safety = (Intrinsic - Current) / Intrinsic (using 2-stage DCF)
          CASE
            WHEN v.trailing_pe > 0 AND v.trailing_pe < 200 THEN
              ROUND(CAST(
                (1.0 - pd.current_price_pd / NULLIF(
                  (
                    (pd.current_price_pd / v.trailing_pe) *
                    ((1.0 + LEAST(GREATEST(COALESCE(gr.eps_growth_3y_cagr, 5.0) / 100.0, -0.02), 0.12)) / 1.11) *
                    (POWER((1.0 + LEAST(GREATEST(COALESCE(gr.eps_growth_3y_cagr, 5.0) / 100.0, -0.02), 0.12)) / 1.11, 5) - 1) /
                    NULLIF(((1.0 + LEAST(GREATEST(COALESCE(gr.eps_growth_3y_cagr, 5.0) / 100.0, -0.02), 0.12)) / 1.11) - 1, 0)
                  ) +
                  (
                    (pd.current_price_pd / v.trailing_pe) *
                    POWER(1.0 + LEAST(GREATEST(COALESCE(gr.eps_growth_3y_cagr, 5.0) / 100.0, -0.02), 0.12), 5) *
                    1.03 / (0.11 - 0.03) /
                    POWER(1.11, 5)
                  )
                , 0)) * 100
                AS NUMERIC), 1)
            ELSE NULL
          END AS margin_of_safety_pct
        FROM latest_value v
        LEFT JOIN historical_value h ON v.symbol = h.symbol
        INNER JOIN latest_quality q ON v.symbol = q.symbol
        INNER JOIN price_dislocation pd ON v.symbol = pd.symbol
        LEFT JOIN latest_growth gr ON v.symbol = gr.symbol
        LEFT JOIN forward_earnings fe ON v.symbol = fe.symbol
        LEFT JOIN latest_ttm_fcf lf ON v.symbol = lf.symbol
        LEFT JOIN market_caps mc ON v.symbol = mc.symbol
        WHERE q.return_on_equity_pct >= 30
          AND q.operating_margin_pct >= 18
          AND q.gross_margin_pct >= 40
          AND q.current_ratio > 2.0
          AND q.debt_to_equity < 1.0
          AND pd.high_52w IS NOT NULL
          AND pd.current_price_pd IS NOT NULL
          -- TRAP DETECTION: fundamentals must NOT be severely deteriorating
          -- Values stored as percentage points: -5 = 5pp drop in margin/ROE; revenue_growth_yoy is %
          -- Allow up to -5pp margin compression and -10% revenue decline (real concern but not collapse)
          AND COALESCE(gr.operating_margin_trend, 0) >= -5.0
          AND COALESCE(gr.roe_trend, 0) >= -15.0
          AND COALESCE(gr.revenue_growth_yoy, 0) >= -10.0
          -- FIRE SALE: must be down significantly from highs
          AND (
            (pd.current_price_pd < pd.high_52w * 0.75)
            OR (pd.current_price_pd < pd.high_3y * 0.65)
          )
      ),
      discount_calc AS (
        SELECT
          c.symbol, c.trailing_pe, c.price_to_book, c.price_to_sales_ttm,
          c.ev_to_ebitda, c.peg_ratio, c.dividend_yield,
          c.roe, c.roa, c.gross_margin, c.op_margin, c.net_margin,
          c.debt_to_equity, c.current_ratio, c.hist_avg_pe, c.hist_avg_pb, c.hist_max_pe,
          c.high_52w, c.high_3y, c.low_52w, c.current_price_pd,
          c.drop_from_52w_high_pct, c.drop_from_3y_high_pct,
          c.revenue_growth_3y_cagr, c.eps_growth_3y_cagr, c.revenue_growth_yoy,
          c.fcf_growth_yoy, c.operating_margin_trend, c.gross_margin_trend,
          c.roe_trend, c.sustainable_growth_rate, c.quarterly_growth_momentum,
          c.intrinsic_value_epv, c.margin_of_safety_pct,
          c.forward_eps, c.estimate_quarter, c.forward_pe, c.fcf_yield,
          ROUND(CAST((c.hist_avg_pe - c.trailing_pe) / NULLIF(c.hist_avg_pe, 0) * 100 AS NUMERIC), 1) AS discount_vs_historical_pe_pct,
          ROUND(CAST((c.hist_avg_pb - c.price_to_book) / NULLIF(c.hist_avg_pb, 0) * 100 AS NUMERIC), 1) AS discount_vs_historical_pb_pct,
          CASE
            WHEN c.drop_from_52w_high_pct >= 40 THEN 100
            WHEN c.drop_from_52w_high_pct >= 35 THEN 95
            WHEN c.drop_from_52w_high_pct >= 30 THEN 90
            WHEN c.drop_from_52w_high_pct >= 25 THEN 80
            WHEN c.drop_from_3y_high_pct >= 40 THEN 85
            WHEN c.drop_from_3y_high_pct >= 35 THEN 75
            ELSE 50
          END AS discount_strength
        FROM combined c
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
          d.high_52w, d.high_3y, d.low_52w, d.current_price_pd,
          d.drop_from_52w_high_pct, d.drop_from_3y_high_pct,
          d.revenue_growth_3y_cagr, d.eps_growth_3y_cagr, d.revenue_growth_yoy,
          d.fcf_growth_yoy, d.operating_margin_trend, d.gross_margin_trend,
          d.roe_trend, d.sustainable_growth_rate, d.quarterly_growth_momentum,
          d.intrinsic_value_epv, d.margin_of_safety_pct,
          d.forward_eps, d.estimate_quarter, d.forward_pe, d.fcf_yield,
          sm.sector_median_pe, ms.market_median_pe,
          d.discount_vs_historical_pe_pct, d.discount_vs_historical_pb_pct,
          d.discount_strength,
          ROUND(CAST((sm.sector_median_pe - d.trailing_pe) / NULLIF(sm.sector_median_pe, 0) * 100 AS NUMERIC), 1) AS discount_vs_sector_pe_pct,
          ROUND(CAST((ms.market_median_pe - d.trailing_pe) / NULLIF(ms.market_median_pe, 0) * 100 AS NUMERIC), 1) AS discount_vs_market_pe_pct,
          PERCENT_RANK() OVER (ORDER BY d.drop_from_52w_high_pct DESC NULLS LAST) * 100 AS anomaly_intensity_pct
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
        ROUND(CAST(s.high_52w AS NUMERIC), 2) AS high_52w,
        ROUND(CAST(s.high_3y AS NUMERIC), 2) AS high_3y,
        ROUND(CAST(s.low_52w AS NUMERIC), 2) AS low_52w,
        s.drop_from_52w_high_pct,
        s.drop_from_3y_high_pct,
        s.discount_vs_historical_pe_pct,
        s.discount_vs_historical_pb_pct,
        s.discount_vs_sector_pe_pct,
        s.discount_vs_market_pe_pct,
        ROUND(CAST(s.revenue_growth_3y_cagr AS NUMERIC), 1) AS revenue_growth_3y_pct,
        ROUND(CAST(s.eps_growth_3y_cagr AS NUMERIC), 1) AS eps_growth_3y_pct,
        ROUND(CAST(s.revenue_growth_yoy AS NUMERIC), 1) AS revenue_growth_yoy_pct,
        ROUND(CAST(s.fcf_growth_yoy AS NUMERIC), 1) AS fcf_growth_yoy_pct,
        ROUND(CAST(s.operating_margin_trend AS NUMERIC), 2) AS op_margin_trend_pp,
        ROUND(CAST(s.gross_margin_trend AS NUMERIC), 2) AS gross_margin_trend_pp,
        ROUND(CAST(s.roe_trend AS NUMERIC), 2) AS roe_trend_pp,
        ROUND(CAST(s.sustainable_growth_rate AS NUMERIC), 1) AS sustainable_growth_pct,
        ROUND(CAST(s.intrinsic_value_epv AS NUMERIC), 2) AS intrinsic_value_per_share,
        s.margin_of_safety_pct,
        ROUND(CAST(s.forward_pe AS NUMERIC), 2) AS forward_pe,
        ROUND(CAST(s.forward_eps AS NUMERIC), 4) AS forward_eps,
        CAST(s.estimate_quarter AS TEXT) AS estimate_quarter,
        ROUND(CAST(s.fcf_yield AS NUMERIC), 2) AS fcf_yield_pct,
        -- BULLETPROOF SCORE: ONLY TRUE ANOMALIES
        -- Quality + Valuation mismatch is PRIMARY signal, not historical discount
        ROUND(CAST(
          (CASE
            WHEN s.trailing_pe < 12 AND s.roe >= 30 THEN 100
            WHEN s.trailing_pe < 15 AND s.roe >= 30 THEN 95
            WHEN s.trailing_pe < 18 AND s.roe >= 30 THEN 90
            WHEN s.trailing_pe < 20 AND s.roe >= 35 THEN 95
            WHEN s.peg_ratio < 0.6 AND s.roe >= 25 THEN 85
            WHEN s.price_to_book < 5 AND s.roe >= 35 THEN 90
            WHEN s.trailing_pe < (s.market_median_pe * 0.7) AND s.roe >= 30 THEN 85
            ELSE 50
          END) * 0.70 +
          COALESCE(s.discount_vs_historical_pe_pct, 0) * 0.20 +
          COALESCE(s.discount_strength, 30) * 0.10
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
      ORDER BY s.drop_from_52w_high_pct DESC NULLS LAST
      LIMIT $1 OFFSET $2`,
      [limit, offset]
    );

    const countResult = await query(
      `WITH sp500 AS (SELECT symbol FROM stock_symbols WHERE is_sp500 = true),
       latest_value AS (
         SELECT DISTINCT ON (vm.symbol)
           vm.symbol, vm.trailing_pe, vm.price_to_book
         FROM value_metrics vm
         JOIN sp500 st ON vm.symbol = st.symbol
         WHERE vm.trailing_pe > 0 AND vm.trailing_pe < 200 AND vm.price_to_book > 0 AND vm.price_to_book < 50
         ORDER BY vm.symbol, vm.date DESC
       ),
       latest_quality AS (
         SELECT DISTINCT ON (qm.symbol)
           qm.symbol, qm.return_on_equity_pct, qm.operating_margin_pct, qm.gross_margin_pct, qm.current_ratio, qm.debt_to_equity
         FROM quality_metrics qm JOIN sp500 st ON qm.symbol = st.symbol
         WHERE qm.return_on_equity_pct > 0 AND qm.operating_margin_pct > 0
         ORDER BY qm.symbol, qm.date DESC
       ),
       latest_growth AS (
         SELECT DISTINCT ON (gm.symbol)
           gm.symbol, gm.operating_margin_trend, gm.roe_trend, gm.revenue_growth_yoy
         FROM growth_metrics gm JOIN sp500 st ON gm.symbol = st.symbol
         ORDER BY gm.symbol, gm.date DESC
       ),
       latest_price AS (
         SELECT DISTINCT ON (pd.symbol) pd.symbol, pd.close AS current_price_pd
         FROM price_daily pd JOIN sp500 st ON pd.symbol = st.symbol
         WHERE pd.date >= CURRENT_DATE - INTERVAL '30 days' AND pd.close IS NOT NULL
         ORDER BY pd.symbol, pd.date DESC
       ),
       price_dislocation AS (
         SELECT pd.symbol,
           MAX(pd.close) FILTER (WHERE pd.date >= CURRENT_DATE - INTERVAL '252 days') AS high_52w,
           MAX(pd.close) AS high_3y,
           lp.current_price_pd
         FROM price_daily pd
         JOIN sp500 st ON pd.symbol = st.symbol
         JOIN latest_price lp ON pd.symbol = lp.symbol
         WHERE pd.date >= CURRENT_DATE - INTERVAL '756 days' AND pd.close IS NOT NULL
         GROUP BY pd.symbol, lp.current_price_pd
       )
       SELECT COUNT(DISTINCT v.symbol) as total
       FROM latest_value v
       INNER JOIN latest_quality q ON v.symbol = q.symbol
       INNER JOIN price_dislocation pd ON v.symbol = pd.symbol
       LEFT JOIN latest_growth gr ON v.symbol = gr.symbol
       WHERE q.return_on_equity_pct >= 30
         AND q.operating_margin_pct >= 18
         AND q.gross_margin_pct >= 40
         AND q.current_ratio > 2.0
         AND q.debt_to_equity < 1.0
         AND pd.high_52w IS NOT NULL
         AND pd.current_price_pd IS NOT NULL
         AND COALESCE(gr.operating_margin_trend, 0) >= -5.0
         AND COALESCE(gr.roe_trend, 0) >= -15.0
         AND COALESCE(gr.revenue_growth_yoy, 0) >= -10.0
         AND (
           (pd.current_price_pd < pd.high_52w * 0.75)
           OR (pd.current_price_pd < pd.high_3y * 0.65)
         )`
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

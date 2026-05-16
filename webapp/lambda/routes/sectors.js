const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const router = express.Router();

// GET / - Get all sectors with full performance rankings, scores, and price performance
router.get("/", async (req, res) => {
  try {
    const { limit = 500, page = 1 } = req.query;
    const limitNum = Math.min(parseInt(limit) || 500, 5000);
    const pageNum = Math.max(parseInt(page) || 1, 1);
    const offset = (pageNum - 1) * limitNum;

    // Parallelize data and count queries
    const [result, countResult] = await Promise.all([
      query(`
      WITH recent_prices AS (
        SELECT symbol, date, close,
          ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '60 days'
      ),
      symbol_perf AS (
        SELECT
          symbol,
          MAX(close) FILTER (WHERE rn = 1) as close_now,
          MAX(close) FILTER (WHERE rn = 2) as close_1d,
          MAX(close) FILTER (WHERE rn = 6) as close_5d,
          MAX(close) FILTER (WHERE rn = 21) as close_20d
        FROM recent_prices
        GROUP BY symbol
      ),
      sector_scores AS (
        SELECT
          cp.sector as sector_name,
          COUNT(DISTINCT cp.symbol) as stock_count,
          AVG(ss.composite_score) as composite_score,
          AVG(ss.momentum_score) as momentum_score,
          AVG(ss.value_score) as value_score,
          AVG(ss.quality_score) as quality_score,
          AVG(ss.growth_score) as growth_score,
          AVG(ss.stability_score) as stability_score,
          AVG(CASE WHEN sp.close_1d > 0 THEN (sp.close_now - sp.close_1d) / sp.close_1d * 100 END) as perf_1d,
          AVG(CASE WHEN sp.close_5d > 0 THEN (sp.close_now - sp.close_5d) / sp.close_5d * 100 END) as perf_5d,
          AVG(CASE WHEN sp.close_20d > 0 THEN (sp.close_now - sp.close_20d) / sp.close_20d * 100 END) as perf_20d
        FROM company_profile cp
        LEFT JOIN symbol_perf sp ON cp.symbol = sp.symbol
        LEFT JOIN stock_scores ss ON cp.symbol = ss.symbol
        WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) != ''
        GROUP BY cp.sector
      ),
      ranked AS (
        SELECT *,
          RANK() OVER (ORDER BY composite_score DESC NULLS LAST) as current_rank
        FROM sector_scores
      ),
      sector_pe AS (
        SELECT
          cp.sector,
          AVG(vm.trailing_pe) FILTER (WHERE vm.trailing_pe > 0 AND vm.trailing_pe < 200) AS avg_trailing_pe,
          AVG(vm.forward_pe) FILTER (WHERE vm.forward_pe > 0 AND vm.forward_pe < 200) AS avg_forward_pe
        FROM (
          SELECT DISTINCT ON (symbol) symbol, trailing_pe, forward_pe
          FROM value_metrics
          ORDER BY symbol, date DESC
        ) vm
        JOIN company_profile cp ON vm.symbol = cp.symbol
        WHERE cp.sector IS NOT NULL
        GROUP BY cp.sector
      ),
      sector_pe_ranked AS (
        SELECT *,
          PERCENT_RANK() OVER (ORDER BY avg_trailing_pe ASC NULLS LAST) * 100 AS pe_percentile
        FROM sector_pe
      )
      SELECT r.*, spe.avg_trailing_pe, spe.avg_forward_pe, spe.pe_percentile
      FROM ranked r
      LEFT JOIN sector_pe_ranked spe ON spe.sector = r.sector_name
      ORDER BY r.current_rank, r.stock_count DESC
      LIMIT $1 OFFSET $2
    `, [limitNum, offset]),
      query(`SELECT COUNT(DISTINCT sector) as count FROM company_profile WHERE sector IS NOT NULL`)
    ]);

    const total = parseInt(countResult?.rows[0]?.count || 0);

    const sf = v => (v !== null && v !== undefined) ? parseFloat(v) : null;

    const sectors = (result?.rows || []).map((row, idx) => {
      const composite = sf(row.composite_score);
      const perf20d = sf(row.perf_20d);
      const momentumLabel = composite !== null && composite >= 60 ? 'Strong' : composite !== null && composite >= 45 ? 'Moderate' : 'Weak';
      const trendLabel = perf20d !== null ? (perf20d > 2 ? 'Uptrend' : perf20d < -2 ? 'Downtrend' : 'Sideways') : 'Sideways';

      return {
        sector_name: row.sector_name,
        current_rank: parseInt(row.current_rank) || idx + 1 + offset,
        overall_rank: parseInt(row.current_rank) || idx + 1 + offset,
        stock_count: parseInt(row.stock_count || 0),
        composite_score: composite,
        momentum_score: sf(row.momentum_score),
        value_score: sf(row.value_score),
        quality_score: sf(row.quality_score),
        growth_score: sf(row.growth_score),
        stability_score: sf(row.stability_score),
        performance_1d: sf(row.perf_1d),
        performance_5d: sf(row.perf_5d),
        performance_20d: perf20d,
        current_momentum: momentumLabel,
        current_trend: trendLabel,
        pe: {
          trailing: sf(row.avg_trailing_pe),
          forward: sf(row.avg_forward_pe),
          percentile: sf(row.pe_percentile),
        },
      };
    });

    const totalPages = Math.ceil(total / limitNum);
    return sendPaginated(res, sectors, {page: pageNum, limit: limitNum, total, totalPages, hasNext: pageNum < totalPages, hasPrev: pageNum > 1});
  } catch (error) {
    console.error("Error fetching sectors:", error.message);
    return sendError(res, `Failed to fetch sectors: ${error.message.substring(0, 100)}`, 500);
  }
});

// GET /:sector/trend - Get historical trend data for a specific sector
router.get("/:sector/trend", async (req, res) => {
  try {
    const { sector } = req.params;
    const days = Math.min(parseInt(req.query.days) || 90, 365);

    const resultObj = await query(`
      SELECT
        sr.date,
        sr.sector,
        sr.avg_price,
        sr.stock_count,
        sr.composite_score,
        sr.momentum_score,
        sr.rank_1w_ago,
        sr.rank_4w_ago,
        sr.rank_12w_ago
      FROM sector_ranking sr
      WHERE sr.sector = $1
        AND sr.date >= CURRENT_DATE - INTERVAL '${days} days'
      ORDER BY sr.date DESC
    `, [sector]);

    const result = Array.isArray(resultObj) ? resultObj : (resultObj?.rows || []);

    if (result.length === 0) {
      return sendError(res, `No trend data for sector: ${sector}`, 404);
    }

    sendSuccess(res, result, 200);
  } catch (error) {
    console.error("Error fetching sector trend:", error);
    sendError(res, "Failed to fetch sector trend: " + error.message, 500);
  }
});

module.exports = router;

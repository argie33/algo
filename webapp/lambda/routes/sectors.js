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

    // Single 30-day scan for all price performance — avoids 4x full-table scans on 22M rows
    const result = await query(`
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
          COUNT(DISTINCT cp.ticker) as stock_count,
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
        LEFT JOIN symbol_perf sp ON cp.ticker = sp.symbol
        LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
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
        JOIN company_profile cp ON vm.symbol = cp.ticker
        WHERE cp.sector IS NOT NULL
        GROUP BY cp.sector
      ),
      sector_pe_ranked AS (
        SELECT *,
          PERCENT_RANK() OVER (ORDER BY avg_trailing_pe ASC NULLS LAST) * 100 AS pe_percentile
        FROM sector_pe
      ),
      max_snapshot_date AS (
        SELECT MAX(date_recorded) AS max_date FROM sector_ranking
      )
      SELECT r.*,
        spe.avg_trailing_pe,
        spe.avg_forward_pe,
        spe.pe_percentile,
        sr_1w.current_rank as rank_1w_ago,
        sr_4w.current_rank as rank_4w_ago,
        sr_12w.current_rank as rank_12w_ago
      FROM ranked r
      LEFT JOIN sector_pe_ranked spe ON spe.sector = r.sector_name
      LEFT JOIN LATERAL (
        SELECT current_rank FROM sector_ranking
        WHERE LOWER(TRIM(sector_name)) = LOWER(TRIM(r.sector_name))
          AND date_recorded <= (SELECT max_date FROM max_snapshot_date) - INTERVAL '7 days'
        ORDER BY date_recorded DESC LIMIT 1
      ) sr_1w ON true
      LEFT JOIN LATERAL (
        SELECT current_rank FROM sector_ranking
        WHERE LOWER(TRIM(sector_name)) = LOWER(TRIM(r.sector_name))
          AND date_recorded <= (SELECT max_date FROM max_snapshot_date) - INTERVAL '28 days'
        ORDER BY date_recorded DESC LIMIT 1
      ) sr_4w ON true
      LEFT JOIN LATERAL (
        SELECT current_rank FROM sector_ranking
        WHERE LOWER(TRIM(sector_name)) = LOWER(TRIM(r.sector_name))
          AND date_recorded <= (SELECT max_date FROM max_snapshot_date) - INTERVAL '84 days'
        ORDER BY date_recorded DESC LIMIT 1
      ) sr_12w ON true
      ORDER BY r.current_rank, r.stock_count DESC
      LIMIT $1 OFFSET $2
    `, [limitNum, offset]);

    const countResult = await query("SELECT COUNT(DISTINCT sector) as count FROM company_profile WHERE sector IS NOT NULL");
    const total = parseInt(countResult?.rows[0]?.count || 0);

    const sf = v => (v !== null && v !== undefined) ? parseFloat(v) : null;
    const si = v => (v !== null && v !== undefined) ? parseInt(v) : null;

    const sectors = (result?.rows || []).map((row, idx) => {
      const composite = sf(row.composite_score);
      const perf20d = sf(row.perf_20d);
      const momentumLabel = composite !== null && composite >= 60 ? 'Strong' : composite !== null && composite >= 45 ? 'Moderate' : 'Weak';
      const trendLabel = perf20d !== null ? (perf20d > 2 ? 'Uptrend' : perf20d < -2 ? 'Downtrend' : 'Sideways') : 'Sideways';

      return {
        sector_name: row.sector_name,
        current_rank: parseInt(row.current_rank) || idx + 1 + offset,
        overall_rank: parseInt(row.current_rank) || idx + 1 + offset,
        rank_1w_ago: si(row.rank_1w_ago),
        rank_4w_ago: si(row.rank_4w_ago),
        rank_12w_ago: si(row.rank_12w_ago),
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

// GET /:sector/trend - Sector trend (proper REST structure)
router.get("/:sector/trend", async (req, res) => {
  try {
    const { sector } = req.params;
    const { days = 90 } = req.query;
    const daysNum = Math.min(parseInt(days) || 90, 365);

    const result = await query(`
      WITH prices AS (
        SELECT
          DATE(pd.date) as date,
          AVG(CAST(pd.close AS FLOAT)) as avg_price,
          COUNT(DISTINCT pd.symbol) as stock_count
        FROM price_daily pd
        JOIN company_profile cp ON pd.symbol = cp.ticker
        WHERE LOWER(TRIM(cp.sector)) = LOWER(TRIM($1))
          AND pd.date >= CURRENT_DATE - INTERVAL '${daysNum} days'
        GROUP BY DATE(pd.date)
        ORDER BY date ASC
      )
      SELECT date, avg_price, stock_count,
        ((avg_price / NULLIF(FIRST_VALUE(avg_price) OVER (ORDER BY date), 0)) - 1) * 100 AS daily_strength_score
      FROM prices
      ORDER BY date ASC
    `, [sector]);

    if (!result?.rows || result.rows.length === 0) {
      return sendSuccess(res, { sector, trendData: [] });
    }

    return sendSuccess(res, {
      sector,
      trendData: result.rows.map(row => ({
        date: row.date,
        avgPrice: parseFloat(row.avg_price) || 0,
        stockCount: parseInt(row.stock_count) || 0,
        dailyStrengthScore: parseFloat(row.daily_strength_score) || 0
      }))
    });
  } catch (error) {
    console.error("Error fetching sector trend:", error.message);
    return sendError(res, `Failed to fetch sector trend: ${error.message.substring(0, 100)}`, 500);
  }
});

// GET /trend/sector/:sectorName - Get sector trend data (for SectorAnalysis charts)
router.get("/trend/sector/:sectorName", async (req, res) => {
  try {
    const { sectorName } = req.params;
    const { days = 90 } = req.query;
    const daysNum = Math.min(parseInt(days) || 90, 365);

    const result = await query(`
      WITH prices AS (
        SELECT
          DATE(pd.date) as date,
          AVG(CAST(pd.close AS FLOAT)) as avg_price,
          COUNT(DISTINCT pd.symbol) as stock_count
        FROM price_daily pd
        JOIN company_profile cp ON pd.symbol = cp.ticker
        WHERE LOWER(TRIM(cp.sector)) = LOWER(TRIM($1))
          AND pd.date >= CURRENT_DATE - INTERVAL '${daysNum} days'
        GROUP BY DATE(pd.date)
        ORDER BY date ASC
      )
      SELECT date, avg_price, stock_count,
        ((avg_price / NULLIF(FIRST_VALUE(avg_price) OVER (ORDER BY date), 0)) - 1) * 100 AS daily_strength_score
      FROM prices
      ORDER BY date ASC
    `, [sectorName]);

    if (!result?.rows || result.rows.length === 0) {
      return sendError(res, `No trend data found for sector: ${sectorName}`, 404);
    }

    const trendData = result.rows.map(row => ({
      date: row.date,
      avgPrice: parseFloat(row.avg_price) || 0,
      stockCount: parseInt(row.stock_count) || 0,
      dailyStrengthScore: parseFloat(row.daily_strength_score) || 0
    }));

    return sendSuccess(res, { sector: sectorName, trendData });
  } catch (error) {
    console.error("Error fetching sector trend:", error.message);
    return sendError(res, `Failed to fetch sector trend: ${error.message.substring(0, 100)}`, 500);
  }
});

module.exports = router;

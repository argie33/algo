const express = require("express");

const { query } = require("../utils/database");
const {
  sendSuccess,
  sendError,
  sendPaginated,
} = require("../utils/apiResponse");
const {
  validateQueryResult,
} = require("../utils/responseValidation");
const router = express.Router();

// GET / - Get all sectors with full performance rankings, scores, and price performance
router.get("/", async (req, res) => {
  try {
    const { limit = 500, page = 1 } = req.query;
    const limitNum = Math.min(parseInt(limit) || 500, 5000);
    const pageNum = Math.max(parseInt(page) || 1, 1);
    const offset = (pageNum - 1) * limitNum;

    // Parallelize data and count queries
    const [dataResult, countResult] = await Promise.all([
      query(
        `
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
      sector_ranking_12w AS (
        SELECT sector_name, NULL::INTEGER as rank_12w_ago
        FROM sector_scores
      ),
      sector_pe AS (
        SELECT
          cp.sector,
          AVG(vm.pe_ratio) FILTER (WHERE vm.pe_ratio > 0 AND vm.pe_ratio < 200) AS avg_trailing_pe,
          AVG(vm.pb_ratio) FILTER (WHERE vm.pb_ratio > 0 AND vm.pb_ratio < 50) AS avg_forward_pe
        FROM value_metrics vm
        JOIN company_profile cp ON vm.symbol = cp.ticker
        WHERE cp.sector IS NOT NULL AND cp.sector != ''
        GROUP BY cp.sector
      ),
      sector_pe_ranked AS (
        SELECT *,
          PERCENT_RANK() OVER (ORDER BY avg_trailing_pe ASC NULLS LAST) * 100 AS pe_percentile
        FROM sector_pe
      )
      SELECT r.*, spe.avg_trailing_pe, spe.avg_forward_pe, spe.pe_percentile, sr12.rank_12w_ago
      FROM ranked r
      LEFT JOIN sector_pe_ranked spe ON spe.sector = r.sector_name
      LEFT JOIN sector_ranking_12w sr12 ON sr12.sector_name = r.sector_name
      ORDER BY r.current_rank, r.stock_count DESC
      LIMIT $1 OFFSET $2
    `,
        [limitNum, offset]
      ),
      query(
        `SELECT COUNT(DISTINCT sector) as count FROM company_profile WHERE sector IS NOT NULL`
      ),
    ]);
    validateQueryResult(dataResult, { requireRows: false });
    validateQueryResult(countResult, { requireRows: false });

    const total = parseInt(countResult?.rows[0]?.count || 0);

    const sf = (v) => (v !== null && v !== undefined ? parseFloat(v) : null);

    const sectors = (dataResult?.rows || []).map((row, idx) => {
      const composite = sf(row.composite_score);
      const perf20d = sf(row.perf_20d);
      const momentumLabel =
        composite !== null && composite >= 60
          ? "Strong"
          : composite !== null && composite >= 45
            ? "Moderate"
            : "Weak";
      const trendLabel =
        perf20d !== null
          ? perf20d > 2
            ? "Uptrend"
            : perf20d < -2
              ? "Downtrend"
              : "Sideways"
          : "Sideways";

      return {
        sector_name: row.sector_name,
        current_rank: parseInt(row.current_rank) || idx + 1 + offset,
        rank_12w_ago: parseInt(row.rank_12w_ago) || null,
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
    return sendPaginated(res, sectors, {
      page: pageNum,
      limit: limitNum,
      total,
      totalPages,
      hasNext: pageNum < totalPages,
      hasPrev: pageNum > 1,
    });
  } catch (error) {
    console.error("Error fetching sectors:", error.message);
    return sendError(
      res,
      `Failed to fetch sectors: ${error.message.substring(0, 100)}`,
      500
    );
  }
});

// GET /trends-batch - Get daily sector price averages for the past N days (for relative performance charts)
router.get("/trends-batch", async (req, res) => {
  try {
    const { sectors: sectorsList, days = 90 } = req.query;
    if (!sectorsList) {
      return sendError(
        res,
        "sectors parameter required (comma-separated)",
        400
      );
    }

    // Parse sector names (preserve case, don't uppercase)
    const sectors = sectorsList
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    const daysNum = Math.min(parseInt(days) || 90, 365);

    if (sectors.length === 0) {
      return sendSuccess(res, {});
    }

    // Query daily returns per sector from sector_performance table
    const placeholders = sectors.map((_, i) => `$${i + 1}`).join(",");
    const resultObj = await query(
      `
      SELECT
        sector,
        date,
        return_pct
      FROM sector_performance
      WHERE sector IN (${placeholders})
        AND date >= CURRENT_DATE - INTERVAL '${daysNum} days'
      ORDER BY sector, date ASC
    `,
      sectors
    );
    validateQueryResult(resultObj, { requireRows: false });

    const result = Array.isArray(resultObj) ? resultObj : resultObj?.rows || [];

    // Group by sector and compute cumulative index
    const grouped = {};
    result.forEach((row) => {
      if (!grouped[row.sector]) {
        grouped[row.sector] = [];
      }
      grouped[row.sector].push({
        date: row.date,
        return_pct: parseFloat(row.return_pct),
      });
    });

    // Compute price index (100 at start, then compound daily returns)
    Object.keys(grouped).forEach((sector) => {
      let index = 100;
      grouped[sector] = grouped[sector].map((point) => {
        index = index * (1 + (point.return_pct || 0) / 100);
        return {
          date: point.date,
          avgPrice: parseFloat(index.toFixed(2)),
        };
      });
    });

    return sendSuccess(res, grouped, 200);
  } catch (error) {
    console.error("Error fetching sector trends batch:", error);
    return sendError(
      res,
      "Failed to fetch sector trends: " + error.message,
      500
    );
  }
});

// GET /:sector/trend - Get historical daily prices for a specific sector
router.get("/:sector/trend", async (req, res) => {
  try {
    const { sector } = req.params;
    const days = Math.min(parseInt(req.query.days) || 90, 365);

    // Query daily average price for the sector
    const resultObj = await query(
      `
      SELECT
        pd.date,
        AVG(pd.close) AS avgPrice,
        COUNT(DISTINCT pd.symbol) AS stockCount
      FROM price_daily pd
      JOIN company_profile cp ON cp.ticker = pd.symbol
      WHERE cp.sector = $1
        AND pd.date >= CURRENT_DATE - INTERVAL '${days} days'
        AND pd.close > 0
      GROUP BY pd.date
      ORDER BY pd.date ASC
    `,
      [sector]
    );
    validateQueryResult(resultObj, { requireRows: false });

    const result = Array.isArray(resultObj) ? resultObj : resultObj?.rows || [];

    if (result.length === 0) {
      return sendError(res, `No price data for sector: ${sector}`, 404);
    }

    // Convert to required format with trendData wrapper
    const trendData = result.map((row) => ({
      date: row.date,
      avgPrice: parseFloat(row.avgprice),
      dailyStrengthScore: 0, // Placeholder; can compute from price momentum if needed
    }));

    return sendSuccess(res, { sector, trendData }, 200);
  } catch (error) {
    console.error("Error fetching sector trend:", error);
    return sendError(
      res,
      "Failed to fetch sector trend: " + error.message,
      500
    );
  }
});

// ============================================
// WILDCARD ROUTES - Must come AFTER specific routes!
// ============================================

// GET /:sector/trend - Get sector trend data
router.get("/:sector/trend", async (req, res) => {
  try {
    const { sector } = req.params;
    if (!sector || sector.length === 0) {
      return sendError(res, "Sector name required", 400);
    }

    // Query using LOWER to allow case-insensitive lookup
    const result = await query(
      `
      SELECT
        sector,
        date,
        avgprice
      FROM sector_performance
      WHERE LOWER(sector) = LOWER($1)
      ORDER BY date DESC
      LIMIT 100
    `,
      [sector]
    );
    validateQueryResult(result, { requireRows: false });

    if (result.length === 0) {
      return sendError(res, `No price data for sector: ${sector}`, 404);
    }

    // Convert to required format with trendData wrapper
    const trendData = result.map((row) => ({
      date: row.date,
      avgPrice: parseFloat(row.avgprice),
      dailyStrengthScore: 0, // Placeholder; can compute from price momentum if needed
    }));

    return sendSuccess(res, { sector, trendData }, 200);
  } catch (error) {
    console.error("Error fetching sector trend:", error);
    return sendError(
      res,
      "Failed to fetch sector trend: " + error.message,
      500
    );
  }
});

// GET /:sector - Get specific sector details
// MUST be last so more specific routes like /trends-batch and /:sector/trend match first
router.get("/:sector", async (req, res) => {
  try {
    const { sector } = req.params;
    if (!sector || sector.length === 0) {
      return sendError(res, "Sector name required", 400);
    }

    // Query sector details with performance metrics
    const result = await query(
      `
      SELECT
        cp.sector as sector_name,
        COUNT(DISTINCT cp.ticker) as stock_count,
        AVG(ss.composite_score) as composite_score,
        AVG(ss.momentum_score) as momentum_score,
        AVG(ss.value_score) as value_score,
        AVG(ss.quality_score) as quality_score,
        AVG(ss.growth_score) as growth_score,
        AVG(ss.stability_score) as stability_score
      FROM company_profile cp
      LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
      WHERE cp.sector = $1
      GROUP BY cp.sector
    `,
      [sector]
    );
    validateQueryResult(result, { requireRows: false });

    if (result.rows.length === 0) {
      return sendError(res, `Sector not found: ${sector}`, 404);
    }

    const row = result.rows[0];
    const sectorData = {
      sector_name: row.sector_name,
      stock_count: parseInt(row.stock_count || 0),
      composite_score: row.composite_score
        ? parseFloat(row.composite_score)
        : null,
      momentum_score: row.momentum_score
        ? parseFloat(row.momentum_score)
        : null,
      value_score: row.value_score ? parseFloat(row.value_score) : null,
      quality_score: row.quality_score ? parseFloat(row.quality_score) : null,
      growth_score: row.growth_score ? parseFloat(row.growth_score) : null,
      stability_score: row.stability_score
        ? parseFloat(row.stability_score)
        : null,
    };

    return sendSuccess(res, sectorData);
  } catch (error) {
    console.error("Error fetching sector:", error);
    return sendError(
      res,
      `Failed to fetch sector: ${error.message.substring(0, 100)}`,
      500
    );
  }
});

module.exports = router;

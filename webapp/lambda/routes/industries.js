const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const router = express.Router();

// Helper function to get industries ranked by composite score with performance metrics
async function fetchIndustries(req, res) {
  try {
    const { limit = 500, page = 1 } = req.query;
    const limitNum = Math.min(parseInt(limit) || 500, 1000);
    const pageNum = Math.max(parseInt(page) || 1, 1);
    const offset = (pageNum - 1) * limitNum;

    const result = await query(`
      WITH latest_prices AS (
        SELECT pd.symbol, pd.close, pd.date
        FROM price_daily pd
        INNER JOIN (
          SELECT symbol, MAX(date) as max_date FROM price_daily GROUP BY symbol
        ) lp ON pd.symbol = lp.symbol AND pd.date = lp.max_date
      ),
      price_1d AS (
        SELECT pd.symbol, pd.close
        FROM price_daily pd
        INNER JOIN (
          SELECT symbol, MAX(date) as max_date FROM price_daily
          WHERE date < CURRENT_DATE - INTERVAL '1 day' GROUP BY symbol
        ) prev ON pd.symbol = prev.symbol AND pd.date = prev.max_date
      ),
      price_5d AS (
        SELECT pd.symbol, pd.close
        FROM price_daily pd
        INNER JOIN (
          SELECT symbol, MAX(date) as max_date FROM price_daily
          WHERE date <= CURRENT_DATE - INTERVAL '5 days' GROUP BY symbol
        ) prev ON pd.symbol = prev.symbol AND pd.date = prev.max_date
      ),
      price_20d AS (
        SELECT pd.symbol, pd.close
        FROM price_daily pd
        INNER JOIN (
          SELECT symbol, MAX(date) as max_date FROM price_daily
          WHERE date <= CURRENT_DATE - INTERVAL '20 days' GROUP BY symbol
        ) prev ON pd.symbol = prev.symbol AND pd.date = prev.max_date
      ),
      industry_scores AS (
        SELECT
          cp.industry,
          cp.sector,
          COUNT(DISTINCT cp.ticker) as stock_count,
          AVG(lp.close) as avg_price,
          AVG(ss.composite_score) as composite_score,
          AVG(ss.momentum_score) as momentum_score,
          AVG(ss.value_score) as value_score,
          AVG(ss.quality_score) as quality_score,
          AVG(ss.growth_score) as growth_score,
          AVG(ss.stability_score) as stability_score,
          AVG(CASE WHEN p1.close > 0 THEN (lp.close - p1.close) / p1.close * 100 ELSE NULL END) as perf_1d,
          AVG(CASE WHEN p5.close > 0 THEN (lp.close - p5.close) / p5.close * 100 ELSE NULL END) as perf_5d,
          AVG(CASE WHEN p20.close > 0 THEN (lp.close - p20.close) / p20.close * 100 ELSE NULL END) as perf_20d
        FROM company_profile cp
        LEFT JOIN latest_prices lp ON cp.ticker = lp.symbol
        LEFT JOIN price_1d p1 ON cp.ticker = p1.symbol
        LEFT JOIN price_5d p5 ON cp.ticker = p5.symbol
        LEFT JOIN price_20d p20 ON cp.ticker = p20.symbol
        LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
        WHERE cp.industry IS NOT NULL AND TRIM(cp.industry) != ''
        GROUP BY cp.industry, cp.sector
      ),
      ranked AS (
        SELECT *,
          RANK() OVER (ORDER BY composite_score DESC NULLS LAST) as current_rank
        FROM industry_scores
      )
      SELECT * FROM ranked
      ORDER BY current_rank, stock_count DESC
      LIMIT $1 OFFSET $2
    `, [limitNum, offset]);

    const countResult = await query(`SELECT COUNT(DISTINCT industry) as count FROM company_profile WHERE industry IS NOT NULL`);
    const total = parseInt(countResult?.rows[0]?.count || 0);

    const sf = v => (v !== null && v !== undefined) ? parseFloat(v) : null;

    const industries = (result?.rows || []).map((row, idx) => {
      const composite = sf(row.composite_score);
      const perf20d = sf(row.perf_20d);
      const momentumLabel = composite >= 60 ? 'Strong' : composite >= 45 ? 'Moderate' : 'Weak';
      const trendLabel = perf20d > 2 ? 'Uptrend' : perf20d < -2 ? 'Downtrend' : 'Sideways';

      return {
        industry: row.industry,
        sector: row.sector,
        current_rank: parseInt(row.current_rank) || idx + 1 + offset,
        overall_rank: parseInt(row.current_rank) || idx + 1 + offset,
        stock_count: parseInt(row.stock_count || 0),
        avg_price: sf(row.avg_price),
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
      };
    });

    const totalPages = Math.ceil(total / limitNum);
    return sendPaginated(res, industries, {page: pageNum, limit: limitNum, total, totalPages, hasNext: pageNum < totalPages, hasPrev: pageNum > 1});
  } catch (error) {
    console.error("Error fetching industries:", error.message);
    return sendError(res, `Failed to fetch industries: ${error.message.substring(0, 100)}`, 500);
  }
}

// GET / - Get all industries
router.get("/", fetchIndustries);

// GET /industries - Alias for backward compatibility
router.get("/industries", fetchIndustries);

// GET /:industry/trend - Industry trend (proper REST structure)
router.get("/:industry/trend", async (req, res) => {
  try {
    const { industry } = req.params;
    const { days = 90 } = req.query;
    const daysNum = Math.min(parseInt(days) || 90, 365);

    const result = await query(`
      SELECT
        DATE(pd.date) as date,
        AVG(CAST(pd.close AS FLOAT)) as avg_price,
        COUNT(DISTINCT pd.symbol) as stock_count
      FROM price_daily pd
      JOIN company_profile cp ON pd.symbol = cp.ticker
      WHERE LOWER(TRIM(cp.industry)) = LOWER(TRIM($1))
      AND pd.date >= CURRENT_DATE - INTERVAL '${daysNum} days'
      GROUP BY DATE(pd.date)
      ORDER BY date ASC
    `, [industry]);

    if (!result?.rows || result.rows.length === 0) {
      return sendSuccess(res, { industry, trendData: [] });
    }

    return sendSuccess(res, {
      industry,
      trendData: result.rows.map(row => ({
        date: row.date,
        avgPrice: parseFloat(row.avg_price) || 0,
        stockCount: parseInt(row.stock_count) || 0
      }))
    });
  } catch (error) {
    console.error("Error fetching industry trend:", error.message);
    return sendError(res, `Failed to fetch industry trend: ${error.message.substring(0, 100)}`, 500);
  }
});

// GET /trend/industry/:industryName - Get industry trend data (for SectorAnalysis charts)
router.get("/trend/industry/:industryName", async (req, res) => {
  try {
    const { industryName } = req.params;
    const { days = 90 } = req.query;
    const daysNum = Math.min(parseInt(days) || 90, 365);

    const result = await query(`
      SELECT
        DATE(pd.date) as date,
        AVG(CAST(pd.close AS FLOAT)) as avg_price,
        COUNT(DISTINCT pd.symbol) as stock_count
      FROM price_daily pd
      JOIN company_profile cp ON pd.symbol = cp.ticker
      WHERE LOWER(TRIM(cp.industry)) = LOWER(TRIM($1))
      AND pd.date >= CURRENT_DATE - INTERVAL '${daysNum} days'
      GROUP BY DATE(pd.date)
      ORDER BY date ASC
    `, [industryName]);

    if (!result?.rows || result.rows.length === 0) {
      return sendError(res, `No trend data found for industry: ${industryName}`, 404);
    }

    const trendData = result.rows.map(row => ({
      date: row.date,
      avgPrice: parseFloat(row.avg_price) || 0,
      stockCount: parseInt(row.stock_count) || 0
    }));

    return sendSuccess(res, { industry: industryName, trendData });
  } catch (error) {
    console.error("Error fetching industry trend:", error.message);
    return sendError(res, `Failed to fetch industry trend: ${error.message.substring(0, 100)}`, 500);
  }
});

module.exports = router;

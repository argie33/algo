const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const router = express.Router();

// GET /api/optimization/analysis - Real portfolio optimization data from DB
router.get("/analysis", async (req, res) => {
  try {
    const symbolsParam = req.query.symbols;
    const symbols = symbolsParam
      ? symbolsParam.split(",").map(s => s.trim().toUpperCase()).filter(Boolean)
      : [];

    // Fetch real metrics for requested symbols (or top SP500 by composite score)
    const symbolFilter = symbols.length > 0
      ? `AND ss.symbol = ANY($1)`
      : `AND st.is_sp500 = true`;
    const queryArgs = symbols.length > 0 ? [symbols] : [];

    const result = await query(
      `SELECT
         ss.symbol,
         cp.long_name AS company_name,
         cp.sector,
         ss.composite_score,
         ss.momentum_score,
         ss.quality_score,
         ss.value_score,
         ss.stability_score,
         sm.beta,
         sm.volatility_12m      AS volatility_90d,
         sm.max_drawdown_52w    AS max_drawdown_1y,
         mm.momentum_1m         AS return_1m,
         mm.momentum_3m         AS return_3m,
         mm.momentum_6m         AS return_6m,
         mm.momentum_12m        AS return_12m,
         vm.trailing_pe,
         vm.dividend_yield
       FROM stock_scores ss
       JOIN stock_symbols st ON ss.symbol = st.symbol
       LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
       LEFT JOIN LATERAL (
         SELECT beta, volatility_12m, max_drawdown_52w
         FROM stability_metrics WHERE symbol = ss.symbol
         ORDER BY date DESC LIMIT 1
       ) sm ON true
       LEFT JOIN LATERAL (
         SELECT momentum_1m, momentum_3m, momentum_6m, momentum_12m
         FROM momentum_metrics WHERE symbol = ss.symbol
         ORDER BY date DESC LIMIT 1
       ) mm ON true
       LEFT JOIN LATERAL (
         SELECT trailing_pe, dividend_yield
         FROM value_metrics WHERE symbol = ss.symbol
         ORDER BY date DESC LIMIT 1
       ) vm ON true
       WHERE ss.composite_score IS NOT NULL
         ${symbolFilter}
       ORDER BY ss.composite_score DESC
       LIMIT 20`,
      queryArgs
    );

    if (!result.rows || result.rows.length === 0) {
      return sendError(res, "No optimization data available — run loadstockscores.py and loadfactormetrics.py first", 404);
    }

    const stocks = result.rows;
    const n = stocks.length;
    const equalWeight = parseFloat((100 / n).toFixed(1));

    // Build allocations from real composite scores (score-weighted)
    const totalScore = stocks.reduce((s, r) => s + (parseFloat(r.composite_score) || 0), 0);
    const allocations = stocks.map(r => ({
      symbol: r.symbol,
      company_name: r.company_name || r.symbol,
      sector: r.sector || "Unknown",
      allocation: totalScore > 0
        ? parseFloat(((parseFloat(r.composite_score) / totalScore) * 100).toFixed(1))
        : equalWeight,
      composite_score: parseFloat(r.composite_score) || null,
      momentum_score: parseFloat(r.momentum_score) || null,
      quality_score: parseFloat(r.quality_score) || null,
      beta: r.beta != null ? parseFloat(r.beta) : null,
      return_12m: r.return_12m != null ? parseFloat(r.return_12m) : null,
      dividend_yield: r.dividend_yield != null ? parseFloat(r.dividend_yield) : null,
    }));

    // Portfolio-level aggregates from real data
    const validBetas = stocks.filter(r => r.beta != null).map(r => parseFloat(r.beta));
    const validReturns = stocks.filter(r => r.return_12m != null).map(r => parseFloat(r.return_12m));
    const validVols = stocks.filter(r => r.volatility_90d != null).map(r => parseFloat(r.volatility_90d));
    const avgBeta = validBetas.length ? (validBetas.reduce((a, b) => a + b, 0) / validBetas.length) : null;
    const avgReturn = validReturns.length ? (validReturns.reduce((a, b) => a + b, 0) / validReturns.length) : null;
    const avgVol = validVols.length ? (validVols.reduce((a, b) => a + b, 0) / validVols.length) : null;

    return sendSuccess(res, {
      allocations,
      portfolioMetrics: {
        symbolCount: n,
        avgBeta: avgBeta != null ? parseFloat(avgBeta.toFixed(2)) : null,
        avgReturn12m: avgReturn != null ? parseFloat(avgReturn.toFixed(2)) : null,
        avgVolatility: avgVol != null ? parseFloat(avgVol.toFixed(2)) : null,
        weightingMethod: "composite_score_weighted",
      },
      note: "Allocations weighted by composite score. Run factor loaders to improve data coverage.",
    });
  } catch (error) {
    console.error("Error fetching optimization data:", error.message);
    return sendError(res, `Failed to fetch optimization data: ${error.message}`, 500);
  }
});

module.exports = router;

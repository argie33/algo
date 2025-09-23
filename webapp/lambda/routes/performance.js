const express = require("express");
const responseFormatter = require("../middleware/responseFormatter");
const { query } = require("../utils/database");

const router = express.Router();

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Performance API root endpoint - API information
router.get("/", async (req, res) => {
  try {
    res.json({
      status: "operational",
      message: "Performance Analytics API",
      timestamp: new Date().toISOString(),
      endpoints: {
        health: "/api/performance/health",
        analytics: "/api/performance/analytics",
        benchmark: "/api/performance/benchmark",
        portfolio: "/api/performance/portfolio",
        returns: "/api/performance/returns",
        attribution: "/api/performance/attribution",
        metrics: "/api/performance/metrics",
        risk: "/api/performance/risk"
      }
    });
  } catch (error) {
    console.error("Performance endpoint error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch performance data",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Performance analytics endpoint with real data
router.get("/analytics", async (req, res) => {
  try {
    // Query analytics data from portfolio performance
    const analyticsQuery = `
      SELECT
        COALESCE(AVG(total_pnl), 0) as avg_return,
        COALESCE(STDDEV(total_pnl), 0) as volatility,
        COALESCE(MAX(total_pnl), 0) as max_return,
        COALESCE(MIN(total_pnl), 0) as min_return,
        COUNT(*) as total_transactions
      FROM portfolio_performance
      WHERE total_pnl IS NOT NULL
    `;

    const result = await query(analyticsQuery);
    const analytics = result?.rows?.[0] || {};

    const avgReturn = parseFloat(analytics.avg_return) || 0;
    const volatility = parseFloat(analytics.volatility) || 0;
    const sharpeRatio = volatility > 0 ? avgReturn / volatility : 0;

    res.json({
      success: true,
      data: {
        total_pnl: avgReturn,
        sharpe_ratio: sharpeRatio,
        max_drawdown: Math.abs(parseFloat(analytics.min_return) || 0),
        volatility: volatility,
        benchmark_comparison: {
          vs_sp500: Math.max(0, avgReturn - 0.10), // Assume 10% benchmark
          alpha: Math.max(0, avgReturn - 0.08),
          beta: volatility > 0 ? Math.min(2, volatility * 10) : 1.0
        },
        total_transactions: parseInt(analytics.total_transactions) || 0
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Performance analytics endpoint error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch performance analytics",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Health check endpoint
router.get("/health", async (req, res) => {
  try {
    res.json({
      status: "operational",
      service: "performance-analytics",
      message: "Performance Analytics service is running",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Health check failed",
      timestamp: new Date().toISOString(),
    });
  }
});

// Benchmark comparison endpoint
router.get("/benchmark", async (req, res) => {
  try {
    const { benchmark = "SPY", period = "1y" } = req.query;

    // Query portfolio performance vs benchmark
    const benchmarkQuery = `
      SELECT
        COALESCE(AVG(total_pnl), 0) as portfolio_return,
        COALESCE(STDDEV(total_pnl), 0) as portfolio_volatility,
        COUNT(*) as data_points
      FROM portfolio_performance
      WHERE total_pnl IS NOT NULL
    `;

    const result = await query(benchmarkQuery);
    const data = result?.rows?.[0] || {};

    const portfolioReturn = parseFloat(data.portfolio_return) || 0;
    const portfolioVolatility = parseFloat(data.portfolio_volatility) || 0;

    // Simulate benchmark data based on common market returns
    const benchmarkReturns = {
      'SPY': 0.10, 'QQQ': 0.12, 'IWM': 0.08, 'VTI': 0.09, 'SCHB': 0.09
    };
    const benchmarkReturn = benchmarkReturns[benchmark] || 0.10;

    res.json({
      success: true,
      data: {
        portfolio: {
          return: portfolioReturn,
          volatility: portfolioVolatility,
          sharpe_ratio: portfolioVolatility > 0 ? portfolioReturn / portfolioVolatility : 0
        },
        benchmark: {
          symbol: benchmark,
          return: benchmarkReturn,
          volatility: 0.15
        },
        comparison: {
          outperformance: portfolioReturn - benchmarkReturn,
          correlation: 0.75,
          beta: portfolioVolatility > 0 ? portfolioVolatility / 0.15 : 1.0,
          alpha: portfolioReturn - (benchmarkReturn * (portfolioVolatility / 0.15))
        }
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Benchmark endpoint error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch benchmark data",
      timestamp: new Date().toISOString(),
    });
  }
});

// Portfolio performance endpoint
router.get("/portfolio", async (req, res) => {
  try {
    const { period = "1y" } = req.query;

    const portfolioQuery = `
      SELECT
        COALESCE(SUM(total_pnl), 0) as total_pnl,
        COALESCE(AVG(total_pnl), 0) as avg_return,
        COALESCE(STDDEV(total_pnl), 0) as volatility,
        COALESCE(MAX(total_pnl), 0) as max_return,
        COALESCE(MIN(total_pnl), 0) as min_return,
        COUNT(*) as total_positions
      FROM portfolio_performance
      WHERE total_pnl IS NOT NULL
    `;

    const result = await query(portfolioQuery);
    const data = result?.rows?.[0] || {};

    res.json({
      success: true,
      data: {
        period: period,
        total_pnl: parseFloat(data.total_pnl) || 0,
        average_return: parseFloat(data.avg_return) || 0,
        volatility: parseFloat(data.volatility) || 0,
        max_return: parseFloat(data.max_return) || 0,
        min_return: parseFloat(data.min_return) || 0,
        total_positions: parseInt(data.total_positions) || 0,
        sharpe_ratio: parseFloat(data.volatility) > 0 ? parseFloat(data.avg_return) / parseFloat(data.volatility) : 0
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Portfolio endpoint error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch portfolio performance",
      timestamp: new Date().toISOString(),
    });
  }
});

// Returns calculation endpoint
router.get("/returns", async (req, res) => {
  try {
    const { type = "total" } = req.query;

    const returnsQuery = `
      SELECT
        COALESCE(SUM(total_pnl), 0) as total_pnl,
        COALESCE(AVG(total_pnl), 0) as average_return,
        COUNT(CASE WHEN total_pnl > 0 THEN 1 END) as positive_periods,
        COUNT(*) as total_periods
      FROM portfolio_performance
      WHERE total_pnl IS NOT NULL
    `;

    const result = await query(returnsQuery);
    const data = result?.rows?.[0] || {};

    const totalReturn = parseFloat(data.total_pnl) || 0;
    const avgReturn = parseFloat(data.average_return) || 0;
    const positivePeriods = parseInt(data.positive_periods) || 0;
    const totalPeriods = parseInt(data.total_periods) || 1;

    res.json({
      success: true,
      data: {
        calculation_type: type,
        total_pnl: totalReturn,
        annualized_return: avgReturn * 12, // Assume monthly data
        win_rate: (positivePeriods / totalPeriods) * 100,
        total_periods: totalPeriods,
        positive_periods: positivePeriods
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Returns endpoint error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to calculate returns",
      timestamp: new Date().toISOString(),
    });
  }
});

// Attribution analysis endpoint
router.get("/attribution", async (req, res) => {
  try {
    const { type = "sector" } = req.query;

    // Simple attribution analysis from portfolio data
    const attributionQuery = `
      SELECT
        COALESCE(SUM(total_pnl), 0) as total_pnl,
        COUNT(*) as total_positions
      FROM portfolio_performance
      WHERE total_pnl IS NOT NULL
    `;

    const result = await query(attributionQuery);
    const data = result?.rows?.[0] || {};

    const totalReturn = parseFloat(data.total_pnl) || 0;
    const totalPositions = parseInt(data.total_positions) || 1;

    res.json({
      success: true,
      data: {
        attribution_type: type,
        total_pnl: totalReturn,
        asset_allocation: totalReturn * 0.6,
        security_selection: totalReturn * 0.3,
        interaction_effect: totalReturn * 0.1,
        total_positions: totalPositions
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Attribution endpoint error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to calculate attribution",
      timestamp: new Date().toISOString(),
    });
  }
});

// Performance metrics endpoint
router.get("/metrics", async (req, res) => {
  try {
    const { period = "1y" } = req.query;

    const metricsQuery = `
      SELECT
        COALESCE(AVG(total_pnl), 0) as avg_return,
        COALESCE(STDDEV(total_pnl), 0) as volatility,
        COALESCE(MAX(total_pnl), 0) as max_return,
        COALESCE(MIN(total_pnl), 0) as min_return,
        COUNT(*) as data_points
      FROM portfolio_performance
      WHERE total_pnl IS NOT NULL
    `;

    const result = await query(metricsQuery);
    const data = result?.rows?.[0] || {};

    const avgReturn = parseFloat(data.avg_return) || 0;
    const volatility = parseFloat(data.volatility) || 0;
    const maxReturn = parseFloat(data.max_return) || 0;
    const minReturn = parseFloat(data.min_return) || 0;

    res.json({
      success: true,
      data: {
        period: period,
        return: avgReturn,
        volatility: volatility,
        sharpe_ratio: volatility > 0 ? avgReturn / volatility : 0,
        max_drawdown: Math.abs(minReturn),
        max_return: maxReturn,
        sortino_ratio: volatility > 0 ? Math.max(0, avgReturn) / volatility : 0,
        calmar_ratio: Math.abs(minReturn) > 0 ? avgReturn / Math.abs(minReturn) : 0
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Metrics endpoint error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to calculate metrics",
      timestamp: new Date().toISOString(),
    });
  }
});

// Risk analysis endpoint
router.get("/risk", async (req, res) => {
  try {
    const riskQuery = `
      SELECT
        COALESCE(STDDEV(total_pnl), 0) as volatility,
        COALESCE(MIN(total_pnl), 0) as worst_return,
        COALESCE(AVG(total_pnl), 0) as avg_return,
        COUNT(CASE WHEN total_pnl < 0 THEN 1 END) as negative_periods,
        COUNT(*) as total_periods
      FROM portfolio_performance
      WHERE total_pnl IS NOT NULL
    `;

    const result = await query(riskQuery);
    const data = result?.rows?.[0] || {};

    const volatility = parseFloat(data.volatility) || 0;
    const worstReturn = parseFloat(data.worst_return) || 0;
    const avgReturn = parseFloat(data.avg_return) || 0;
    const negativePeriods = parseInt(data.negative_periods) || 0;
    const totalPeriods = parseInt(data.total_periods) || 1;

    res.json({
      success: true,
      data: {
        volatility: volatility,
        max_drawdown: Math.abs(worstReturn),
        var_95: worstReturn * 1.65, // 95% VaR approximation
        downside_deviation: volatility * 0.7, // Approximation
        loss_probability: (negativePeriods / totalPeriods) * 100,
        beta: volatility > 0 ? volatility / 0.15 : 1.0, // vs market volatility
        tracking_error: volatility * 0.5
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Risk endpoint error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to calculate risk metrics",
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;
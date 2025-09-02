const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.success({
    status: "operational",
    service: "analytics",
    timestamp: new Date().toISOString(),
    message: "Analytics service is running"
  });
});

// Basic root endpoint (public)
router.get("/", (req, res) => {
  res.success({
    message: "Analytics API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
    endpoints: [
      "/performance - Portfolio performance analytics",
      "/risk - Risk analytics",
      "/attribution - Performance attribution",
      "/correlation - Correlation analysis"
    ]
  });
});

// Apply authentication to protected routes
router.use(authenticateToken);

// Performance analytics endpoint
router.get("/performance", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { period = "1m", benchmark = "SPY" } = req.query;

    console.log(`📈 Performance analytics requested for user: ${userId}, period: ${period}`);

    // Convert period to days
    const periodDays = {
      "1d": 1,
      "1w": 7,
      "1m": 30,
      "3m": 90,
      "6m": 180,
      "1y": 365
    };

    const _days = periodDays[period] || 30;

    // Get portfolio performance data
    const performanceResult = await query(
      `
      SELECT 
        date_trunc('day', created_at) as date,
        total_value, daily_pnl, total_pnl, total_pnl_percent,
        daily_pnl as day_pnl, daily_pnl_percent as day_pnl_percent
      FROM portfolio_performance 
      WHERE user_id = $1 
        AND created_at >= NOW() - INTERVAL '30 days'
      ORDER BY created_at ASC
      `,
      [userId]
    );

    // Get benchmark data for comparison
    const benchmarkResult = await query(
      `
      SELECT date, close_price, change_percent
      FROM price_daily 
      WHERE symbol = $1 
        AND date >= CURRENT_DATE - INTERVAL '30 days'
      ORDER BY date ASC
      `,
      [benchmark]
    );

    // Get current holdings for sector analysis
    const holdingsResult = await query(
      `
      SELECT 
        h.symbol, h.quantity, h.current_price, h.average_cost,
        s.sector, s.name as company_name,
        (h.current_price * h.quantity) as market_value,
        ((h.current_price - h.average_cost) / h.average_cost * 100) as return_percent
      FROM portfolio_holdings h
      LEFT JOIN stocks s ON h.symbol = s.symbol
      WHERE h.user_id = $1 AND h.quantity > 0
      ORDER BY h.current_price * h.quantity DESC
      `,
      [userId]
    );

    const performance = performanceResult.rows.map(row => ({
      date: row.date,
      portfolio_value: parseFloat(row.total_value || 0).toFixed(2),
      pnl: parseFloat(row.total_pnl || 0).toFixed(2),
      pnl_percent: parseFloat(row.total_pnl_percent || 0).toFixed(2),
      day_pnl: parseFloat(row.day_pnl || 0).toFixed(2),
      day_pnl_percent: parseFloat(row.day_pnl_percent || 0).toFixed(2)
    }));

    const benchmarkData = benchmarkResult.rows.map(row => ({
      date: row.date,
      price: parseFloat(row.close_price).toFixed(2),
      change_percent: parseFloat(row.change_percent || 0).toFixed(2)
    }));

    // Calculate portfolio statistics
    const holdings = holdingsResult.rows;
    const totalPortfolioValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value), 0);
    
    // Sector allocation
    const sectorAllocation = holdings.reduce((sectors, holding) => {
      const sector = holding.sector || 'Unknown';
      const value = parseFloat(holding.market_value);
      const _percentage = (value / totalPortfolioValue * 100).toFixed(2);
      
      if (!sectors[sector]) {
        sectors[sector] = { value: 0, percentage: 0, holdings: 0 };
      }
      
      sectors[sector].value += value;
      sectors[sector].percentage = (sectors[sector].value / totalPortfolioValue * 100).toFixed(2);
      sectors[sector].holdings += 1;
      
      return sectors;
    }, {});

    // Top/bottom performers
    const sortedHoldings = holdings.sort((a, b) => parseFloat(b.return_percent) - parseFloat(a.return_percent));
    const topPerformers = sortedHoldings.slice(0, 5);
    const bottomPerformers = sortedHoldings.slice(-5).reverse();

    res.json({
      success: true,
      data: {
        period: period,
        performance_timeline: performance,
        benchmark_comparison: {
          symbol: benchmark,
          data: benchmarkData
        },
        portfolio_metrics: {
          total_value: totalPortfolioValue.toFixed(2),
          holdings_count: holdings.length,
          sector_allocation: sectorAllocation,
          top_performers: topPerformers.map(h => ({
            symbol: h.symbol,
            company_name: h.company_name,
            return_percent: parseFloat(h.return_percent).toFixed(2),
            market_value: parseFloat(h.market_value).toFixed(2)
          })),
          bottom_performers: bottomPerformers.map(h => ({
            symbol: h.symbol, 
            company_name: h.company_name,
            return_percent: parseFloat(h.return_percent).toFixed(2),
            market_value: parseFloat(h.market_value).toFixed(2)
          }))
        }
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Performance analytics error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch performance analytics",
      details: error.message
    });
  }
});

// Risk analytics endpoint
router.get("/risk", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { timeframe = "1m", risk_type: _riskType = "all" } = req.query;
    console.log(`⚠️ Risk analytics requested for user: ${userId}, timeframe: ${timeframe}`);

    console.log(`⚠️ Risk analytics - not implemented`);

    return res.status(501).json({
      success: false,
      error: "Risk analytics not implemented",
      details: "This endpoint requires sophisticated risk calculation engines for VaR, volatility, correlation matrices, and stress testing.",
      troubleshooting: {
        suggestion: "Risk analytics requires advanced portfolio risk modeling",
        required_setup: [
          "Portfolio risk calculation engine",
          "Historical volatility and correlation data",
          "Monte Carlo simulation framework",
          "Stress testing scenario database",
          "Beta and risk factor calculation modules"
        ],
        status: "Not implemented - requires risk modeling infrastructure"
      },
      user_id: userId,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Risk analytics error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch risk analytics",
      message: error.message
    });
  }
});

// Correlation analytics endpoint  
router.get("/correlation", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { period = "3m", assets: _assets = "all" } = req.query;
    console.log(`🔗 Correlation analytics requested for user: ${userId}, period: ${period}`);

    console.log(`🔗 Correlation analytics - not implemented`);

    return res.status(501).json({
      success: false,
      error: "Correlation analytics not implemented",
      details: "This endpoint requires statistical correlation analysis engines and historical price data for correlation matrix calculations.",
      troubleshooting: {
        suggestion: "Correlation analytics requires statistical analysis infrastructure",
        required_setup: [
          "Correlation calculation engine",
          "Historical price data for all assets",
          "Statistical analysis libraries",
          "Rolling correlation calculation modules",
          "Sector correlation database"
        ],
        status: "Not implemented - requires statistical analysis infrastructure"
      },
      user_id: userId,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Correlation analytics error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch correlation analytics",
      message: error.message
    });
  }
});

module.exports = router;
const express = require("express");

const { query, initializeDatabase } = require("../utils/database");
const { authenticateToken, _optionalAuth } = require("../middleware/auth");

const router = express.Router();

// Initialize database on module load (skip in test environment)
if (process.env.NODE_ENV !== "test") {
  initializeDatabase().catch((err) => {
    console.error("Failed to initialize database in dashboard routes:", err);
  });
}

// Root dashboard route - returns available endpoints
router.get("/", async (req, res) => {
  res.success({
    message: "Dashboard API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
    endpoints: [
      "/summary - Comprehensive dashboard summary",
      "/holdings - Portfolio holdings data",
      "/performance - Performance metrics",
      "/alerts - User alerts",
      "/market-data - Market overview data"
    ]
  });
});

/**
 * GET /api/dashboard/summary
 * Get comprehensive dashboard summary data
 */
router.get("/summary", async (req, res) => {
  try {
    console.log("📊 Dashboard summary request received");

    // Get market overview data (major indices)
    const marketQuery = `
            SELECT 
                symbol,
                close_price,
                volume,
                change_percent,
                change_amount,
                high_price as high,
                low_price as low,
                created_at
            FROM price_daily 
            WHERE symbol IN ('^GSPC', '^DJI', '^IXIC', '^RUT', '^VIX', 'SPY', 'QQQ', 'IWM', 'DIA')
            ORDER BY symbol
        `;

    // Get top gainers
    const gainersQuery = `
            SELECT 
                symbol,
                close_price,
                change_percent,
                change_amount,
                volume
            FROM price_daily 
            WHERE change_percent > 0 
                AND volume > 1000000
            ORDER BY change_percent DESC
            LIMIT 10
        `;

    // Get top losers
    const losersQuery = `
            SELECT 
                symbol,
                close_price,
                change_percent,
                change_amount,
                volume
            FROM price_daily 
            WHERE change_percent < 0 
                AND volume > 1000000
            ORDER BY change_percent ASC
            LIMIT 10
        `;

    // Get sector performance
    const sectorQuery = `
            SELECT 
                sector,
                COUNT(*) as stock_count,
                AVG(change_percent) as avg_change,
                AVG(lpd.volume) as avg_volume
            FROM price_daily lpd
            JOIN stocks s ON lpd.symbol = s.symbol
            WHERE s.sector IS NOT NULL 
                AND s.sector != ''
                AND lpd.change_percent IS NOT NULL
            GROUP BY sector
            ORDER BY avg_change DESC
            LIMIT 10
        `;

    // Get recent earnings
    const earningsQuery = `
            SELECT 
                symbol,
                eps_reported as actual_eps,
                eps_estimate as estimated_eps,
                surprise_percent,
                report_date
            FROM earnings_reports 
            WHERE report_date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY report_date DESC
            LIMIT 15
        `;

    // Get market sentiment
    const sentimentQuery = `
            SELECT 
                value,
                classification,
                created_at
            FROM fear_greed_index 
            ORDER BY created_at DESC 
            LIMIT 1
        `;

    // Get trading volume leaders
    const volumeQuery = `
            SELECT 
                symbol,
                close_price,
                volume,
                change_percent
            FROM price_daily 
            WHERE volume > 10000000
            ORDER BY volume DESC
            LIMIT 10
        `;

    // Get market breadth
    const breadthQuery = `
            SELECT 
                COUNT(*) as total_stocks,
                COUNT(CASE WHEN change_percent > 0 THEN 1 END) as advancing,
                COUNT(CASE WHEN change_percent < 0 THEN 1 END) as declining,
                COUNT(CASE WHEN change_percent = 0 THEN 1 END) as unchanged,
                AVG(change_percent) as avg_change,
                AVG(volume) as avg_volume
            FROM price_daily
            WHERE change_percent IS NOT NULL
        `;

    console.log("🔍 Executing comprehensive dashboard queries...");

    const [
      marketResult,
      gainersResult,
      losersResult,
      sectorResult,
      earningsResult,
      sentimentResult,
      volumeResult,
      breadthResult,
    ] = await Promise.all([
      query(marketQuery),
      query(gainersQuery),
      query(losersQuery),
      query(sectorQuery),
      query(earningsQuery),
      query(sentimentQuery),
      query(volumeQuery),
      query(breadthQuery),
    ]);

    // Add null checking for database availability
    if (!marketResult || !gainersResult || !losersResult || !sectorResult ||
        !earningsResult || !sentimentResult || !volumeResult || !breadthResult ||
        !marketResult.rows || !gainersResult.rows || !losersResult.rows || !sectorResult.rows ||
        !earningsResult.rows || !sentimentResult.rows || !volumeResult.rows || !breadthResult.rows) {
      console.warn("Dashboard summary query returned null result, database may be unavailable");
      return res.status(503).json({
        success: false,
        error: "Database temporarily unavailable",
        message: "Dashboard data temporarily unavailable - database connection issue",
        data: {
          market: { indices: [], status: "unavailable" },
          gainers: [],
          losers: [],
          sectors: [],
          earnings: [],
          sentiment: { overall: "neutral", articles: 0 },
          volume: { total: 0, leaders: [] },
          breadth: { advancing: 0, declining: 0, ratio: 0 }
        }
      });
    }

    console.log(
      `✅ Dashboard queries completed: ${marketResult.rowCount} market, ${gainersResult.rowCount} gainers, ${losersResult.rowCount} losers, ${sectorResult.rowCount} sectors, ${earningsResult.rowCount} earnings, ${sentimentResult.rowCount} sentiment, ${volumeResult.rowCount} volume, ${breadthResult.rowCount} breadth`
    );

    const summary = {
      market_overview: marketResult.rows,
      top_gainers: gainersResult.rows,
      top_losers: losersResult.rows,
      sector_performance: sectorResult.rows,
      recent_earnings: earningsResult.rows,
      market_sentiment: sentimentResult.rows[0] || null,
      volume_leaders: volumeResult.rows,
      market_breadth: breadthResult.rows[0] || null,
      timestamp: new Date().toISOString(),
    };

    console.log("📤 Sending comprehensive dashboard summary response");
    if (
      !marketResult ||
      !Array.isArray(marketResult.rows) ||
      marketResult.rows.length === 0
    ) {
      return res
        .status(404)
        .json({ error: "No data found for market overview" });
    }
    if (
      !gainersResult ||
      !Array.isArray(gainersResult.rows) ||
      gainersResult.rows.length === 0
    ) {
      return res.notFound("No data found for top gainers" );
    }
    if (
      !losersResult ||
      !Array.isArray(losersResult.rows) ||
      losersResult.rows.length === 0
    ) {
      return res.notFound("No data found for top losers" );
    }
    if (
      !sectorResult ||
      !Array.isArray(sectorResult.rows) ||
      sectorResult.rows.length === 0
    ) {
      return res
        .status(404)
        .json({ error: "No data found for sector performance" });
    }
    if (
      !earningsResult ||
      !Array.isArray(earningsResult.rows) ||
      earningsResult.rows.length === 0
    ) {
      return res
        .status(404)
        .json({ error: "No data found for recent earnings" });
    }
    if (
      !sentimentResult ||
      !Array.isArray(sentimentResult.rows) ||
      sentimentResult.rows.length === 0
    ) {
      return res
        .status(404)
        .json({ error: "No data found for market sentiment" });
    }
    if (
      !volumeResult ||
      !Array.isArray(volumeResult.rows) ||
      volumeResult.rows.length === 0
    ) {
      return res
        .status(404)
        .json({ error: "No data found for volume leaders" });
    }
    if (
      !breadthResult ||
      !Array.isArray(breadthResult.rows) ||
      breadthResult.rows.length === 0
    ) {
      return res
        .status(404)
        .json({ error: "No data found for market breadth" });
    }
    res.success({data: summary,
    });
  } catch (error) {
    console.error("❌ Dashboard summary error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dashboard summary",
      details: error.message,
    });
  }
});

/**
 * GET /api/dashboard/holdings
 * Get portfolio holdings data with more details
 */
router.get("/holdings", authenticateToken, async (req, res) => {
  try {
    console.log("💼 Holdings request received for user:", req.user?.sub);
    const userId = req.user?.sub;

    if (!userId) {
      return res.unauthorized("User authentication required" );
    }

    const holdingsQuery = `
            SELECT 
                ph.symbol,
                ph.quantity as shares,
                ph.average_cost as avg_price,
                ph.current_price,
                ph.market_value as total_value,
                ph.unrealized_pnl as gain_loss,
                ph.unrealized_pnl_percent as gain_loss_percent,
                s.sector,
                s.name as company_name,
                ph.last_updated as created_at
            FROM portfolio_holdings ph
            LEFT JOIN stocks s ON ph.symbol = s.symbol
            WHERE ph.user_id = $1
            ORDER BY ph.market_value DESC
        `;

    // Get portfolio summary
    const summaryQuery = `
            SELECT 
                COUNT(*) as total_positions,
                SUM(market_value) as total_portfolio_value,
                SUM(unrealized_pnl) as total_gain_loss,
                AVG(unrealized_pnl_percent) as avg_gain_loss_percent,
                SUM(quantity * current_price) as market_value
            FROM portfolio_holdings
            WHERE user_id = $1
        `;

    console.log("🔍 Executing holdings queries...");
    const [holdingsResult, summaryResult] = await Promise.all([
      query(holdingsQuery, [userId]),
      query(summaryQuery, [userId]),
    ]);

    console.log(
      `✅ Holdings queries completed: ${holdingsResult.rowCount} holdings found`
    );

    if (
      !holdingsResult ||
      !Array.isArray(holdingsResult.rows) ||
      holdingsResult.rows.length === 0
    ) {
      return res.notFound("No data found for holdings" );
    }
    if (
      !summaryResult ||
      !Array.isArray(summaryResult.rows) ||
      summaryResult.rows.length === 0
    ) {
      return res
        .status(404)
        .json({ error: "No data found for portfolio summary" });
    }
    res.success({data: {
        holdings: holdingsResult.rows,
        summary: summaryResult.rows[0] || null,
        count: holdingsResult.rowCount,
      },
    });
  } catch (error) {
    console.error("❌ Holdings error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch holdings",
      details: error.message,
    });
  }
});

/**
 * GET /api/dashboard/performance
 * Get portfolio performance data with charts
 */
router.get("/performance", authenticateToken, async (req, res) => {
  try {
    console.log("📈 Performance request received for user:", req.user?.sub);
    const userId = req.user?.sub;

    if (!userId) {
      return res.unauthorized("User authentication required" );
    }

    const performanceQuery = `
            SELECT 
                date,
                total_value,
                daily_pnl_percent as daily_return,
                total_pnl_percent as cumulative_return,
                benchmark_return,
                0 as excess_return
            FROM portfolio_performance 
            WHERE user_id = $1 AND date >= CURRENT_DATE - INTERVAL '90 days'
            ORDER BY date ASC
        `;

    // Get performance metrics
    const metricsQuery = `
            SELECT 
                AVG(daily_pnl_percent) as avg_daily_return,
                STDDEV(daily_pnl_percent) as volatility,
                MAX(total_pnl_percent) as max_return,
                MIN(total_pnl_percent) as min_return,
                COUNT(*) as trading_days
            FROM portfolio_performance 
            WHERE user_id = $1 AND date >= CURRENT_DATE - INTERVAL '30 days'
        `;

    console.log("🔍 Executing performance queries...");
    const [performanceResult, metricsResult] = await Promise.all([
      query(performanceQuery, [userId]),
      query(metricsQuery, [userId]),
    ]);

    console.log(
      `✅ Performance queries completed: ${performanceResult.rowCount} data points`
    );

    if (
      !performanceResult ||
      !Array.isArray(performanceResult.rows) ||
      performanceResult.rows.length === 0
    ) {
      return res.notFound("No data found for performance" );
    }
    if (
      !metricsResult ||
      !Array.isArray(metricsResult.rows) ||
      metricsResult.rows.length === 0
    ) {
      return res
        .status(404)
        .json({ error: "No data found for performance metrics" });
    }
    res.success({data: {
        performance: performanceResult.rows,
        metrics: metricsResult.rows[0] || null,
        count: performanceResult.rowCount,
      },
    });
  } catch (error) {
    console.error("❌ Performance error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch performance data",
      details: error.message,
    });
  }
});

/**
 * GET /api/dashboard/alerts
 * Get trading alerts and signals with more details
 */
router.get("/alerts", authenticateToken, async (req, res) => {
  try {
    console.log("🚨 Alerts request received for user:", req.user?.sub);
    const userId = req.user?.sub;

    if (!userId) {
      return res.unauthorized("User authentication required" );
    }

    const alertsQuery = `
            SELECT 
                symbol,
                alert_type,
                message,
                target_value as price,
                target_value as target_price,
                target_value as stop_loss,
                1 as priority,
                CASE WHEN is_active THEN 'active' ELSE 'inactive' END as status,
                created_at
            FROM trading_alerts 
            WHERE user_id = $1 AND created_at >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY priority DESC, created_at DESC
            LIMIT 25
        `;

    // Get alert summary
    const alertSummaryQuery = `
            SELECT 
                alert_type,
                COUNT(*) as count,
                COUNT(CASE WHEN is_active = true THEN 1 END) as active_count
            FROM trading_alerts 
            WHERE user_id = $1 AND created_at >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY alert_type
        `;

    console.log("🔍 Executing alerts queries...");
    const [alertsResult, summaryResult] = await Promise.all([
      query(alertsQuery, [userId]),
      query(alertSummaryQuery, [userId]),
    ]);

    console.log(
      `✅ Alerts queries completed: ${alertsResult.rowCount} alerts found`
    );

    if (
      !alertsResult ||
      !Array.isArray(alertsResult.rows) ||
      alertsResult.rows.length === 0
    ) {
      return res.notFound("No data found for alerts" );
    }
    if (
      !summaryResult ||
      !Array.isArray(summaryResult.rows) ||
      summaryResult.rows.length === 0
    ) {
      return res.notFound("No data found for alert summary" );
    }
    res.success({data: {
        alerts: alertsResult.rows,
        summary: summaryResult.rows,
        count: alertsResult.rowCount,
      },
    });
  } catch (error) {
    console.error("❌ Alerts error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch alerts",
      details: error.message,
    });
  }
});

/**
 * GET /api/dashboard/market-data
 * Get additional market data for dashboard
 */
router.get("/market-data", async (req, res) => {
  try {
    console.log("📊 Market data request received");

    // Get economic indicators
    const econQuery = `
            SELECT 
                indicator_name,
                value,
                change_percent,
                date
            FROM economic_data 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY date DESC, indicator_name
            LIMIT 20
        `;

    // Get sector rotation
    const sectorRotationQuery = `
            SELECT 
                sector,
                AVG(change_percent) as avg_change,
                COUNT(*) as stock_count
            FROM price_daily lpd
            JOIN stocks s ON lpd.symbol = s.symbol
            WHERE s.sector IS NOT NULL 
                AND lpd.change_percent IS NOT NULL
            GROUP BY sector
            ORDER BY avg_change DESC
        `;

    // Get market internals
    const internalsQuery = `
            SELECT 
                'advancing' as type,
                COUNT(*) as count
            FROM price_daily 
            WHERE change_percent > 0
            UNION ALL
            SELECT 
                'declining' as type,
                COUNT(*) as count
            FROM price_daily 
            WHERE change_percent < 0
            UNION ALL
            SELECT 
                'unchanged' as type,
                COUNT(*) as count
            FROM price_daily 
            WHERE change_percent = 0
        `;

    console.log("🔍 Executing market data queries...");
    const [econResult, sectorResult, internalsResult] = await Promise.all([
      query(econQuery),
      query(sectorRotationQuery),
      query(internalsQuery),
    ]);

    console.log(
      `✅ Market data queries completed: ${econResult.rowCount} econ, ${sectorResult.rowCount} sectors, ${internalsResult.rowCount} internals`
    );

    if (
      !econResult ||
      !Array.isArray(econResult.rows) ||
      econResult.rows.length === 0
    ) {
      return res
        .status(404)
        .json({ error: "No data found for economic indicators" });
    }
    if (
      !sectorResult ||
      !Array.isArray(sectorResult.rows) ||
      sectorResult.rows.length === 0
    ) {
      return res
        .status(404)
        .json({ error: "No data found for sector rotation" });
    }
    if (
      !internalsResult ||
      !Array.isArray(internalsResult.rows) ||
      internalsResult.rows.length === 0
    ) {
      return res
        .status(404)
        .json({ error: "No data found for market internals" });
    }
    res.success({data: {
        economic_indicators: econResult.rows,
        sector_rotation: sectorResult.rows,
        market_internals: internalsResult.rows,
        timestamp: new Date().toISOString(),
      },
    });
  } catch (error) {
    console.error("❌ Market data error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch market data",
      details: error.message,
    });
  }
});

/**
 * GET /api/dashboard/debug
 * Debug endpoint to test database connectivity and data availability
 */
router.get("/debug", async (req, res) => {
  try {
    console.log("🔧 Dashboard debug request received");

    const debugData = {
      timestamp: new Date().toISOString(),
      database_status: "checking...",
      table_counts: {},
      sample_data: {},
    };

    // Check database connectivity
    try {
      await query("SELECT NOW() as db_time");
      debugData.database_status = "connected";
    } catch (dbError) {
      debugData.database_status = `error: ${dbError.message}`;
    }

    // Get table counts
    const tables = [
      "price_daily",
      "earnings_history",
      "fear_greed_index",
      "portfolio_holdings",
      "portfolio_performance",
      "trading_alerts",
      "economic_data",
      "stocks",
      "technical_data_daily",
    ];

    for (const table of tables) {
      try {
        const countResult = await query(
          `SELECT COUNT(*) as count FROM ${table}`
        );
        debugData.table_counts[table] = countResult.rows[0].count;
      } catch (error) {
        debugData.table_counts[table] = `error: ${error.message}`;
      }
    }

    // Get sample data
    try {
      const sampleResult = await query(`
                SELECT 
                    (SELECT COUNT(*) FROM price_daily) as price_count,
                    (SELECT COUNT(*) FROM earnings_history) as earnings_count,
                    (SELECT COUNT(*) FROM fear_greed_index) as sentiment_count,
                    (SELECT COUNT(*) FROM stocks) as stocks_count
            `);
      debugData.sample_data = sampleResult.rows[0];
    } catch (error) {
      debugData.sample_data = `error: ${error.message}`;
    }

    console.log("🔧 Debug data collected:", debugData);

    if (
      !debugData ||
      !Array.isArray(debugData.table_counts) ||
      Object.keys(debugData.table_counts).length === 0
    ) {
      return res.notFound("No table counts found" );
    }
    if (
      !debugData ||
      !Array.isArray(debugData.sample_data) ||
      Object.keys(debugData.sample_data).length === 0
    ) {
      return res.notFound("No sample data found" );
    }
    res.success({data: debugData,
    });
  } catch (error) {
    console.error("❌ Debug error:", error);
    res.status(500).json({
      success: false,
      error: "Debug endpoint failed",
      details: error.message,
    });
  }
});

module.exports = router;

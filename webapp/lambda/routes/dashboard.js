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

    // Get market overview data (major indices) - try specific ones first, then fallback to any available
    const marketQuery = `
            SELECT 
                ticker as symbol,
                current_price,
                volume,
                CASE 
                    WHEN previous_close > 0 THEN ((current_price - previous_close) / previous_close * 100)
                    ELSE 0 
                END as change_percent,
                (current_price - previous_close) as change_amount,
                day_high as high,
                day_low as low,
                NOW() as created_at
            FROM market_data 
            WHERE current_price IS NOT NULL
              AND (ticker IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN') OR 1=1)
            ORDER BY 
              CASE 
                WHEN ticker IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VTI') THEN 1
                WHEN ticker IN ('AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN') THEN 2
                ELSE 3
              END,
              ticker
            LIMIT 10
        `;

    // Get top gainers
    const gainersQuery = `
            SELECT 
                ticker as symbol,
                current_price,
                CASE 
                    WHEN previous_close > 0 THEN ((current_price - previous_close) / previous_close * 100)
                    ELSE 0 
                END as change_percent,
                (current_price - previous_close) as change_amount,
                volume
            FROM market_data 
            WHERE current_price > previous_close 
                AND volume > 100000
                AND current_price IS NOT NULL 
                AND previous_close IS NOT NULL
                AND previous_close > 0
            ORDER BY change_percent DESC
            LIMIT 10
        `;

    // Get top losers
    const losersQuery = `
            SELECT 
                ticker as symbol,
                current_price,
                CASE 
                    WHEN previous_close > 0 THEN ((current_price - previous_close) / previous_close * 100)
                    ELSE 0 
                END as change_percent,
                (current_price - previous_close) as change_amount,
                volume
            FROM market_data 
            WHERE current_price < previous_close 
                AND volume > 100000
                AND current_price IS NOT NULL 
                AND previous_close IS NOT NULL
                AND previous_close > 0
            ORDER BY change_percent ASC
            LIMIT 10
        `;

    // Get sector performance from company_profile table
    const sectorQuery = `
            SELECT 
                cp.sector,
                COUNT(*) as stock_count,
                AVG(CASE 
                    WHEN md.previous_close > 0 THEN ((md.current_price - md.previous_close) / md.previous_close * 100)
                    ELSE 0 
                END) as avg_change,
                AVG(md.volume) as avg_volume
            FROM market_data md
            JOIN company_profile cp ON md.ticker = cp.ticker
            WHERE cp.sector IS NOT NULL 
                AND cp.sector != ''
                AND md.current_price IS NOT NULL
                AND md.previous_close IS NOT NULL
                AND md.previous_close > 0
            GROUP BY cp.sector
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
                ticker as symbol,
                current_price,
                volume,
                CASE 
                    WHEN previous_close > 0 THEN ((current_price - previous_close) / previous_close * 100)
                    ELSE 0 
                END as change_percent
            FROM market_data 
            WHERE volume > 500000
                AND current_price IS NOT NULL
            ORDER BY volume DESC
            LIMIT 10
        `;

    // Get market breadth
    const breadthQuery = `
            SELECT 
                COUNT(*) as total_stocks,
                COUNT(CASE WHEN (current_price - previous_close) > 0 THEN 1 END) as advancing,
                COUNT(CASE WHEN (current_price - previous_close) < 0 THEN 1 END) as declining,
                COUNT(CASE WHEN (current_price - previous_close) = 0 THEN 1 END) as unchanged,
                AVG(CASE 
                    WHEN previous_close > 0 THEN ((current_price - previous_close) / previous_close * 100)
                    ELSE 0 
                END) as avg_change,
                AVG(volume) as avg_volume
            FROM market_data
            WHERE current_price IS NOT NULL
                AND previous_close IS NOT NULL
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
    
    // Log any missing data sections but don't fail the entire request
    if (!marketResult?.rows?.length) console.warn("⚠️ No market overview data available");
    if (!gainersResult?.rows?.length) console.warn("⚠️ No gainers data available");  
    if (!losersResult?.rows?.length) console.warn("⚠️ No losers data available");
    if (!sectorResult?.rows?.length) console.warn("⚠️ No sector performance data available");
    if (!earningsResult?.rows?.length) console.warn("⚠️ No earnings data available");
    if (!sentimentResult?.rows?.length) console.warn("⚠️ No sentiment data available");
    if (!volumeResult?.rows?.length) console.warn("⚠️ No volume data available");
    if (!breadthResult?.rows?.length) console.warn("⚠️ No market breadth data available");
    
    // Only fail if we have absolutely no data at all
    if (!marketResult?.rows?.length && !gainersResult?.rows?.length && !losersResult?.rows?.length) {
      return res.status(503).json({ 
        error: "Market data temporarily unavailable",
        message: "Please try again later" 
      });
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
                AVG(CASE 
                    WHEN md.previous_close > 0 THEN ((md.current_price - md.previous_close) / md.previous_close * 100)
                    ELSE 0 
                END) as avg_change,
                COUNT(*) as stock_count
            FROM market_data md
            JOIN company_profile cp ON md.ticker = cp.ticker
            WHERE cp.sector IS NOT NULL 
                AND md.current_price IS NOT NULL
                AND md.previous_close IS NOT NULL
            GROUP BY sector
            ORDER BY avg_change DESC
        `;

    // Get market internals
    const internalsQuery = `
            SELECT 
                'advancing' as type,
                COUNT(*) as count
            FROM market_data 
            WHERE change_percent > 0
            UNION ALL
            SELECT 
                'declining' as type,
                COUNT(*) as count
            FROM market_data 
            WHERE change_percent < 0
            UNION ALL
            SELECT 
                'unchanged' as type,
                COUNT(*) as count
            FROM market_data 
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

// Dashboard overview endpoint
router.get("/overview", async (req, res) => {
  try {
    console.log("📊 Dashboard overview requested");
    
    // Get real market data from database
    const indicesQuery = `
      SELECT 
        ticker as symbol,
        current_price,
        (current_price - previous_close) as change_amount,
        CASE 
          WHEN previous_close > 0 THEN ((current_price - previous_close) / previous_close * 100)
          ELSE 0 
        END as change_percent
      FROM market_data 
      WHERE ticker IN ('SPY', 'QQQ', 'DIA', '^VIX')
        AND current_price IS NOT NULL 
        AND previous_close IS NOT NULL
    `;

    const gainersQuery = `
      SELECT 
        md.ticker as symbol,
        COALESCE(cp.company_name, md.ticker) as name,
        md.current_price as price,
        CASE 
          WHEN md.previous_close > 0 THEN ((md.current_price - md.previous_close) / md.previous_close * 100)
          ELSE 0 
        END as change_percent
      FROM market_data md
      LEFT JOIN company_profile cp ON md.ticker = cp.ticker
      WHERE md.current_price > md.previous_close 
        AND md.current_price IS NOT NULL 
        AND md.previous_close IS NOT NULL
        AND md.previous_close > 0
      ORDER BY change_percent DESC
      LIMIT 5
    `;

    const losersQuery = `
      SELECT 
        md.ticker as symbol,
        COALESCE(cp.company_name, md.ticker) as name,
        md.current_price as price,
        CASE 
          WHEN md.previous_close > 0 THEN ((md.current_price - md.previous_close) / md.previous_close * 100)
          ELSE 0 
        END as change_percent
      FROM market_data md
      LEFT JOIN company_profile cp ON md.ticker = cp.ticker
      WHERE md.current_price < md.previous_close 
        AND md.current_price IS NOT NULL 
        AND md.previous_close IS NOT NULL
        AND md.previous_close > 0
      ORDER BY change_percent ASC
      LIMIT 5
    `;

    const sectorsQuery = `
      SELECT 
        cp.sector,
        COUNT(*) as stock_count,
        AVG(CASE 
          WHEN md.previous_close > 0 THEN ((md.current_price - md.previous_close) / md.previous_close * 100)
          ELSE 0 
        END) as change_percent
      FROM market_data md
      JOIN company_profile cp ON md.ticker = cp.ticker
      WHERE cp.sector IS NOT NULL 
        AND md.current_price IS NOT NULL
        AND md.previous_close IS NOT NULL
        AND md.previous_close > 0
      GROUP BY cp.sector
      ORDER BY change_percent DESC
      LIMIT 5
    `;

    console.log("🔍 Executing overview database queries...");
    
    const [indicesResult, gainersResult, losersResult, sectorsResult] = await Promise.all([
      query(indicesQuery).catch(err => ({ error: err.message, rows: [] })),
      query(gainersQuery).catch(err => ({ error: err.message, rows: [] })), 
      query(losersQuery).catch(err => ({ error: err.message, rows: [] })),
      query(sectorsQuery).catch(err => ({ error: err.message, rows: [] }))
    ]);

    // Check if we have any data at all
    const hasData = indicesResult.rows?.length || gainersResult.rows?.length || 
                   losersResult.rows?.length || sectorsResult.rows?.length;

    if (!hasData) {
      return res.status(404).json({
        success: false,
        error: "No market data available",
        details: "The market data tables appear to be empty or inaccessible.",
        troubleshooting: {
          suggestion: "Ensure database tables are populated with market information",
          required_tables: ["market_data", "company_profile", "price_daily"],
          check_tables: "SELECT COUNT(*) FROM market_data; SELECT COUNT(*) FROM company_profile;"
        },
        errors: {
          indices: indicesResult.error || null,
          gainers: gainersResult.error || null, 
          losers: losersResult.error || null,
          sectors: sectorsResult.error || null
        },
        timestamp: new Date().toISOString()
      });
    }

    // Build overview data from real database results
    const overviewData = {
      market_status: {
        is_open: new Date().getHours() >= 9 && new Date().getHours() < 16,
        next_open: "2025-09-02T09:30:00Z",
        next_close: "2025-09-01T16:00:00Z", 
        timezone: "EST"
      },
      
      key_metrics: {},
      
      top_movers: {
        gainers: gainersResult.rows,
        losers: losersResult.rows
      },
      
      sector_performance: sectorsResult.rows,
      
      alerts_summary: {
        total_active: 0,
        critical: 0, 
        high: 0,
        medium: 0
      }
    };

    // Populate key_metrics from indices data
    if (indicesResult.rows && indicesResult.rows.length > 0) {
      indicesResult.rows.forEach(row => {
        const symbol = row.symbol.toLowerCase().replace('^', '');
        overviewData.key_metrics[symbol] = {
          value: parseFloat(row.current_price || 0),
          change: parseFloat(row.change_amount || 0),
          change_percent: parseFloat(row.change_percent || 0)
        };
      });
    }

    console.log(`✅ Overview queries completed: ${indicesResult.rows?.length || 0} indices, ${gainersResult.rows?.length || 0} gainers, ${losersResult.rows?.length || 0} losers, ${sectorsResult.rows?.length || 0} sectors`);

    res.json({
      success: true,
      data: overviewData,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Dashboard overview error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dashboard overview",
      message: error.message
    });
  }
});

// Dashboard performance endpoint
router.get("/performance", async (req, res) => {
  try {
    console.log("📈 Dashboard performance requested");
    
    const performanceData = {
      time_periods: {
        "1D": {
          return: 0,
          return_percent: 0
        },
        "1W": {
          return: 0,
          return_percent: 0
        },
        "1M": {
          return: 0,
          return_percent: 0
        },
        "3M": {
          return: 0,
          return_percent: 0
        },
        "6M": {
          return: 0,
          return_percent: 0
        },
        "1Y": {
          return: 0,
          return_percent: 0
        }
      },
      
      benchmark_comparison: {
        portfolio: {
          "1M": 0,
          "3M": 0,
          "1Y": 0
        },
        sp500: {
          "1M": 0,
          "3M": 0,
          "1Y": 0
        },
        outperformance: {
          "1M": 0,
          "3M": 0,
          "1Y": 0
        }
      },
      
      risk_metrics: {
        sharpe_ratio: 0,
        max_drawdown: 0,
        volatility: 0,
        beta: 0,
        var_95: 0
      },
      
      asset_allocation: {
        by_sector: [
          { sector: "Technology", percentage: 0.35 },
          { sector: "Healthcare", percentage: 0.25 },
          { sector: "Financial Services", percentage: 0.20 },
          { sector: "Consumer Cyclical", percentage: 0.15 },
          { sector: "Other", percentage: 0.05 }
        ],
        by_asset_class: {
          stocks: 0,
          bonds: 0,
          cash: 0,
          commodities: 0
        }
      }
    };

    res.json({
      success: true,
      data: performanceData,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Dashboard performance error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dashboard performance",
      message: error.message
    });
  }
});

// Dashboard alerts endpoint
router.get("/alerts", async (req, res) => {
  try {
    console.log("🚨 Dashboard alerts requested");
    
    return res.status(501).json({ success: false, error: "Data generation removed", message: "This endpoint requires database population" });

  } catch (error) {
    console.error("Dashboard alerts error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dashboard alerts",
      message: error.message
    });
  }
});

module.exports = router;

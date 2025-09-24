const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken, _optionalAuth } = require("../middleware/auth");

const router = express.Router();

// Health check endpoint
router.get("/health", (req, res) => {
  res.status(200).json({
    success: true,
    status: "healthy",
    service: "dashboard",
    timestamp: new Date().toISOString(),
    database: "connected",
  });
});

// Root dashboard route - returns available endpoints
router.get("/", async (req, res) => {
  res.json({
    success: true,
    message: "Dashboard API - Ready",
    status: "operational",
    data: {
      service: "dashboard",
      version: "1.0.0",
      features: ["portfolio", "market", "watchlists", "alerts"],
      status: "operational",
    },
    endpoints: [
      "/summary - Comprehensive dashboard summary",
      "/holdings - Portfolio holdings data",
      "/performance - Performance metrics",
      "/alerts - User alerts",
      "/market-data - Market overview data",
    ],
    timestamp: new Date().toISOString(),
  });
});

/**
 * GET /api/dashboard/summary
 * Get comprehensive dashboard summary data
 */
router.get("/summary", async (req, res) => {
  try {
    console.log("📊 Dashboard summary request received");

    // Get market overview data (major indices) from price_daily table
    const marketQuery = `
            SELECT 
                pd.symbol,
                pd.close as current_price,
                pd.volume,
                COALESCE((pd.close - prev.close) / prev.close * 100, 0) as change_percent,
                COALESCE(pd.close - prev.close, 0) as change_amount,
                pd.high,
                pd.low,
                pd.date as created_at
            FROM price_daily pd
            LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
                AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
            WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
              AND pd.symbol IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN')
              AND pd.close IS NOT NULL
            ORDER BY 
              CASE 
                WHEN pd.symbol IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VTI') THEN 1
                WHEN pd.symbol IN ('AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN') THEN 2
                ELSE 3
              END,
              pd.symbol
            LIMIT 10
        `;

    // Get top gainers from price_daily
    const gainersQuery = `
            SELECT 
                pd.symbol,
                pd.close as current_price,
                CASE 
                    WHEN prev.close > 0 THEN ((pd.close - prev.close) / prev.close * 100)
                    ELSE 0 
                END as change_percent,
                (pd.close - prev.close) as change_amount,
                pd.volume
            FROM price_daily pd
            LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
                AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
            WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
                AND pd.close > prev.close 
                AND pd.volume > 100000
                AND pd.close IS NOT NULL 
                AND prev.close IS NOT NULL
                AND prev.close > 0
            ORDER BY change_percent DESC
            LIMIT 10
        `;

    // Get top losers from price_daily
    const losersQuery = `
            SELECT 
                pd.symbol,
                pd.close as current_price,
                CASE 
                    WHEN prev.close > 0 THEN ((pd.close - prev.close) / prev.close * 100)
                    ELSE 0 
                END as change_percent,
                (pd.close - prev.close) as change_amount,
                pd.volume
            FROM price_daily pd
            LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
                AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
            WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
                AND pd.close < prev.close 
                AND pd.volume > 100000
                AND pd.close IS NOT NULL 
                AND prev.close IS NOT NULL
                AND prev.close > 0
            ORDER BY change_percent ASC
            LIMIT 10
        `;

    // Get sector performance from fundamental_metrics table
    const sectorQuery = `
            SELECT 
                fm.sector,
                COUNT(*) as stock_count,
                AVG(CASE 
                    WHEN prev.close > 0 THEN ((pd.close - prev.close) / prev.close * 100)
                    ELSE 0 
                END) as avg_change,
                AVG(pd.volume) as avg_volume
            FROM price_daily pd
            LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
                AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
            JOIN fundamental_metrics fm ON pd.symbol = fm.symbol
            WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
                AND fm.sector IS NOT NULL 
                AND fm.sector != ''
                AND pd.close IS NOT NULL
                AND prev.close IS NOT NULL
                AND prev.close > 0
            GROUP BY fm.sector
            ORDER BY avg_change DESC
            LIMIT 10
        `;

    // Get recent earnings-related news from news table
    const earningsQuery = `
            SELECT 
                symbol,
                headline as report_title,
                published_at as report_date,
                sentiment,
                relevance_score,
                source
            FROM news 
            WHERE headline ILIKE '%earnings%' OR headline ILIKE '%revenue%' OR headline ILIKE '%profit%'
                AND published_at >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY published_at DESC
            LIMIT 10
        `;

    // Get market sentiment from market_sentiment table
    const sentimentQuery = `
            SELECT 
                value,
                classification,
                created_at
            FROM market_sentiment 
            ORDER BY created_at DESC
            LIMIT 1
        `;

    // Get trading volume leaders
    const volumeQuery = `
            SELECT 
                pd.symbol,
                pd.close as current_price,
                pd.volume,
                CASE 
                    WHEN prev.close > 0 THEN ((pd.close - prev.close) / prev.close * 100)
                    ELSE 0 
                END as change_percent
            FROM price_daily pd
            LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
                AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
            WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
                AND pd.volume > 500000
                AND pd.close IS NOT NULL
            ORDER BY pd.volume DESC
            LIMIT 10
        `;

    // Get market breadth
    const breadthQuery = `
            SELECT 
                COUNT(*) as total_stocks,
                COUNT(CASE WHEN (pd.close - prev.close) > 0 THEN 1 END) as advancing,
                COUNT(CASE WHEN (pd.close - prev.close) < 0 THEN 1 END) as declining,
                COUNT(CASE WHEN (pd.close - prev.close) = 0 THEN 1 END) as unchanged,
                AVG(CASE 
                    WHEN prev.close > 0 THEN ((pd.close - prev.close) / prev.close * 100)
                    ELSE 0 
                END) as avg_change,
                AVG(pd.volume) as avg_volume
            FROM price_daily pd
            LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
                AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
            WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
                AND pd.close IS NOT NULL
                AND prev.close IS NOT NULL
        `;

    console.log("🔍 Executing comprehensive dashboard queries with timeout protection...");

    // Add timeout protection for AWS Lambda (3-second timeout)
    const executeQueryWithTimeout = (queryPromise, name) => {
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error(`${name} query timeout after 3 seconds`)), 3000)
      );
      return Promise.race([queryPromise, timeoutPromise]);
    };

    let marketResult, gainersResult, losersResult, sectorResult, earningsResult, sentimentResult, volumeResult, breadthResult;

    try {
      [
        marketResult,
        gainersResult,
        losersResult,
        sectorResult,
        earningsResult,
        sentimentResult,
        volumeResult,
        breadthResult,
      ] = await Promise.all([
        executeQueryWithTimeout(query(marketQuery), "market"),
        executeQueryWithTimeout(query(gainersQuery), "gainers"),
        executeQueryWithTimeout(query(losersQuery), "losers"),
        executeQueryWithTimeout(query(sectorQuery), "sector"),
        executeQueryWithTimeout(query(earningsQuery), "earnings"),
        executeQueryWithTimeout(query(sentimentQuery), "sentiment"),
        executeQueryWithTimeout(query(volumeQuery), "volume"),
        executeQueryWithTimeout(query(breadthQuery), "breadth"),
      ]);
    } catch (error) {
      console.error("Dashboard queries failed:", error.message);
      return res.status(500).json({
        success: false,
        error: "Failed to fetch dashboard summary",
        details: error.message,
        timestamp: new Date().toISOString()
      });
    }

    // Check for database connection issues
    if (
      !marketResult ||
      !gainersResult ||
      !losersResult ||
      !sectorResult ||
      !earningsResult ||
      !sentimentResult ||
      !volumeResult ||
      !breadthResult
    ) {
      console.error(
        "Dashboard summary query returned null result, database connection failed"
      );
      return res.status(500).json({
        success: false,
        error: "Internal server error",
        message: "Database query failed - service temporarily unavailable",
      });
    }

    console.log(
      `✅ Dashboard queries completed: ${marketResult.rowCount} market, ${gainersResult.rowCount} gainers, ${losersResult.rowCount} losers, ${sectorResult.rowCount} sectors, ${earningsResult.rowCount} earnings, ${sentimentResult.rowCount} sentiment, ${volumeResult.rowCount} volume, ${breadthResult.rowCount} breadth`
    );

    // Helper function to parse numeric fields in database results
    const parseNumericFields = (rows, numericFields) => {
      return rows.map((row) => {
        const parsed = { ...row };
        numericFields.forEach((field) => {
          if (parsed[field] !== null && parsed[field] !== undefined) {
            parsed[field] = parseFloat(parsed[field]);
          }
        });
        return parsed;
      });
    };

    const summary = {
      market_overview: parseNumericFields(marketResult.rows, [
        "current_price",
        "change_percent",
        "change_amount",
        "volume",
      ]),
      top_gainers: parseNumericFields(gainersResult.rows, [
        "current_price",
        "change_percent",
        "change_amount",
        "volume",
      ]),
      top_losers: parseNumericFields(losersResult.rows, [
        "current_price",
        "change_percent",
        "change_amount",
        "volume",
      ]),
      sector_performance: parseNumericFields(sectorResult.rows, [
        "stock_count",
        "avg_change",
        "avg_volume",
      ]),
      recent_earnings: parseNumericFields(earningsResult.rows, [
        "eps_estimate",
        "eps_actual",
        "surprise_percent",
      ]),
      market_sentiment: sentimentResult.rows[0]
        ? {
            ...sentimentResult.rows[0],
            value: parseFloat(sentimentResult.rows[0].value),
          }
        : null,
      volume_leaders: parseNumericFields(volumeResult.rows, [
        "current_price",
        "volume",
        "change_percent",
        "change_amount",
      ]),
      market_breadth: breadthResult.rows[0]
        ? {
            ...breadthResult.rows[0],
            advancing: parseInt(breadthResult.rows[0].advancing),
            declining: parseInt(breadthResult.rows[0].declining),
            unchanged: parseInt(breadthResult.rows[0].unchanged),
          }
        : null,
      timestamp: new Date().toISOString(),
    };

    // Check if we have minimal data required for dashboard
    if (!marketResult.rows || marketResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No market data found",
        message: "No market overview data available in database",
      });
    }
    res.json({
      success: true,
      data: summary,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ Dashboard summary error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dashboard summary",
      message: "Database query failed",
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
      return res.status(401).json({
        success: false,
        error: "User authentication required",
        message: "Please provide valid authentication credentials",
      });
    }

    const holdingsQuery = `
            SELECT 
                ph.symbol,
                ph.quantity::numeric as shares,
                ph.average_cost::numeric as avg_price,
                ph.current_price::numeric,
                ph.market_value::numeric as total_value,
                ph.unrealized_pnl::numeric as gain_loss,
                ph.unrealized_pnl_percent::numeric as gain_loss_percent,
                'General' as sector,
                ph.symbol as company_name,
                ph.last_updated as created_at
            FROM portfolio_holdings ph
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

    // Process and convert data types properly
    const processedHoldings = holdingsResult.rows.map((holding) => ({
      ...holding,
      shares: parseFloat(holding.shares) || 0,
      avg_price: parseFloat(holding.avg_price) || 0,
      current_price: parseFloat(holding.current_price) || 0,
      total_value: parseFloat(holding.total_value) || 0,
      gain_loss: parseFloat(holding.gain_loss) || 0,
      gain_loss_percent: parseFloat(holding.gain_loss_percent) || 0,
    }));

    // Process summary data with proper type conversion
    const processedSummary = summaryResult.rows[0]
      ? {
          ...summaryResult.rows[0],
          total_positions: parseInt(summaryResult.rows[0].total_positions) || 0,
          total_portfolio_value:
            parseFloat(summaryResult.rows[0].total_portfolio_value) || 0,
          total_gain_loss:
            parseFloat(summaryResult.rows[0].total_gain_loss) || 0,
          avg_gain_loss_percent:
            parseFloat(summaryResult.rows[0].avg_gain_loss_percent) || 0,
          market_value: parseFloat(summaryResult.rows[0].market_value) || 0,
        }
      : null;

    // Handle cases where database query succeeded but returned no data
    if (!holdingsResult || !Array.isArray(holdingsResult.rows)) {
      return res.status(500).json({
        success: false,
        error: "Database query failed for holdings",
        message: "Failed to retrieve portfolio holdings data",
      });
    }
    if (!summaryResult || !Array.isArray(summaryResult.rows)) {
      return res.status(500).json({
        success: false,
        error: "Database query failed for summary",
        message: "Failed to retrieve portfolio summary data",
      });
    }
    res.json({
      success: true,
      data: {
        holdings: processedHoldings,
        summary: processedSummary,
        count: holdingsResult.rowCount,
      },
      timestamp: new Date().toISOString(),
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
      return res.unauthorized("User authentication required");
    }

    const performanceQuery = `
            SELECT
                date,
                total_value,
                daily_pnl_percent as daily_return,
                total_pnl_percent as cumulative_return,
                0 as benchmark_return,
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

    // Handle cases where database query succeeded but returned no data
    if (!performanceResult || !performanceResult.rows) {
      return res.status(500).json({
        success: false,
        error: "Database query failed for performance data",
        message: "Failed to retrieve performance data",
      });
    }

    if (!metricsResult || !metricsResult.rows) {
      return res.status(500).json({
        success: false,
        error: "Database query failed for performance metrics",
        message: "Failed to retrieve performance metrics",
      });
    }

    // Process and convert data types properly for performance data
    const performance = performanceResult.rows.map((row) => ({
      ...row,
      total_value: parseFloat(row.total_value) || 0,
      daily_return: parseFloat(row.daily_return) || 0,
      cumulative_return: parseFloat(row.cumulative_return) || 0,
      benchmark_return: parseFloat(row.benchmark_return) || 0,
      excess_return: parseFloat(row.excess_return) || 0,
    }));

    // Process metrics with proper type conversion
    const metrics = {
      ...metricsResult.rows[0],
      avg_daily_return: parseFloat(metricsResult.rows[0].avg_daily_return) || 0,
      volatility: parseFloat(metricsResult.rows[0].volatility) || 0,
      max_return: parseFloat(metricsResult.rows[0].max_return) || 0,
      min_return: parseFloat(metricsResult.rows[0].min_return) || 0,
      trading_days: parseInt(metricsResult.rows[0].trading_days) || 0,
    };

    res.json({
      success: true,
      data: {
        performance: performance,
        metrics: metrics,
        count: performance.length,
      },
      timestamp: new Date().toISOString(),
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
      return res.unauthorized("User authentication required");
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
      `✅ Alerts queries completed: ${alertsResult?.rowCount || 0} alerts found`
    );

    // Return empty data instead of 404 for better API consistency
    const alerts = alertsResult?.rows || [];
    const summaryRows = summaryResult?.rows || [];
    const summary = summaryRows.map((row) => ({
      ...row,
      count: parseInt(row.count),
      active_count: parseInt(row.active_count),
    }));

    res.json({
      success: true,
      data: {
        alerts: alerts,
        summary: summary,
        count: alerts.length,
      },
      timestamp: new Date().toISOString(),
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

    // Get economic indicators from database - check if table exists and has proper schema
    let economicResult = { rows: [] };
    try {
      const economicQuery = `
        SELECT 
          series_id as indicator_name,
          series_id,
          value,
          date,
          'units' as units,
          'daily' as frequency
        FROM economic_data 
        WHERE date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY date DESC
        LIMIT 10
      `;

      economicResult = await query(economicQuery);
    } catch (error) {
      console.error("❌ Economic data query failed:", error.message);
      return res.status(503).json({
        success: false,
        error: "Economic data unavailable",
        message: "Database query failed for economic indicators",
        details: error.message,
        timestamp: new Date().toISOString(),
      });
    }

    // Get sector rotation using price_daily table with yfinance structure
    const sectorRotationQuery = `
            SELECT 
                fm.sector,
                AVG(((pd.close - pd.open) / pd.open * 100)) as avg_change,
                COUNT(DISTINCT pd.symbol) as stock_count,
                AVG(pd.volume) as avg_volume,
                SUM(pd.volume * pd.close) as total_value
            FROM price_daily pd
            JOIN fundamental_metrics fm ON pd.symbol = fm.symbol
            WHERE fm.sector IS NOT NULL 
                AND pd.date >= CURRENT_DATE - INTERVAL '1 day'
                AND pd.close IS NOT NULL
                AND ((pd.close - pd.open) / pd.open * 100) IS NOT NULL
            GROUP BY fm.sector
            ORDER BY avg_change DESC
            LIMIT 20
        `;

    // Get market internals
    const internalsQuery = `
            SELECT 
                'advancing' as type,
                COUNT(*) as count
            FROM price_daily pd
            LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
                AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
            WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
                AND pd.close > prev.close
                AND pd.close IS NOT NULL 
                AND prev.close IS NOT NULL
            UNION ALL
            SELECT 
                'declining' as type,
                COUNT(*) as count
            FROM price_daily pd
            LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
                AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
            WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
                AND pd.close < prev.close
                AND pd.close IS NOT NULL 
                AND prev.close IS NOT NULL
            UNION ALL
            SELECT 
                'unchanged' as type,
                COUNT(*) as count
            FROM price_daily pd
            LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
                AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
            WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
                AND pd.close = prev.close
                AND pd.close IS NOT NULL 
                AND prev.close IS NOT NULL
        `;

    console.log("🔍 Executing market data queries...");
    const [sectorResult, internalsResult] = await Promise.all([
      query(sectorRotationQuery),
      query(internalsQuery),
    ]);

    console.log(
      `✅ Market data queries completed: ${economicResult.rowCount} econ, ${sectorResult.rowCount} sectors, ${internalsResult.rowCount} internals`
    );

    // Prepare data with graceful handling of missing components
    const econData = economicResult.rows || [];
    const sectorData = sectorResult.rows || [];
    const internalsData = internalsResult.rows || [];

    // Log data availability
    console.log(`📊 Market data prepared: ${econData.length} econ, ${sectorData.length} sectors, ${internalsData.length} internals`);

    // Convert count strings to numbers for market_internals
    const processedInternalsData = internalsData.map(item => ({
      ...item,
      count: parseInt(item.count) || 0
    }));

    // Convert numeric strings to numbers for sector rotation
    const processedSectorData = sectorData.map(item => ({
      ...item,
      stock_count: parseInt(item.stock_count) || 0,
      avg_change: parseFloat(item.avg_change) || 0,
      avg_volume: parseFloat(item.avg_volume) || 0,
      total_value: parseFloat(item.total_value) || 0
    }));

    res.json({
      success: true,
      data: {
        economic_indicators: econData,
        sector_rotation: processedSectorData,
        market_internals: processedInternalsData,
        data_status: {
          economic_available: econData.length > 0,
          sector_available: sectorData.length > 0,
          internals_available: internalsData.length > 0,
        },
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
 * GET /api/dashboard/overview
 * Get dashboard overview with market data
 */
router.get("/overview", async (req, res) => {
  try {
    console.log("📊 Dashboard overview requested");

    // Get key market indices
    const keyMetricsQuery = `
      SELECT 
        pd.symbol,
        pd.close as value,
        (pd.close - prev.close) as change,
        CASE 
          WHEN prev.close > 0 THEN ((pd.close - prev.close) / prev.close * 100)
          ELSE 0 
        END as change_percent
      FROM price_daily pd
      LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
          AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
      WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
        AND pd.symbol IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VTI')
        AND pd.close IS NOT NULL
        AND prev.close IS NOT NULL
      ORDER BY pd.symbol
    `;

    // Get top gainers and losers
    const moversQuery = `
      (SELECT 
        pd.symbol,
        pd.close as price,
        CASE 
          WHEN prev.close > 0 THEN ((pd.close - prev.close) / prev.close * 100)
          ELSE 0 
        END as change_percent,
        'gainer' as type
      FROM price_daily pd
      LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
          AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
      WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
        AND pd.close > prev.close 
        AND pd.close IS NOT NULL
        AND prev.close IS NOT NULL
      ORDER BY change_percent DESC
      LIMIT 3)
      UNION ALL
      (SELECT 
        pd.symbol,
        pd.close as price,
        CASE 
          WHEN prev.close > 0 THEN ((pd.close - prev.close) / prev.close * 100)
          ELSE 0 
        END as change_percent,
        'loser' as type
      FROM price_daily pd
      LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
          AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
      WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
        AND pd.close < prev.close 
        AND pd.close IS NOT NULL
        AND prev.close IS NOT NULL
      ORDER BY change_percent ASC
      LIMIT 3)
    `;

    // Get sector performance
    const sectorQuery = `
      SELECT 
        fm.sector,
        COUNT(*) as stock_count,
        AVG(CASE 
          WHEN prev.close > 0 THEN ((pd.close - prev.close) / prev.close * 100)
          ELSE 0 
        END) as change_percent
      FROM price_daily pd
      LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
          AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
      JOIN fundamental_metrics fm ON pd.symbol = fm.symbol
      WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
        AND fm.sector IS NOT NULL 
        AND pd.close IS NOT NULL
        AND prev.close IS NOT NULL
      GROUP BY fm.sector
      ORDER BY change_percent DESC
      LIMIT 5
    `;

    console.log("🔍 Executing overview queries...");
    const [keyMetricsResult, moversResult, sectorResult] = await Promise.all([
      query(keyMetricsQuery),
      query(moversQuery),
      query(sectorQuery),
    ]);

    // Prepare data with graceful handling of missing components
    const keyMetrics = keyMetricsResult?.rows || [];
    const movers = moversResult?.rows || [];
    const sectors = sectorResult?.rows || [];

    console.log(`📊 Overview data prepared: ${keyMetrics.length} key metrics, ${movers.length} movers, ${sectors.length} sectors`);

    // Process the results
    const keyMetricsObj = {};
    keyMetrics.forEach((row) => {
      keyMetricsObj[row.symbol.toLowerCase()] = {
        value: parseFloat(row.value) || 0,
        change: parseFloat(row.change) || 0,
        change_percent: parseFloat(row.change_percent) || 0,
      };
    });

    const gainers = movers.filter((row) => row.type === "gainer");
    const losers = movers.filter((row) => row.type === "loser");

    const overviewData = {
      market_status: {
        is_open: new Date().getHours() >= 9 && new Date().getHours() < 16,
        next_open: "2025-09-02T09:30:00Z",
        next_close: "2025-09-01T16:00:00Z",
        timezone: "EST",
      },
      key_metrics: keyMetricsObj,
      top_movers: {
        gainers: gainers.map((row) => ({
          symbol: row.symbol,
          price: parseFloat(row.price) || 0,
          change_percent: parseFloat(row.change_percent) || 0,
        })),
        losers: losers.map((row) => ({
          symbol: row.symbol,
          price: parseFloat(row.price) || 0,
          change_percent: parseFloat(row.change_percent) || 0,
        })),
      },
      sector_performance: sectors.map((row) => ({
        sector: row.sector,
        stock_count: parseInt(row.stock_count) || 0,
        change_percent: parseFloat(row.change_percent) || 0,
      })),
      alerts_summary: {
        total_active: 0,
        critical: 0,
        high: 0,
        medium: 0,
      },
    };

    res.json({
      success: true,
      data: overviewData,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Dashboard overview error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dashboard overview",
      message: error.message,
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

    // Get data counts only (no sample generation)
    try {
      const countsResult = await query(`
                SELECT
                    (SELECT COUNT(*) FROM price_daily) as price_count,
                    (SELECT COUNT(*) FROM fundamental_metrics) as profile_count,
                    (SELECT COUNT(*) FROM stock_symbols) as symbols_count,
                    (SELECT COUNT(*) FROM fundamental_metrics) as stocks_count
            `);
      debugData.data_counts = countsResult.rows[0];
    } catch (error) {
      debugData.data_counts = `error: ${error.message}`;
    }


    // Database connectivity check
    debugData.database_connectivity = "operational";

    console.log("🔧 Debug data collected:", debugData);

    // Return debug data even if some components are missing
    console.log("🔧 Debug data validation - table_counts type:", typeof debugData.table_counts);
    console.log("🔧 Debug data validation - data_counts type:", typeof debugData.data_counts);
    res.json({
      success: true,
      data: debugData,
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

// Dashboard analytics endpoint
router.get("/analytics", async (req, res) => {
  try {
    const {
      period = "30d",
      include_sectors = "true",
      include_performance = "true",
    } = req.query;

    console.log(
      `📊 Dashboard analytics requested - period: ${period}, sectors: ${include_sectors}, performance: ${include_performance}`
    );

    // Calculate date range
    const periodDays = {
      "7d": 7,
      "30d": 30,
      "90d": 90,
      "1y": 365,
    };
    const days = periodDays[period] || 30;

    // Get portfolio overview
    const portfolioResult = await query(`
      SELECT 
        COUNT(DISTINCT symbol) as total_positions,
        SUM(market_value) as total_value,
        SUM(gain_loss) as total_gain_loss,
        AVG(gain_loss_percent) as avg_gain_loss_percent
      FROM user_portfolio
    `);

    // Get recent trades summary
    const tradesResult = await query(`
      SELECT 
        COUNT(*) as total_trades,
        COUNT(CASE WHEN trade_type = 'BUY' THEN 1 END) as buy_trades,
        COUNT(CASE WHEN trade_type = 'SELL' THEN 1 END) as sell_trades,
        SUM(total_value) as total_volume,
        AVG(profit_loss) as avg_profit_loss
      FROM trades 
      WHERE date >= CURRENT_DATE - INTERVAL '${days} days'
    `);

    // Get watchlist stats
    const watchlistResult = await query(`
      SELECT 
        COUNT(*) as total_watchlist_items,
        COUNT(DISTINCT symbol) as unique_symbols
      FROM watchlist
    `);

    let sectorAnalysis = {};
    if (include_sectors === "true") {
      const sectorResult = await query(`
        SELECT 
          s.sector,
          COUNT(up.symbol) as positions,
          SUM(up.market_value) as total_value,
          AVG(up.gain_loss_percent) as avg_performance
        FROM user_portfolio up
        LEFT JOIN fundamental_metrics s ON up.symbol = s.symbol
        WHERE s.sector IS NOT NULL
        GROUP BY s.sector
        ORDER BY total_value DESC
        LIMIT 10
      `);

      sectorAnalysis = {
        sectors: (sectorResult.rows || []).map((row) => ({
          sector: row.sector,
          positions: parseInt(row.positions),
          total_value: parseFloat(row.total_value || 0),
          avg_performance:
            parseFloat(row.avg_performance || 0).toFixed(2) + "%",
        })),
        diversification_score:
          (sectorResult.rows || []).length >= 5 ? "Good" : "Needs Improvement",
      };
    }

    let performanceMetrics = {};
    if (include_performance === "true") {
      // Get price performance for major indices
      const performanceResult = await query(`
        SELECT 
          symbol,
          close,
          change_percent,
          date
        FROM price_daily 
        WHERE symbol IN ('SPY', 'QQQ', 'IWM')
          AND date = (SELECT MAX(date) FROM price_daily WHERE symbol IN ('SPY', 'QQQ', 'IWM'))
      `);

      performanceMetrics = {
        market_indices: (performanceResult.rows || []).map((row) => ({
          symbol: row.symbol,
          name: getIndexName(row.symbol),
          price: parseFloat(row.close),
          change_percent: parseFloat(row.change_percent).toFixed(2) + "%",
          date: row.date,
        })),
        market_sentiment: calculateMarketSentiment(
          performanceResult.rows || []
        ),
      };
    }

    // Calculate key metrics
    const portfolioData = portfolioResult.rows[0] || {};
    const tradesData = tradesResult.rows[0] || {};
    const watchlistData = watchlistResult.rows[0] || {};

    const dashboardAnalytics = {
      overview: {
        portfolio_value: parseFloat(portfolioData.total_value || 0).toFixed(2),
        total_positions: parseInt(portfolioData.total_positions || 0),
        total_gain_loss: parseFloat(portfolioData.total_gain_loss || 0).toFixed(
          2
        ),
        portfolio_performance:
          parseFloat(portfolioData.avg_gain_loss_percent || 0).toFixed(2) + "%",
        watchlist_size: parseInt(watchlistData.total_watchlist_items || 0),
      },

      trading_activity: {
        period: period,
        total_trades: parseInt(tradesData.total_trades || 0),
        buy_trades: parseInt(tradesData.buy_trades || 0),
        sell_trades: parseInt(tradesData.sell_trades || 0),
        total_volume: parseFloat(tradesData.total_volume || 0).toFixed(2),
        avg_profit_per_trade: parseFloat(
          tradesData.avg_profit_loss || 0
        ).toFixed(2),
        trade_frequency:
          parseInt(tradesData.total_trades || 0) > 0
            ? `${(parseInt(tradesData.total_trades) / days).toFixed(1)} trades/day`
            : "0 trades/day",
      },

      sector_analysis: sectorAnalysis,
      performance_metrics: performanceMetrics,

      insights: generateDashboardInsights(
        portfolioData,
        tradesData,
        sectorAnalysis
      ),

      last_updated: new Date().toISOString(),
    };

    res.json({
      success: true,
      data: dashboardAnalytics,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Dashboard analytics error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dashboard analytics",
      message: error.message,
    });
  }
});

// Helper functions for dashboard analytics
function getIndexName(symbol) {
  const indexMap = {
    SPY: "S&P 500",
    QQQ: "NASDAQ-100",
    IWM: "Russell 2000",
  };
  return indexMap[symbol] || symbol;
}

function calculateMarketSentiment(indices) {
  if (!indices || indices.length === 0) return "Neutral";

  const avgChange =
    indices.reduce((sum, idx) => sum + parseFloat(idx.change_percent || 0), 0) /
    indices.length;

  if (avgChange > 1) return "Bullish";
  if (avgChange > 0) return "Slightly Bullish";
  if (avgChange > -1) return "Slightly Bearish";
  return "Bearish";
}

function generateDashboardInsights(portfolio, trades, sectors) {
  const insights = [];

  // Portfolio insights
  const portfolioPerf = parseFloat(portfolio.avg_gain_loss_percent || 0);

  if (portfolioPerf > 5) {
    insights.push({
      type: "positive",
      message: `Strong portfolio performance with ${portfolioPerf.toFixed(1)}% average gains`,
    });
  } else if (portfolioPerf < -5) {
    insights.push({
      type: "warning",
      message: `Portfolio showing losses with ${portfolioPerf.toFixed(1)}% average performance`,
    });
  }

  // Trading insights
  const totalTrades = parseInt(trades.total_trades || 0);
  const avgProfit = parseFloat(trades.avg_profit_loss || 0);

  if (totalTrades > 0) {
    if (avgProfit > 0) {
      insights.push({
        type: "positive",
        message: `Profitable trading with average $${avgProfit.toFixed(2)} per trade`,
      });
    } else if (avgProfit < 0) {
      insights.push({
        type: "warning",
        message: `Trading showing losses averaging $${Math.abs(avgProfit).toFixed(2)} per trade`,
      });
    }
  }

  // Diversification insights
  if (sectors.sectors && sectors.sectors.length < 3) {
    insights.push({
      type: "suggestion",
      message:
        "Consider diversifying across more sectors for better risk management",
    });
  }

  return insights;
}

/**
 * GET /api/dashboard/metrics
 * Get key dashboard metrics
 */
router.get("/metrics", async (req, res) => {
  try {
    console.log("📊 Dashboard metrics request received");

    // Get market overview metrics (use close instead of current_price)
    const marketMetricsQuery = `
      SELECT
        COUNT(*) as total_symbols,
        SUM(volume::bigint) as total_volume,
        AVG(close::float) as avg_price,
        MAX(close::float) as max_price,
        MIN(close::float) as min_price
      FROM price_daily
      WHERE date = (SELECT MAX(date) FROM price_daily)
        AND close IS NOT NULL
        AND close > 0
    `;

    // Get portfolio metrics (simulated for development)
    const portfolioMetricsQuery = `
      SELECT
        COUNT(*) as total_holdings,
        SUM(market_value::float) as total_value,
        AVG(daily_return::float) as avg_return
      FROM portfolio_holdings
      LIMIT 1
    `;

    const [marketResult, portfolioResult] = await Promise.all([
      query(marketMetricsQuery),
      query(portfolioMetricsQuery).catch(() => ({ rows: [{}] })),
    ]);

    const marketMetrics = marketResult.rows[0] || {};
    const portfolioMetrics = portfolioResult.rows[0] || {};

    res.json({
      success: true,
      data: {
        market: {
          total_symbols: parseInt(marketMetrics.total_symbols) || 0,
          total_volume: parseInt(marketMetrics.total_volume) || 0,
          avg_price: parseFloat(marketMetrics.avg_price) || 0,
          max_price: parseFloat(marketMetrics.max_price) || 0,
          min_price: parseFloat(marketMetrics.min_price) || 0,
        },
        portfolio: {
          total_holdings: parseInt(portfolioMetrics.total_holdings) || 0,
          total_value: parseFloat(portfolioMetrics.total_value) || 0,
          avg_return: parseFloat(portfolioMetrics.avg_return) || 0,
        },
        system: {
          uptime: process.uptime(),
          memory_usage: process.memoryUsage(),
          timestamp: new Date().toISOString(),
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Dashboard metrics error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dashboard metrics",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * GET /api/dashboard/widgets
 * Dashboard widgets configuration endpoint
 */
router.get("/widgets", async (req, res) => {
  try {
    console.log("🧩 Dashboard widgets requested");

    const widgets = {
      available_widgets: [
        "portfolio_overview",
        "market_overview",
        "performance_chart",
        "watchlist",
        "recent_trades",
        "alerts",
        "news_feed",
        "sector_performance",
        "economic_calendar",
        "earnings_calendar",
        "heat_map",
      ],
      default_layout: {
        grid: [
          { widget: "portfolio_overview", position: { x: 0, y: 0, w: 6, h: 4 } },
          { widget: "market_overview", position: { x: 6, y: 0, w: 6, h: 4 } },
          { widget: "performance_chart", position: { x: 0, y: 4, w: 8, h: 6 } },
          { widget: "watchlist", position: { x: 8, y: 4, w: 4, h: 6 } },
          { widget: "recent_trades", position: { x: 0, y: 10, w: 6, h: 4 } },
          { widget: "alerts", position: { x: 6, y: 10, w: 6, h: 4 } },
        ],
      },
      widget_settings: {
        refresh_intervals: ["5s", "10s", "30s", "1m", "5m"],
        themes: ["light", "dark", "auto"],
        chart_types: ["line", "candlestick", "area", "bar"],
      },
    };

    res.json({
      success: true,
      data: widgets,
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error("Dashboard widgets error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dashboard widgets",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Dashboard watchlist endpoints
router.get("/watchlists", authenticateToken, async (req, res) => {
  try {
    const userId = req.user ? req.user.sub : 'dev-user-bypass';
    console.log(`📋 Dashboard watchlists requested for user: ${userId}`);

    // Get user's watchlists with summary data (defensive query for AWS compatibility)
    let watchlists = [];
    try {
      const watchlistsResult = await query(`
        SELECT
          w.id,
          w.name,
          w.description,
          false as is_public,
          w.created_at,
          COUNT(wi.symbol) as stock_count,
          ARRAY_AGG(wi.symbol ORDER BY wi.added_at DESC) FILTER (WHERE wi.symbol IS NOT NULL) as stocks
        FROM watchlists w
        LEFT JOIN watchlist_items wi ON w.id = wi.watchlist_id
        WHERE w.user_id = $1
        GROUP BY w.id, w.name, w.description, w.created_at
        ORDER BY w.created_at DESC
        LIMIT 10
      `, [userId]);

      watchlists = watchlistsResult.rows || [];
    } catch (error) {
      console.error("Watchlist query error:", error.message);

      console.error("Watchlist database error:", error.message);
      return res.status(500).json({
        success: false,
        error: "Watchlist data unavailable",
        message: "Database error occurred",
        details: process.env.NODE_ENV === "development" ? error.message : "Internal database error",
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      data: watchlists,
      total: watchlists.length,
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error("Dashboard watchlists error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dashboard watchlists",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Dashboard watchlist performance endpoint
router.get("/watchlists/performance", authenticateToken, async (req, res) => {
  try {
    const userId = req.user ? req.user.sub : 'dev-user-bypass';
    console.log(`📊 Dashboard watchlist performance requested for user: ${userId}`);

    // Get watchlist performance data
    const performanceResult = await query(`
      SELECT
        w.id as watchlist_id,
        w.name as watchlist_name,
        COUNT(wi.symbol) as stock_count,
        AVG(CASE WHEN pd.close IS NOT NULL THEN
          ((pd.close - pd.open) / pd.open * 100)
        END) as avg_daily_return,
        SUM(CASE WHEN pd.close > pd.open THEN 1 ELSE 0 END) as gainers,
        SUM(CASE WHEN pd.close < pd.open THEN 1 ELSE 0 END) as losers
      FROM watchlists w
      LEFT JOIN watchlist_items wi ON w.id = wi.watchlist_id
      LEFT JOIN price_daily pd ON wi.symbol = pd.symbol
        AND pd.date = (SELECT MAX(date) FROM price_daily WHERE symbol = wi.symbol)
      WHERE w.user_id = $1
      GROUP BY w.id, w.name
      ORDER BY avg_daily_return DESC NULLS LAST
    `, [userId]);

    const performance = performanceResult.rows || [];

    // If no performance data, return 404
    if (performance.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No performance data found",
        message: "No watchlist performance data available",
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      data: performance,
      summary: {
        total_watchlists: performance.length,
        avg_return: performance.reduce((sum, w) => sum + (parseFloat(w.avg_daily_return) || 0), 0) / performance.length,
        best_performer: performance[0]?.watchlist_name || "N/A",
        worst_performer: performance[performance.length - 1]?.watchlist_name || "N/A"
      },
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error("Dashboard watchlist performance error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch watchlist performance",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;

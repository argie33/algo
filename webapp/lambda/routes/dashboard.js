const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken, _optionalAuth } = require("../middleware/auth");

const router = express.Router();

// Health check endpoint
router.get("/health", (req, res) => {
  res
    .status(200)
    .json({
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

    // Get sector performance from company_profile table
    const sectorQuery = `
            SELECT 
                cp.sector,
                COUNT(*) as stock_count,
                AVG(CASE 
                    WHEN prev.close > 0 THEN ((pd.close - prev.close) / prev.close * 100)
                    ELSE 0 
                END) as avg_change,
                AVG(pd.volume) as avg_volume
            FROM price_daily pd
            LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
                AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
            JOIN company_profile cp ON pd.symbol = cp.ticker
            WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
                AND cp.sector IS NOT NULL 
                AND cp.sector != ''
                AND pd.close IS NOT NULL
                AND prev.close IS NOT NULL
                AND prev.close > 0
            GROUP BY cp.sector
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
      return rows.map(row => {
        const parsed = { ...row };
        numericFields.forEach(field => {
          if (parsed[field] !== null && parsed[field] !== undefined) {
            parsed[field] = parseFloat(parsed[field]);
          }
        });
        return parsed;
      });
    };

    const summary = {
      market_overview: parseNumericFields(marketResult.rows, ['current_price', 'change_percent', 'change_amount', 'volume']),
      top_gainers: parseNumericFields(gainersResult.rows, ['current_price', 'change_percent', 'change_amount', 'volume']),
      top_losers: parseNumericFields(losersResult.rows, ['current_price', 'change_percent', 'change_amount', 'volume']),
      sector_performance: parseNumericFields(sectorResult.rows, ['stock_count', 'avg_change', 'avg_volume']),
      recent_earnings: parseNumericFields(earningsResult.rows, ['eps_estimate', 'eps_actual', 'surprise_percent']),
      market_sentiment: sentimentResult.rows[0] ? {
        ...sentimentResult.rows[0],
        value: parseFloat(sentimentResult.rows[0].value)
      } : null,
      volume_leaders: parseNumericFields(volumeResult.rows, ['current_price', 'volume', 'change_percent', 'change_amount']),
      market_breadth: breadthResult.rows[0] ? {
        ...breadthResult.rows[0],
        advancing: parseInt(breadthResult.rows[0].advancing),
        declining: parseInt(breadthResult.rows[0].declining),
        unchanged: parseInt(breadthResult.rows[0].unchanged)
      } : null,
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

    if (
      !holdingsResult ||
      !Array.isArray(holdingsResult.rows) ||
      holdingsResult.rows.length === 0
    ) {
      return res.status(404).json({
        success: false,
        error: "No data found for holdings",
        message: "No portfolio holdings found for this user",
      });
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
      !performanceResult.rows ||
      performanceResult.rows.length === 0
    ) {
      return res.status(404).json({
        success: false,
        error: "No performance data found",
        message: "No performance data available for this user",
      });
    }

    if (
      !metricsResult ||
      !metricsResult.rows ||
      metricsResult.rows.length === 0
    ) {
      return res.status(404).json({
        success: false,
        error: "No performance metrics found",
        message: "No performance metrics available for this user",
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
      `✅ Alerts queries completed: ${alertsResult.rowCount} alerts found`
    );

    if (!alertsResult || !alertsResult.rows || alertsResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No alerts found",
        message: "No trading alerts available for this user",
      });
    }

    if (
      !summaryResult ||
      !summaryResult.rows ||
      summaryResult.rows.length === 0
    ) {
      return res.status(404).json({
        success: false,
        error: "No alert summary found",
        message: "No alert summary data available for this user",
      });
    }

    const alerts = alertsResult.rows;
    const summary = summaryResult.rows.map(row => ({
      ...row,
      count: parseInt(row.count),
      active_count: parseInt(row.active_count)
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
                cp.sector,
                AVG(pd.change_percent) as avg_change,
                COUNT(DISTINCT pd.symbol) as stock_count,
                AVG(pd.volume) as avg_volume,
                SUM(pd.volume * pd.close) as total_value
            FROM price_daily pd
            JOIN company_profile cp ON pd.symbol = cp.ticker
            WHERE cp.sector IS NOT NULL 
                AND pd.date >= CURRENT_DATE - INTERVAL '1 day'
                AND pd.close IS NOT NULL
                AND pd.change_percent IS NOT NULL
            GROUP BY cp.sector
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

    // Check if we have any data, return proper errors if not
    if (!economicResult.rows || economicResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No economic data found",
        message: "No economic indicators available in database",
        details: {
          table_checked: "economic_data",
          suggestion: "Load economic data from data providers",
          troubleshooting: [
            "1. Run economic data loader to populate economic_data table",
            "2. Verify economic_data table structure matches expected format",
            "3. Check data provider API connections",
          ],
        },
        timestamp: new Date().toISOString(),
      });
    }

    if (!sectorResult.rows || sectorResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No sector rotation data found",
        message: "No sector performance data available",
        details: {
          tables_checked: ["price_daily", "company_profile"],
          suggestion: "Ensure price data and company profiles are loaded",
          troubleshooting: [
            "1. Load price data using yfinance data loaders",
            "2. Populate company_profile table with sector information",
            "3. Verify price_daily has recent data with change_percent",
          ],
        },
        timestamp: new Date().toISOString(),
      });
    }

    const econData = economicResult.rows;
    const sectorData = sectorResult.rows;
    const internalsData = internalsResult.rows;

    res.json({
      success: true,
      data: {
        economic_indicators: econData,
        sector_rotation: sectorData,
        market_internals: internalsData,
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
        cp.sector,
        COUNT(*) as stock_count,
        AVG(CASE 
          WHEN prev.close > 0 THEN ((pd.close - prev.close) / prev.close * 100)
          ELSE 0 
        END) as change_percent
      FROM price_daily pd
      LEFT JOIN price_daily prev ON pd.symbol = prev.symbol 
          AND prev.date = (SELECT MAX(date) FROM price_daily p2 WHERE p2.symbol = pd.symbol AND p2.date < pd.date)
      JOIN company_profile cp ON pd.symbol = cp.symbol
      WHERE pd.date = (SELECT MAX(date) FROM price_daily p3 WHERE p3.symbol = pd.symbol)
        AND cp.sector IS NOT NULL 
        AND pd.close IS NOT NULL
        AND prev.close IS NOT NULL
      GROUP BY cp.sector
      ORDER BY change_percent DESC
      LIMIT 5
    `;

    console.log("🔍 Executing overview queries...");
    const [keyMetricsResult, moversResult, sectorResult] = await Promise.all([
      query(keyMetricsQuery),
      query(moversQuery),
      query(sectorQuery),
    ]);

    if (
      !keyMetricsResult ||
      !keyMetricsResult.rows ||
      keyMetricsResult.rows.length === 0
    ) {
      return res.status(404).json({
        success: false,
        error: "No key market metrics found",
        message: "No market data available for key indices",
        details: {
          attempted_symbols: ["SPY", "QQQ", "IWM", "DIA", "VTI"],
          rows_found: keyMetricsResult?.rows?.length || 0,
          table_status:
            "price_daily table exists but no data for required symbols",
        },
        troubleshooting: {
          required_tables: ["price_daily", "stock_symbols"],
          check_tables:
            "SELECT COUNT(*) FROM price_daily WHERE symbol IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VTI')",
          solution: "Ensure key market indices have data in price_daily table",
          data_requirements:
            "At least one of: SPY, QQQ, IWM, DIA, VTI with current and previous day prices",
        },
      });
    }

    if (!moversResult || !moversResult.rows || moversResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No market movers found",
        message: "No market mover data available",
      });
    }

    if (!sectorResult || !sectorResult.rows || sectorResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No sector performance found",
        message: "No sector performance data available",
      });
    }

    // Process the results
    const keyMetrics = {};
    keyMetricsResult.rows.forEach((row) => {
      keyMetrics[row.symbol.toLowerCase()] = {
        value: parseFloat(row.value) || 0,
        change: parseFloat(row.change) || 0,
        change_percent: parseFloat(row.change_percent) || 0,
      };
    });

    const gainers = moversResult.rows.filter((row) => row.type === "gainer");
    const losers = moversResult.rows.filter((row) => row.type === "loser");

    const overviewData = {
      market_status: {
        is_open: new Date().getHours() >= 9 && new Date().getHours() < 16,
        next_open: "2025-09-02T09:30:00Z",
        next_close: "2025-09-01T16:00:00Z",
        timezone: "EST",
      },
      key_metrics: keyMetrics,
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
      sector_performance: sectorResult.rows.map((row) => ({
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
                    (SELECT COUNT(*) FROM company_profile) as profile_count,
                    (SELECT COUNT(*) FROM stock_symbols) as symbols_count,
                    (SELECT COUNT(*) FROM stocks) as stocks_count
            `);
      debugData.data_counts = countsResult.rows[0];
    } catch (error) {
      debugData.data_counts = `error: ${error.message}`;
    }

    console.log("🔧 Debug data collected:", debugData);

    if (
      !debugData ||
      !Array.isArray(debugData.table_counts) ||
      Object.keys(debugData.table_counts).length === 0
    ) {
      return res.notFound("No table counts found");
    }
    if (
      !debugData ||
      !debugData.data_counts ||
      Object.keys(debugData.data_counts).length === 0
    ) {
      return res.status(503).json({
        success: false,
        error: "Database statistics unavailable",
        message: "Unable to retrieve database counts",
      });
    }
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
        LEFT JOIN stocks s ON up.symbol = s.symbol
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
          close_price,
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
          price: parseFloat(row.close_price),
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

module.exports = router;

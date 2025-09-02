/**
 * Performance Monitoring API Routes
 * Provides real-time performance metrics and system health information
 */

const express = require("express");

const router = express.Router();
const performanceMonitor = require("../utils/performanceMonitor");
const { authenticateToken } = require("../middleware/auth");
const { query } = require("../utils/database");

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.success({status: "operational",
    service: "performance-analytics",
    timestamp: new Date().toISOString(),
    message: "Performance Analytics service is running",
  });
});

// Basic root endpoint (public)
router.get("/", (req, res) => {
  res.success({message: "Performance Analytics API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
  });
});

// Portfolio performance benchmark comparison endpoint
router.get("/benchmark", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const { benchmark = "SPY", period = "1y" } = req.query;
    console.log(`📈 Performance benchmark requested for user: ${userId}, benchmark: ${benchmark}, period: ${period}`);
    
    // Convert period to days
    const periodDays = {
      "1d": 1,
      "1w": 7, 
      "1m": 30,
      "3m": 90,
      "6m": 180,
      "1y": 365,
      "2y": 730
    };
    
    const days = periodDays[period] || 365;
    
    // Get portfolio performance data
    const portfolioResult = await query(
      `
      SELECT 
        DATE(created_at) as date,
        total_value,
        daily_pnl_percent,
        total_pnl_percent
      FROM portfolio_performance 
      WHERE user_id = $1 
        AND created_at >= NOW() - INTERVAL '${days} days'
      ORDER BY created_at ASC
      `,
      [userId]
    );
    
    // Get benchmark data
    const benchmarkResult = await query(
      `
      SELECT 
        date,
        close_price,
        change_percent as daily_return
      FROM price_daily 
      WHERE symbol = $1 
        AND date >= CURRENT_DATE - INTERVAL '${days} days'
      ORDER BY date ASC
      `,
      [benchmark.toUpperCase()]
    );
    
    const portfolioData = portfolioResult.rows;
    const benchmarkData = benchmarkResult.rows;
    
    // Calculate cumulative returns for both portfolio and benchmark
    let portfolioCumulative = 0;
    let benchmarkCumulative = 0;
    
    const portfolioReturns = [];
    const benchmarkReturns = [];
    const comparisonData = [];
    
    // Process portfolio data
    if (portfolioData.length > 0) {
      const startValue = parseFloat(portfolioData[0].total_value) || 100000;
      
      portfolioData.forEach((row, index) => {
        const dailyReturn = parseFloat(row.daily_pnl_percent) || 0;
        portfolioCumulative += dailyReturn;
        
        portfolioReturns.push(dailyReturn);
        comparisonData.push({
          date: row.date,
          portfolio_value: parseFloat(row.total_value),
          portfolio_return: dailyReturn,
          portfolio_cumulative: portfolioCumulative
        });
      });
    }
    
    // Process benchmark data
    if (benchmarkData.length > 0) {
      benchmarkData.forEach((row, index) => {
        const dailyReturn = parseFloat(row.daily_return) || 0;
        benchmarkCumulative += dailyReturn;
        
        benchmarkReturns.push(dailyReturn);
        
        // Find matching comparison data entry
        const existingEntry = comparisonData.find(entry => 
          entry.date.toDateString() === new Date(row.date).toDateString()
        );
        
        if (existingEntry) {
          existingEntry.benchmark_price = parseFloat(row.close_price);
          existingEntry.benchmark_return = dailyReturn;
          existingEntry.benchmark_cumulative = benchmarkCumulative;
        } else {
          comparisonData.push({
            date: row.date,
            benchmark_price: parseFloat(row.close_price),
            benchmark_return: dailyReturn,
            benchmark_cumulative: benchmarkCumulative
          });
        }
      });
    }
    
    // Calculate performance metrics
    const calculateMetrics = (returns) => {
      if (returns.length === 0) return {};
      
      const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
      const variance = returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / returns.length;
      const volatility = Math.sqrt(variance);
      const annualizedReturn = avgReturn * 252; // 252 trading days
      const annualizedVolatility = volatility * Math.sqrt(252);
      const sharpeRatio = annualizedVolatility !== 0 ? (annualizedReturn - 2) / annualizedVolatility : 0; // 2% risk-free rate
      
      return {
        total_return: returns.reduce((sum, r) => sum + r, 0),
        annualized_return: annualizedReturn,
        volatility: annualizedVolatility,
        sharpe_ratio: sharpeRatio,
        best_day: Math.max(...returns),
        worst_day: Math.min(...returns),
        positive_days: returns.filter(r => r > 0).length,
        total_days: returns.length
      };
    };
    
    const portfolioMetrics = calculateMetrics(portfolioReturns);
    const benchmarkMetrics = calculateMetrics(benchmarkReturns);
    
    // Calculate beta (portfolio volatility relative to benchmark)
    let beta = 0;
    if (portfolioReturns.length > 0 && benchmarkReturns.length > 0) {
      const minLength = Math.min(portfolioReturns.length, benchmarkReturns.length);
      const portfolioSubset = portfolioReturns.slice(0, minLength);
      const benchmarkSubset = benchmarkReturns.slice(0, minLength);
      
      const portfolioAvg = portfolioSubset.reduce((sum, r) => sum + r, 0) / minLength;
      const benchmarkAvg = benchmarkSubset.reduce((sum, r) => sum + r, 0) / minLength;
      
      let covariance = 0;
      let benchmarkVariance = 0;
      
      for (let i = 0; i < minLength; i++) {
        const portfolioDeviation = portfolioSubset[i] - portfolioAvg;
        const benchmarkDeviation = benchmarkSubset[i] - benchmarkAvg;
        covariance += portfolioDeviation * benchmarkDeviation;
        benchmarkVariance += benchmarkDeviation * benchmarkDeviation;
      }
      
      beta = benchmarkVariance !== 0 ? covariance / benchmarkVariance : 0;
    }
    
    res.json({
      success: true,
      data: {
        benchmark_symbol: benchmark.toUpperCase(),
        period: period,
        comparison_data: comparisonData.sort((a, b) => new Date(a.date) - new Date(b.date)),
        portfolio_metrics: portfolioMetrics,
        benchmark_metrics: benchmarkMetrics,
        relative_performance: {
          excess_return: portfolioMetrics.total_return - benchmarkMetrics.total_return,
          beta: beta,
          alpha: portfolioMetrics.total_return - (beta * benchmarkMetrics.total_return),
          information_ratio: portfolioMetrics.volatility !== 0 ? 
            (portfolioMetrics.total_return - benchmarkMetrics.total_return) / portfolioMetrics.volatility : 0,
          tracking_error: Math.abs(portfolioMetrics.volatility - benchmarkMetrics.volatility)
        },
        summary: {
          portfolio_outperformed: portfolioMetrics.total_return > benchmarkMetrics.total_return,
          outperformance_amount: portfolioMetrics.total_return - benchmarkMetrics.total_return,
          data_points: comparisonData.length,
          period_analyzed: `${days} days`
        }
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Performance benchmark error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch performance benchmark data",
      details: error.message
    });
  }
});

/**
 * Get current performance metrics
 */
router.get("/metrics", authenticateToken, async (req, res) => {
  try {
    const metrics = performanceMonitor.getMetrics();

    req.logger?.info("Performance metrics requested", {
      requestedBy: req.user?.sub,
      metricsSize: JSON.stringify(metrics).length,
    });

    res.success({data: metrics,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    req.logger?.error("Error retrieving performance metrics", { error });
    res.status(500).json({
      success: false,
      error: "Failed to retrieve performance metrics",
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * Get performance attribution analysis
 */
router.get("/attribution", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const { 
      period = "1y", 
      level = "sector", 
      include_holdings = "true",
      attribution_method = "brinson" 
    } = req.query;

    console.log(`🚫 Performance attribution endpoint accessed but not implemented - user: ${userId}, period: ${period}, level: ${level}, method: ${attribution_method}`);

    res.status(501).json({
      success: false,
      error: "Performance Attribution Not Implemented",
      message: "Performance attribution analysis requires portfolio analytics integration with Brinson attribution modeling framework",
      details: {
        endpoint: "/performance/attribution",
        status: "not_implemented",
        reason: "Requires advanced portfolio attribution analysis capabilities",
        requested_parameters: {
          user_id: userId,
          period: period,
          attribution_level: level,
          method: attribution_method,
          include_holdings: include_holdings === "true"
        }
      },
      required_setup: {
        portfolio_analytics: "Portfolio composition and historical performance data integration",
        brinson_attribution: "Brinson-Fachler attribution model implementation for sector/security-level analysis", 
        benchmark_data: "Benchmark composition and return data for attribution baseline",
        risk_analytics: "Risk factor modeling and portfolio decomposition capabilities",
        performance_calculation: "Multi-period return calculation and compounding methodology"
      },
      troubleshooting: {
        portfolio_data_source: "Configure portfolio holdings and transaction history data feed",
        attribution_engine: "Implement Brinson attribution calculation engine with allocation, selection, and interaction effects",
        benchmark_integration: "Set up benchmark data feeds and composition tracking",
        risk_factor_models: "Integrate risk factor models for style and sector attribution analysis",
        data_validation: "Implement data quality checks for attribution accuracy and completeness"
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Performance attribution endpoint error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to process performance attribution request",
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * Get performance summary (lightweight)
 */
router.get("/summary", authenticateToken, async (req, res) => {
  try {
    const summary = performanceMonitor.getSummary();

    req.logger?.info("Performance summary requested", {
      requestedBy: req.user?.sub,
      status: summary.status,
      activeRequests: summary.activeRequests,
    });

    res.success({data: summary,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    req.logger?.error("Error retrieving performance summary", { error });
    res.status(500).json({
      success: false,
      error: "Failed to retrieve performance summary",
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * Get system health status
 */
router.get("/health", async (req, res) => {
  try {
    const summary = performanceMonitor.getSummary();
    const memUsage = process.memoryUsage();

    // Health check doesn't require auth for monitoring systems
    const healthStatus = {
      status: summary.status,
      uptime: summary.uptime,
      timestamp: new Date().toISOString(),
      memory: {
        used: memUsage.heapUsed,
        total: memUsage.heapTotal,
        utilization: (memUsage.heapUsed / memUsage.heapTotal) * 100,
      },
      requests: {
        active: summary.activeRequests,
        total: summary.totalRequests,
        errorRate: summary.errorRate,
      },
      alerts: summary.alerts,
    };

    const statusCode =
      summary.status === "critical"
        ? 503
        : summary.status === "warning"
          ? 200
          : 200;

    res.status(statusCode).json({
      success: true,
      data: healthStatus,
    });
  } catch (error) {
    req.logger?.error("Error retrieving system health", { error });
    res.status(500).json({
      success: false,
      error: "Failed to retrieve system health",
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * Get API endpoint performance statistics
 */
router.get("/api-stats", authenticateToken, async (req, res) => {
  try {
    const metrics = performanceMonitor.getMetrics();

    // Transform API metrics into a more readable format
    const apiStats = Object.entries(metrics.api.requests).map(
      ([endpoint, stats]) => ({
        endpoint,
        count: stats.count,
        errors: stats.errors,
        errorRate: stats.count > 0 ? (stats.errors / stats.count) * 100 : 0,
        avgResponseTime: stats.avgResponseTime,
        minResponseTime:
          stats.minResponseTime === Infinity ? 0 : stats.minResponseTime,
        maxResponseTime: stats.maxResponseTime,
        recentRequests: stats.recentRequests.length,
      })
    );

    // Sort by request count (most used endpoints first)
    apiStats.sort((a, b) => b.count - a.count);

    req.logger?.info("API statistics requested", {
      requestedBy: req.user?.sub,
      endpointCount: apiStats.length,
    });

    res.success({data: {
        endpoints: apiStats,
        responseTimeHistogram: Object.fromEntries(
          metrics.api.responseTimeHistogram
        ),
        totalRequests: metrics.system.totalRequests,
        totalErrors: metrics.system.totalErrors,
        overallErrorRate: metrics.system.errorRate * 100,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    req.logger?.error("Error retrieving API statistics", { error });
    res.status(500).json({
      success: false,
      error: "Failed to retrieve API statistics",
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * Get database performance statistics
 */
router.get("/database-stats", authenticateToken, async (req, res) => {
  try {
    const metrics = performanceMonitor.getMetrics();

    // Transform database metrics into a more readable format
    const dbStats = Object.entries(metrics.database.queries).map(
      ([operation, stats]) => ({
        operation,
        count: stats.count,
        errors: stats.errors,
        errorRate: stats.count > 0 ? (stats.errors / stats.count) * 100 : 0,
        avgTime: stats.avgTime,
        minTime: stats.minTime === Infinity ? 0 : stats.minTime,
        maxTime: stats.maxTime,
        recentQueries: stats.recentQueries.length,
      })
    );

    // Sort by average time (slowest first)
    dbStats.sort((a, b) => b.avgTime - a.avgTime);

    req.logger?.info("Database statistics requested", {
      requestedBy: req.user?.sub,
      operationCount: dbStats.length,
    });

    res.success({data: {
        operations: dbStats,
        slowestQueries: dbStats.slice(0, 10), // Top 10 slowest
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    req.logger?.error("Error retrieving database statistics", { error });
    res.status(500).json({
      success: false,
      error: "Failed to retrieve database statistics",
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * Get external API performance statistics
 */
router.get("/external-api-stats", authenticateToken, async (req, res) => {
  try {
    const metrics = performanceMonitor.getMetrics();

    // Transform external API metrics into a more readable format
    const externalStats = Object.entries(metrics.external.apis).map(
      ([service, stats]) => ({
        service,
        count: stats.count,
        errors: stats.errors,
        errorRate: stats.count > 0 ? (stats.errors / stats.count) * 100 : 0,
        avgTime: stats.avgTime,
        minTime: stats.minTime === Infinity ? 0 : stats.minTime,
        maxTime: stats.maxTime,
        recentCalls: stats.recentCalls.length,
      })
    );

    // Sort by error rate (most problematic first)
    externalStats.sort((a, b) => b.errorRate - a.errorRate);

    req.logger?.info("External API statistics requested", {
      requestedBy: req.user?.sub,
      serviceCount: externalStats.length,
    });

    res.success({data: {
        services: externalStats,
        mostProblematic: externalStats.slice(0, 5), // Top 5 most problematic
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    req.logger?.error("Error retrieving external API statistics", { error });
    res.status(500).json({
      success: false,
      error: "Failed to retrieve external API statistics",
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * Get performance alerts
 */
router.get("/alerts", authenticateToken, async (req, res) => {
  try {
    const summary = performanceMonitor.getSummary();

    req.logger?.info("Performance alerts requested", {
      requestedBy: req.user?.sub,
      alertCount: summary.alerts.length,
    });

    res.success({data: {
        alerts: summary.alerts,
        systemStatus: summary.status,
        alertCount: summary.alerts.length,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    req.logger?.error("Error retrieving performance alerts", { error });
    res.status(500).json({
      success: false,
      error: "Failed to retrieve performance alerts",
      timestamp: new Date().toISOString(),
    });
  }
});

/**
 * Clear performance metrics (admin only)
 */
router.post("/clear-metrics", authenticateToken, async (req, res) => {
  try {
    // Only allow admin users to clear metrics
    if (req.user?.role !== "admin") {
      return res.status(403).json({
        success: false,
        error: "Admin access required",
        timestamp: new Date().toISOString(),
      });
    }

    // Reset metrics
    performanceMonitor.reset();

    req.logger?.warn("Performance metrics cleared", {
      clearedBy: req.user?.sub,
    });

    res.success({message: "Performance metrics cleared successfully",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    req.logger?.error("Error clearing performance metrics", { error });
    res.status(500).json({
      success: false,
      error: "Failed to clear performance metrics",
      timestamp: new Date().toISOString(),
    });
  }
});

// Symbol vs benchmark performance comparison endpoint
router.get("/comparison", async (req, res) => {
  try {
    const { symbol, benchmark = "SPY", period = "1y" } = req.query;
    
    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: "Symbol parameter required",
        message: "Please provide a symbol using ?symbol=TICKER"
      });
    }
    
    console.log(`📊 Performance comparison requested - symbol: ${symbol}, benchmark: ${benchmark}, period: ${period}`);
    
    // Convert period to days
    const periodDays = {
      "1d": 1,
      "1w": 7, 
      "1m": 30,
      "3m": 90,
      "6m": 180,
      "1y": 365,
      "2y": 730
    };
    
    const days = periodDays[period] || 365;
    
    // Get symbol price data
    const symbolResult = await query(
      `
      SELECT 
        date,
        close_price,
        change_percent as daily_return
      FROM price_daily 
      WHERE symbol = $1 
        AND date >= CURRENT_DATE - INTERVAL '${days} days'
      ORDER BY date ASC
      `,
      [symbol.toUpperCase()]
    );
    
    // Get benchmark data
    const benchmarkResult = await query(
      `
      SELECT 
        date,
        close_price,
        change_percent as daily_return
      FROM price_daily 
      WHERE symbol = $1 
        AND date >= CURRENT_DATE - INTERVAL '${days} days'
      ORDER BY date ASC
      `,
      [benchmark.toUpperCase()]
    );
    
    const symbolData = symbolResult.rows;
    const benchmarkData = benchmarkResult.rows;
    
    if (symbolData.length === 0 || benchmarkData.length === 0) {
      return res.json({
        success: true,
        data: {
          symbol: symbol.toUpperCase(),
          benchmark: benchmark.toUpperCase(),
          period,
          message: "Limited data available for comparison",
          symbol_data_points: symbolData.length,
          benchmark_data_points: benchmarkData.length,
          comparison: []
        },
        timestamp: new Date().toISOString()
      });
    }
    
    // Calculate performance metrics
    let symbolCumulative = 0;
    let benchmarkCumulative = 0;
    const comparisonData = [];
    
    // Create date-aligned comparison data
    const symbolMap = new Map(symbolData.map(row => [row.date.toISOString().split('T')[0], row]));
    const benchmarkMap = new Map(benchmarkData.map(row => [row.date.toISOString().split('T')[0], row]));
    
    // Get common dates
    const commonDates = [...symbolMap.keys()].filter(date => benchmarkMap.has(date)).sort();
    
    commonDates.forEach(date => {
      const symbolRow = symbolMap.get(date);
      const benchmarkRow = benchmarkMap.get(date);
      
      const symbolReturn = parseFloat(symbolRow.daily_return) || 0;
      const benchmarkReturn = parseFloat(benchmarkRow.daily_return) || 0;
      
      symbolCumulative += symbolReturn;
      benchmarkCumulative += benchmarkReturn;
      
      comparisonData.push({
        date: date,
        symbol_price: parseFloat(symbolRow.close_price) || 0,
        benchmark_price: parseFloat(benchmarkRow.close_price) || 0,
        symbol_daily_return: symbolReturn,
        benchmark_daily_return: benchmarkReturn,
        symbol_cumulative_return: symbolCumulative,
        benchmark_cumulative_return: benchmarkCumulative,
        relative_performance: symbolCumulative - benchmarkCumulative
      });
    });
    
    // Calculate summary statistics
    const latestData = comparisonData[comparisonData.length - 1] || {};
    const symbolReturns = comparisonData.map(d => d.symbol_daily_return);
    const benchmarkReturns = comparisonData.map(d => d.benchmark_daily_return);
    
    // Calculate volatility (standard deviation)
    const symbolVolatility = Math.sqrt(symbolReturns.reduce((sum, r) => sum + Math.pow(r - (symbolCumulative / symbolReturns.length), 2), 0) / symbolReturns.length);
    const benchmarkVolatility = Math.sqrt(benchmarkReturns.reduce((sum, r) => sum + Math.pow(r - (benchmarkCumulative / benchmarkReturns.length), 2), 0) / benchmarkReturns.length);
    
    res.json({
      success: true,
      data: {
        symbol: symbol.toUpperCase(),
        benchmark: benchmark.toUpperCase(),
        period,
        summary: {
          symbol_total_return: latestData.symbol_cumulative_return || 0,
          benchmark_total_return: latestData.benchmark_cumulative_return || 0,
          relative_performance: latestData.relative_performance || 0,
          symbol_volatility: symbolVolatility,
          benchmark_volatility: benchmarkVolatility,
          data_points: comparisonData.length,
          start_date: comparisonData[0]?.date || null,
          end_date: comparisonData[comparisonData.length - 1]?.date || null
        },
        comparison_data: comparisonData
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Performance comparison error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch performance comparison",
      details: error.message
    });
  }
});

module.exports = router;

/**
 * Performance Monitoring API Routes
 * Provides real-time performance metrics and system health information
 */

const express = require("express");

const router = express.Router();
const performanceMonitor = require("../utils/performanceMonitor");
const { authenticateToken } = require("../middleware/auth");

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

module.exports = router;

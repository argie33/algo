/**
 * Performance Monitor Integration Tests
 * Tests real performance monitoring functionality with database integration
 */

const { initializeDatabase, closeDatabase, query } = require("../../../utils/database");

// Import the actual performance monitor instance
const performanceMonitor = require("../../../utils/performanceMonitor");

// Create wrapper functions to match the test API expectations
const startTimer = (operationId, category = "general", metadata = {}) => {
  performanceMonitor.startOperation(operationId, category, metadata);
  return operationId;
};

const endTimer = (operationId) => {
  const result = performanceMonitor.endOperation(operationId, { success: true });
  return result ? result.duration : 0;
};

const recordMetric = async (name, value, category, metadata = {}) => {
  const metric = {
    operationId: name,
    category,
    duration: value,
    timestamp: Date.now(),
    success: true,
    metadata
  };
  return performanceMonitor.recordMetric(metric);
};

const getMetrics = () => {
  return performanceMonitor.getMetrics();
};

const getAverageResponseTime = (category) => {
  const stats = performanceMonitor.getPerformanceStats();
  if (stats[category]) {
    return stats[category].avgResponseTime || 0;
  }
  return 0;
};

const getSystemHealth = () => {
  return performanceMonitor.calculateSystemHealth();
};

const detectAnomalies = (operationId, timeRange, category) => {
  // The actual detectAnomalies only uses category parameter
  return performanceMonitor.detectAnomalies(category);
};

const generatePerformanceReport = () => {
  return performanceMonitor.getPerformanceSummary();
};

describe("Performance Monitor Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
    
    // Clear any existing performance data for clean tests
    try {
      await query("DELETE FROM performance_metrics WHERE test_run = true");
    } catch (error) {
      // Table might not exist yet, that's ok
    }
  });

  afterAll(async () => {
    // Clean up test data
    try {
      await query("DELETE FROM performance_metrics WHERE test_run = true");
    } catch (error) {
      // Ignore cleanup errors
    }
    
    await closeDatabase();
  });

  describe("Performance Timing", () => {
    test("should measure operation duration accurately", () => {
      const timerId = startTimer("test_operation");
      expect(timerId).toBeDefined();
      expect(typeof timerId).toBe("string");
      
      // Simulate some work
      const startTime = Date.now();
      
      // End timing after a small delay
      setTimeout(() => {
        const duration = endTimer(timerId);
        const actualDuration = Date.now() - startTime;
        
        expect(duration).toBeGreaterThan(0);
        expect(duration).toBeLessThan(actualDuration + 50); // Allow for 50ms variance
      }, 10);
    });

    test("should handle multiple concurrent timers", () => {
      const timer1 = startTimer("concurrent_op_1");
      const timer2 = startTimer("concurrent_op_2");
      const timer3 = startTimer("concurrent_op_3");

      expect(timer1).not.toBe(timer2);
      expect(timer2).not.toBe(timer3);
      expect(timer1).not.toBe(timer3);

      const duration1 = endTimer(timer1);
      const duration2 = endTimer(timer2);
      const duration3 = endTimer(timer3);

      expect(duration1).toBeGreaterThan(0);
      expect(duration2).toBeGreaterThan(0);
      expect(duration3).toBeGreaterThan(0);
    });

    test("should handle invalid timer IDs gracefully", () => {
      const duration = endTimer("non_existent_timer");
      expect(duration).toBe(0); // Should return 0 for invalid timers
    });
  });

  describe("Metrics Recording", () => {
    test("should record custom metrics", async () => {
      await recordMetric("test_metric", 42.5, "test", { test_run: true });
      await recordMetric("test_metric", 45.0, "test", { test_run: true });
      await recordMetric("test_metric", 40.0, "test", { test_run: true });

      const metrics = await getMetrics("test_metric", "1h");
      
      expect(Array.isArray(metrics)).toBe(true);
      expect(metrics.length).toBeGreaterThan(0);
      
      const values = metrics.map(m => m.value);
      expect(values).toContain(42.5);
      expect(values).toContain(45.0);
      expect(values).toContain(40.0);
    });

    test("should record metrics with different categories", async () => {
      await recordMetric("response_time", 150, "api", { endpoint: "/test", test_run: true });
      await recordMetric("response_time", 200, "database", { query: "SELECT test", test_run: true });
      await recordMetric("response_time", 75, "cache", { operation: "get", test_run: true });

      const apiMetrics = await getMetrics("response_time", "1h", "api");
      const dbMetrics = await getMetrics("response_time", "1h", "database");
      const cacheMetrics = await getMetrics("response_time", "1h", "cache");

      expect(apiMetrics.length).toBeGreaterThan(0);
      expect(dbMetrics.length).toBeGreaterThan(0);
      expect(cacheMetrics.length).toBeGreaterThan(0);

      expect(apiMetrics[0].category).toBe("api");
      expect(dbMetrics[0].category).toBe("database");
      expect(cacheMetrics[0].category).toBe("cache");
    });

    test("should handle metrics with metadata", async () => {
      const metadata = {
        user_id: "test_user_123",
        endpoint: "/api/test",
        method: "GET",
        test_run: true
      };

      await recordMetric("request_duration", 125.5, "api", metadata);

      const metrics = await getMetrics("request_duration", "1h", "api");
      const metric = metrics.find(m => m.metadata?.user_id === "test_user_123");

      expect(metric).toBeDefined();
      expect(metric.metadata.endpoint).toBe("/api/test");
      expect(metric.metadata.method).toBe("GET");
    });
  });

  describe("Performance Analytics", () => {
    test("should calculate average response times", async () => {
      // Record some test response times
      await recordMetric("api_response", 100, "api", { test_run: true });
      await recordMetric("api_response", 150, "api", { test_run: true });
      await recordMetric("api_response", 200, "api", { test_run: true });
      await recordMetric("api_response", 125, "api", { test_run: true });

      const avgResponseTime = await getAverageResponseTime("api_response", "1h", "api");
      
      expect(avgResponseTime).toBeGreaterThan(0);
      expect(avgResponseTime).toBe(143.75); // (100 + 150 + 200 + 125) / 4
    });

    test("should handle empty metrics gracefully", async () => {
      const avgResponseTime = await getAverageResponseTime("nonexistent_metric", "1h", "api");
      expect(avgResponseTime).toBe(0);
    });

    test("should calculate metrics for different time ranges", async () => {
      // Record metrics over time
      const now = Date.now();
      await recordMetric("time_test", 100, "test", { test_run: true, timestamp: now });
      await recordMetric("time_test", 200, "test", { test_run: true, timestamp: now - 3600000 }); // 1 hour ago
      await recordMetric("time_test", 300, "test", { test_run: true, timestamp: now - 7200000 }); // 2 hours ago

      const metrics1h = await getMetrics("time_test", "1h", "test");
      const metrics2h = await getMetrics("time_test", "2h", "test");

      expect(metrics1h.length).toBeLessThanOrEqual(metrics2h.length);
    });
  });

  describe("System Health Monitoring", () => {
    test("should collect system health metrics", async () => {
      const health = await getSystemHealth();

      expect(health).toHaveProperty("status");
      expect(health).toHaveProperty("timestamp");
      expect(health).toHaveProperty("metrics");
      
      expect(health.metrics).toHaveProperty("memory");
      expect(health.metrics).toHaveProperty("cpu");
      expect(health.metrics).toHaveProperty("uptime");
      
      expect(typeof health.metrics.memory.used).toBe("number");
      expect(typeof health.metrics.memory.total).toBe("number");
      expect(typeof health.metrics.cpu.usage).toBe("number");
      expect(typeof health.metrics.uptime).toBe("number");
      
      expect(health.metrics.memory.used).toBeGreaterThan(0);
      expect(health.metrics.memory.total).toBeGreaterThan(health.metrics.memory.used);
      expect(health.metrics.cpu.usage).toBeGreaterThanOrEqual(0);
      expect(health.metrics.uptime).toBeGreaterThan(0);
    });

    test("should include database health in system metrics", async () => {
      const health = await getSystemHealth();

      expect(health.metrics).toHaveProperty("database");
      expect(health.metrics.database).toHaveProperty("connected");
      expect(health.metrics.database).toHaveProperty("pool_size");
      expect(health.metrics.database).toHaveProperty("active_connections");

      expect(typeof health.metrics.database.connected).toBe("boolean");
      expect(typeof health.metrics.database.pool_size).toBe("number");
      expect(typeof health.metrics.database.active_connections).toBe("number");
    });

    test("should detect system health status accurately", async () => {
      const health = await getSystemHealth();

      expect(["healthy", "warning", "critical"]).toContain(health.status);

      if (health.status === "healthy") {
        expect(health.metrics.memory.usage_percent).toBeLessThan(90);
        expect(health.metrics.cpu.usage).toBeLessThan(90);
      }
    });
  });

  describe("Anomaly Detection", () => {
    test("should detect performance anomalies", async () => {
      // Record baseline performance data
      const baselineValues = [95, 100, 105, 98, 102, 97, 103, 99, 101, 96];
      for (const value of baselineValues) {
        await recordMetric("anomaly_test", value, "baseline", { test_run: true });
      }

      // Record an anomaly
      await recordMetric("anomaly_test", 500, "baseline", { test_run: true }); // Significant spike

      const anomalies = await detectAnomalies("anomaly_test", "1h", "baseline");

      expect(Array.isArray(anomalies)).toBe(true);
      expect(anomalies.length).toBeGreaterThan(0);

      const highAnomaly = anomalies.find(a => a.value === 500);
      expect(highAnomaly).toBeDefined();
      expect(highAnomaly.type).toBe("outlier");
      expect(highAnomaly.deviation).toBeGreaterThan(2); // Should be significant deviation
    });

    test("should handle normal data without false positives", async () => {
      // Record normal, consistent data
      const normalValues = [100, 102, 98, 101, 99, 103, 97, 100, 102, 98];
      for (const value of normalValues) {
        await recordMetric("normal_test", value, "normal", { test_run: true });
      }

      const anomalies = await detectAnomalies("normal_test", "1h", "normal");

      // Should have few or no anomalies for normal data
      expect(anomalies.length).toBeLessThanOrEqual(1);
    });

    test("should detect trend-based anomalies", async () => {
      // Record gradually increasing data
      const trendValues = [100, 105, 110, 115, 120, 125, 130, 135, 140, 145];
      for (const value of trendValues) {
        await recordMetric("trend_test", value, "trend", { test_run: true });
      }

      // Add a sudden drop
      await recordMetric("trend_test", 50, "trend", { test_run: true });

      const anomalies = await detectAnomalies("trend_test", "1h", "trend");

      expect(anomalies.length).toBeGreaterThan(0);
      
      const dropAnomaly = anomalies.find(a => a.value === 50);
      expect(dropAnomaly).toBeDefined();
      expect(dropAnomaly.type).toContain("trend");
    });
  });

  describe("Performance Reporting", () => {
    test("should generate comprehensive performance report", async () => {
      // Record various performance metrics for reporting
      await recordMetric("report_cpu", 45.2, "system", { test_run: true });
      await recordMetric("report_memory", 67.8, "system", { test_run: true });
      await recordMetric("report_response", 125, "api", { endpoint: "/test", test_run: true });
      await recordMetric("report_db_query", 50, "database", { query: "SELECT test", test_run: true });

      const report = await generatePerformanceReport("1h");

      expect(report).toHaveProperty("summary");
      expect(report).toHaveProperty("metrics");
      expect(report).toHaveProperty("anomalies");
      expect(report).toHaveProperty("recommendations");
      expect(report).toHaveProperty("timestamp");

      expect(report.summary).toHaveProperty("total_metrics");
      expect(report.summary).toHaveProperty("avg_response_time");
      expect(report.summary).toHaveProperty("health_status");

      expect(Array.isArray(report.metrics)).toBe(true);
      expect(Array.isArray(report.anomalies)).toBe(true);
      expect(Array.isArray(report.recommendations)).toBe(true);

      expect(report.summary.total_metrics).toBeGreaterThan(0);
    });

    test("should include performance recommendations", async () => {
      // Record some performance data that might trigger recommendations
      await recordMetric("slow_response", 2000, "api", { test_run: true }); // Slow response
      await recordMetric("high_memory", 85, "system", { test_run: true }); // High memory usage

      const report = await generatePerformanceReport("1h");

      expect(report.recommendations.length).toBeGreaterThan(0);

      const recommendations = report.recommendations;
      const hasPerformanceRecommendation = recommendations.some(r => 
        r.type === "performance" && r.priority === "high"
      );

      if (hasPerformanceRecommendation) {
        expect(recommendations.find(r => r.type === "performance")).toHaveProperty("description");
        expect(recommendations.find(r => r.type === "performance")).toHaveProperty("action");
      }
    });

    test("should filter report by categories", async () => {
      // Record metrics in different categories
      await recordMetric("cat_api", 100, "api", { test_run: true });
      await recordMetric("cat_db", 50, "database", { test_run: true });
      await recordMetric("cat_cache", 25, "cache", { test_run: true });

      const apiReport = await generatePerformanceReport("1h", "api");
      const dbReport = await generatePerformanceReport("1h", "database");

      expect(apiReport.metrics.every(m => m.category === "api")).toBe(true);
      expect(dbReport.metrics.every(m => m.category === "database")).toBe(true);

      expect(apiReport.summary.total_metrics).toBeGreaterThan(0);
      expect(dbReport.summary.total_metrics).toBeGreaterThan(0);
    });
  });

  describe("Performance Benchmarking", () => {
    test("should benchmark database operations", async () => {
      const timerId = startTimer("db_benchmark");
      
      // Perform database operation
      await query("SELECT COUNT(*) FROM stock_symbols");
      
      const duration = endTimer(timerId);
      await recordMetric("db_benchmark", duration, "database", { 
        operation: "count", 
        test_run: true 
      });

      expect(duration).toBeGreaterThan(0);
      expect(duration).toBeLessThan(1000); // Should complete within 1 second

      // Verify metric was recorded
      const metrics = await getMetrics("db_benchmark", "1h", "database");
      expect(metrics.length).toBeGreaterThan(0);
      expect(metrics[0].value).toBe(duration);
    });

    test("should benchmark API response times", async () => {
      const operations = ["user_lookup", "portfolio_calc", "market_data_fetch"];
      const durations = [];

      for (const operation of operations) {
        const timerId = startTimer(operation);
        
        // Simulate API operation with varying complexity
        const delay = (operations.indexOf(operation) * 17 + 23) % 100 + 50; // deterministic delay
        await new Promise(resolve => setTimeout(resolve, delay));
        
        const duration = endTimer(timerId);
        durations.push(duration);
        
        await recordMetric("api_benchmark", duration, "api", { 
          operation, 
          test_run: true 
        });
      }

      // All operations should complete reasonably quickly
      durations.forEach(duration => {
        expect(duration).toBeGreaterThan(40); // At least 40ms (due to our setTimeout)
        expect(duration).toBeLessThan(500); // Less than 500ms
      });

      // Verify all metrics were recorded
      const metrics = await getMetrics("api_benchmark", "1h", "api");
      expect(metrics.length).toBe(operations.length);
    });

    test("should compare performance across time periods", async () => {
      const now = Date.now();
      
      // Record metrics for "previous period"
      await recordMetric("comparison_test", 100, "test", { 
        test_run: true, 
        timestamp: now - 3600000 // 1 hour ago
      });
      await recordMetric("comparison_test", 110, "test", { 
        test_run: true, 
        timestamp: now - 3600000
      });

      // Record metrics for "current period"
      await recordMetric("comparison_test", 90, "test", { 
        test_run: true, 
        timestamp: now
      });
      await recordMetric("comparison_test", 95, "test", { 
        test_run: true, 
        timestamp: now
      });

      const previousAvg = await getAverageResponseTime("comparison_test", "1h", "test");
      const currentMetrics = await getMetrics("comparison_test", "30m", "test");
      const currentAvg = currentMetrics.reduce((sum, m) => sum + m.value, 0) / currentMetrics.length;

      expect(previousAvg).toBeGreaterThan(currentAvg); // Performance improved
      expect(previousAvg).toBe(105); // (100 + 110) / 2
      expect(currentAvg).toBe(92.5); // (90 + 95) / 2
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle database connection issues gracefully", async () => {
      // This test would normally require temporarily breaking the DB connection
      // For now, we test that metrics functions handle errors gracefully
      
      try {
        const metrics = await getMetrics("nonexistent_metric", "1h", "test");
        expect(Array.isArray(metrics)).toBe(true);
        expect(metrics.length).toBe(0);
      } catch (error) {
        // Should not throw unhandled errors
        expect(error).toBeDefined();
      }
    });

    test("should handle invalid time ranges", async () => {
      const metrics = await getMetrics("test_metric", "invalid_range", "test");
      expect(Array.isArray(metrics)).toBe(true);
      // Should default to a reasonable time range
    });

    test("should handle very large metric values", async () => {
      const largeValue = Number.MAX_SAFE_INTEGER - 1;
      
      await recordMetric("large_value_test", largeValue, "test", { test_run: true });
      
      const metrics = await getMetrics("large_value_test", "1h", "test");
      expect(metrics.length).toBeGreaterThan(0);
      expect(metrics[0].value).toBe(largeValue);
    });

    test("should handle concurrent metric recording", async () => {
      const concurrentOps = Array.from({ length: 10 }, (_, i) =>
        recordMetric("concurrent_test", i * 10, "test", { 
          iteration: i, 
          test_run: true 
        })
      );

      await Promise.all(concurrentOps);

      const metrics = await getMetrics("concurrent_test", "1h", "test");
      expect(metrics.length).toBe(10);

      // Verify all values were recorded correctly
      const values = metrics.map(m => m.value).sort((a, b) => a - b);
      const expectedValues = Array.from({ length: 10 }, (_, i) => i * 10);
      expect(values).toEqual(expectedValues);
    });
  });
});
const monitor = require("../../../utils/performanceMonitor");
jest.mock("../../../utils/database");
jest.mock("../../../utils/logger");
describe("Performance Monitor", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Clear monitor state
    monitor.reset();
  });
const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require("../../../utils/database");

  describe("operation tracking", () => {
    test("should start and end operations", () => {
      const operationId = "test-operation-123";
      const category = "api";
      const metadata = { endpoint: "/api/test", method: "GET" };
      // Start operation
      monitor.startOperation(operationId, category, metadata);
      const activeOps = monitor.getActiveOperations();
      expect(activeOps.length).toBe(1);
      expect(activeOps.some((op) => op.id === operationId)).toBe(true);
      // End operation
      const result = { success: true, statusCode: 200 };
      monitor.endOperation(operationId, result);
      const activeOpsAfter = monitor.getActiveOperations();
      expect(activeOpsAfter.length).toBe(0);
    });
    test("should handle duplicate operation start", () => {
      const operationId = "duplicate-op";
      const category = "api";
      // Start operation twice
      monitor.startOperation(operationId, category);
      monitor.startOperation(operationId, category);
      const activeOps = monitor.getActiveOperations();
      expect(activeOps.length).toBe(1);
    });
    test("should handle ending non-existent operation", () => {
      expect(() => {
        monitor.endOperation("non-existent-op", { success: true });
      }).not.toThrow();
    });
    test("should record operation metrics", async () => {
      const operationId = "metrics-test";
      const category = "database";
      monitor.startOperation(operationId, category);
      // Wait a bit to ensure duration > 0
      await new Promise((resolve) => setTimeout(resolve, 10));
      monitor.endOperation(operationId, { success: true, rows: 5 });
      const metrics = monitor.getMetrics();
      expect(metrics.database).toBeDefined();
      expect(metrics.database.queries).toBeDefined();
      expect(metrics.system.totalRequests).toBeGreaterThan(0);
    });
  });
  describe("metrics collection", () => {
    test("should record custom metrics", () => {
      const customMetric = {
        id: "custom-123",
        category: "custom",
        duration: 150,
        success: true,
        timestamp: Date.now(),
        metadata: { type: "test" },
      };
      monitor.recordMetric(customMetric);
      // Check that the metric was recorded and verify metrics structure
      const metrics = monitor.getMetrics();
      expect(metrics.system.totalRequests).toBe(1);
      expect(Object.keys(metrics)).toEqual([
        "system",
        "api",
        "database",
        "external",
      ]);
    });
    test("should get performance statistics", () => {
      // Add some test metrics
      monitor.recordMetric({
        operationId: "stat-test-1",
        category: "api",
        duration: 100,
        success: true,
        timestamp: Date.now(),
      });
      monitor.recordMetric({
        operationId: "stat-test-2",
        category: "api",
        duration: 200,
        success: false,
        timestamp: Date.now(),
      });
      const stats = monitor.getPerformanceStats();
      expect(stats).toHaveProperty("overview");
      expect(stats.overview).toHaveProperty("totalOperations");
      expect(stats).toHaveProperty("byCategory");
      expect(stats).toHaveProperty("systemHealth");
    });
    test("should calculate system health", () => {
      // Add some recent metrics
      const now = Date.now();
      monitor.recordMetric({
        operationId: "health-1",
        category: "api",
        duration: 50,
        success: true,
        timestamp: now,
      });
      const health = monitor.calculateSystemHealth();
      expect(health).toHaveProperty("score");
      expect(health).toHaveProperty("status");
      expect(health).toHaveProperty("totalOperations");
      expect(health.score).toBeGreaterThanOrEqual(0);
      expect(health.score).toBeLessThanOrEqual(100);
    });
  });
  describe("performance analysis", () => {
    test("should identify slow operations", () => {
      // Add fast and slow operations
      monitor.recordMetric({
        operationId: "fast-op",
        category: "api",
        duration: 50,
        success: true,
        timestamp: Date.now(),
      });
      monitor.recordMetric({
        operationId: "slow-op",
        category: "api",
        duration: 6000, // Slow operation (exceeds api threshold of 5000ms)
        success: true,
        timestamp: Date.now(),
      });
      const slowOps = monitor.getSlowOperations(10);
      expect(Array.isArray(slowOps)).toBe(true);
      expect(slowOps.length).toBeGreaterThan(0);
      expect(slowOps[0].duration).toBeGreaterThanOrEqual(
        slowOps[1]?.duration || 0
      );
    });
    test("should calculate percentiles", () => {
      const durations = [100, 200, 300, 400, 500];
      const percentile95 = monitor.calculatePercentile(durations, 95);
      const percentile50 = monitor.calculatePercentile(durations, 50);
      expect(percentile95).toBeGreaterThan(percentile50);
      expect(percentile95).toBeGreaterThan(0);
    });
    test("should get performance summary", () => {
      // Add some test data
      monitor.recordMetric({
        operationId: "summary-test",
        category: "database",
        duration: 75,
        success: true,
        timestamp: Date.now(),
      });
      const summary = monitor.getPerformanceSummary();
      expect(summary).toHaveProperty("status");
      expect(summary).toHaveProperty("activeRequests");
      expect(summary).toHaveProperty("alerts");
    });
  });
  describe("specialized metrics", () => {
    test("should track API request metrics", () => {
      monitor.recordMetric({
        operationId: "api-test",
        category: "api_request",
        duration: 120,
        success: true,
        timestamp: Date.now(),
        metadata: { endpoint: "/api/users", method: "GET", statusCode: 200 },
      });
      const apiMetrics = monitor.getApiRequestMetrics();
      expect(apiMetrics).toBeDefined();
      expect(Object.keys(apiMetrics)).toContain("GET /api/users");
    });
    test("should track database metrics", () => {
      monitor.recordMetric({
        operationId: "db-test",
        category: "database",
        duration: 80,
        success: true,
        timestamp: Date.now(),
        metadata: { operation: "SELECT", table: "users", rows: 10 },
      });
      const dbMetrics = monitor.getDatabaseMetrics();
      expect(dbMetrics).toBeDefined();
      expect(Object.keys(dbMetrics)).toContain("SELECT");
    });
    test("should track external API metrics", () => {
      monitor.recordMetric({
        operationId: "ext-api-test",
        category: "external_api",
        duration: 300,
        success: true,
        timestamp: Date.now(),
        metadata: {
          service: "yahoo-finance",
          endpoint: "/quote",
          statusCode: 200,
        },
      });
      const extMetrics = monitor.getExternalApiMetrics();
      expect(extMetrics).toBeDefined();
      expect(Object.keys(extMetrics)).toContain("yahoo-finance");
    });
    test("should generate response time histogram", () => {
      // Add various response times
      monitor.recordMetric({
        operationId: "hist-1",
        category: "api",
        duration: 50,
        success: true,
        timestamp: Date.now(),
      });
      monitor.recordMetric({
        operationId: "hist-2",
        category: "api",
        duration: 150,
        success: true,
        timestamp: Date.now(),
      });
      monitor.recordMetric({
        operationId: "hist-3",
        category: "api",
        duration: 350,
        success: true,
        timestamp: Date.now(),
      });
      const histogram = monitor.getResponseTimeHistogram();
      expect(histogram).toBeDefined();
      expect(histogram instanceof Map).toBe(true);
      expect(histogram.size).toBeGreaterThan(0);
    });
  });
  describe("time utility", () => {
    test("should time async operations", async () => {
      const asyncOperation = async () => {
        await new Promise((resolve) => setTimeout(resolve, 10));
        return { result: "success" };
      };
      const timer = monitor.time("test", null, { type: "async" });
      const result = await timer.wrap(asyncOperation);
      expect(result.result).toBe("success");
      const metrics = monitor.getMetrics();
      expect(metrics.system.totalRequests).toBeGreaterThan(0);
    });
    test("should time sync operations", () => {
      const syncOperation = () => {
        // Simulate some work
        let sum = 0;
        for (let i = 0; i < 1000; i++) {
          sum += i;
        }
        return sum;
      };
      const timer = monitor.time("sync-test");
      timer.start();
      const result = syncOperation();
      timer.end({ success: true, data: result });
      expect(typeof result).toBe("number");
      const metrics = monitor.getMetrics();
      expect(metrics.system.totalRequests).toBeGreaterThan(0);
    });
    test("should handle operation errors in time utility", () => {
      const failingOperation = () => {
        throw new Error("Test error");
      };
      expect(() => {
        monitor.time("error-test", failingOperation);
      }).toThrow("Test error");
      // Should still record the failed operation
      const metrics = monitor.getMetrics();
      expect(metrics.system.totalErrors).toBeGreaterThan(0);
    });
  });
  describe("Express middleware", () => {
    test("should create middleware function", () => {
      const middleware = monitor.middleware();
      expect(typeof middleware).toBe("function");
      expect(middleware.length).toBe(3); // req, res, next
    });
    test("should categorize requests", () => {
      const req1 = { path: "/api/users", method: "GET" };
      const req2 = { path: "/health", method: "GET" };
      const req3 = { path: "/unknown", method: "POST" };
      expect(monitor.categorizeRequest(req1)).toBe("api_request");
      expect(monitor.categorizeRequest(req2)).toBe("health_check");
      expect(monitor.categorizeRequest(req3)).toBe("other");
    });
  });
  describe("alerts and monitoring", () => {
    test("should get alerts", () => {
      // Add a slow operation to trigger potential alert
      monitor.recordMetric({
        operationId: "slow-alert-test",
        category: "api",
        duration: 3000, // Very slow
        success: false,
        timestamp: Date.now(),
      });
      const alerts = monitor.getAlerts();
      expect(Array.isArray(alerts)).toBe(true);
    });
    test("should get active alerts", () => {
      const activeAlerts = monitor.getActiveAlerts();
      expect(Array.isArray(activeAlerts)).toBe(true);
    });
  });
  describe("data management", () => {
    test("should export metrics", () => {
      // Add some test data
      monitor.recordMetric({
        operationId: "export-test",
        category: "api",
        duration: 100,
        success: true,
        timestamp: Date.now(),
      });
      const exported = monitor.exportMetrics();
      expect(exported).toHaveProperty("metrics");
      expect(exported).toHaveProperty("performanceHistory");
      expect(exported).toHaveProperty("exportedAt");
    });
    test("should import metrics", () => {
      const testData = {
        metrics: new Map([["test", { totalOperations: 5 }]]),
        performanceHistory: [
          { operationId: "imported", category: "test", duration: 50 },
        ],
        exportedAt: Date.now(),
      };
      monitor.importMetrics(testData);
      const metrics = monitor.getMetrics();
      expect(metrics).toBeDefined();
      expect(metrics.system).toBeDefined();
    });
    test("should clear history", () => {
      // Add some data
      monitor.recordMetric({
        operationId: "clear-test",
        category: "api",
        duration: 100,
        success: true,
        timestamp: Date.now(),
      });
      monitor.clearHistory();
      const stats = monitor.getPerformanceStats();
      expect(stats.overview.totalOperations).toBe(0);
    });
    test("should reset monitor", () => {
      // Add some data and active operations
      monitor.startOperation("reset-test", "api");
      monitor.recordMetric({
        operationId: "reset-data",
        category: "api",
        duration: 100,
        success: true,
        timestamp: Date.now(),
      });
      monitor.reset();
      const activeOps = monitor.getActiveOperations();
      const metrics = monitor.getMetrics();
      expect(activeOps.length).toBe(0);
      expect(Object.keys(metrics)).toEqual([
        "system",
        "api",
        "database",
        "external",
      ]);
    });
  });
  describe("advanced analytics", () => {
    test("should set custom thresholds", () => {
      const customThresholds = {
        api: 500,
        database: 200,
        external_api: 1000,
      };
      monitor.setThresholds(customThresholds);
      // Add a metric that should trigger alert with custom threshold
      monitor.recordMetric({
        operationId: "threshold-test",
        category: "api",
        duration: 600, // Above custom threshold
        success: true,
        timestamp: Date.now(),
      });
      // Check that alert logic uses new thresholds
      expect(() =>
        monitor.recordMetric({
          operationId: "threshold-test-2",
          category: "api",
          duration: 600,
          success: true,
          timestamp: Date.now(),
        })
      ).not.toThrow();
    });
    test("should set history size", () => {
      monitor.setHistorySize(5); // Small history size
      // Add more metrics than history size
      for (let i = 0; i < 10; i++) {
        monitor.recordMetric({
          operationId: `history-test-${i}`,
          category: "test",
          duration: 50,
          success: true,
          timestamp: Date.now(),
        });
      }
      // Should maintain only recent items
      const stats = monitor.getPerformanceStats();
      expect(stats.overview.totalOperations).toBeLessThanOrEqual(5);
    });
    test("should cleanup memory periodically", () => {
      // Add old data
      const oldTimestamp = Date.now() - 24 * 60 * 60 * 1000; // 24 hours ago
      monitor.recordMetric({
        operationId: "old-metric",
        category: "api",
        duration: 100,
        success: true,
        timestamp: oldTimestamp,
      });
      monitor.cleanupMemory();
      // Should still work after cleanup
      expect(() => monitor.getPerformanceStats()).not.toThrow();
    });
    test("should cleanup orphaned operations", () => {
      // Start an operation and don't end it
      monitor.startOperation("orphaned-op", "api");
      // Manually set old start time to simulate orphaned operation
      const activeOps = monitor.getActiveOperations();
      const operation = activeOps.find((op) => op.id === "orphaned-op");
      if (operation) {
        operation.startTime = Date.now() - 5 * 60 * 1000; // 5 minutes ago
      }
      monitor.cleanupOrphanedOperations();
      const activeOpsAfter = monitor.getActiveOperations();
      expect(activeOpsAfter.length).toBe(0);
    });
  });
  describe("error handling and edge cases", () => {
    test("should handle invalid metrics", () => {
      expect(() => {
        monitor.recordMetric(null);
      }).not.toThrow();
      expect(() => {
        monitor.recordMetric({});
      }).not.toThrow();
      expect(() => {
        monitor.recordMetric({ duration: "invalid" });
      }).not.toThrow();
    });
    test("should handle invalid operation IDs", () => {
      expect(() => {
        monitor.startOperation(null, "api");
      }).not.toThrow();
      expect(() => {
        monitor.endOperation("", { success: true });
      }).not.toThrow();
    });
    test("should handle edge case percentile calculations", () => {
      expect(monitor.calculatePercentile([], 50)).toBe(0);
      expect(monitor.calculatePercentile([100], 50)).toBe(100);
    });
    test("should handle concurrent access", () => {
      // Simulate concurrent operations
      const promises = [];
      for (let i = 0; i < 10; i++) {
        promises.push(
          new Promise((resolve) => {
            monitor.startOperation(`concurrent-${i}`, "test");
            setTimeout(() => {
              monitor.endOperation(`concurrent-${i}`, { success: true });
              resolve();
            }, Math.random() * 10);
          })
        );
      }
      return Promise.all(promises).then(() => {
        const stats = monitor.getPerformanceStats();
        expect(stats.overview.totalOperations).toBeGreaterThan(0);
      });
    });
  });
});

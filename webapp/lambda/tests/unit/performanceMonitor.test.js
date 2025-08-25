/**
 * Unit Tests for Performance Monitor
 * Tests operation timing, metrics aggregation, performance alerts, and statistics
 */

// Mock logger before requiring performanceMonitor
jest.mock("../../utils/logger", () => ({
  debug: jest.fn(),
  warn: jest.fn(),
  info: jest.fn(),
  error: jest.fn(),
}));

const logger = require("../../utils/logger");

describe("Performance Monitor", () => {
  let performanceMonitor;

  beforeEach(() => {
    jest.clearAllMocks();

    // Clear module cache to get fresh instance
    delete require.cache[require.resolve("../../utils/performanceMonitor")];
    performanceMonitor = require("../../utils/performanceMonitor");

    // Reset the singleton state for each test
    performanceMonitor.reset();

    // Mock console.log to reduce noise
    jest.spyOn(console, "log").mockImplementation();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("Initialization", () => {
    test("should initialize with empty metrics and operations", () => {
      expect(performanceMonitor.metrics.size).toBe(0);
      expect(performanceMonitor.activeOperations.size).toBe(0);
      expect(performanceMonitor.performanceHistory).toHaveLength(0);
    });

    test("should initialize with default thresholds", () => {
      expect(performanceMonitor.thresholds.database).toBe(1000);
      expect(performanceMonitor.thresholds.api).toBe(5000);
      expect(performanceMonitor.thresholds.pattern).toBe(3000);
      expect(performanceMonitor.thresholds.dashboard).toBe(2000);
      expect(performanceMonitor.thresholds.general).toBe(10000);
    });

    test("should set default history size", () => {
      expect(performanceMonitor.historySize).toBe(1000);
    });
  });

  describe("Operation Timing", () => {
    test("should start operation tracking", () => {
      const operationId = "test-op-123";
      const metadata = { userId: "user-456", route: "/api/test" };

      const operation = performanceMonitor.startOperation(
        operationId,
        "database",
        metadata
      );

      expect(operation.id).toBe(operationId);
      expect(operation.category).toBe("database");
      expect(operation.startTime).toBeCloseTo(Date.now(), -1); // Allow up to 5ms difference
      expect(operation.startHrTime).toBeDefined();
      expect(operation.metadata).toEqual(metadata);
      expect(operation.userId).toBe("user-456");

      expect(performanceMonitor.activeOperations.has(operationId)).toBe(true);

      expect(logger.debug).toHaveBeenCalledWith("Operation Started", {
        operationId,
        category: "database",
        metadata,
      });
    });

    test("should end operation and calculate duration", (done) => {
      const operationId = "test-op-456";

      performanceMonitor.startOperation(operationId, "api", { route: "/test" });

      // Wait a bit to ensure duration > 0
      setTimeout(() => {
        const result = { success: true, data: { rows: 10 } };
        const metric = performanceMonitor.endOperation(operationId, result);

        expect(metric).toBeDefined();
        expect(metric.id).toBe(operationId);
        expect(metric.category).toBe("api");
        expect(metric.duration).toBeGreaterThan(0);
        expect(metric.preciseDuration).toBeGreaterThan(0);
        expect(metric.success).toBe(true);
        expect(metric.result).toEqual({ rows: 10 });
        expect(metric.timestamp).toBeDefined();

        expect(performanceMonitor.activeOperations.has(operationId)).toBe(
          false
        );

        expect(logger.debug).toHaveBeenCalledWith(
          "Operation Completed",
          expect.objectContaining({
            operationId,
            category: "api",
            duration: expect.any(Number),
            success: true,
          })
        );

        done();
      }, 10);
    });

    test("should handle ending non-existent operation", () => {
      const metric = performanceMonitor.endOperation("non-existent");

      expect(metric).toBeNull();
      expect(logger.warn).toHaveBeenCalledWith("Operation not found", {
        operationId: "non-existent",
      });
    });

    test("should record failed operation", (done) => {
      const operationId = "failed-op";

      performanceMonitor.startOperation(operationId, "database");

      setTimeout(() => {
        const result = { success: false, error: "Connection timeout" };
        const metric = performanceMonitor.endOperation(operationId, result);

        expect(metric.success).toBe(false);
        expect(metric.error).toBe("Connection timeout");

        done();
      }, 5);
    });

    test("should track correlation ID and user ID", () => {
      const operationId = "corr-op";
      const metadata = {
        correlationId: "req-123",
        userId: "user-789",
      };

      performanceMonitor.startOperation(operationId, "dashboard", metadata);
      const metric = performanceMonitor.endOperation(operationId, {
        success: true,
      });

      expect(metric.correlationId).toBe("req-123");
      expect(metric.userId).toBe("user-789");
    });
  });

  describe("Metrics Aggregation", () => {
    test("should aggregate metrics by category", (done) => {
      const operations = [
        { id: "db-1", category: "database", duration: 100 },
        { id: "db-2", category: "database", duration: 200 },
        { id: "api-1", category: "api", duration: 500 },
      ];

      // Start and end operations quickly
      operations.forEach(({ id, category }) => {
        performanceMonitor.startOperation(id, category);
      });

      setTimeout(() => {
        operations.forEach(({ id, duration }) => {
          // Mock the end time to get predictable duration
          const operation = performanceMonitor.activeOperations.get(id);
          operation.startTime = Date.now() - duration;
          performanceMonitor.endOperation(id, { success: true });
        });

        const dbStats = performanceMonitor.metrics.get("database");
        expect(dbStats.count).toBe(2);
        expect(dbStats.totalDuration).toBe(300);
        expect(dbStats.averageDuration).toBe(150);
        expect(dbStats.minDuration).toBe(100);
        expect(dbStats.maxDuration).toBe(200);
        expect(dbStats.successCount).toBe(2);
        expect(dbStats.errorCount).toBe(0);

        const apiStats = performanceMonitor.metrics.get("api");
        expect(apiStats.count).toBe(1);
        expect(apiStats.totalDuration).toBe(500);
        expect(apiStats.averageDuration).toBe(500);

        done();
      }, 5);
    });

    test("should maintain recent durations for percentile calculation", () => {
      // Add many operations to test recent durations limit
      for (let i = 0; i < 150; i++) {
        const operation = {
          id: `op-${i}`,
          category: "test",
          duration: i * 10,
          timestamp: new Date().toISOString(),
          success: true,
          metadata: {},
        };
        performanceMonitor.recordMetric(operation);
      }

      const stats = performanceMonitor.metrics.get("test");
      expect(stats.recentDurations).toHaveLength(100); // Should be capped at 100
      expect(stats.count).toBe(150); // Total count should still be 150
    });

    test("should track success and error counts", () => {
      const operations = [
        { category: "database", success: true },
        { category: "database", success: false },
        { category: "database", success: true },
        { category: "database", success: false },
      ];

      operations.forEach((op, index) => {
        const metric = {
          id: `op-${index}`,
          category: op.category,
          duration: 100,
          timestamp: new Date().toISOString(),
          success: op.success,
          metadata: {},
        };
        performanceMonitor.recordMetric(metric);
      });

      const stats = performanceMonitor.metrics.get("database");
      expect(stats.successCount).toBe(2);
      expect(stats.errorCount).toBe(2);
      expect(stats.count).toBe(4);
    });
  });

  describe("Performance Alerts", () => {
    test("should trigger alert when threshold exceeded", () => {
      const consoleSpy = jest.spyOn(console, "log").mockImplementation();

      const operationId = "slow-db-op";
      performanceMonitor.startOperation(operationId, "database");

      // Mock slow operation by setting start time far in the past
      const operation = performanceMonitor.activeOperations.get(operationId);
      operation.startTime = Date.now() - 2500; // 2.5 seconds ago (exceeds 2x threshold for high severity)

      performanceMonitor.endOperation(operationId, { success: true });

      expect(logger.warn).toHaveBeenCalledWith(
        "Performance Alert",
        expect.objectContaining({
          category: "database",
          duration: expect.any(Number),
          threshold: 1000,
          severity: "high",
          operationId,
        })
      );

      expect(consoleSpy).toHaveBeenCalledWith(
        "⚠️ PERFORMANCE ALERT:",
        expect.stringContaining("Slow operation detected: database took")
      );

      consoleSpy.mockRestore();
    });

    test("should set appropriate severity levels", () => {
      const operationId = "medium-slow-op";
      performanceMonitor.startOperation(operationId, "api");

      const operation = performanceMonitor.activeOperations.get(operationId);
      operation.startTime = Date.now() - 6000; // 6 seconds (exceeds 5s threshold but < 2x threshold)

      performanceMonitor.endOperation(operationId, { success: true });

      expect(logger.warn).toHaveBeenCalledWith(
        "Performance Alert",
        expect.objectContaining({
          severity: "medium",
        })
      );
    });

    test("should use general threshold for unknown category", () => {
      const operationId = "unknown-op";
      performanceMonitor.startOperation(operationId, "unknown-category");

      const operation = performanceMonitor.activeOperations.get(operationId);
      operation.startTime = Date.now() - 11000; // 11 seconds (exceeds 10s general threshold)

      performanceMonitor.endOperation(operationId, { success: true });

      expect(logger.warn).toHaveBeenCalledWith(
        "Performance Alert",
        expect.objectContaining({
          category: "unknown-category",
          threshold: 10000,
        })
      );
    });

    test("should not trigger alert when within threshold", () => {
      const operationId = "fast-op";
      performanceMonitor.startOperation(operationId, "database");

      const operation = performanceMonitor.activeOperations.get(operationId);
      operation.startTime = Date.now() - 500; // 500ms (within 1s threshold)

      performanceMonitor.endOperation(operationId, { success: true });

      expect(logger.warn).not.toHaveBeenCalledWith(
        "Performance Alert",
        expect.anything()
      );
    });
  });

  describe("Performance Statistics", () => {
    beforeEach(() => {
      // Add some test metrics
      const testMetrics = [
        { id: "db-1", category: "database", duration: 500, success: true },
        { id: "db-2", category: "database", duration: 800, success: true },
        { id: "db-3", category: "database", duration: 1200, success: false },
        { id: "api-1", category: "api", duration: 2000, success: true },
        { id: "api-2", category: "api", duration: 6000, success: false },
      ];

      testMetrics.forEach((metric) => {
        performanceMonitor.recordMetric({
          ...metric,
          timestamp: new Date().toISOString(),
          metadata: {},
        });
      });
    });

    test("should provide comprehensive performance statistics", () => {
      const stats = performanceMonitor.getPerformanceStats();

      expect(stats).toHaveProperty("overview");
      expect(stats).toHaveProperty("byCategory");
      expect(stats).toHaveProperty("slowOperations");
      expect(stats).toHaveProperty("systemHealth");

      // Overview stats
      expect(stats.overview.totalOperations).toBe(5);
      expect(stats.overview.activeOperations).toBe(0);
      expect(typeof stats.overview.lastHour).toBe("number");

      // Category stats
      expect(stats.byCategory).toHaveProperty("database");
      expect(stats.byCategory).toHaveProperty("api");

      const dbStats = stats.byCategory.database;
      expect(dbStats.count).toBe(3);
      expect(dbStats.successCount).toBe(2);
      expect(dbStats.errorCount).toBe(1);
      expect(dbStats.successRate).toBe("66.67");
      expect(dbStats.averageDuration).toBeCloseTo(833.33, 2);

      const apiStats = stats.byCategory.api;
      expect(apiStats.count).toBe(2);
      expect(apiStats.successCount).toBe(1);
      expect(apiStats.errorCount).toBe(1);
      expect(apiStats.successRate).toBe("50.00");
    });

    test("should calculate percentiles correctly", () => {
      // Add more data points for better percentile testing
      const durations = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000];
      durations.forEach((duration, index) => {
        const metric = {
          id: `test-${index}`,
          category: "test",
          duration,
          timestamp: new Date().toISOString(),
          success: true,
          metadata: {},
        };
        performanceMonitor.recordMetric(metric);
      });

      const p95 = performanceMonitor.calculatePercentile(durations, 95);
      const p99 = performanceMonitor.calculatePercentile(durations, 99);

      expect(p95).toBe(1000); // 95th percentile of 10 items = 10th item
      expect(p99).toBe(1000); // 99th percentile of 10 items = 10th item

      // Test empty array
      const emptyP95 = performanceMonitor.calculatePercentile([], 95);
      expect(emptyP95).toBe(0);
    });

    test("should identify slow operations", () => {
      const slowOps = performanceMonitor.getSlowOperations();

      expect(Array.isArray(slowOps)).toBe(true);

      // Should include operations that exceed their category thresholds
      const slowDbOp = slowOps.find(
        (op) => op.category === "database" && op.duration > 1000
      );
      const slowApiOp = slowOps.find(
        (op) => op.category === "api" && op.duration > 5000
      );

      expect(slowDbOp).toBeDefined();
      expect(slowApiOp).toBeDefined();

      // Should be sorted by duration (slowest first)
      for (let i = 1; i < slowOps.length; i++) {
        expect(slowOps[i].duration).toBeLessThanOrEqual(
          slowOps[i - 1].duration
        );
      }
    });

    test("should limit slow operations results", () => {
      // Add many slow operations
      for (let i = 0; i < 50; i++) {
        const metric = {
          id: `slow-${i}`,
          category: "database",
          duration: 2000 + i, // All exceed 1s threshold
          timestamp: new Date().toISOString(),
          success: true,
          metadata: {},
        };
        performanceMonitor.recordMetric(metric);
      }

      const slowOps = performanceMonitor.getSlowOperations(10);
      expect(slowOps).toHaveLength(10);
    });

    test("should calculate system health", () => {
      const stats = performanceMonitor.getPerformanceStats();
      const systemHealth = stats.systemHealth;

      expect(systemHealth).toHaveProperty("score");
      expect(systemHealth).toHaveProperty("status");
      expect(systemHealth).toHaveProperty("successRate");
      expect(systemHealth).toHaveProperty("averageDuration");
      expect(systemHealth).toHaveProperty("slowOperations");
      expect(systemHealth).toHaveProperty("totalOperations");

      expect(typeof systemHealth.status).toBe("string");
      expect(
        ["healthy", "warning", "degraded", "critical"].includes(systemHealth.status)
      ).toBe(true);

      expect(typeof systemHealth.score).toBe("number");
      expect(systemHealth.score).toBeGreaterThanOrEqual(0);
      expect(systemHealth.score).toBeLessThanOrEqual(100);
    });
  });

  describe("History Management", () => {
    test("should maintain history size limit", () => {
      // Set smaller limit for testing
      performanceMonitor.historySize = 5;

      // Add more metrics than the limit
      for (let i = 0; i < 10; i++) {
        const metric = {
          id: `op-${i}`,
          category: "test",
          duration: i * 100,
          timestamp: new Date().toISOString(),
          success: true,
          metadata: {},
        };
        performanceMonitor.recordMetric(metric);
      }

      expect(performanceMonitor.performanceHistory).toHaveLength(5);

      // Should keep the most recent metrics
      const lastMetric = performanceMonitor.performanceHistory[4];
      expect(lastMetric.id).toBe("op-9");
    });

    test("should count operations from last hour", () => {
      const now = Date.now();

      // Add recent operation
      performanceMonitor.recordMetric({
        id: "recent",
        category: "test",
        duration: 100,
        timestamp: new Date(now).toISOString(),
        success: true,
        metadata: {},
      });

      // Add old operation (2 hours ago)
      performanceMonitor.recordMetric({
        id: "old",
        category: "test",
        duration: 200,
        timestamp: new Date(now - 7200000).toISOString(),
        success: true,
        metadata: {},
      });

      const stats = performanceMonitor.getPerformanceStats();
      expect(stats.overview.lastHour).toBe(1); // Only recent operation
      expect(stats.overview.totalOperations).toBe(2); // Both operations in total
    });
  });

  describe("Active Operations Tracking", () => {
    test("should track active operations count", () => {
      performanceMonitor.startOperation("op-1", "database");
      performanceMonitor.startOperation("op-2", "api");

      expect(performanceMonitor.activeOperations.size).toBe(2);

      const stats = performanceMonitor.getPerformanceStats();
      expect(stats.overview.activeOperations).toBe(2);

      performanceMonitor.endOperation("op-1", { success: true });

      expect(performanceMonitor.activeOperations.size).toBe(1);
    });

    test("should handle concurrent operations", () => {
      const operationIds = ["concurrent-1", "concurrent-2", "concurrent-3"];

      // Start all operations
      operationIds.forEach((id) => {
        performanceMonitor.startOperation(id, "concurrent", { testData: true });
      });

      expect(performanceMonitor.activeOperations.size).toBe(3);

      // End operations in different order
      performanceMonitor.endOperation("concurrent-2", { success: true });
      performanceMonitor.endOperation("concurrent-1", {
        success: false,
        error: "Test error",
      });
      performanceMonitor.endOperation("concurrent-3", { success: true });

      expect(performanceMonitor.activeOperations.size).toBe(0);

      const stats = performanceMonitor.metrics.get("concurrent");
      expect(stats.count).toBe(3);
      expect(stats.successCount).toBe(2);
      expect(stats.errorCount).toBe(1);
    });
  });
});

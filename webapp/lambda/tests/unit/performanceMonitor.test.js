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

    // Get the current instance and reset it (instead of creating new instances)
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

      expect(p95).toBe(1000); // 95th percentile: ceil(0.95 * 10) - 1 = index 9 = 1000
      expect(p99).toBe(1000); // 99th percentile: ceil(0.99 * 10) - 1 = index 9 = 1000

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
        ["healthy", "warning", "degraded", "critical"].includes(
          systemHealth.status
        )
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

  describe("History Management", () => {
    test("should maintain history size limit", () => {
      performanceMonitor.historySize = 5; // Set small limit for testing

      // Add more operations than history limit
      for (let i = 0; i < 10; i++) {
        const opId = `hist-op-${i}`;
        performanceMonitor.startOperation(opId, "test");
        performanceMonitor.endOperation(opId, { success: true });
      }

      expect(performanceMonitor.performanceHistory.length).toBe(5);
      expect(performanceMonitor.performanceHistory[0].id).toBe("hist-op-5");
      expect(performanceMonitor.performanceHistory[4].id).toBe("hist-op-9");
    });

    test("should clear history", () => {
      performanceMonitor.startOperation("clear-test", "test");
      performanceMonitor.endOperation("clear-test", { success: true });

      expect(performanceMonitor.performanceHistory.length).toBeGreaterThan(0);

      performanceMonitor.clearHistory();

      expect(performanceMonitor.performanceHistory.length).toBe(0);
    });
  });

  describe("Memory and Resource Management", () => {
    test("should handle memory pressure cleanup", () => {
      // Fill with many operations
      for (let i = 0; i < 50; i++) {
        const opId = `memory-op-${i}`;
        performanceMonitor.startOperation(opId, "test");
        performanceMonitor.endOperation(opId, { success: true });
      }

      const initialHistorySize = performanceMonitor.performanceHistory.length;

      // Simulate memory pressure cleanup
      performanceMonitor.cleanupMemory();

      expect(performanceMonitor.performanceHistory.length).toBeLessThanOrEqual(
        initialHistorySize
      );
    });

    test("should handle orphaned operations", () => {
      const orphanedOp = "orphaned-operation";
      performanceMonitor.startOperation(orphanedOp, "test");

      // Simulate operation timeout by manually setting old start time
      const operation = performanceMonitor.activeOperations.get(orphanedOp);
      operation.startTime = Date.now() - 65000; // 65 seconds ago (more than 60 seconds)

      performanceMonitor.cleanupOrphanedOperations();

      expect(performanceMonitor.activeOperations.has(orphanedOp)).toBe(false);
      expect(logger.warn).toHaveBeenCalledWith(
        "Cleaned up orphaned operation",
        expect.objectContaining({
          operationId: orphanedOp,
        })
      );
    });
  });

  describe("Advanced Metrics and Statistics", () => {
    test("should calculate percentiles correctly", () => {
      const durations = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000];

      durations.forEach((duration, i) => {
        const opId = `perf-op-${i}`;
        performanceMonitor.startOperation(opId, "percentile-test");

        // Mock the duration by manipulating the operation
        const operation = performanceMonitor.activeOperations.get(opId);
        operation.startTime = Date.now() - duration;

        performanceMonitor.endOperation(opId, { success: true });
      });

      const stats = performanceMonitor.getPerformanceStats();
      const categoryStats = stats.byCategory["percentile-test"];

      // For 10 items [100,200,300,400,500,600,700,800,900,1000] using nearest rank method:
      // p50: ceil(0.50 * 10) - 1 = 4 -> index 4 -> 500
      // p95: ceil(0.95 * 10) - 1 = 9 -> index 9 -> 1000
      // p99: ceil(0.99 * 10) - 1 = 9 -> index 9 -> 1000
      expect(categoryStats.percentiles.p50).toBe(500);
      expect(categoryStats.percentiles.p95).toBe(1000);
      expect(categoryStats.percentiles.p99).toBe(1000);
    });

    test("should track operation trends", () => {
      // Simulate operations with increasing duration (performance degradation)
      for (let i = 0; i < 10; i++) {
        const opId = `trend-op-${i}`;
        const duration = 100 + i * 50; // Increasing duration

        performanceMonitor.startOperation(opId, "trend-test");

        const operation = performanceMonitor.activeOperations.get(opId);
        operation.startTime = Date.now() - duration;

        performanceMonitor.endOperation(opId, { success: true });
      }

      const trends = performanceMonitor.getPerformanceTrends("trend-test");

      expect(trends.direction).toBe("degrading");
      expect(trends.slope).toBeGreaterThan(0);
    });

    test("should identify performance anomalies", () => {
      const testCategory = `anomaly-test-${Date.now()}`;

      // Ensure clean state for this test
      performanceMonitor.reset();
      expect(performanceMonitor.performanceHistory.length).toBe(0);

      // Create baseline with normal variance (need at least 10 for detection)
      const baselineDurations = [
        90, 95, 100, 105, 110, 85, 115, 92, 108, 88, 112, 94, 106, 87, 113,
      ];
      for (let i = 0; i < 15; i++) {
        const opId = `baseline-op-${i}-${Date.now()}`;
        performanceMonitor.recordMetric({
          id: opId,
          category: testCategory,
          duration: baselineDurations[i], // Variable durations to create statistical variance
          timestamp: new Date().toISOString(),
          success: true,
          metadata: {},
        });
      }

      // Add anomalous operation - needs to be way outside the baseline (3+ standard deviations)
      const anomalyOpId = `anomaly-op-${Date.now()}`;
      performanceMonitor.recordMetric({
        id: anomalyOpId,
        category: testCategory,
        duration: 500, // Much higher than baseline range of ~85-115ms
        timestamp: new Date().toISOString(),
        success: true,
        metadata: {},
      });

      const anomalies = performanceMonitor.detectAnomalies(testCategory);

      expect(anomalies.length).toBeGreaterThan(0);
      expect(anomalies[0].operationId).toBe(anomalyOpId);
      expect(anomalies[0].severity).toBe("medium");
    });
  });

  describe("Real-time Monitoring", () => {
    test("should provide real-time dashboard data", () => {
      // Create mix of operations
      const operations = [
        { id: "rt-db-1", category: "database", duration: 150, success: true },
        { id: "rt-api-1", category: "api", duration: 2000, success: true },
        { id: "rt-db-2", category: "database", duration: 800, success: false },
        { id: "rt-api-2", category: "api", duration: 6000, success: true }, // Slow
      ];

      operations.forEach((op) => {
        performanceMonitor.startOperation(op.id, op.category);

        const operation = performanceMonitor.activeOperations.get(op.id);
        operation.startTime = Date.now() - op.duration;

        performanceMonitor.endOperation(op.id, { success: op.success });
      });

      const dashboardData = performanceMonitor.getRealTimeDashboard();

      expect(dashboardData.totalOperations).toBe(4);
      expect(dashboardData.activeOperations).toBe(0);
      expect(dashboardData.errorRate).toBe(0.25); // 1 out of 4 failed
      expect(dashboardData.alerts.length).toBeGreaterThan(0); // Should have slow operation alert

      expect(dashboardData.categoryBreakdown.database.count).toBe(2);
      expect(dashboardData.categoryBreakdown.api.count).toBe(2);
    });

    test("should handle empty dashboard data", () => {
      const dashboardData = performanceMonitor.getRealTimeDashboard();

      expect(dashboardData.totalOperations).toBe(0);
      expect(dashboardData.activeOperations).toBe(0);
      expect(dashboardData.errorRate).toBe(0);
      expect(dashboardData.alerts.length).toBe(0);
    });
  });

  describe("Configuration and Thresholds", () => {
    test("should allow custom threshold configuration", () => {
      const customThresholds = {
        database: 500,
        api: 3000,
        custom_category: 1500,
      };

      performanceMonitor.setThresholds(customThresholds);

      expect(performanceMonitor.thresholds.database).toBe(500);
      expect(performanceMonitor.thresholds.api).toBe(3000);
      expect(performanceMonitor.thresholds.custom_category).toBe(1500);
    });

    test("should allow history size configuration", () => {
      performanceMonitor.setHistorySize(2000);

      expect(performanceMonitor.historySize).toBe(2000);
    });

    test("should validate configuration parameters", () => {
      expect(() => {
        performanceMonitor.setHistorySize(-100);
      }).toThrow("History size must be positive");

      expect(() => {
        performanceMonitor.setThresholds({ database: -500 });
      }).toThrow("Threshold values must be positive");
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle concurrent operations with same ID", () => {
      const duplicateId = "duplicate-op";

      performanceMonitor.startOperation(duplicateId, "test");
      performanceMonitor.startOperation(duplicateId, "test"); // Duplicate

      expect(logger.warn).toHaveBeenCalledWith(
        "Operation ID already exists, overwriting",
        expect.objectContaining({
          operationId: duplicateId,
        })
      );
    });

    test("should handle null/undefined results", () => {
      const opId = "null-result-op";
      performanceMonitor.startOperation(opId, "test");

      const metric1 = performanceMonitor.endOperation(opId, null);
      expect(metric1.result).toEqual({}); // null gets converted to empty object

      performanceMonitor.startOperation(opId + "-2", "test");
      const metric2 = performanceMonitor.endOperation(opId + "-2", undefined);
      expect(metric2.result).toEqual({}); // undefined gets converted to empty object
    });

    test("should handle operations with missing metadata", () => {
      const opId = "no-metadata-op";

      const operation = performanceMonitor.startOperation(opId, "test");

      expect(operation.metadata).toEqual({});
      expect(operation.correlationId).toBeUndefined();
      expect(operation.userId).toBeUndefined();
    });

    test("should handle system clock changes", () => {
      const opId = "clock-change-op";
      performanceMonitor.startOperation(opId, "test");

      // Simulate backward clock change
      const operation = performanceMonitor.activeOperations.get(opId);
      operation.startTime = Date.now() + 5000; // Future time

      const metric = performanceMonitor.endOperation(opId, { success: true });

      // Should handle negative duration gracefully
      expect(metric.duration).toBeGreaterThanOrEqual(0);
      expect(logger.warn).toHaveBeenCalledWith(
        "Clock skew detected in performance monitoring",
        expect.any(Object)
      );
    });
  });

  describe("Integration with External Systems", () => {
    test("should export metrics in standard format", () => {
      performanceMonitor.startOperation("export-op", "database", {
        table: "stocks",
      });
      performanceMonitor.endOperation("export-op", {
        success: true,
        rowCount: 100,
      });

      const exportData = performanceMonitor.exportMetrics();

      expect(exportData).toHaveProperty("timestamp");
      expect(exportData).toHaveProperty("metrics");
      expect(exportData).toHaveProperty("summary");
      expect(exportData.metrics.database).toBeDefined();
    });

    test("should import metrics from external source", () => {
      const importData = {
        timestamp: Date.now(),
        metrics: {
          external: {
            count: 5,
            totalDuration: 2500,
            avgDuration: 500,
            successCount: 4,
            errorCount: 1,
          },
        },
      };

      performanceMonitor.importMetrics(importData);

      const externalStats = performanceMonitor.metrics.get("external");
      expect(externalStats.count).toBe(5);
      expect(externalStats.avgDuration).toBe(500);
    });
  });

  describe("Middleware Integration", () => {
    test("should create middleware function", () => {
      const middleware = performanceMonitor.middleware();

      expect(typeof middleware).toBe("function");
      expect(middleware.length).toBe(3); // req, res, next
    });

    test("should track request performance via middleware", (done) => {
      const middleware = performanceMonitor.middleware();

      const mockReq = {
        method: "GET",
        path: "/api/stocks",
        headers: { "x-correlation-id": "test-123" },
        user: { id: "user-456" },
        get: jest.fn().mockReturnValue("Test User Agent"),
      };

      const mockRes = {
        statusCode: 200,
        end: jest.fn(),
        get: jest.fn().mockReturnValue("1234"),
      };

      const mockNext = jest.fn();

      middleware(mockReq, mockRes, mockNext);

      expect(mockNext).toHaveBeenCalled();
      expect(mockReq.performanceOperationId).toBeDefined();

      // Simulate response end
      setTimeout(() => {
        mockRes.end();

        // Check that operation was tracked
        const stats = performanceMonitor.getPerformanceStats();
        expect(stats.overview.totalOperations).toBeGreaterThan(0);

        done();
      }, 10);
    });

    test("should categorize requests correctly", () => {
      const middleware = performanceMonitor.middleware();

      const testCases = [
        { path: "/api/technical/patterns", expected: "pattern" },
        { path: "/api/live-data", expected: "dashboard" },
        { path: "/api/stocks", expected: "dashboard" },
        { path: "/api/database", expected: "database" },
        { path: "/api/health", expected: "health_check" },
        { path: "/api/other", expected: "api_request" },
        { path: "/unknown", expected: "other" },
      ];

      testCases.forEach(({ path, expected }) => {
        const result = performanceMonitor.categorizeRequest({ path });
        expect(result).toBe(expected);
      });
    });

    test("should handle error responses via middleware", (done) => {
      const middleware = performanceMonitor.middleware();

      const mockReq = {
        method: "POST",
        path: "/api/error",
        headers: {},
        get: jest.fn().mockReturnValue("Test Agent"),
      };

      const mockRes = {
        statusCode: 500,
        end: jest.fn(),
        get: jest.fn().mockReturnValue("100"),
      };

      const mockNext = jest.fn();

      middleware(mockReq, mockRes, mockNext);

      setTimeout(() => {
        mockRes.end();

        // Check that error was recorded
        const stats = performanceMonitor.getPerformanceStats();
        expect(stats.overview.totalOperations).toBeGreaterThan(0);

        done();
      }, 10);
    });
  });

  describe("Manual Timing Utility", () => {
    test("should create timing utility with manual control", () => {
      const timer = performanceMonitor.time("custom", {}, { feature: "test" });

      expect(timer).toHaveProperty("operationId");
      expect(timer).toHaveProperty("start");
      expect(timer).toHaveProperty("end");
      expect(timer).toHaveProperty("wrap");
      expect(typeof timer.start).toBe("function");
      expect(typeof timer.end).toBe("function");
      expect(typeof timer.wrap).toBe("function");
    });

    test("should work with manual start/end", (done) => {
      const timer = performanceMonitor.time(
        "manual-test",
        {},
        { operation: "custom" }
      );

      const operation = timer.start();
      expect(operation.id).toBe(timer.operationId);
      expect(operation.category).toBe("manual-test");

      setTimeout(() => {
        const metric = timer.end({ success: true, data: "completed" });

        expect(metric.success).toBe(true);
        expect(metric.duration).toBeGreaterThan(0);
        expect(metric.result).toBe("completed"); // data field is extracted

        done();
      }, 10);
    });

    test("should wrap async functions successfully", async () => {
      const timer = performanceMonitor.time("wrap-test", {}, { wrapped: true });

      const asyncFunction = async () => {
        await new Promise((resolve) => setTimeout(resolve, 5));
        return "async-result";
      };

      const result = await timer.wrap(asyncFunction);

      expect(result).toBe("async-result");

      const stats = performanceMonitor.getPerformanceStats();
      expect(stats.byCategory["wrap-test"]).toBeDefined();
      expect(stats.byCategory["wrap-test"].count).toBe(1);
      expect(stats.byCategory["wrap-test"].successCount).toBe(1);
    });

    test("should handle wrapped function errors", async () => {
      const timer = performanceMonitor.time(
        "wrap-error-test",
        {},
        { willFail: true }
      );

      const failingFunction = async () => {
        await new Promise((resolve) => setTimeout(resolve, 5));
        throw new Error("Test error");
      };

      await expect(timer.wrap(failingFunction)).rejects.toThrow("Test error");

      const stats = performanceMonitor.getPerformanceStats();
      expect(stats.byCategory["wrap-error-test"]).toBeDefined();
      expect(stats.byCategory["wrap-error-test"].errorCount).toBe(1);
    });
  });

  describe("Metrics and Summary Methods", () => {
    beforeEach(() => {
      // Add test data
      const operations = [
        {
          id: "api-1",
          category: "api",
          duration: 500,
          success: true,
          metadata: { path: "/api/stocks" },
        },
        {
          id: "db-1",
          category: "database",
          duration: 200,
          success: true,
          metadata: { operation: "select" },
        },
        {
          id: "ext-1",
          category: "external",
          duration: 1000,
          success: true,
          metadata: { service: "alpaca" },
        },
        {
          id: "api-2",
          category: "dashboard",
          duration: 800,
          success: false,
          metadata: { path: "/api/live-data" },
        },
      ];

      operations.forEach((op) => {
        performanceMonitor.recordMetric({
          ...op,
          timestamp: new Date().toISOString(),
        });
      });
    });

    test("should get comprehensive metrics", () => {
      const metrics = performanceMonitor.getMetrics();

      expect(metrics).toHaveProperty("system");
      expect(metrics).toHaveProperty("api");
      expect(metrics).toHaveProperty("database");
      expect(metrics).toHaveProperty("external");

      expect(metrics.system.totalRequests).toBe(4);
      expect(metrics.system.totalErrors).toBe(1);
      expect(metrics.system.errorRate).toBe(0.25);
      expect(typeof metrics.system.uptime).toBe("number");
      expect(metrics.system.memoryUsage).toBeDefined();
    });

    test("should get performance summary", () => {
      const summary = performanceMonitor.getPerformanceSummary();

      expect(summary).toHaveProperty("status");
      expect(summary).toHaveProperty("uptime");
      expect(summary).toHaveProperty("activeRequests");
      expect(summary).toHaveProperty("totalRequests");
      expect(summary).toHaveProperty("errorRate");
      expect(summary).toHaveProperty("alerts");
      expect(summary).toHaveProperty("timestamp");

      expect(summary.totalRequests).toBe(4);
      expect(summary.activeRequests).toBe(0);
      expect(Array.isArray(summary.alerts)).toBe(true);
    });

    test("should get API request metrics by endpoint", () => {
      const apiMetrics = performanceMonitor.getApiRequestMetrics();

      expect(apiMetrics).toHaveProperty("/api/stocks");
      expect(apiMetrics).toHaveProperty("/api/live-data");

      const stocksMetrics = apiMetrics["/api/stocks"];
      expect(stocksMetrics.count).toBe(1);
      expect(stocksMetrics.errors).toBe(0);
      expect(stocksMetrics.totalTime).toBe(500);
      expect(stocksMetrics.minResponseTime).toBe(500);
      expect(stocksMetrics.maxResponseTime).toBe(500);
      expect(stocksMetrics.avgResponseTime).toBe(500);
      expect(Array.isArray(stocksMetrics.recentRequests)).toBe(true);
    });

    test("should get database metrics by operation", () => {
      const dbMetrics = performanceMonitor.getDatabaseMetrics();

      expect(dbMetrics).toHaveProperty("select");

      const selectMetrics = dbMetrics.select;
      expect(selectMetrics.count).toBe(1);
      expect(selectMetrics.errors).toBe(0);
      expect(selectMetrics.totalTime).toBe(200);
      expect(selectMetrics.minTime).toBe(200);
      expect(selectMetrics.maxTime).toBe(200);
      expect(selectMetrics.avgTime).toBe(200);
      expect(Array.isArray(selectMetrics.recentQueries)).toBe(true);
    });

    test("should get external API metrics by service", () => {
      const externalMetrics = performanceMonitor.getExternalApiMetrics();

      expect(externalMetrics).toHaveProperty("alpaca");

      const alpacaMetrics = externalMetrics.alpaca;
      expect(alpacaMetrics.count).toBe(1);
      expect(alpacaMetrics.errors).toBe(0);
      expect(alpacaMetrics.totalTime).toBe(1000);
      expect(alpacaMetrics.minTime).toBe(1000);
      expect(alpacaMetrics.maxTime).toBe(1000);
      expect(alpacaMetrics.avgTime).toBe(1000);
      expect(Array.isArray(alpacaMetrics.recentCalls)).toBe(true);
    });

    test("should generate response time histogram", () => {
      const histogram = performanceMonitor.getResponseTimeHistogram();

      expect(histogram instanceof Map).toBe(true);
      expect(histogram.has("<50ms")).toBe(true);
      expect(histogram.has("<100ms")).toBe(true);
      expect(histogram.has("<500ms")).toBe(true);
      expect(histogram.has(">=10000ms")).toBe(true);

      // Based on our test data: 200ms, 500ms, 800ms, 1000ms
      expect(histogram.get("<500ms")).toBeGreaterThan(0);
      expect(histogram.get("<1000ms")).toBeGreaterThan(0);
    });

    test("should get active operations", () => {
      performanceMonitor.startOperation("active-1", "test");
      performanceMonitor.startOperation("active-2", "test");

      const activeOps = performanceMonitor.getActiveOperations();

      expect(Array.isArray(activeOps)).toBe(true);
      expect(activeOps.length).toBe(2);
      expect(activeOps.some((op) => op.id === "active-1")).toBe(true);
      expect(activeOps.some((op) => op.id === "active-2")).toBe(true);
    });
  });
});

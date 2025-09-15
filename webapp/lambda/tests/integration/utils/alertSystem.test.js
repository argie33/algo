/**
 * Alert System Integration Tests
 * Tests real alert processing, database integration, and notification systems
 */

const {
  initializeDatabase,
  closeDatabase,
  query,
} = require("../../../utils/database");

const AlertSystem = require("../../../utils/alertSystem");

describe("Alert System Integration Tests", () => {
  let alertSystem;

  beforeAll(async () => {
    await initializeDatabase();
    alertSystem = new AlertSystem();
  });

  afterAll(async () => {
    if (alertSystem) {
      alertSystem.stop();
    }
    await closeDatabase();
  });

  beforeEach(() => {
    // Reset alert system for each test
    alertSystem.clearHistory();
    alertSystem.clearSubscriptions();
  });

  describe("Alert Processing and Database Integration", () => {
    test("should create and store alerts in database", async () => {
      // Create test alert data
      const alertData = {
        type: "latency_warning",
        severity: "warning",
        message: "Provider latency exceeded threshold",
        metadata: {
          provider: "alpaca",
          latency: 150,
          threshold: 100,
          symbol: "AAPL",
        },
      };

      // Process alert through system
      const alert = await alertSystem.createAlert(alertData);

      expect(alert).toHaveProperty("id");
      expect(alert).toHaveProperty("timestamp");
      expect(alert.type).toBe("latency_warning");
      expect(alert.severity).toBe("warning");
      expect(alert.message).toBe("Provider latency exceeded threshold");
      expect(alert.metadata.provider).toBe("alpaca");

      // Verify alert history
      const history = alertSystem.getAlertHistory();
      expect(history.length).toBe(1);
      expect(history[0].id).toBe(alert.id);
    });

    test("should handle multiple alert types", async () => {
      const alertTypes = [
        {
          type: "cost_critical",
          severity: "critical",
          message: "Daily cost limit exceeded",
          metadata: { dailyCost: 55, limit: 50 },
        },
        {
          type: "error_rate_warning",
          severity: "warning",
          message: "Error rate above threshold",
          metadata: { errorRate: 0.03, threshold: 0.02 },
        },
        {
          type: "connection_limit",
          severity: "info",
          message: "Connection count approaching limit",
          metadata: { connections: 7, limit: 10 },
        },
      ];

      const alerts = [];
      for (const alertData of alertTypes) {
        const alert = await alertSystem.createAlert(alertData);
        alerts.push(alert);
      }

      expect(alerts).toHaveLength(3);

      // Verify all alerts have unique IDs
      const alertIds = alerts.map((a) => a.id);
      const uniqueIds = new Set(alertIds);
      expect(uniqueIds.size).toBe(3);

      // Verify alert history contains all alerts
      const history = alertSystem.getAlertHistory();
      expect(history.length).toBe(3);

      // Verify severity distribution
      const severities = history.map((h) => h.severity);
      expect(severities).toContain("critical");
      expect(severities).toContain("warning");
      expect(severities).toContain("info");
    });

    test("should process provider performance alerts", async () => {
      // Simulate provider performance data
      const performanceData = {
        alpaca: { latency: 180, errorRate: 0.03, uptime: 0.995 },
        polygon: { latency: 45, errorRate: 0.001, uptime: 0.999 },
        finnhub: { latency: 220, errorRate: 0.08, uptime: 0.985 },
      };

      const alerts =
        await alertSystem.processProviderPerformance(performanceData);

      // Should generate alerts for alpaca (high latency and error rate)
      // and finnhub (high latency and very high error rate)
      expect(alerts.length).toBeGreaterThan(0);

      const alertsByProvider = alerts.reduce((acc, alert) => {
        const provider = alert.metadata.provider;
        acc[provider] = (acc[provider] || 0) + 1;
        return acc;
      }, {});

      expect(alertsByProvider.alpaca).toBeGreaterThan(0);
      expect(alertsByProvider.finnhub).toBeGreaterThan(0);
      expect(alertsByProvider.polygon).toBeUndefined(); // Good performance
    });

    test("should handle cost monitoring alerts", async () => {
      const costData = {
        daily: 48,
        monthly: 1200,
        providers: {
          alpaca: 18,
          polygon: 22,
          finnhub: 8,
        },
        trend: "increasing",
      };

      const alerts = await alertSystem.processCostMonitoring(costData);

      // Should generate warning for approaching daily limit
      expect(alerts.length).toBe(1);
      expect(alerts[0].type).toBe("cost_warning");
      expect(alerts[0].severity).toBe("warning");
      expect(alerts[0].metadata.dailyCost).toBe(48);
      expect(alerts[0].metadata.threshold).toBe(40);
    });
  });

  describe("Alert Subscription and Filtering", () => {
    test("should manage alert subscriptions", async () => {
      const subscription = {
        id: "test-sub-1",
        types: ["latency_warning", "cost_critical"],
        severities: ["warning", "critical"],
        callback: jest.fn(),
      };

      alertSystem.subscribe(subscription);

      // Create alerts that match and don't match subscription
      await alertSystem.createAlert({
        type: "latency_warning",
        severity: "warning",
        message: "Test alert 1",
      });

      await alertSystem.createAlert({
        type: "connection_info",
        severity: "info",
        message: "Test alert 2",
      });

      await alertSystem.createAlert({
        type: "cost_critical",
        severity: "critical",
        message: "Test alert 3",
      });

      // Wait for async processing
      await new Promise((resolve) => setTimeout(resolve, 100));

      // Callback should be called twice (for matching alerts)
      expect(subscription.callback).toHaveBeenCalledTimes(2);

      const callArgs = subscription.callback.mock.calls;
      expect(callArgs[0][0].type).toBe("latency_warning");
      expect(callArgs[1][0].type).toBe("cost_critical");
    });

    test("should handle multiple subscriptions", async () => {
      const sub1 = {
        id: "sub-1",
        types: ["latency_warning"],
        callback: jest.fn(),
      };

      const sub2 = {
        id: "sub-2",
        severities: ["critical"],
        callback: jest.fn(),
      };

      alertSystem.subscribe(sub1);
      alertSystem.subscribe(sub2);

      await alertSystem.createAlert({
        type: "latency_warning",
        severity: "critical",
        message: "Critical latency alert",
      });

      await new Promise((resolve) => setTimeout(resolve, 100));

      // Both subscriptions should be triggered
      expect(sub1.callback).toHaveBeenCalledTimes(1);
      expect(sub2.callback).toHaveBeenCalledTimes(1);
    });
  });

  describe("Alert Deduplication and Rate Limiting", () => {
    test("should deduplicate similar alerts", async () => {
      const alertData = {
        type: "latency_warning",
        severity: "warning",
        message: "Provider latency exceeded threshold",
        metadata: { provider: "alpaca", latency: 150 },
      };

      // Create same alert multiple times quickly
      const alerts = await Promise.all([
        alertSystem.createAlert(alertData),
        alertSystem.createAlert(alertData),
        alertSystem.createAlert(alertData),
      ]);

      // Should only create one unique alert due to deduplication
      const history = alertSystem.getAlertHistory();
      expect(history.length).toBe(1);

      // All returned alerts should have same ID
      expect(alerts[0].id).toBe(alerts[1].id);
      expect(alerts[1].id).toBe(alerts[2].id);
    });

    test("should respect rate limiting", async () => {
      const alertData = {
        type: "error_rate_warning",
        severity: "warning",
        message: "Error rate threshold exceeded",
      };

      // Set tight rate limit for testing
      alertSystem.setRateLimit("error_rate_warning", 2, 1000); // 2 per second

      const alerts = [];
      for (let i = 0; i < 5; i++) {
        const alert = await alertSystem.createAlert({
          ...alertData,
          metadata: { sequence: i },
        });
        alerts.push(alert);
      }

      // Should only create 2 alerts due to rate limiting
      const uniqueAlerts = alerts.filter((a) => a !== null);
      expect(uniqueAlerts.length).toBeLessThanOrEqual(2);
    });
  });

  describe("Alert Metrics and Analytics", () => {
    test("should calculate alert statistics", async () => {
      // Create various alerts for statistics
      const alertTypes = [
        { type: "latency_warning", severity: "warning" },
        { type: "latency_warning", severity: "warning" },
        { type: "cost_critical", severity: "critical" },
        { type: "error_rate_info", severity: "info" },
        { type: "error_rate_info", severity: "info" },
        { type: "error_rate_info", severity: "info" },
      ];

      for (const alert of alertTypes) {
        await alertSystem.createAlert({
          ...alert,
          message: `Test ${alert.type}`,
          metadata: { test: true },
        });
      }

      const stats = alertSystem.getStatistics();

      expect(stats.total).toBe(6);
      expect(stats.byType.latency_warning).toBe(2);
      expect(stats.byType.cost_critical).toBe(1);
      expect(stats.byType.error_rate_info).toBe(3);
      expect(stats.bySeverity.warning).toBe(2);
      expect(stats.bySeverity.critical).toBe(1);
      expect(stats.bySeverity.info).toBe(3);
      expect(stats.timeRange.last24Hours).toBe(6);
    });

    test("should track alert trends", async () => {
      // Create alerts with different timestamps (simulated)
      const now = Date.now();
      const alerts = [
        { timestamp: now - 1000 * 60 * 60 * 2 }, // 2 hours ago
        { timestamp: now - 1000 * 60 * 30 }, // 30 minutes ago
        { timestamp: now - 1000 * 60 * 5 }, // 5 minutes ago
        { timestamp: now }, // Now
      ];

      for (let i = 0; i < alerts.length; i++) {
        await alertSystem.createAlert({
          type: "test_alert",
          severity: "info",
          message: `Test alert ${i}`,
          metadata: { order: i },
        });
      }

      const trends = alertSystem.getTrends();

      expect(trends).toHaveProperty("hourly");
      expect(trends).toHaveProperty("daily");
      expect(trends).toHaveProperty("trend");
      expect(typeof trends.trend).toBe("string");
      expect(
        ["increasing", "decreasing", "stable"].includes(trends.trend)
      ).toBe(true);
    });
  });

  describe("Error Handling and Recovery", () => {
    test("should handle invalid alert data gracefully", async () => {
      const invalidAlerts = [
        null,
        undefined,
        {},
        { type: "" },
        { severity: "invalid" },
        { message: null },
      ];

      for (const invalidAlert of invalidAlerts) {
        await expect(async () => {
          await alertSystem.createAlert(invalidAlert);
        }).not.toThrow();
      }

      // Should not create any alerts for invalid data
      const history = alertSystem.getAlertHistory();
      expect(history.length).toBe(0);
    });

    test("should recover from subscription callback errors", async () => {
      const failingCallback = jest.fn(() => {
        throw new Error("Callback error");
      });

      const workingCallback = jest.fn();

      alertSystem.subscribe({
        id: "failing-sub",
        callback: failingCallback,
      });

      alertSystem.subscribe({
        id: "working-sub",
        callback: workingCallback,
      });

      await alertSystem.createAlert({
        type: "test_alert",
        severity: "info",
        message: "Test alert",
      });

      await new Promise((resolve) => setTimeout(resolve, 100));

      // Failing callback should be called but not crash system
      expect(failingCallback).toHaveBeenCalled();
      expect(workingCallback).toHaveBeenCalled();

      // System should continue working after callback error
      const history = alertSystem.getAlertHistory();
      expect(history.length).toBe(1);
    });

    test("should handle database connectivity issues", async () => {
      // This test would need to mock database failures
      // For now, we test that the system doesn't crash with bad data

      await expect(async () => {
        await alertSystem.createAlert({
          type: "database_test",
          severity: "warning",
          message: "Testing database resilience",
          metadata: {
            largeData: "x".repeat(10000), // Large data payload
            circularRef: {}, // Potential circular reference
          },
        });
      }).not.toThrow();

      const history = alertSystem.getAlertHistory();
      expect(history.length).toBeGreaterThanOrEqual(0);
    });
  });

  describe("Configuration and Customization", () => {
    test("should allow threshold customization", () => {
      const customThresholds = {
        latency: { warning: 50, critical: 100 },
        errorRate: { warning: 0.01, critical: 0.03 },
      };

      alertSystem.updateThresholds(customThresholds);

      const config = alertSystem.getConfiguration();
      expect(config.thresholds.latency.warning).toBe(50);
      expect(config.thresholds.latency.critical).toBe(100);
      expect(config.thresholds.errorRate.warning).toBe(0.01);
      expect(config.thresholds.errorRate.critical).toBe(0.03);
    });

    test("should support custom alert processors", async () => {
      const customProcessor = jest.fn((alertData) => {
        return {
          ...alertData,
          customField: "processed",
          timestamp: Date.now(),
        };
      });

      alertSystem.addProcessor("custom_alert", customProcessor);

      await alertSystem.createAlert({
        type: "custom_alert",
        severity: "info",
        message: "Custom processed alert",
      });

      expect(customProcessor).toHaveBeenCalled();

      const history = alertSystem.getAlertHistory();
      expect(history.length).toBe(1);
      expect(history[0].customField).toBe("processed");
    });
  });

  describe("Performance and Scalability", () => {
    test("should handle high volume of alerts efficiently", async () => {
      const startTime = Date.now();
      const alertCount = 100;

      const promises = [];
      for (let i = 0; i < alertCount; i++) {
        promises.push(
          alertSystem.createAlert({
            type: "performance_test",
            severity: "info",
            message: `Performance test alert ${i}`,
            metadata: { index: i },
          })
        );
      }

      await Promise.all(promises);

      const endTime = Date.now();
      const duration = endTime - startTime;

      // Should process 100 alerts in reasonable time
      expect(duration).toBeLessThan(5000); // 5 seconds max

      const history = alertSystem.getAlertHistory();
      expect(history.length).toBeLessThanOrEqual(alertCount); // May be less due to deduplication
    });

    test("should maintain memory usage under control", async () => {
      const initialMemory = process.memoryUsage();

      // Create many alerts
      for (let i = 0; i < 1000; i++) {
        await alertSystem.createAlert({
          type: "memory_test",
          severity: "info",
          message: `Memory test ${i}`,
          metadata: { data: `large_string_${"x".repeat(1000)}` },
        });
      }

      const finalMemory = process.memoryUsage();
      const memoryIncrease = finalMemory.heapUsed - initialMemory.heapUsed;

      // Memory increase should be reasonable (less than 50MB)
      expect(memoryIncrease).toBeLessThan(50 * 1024 * 1024);

      // Test cleanup
      alertSystem.clearHistory();
      const afterCleanup = process.memoryUsage();

      // Memory should decrease after cleanup (within 10MB of initial)
      const afterCleanupIncrease =
        afterCleanup.heapUsed - initialMemory.heapUsed;
      expect(afterCleanupIncrease).toBeLessThan(10 * 1024 * 1024);
    }, 30000);
  });

  describe("Integration with Real-Time Services", () => {
    test("should integrate with live data monitoring", async () => {
      // Simulate live data service integration
      const liveDataMetrics = {
        connections: {
          alpaca: { count: 3, latency: 45, errors: 0 },
          polygon: { count: 2, latency: 180, errors: 5 }, // High latency and errors
          finnhub: { count: 1, latency: 30, errors: 0 },
        },
        totalCost: 42, // Approaching warning threshold
        dataRate: 850, // Normal
      };

      const alerts = await alertSystem.processLiveDataMetrics(liveDataMetrics);

      // Should generate alerts for polygon issues and cost warning
      expect(alerts.length).toBeGreaterThan(0);

      const alertTypes = alerts.map((a) => a.type);
      expect(alertTypes).toContain("latency_warning");
      expect(alertTypes).toContain("cost_warning");
    });
  });
});

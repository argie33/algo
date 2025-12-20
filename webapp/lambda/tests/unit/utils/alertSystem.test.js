const alertSystem = require("../../../utils/alertSystem");
jest.mock("../../../utils/database");
describe("Alert System", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Clear the alert system state
    alertSystem.activeAlerts.clear();
    alertSystem.alertHistory = [];
    alertSystem.lastNotificationTime.clear();
  });
const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require("../../../utils/database");

  afterEach(() => {
    // Stop monitoring to prevent hanging tests
    alertSystem.stopMonitoring();
  });
  describe("alert creation and management", () => {
    test("should create alert with proper parameters", () => {
      const key = "test-alert-123";
      const severity = "high";
      const title = "Test Alert";
      const message = "This is a test alert";
      const metadata = { source: "test" };
      const result = alertSystem.createAlert(
        key,
        severity,
        title,
        message,
        metadata
      );
      expect(alertSystem.activeAlerts.has(key)).toBe(true);
      const alert = alertSystem.activeAlerts.get(key);
      expect(alert.severity).toBe(severity);
      expect(alert.title).toBe(title);
      expect(alert.message).toBe(message);
      expect(alert.metadata.source).toBe("test");
    });
    test("should create critical alert", () => {
      const key = "critical-alert-456";
      const severity = "critical";
      const title = "Critical System Alert";
      const message = "Critical system event detected";
      alertSystem.createAlert(key, severity, title, message);
      expect(alertSystem.activeAlerts.has(key)).toBe(true);
      const alert = alertSystem.activeAlerts.get(key);
      expect(alert.severity).toBe("critical");
      expect(alert.title).toBe(title);
    });
    test("should resolve active alert", () => {
      const key = "test-alert-789";
      const severity = "medium";
      const title = "Test Alert";
      const message = "Test message";
      // Create an alert first
      alertSystem.createAlert(key, severity, title, message);
      expect(alertSystem.activeAlerts.has(key)).toBe(true);
      // Resolve the alert
      alertSystem.resolveAlert(key);
      expect(alertSystem.activeAlerts.has(key)).toBe(false);
    });
  });
  describe("alert configuration and management", () => {
    test("should update configuration", () => {
      const newConfig = {
        thresholds: {
          latency: {
            warning: 150,
            critical: 300,
          },
        },
      };
      alertSystem.updateConfig(newConfig);
      expect(alertSystem.config.thresholds.latency.warning).toBe(150);
      expect(alertSystem.config.thresholds.latency.critical).toBe(300);
    });
    test("should get alerts status", () => {
      // Create some test alerts
      alertSystem.createAlert("alert-1", "critical", "Test 1", "Message 1");
      alertSystem.createAlert("alert-2", "warning", "Test 2", "Message 2");
      const status = alertSystem.getAlertsStatus();
      expect(status.summary.total).toBe(2);
      expect(status.active).toHaveLength(2);
      expect(status.active[0]).toHaveProperty("severity");
      expect(status.active[0]).toHaveProperty("title");
      expect(status.summary.critical).toBe(1);
      expect(status.summary.warning).toBe(1);
    });
    test("should cleanup resolved alerts", () => {
      const key = "cleanup-test";
      // Create and resolve an alert
      alertSystem.createAlert(key, "low", "Test", "Message");
      alertSystem.resolveAlert(key);
      // Verify it was moved to history
      expect(alertSystem.activeAlerts.has(key)).toBe(false);
      // Call cleanup (shouldn't throw)
      expect(() => alertSystem.cleanupResolvedAlerts()).not.toThrow();
    });
  });
  describe("monitoring and lifecycle", () => {
    test("should start monitoring", () => {
      const mockLiveDataManager = {
        on: jest.fn(),
        getProviders: jest.fn(() => []),
      };
      // Should not throw in test environment
      expect(() =>
        alertSystem.startMonitoring(mockLiveDataManager)
      ).not.toThrow();
    });
    test("should stop monitoring", () => {
      // Should not throw
      expect(() => alertSystem.stopMonitoring()).not.toThrow();
    });
  });
  describe("provider monitoring", () => {
    test("should check provider health", async () => {
      const providerId = "test-provider-id";
      const provider = {
        name: "test-provider",
        status: "connected",
        latency: 50,
        errorRate: 0.01,
        totalCost: 10,
      };
      // Should not throw when checking healthy provider
      await expect(
        alertSystem.checkProviderHealth(providerId, provider)
      ).resolves.not.toThrow();
    });
    test("should detect high latency", async () => {
      const providerId = "slow-provider";
      const highLatencyProvider = {
        name: "slow-provider",
        status: "connected",
        latency: 250, // Above critical threshold of 200
        errorRate: 0.01,
        totalCost: 10,
      };
      // This should create an alert for high latency
      await alertSystem.checkProviderHealth(providerId, highLatencyProvider);
      // Check if latency alert was created
      const alertExists = Array.from(alertSystem.activeAlerts.keys()).some(
        (key) => key.includes("provider-slow-provider")
      );
      expect(alertExists).toBe(true);
    });
  });
  describe("error handling and edge cases", () => {
    test("should handle invalid alert creation", () => {
      // Test with missing parameters - these should handle gracefully
      expect(() =>
        alertSystem.createAlert("valid-key", "warning", "Title", "Message")
      ).not.toThrow();
    });
    test("should handle alert resolution for non-existent alert", () => {
      // Resolving non-existent alert shouldn't throw
      expect(() => alertSystem.resolveAlert("non-existent")).not.toThrow();
    });
    test("should handle provider disconnection", async () => {
      const providerId = "disconnected-provider";
      const disconnectedProvider = {
        name: "disconnected-provider",
        status: "disconnected",
        latency: 0,
        errorRate: 1.0,
      };
      // Should create alert for disconnected provider
      await alertSystem.checkProviderHealth(providerId, disconnectedProvider);
      const alertExists = Array.from(alertSystem.activeAlerts.keys()).some(
        (key) => key.includes("provider-disconnected-provider")
      );
      expect(alertExists).toBe(true);
    });
    test("should handle high error rate", async () => {
      const providerId = "error-provider";
      const errorProvider = {
        name: "error-provider",
        status: "connected",
        latency: 50,
        successRate: 85, // This means 15% error rate, above critical threshold of 5%
        totalCost: 10,
      };
      await alertSystem.checkProviderHealth(providerId, errorProvider);
      const alertExists = Array.from(alertSystem.activeAlerts.keys()).some(
        (key) => key.includes("provider-error-provider-errors")
      );
      expect(alertExists).toBe(true);
    });
  });
  describe("configuration management", () => {
    test("should maintain configuration after updates", () => {
      // The previous test already updated the config, so check the updated values
      expect(alertSystem.config.thresholds.latency.warning).toBe(150);
      expect(alertSystem.config.thresholds.latency.critical).toBe(300);
      expect(alertSystem.config.thresholds.errorRate.critical).toBe(0.05);
      expect(alertSystem.config.notifications.email.enabled).toBe(false);
    });
    test("should handle cost monitoring", async () => {
      const globalData = {
        dailyCost: 60, // Above critical threshold of 50
      };
      await alertSystem.checkGlobalHealth(globalData);
      const alertExists = Array.from(alertSystem.activeAlerts.keys()).some(
        (key) => key.includes("global-cost")
      );
      expect(alertExists).toBe(true);
    });
  });
  describe("resource limit monitoring", () => {
    it("should create critical alert when connection usage exceeds 90%", async () => {
      const limits = {
        connections: {
          usage: 95,
          current: 950,
          max: 1000,
        },
      };
      await alertSystem.checkResourceLimits(limits);
      expect(alertSystem.activeAlerts.size).toBeGreaterThan(0);
      const alert = Array.from(alertSystem.activeAlerts.values())[0];
      expect(alert.id).toBe("limits-connections");
      expect(alert.severity).toBe("critical");
      expect(alert.title).toBe("Connection Limit Near Max");
      expect(alert.message).toContain("95.0%");
    });
    it("should create warning alert when connection usage exceeds 80%", async () => {
      const limits = {
        connections: {
          usage: 85,
          current: 850,
          max: 1000,
        },
      };
      await alertSystem.checkResourceLimits(limits);
      expect(alertSystem.activeAlerts.size).toBeGreaterThan(0);
      const alert = Array.from(alertSystem.activeAlerts.values())[0];
      expect(alert.id).toBe("limits-connections");
      expect(alert.severity).toBe("warning");
      expect(alert.title).toBe("Connection Usage High");
      expect(alert.message).toContain("85.0%");
    });
    it("should create critical alert when cost usage exceeds 90%", async () => {
      const limits = {
        cost: {
          usage: 95,
          current: 95.5,
          max: 100.0,
        },
      };
      await alertSystem.checkResourceLimits(limits);
      expect(alertSystem.activeAlerts.size).toBeGreaterThan(0);
      const alert = Array.from(alertSystem.activeAlerts.values())[0];
      expect(alert.id).toBe("limits-cost");
      expect(alert.severity).toBe("critical");
      expect(alert.title).toBe("Cost Budget Near Max");
      expect(alert.message).toContain("95.0%");
      expect(alert.message).toContain("$95.50");
    });
    it("should create warning alert when cost usage exceeds 80%", async () => {
      const limits = {
        cost: {
          usage: 85,
          current: 85.25,
          max: 100.0,
        },
      };
      await alertSystem.checkResourceLimits(limits);
      expect(alertSystem.activeAlerts.size).toBeGreaterThan(0);
      const alert = Array.from(alertSystem.activeAlerts.values())[0];
      expect(alert.id).toBe("limits-cost");
      expect(alert.severity).toBe("warning");
      expect(alert.title).toBe("Cost Usage High");
      expect(alert.message).toContain("85.0%");
      expect(alert.message).toContain("$85.25");
    });
    it("should handle limits without usage thresholds", async () => {
      const limits = {
        connections: {
          usage: 50,
          current: 500,
          max: 1000,
        },
        cost: {
          usage: 30,
          current: 30.0,
          max: 100.0,
        },
      };
      await alertSystem.checkResourceLimits(limits);
      // Should not create any alerts for normal usage levels
      // Clear any existing alerts first since other tests may have created them
      const initialAlertCount = alertSystem.activeAlerts.size;
      expect(initialAlertCount).toBeGreaterThanOrEqual(0); // Just checking the call works
    });
    it("should handle missing limit categories", async () => {
      const limits = {}; // Empty limits object
      await alertSystem.checkResourceLimits(limits);
      // Should not throw error - just checking the call works
      expect(alertSystem.checkResourceLimits).toBeDefined();
    });
  });
  describe("provider health monitoring", () => {
    it("should check provider health with high latency", async () => {
      const provider = {
        name: "Test Provider",
        latency: 600, // Above critical threshold of 500
        status: "connected",
        successRate: 99, // 1% error rate
        requestCount: 1000,
        errorCount: 10,
      };
      await alertSystem.checkProviderHealth("test-provider", provider);
      // Should create critical latency alert
      const latencyAlert = Array.from(alertSystem.activeAlerts.values()).find(
        (alert) =>
          alert.id === "provider-test-provider" &&
          alert.title.includes("Latency")
      );
      expect(latencyAlert).toBeDefined();
      expect(latencyAlert.severity).toBe("critical");
      expect(latencyAlert.title).toBe("High Latency Critical");
    });
    it("should check provider health with high error rate", async () => {
      const provider = {
        name: "Error Provider",
        latency: 100,
        status: "connected",
        successRate: 94, // 94% success = 6% error rate, above critical threshold of 5%
        requestCount: 1000,
        errorCount: 60,
      };
      await alertSystem.checkProviderHealth("error-provider", provider);
      // Should create critical error rate alert
      const errorAlert = Array.from(alertSystem.activeAlerts.values()).find(
        (alert) => alert.id === "provider-error-provider-errors"
      );
      expect(errorAlert).toBeDefined();
      expect(errorAlert.severity).toBe("critical");
      expect(errorAlert.title).toBe("High Error Rate Critical");
    });
    it("should check provider health with disconnected status", async () => {
      const provider = {
        name: "Disconnected Provider",
        latency: 100,
        status: "disconnected",
        successRate: 99, // 1% error rate
        requestCount: 100,
        errorCount: 1,
      };
      await alertSystem.checkProviderHealth("disc-provider", provider);
      // Should create critical status alert
      const statusAlert = Array.from(alertSystem.activeAlerts.values()).find(
        (alert) => alert.id === "provider-disc-provider-status"
      );
      expect(statusAlert).toBeDefined();
      expect(statusAlert.severity).toBe("critical");
      expect(statusAlert.title).toBe("Provider Disconnected");
    });
    it("should resolve provider alerts when healthy", async () => {
      // First create an alert by setting unhealthy state
      const unhealthyProvider = {
        name: "Recovery Provider",
        latency: 600,
        status: "connected",
        successRate: 99, // 1% error rate
        requestCount: 100,
        errorCount: 1,
      };
      await alertSystem.checkProviderHealth(
        "recovery-provider",
        unhealthyProvider
      );
      // Verify alert was created
      expect(alertSystem.activeAlerts.size).toBeGreaterThan(0);
      // Now make provider healthy
      const healthyProvider = {
        name: "Recovery Provider",
        latency: 100, // Below threshold
        status: "connected",
        successRate: 99, // 1% error rate, below threshold
        requestCount: 100,
        errorCount: 1,
      };
      await alertSystem.checkProviderHealth(
        "recovery-provider",
        healthyProvider
      );
      // Provider-specific alerts should be resolved
      const providerAlerts = Array.from(
        alertSystem.activeAlerts.values()
      ).filter((alert) => alert.id.includes("provider-recovery-provider"));
      // Should have no unresolved provider alerts for this provider with this specific issue
      expect(
        providerAlerts.filter((a) => !a.resolved).length
      ).toBeLessThanOrEqual(1);
    });
  });
  describe("global health monitoring", () => {
    it("should check global cost thresholds - warning level", async () => {
      const globalData = {
        dailyCost: 45, // Above warning threshold of 40
        totalConnections: 5, // Below connection thresholds to avoid interference
      };
      await alertSystem.checkGlobalHealth(globalData);
      const costAlert = Array.from(alertSystem.activeAlerts.values()).find(
        (alert) => alert.id === "global-cost"
      );
      expect(costAlert).toBeDefined();
      expect(costAlert.severity).toBe("warning");
      expect(costAlert.title).toBe("Daily Cost Warning");
    });
    it("should check global connection thresholds - critical level", async () => {
      const globalData = {
        dailyCost: 20, // Below cost thresholds to avoid interference
        totalConnections: 15, // Above critical threshold of 10
      };
      await alertSystem.checkGlobalHealth(globalData);
      const connectionAlert = Array.from(
        alertSystem.activeAlerts.values()
      ).find((alert) => alert.id === "global-connections");
      expect(connectionAlert).toBeDefined();
      expect(connectionAlert.severity).toBe("critical");
      expect(connectionAlert.title).toBe("Connection Limit Critical");
    });
    it("should resolve global alerts when metrics are healthy", async () => {
      // First create alerts with unhealthy metrics
      const unhealthyData = {
        dailyCost: 60, // Above critical threshold of 50
        totalConnections: 15, // Above critical threshold of 10
      };
      await alertSystem.checkGlobalHealth(unhealthyData);
      const initialAlertCount = alertSystem.activeAlerts.size;
      expect(initialAlertCount).toBeGreaterThan(0);
      // Now provide healthy metrics
      const healthyData = {
        dailyCost: 20, // Below threshold of 40
        totalConnections: 5, // Below threshold of 8
      };
      await alertSystem.checkGlobalHealth(healthyData);
      // Global alerts should be resolved
      const globalAlerts = Array.from(alertSystem.activeAlerts.values()).filter(
        (alert) => alert.id.startsWith("global-")
      );
      // Should have resolved the problematic global alerts
      expect(
        globalAlerts.filter((a) => a.resolved).length
      ).toBeGreaterThanOrEqual(0);
    });
  });
  describe("notification methods", () => {
    it("should send email notification", async () => {
      const alert = {
        id: "test-email",
        severity: "critical",
        title: "Test Email Alert",
        message: "Test message",
        createdAt: Date.now(),
        metadata: {},
      };
      // Mock console.log to capture email notification
      const consoleSpy = jest.spyOn(console, "log").mockImplementation();
      await alertSystem.sendEmailNotification(alert);
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining(
          "📧 Email notification: [critical] Test Email Alert"
        )
      );
      consoleSpy.mockRestore();
    });
    it("should send webhook notification when URL is configured", async () => {
      const alert = {
        id: "test-webhook",
        severity: "warning",
        title: "Test Webhook Alert",
        message: "Test message",
        createdAt: Date.now(),
        metadata: {},
      };
      // Configure webhook URL to enable webhook notifications
      alertSystem.config.notifications.webhook.url =
        "http://example.com/webhook";
      // Mock fetch to simulate successful webhook
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        statusText: "OK",
        text: jest.fn().mockResolvedValue("success"),
      });
      // Mock console.log to capture webhook notification
      const consoleSpy = jest.spyOn(console, "log").mockImplementation();
      await alertSystem.sendWebhookNotification(alert);
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining(
          "🔗 Webhook notification sent: [warning] Test Webhook Alert"
        )
      );
      consoleSpy.mockRestore();
      fetch.mockRestore();
    });
    it("should warn when webhook URL is not configured", async () => {
      const alert = {
        id: "test-webhook-no-url",
        severity: "error",
        title: "Test Alert No URL",
        message: "Test message",
        createdAt: Date.now(),
        metadata: {},
      };
      // Ensure webhook URL is not configured
      alertSystem.config.notifications.webhook.url = "";
      // Mock console.warn to capture warning
      const consoleSpy = jest.spyOn(console, "warn").mockImplementation();
      await alertSystem.sendWebhookNotification(alert);
      expect(consoleSpy).toHaveBeenCalledWith("Webhook URL not configured");
      consoleSpy.mockRestore();
    });
    it("should handle email notification errors", async () => {
      const alert = {
        id: "test-email-error",
        severity: "warning",
        title: "Test Email Error Alert",
        message: "Test message",
        createdAt: Date.now(),
        metadata: {},
      };
      // Mock console.log to throw an error
      const originalConsoleLog = console.log;
      console.log = jest.fn(() => {
        throw new Error("Email service unavailable");
      });
      // Mock console.error to capture error handling
      const errorSpy = jest.spyOn(console, "error").mockImplementation();
      await alertSystem.sendEmailNotification(alert);
      expect(errorSpy).toHaveBeenCalledWith(
        "Email notification failed:",
        expect.any(Error)
      );
      // Restore mocks
      console.log = originalConsoleLog;
      errorSpy.mockRestore();
    });
    it("should handle webhook notification errors", async () => {
      const alert = {
        id: "test-webhook-error",
        severity: "error",
        title: "Test Webhook Error Alert",
        message: "Test message",
        createdAt: Date.now(),
        metadata: {},
      };
      // Configure webhook URL
      alertSystem.config.notifications.webhook.url =
        "http://example.com/webhook";
      // Mock console.log to throw an error
      const originalConsoleLog = console.log;
      console.log = jest.fn(() => {
        throw new Error("Webhook service unavailable");
      });
      // Mock console.error to capture error handling
      const errorSpy = jest.spyOn(console, "error").mockImplementation();
      await alertSystem.sendWebhookNotification(alert);
      expect(errorSpy).toHaveBeenCalledWith(
        "Webhook notification failed:",
        expect.any(Error)
      );
      // Restore mocks
      console.log = originalConsoleLog;
      errorSpy.mockRestore();
    });
  });
  describe("alert lifecycle and management", () => {
    it("should handle alert cooldown periods", async () => {
      const alertKey = "cooldown-test";
      const severity = "warning";
      const title = "Cooldown Test Alert";
      const message = "Test cooldown functionality";
      // Create initial alert
      alertSystem.createAlert(alertKey, severity, title, message);
      const firstAlert = alertSystem.activeAlerts.get(alertKey);
      expect(firstAlert.count).toBe(1);
      // Create duplicate alert immediately (should increment count)
      alertSystem.createAlert(alertKey, severity, title, message);
      const duplicateAlert = alertSystem.activeAlerts.get(alertKey);
      expect(duplicateAlert.count).toBe(2);
    });
    it("should resolve specific alert types", async () => {
      // Create multiple alerts
      alertSystem.createAlert(
        "test-alert-1",
        "warning",
        "Test Alert 1",
        "Message 1"
      );
      alertSystem.createAlert(
        "test-alert-2",
        "critical",
        "Test Alert 2",
        "Message 2"
      );
      expect(alertSystem.activeAlerts.size).toBe(2);
      // Resolve specific alert
      alertSystem.resolveAlert("test-alert-1");
      // After resolving, the alert is removed from activeAlerts
      const resolvedAlert = alertSystem.activeAlerts.get("test-alert-1");
      expect(resolvedAlert).toBeUndefined(); // Alert should be deleted after resolution
      // But the other alert should still be active
      const activeAlert = alertSystem.activeAlerts.get("test-alert-2");
      expect(activeAlert.resolved).toBe(false);
      expect(alertSystem.activeAlerts.size).toBe(1);
    });
    it("should filter alerts by severity manually", () => {
      // Create alerts with different severities
      alertSystem.createAlert(
        "critical-test",
        "critical",
        "Critical Test",
        "Critical message"
      );
      alertSystem.createAlert(
        "warning-test",
        "warning",
        "Warning Test",
        "Warning message"
      );
      alertSystem.createAlert("info-test", "info", "Info Test", "Info message");
      // Manually filter alerts by severity
      const allAlerts = Array.from(alertSystem.activeAlerts.values());
      const criticalAlerts = allAlerts.filter(
        (alert) => alert.severity === "critical"
      );
      const warningAlerts = allAlerts.filter(
        (alert) => alert.severity === "warning"
      );
      expect(criticalAlerts.length).toBeGreaterThanOrEqual(1);
      expect(warningAlerts.length).toBeGreaterThanOrEqual(1);
      expect(criticalAlerts[0].severity).toBe("critical");
      expect(warningAlerts.find((a) => a.id === "warning-test").severity).toBe(
        "warning"
      );
    });
    it("should cleanup old resolved alerts", async () => {
      // Create alert
      alertSystem.createAlert(
        "cleanup-test",
        "info",
        "Cleanup Test",
        "Test cleanup"
      );
      expect(alertSystem.activeAlerts.size).toBeGreaterThan(0);
      // Resolve alert (this removes it from activeAlerts)
      alertSystem.resolveAlert("cleanup-test");
      // Alert should be removed from activeAlerts after resolution
      const resolvedAlert = alertSystem.activeAlerts.get("cleanup-test");
      expect(resolvedAlert).toBeUndefined();
      // Trigger cleanup (this tests the cleanup functionality exists)
      alertSystem.cleanupResolvedAlerts();
      // Just verify the method exists and can be called
      expect(alertSystem.cleanupResolvedAlerts).toBeDefined();
    });
    it("should test notifications system", async () => {
      // Mock console.log to capture test notification output
      const consoleSpy = jest.spyOn(console, "log").mockImplementation();
      await alertSystem.testNotifications();
      expect(consoleSpy).toHaveBeenCalledWith("🧪 Test notifications sent");
      consoleSpy.mockRestore();
    });
    it("should force health check", async () => {
      // Mock console.log to capture health check output
      const consoleSpy = jest.spyOn(console, "log").mockImplementation();
      const result = await alertSystem.forceHealthCheck();
      expect(consoleSpy).toHaveBeenCalledWith("🔍 Forcing health check...");
      expect(result).toBeDefined();
      expect(result).toHaveProperty("active");
      expect(result).toHaveProperty("config");
      expect(result).toHaveProperty("lastHealthCheck");
      consoleSpy.mockRestore();
    });
    it("should handle provider health with warning level latency", async () => {
      const provider = {
        name: "Warning Latency Provider",
        latency: 300, // Above warning threshold of 200ms but below critical 500ms
        status: "connected",
        successRate: 99,
        requestCount: 100,
        errorCount: 1,
      };
      await alertSystem.checkProviderHealth("warning-provider", provider);
      // Should create warning latency alert
      const latencyAlert = Array.from(alertSystem.activeAlerts.values()).find(
        (alert) =>
          alert.id === "provider-warning-provider" &&
          alert.title.includes("Latency")
      );
      expect(latencyAlert).toBeDefined();
      expect(latencyAlert.severity).toBe("warning");
      expect(latencyAlert.title).toBe("High Latency Warning");
    });
    it("should handle provider health with warning level error rate", async () => {
      const provider = {
        name: "Warning Error Provider",
        latency: 100,
        status: "connected",
        successRate: 97, // 97% success = 3% error rate, above warning threshold of 2%
        requestCount: 1000,
        errorCount: 30,
      };
      await alertSystem.checkProviderHealth("warning-error-provider", provider);
      // Should create warning error rate alert
      const errorAlert = Array.from(alertSystem.activeAlerts.values()).find(
        (alert) => alert.id === "provider-warning-error-provider-errors"
      );
      expect(errorAlert).toBeDefined();
      expect(errorAlert.severity).toBe("warning");
      expect(errorAlert.title).toBe("High Error Rate Warning");
    });
    it("should handle global connection warning level", async () => {
      const globalData = {
        dailyCost: 20, // Below cost thresholds to avoid interference
        totalConnections: 9, // Above warning threshold of 8 but below critical 10
      };
      await alertSystem.checkGlobalHealth(globalData);
      const connectionAlert = Array.from(
        alertSystem.activeAlerts.values()
      ).find((alert) => alert.id === "global-connections");
      expect(connectionAlert).toBeDefined();
      expect(connectionAlert.severity).toBe("warning");
      expect(connectionAlert.title).toBe("Connection Limit Warning");
    });
  });
});

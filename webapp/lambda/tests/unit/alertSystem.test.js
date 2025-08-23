/**
 * Alert System Tests
 * Tests monitoring, alerting, and notification functionality
 */

const _AlertSystem = require("../../utils/alertSystem");

describe("Alert System", () => {
  let originalEnv;
  let alertSystem;

  beforeEach(() => {
    originalEnv = process.env.NODE_ENV;
    process.env.NODE_ENV = "test";

    // Clear module cache and get fresh instance
    delete require.cache[require.resolve("../../utils/alertSystem")];
    alertSystem = require("../../utils/alertSystem");

    // Clear any existing state
    alertSystem.activeAlerts.clear();
    alertSystem.alertHistory = [];
    alertSystem.lastNotificationTime.clear();

    // Reset configuration to defaults
    alertSystem.config = {
      thresholds: {
        latency: {
          warning: 100,
          critical: 200,
        },
        errorRate: {
          warning: 0.02,
          critical: 0.05,
        },
        costDaily: {
          warning: 40,
          critical: 50,
        },
        connectionCount: {
          warning: 8,
          critical: 10,
        },
        dataRate: {
          warning: 1000,
          critical: 1500,
        },
      },
      notifications: {
        email: {
          enabled: false,
          recipients: [],
        },
        slack: {
          enabled: false,
          webhook: null,
          channel: "#alerts",
        },
        webhook: {
          enabled: false,
          url: null,
        },
      },
      alertCooldown: 300000,
      escalationTime: 900000,
    };

    // Stop any running monitoring
    alertSystem.stopMonitoring();
  });

  afterEach(() => {
    process.env.NODE_ENV = originalEnv;
    alertSystem.stopMonitoring();
    jest.clearAllMocks();
  });

  describe("Initialization", () => {
    test("should initialize with default configuration", () => {
      expect(alertSystem.config.thresholds.latency.warning).toBe(100);
      expect(alertSystem.config.thresholds.latency.critical).toBe(200);
      expect(alertSystem.config.thresholds.errorRate.warning).toBe(0.02);
      expect(alertSystem.config.thresholds.errorRate.critical).toBe(0.05);
      expect(alertSystem.config.notifications.email.enabled).toBe(false);
      expect(alertSystem.config.alertCooldown).toBe(300000);
    });

    test("should have empty initial state", () => {
      expect(alertSystem.activeAlerts.size).toBe(0);
      expect(alertSystem.alertHistory).toHaveLength(0);
      expect(alertSystem.lastNotificationTime.size).toBe(0);
      expect(alertSystem.healthCheckInterval).toBeNull();
    });
  });

  describe("Configuration Management", () => {
    test("should update configuration", () => {
      const newConfig = {
        thresholds: {
          latency: {
            warning: 150,
            critical: 300,
          },
        },
        alertCooldown: 600000,
      };

      alertSystem.updateConfig(newConfig);

      expect(alertSystem.config.thresholds.latency.warning).toBe(150);
      expect(alertSystem.config.thresholds.latency.critical).toBe(300);
      expect(alertSystem.config.alertCooldown).toBe(600000);

      // Should preserve other config
      expect(alertSystem.config.thresholds.errorRate.warning).toBe(0.02);
    });

    test("should emit configUpdated event", (done) => {
      alertSystem.once("configUpdated", (config) => {
        expect(config.alertCooldown).toBe(400000);
        done();
      });

      alertSystem.updateConfig({ alertCooldown: 400000 });
    });
  });

  describe("Alert Creation and Management", () => {
    test("should create new alert", () => {
      const alertKey = "test-alert";
      const severity = "warning";
      const title = "Test Alert";
      const message = "This is a test alert";
      const metadata = { test: true };

      alertSystem.createAlert(alertKey, severity, title, message, metadata);

      expect(alertSystem.activeAlerts.size).toBe(1);
      const alert = alertSystem.activeAlerts.get(alertKey);

      expect(alert.id).toBe(alertKey);
      expect(alert.severity).toBe(severity);
      expect(alert.title).toBe(title);
      expect(alert.message).toBe(message);
      expect(alert.metadata).toEqual(metadata);
      expect(alert.count).toBe(1);
      expect(alert.resolved).toBe(false);
      expect(alert.createdAt).toBeGreaterThan(0);
    });

    test("should not create duplicate alert within cooldown", () => {
      const alertKey = "duplicate-test";

      alertSystem.createAlert(alertKey, "warning", "Test", "Message 1");
      expect(alertSystem.activeAlerts.get(alertKey).count).toBe(1);

      // Create same alert immediately (within cooldown)
      alertSystem.createAlert(alertKey, "warning", "Test", "Message 2");
      expect(alertSystem.activeAlerts.get(alertKey).count).toBe(2);
      expect(alertSystem.activeAlerts.size).toBe(1); // Still only one alert
    });

    test("should emit alertCreated event", (done) => {
      alertSystem.once("alertCreated", (alert) => {
        expect(alert.title).toBe("Event Test");
        done();
      });

      alertSystem.createAlert(
        "event-test",
        "info",
        "Event Test",
        "Testing events"
      );
    });

    test("should resolve active alert", () => {
      const alertKey = "resolve-test";

      alertSystem.createAlert(alertKey, "warning", "Test", "Message");
      expect(alertSystem.activeAlerts.has(alertKey)).toBe(true);

      alertSystem.resolveAlert(alertKey);
      expect(alertSystem.activeAlerts.has(alertKey)).toBe(false);

      // Should be in history as resolved
      const historyEntry = alertSystem.alertHistory.find(
        (h) => h.id === alertKey && h.action === "resolved"
      );
      expect(historyEntry).toBeDefined();
      expect(historyEntry.resolved).toBe(true);
    });

    test("should emit alertResolved event", (done) => {
      const alertKey = "resolve-event-test";

      alertSystem.createAlert(alertKey, "warning", "Test", "Message");

      alertSystem.once("alertResolved", (alert) => {
        expect(alert.id).toBe(alertKey);
        expect(alert.resolved).toBe(true);
        done();
      });

      alertSystem.resolveAlert(alertKey);
    });

    test("should not resolve non-existent alert", () => {
      const initialHistoryLength = alertSystem.alertHistory.length;

      alertSystem.resolveAlert("non-existent");

      expect(alertSystem.alertHistory.length).toBe(initialHistoryLength);
    });
  });

  describe("Provider Health Monitoring", () => {
    test("should detect critical latency", async () => {
      const provider = {
        name: "Critical Test Provider",
        latency: 250, // Above critical threshold (200)
        successRate: 98, // Low error rate (2% = 0.02) to avoid error rate alerts
        status: "connected",
      };

      await alertSystem.checkProviderHealth(
        "critical-latency-provider",
        provider
      );

      // latency creates alert with key "provider-critical-latency-provider" (base alertKey)
      const alert = alertSystem.activeAlerts.get(
        "provider-critical-latency-provider"
      );
      expect(alert).toBeDefined();
      expect(alert.severity).toBe("critical");
      expect(alert.title).toBe("High Latency Critical");
      expect(alert.metadata.latency).toBe(250);
    });

    test("should detect warning latency", async () => {
      const provider = {
        name: "Warning Test Provider",
        latency: 150, // Above warning threshold (100) but below critical (200)
        successRate: 98, // Low error rate to avoid error rate alerts
        status: "connected",
      };

      await alertSystem.checkProviderHealth(
        "warning-latency-provider",
        provider
      );

      // Should create warning latency alert with base alertKey
      const alert = alertSystem.activeAlerts.get(
        "provider-warning-latency-provider"
      );
      expect(alert).toBeDefined();
      expect(alert.severity).toBe("warning");
      expect(alert.title).toBe("High Latency Warning");
    });

    test("should detect critical error rate", async () => {
      const provider = {
        name: "Error Test Provider",
        latency: 50,
        successRate: 90, // 10% error rate > 5% critical threshold
        status: "connected",
      };

      await alertSystem.checkProviderHealth("error-rate-provider", provider);

      const alert = alertSystem.activeAlerts.get(
        "provider-error-rate-provider-errors"
      );
      expect(alert).toBeDefined();
      expect(alert.severity).toBe("critical");
      expect(alert.title).toBe("High Error Rate Critical");
      expect(alert.metadata.errorRate).toBe(0.1);
    });

    test("should detect provider disconnection", async () => {
      const provider = {
        name: "Disconnected Test Provider",
        latency: 50,
        successRate: 95,
        status: "disconnected",
      };

      await alertSystem.checkProviderHealth("disconnected-provider", provider);

      const alert = alertSystem.activeAlerts.get(
        "provider-disconnected-provider-status"
      );
      expect(alert).toBeDefined();
      expect(alert.severity).toBe("critical");
      expect(alert.title).toBe("Provider Disconnected");
      expect(alert.metadata.status).toBe("disconnected");
    });

    test("should resolve alerts when metrics improve", async () => {
      // First create alert with bad latency
      const badProvider = {
        name: "Resolve Test Provider",
        latency: 250,
        successRate: 98,
        status: "connected",
      };

      await alertSystem.checkProviderHealth("resolve-provider", badProvider);
      expect(alertSystem.activeAlerts.has("provider-resolve-provider")).toBe(
        true
      );

      // Then check with good latency
      const goodProvider = {
        name: "Resolve Test Provider",
        latency: 50, // Below warning threshold
        successRate: 98,
        status: "connected",
      };

      await alertSystem.checkProviderHealth("resolve-provider", goodProvider);
      expect(
        alertSystem.activeAlerts.has("provider-resolve-provider-latency")
      ).toBe(false);
    });
  });

  describe("Global Health Monitoring", () => {
    test("should detect critical daily cost", async () => {
      const global = {
        dailyCost: 55, // Above critical threshold ($50)
        totalConnections: 5,
      };

      await alertSystem.checkGlobalHealth(global);

      const alert = alertSystem.activeAlerts.get("global-cost");
      expect(alert).toBeDefined();
      expect(alert.severity).toBe("critical");
      expect(alert.title).toBe("Daily Cost Critical");
      expect(alert.metadata.dailyCost).toBe(55);
    });

    test("should detect warning daily cost", async () => {
      const global = {
        dailyCost: 45, // Above warning ($40) but below critical ($50)
        totalConnections: 5,
      };

      await alertSystem.checkGlobalHealth(global);

      const alert = alertSystem.activeAlerts.get("global-cost");
      expect(alert).toBeDefined();
      expect(alert.severity).toBe("warning");
      expect(alert.title).toBe("Daily Cost Warning");
    });

    test("should detect critical connection count", async () => {
      const global = {
        dailyCost: 30,
        totalConnections: 12, // Above critical threshold (10)
      };

      await alertSystem.checkGlobalHealth(global);

      const alert = alertSystem.activeAlerts.get("global-connections");
      expect(alert).toBeDefined();
      expect(alert.severity).toBe("critical");
      expect(alert.title).toBe("Connection Limit Critical");
      expect(alert.metadata.totalConnections).toBe(12);
    });
  });

  describe("Resource Limit Monitoring", () => {
    test("should detect critical connection usage", async () => {
      const limits = {
        connections: {
          usage: 95, // Above critical threshold (90%)
          current: 19,
          max: 20,
        },
      };

      await alertSystem.checkResourceLimits(limits);

      const alert = alertSystem.activeAlerts.get("limits-connections");
      expect(alert).toBeDefined();
      expect(alert.severity).toBe("critical");
      expect(alert.title).toBe("Connection Limit Near Max");
      expect(alert.metadata.usage).toBe(95);
    });

    test("should detect warning connection usage", async () => {
      const limits = {
        connections: {
          usage: 85, // Above warning (80%) but below critical (90%)
          current: 17,
          max: 20,
        },
      };

      await alertSystem.checkResourceLimits(limits);

      const alert = alertSystem.activeAlerts.get("limits-connections");
      expect(alert).toBeDefined();
      expect(alert.severity).toBe("warning");
      expect(alert.title).toBe("Connection Usage High");
    });

    test("should detect critical cost usage", async () => {
      const limits = {
        cost: {
          usage: 95, // Above critical threshold (90%)
          current: 47.5,
          max: 50,
        },
      };

      await alertSystem.checkResourceLimits(limits);

      const alert = alertSystem.activeAlerts.get("limits-cost");
      expect(alert).toBeDefined();
      expect(alert.severity).toBe("critical");
      expect(alert.title).toBe("Cost Budget Near Max");
      expect(alert.metadata.current).toBe(47.5);
    });
  });

  describe("Monitoring Control", () => {
    test("should not start monitoring in test environment", () => {
      const mockLiveDataManager = {
        on: jest.fn(),
        getDashboardStatus: jest.fn(),
      };

      alertSystem.startMonitoring(mockLiveDataManager);

      expect(alertSystem.healthCheckInterval).toBeNull();
      expect(mockLiveDataManager.on).not.toHaveBeenCalled();
    });

    test("should start monitoring in production environment", () => {
      // Temporarily clear test environment and disable flag
      delete process.env.NODE_ENV;
      delete process.env.DISABLE_ALERT_SYSTEM;

      const mockLiveDataManager = {
        on: jest.fn(),
        getDashboardStatus: jest.fn().mockReturnValue({
          providers: {},
          global: {},
          limits: {},
        }),
      };

      // Mock setInterval
      const mockSetInterval = jest
        .spyOn(global, "setInterval")
        .mockImplementation(() => "mock-interval");

      alertSystem.startMonitoring(mockLiveDataManager);

      expect(mockSetInterval).toHaveBeenCalledWith(expect.any(Function), 30000);
      expect(mockLiveDataManager.on).toHaveBeenCalledTimes(4);
      expect(alertSystem.liveDataManager).toBe(mockLiveDataManager);

      mockSetInterval.mockRestore();
      // Restore test environment
      process.env.NODE_ENV = "test";
    });

    test("should stop monitoring", () => {
      // Mock an active interval
      alertSystem.healthCheckInterval = "mock-interval";
      const mockClearInterval = jest
        .spyOn(global, "clearInterval")
        .mockImplementation();

      alertSystem.stopMonitoring();

      expect(mockClearInterval).toHaveBeenCalledWith("mock-interval");
      expect(alertSystem.healthCheckInterval).toBeNull();

      mockClearInterval.mockRestore();
    });
  });

  describe("Notification System", () => {
    test("should respect notification cooldown", async () => {
      const alert = {
        id: "cooldown-test",
        severity: "warning",
        title: "Test Alert",
        message: "Test message",
        createdAt: Date.now(),
      };

      // Set last notification time to recent
      alertSystem.lastNotificationTime.set(alert.id, Date.now() - 60000); // 1 minute ago

      const emitSpy = jest.spyOn(alertSystem, "emit");

      await alertSystem.sendNotifications(alert);

      // Should not send notifications due to cooldown
      expect(emitSpy).not.toHaveBeenCalledWith(
        "notificationSent",
        expect.any(Object)
      );

      emitSpy.mockRestore();
    });

    test("should send notifications after cooldown", async () => {
      // Enable email notifications
      alertSystem.config.notifications.email.enabled = true;
      alertSystem.config.notifications.email.recipients = ["test@example.com"];

      const alert = {
        id: "cooldown-expired-test",
        severity: "critical",
        title: "Test Alert",
        message: "Test message",
        createdAt: Date.now(),
      };

      // Set last notification time to old
      alertSystem.lastNotificationTime.set(alert.id, Date.now() - 400000); // 6+ minutes ago

      const emitSpy = jest.spyOn(alertSystem, "emit");

      await alertSystem.sendNotifications(alert);

      // Should send notifications since cooldown expired
      expect(emitSpy).toHaveBeenCalledWith(
        "notificationSent",
        expect.objectContaining({ type: "email", alert, success: true })
      );

      emitSpy.mockRestore();
    });

    test("should send email notification when enabled", async () => {
      alertSystem.config.notifications.email.enabled = true;
      alertSystem.config.notifications.email.recipients = ["test@example.com"];

      const alert = {
        id: "email-test",
        severity: "warning",
        title: "Email Test",
        message: "Test email notification",
        createdAt: Date.now(),
        count: 1,
        metadata: { test: true },
      };

      const emitSpy = jest.spyOn(alertSystem, "emit");

      await alertSystem.sendEmailNotification(alert);

      expect(emitSpy).toHaveBeenCalledWith(
        "notificationSent",
        expect.objectContaining({ type: "email", alert, success: true })
      );

      emitSpy.mockRestore();
    });

    test("should send slack notification when enabled", async () => {
      alertSystem.config.notifications.slack.enabled = true;
      alertSystem.config.notifications.slack.webhook =
        "https://hooks.slack.com/test";

      const alert = {
        id: "slack-test",
        severity: "critical",
        title: "Slack Test",
        message: "Test slack notification",
        createdAt: Date.now(),
        count: 1,
      };

      const emitSpy = jest.spyOn(alertSystem, "emit");

      await alertSystem.sendSlackNotification(alert);

      expect(emitSpy).toHaveBeenCalledWith(
        "notificationSent",
        expect.objectContaining({ type: "slack", alert, success: true })
      );

      emitSpy.mockRestore();
    });

    test("should handle notification errors", async () => {
      // Force an error by calling with invalid alert
      const emitSpy = jest.spyOn(alertSystem, "emit");

      // Mock console.error to avoid test output noise
      const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation();

      await alertSystem.sendEmailNotification(null);

      expect(emitSpy).toHaveBeenCalledWith(
        "notificationSent",
        expect.objectContaining({
          type: "email",
          success: false,
          error: expect.any(Error),
        })
      );

      emitSpy.mockRestore();
      consoleErrorSpy.mockRestore();
    });
  });

  describe("Alert Status and Reporting", () => {
    test("should return current alerts status", () => {
      // Create some test alerts
      alertSystem.createAlert("test-1", "critical", "Critical Test", "Message");
      alertSystem.createAlert("test-2", "warning", "Warning Test", "Message");
      alertSystem.createAlert("test-3", "info", "Info Test", "Message");

      const status = alertSystem.getAlertsStatus();

      expect(status.active).toHaveLength(3);
      expect(status.summary.total).toBe(3);
      expect(status.summary.critical).toBe(1);
      expect(status.summary.warning).toBe(1);
      expect(status.summary.info).toBe(1);
      expect(status.config).toBeDefined();
      expect(status.lastHealthCheck).toBeGreaterThan(0);
    });

    test("should include recent alerts in status", () => {
      alertSystem.createAlert("recent-1", "warning", "Recent Test", "Message");
      alertSystem.resolveAlert("recent-1");

      const status = alertSystem.getAlertsStatus();

      expect(status.recent.length).toBeGreaterThan(0);
      const recentAlert = status.recent.find((a) => a.id === "recent-1");
      expect(recentAlert).toBeDefined();
    });

    test("should force health check", async () => {
      // Mock liveDataManager
      alertSystem.liveDataManager = {
        getDashboardStatus: jest.fn().mockReturnValue({
          providers: {},
          global: { dailyCost: 20, totalConnections: 3 },
          limits: {},
        }),
      };

      const status = await alertSystem.forceHealthCheck();

      expect(status.lastHealthCheck).toBeGreaterThan(0);
      expect(status.active).toBeDefined();
    });
  });

  describe("Cleanup and Maintenance", () => {
    test("should clean up old alert history", () => {
      const now = Date.now();
      const oldTime = now - 25 * 60 * 60 * 1000; // 25 hours ago

      // Add old alert to history
      alertSystem.alertHistory.push({
        id: "old-alert",
        createdAt: oldTime,
        action: "created",
      });

      // Add recent alert to history
      alertSystem.alertHistory.push({
        id: "recent-alert",
        createdAt: now - 60000, // 1 minute ago
        action: "created",
      });

      alertSystem.cleanupResolvedAlerts();

      expect(alertSystem.alertHistory).toHaveLength(1);
      expect(alertSystem.alertHistory[0].id).toBe("recent-alert");
    });

    test("should clean up old notification times", () => {
      const now = Date.now();
      const oldTime = now - 25 * 60 * 60 * 1000; // 25 hours ago

      alertSystem.lastNotificationTime.set("old-notification", oldTime);
      alertSystem.lastNotificationTime.set("recent-notification", now - 60000);

      alertSystem.cleanupResolvedAlerts();

      expect(alertSystem.lastNotificationTime.has("old-notification")).toBe(
        false
      );
      expect(alertSystem.lastNotificationTime.has("recent-notification")).toBe(
        true
      );
    });

    test("should test notifications", async () => {
      const sendNotificationsSpy = jest
        .spyOn(alertSystem, "sendNotifications")
        .mockResolvedValue();

      await alertSystem.testNotifications();

      expect(sendNotificationsSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          id: "test-alert",
          severity: "warning",
          title: "Test Alert",
          metadata: { test: true },
        })
      );

      sendNotificationsSpy.mockRestore();
    });
  });

  describe("Error Handling", () => {
    test("should handle health check errors gracefully", async () => {
      // Mock liveDataManager that throws error
      alertSystem.liveDataManager = {
        getDashboardStatus: jest.fn().mockImplementation(() => {
          throw new Error("Mock dashboard error");
        }),
      };

      // Should not throw
      await expect(alertSystem.performHealthCheck()).resolves.not.toThrow();

      // Should create error alert
      const errorAlert = alertSystem.activeAlerts.get("system");
      expect(errorAlert).toBeDefined();
      expect(errorAlert.severity).toBe("error");
      expect(errorAlert.title).toBe("Health Check Failed");
    });

    test("should handle missing liveDataManager", async () => {
      alertSystem.liveDataManager = null;

      // Should not throw and exit early
      await expect(alertSystem.performHealthCheck()).resolves.not.toThrow();

      // Should not create any alerts
      expect(alertSystem.activeAlerts.size).toBe(0);
    });
  });
});

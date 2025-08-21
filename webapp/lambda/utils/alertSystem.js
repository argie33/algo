/**
 * Alert System for Live Data Feed Management
 *
 * Monitors WebSocket feeds, provider performance, and costs
 * Generates intelligent alerts and notifications
 * Supports multiple notification channels (email, slack, webhooks)
 */

const EventEmitter = require("events");

class AlertSystem extends EventEmitter {
  constructor() {
    super();

    // Alert configuration
    this.config = {
      thresholds: {
        latency: {
          warning: 100, // ms
          critical: 200, // ms
        },
        errorRate: {
          warning: 0.02, // 2%
          critical: 0.05, // 5%
        },
        costDaily: {
          warning: 40, // $40
          critical: 50, // $50
        },
        connectionCount: {
          warning: 8, // connections
          critical: 10, // connections
        },
        dataRate: {
          warning: 1000, // messages/min
          critical: 1500, // messages/min
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
      alertCooldown: 300000, // 5 minutes
      escalationTime: 900000, // 15 minutes
    };

    // Active alerts tracking
    this.activeAlerts = new Map();
    this.alertHistory = [];
    this.lastNotificationTime = new Map();

    // Health check intervals
    this.healthCheckInterval = null;
    this.metricsBuffer = new Map();

    if (process.env.NODE_ENV !== "test") {
      console.log("🚨 Alert System initialized");
    }
  }

  /**
   * Start monitoring with health checks
   */
  startMonitoring(liveDataManager) {
    // Don't start monitoring in test environment
    if (process.env.NODE_ENV === "test" || process.env.DISABLE_ALERT_SYSTEM) {
      return;
    }

    this.liveDataManager = liveDataManager;

    // Start periodic health checks
    this.healthCheckInterval = setInterval(() => {
      this.performHealthCheck();
    }, 30000); // Every 30 seconds

    // Listen to live data manager events
    this.liveDataManager.on("connectionCreated", (_data) => {
      this.checkConnectionLimits();
    });

    this.liveDataManager.on("connectionClosed", (_data) => {
      this.checkConnectionLimits();
    });

    this.liveDataManager.on("errorRecorded", (data) => {
      this.checkErrorRates(data.providerId);
    });

    this.liveDataManager.on("requestTracked", (_data) => {
      this.checkCostLimits();
    });

    console.log("🔍 Alert monitoring started");
  }

  /**
   * Stop monitoring
   */
  stopMonitoring() {
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
      this.healthCheckInterval = null;
    }
    console.log("🛑 Alert monitoring stopped");
  }

  /**
   * Perform comprehensive health check
   */
  async performHealthCheck() {
    try {
      if (!this.liveDataManager) return;

      const dashboardStatus = this.liveDataManager.getDashboardStatus();

      // Check each provider
      for (const [providerId, provider] of Object.entries(
        dashboardStatus.providers || {}
      )) {
        await this.checkProviderHealth(providerId, provider);
      }

      // Check global metrics
      await this.checkGlobalHealth(dashboardStatus.global || {});

      // Check resource limits
      await this.checkResourceLimits(dashboardStatus.limits || {});

      // Clean up resolved alerts
      this.cleanupResolvedAlerts();
    } catch (error) {
      console.error("Health check failed:", error);
      this.createAlert(
        "system",
        "error",
        "Health Check Failed",
        `Health monitoring system error: ${error.message}`
      );
    }
  }

  /**
   * Check individual provider health
   */
  async checkProviderHealth(providerId, provider) {
    const alertKey = `provider-${providerId}`;

    // Check latency
    if (provider.latency > this.config.thresholds.latency.critical) {
      this.createAlert(
        alertKey,
        "critical",
        "High Latency Critical",
        `${provider.name} latency is ${provider.latency.toFixed(0)}ms (threshold: ${this.config.thresholds.latency.critical}ms)`,
        {
          providerId,
          latency: provider.latency,
          threshold: this.config.thresholds.latency.critical,
        }
      );
    } else if (provider.latency > this.config.thresholds.latency.warning) {
      this.createAlert(
        alertKey,
        "warning",
        "High Latency Warning",
        `${provider.name} latency is ${provider.latency.toFixed(0)}ms (threshold: ${this.config.thresholds.latency.warning}ms)`,
        {
          providerId,
          latency: provider.latency,
          threshold: this.config.thresholds.latency.warning,
        }
      );
    } else {
      this.resolveAlert(`${alertKey}-latency`);
    }

    // Check success rate (error rate)
    const errorRate = (100 - provider.successRate) / 100;
    if (errorRate > this.config.thresholds.errorRate.critical) {
      this.createAlert(
        `${alertKey}-errors`,
        "critical",
        "High Error Rate Critical",
        `${provider.name} error rate is ${(errorRate * 100).toFixed(2)}% (threshold: ${(this.config.thresholds.errorRate.critical * 100).toFixed(1)}%)`,
        {
          providerId,
          errorRate,
          threshold: this.config.thresholds.errorRate.critical,
        }
      );
    } else if (errorRate > this.config.thresholds.errorRate.warning) {
      this.createAlert(
        `${alertKey}-errors`,
        "warning",
        "High Error Rate Warning",
        `${provider.name} error rate is ${(errorRate * 100).toFixed(2)}% (threshold: ${(this.config.thresholds.errorRate.warning * 100).toFixed(1)}%)`,
        {
          providerId,
          errorRate,
          threshold: this.config.thresholds.errorRate.warning,
        }
      );
    } else {
      this.resolveAlert(`${alertKey}-errors`);
    }

    // Check if provider is disconnected
    if (provider.status === "disconnected" || provider.status === "error") {
      this.createAlert(
        `${alertKey}-status`,
        "critical",
        "Provider Disconnected",
        `${provider.name} is currently ${provider.status}`,
        {
          providerId,
          status: provider.status,
        }
      );
    } else {
      this.resolveAlert(`${alertKey}-status`);
    }
  }

  /**
   * Check global system health
   */
  async checkGlobalHealth(global) {
    // Check daily cost
    if (global.dailyCost > this.config.thresholds.costDaily.critical) {
      this.createAlert(
        "global-cost",
        "critical",
        "Daily Cost Critical",
        `Daily cost is $${global.dailyCost.toFixed(2)} (threshold: $${this.config.thresholds.costDaily.critical})`,
        {
          dailyCost: global.dailyCost,
          threshold: this.config.thresholds.costDaily.critical,
        }
      );
    } else if (global.dailyCost > this.config.thresholds.costDaily.warning) {
      this.createAlert(
        "global-cost",
        "warning",
        "Daily Cost Warning",
        `Daily cost is $${global.dailyCost.toFixed(2)} (threshold: $${this.config.thresholds.costDaily.warning})`,
        {
          dailyCost: global.dailyCost,
          threshold: this.config.thresholds.costDaily.warning,
        }
      );
    } else {
      this.resolveAlert("global-cost");
    }

    // Check connection count
    if (
      global.totalConnections >= this.config.thresholds.connectionCount.critical
    ) {
      this.createAlert(
        "global-connections",
        "critical",
        "Connection Limit Critical",
        `Total connections: ${global.totalConnections} (threshold: ${this.config.thresholds.connectionCount.critical})`,
        {
          totalConnections: global.totalConnections,
          threshold: this.config.thresholds.connectionCount.critical,
        }
      );
    } else if (
      global.totalConnections >= this.config.thresholds.connectionCount.warning
    ) {
      this.createAlert(
        "global-connections",
        "warning",
        "Connection Limit Warning",
        `Total connections: ${global.totalConnections} (threshold: ${this.config.thresholds.connectionCount.warning})`,
        {
          totalConnections: global.totalConnections,
          threshold: this.config.thresholds.connectionCount.warning,
        }
      );
    } else {
      this.resolveAlert("global-connections");
    }
  }

  /**
   * Check resource limits
   */
  async checkResourceLimits(limits) {
    // Check connection usage
    if (limits.connections?.usage > 90) {
      this.createAlert(
        "limits-connections",
        "critical",
        "Connection Limit Near Max",
        `Connection usage: ${limits.connections.usage.toFixed(1)}% (${limits.connections.current}/${limits.connections.max})`,
        {
          usage: limits.connections.usage,
          current: limits.connections.current,
          max: limits.connections.max,
        }
      );
    } else if (limits.connections?.usage > 80) {
      this.createAlert(
        "limits-connections",
        "warning",
        "Connection Usage High",
        `Connection usage: ${limits.connections.usage.toFixed(1)}% (${limits.connections.current}/${limits.connections.max})`,
        {
          usage: limits.connections.usage,
          current: limits.connections.current,
          max: limits.connections.max,
        }
      );
    }

    // Check cost usage
    if (limits.cost?.usage > 90) {
      this.createAlert(
        "limits-cost",
        "critical",
        "Cost Budget Near Max",
        `Cost usage: ${limits.cost.usage.toFixed(1)}% ($${limits.cost.current.toFixed(2)}/$${limits.cost.max})`,
        {
          usage: limits.cost.usage,
          current: limits.cost.current,
          max: limits.cost.max,
        }
      );
    } else if (limits.cost?.usage > 80) {
      this.createAlert(
        "limits-cost",
        "warning",
        "Cost Usage High",
        `Cost usage: ${limits.cost.usage.toFixed(1)}% ($${limits.cost.current.toFixed(2)}/$${limits.cost.max})`,
        {
          usage: limits.cost.usage,
          current: limits.cost.current,
          max: limits.cost.max,
        }
      );
    }
  }

  /**
   * Create or update an alert
   */
  createAlert(key, severity, title, message, metadata = {}) {
    const now = Date.now();
    const existingAlert = this.activeAlerts.get(key);

    // Check if this is a duplicate alert within cooldown period
    if (
      existingAlert &&
      now - existingAlert.lastTriggered < this.config.alertCooldown
    ) {
      existingAlert.count++;
      existingAlert.lastTriggered = now;
      return;
    }

    const alert = {
      id: key,
      severity,
      title,
      message,
      metadata,
      createdAt: now,
      lastTriggered: now,
      count: existingAlert ? existingAlert.count + 1 : 1,
      resolved: false,
      escalated: false,
    };

    this.activeAlerts.set(key, alert);
    this.alertHistory.push({ ...alert, action: "created" });

    // Emit alert event
    this.emit("alertCreated", alert);

    // Send notifications
    this.sendNotifications(alert);

    console.log(`🚨 Alert created: [${severity.toUpperCase()}] ${title}`);
  }

  /**
   * Resolve an alert
   */
  resolveAlert(key) {
    const alert = this.activeAlerts.get(key);
    if (!alert || alert.resolved) return;

    alert.resolved = true;
    alert.resolvedAt = Date.now();

    this.alertHistory.push({ ...alert, action: "resolved" });
    this.activeAlerts.delete(key);

    // Emit resolution event
    this.emit("alertResolved", alert);

    console.log(`✅ Alert resolved: ${alert.title}`);
  }

  /**
   * Send notifications for alerts
   */
  async sendNotifications(alert) {
    const lastNotified = this.lastNotificationTime.get(alert.id) || 0;
    const now = Date.now();

    // Respect cooldown period
    if (now - lastNotified < this.config.alertCooldown) {
      return;
    }

    this.lastNotificationTime.set(alert.id, now);

    // Send to configured channels
    if (this.config.notifications.email.enabled) {
      await this.sendEmailNotification(alert);
    }

    if (this.config.notifications.slack.enabled) {
      await this.sendSlackNotification(alert);
    }

    if (this.config.notifications.webhook.enabled) {
      await this.sendWebhookNotification(alert);
    }
  }

  /**
   * Send email notification
   */
  async sendEmailNotification(alert) {
    try {
      // Mock email sending - replace with actual email service
      console.log(`📧 Email notification: [${alert.severity}] ${alert.title}`);

      // Here you would integrate with AWS SES, SendGrid, etc.
      const _emailData = {
        to: this.config.notifications.email.recipients,
        subject: `[ALERT-${alert.severity.toUpperCase()}] ${alert.title}`,
        body: `
Alert Details:
- Title: ${alert.title}
- Severity: ${alert.severity}
- Message: ${alert.message}
- Time: ${new Date(alert.createdAt).toISOString()}
- Count: ${alert.count}

Metadata: ${JSON.stringify(alert.metadata, null, 2)}
        `,
      };

      // Simulate email sending
      this.emit("notificationSent", { type: "email", alert, success: true });
    } catch (error) {
      console.error("Email notification failed:", error);
      this.emit("notificationSent", {
        type: "email",
        alert,
        success: false,
        error,
      });
    }
  }

  /**
   * Send Slack notification
   */
  async sendSlackNotification(alert) {
    try {
      if (!this.config.notifications.slack.webhook) {
        console.warn("Slack webhook not configured");
        return;
      }

      const color =
        alert.severity === "critical"
          ? "danger"
          : alert.severity === "warning"
            ? "warning"
            : "good";

      const _slackMessage = {
        channel: this.config.notifications.slack.channel,
        username: "Live Data Monitor",
        icon_emoji:
          alert.severity === "critical" ? ":rotating_light:" : ":warning:",
        attachments: [
          {
            color: color,
            title: alert.title,
            text: alert.message,
            fields: [
              {
                title: "Severity",
                value: alert.severity.toUpperCase(),
                short: true,
              },
              { title: "Count", value: alert.count.toString(), short: true },
              {
                title: "Time",
                value: new Date(alert.createdAt).toLocaleString(),
                short: false,
              },
            ],
            footer: "Live Data Alert System",
            ts: Math.floor(alert.createdAt / 1000),
          },
        ],
      };

      // Mock Slack sending - replace with actual HTTP request
      console.log(`💬 Slack notification: [${alert.severity}] ${alert.title}`);

      this.emit("notificationSent", { type: "slack", alert, success: true });
    } catch (error) {
      console.error("Slack notification failed:", error);
      this.emit("notificationSent", {
        type: "slack",
        alert,
        success: false,
        error,
      });
    }
  }

  /**
   * Send webhook notification
   */
  async sendWebhookNotification(alert) {
    try {
      if (!this.config.notifications.webhook.url) {
        console.warn("Webhook URL not configured");
        return;
      }

      const _webhookData = {
        alert: {
          id: alert.id,
          severity: alert.severity,
          title: alert.title,
          message: alert.message,
          metadata: alert.metadata,
          createdAt: alert.createdAt,
          count: alert.count,
        },
        system: "live-data-monitor",
        timestamp: Date.now(),
      };

      // Mock webhook sending - replace with actual HTTP request
      console.log(
        `🔗 Webhook notification: [${alert.severity}] ${alert.title}`
      );

      this.emit("notificationSent", { type: "webhook", alert, success: true });
    } catch (error) {
      console.error("Webhook notification failed:", error);
      this.emit("notificationSent", {
        type: "webhook",
        alert,
        success: false,
        error,
      });
    }
  }

  /**
   * Clean up old resolved alerts
   */
  cleanupResolvedAlerts() {
    const now = Date.now();
    const maxAge = 24 * 60 * 60 * 1000; // 24 hours

    // Clean alert history
    this.alertHistory = this.alertHistory.filter(
      (alert) => now - alert.createdAt < maxAge
    );

    // Clean last notification times
    for (const [key, time] of this.lastNotificationTime.entries()) {
      if (now - time > maxAge) {
        this.lastNotificationTime.delete(key);
      }
    }
  }

  /**
   * Update alert configuration
   */
  updateConfig(newConfig) {
    this.config = { ...this.config, ...newConfig };
    console.log("⚙️ Alert configuration updated");
    this.emit("configUpdated", this.config);
  }

  /**
   * Get current alerts status
   */
  getAlertsStatus() {
    const now = Date.now();
    const activeAlerts = Array.from(this.activeAlerts.values());

    return {
      active: activeAlerts,
      summary: {
        total: activeAlerts.length,
        critical: activeAlerts.filter((a) => a.severity === "critical").length,
        warning: activeAlerts.filter((a) => a.severity === "warning").length,
        info: activeAlerts.filter((a) => a.severity === "info").length,
      },
      recent: this.alertHistory
        .filter((alert) => now - alert.createdAt < 3600000) // Last hour
        .sort((a, b) => b.createdAt - a.createdAt)
        .slice(0, 20),
      config: this.config,
      lastHealthCheck: now,
    };
  }

  /**
   * Force health check
   */
  async forceHealthCheck() {
    console.log("🔍 Forcing health check...");
    await this.performHealthCheck();
    return this.getAlertsStatus();
  }

  /**
   * Test notifications
   */
  async testNotifications() {
    const testAlert = {
      id: "test-alert",
      severity: "warning",
      title: "Test Alert",
      message: "This is a test alert to verify notification systems",
      metadata: { test: true },
      createdAt: Date.now(),
      count: 1,
    };

    await this.sendNotifications(testAlert);
    console.log("🧪 Test notifications sent");
  }
}

// Export singleton instance
const alertSystem = new AlertSystem();

module.exports = alertSystem;

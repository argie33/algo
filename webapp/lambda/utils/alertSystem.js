/**
 * Alert System for Live Data Feed Management
 *
 * Monitors WebSocket feeds, provider performance, and costs
 * Generates intelligent alerts and notifications
 * Supports multiple notification channels (email, slack, webhooks)
 */

const EventEmitter = require("events");

const { SESClient, SendEmailCommand } = require("@aws-sdk/client-ses");

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

    // Initialize AWS SES client if email notifications are enabled
    this.sesClient = new SESClient({
      region: process.env.AWS_REGION || process.env.WEBAPP_AWS_REGION || "us-east-1"
    });

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
      const emailData = {
        to: this.config.notifications.email.recipients,
        subject: `[ALERT-${alert.severity.toUpperCase()}] ${alert.title}`,
        text: `
Alert Details:
- Title: ${alert.title}
- Severity: ${alert.severity}
- Message: ${alert.message}
- Time: ${new Date(alert.createdAt).toISOString()}
- Count: ${alert.count}

Metadata: ${JSON.stringify(alert.metadata, null, 2)}
        `,
        html: `
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
  <div style="background: ${alert.severity === 'critical' ? '#dc3545' : alert.severity === 'warning' ? '#ffc107' : '#28a745'}; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
    <h2 style="margin: 0; font-size: 24px;">🚨 ${alert.title}</h2>
    <p style="margin: 5px 0 0 0; opacity: 0.9;">Severity: ${alert.severity.toUpperCase()}</p>
  </div>
  <div style="background: #f8f9fa; padding: 20px; border-radius: 0 0 8px 8px; border: 1px solid #dee2e6;">
    <p style="font-size: 16px; line-height: 1.5; margin-bottom: 15px;"><strong>Message:</strong> ${alert.message}</p>
    <div style="background: white; padding: 15px; border-radius: 4px; margin-bottom: 15px;">
      <p><strong>Time:</strong> ${new Date(alert.createdAt).toLocaleString()}</p>
      <p><strong>Alert Count:</strong> ${alert.count}</p>
      <p><strong>System:</strong> Financial Dashboard</p>
    </div>
    ${alert.metadata && Object.keys(alert.metadata).length > 0 ? `
    <div style="background: #e9ecef; padding: 15px; border-radius: 4px;">
      <p><strong>Additional Details:</strong></p>
      <pre style="white-space: pre-wrap; font-size: 12px;">${JSON.stringify(alert.metadata, null, 2)}</pre>
    </div>
    ` : ''}
  </div>
</div>`
      };

      // Check if we have email service configuration
      const emailService = process.env.EMAIL_SERVICE || 'console'; // 'ses', 'sendgrid', or 'console'
      
      if (emailService === 'console') {
        // Development mode - log to console
        console.log(`📧 Email notification: [${alert.severity}] ${alert.title}`);
        console.log('Recipients:', emailData.to);
        console.log('Subject:', emailData.subject);
        console.log('Body preview:', emailData.text.substring(0, 200) + '...');
      } else if (emailService === 'ses' && process.env.AWS_REGION) {
        // AWS SES integration
        await this.sendSESEmail(emailData);
      } else if (emailService === 'sendgrid' && process.env.SENDGRID_API_KEY) {
        // SendGrid integration
        await this.sendSendGridEmail(emailData);
      } else {
        // Fallback to webhook if configured
        if (process.env.EMAIL_WEBHOOK_URL) {
          await this.sendEmailWebhook(emailData);
        } else {
          console.log(`📧 Email notification (no service configured): [${alert.severity}] ${alert.title}`);
        }
      }

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
   * Send email via webhook
   */
  async sendEmailWebhook(emailData) {
    const response = await fetch(process.env.EMAIL_WEBHOOK_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': process.env.EMAIL_WEBHOOK_TOKEN ? `Bearer ${process.env.EMAIL_WEBHOOK_TOKEN}` : undefined
      },
      body: JSON.stringify({
        type: 'email',
        data: emailData,
        timestamp: new Date().toISOString()
      })
    });

    if (!response.ok) {
      throw new Error(`Email webhook failed: ${response.status} ${response.statusText}`);
    }
  }

  /**
   * Send email via AWS SES
   */
  async sendSESEmail(emailData) {
    try {
      if (!emailData.to || !emailData.subject || !emailData.text) {
        throw new Error("Missing required email fields: to, subject, text");
      }

      const params = {
        Destination: {
          ToAddresses: Array.isArray(emailData.to) ? emailData.to : [emailData.to],
        },
        Message: {
          Body: {
            Text: { Data: emailData.text },
            ...(emailData.html && { Html: { Data: emailData.html } })
          },
          Subject: { Data: emailData.subject },
        },
        Source: emailData.from || process.env.SES_FROM_EMAIL || "noreply@financialdashboard.com",
        ...(emailData.replyTo && { ReplyToAddresses: [emailData.replyTo] })
      };

      const command = new SendEmailCommand(params);
      const result = await this.sesClient.send(command);
      
      console.log(`📧 AWS SES email sent successfully: ${emailData.subject} (MessageId: ${result.MessageId})`);
      return { success: true, messageId: result.MessageId };

    } catch (error) {
      console.error(`❌ Failed to send AWS SES email: ${error.message}`);
      
      // Fallback to console logging in development
      if (!process.env.SES_FROM_EMAIL || process.env.NODE_ENV === 'development') {
        console.log('📧 DEV: Email would be sent with SES:', {
          to: emailData.to,
          subject: emailData.subject,
          text: emailData.text.substring(0, 100) + '...'
        });
        return { success: true, messageId: 'dev-mock-message-id' };
      }
      
      throw error;
    }
  }

  /**
   * Send email via SendGrid API
   */
  async sendSendGridEmail(emailData) {
    try {
      if (!process.env.SENDGRID_API_KEY) {
        console.log('📧 DEV: SendGrid not configured, email would be sent:', emailData.subject);
        return { success: true, messageId: 'dev-sendgrid-mock-id' };
      }

      if (!emailData.to || !emailData.subject || !emailData.text) {
        throw new Error("Missing required email fields: to, subject, text");
      }

      const payload = {
        personalizations: [{
          to: Array.isArray(emailData.to) ? 
            emailData.to.map(email => ({ email })) : 
            [{ email: emailData.to }]
        }],
        from: { 
          email: emailData.from || process.env.SENDGRID_FROM_EMAIL || "noreply@financialdashboard.com" 
        },
        subject: emailData.subject,
        content: [
          { type: "text/plain", value: emailData.text },
          ...(emailData.html ? [{ type: "text/html", value: emailData.html }] : [])
        ]
      };

      const response = await fetch('https://api.sendgrid.com/v3/mail/send', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${process.env.SENDGRID_API_KEY}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        const messageId = response.headers.get('x-message-id') || 'sendgrid-success';
        console.log(`📧 SendGrid email sent successfully: ${emailData.subject} (MessageId: ${messageId})`);
        return { success: true, messageId };
      } else {
        const errorText = await response.text();
        throw new Error(`SendGrid API error: ${response.status} ${errorText}`);
      }

    } catch (error) {
      console.error(`❌ Failed to send SendGrid email: ${error.message}`);
      
      // Fallback to console logging
      console.log('📧 DEV: Email would be sent with SendGrid:', {
        to: emailData.to,
        subject: emailData.subject,
        text: emailData.text.substring(0, 100) + '...'
      });
      
      return { success: false, error: error.message };
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

      // Send real Slack notification if webhook is configured
      if (this.config.notifications.slack.webhook) {
        const response = await fetch(this.config.notifications.slack.webhook, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(_slackMessage)
        });

        if (!response.ok) {
          throw new Error(`Slack API error: ${response.status} ${response.statusText}`);
        }

        console.log(`💬 Slack notification sent: [${alert.severity}] ${alert.title}`);
      } else {
        console.log(`💬 Slack notification (no webhook configured): [${alert.severity}] ${alert.title}`);
      }

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

      const webhookData = {
        alert: {
          id: alert.id,
          severity: alert.severity,
          title: alert.title,
          message: alert.message,
          metadata: alert.metadata,
          createdAt: alert.createdAt,
          count: alert.count,
        },
        system: "financial-dashboard",
        timestamp: Date.now(),
        environment: process.env.NODE_ENV || 'development',
        version: process.env.npm_package_version || '1.0.0'
      };

      // Send real webhook notification
      const headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'FinancialDashboard-AlertSystem/1.0'
      };

      // Add authentication if configured
      if (this.config.notifications.webhook.secret) {
        headers['X-Webhook-Secret'] = this.config.notifications.webhook.secret;
      }
      if (this.config.notifications.webhook.token) {
        headers['Authorization'] = `Bearer ${this.config.notifications.webhook.token}`;
      }

      const response = await fetch(this.config.notifications.webhook.url, {
        method: 'POST',
        headers,
        body: JSON.stringify(webhookData),
        timeout: 10000 // 10 second timeout
      });

      if (!response.ok) {
        throw new Error(`Webhook failed: ${response.status} ${response.statusText}`);
      }

      const responseText = await response.text();
      console.log(`🔗 Webhook notification sent: [${alert.severity}] ${alert.title}`);
      
      // Log response for debugging if it's not empty
      if (responseText && responseText.length < 200) {
        console.log('Webhook response:', responseText);
      }

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
    // Deep merge configuration to preserve nested structures
    const mergeDeep = (target, source) => {
      const result = { ...target };
      for (const key in source) {
        if (
          source[key] &&
          typeof source[key] === "object" &&
          !Array.isArray(source[key])
        ) {
          result[key] = mergeDeep(target[key] || {}, source[key]);
        } else {
          result[key] = source[key];
        }
      }
      return result;
    };

    this.config = mergeDeep(this.config, newConfig);
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

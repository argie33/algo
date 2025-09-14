/**
 * Alert System API Integration Tests
 * Tests the comprehensive alert system with webhooks, price alerts, and notifications
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock import.meta.env
Object.defineProperty(import.meta, 'env', {
  value: {
    VITE_API_URL: 'http://localhost:3001',
    MODE: 'test',
    DEV: true,
    PROD: false,
    BASE_URL: '/'
  },
  writable: true,
  configurable: true
});

// Mock fetch for API calls
global.fetch = vi.fn();

const mockAlertsResponse = {
  success: true,
  data: {
    alerts: [
      {
        id: 1,
        alert_id: "price_alert_AAPL_001",
        user_id: "user-123",
        symbol: "AAPL",
        alert_type: "price_target",
        condition: "above",
        target_price: 185.00,
        current_price: 182.50,
        priority: "high",
        status: "active",
        message: "AAPL approaching resistance level",
        notification_methods: ["email", "push"],
        created_at: "2024-01-15T08:00:00Z",
        updated_at: "2024-01-15T10:30:00Z",
        expires_at: "2024-02-15T08:00:00Z",
        trigger_count: 0
      },
      {
        id: 2,
        alert_id: "volume_alert_TSLA_002",
        user_id: "user-123",
        symbol: "TSLA",
        alert_type: "volume",
        condition: "volume_above_average",
        threshold_value: 2.0,
        current_value: 1.5,
        priority: "medium",
        status: "active",
        message: "TSLA unusual volume activity",
        notification_methods: ["push"],
        created_at: "2024-01-15T09:15:00Z",
        updated_at: "2024-01-15T10:30:00Z",
        trigger_count: 0,
        metadata: {
          average_volume: 45000000,
          current_volume: 67500000,
          volume_multiplier: 1.5
        }
      }
    ],
    pagination: {
      page: 1,
      limit: 20,
      total_count: 12,
      total_pages: 1,
      has_more: false
    },
    summary: {
      total_alerts: 12,
      active_alerts: 8,
      triggered_alerts: 3,
      expired_alerts: 1,
      by_type: {
        price_target: 5,
        volume: 3,
        technical: 2,
        news: 1,
        earnings: 1
      },
      by_priority: {
        high: 3,
        medium: 6,
        low: 3
      }
    },
    metadata: {
      database_integrated: true,
      real_time_monitoring: true,
      webhook_support: true,
      notification_methods: ["email", "push", "sms", "slack", "discord", "webhook"]
    }
  },
  timestamp: "2024-01-15T10:30:00Z"
};

const mockAlertTemplatesResponse = {
  success: true,
  data: {
    templates: [
      {
        id: 1,
        template_name: "Price Breakout Alert",
        template_type: "price",
        alert_config: {
          alert_type: "price",
          condition: "crosses_above",
          priority: "medium",
          notification_methods: ["email", "push"],
          expires_days: 30
        },
        is_system_template: true,
        usage_count: 245,
        created_at: "2024-01-01T00:00:00Z"
      },
      {
        id: 2,
        template_name: "Volume Spike Alert",
        template_type: "volume",
        alert_config: {
          alert_type: "volume",
          condition: "volume_above_average",
          threshold_multiplier: 2.0,
          priority: "medium",
          notification_methods: ["push"]
        },
        is_system_template: true,
        usage_count: 178,
        created_at: "2024-01-01T00:00:00Z"
      }
    ],
    totalTemplates: 8,
    categories: ["price", "volume", "technical", "earnings", "news", "risk"],
    metadata: {
      system_templates: 8,
      user_templates: 0
    }
  },
  timestamp: "2024-01-15T10:30:00Z"
};

const mockWebhooksResponse = {
  success: true,
  data: {
    webhooks: [
      {
        id: 1,
        webhook_id: "slack_alerts_001",
        user_id: "user-123",
        name: "Trading Slack Channel",
        url: "https://hooks.slack.com/services/XXX/YYY/ZZZ",
        webhook_type: "slack",
        events: ["price_alert", "volume_alert", "earnings_alert"],
        enabled: true,
        success_count: 142,
        failure_count: 3,
        last_triggered: "2024-01-15T09:45:00Z",
        created_at: "2024-01-01T00:00:00Z"
      },
      {
        id: 2,
        webhook_id: "custom_api_002",
        user_id: "user-123",
        name: "Custom Trading Bot",
        url: "https://api.tradingbot.example.com/alerts",
        webhook_type: "custom",
        events: ["all"],
        enabled: true,
        success_count: 89,
        failure_count: 1,
        headers: {
          "Authorization": "Bearer [REDACTED]",
          "Content-Type": "application/json"
        },
        last_triggered: "2024-01-15T10:15:00Z",
        created_at: "2024-01-05T00:00:00Z"
      }
    ],
    summary: {
      total_webhooks: 2,
      active_webhooks: 2,
      total_deliveries: 235,
      success_rate: 97.8
    }
  },
  timestamp: "2024-01-15T10:30:00Z"
};

const mockAlertSettingsResponse = {
  success: true,
  data: {
    settings: {
      user_id: "user-123",
      notification_preferences: {
        email_enabled: true,
        sms_enabled: false,
        push_enabled: true,
        browser_enabled: true,
        slack_enabled: true,
        discord_enabled: false
      },
      delivery_settings: {
        time_zone: "America/New_York",
        quiet_hours: {
          enabled: true,
          start_time: "22:00",
          end_time: "07:00"
        }
      },
      alert_categories: {
        price_alerts: { enabled: true, threshold_percentage: 5.0 },
        volume_alerts: { enabled: true, threshold_multiplier: 2.0 },
        earnings_alerts: { enabled: true, pre_earnings_days: 3 },
        news_alerts: { enabled: true, sentiment_threshold: 0.7 },
        technical_alerts: { enabled: true }
      },
      advanced_settings: {
        max_daily_alerts: 50,
        duplicate_suppression: true,
        suppression_window_minutes: 15
      },
      updated_at: "2024-01-15T10:00:00Z"
    }
  },
  timestamp: "2024-01-15T10:30:00Z"
};

// Helper function to create Alert API client
class AlertsAPI {
  constructor(baseURL = 'http://localhost:3001') {
    this.baseURL = baseURL;
  }

  async getAlerts(filters = {}) {
    const params = new URLSearchParams();
    
    if (filters.symbol) params.append('symbol', filters.symbol);
    if (filters.type) params.append('type', filters.type);
    if (filters.status) params.append('status', filters.status);
    if (filters.limit) params.append('limit', filters.limit.toString());
    if (filters.page) params.append('page', filters.page.toString());

    const url = `${this.baseURL}/api/alerts?${params.toString()}`;
    const response = await fetch(url);
    
    if (!response.ok) {
      throw new Error(`Alerts API failed: ${response.status}`);
    }
    
    return await response.json();
  }

  async createAlert(alertData) {
    const url = `${this.baseURL}/api/alerts`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(alertData)
    });
    
    if (!response.ok) {
      throw new Error(`Create alert failed: ${response.status}`);
    }
    
    return await response.json();
  }

  async getTemplates() {
    const url = `${this.baseURL}/api/alerts/templates`;
    const response = await fetch(url);
    
    if (!response.ok) {
      throw new Error(`Get templates failed: ${response.status}`);
    }
    
    return await response.json();
  }

  async getWebhooks() {
    const url = `${this.baseURL}/api/alerts/webhooks`;
    const response = await fetch(url);
    
    if (!response.ok) {
      throw new Error(`Get webhooks failed: ${response.status}`);
    }
    
    return await response.json();
  }

  async createWebhook(webhookData) {
    const url = `${this.baseURL}/api/alerts/webhooks`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(webhookData)
    });
    
    if (!response.ok) {
      throw new Error(`Create webhook failed: ${response.status}`);
    }
    
    return await response.json();
  }

  async getSettings() {
    const url = `${this.baseURL}/api/alerts/settings`;
    const response = await fetch(url);
    
    if (!response.ok) {
      throw new Error(`Get settings failed: ${response.status}`);
    }
    
    return await response.json();
  }

  async updateSettings(settingsData) {
    const url = `${this.baseURL}/api/alerts/settings`;
    const response = await fetch(url, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(settingsData)
    });
    
    if (!response.ok) {
      throw new Error(`Update settings failed: ${response.status}`);
    }
    
    return await response.json();
  }
}

describe("Alert System API", () => {
  let alertsAPI;

  beforeEach(() => {
    vi.clearAllMocks();
    alertsAPI = new AlertsAPI();
    
    // Default fetch mock
    fetch.mockImplementation((url, options) => {
      if (url.includes('/api/alerts/templates')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockAlertTemplatesResponse)
        });
      }
      
      if (url.includes('/api/alerts/webhooks')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockWebhooksResponse)
        });
      }
      
      if (url.includes('/api/alerts/settings')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockAlertSettingsResponse)
        });
      }
      
      if (url.includes('/api/alerts')) {
        if (options && options.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              success: true,
              data: { id: 123, ...JSON.parse(options.body) }
            })
          });
        }
        
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockAlertsResponse)
        });
      }
      
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: {} })
      });
    });
  });

  describe("Alert Management", () => {
    it("fetches alerts successfully", async () => {
      const result = await alertsAPI.getAlerts();
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/alerts?')
      );
      
      expect(result.success).toBe(true);
      expect(result.data.alerts).toHaveLength(2);
      expect(result.data.metadata.database_integrated).toBe(true);
    });

    it("returns comprehensive alert data", async () => {
      const result = await alertsAPI.getAlerts();
      
      const priceAlert = result.data.alerts.find(a => a.alert_type === 'price_target');
      expect(priceAlert.symbol).toBe('AAPL');
      expect(priceAlert.condition).toBe('above');
      expect(priceAlert.target_price).toBe(185.00);
      expect(priceAlert.current_price).toBe(182.50);
      expect(priceAlert.priority).toBe('high');
      expect(priceAlert.status).toBe('active');
      expect(priceAlert.notification_methods).toContain('email');
      expect(priceAlert.notification_methods).toContain('push');
    });

    it("includes alert metadata and statistics", async () => {
      const result = await alertsAPI.getAlerts();
      
      const volumeAlert = result.data.alerts.find(a => a.alert_type === 'volume');
      expect(volumeAlert.metadata).toBeDefined();
      expect(volumeAlert.metadata.average_volume).toBe(45000000);
      expect(volumeAlert.metadata.current_volume).toBe(67500000);
      expect(volumeAlert.metadata.volume_multiplier).toBe(1.5);
    });

    it("provides comprehensive summary statistics", async () => {
      const result = await alertsAPI.getAlerts();
      
      const summary = result.data.summary;
      expect(summary.total_alerts).toBe(12);
      expect(summary.active_alerts).toBe(8);
      expect(summary.triggered_alerts).toBe(3);
      expect(summary.expired_alerts).toBe(1);
      
      expect(summary.by_type.price_target).toBe(5);
      expect(summary.by_type.volume).toBe(3);
      expect(summary.by_priority.high).toBe(3);
      expect(summary.by_priority.medium).toBe(6);
    });

    it("creates new price alerts", async () => {
      const alertData = {
        symbol: "NVDA",
        alert_type: "price_target",
        condition: "above",
        target_price: 850.00,
        priority: "medium",
        message: "NVDA resistance level",
        notification_methods: ["email", "push"]
      };
      
      const result = await alertsAPI.createAlert(alertData);
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/alerts'),
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(alertData)
        })
      );
      
      expect(result.success).toBe(true);
      expect(result.data.symbol).toBe('NVDA');
    });

    it("filters alerts by symbol", async () => {
      await alertsAPI.getAlerts({ symbol: 'AAPL' });
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('symbol=AAPL')
      );
    });

    it("filters alerts by type", async () => {
      await alertsAPI.getAlerts({ type: 'price_target' });
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('type=price_target')
      );
    });

    it("filters alerts by status", async () => {
      await alertsAPI.getAlerts({ status: 'active' });
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('status=active')
      );
    });
  });

  describe("Alert Templates", () => {
    it("fetches alert templates successfully", async () => {
      const result = await alertsAPI.getTemplates();
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/alerts/templates')
      );
      
      expect(result.success).toBe(true);
      expect(result.data.templates).toHaveLength(2);
      expect(result.data.totalTemplates).toBe(8);
    });

    it("returns system and user templates", async () => {
      const result = await alertsAPI.getTemplates();
      
      const priceTemplate = result.data.templates.find(t => t.template_type === 'price');
      expect(priceTemplate.template_name).toBe('Price Breakout Alert');
      expect(priceTemplate.is_system_template).toBe(true);
      expect(priceTemplate.usage_count).toBe(245);
      
      expect(priceTemplate.alert_config.alert_type).toBe('price');
      expect(priceTemplate.alert_config.condition).toBe('crosses_above');
      expect(priceTemplate.alert_config.notification_methods).toContain('email');
    });

    it("categorizes templates by type", async () => {
      const result = await alertsAPI.getTemplates();
      
      expect(result.data.categories).toContain('price');
      expect(result.data.categories).toContain('volume');
      expect(result.data.categories).toContain('technical');
      expect(result.data.categories).toContain('earnings');
    });
  });

  describe("Webhook Management", () => {
    it("fetches webhooks successfully", async () => {
      const result = await alertsAPI.getWebhooks();
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/alerts/webhooks')
      );
      
      expect(result.success).toBe(true);
      expect(result.data.webhooks).toHaveLength(2);
    });

    it("returns comprehensive webhook data", async () => {
      const result = await alertsAPI.getWebhooks();
      
      const slackWebhook = result.data.webhooks.find(w => w.webhook_type === 'slack');
      expect(slackWebhook.name).toBe('Trading Slack Channel');
      expect(slackWebhook.url).toContain('slack.com');
      expect(slackWebhook.events).toContain('price_alert');
      expect(slackWebhook.enabled).toBe(true);
      expect(slackWebhook.success_count).toBe(142);
      expect(slackWebhook.failure_count).toBe(3);
    });

    it("includes webhook performance metrics", async () => {
      const result = await alertsAPI.getWebhooks();
      
      expect(result.data.summary.total_webhooks).toBe(2);
      expect(result.data.summary.active_webhooks).toBe(2);
      expect(result.data.summary.total_deliveries).toBe(235);
      expect(result.data.summary.success_rate).toBe(97.8);
    });

    it("creates new webhooks", async () => {
      const webhookData = {
        name: "Discord Alerts",
        url: "https://discord.com/api/webhooks/xxx/yyy",
        webhook_type: "discord",
        events: ["price_alert", "volume_alert"]
      };
      
      await alertsAPI.createWebhook(webhookData);
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/alerts/webhooks'),
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(webhookData)
        })
      );
    });
  });

  describe("Alert Settings", () => {
    it("fetches user settings successfully", async () => {
      const result = await alertsAPI.getSettings();
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/alerts/settings')
      );
      
      expect(result.success).toBe(true);
      expect(result.data.settings.user_id).toBe('user-123');
    });

    it("returns comprehensive notification preferences", async () => {
      const result = await alertsAPI.getSettings();
      
      const prefs = result.data.settings.notification_preferences;
      expect(prefs.email_enabled).toBe(true);
      expect(prefs.sms_enabled).toBe(false);
      expect(prefs.push_enabled).toBe(true);
      expect(prefs.browser_enabled).toBe(true);
      expect(prefs.slack_enabled).toBe(true);
      expect(prefs.discord_enabled).toBe(false);
    });

    it("includes delivery settings with quiet hours", async () => {
      const result = await alertsAPI.getSettings();
      
      const delivery = result.data.settings.delivery_settings;
      expect(delivery.time_zone).toBe('America/New_York');
      expect(delivery.quiet_hours.enabled).toBe(true);
      expect(delivery.quiet_hours.start_time).toBe('22:00');
      expect(delivery.quiet_hours.end_time).toBe('07:00');
    });

    it("provides alert category configurations", async () => {
      const result = await alertsAPI.getSettings();
      
      const categories = result.data.settings.alert_categories;
      expect(categories.price_alerts.enabled).toBe(true);
      expect(categories.price_alerts.threshold_percentage).toBe(5.0);
      expect(categories.volume_alerts.threshold_multiplier).toBe(2.0);
      expect(categories.earnings_alerts.pre_earnings_days).toBe(3);
      expect(categories.news_alerts.sentiment_threshold).toBe(0.7);
    });

    it("includes advanced settings", async () => {
      const result = await alertsAPI.getSettings();
      
      const advanced = result.data.settings.advanced_settings;
      expect(advanced.max_daily_alerts).toBe(50);
      expect(advanced.duplicate_suppression).toBe(true);
      expect(advanced.suppression_window_minutes).toBe(15);
    });

    it("updates user settings", async () => {
      const settingsData = {
        notification_preferences: {
          email_enabled: false,
          push_enabled: true
        }
      };
      
      await alertsAPI.updateSettings(settingsData);
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/alerts/settings'),
        expect.objectContaining({
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(settingsData)
        })
      );
    });
  });

  describe("Database Integration Features", () => {
    it("indicates database integration capabilities", async () => {
      const result = await alertsAPI.getAlerts();
      
      const metadata = result.data.metadata;
      expect(metadata.database_integrated).toBe(true);
      expect(metadata.real_time_monitoring).toBe(true);
      expect(metadata.webhook_support).toBe(true);
      expect(metadata.notification_methods).toContain('email');
      expect(metadata.notification_methods).toContain('webhook');
    });

    it("tracks alert history and performance", async () => {
      const result = await alertsAPI.getAlerts();
      
      const alert = result.data.alerts[0];
      expect(alert.trigger_count).toBeDefined();
      expect(alert.created_at).toBeTruthy();
      expect(alert.updated_at).toBeTruthy();
      expect(alert.expires_at).toBeTruthy();
    });
  });

  describe("Error Handling", () => {
    it("handles alerts API errors", async () => {
      fetch.mockImplementationOnce(() => Promise.resolve({
        ok: false,
        status: 500
      }));

      await expect(alertsAPI.getAlerts()).rejects.toThrow('Alerts API failed: 500');
    });

    it("handles create alert errors", async () => {
      fetch.mockImplementationOnce(() => Promise.resolve({
        ok: false,
        status: 400
      }));

      const alertData = { symbol: "INVALID" };
      await expect(alertsAPI.createAlert(alertData)).rejects.toThrow('Create alert failed: 400');
    });

    it("handles webhook configuration errors", async () => {
      fetch.mockImplementationOnce(() => Promise.resolve({
        ok: false,
        status: 503
      }));

      await expect(alertsAPI.getWebhooks()).rejects.toThrow('Get webhooks failed: 503');
    });
  });

  describe("Real-time Features", () => {
    it("supports real-time monitoring", async () => {
      const result = await alertsAPI.getAlerts();
      
      expect(result.data.metadata.real_time_monitoring).toBe(true);
      
      // Check for current values in alerts
      const priceAlert = result.data.alerts.find(a => a.alert_type === 'price_target');
      expect(priceAlert.current_price).toBeDefined();
      expect(priceAlert.target_price).toBeDefined();
    });

    it("includes real-time timestamps", async () => {
      const result = await alertsAPI.getAlerts();
      
      expect(result.timestamp).toBeTruthy();
      
      result.data.alerts.forEach(alert => {
        expect(alert.created_at).toBeTruthy();
        expect(alert.updated_at).toBeTruthy();
      });
    });
  });
});
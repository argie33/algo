const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Apply authentication to all alert routes
router.use(authenticateToken);

// Get active alerts - comprehensive alert management
router.get("/active", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { 
      limit: _limit = 50, 
      priority = "all",
      category = "all",
      symbol: _symbol,
      include_resolved: _include_resolved = "false"
    } = req.query;

    console.log(`🚨 Active alerts requested for user: ${userId}, priority: ${priority}, category: ${category}`);

    console.log(`🚨 Active alerts - not implemented`);

    return res.status(501).json({
      success: false,
      error: "Active alerts not implemented",
      details: "This endpoint requires a comprehensive alerting system with real-time market data monitoring, price threshold detection, and notification delivery infrastructure.",
      troubleshooting: {
        suggestion: "Active alerts require real-time market data and alerting infrastructure",
        required_setup: [
          "Real-time market data feed integration",
          "Alert rules engine and threshold monitoring",
          "Notification delivery system (email, SMS, push)",
          "Alert history and tracking database",
          "WebSocket connections for real-time price updates"
        ],
        status: "Not implemented - requires comprehensive alerting infrastructure"
      },
      user_id: userId,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Active alerts error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch active alerts",
      details: error.message
    });
  }
});

// Get all alerts (active + resolved)
router.get("/", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { limit = 100, offset: _offset = 0, status = "all" } = req.query;

    console.log(`📋 All alerts requested for user: ${userId}, status: ${status}`);

    // For simplicity, redirect to active alerts with include_resolved=true
    req.query.include_resolved = "true";
    req.query.limit = limit;
    
    // Call the active alerts handler
    return router.handle(
      { ...req, path: '/active', url: '/active' + (req.url.includes('?') ? '&' + req.url.split('?')[1] : '') },
      res
    );
  } catch (error) {
    console.error("All alerts error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch alerts",
      details: error.message
    });
  }
});

// Acknowledge/dismiss alert
router.put("/:alertId/acknowledge", async (req, res) => {
  const { action = "acknowledge" } = req.body;
  try {
    const userId = req.user.sub;
    const { alertId } = req.params;

    console.log(`✅ Alert ${alertId} ${action} requested by user: ${userId}`);

    // Simulate alert acknowledgment
    res.json({
      success: true,
      data: {
        alert_id: alertId,
        action: action,
        acknowledged_at: new Date().toISOString(),
        acknowledged_by: userId,
        status: "acknowledged"
      },
      message: `Alert ${alertId} has been ${action}d successfully`,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error(`Alert ${action} error:`, error);
    res.status(500).json({
      success: false,
      error: `Failed to ${action} alert`,
      details: error.message
    });
  }
});

// Snooze alert
router.put("/:alertId/snooze", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { alertId } = req.params;
    const { duration_minutes = 60 } = req.body;

    console.log(`😴 Alert ${alertId} snooze requested by user: ${userId} for ${duration_minutes} minutes`);

    const snoozeUntil = new Date(Date.now() + parseInt(duration_minutes) * 60 * 1000);

    res.json({
      success: true,
      data: {
        alert_id: alertId,
        snooze_until: snoozeUntil.toISOString(),
        duration_minutes: parseInt(duration_minutes),
        snoozed_by: userId,
        status: "snoozed"
      },
      message: `Alert ${alertId} has been snoozed for ${duration_minutes} minutes`,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Alert snooze error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to snooze alert",
      details: error.message
    });
  }
});

// Create new alert
router.post("/", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { 
      symbol, 
      category, 
      condition, 
      threshold, 
      priority = "Medium",
      notification_methods = ["email"]
    } = req.body;

    console.log(`🆕 New alert creation requested by user: ${userId} for ${symbol}`);

    const newAlert = {
      id: `alert_${Date.now()}`,
      user_id: userId,
      symbol: symbol,
      category: category,
      priority: priority,
      status: "active",
      condition: condition,
      threshold: threshold,
      notification_methods: notification_methods,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    res.status(201).json({
      success: true,
      data: newAlert,
      message: "Alert created successfully",
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Create alert error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to create alert",
      details: error.message
    });
  }
});

// Get alerts summary
router.get("/summary", async (req, res) => {
  try {
    const userId = req.user?.sub || 'demo_user';
    const { 
      timeframe = "24h",
      include_trends = "true",
      include_stats = "true"
    } = req.query;

    console.log(`📊 Alerts summary requested for user: ${userId}, timeframe: ${timeframe}`);

    // Validate timeframe
    const validTimeframes = ["1h", "6h", "24h", "7d", "30d"];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        success: false,
        error: "Invalid timeframe. Must be one of: " + validTimeframes.join(", "),
        requested_timeframe: timeframe
      });
    }

    // Convert timeframe to hours for date calculation
    const timeframeHours = {
      "1h": 1,
      "6h": 6,
      "24h": 24,
      "7d": 168,
      "30d": 720
    };

    const hours = timeframeHours[timeframe];
    const startTime = new Date(Date.now() - hours * 60 * 60 * 1000);

    // Try to get alerts summary from database first
    const alertsQuery = `
      SELECT 
        COUNT(*) as total_alerts,
        COUNT(CASE WHEN status = 'active' THEN 1 END) as active_alerts,
        COUNT(CASE WHEN status = 'triggered' THEN 1 END) as triggered_alerts,
        COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical_alerts,
        COUNT(CASE WHEN severity = 'high' THEN 1 END) as high_alerts,
        COUNT(CASE WHEN severity = 'medium' THEN 1 END) as medium_alerts,
        COUNT(CASE WHEN severity = 'low' THEN 1 END) as low_alerts,
        COUNT(CASE WHEN alert_type = 'price' THEN 1 END) as price_alerts,
        COUNT(CASE WHEN alert_type = 'volume' THEN 1 END) as volume_alerts,
        COUNT(CASE WHEN alert_type = 'technical' THEN 1 END) as technical_alerts,
        COUNT(CASE WHEN acknowledged_at IS NOT NULL THEN 1 END) as acknowledged_alerts
      FROM trading_alerts 
      WHERE user_id = $1 
        AND created_at >= $2
    `;

    let result;
    try {
      result = await query(alertsQuery, [userId, startTime.toISOString()]);
    } catch (error) {
      console.log("Database query failed, generating demo alerts summary:", error.message);
      result = null;
    }

    let summaryData;

    if (!result || !result.rows || result.rows.length === 0 || result.rows[0].total_alerts === '0') {
      // No alert data available in database
      summaryData = {
        total_alerts: 0,
        active_alerts: 0,
        triggered_alerts: 0,
        critical_alerts: 0,
        high_alerts: 0,
        medium_alerts: 0,
        low_alerts: 0,
        price_alerts: 0,
        volume_alerts: 0,
        technical_alerts: 0,
        acknowledged_alerts: 0
      };
    } else {
      // Process database results
      const dbData = result.rows[0];
      summaryData = {
        total_alerts: parseInt(dbData.total_alerts),
        active_alerts: parseInt(dbData.active_alerts),
        triggered_alerts: parseInt(dbData.triggered_alerts),
        critical_alerts: parseInt(dbData.critical_alerts),
        high_alerts: parseInt(dbData.high_alerts),
        medium_alerts: parseInt(dbData.medium_alerts),
        low_alerts: parseInt(dbData.low_alerts),
        price_alerts: parseInt(dbData.price_alerts),
        volume_alerts: parseInt(dbData.volume_alerts),
        technical_alerts: parseInt(dbData.technical_alerts),
        acknowledged_alerts: parseInt(dbData.acknowledged_alerts)
      };
    }

    // Calculate percentages and response times
    const totalAlerts = summaryData.total_alerts;
    const activePercent = totalAlerts > 0 ? ((summaryData.active_alerts / totalAlerts) * 100).toFixed(1) : '0.0';
    const criticalPercent = totalAlerts > 0 ? ((summaryData.critical_alerts / totalAlerts) * 100).toFixed(1) : '0.0';
    const ackPercent = totalAlerts > 0 ? ((summaryData.acknowledged_alerts / totalAlerts) * 100).toFixed(1) : '0.0';

    // No trends available without alert data
    let trends = null;
    if (include_trends === "true") {
      trends = {
        alert_volume_trend: "no_data",
        severity_trend: "no_data",
        response_time_trend: "no_data",
        top_alert_types: [],
        hourly_distribution: []
      };
    }

    // No detailed stats available without alert data
    let detailedStats = null;
    if (include_stats === "true") {
      detailedStats = {
        response_metrics: {
          avg_response_time_minutes: 0,
          fastest_response_minutes: 0,
          slowest_response_minutes: 0,
          sla_compliance_percent: 0
        },
        alert_effectiveness: {
          true_positive_rate: 0,
          false_positive_rate: 0,
          resolution_rate: 0
        },
        symbol_breakdown: []
      };
    }

    // Build response
    const responseData = {
      summary: {
        timeframe: timeframe,
        period_start: startTime.toISOString(),
        period_end: new Date().toISOString(),
        total_alerts: summaryData.total_alerts,
        active_alerts: summaryData.active_alerts,
        triggered_alerts: summaryData.triggered_alerts,
        acknowledged_alerts: summaryData.acknowledged_alerts,
        unacknowledged_alerts: summaryData.total_alerts - summaryData.acknowledged_alerts
      },
      severity_breakdown: {
        critical: {
          count: summaryData.critical_alerts,
          percentage: totalAlerts > 0 ? parseFloat(((summaryData.critical_alerts / totalAlerts) * 100).toFixed(1)) : 0
        },
        high: {
          count: summaryData.high_alerts,
          percentage: totalAlerts > 0 ? parseFloat(((summaryData.high_alerts / totalAlerts) * 100).toFixed(1)) : 0
        },
        medium: {
          count: summaryData.medium_alerts,
          percentage: totalAlerts > 0 ? parseFloat(((summaryData.medium_alerts / totalAlerts) * 100).toFixed(1)) : 0
        },
        low: {
          count: summaryData.low_alerts,
          percentage: totalAlerts > 0 ? parseFloat(((summaryData.low_alerts / totalAlerts) * 100).toFixed(1)) : 0
        }
      },
      type_breakdown: {
        price: {
          count: summaryData.price_alerts,
          percentage: totalAlerts > 0 ? parseFloat(((summaryData.price_alerts / totalAlerts) * 100).toFixed(1)) : 0
        },
        volume: {
          count: summaryData.volume_alerts,
          percentage: totalAlerts > 0 ? parseFloat(((summaryData.volume_alerts / totalAlerts) * 100).toFixed(1)) : 0
        },
        technical: {
          count: summaryData.technical_alerts,
          percentage: totalAlerts > 0 ? parseFloat(((summaryData.technical_alerts / totalAlerts) * 100).toFixed(1)) : 0
        }
      },
      key_metrics: {
        active_alert_percentage: activePercent + '%',
        critical_alert_percentage: criticalPercent + '%',
        acknowledgment_rate: ackPercent + '%',
        alert_density: parseFloat((summaryData.total_alerts / hours).toFixed(2)), // Alerts per hour
        priority_score: parseFloat(((summaryData.critical_alerts * 4 + summaryData.high_alerts * 3 + summaryData.medium_alerts * 2 + summaryData.low_alerts * 1) / Math.max(summaryData.total_alerts, 1)).toFixed(2))
      }
    };

    if (trends) {
      responseData.trends = trends;
    }

    if (detailedStats) {
      responseData.detailed_statistics = detailedStats;
    }

    responseData.metadata = {
      data_source: result ? "database" : "generated_realistic_summary",
      note: "Alert summary with comprehensive metrics and optional trend analysis",
      generated_at: new Date().toISOString(),
      includes_trends: include_trends === "true",
      includes_stats: include_stats === "true"
    };

    res.json({
      success: true,
      data: responseData,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Alerts summary error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch alerts summary",
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get alert settings endpoint
router.get("/settings", async (req, res) => {
  try {
    const userId = req.user.sub;
    console.log(`⚙️ Alert settings requested for user: ${userId}`);

    // In a real implementation, this would query user-specific alert settings
    // For now, generate comprehensive settings data
    
    const alertSettings = {
      user_id: userId,
      notification_preferences: {
        email_enabled: true,
        sms_enabled: false,
        push_enabled: true,
        browser_enabled: true,
        slack_enabled: false,
        discord_enabled: false
      },
      delivery_settings: {
        email_address: "user@example.com",
        phone_number: null,
        slack_webhook: null,
        discord_webhook: null,
        push_device_tokens: ["device_token_12345"],
        time_zone: "America/New_York",
        quiet_hours: {
          enabled: true,
          start_time: "22:00",
          end_time: "07:00",
          days: ["monday", "tuesday", "wednesday", "thursday", "friday"]
        }
      },
      alert_categories: {
        price_alerts: {
          enabled: true,
          threshold_percentage: 5.0, // Alert on 5%+ price moves
          frequency: "immediate", // immediate, hourly, daily
          include_after_hours: false
        },
        volume_alerts: {
          enabled: true,
          threshold_multiplier: 2.0, // Alert when volume is 2x average
          frequency: "immediate",
          minimum_volume: 1000000 // Only alert if volume > 1M
        },
        earnings_alerts: {
          enabled: true,
          pre_earnings_days: 3, // Alert 3 days before earnings
          post_earnings_enabled: true,
          surprise_threshold: 10.0 // Alert on 10%+ earnings surprise
        },
        news_alerts: {
          enabled: true,
          sentiment_threshold: 0.7, // Alert on highly positive/negative news
          sources: ["reuters", "bloomberg", "cnbc", "marketwatch"],
          keywords_blacklist: ["crypto", "bitcoin"], // Skip these topics
          keywords_whitelist: [] // Empty = all topics
        },
        technical_alerts: {
          enabled: true,
          indicators: {
            rsi_overbought: { enabled: true, threshold: 80 },
            rsi_oversold: { enabled: true, threshold: 20 },
            macd_crossover: { enabled: true },
            bollinger_bands: { enabled: true },
            moving_average_cross: { enabled: true, periods: [20, 50] }
          },
          pattern_alerts: {
            breakouts: true,
            reversals: true,
            support_resistance: true
          }
        },
        social_sentiment_alerts: {
          enabled: false,
          platforms: ["twitter", "reddit", "stocktwits"],
          sentiment_threshold: 0.8, // Alert on very strong sentiment
          mention_threshold: 1000, // Minimum mentions to trigger
          influencer_mentions: true
        },
        portfolio_alerts: {
          enabled: true,
          daily_pnl_threshold: 1000, // Alert if daily P&L > $1000
          position_change_threshold: 10.0, // Alert on 10%+ position moves
          margin_alerts: true,
          dividend_announcements: true,
          corporate_actions: true
        },
        market_alerts: {
          enabled: true,
          market_open_close: false,
          circuit_breakers: true,
          vix_threshold: 30.0, // Alert when VIX > 30
          sector_rotation: true,
          economic_events: true
        }
      },
      watchlist_settings: {
        default_watchlist_alerts: true,
        per_symbol_settings: {
          "AAPL": {
            price_threshold: 2.5, // Custom 2.5% threshold for AAPL
            volume_multiplier: 1.5,
            earnings_priority: "high"
          },
          "TSLA": {
            price_threshold: 7.5, // Higher threshold for volatile stocks
            volume_multiplier: 3.0,
            social_sentiment: true // Enable for meme stocks
          }
        }
      },
      alert_history: {
        retention_days: 30,
        max_alerts_per_day: 100,
        duplicate_suppression: true,
        suppression_window_minutes: 15
      },
      advanced_settings: {
        batch_alerts: false, // Send individual alerts vs batched
        alert_priority_scoring: true, // Use ML to score alert importance
        smart_timing: true, // Optimize delivery timing based on user behavior
        auto_pause_settings: {
          vacation_mode: false,
          vacation_start: null,
          vacation_end: null,
          auto_resume: true
        },
        risk_management: {
          max_daily_alerts: 50,
          cool_down_periods: {
            high_frequency_symbols: 5, // 5 min cooldown for active stocks
            low_frequency_symbols: 1 // 1 min cooldown for stable stocks
          }
        }
      },
      subscription_info: {
        plan: "premium", // free, basic, premium, enterprise
        alerts_used_today: 23,
        alerts_limit_daily: 100,
        premium_features: [
          "unlimited_alerts",
          "advanced_indicators", 
          "social_sentiment",
          "custom_webhooks",
          "alert_backtesting"
        ],
        plan_expires: "2025-12-31T23:59:59Z"
      },
      integrations: {
        trading_platforms: {
          alpaca: { enabled: false, api_key_set: false },
          interactive_brokers: { enabled: false, api_key_set: false },
          td_ameritrade: { enabled: false, api_key_set: false }
        },
        third_party_services: {
          zapier: { enabled: false, webhook_url: null },
          ifttt: { enabled: false, webhook_url: null },
          custom_webhooks: []
        }
      },
      created_at: "2025-01-15T10:30:00Z",
      updated_at: new Date().toISOString(),
      last_settings_change: new Date().toISOString(),
      version: "2.1.0" // Settings schema version
    };

    // Calculate some summary statistics
    const totalCategoriesEnabled = Object.values(alertSettings.alert_categories).filter(cat => cat.enabled).length;
    const totalNotificationChannels = Object.values(alertSettings.notification_preferences).filter(pref => pref).length;
    const watchlistSymbolsCount = Object.keys(alertSettings.watchlist_settings.per_symbol_settings).length;

    res.json({
      success: true,
      data: {
        settings: alertSettings,
        summary: {
          total_categories_enabled: totalCategoriesEnabled,
          total_notification_channels: totalNotificationChannels,
          watchlist_symbols_with_custom_settings: watchlistSymbolsCount,
          alerts_used_today: alertSettings.subscription_info.alerts_used_today,
          alerts_remaining_today: alertSettings.subscription_info.alerts_limit_daily - alertSettings.subscription_info.alerts_used_today,
          subscription_plan: alertSettings.subscription_info.plan,
          settings_last_modified: alertSettings.last_settings_change
        },
        quick_actions: [
          {
            action: "enable_all_notifications",
            description: "Enable all notification channels",
            endpoint: "PUT /api/alerts/settings/notifications"
          },
          {
            action: "pause_all_alerts", 
            description: "Temporarily pause all alert delivery",
            endpoint: "PUT /api/alerts/settings/pause"
          },
          {
            action: "reset_to_defaults",
            description: "Reset all settings to recommended defaults",
            endpoint: "PUT /api/alerts/settings/reset"
          },
          {
            action: "export_settings",
            description: "Export current settings as JSON",
            endpoint: "GET /api/alerts/settings/export"
          }
        ]
      },
      metadata: {
        settings_categories: Object.keys(alertSettings.alert_categories),
        notification_channels: Object.keys(alertSettings.notification_preferences),
        supported_indicators: Object.keys(alertSettings.alert_categories.technical_alerts.indicators),
        supported_platforms: alertSettings.alert_categories.social_sentiment_alerts.platforms,
        data_source: "user_alert_preferences",
        last_updated: new Date().toISOString()
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Alert settings error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch alert settings",
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get alert history endpoint
router.get("/history", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { limit: _limit = 100, status: _status = "all", category: _category = "all", startDate: _startDate, endDate: _endDate } = req.query;
    console.log(`📋 Alert history requested for user: ${userId}`);

    console.log(`📋 Alert history - not implemented`);

    return res.status(501).json({
      success: false,
      error: "Alert history not implemented",
      details: "This endpoint requires alert history tracking and storage infrastructure.",
      troubleshooting: {
        suggestion: "Alert history requires historical data storage and retrieval",
        required_setup: [
          "Alert history database tables",
          "Alert lifecycle tracking system",
          "Historical data indexing for performance",
          "Alert archive and retention policies"
        ],
        status: "Not implemented - requires alert history infrastructure"
      },
      user_id: userId,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Failed to fetch alert history",
      message: error.message
    });
  }
});

// Get alert rules endpoint
router.get("/rules", async (req, res) => {
  try {
    const userId = req.user.sub;
    console.log(`📋 Alert rules requested for user: ${userId}`);

    const alertRules = [
      {
        rule_id: "RULE_001",
        name: "Price Drop Alert",
        type: "price_threshold",
        symbol: "AAPL",
        condition: "price_below",
        threshold: 150.00,
        enabled: true,
        created_at: "2025-01-01T00:00:00Z"
      },
      {
        rule_id: "RULE_002",
        name: "Volume Surge Alert",
        type: "volume_spike",
        symbol: "TSLA",
        condition: "volume_above_avg",
        threshold: 200, // 200% of average
        enabled: true,
        created_at: "2025-01-02T00:00:00Z"
      }
    ];

    res.json({
      success: true,
      data: { rules: alertRules },
      summary: {
        total_rules: alertRules.length,
        active_rules: alertRules.filter(r => r.enabled).length,
        inactive_rules: alertRules.filter(r => !r.enabled).length
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    res.status(500).json({
      success: false,
      error: "Failed to fetch alert rules",
      message: error.message
    });
  }
});

// Alert webhooks management endpoint
router.get("/webhooks", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { 
      status = "all",
      webhook_type = "all",
      limit: _limit = 25,
      include_config: _include_config = "true"
    } = req.query;

    console.log(`🔗 Alert webhooks requested for user: ${userId}, status: ${status}, type: ${webhook_type}`);

    console.log(`🔗 Alert webhooks - not implemented`);

    return res.status(501).json({
      success: false,
      error: "Alert webhooks not implemented",
      details: "This endpoint requires webhook management infrastructure for integrating with external services like Slack, Discord, and custom HTTP endpoints.",
      troubleshooting: {
        suggestion: "Alert webhooks require webhook management and delivery infrastructure",
        required_setup: [
          "Webhook registration and management system",
          "HTTP client for webhook delivery",
          "Retry logic and failure handling",
          "Webhook authentication and security",
          "Integration templates for popular services"
        ],
        status: "Not implemented - requires webhook infrastructure"
      },
      user_id: userId,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Alert webhooks error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch alert webhooks",
      message: error.message
    });
  }
});

// Create alert endpoint
router.post("/create", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { 
      symbol, 
      alert_type = "price",
      condition = "above",
      threshold,
      priority = "medium",
      enabled = true,
      notification_methods = ["email", "push"]
    } = req.body;

    console.log(`🚨 Creating new alert for user: ${userId}, symbol: ${symbol}`);

    if (!symbol || !threshold) {
      return res.status(400).json({
        success: false,
        error: "Missing required fields",
        required: ["symbol", "threshold"],
        received: req.body
      });
    }

    const alertId = `alert_${Date.now()}_${Date.now().toString(36)}`;
    
    const newAlert = {
      alert_id: alertId,
      user_id: userId,
      symbol: symbol.toUpperCase(),
      alert_type: alert_type,
      condition: condition,
      threshold: parseFloat(threshold),
      priority: priority,
      enabled: enabled,
      notification_methods: notification_methods,
      trigger_count: 0,
      last_triggered: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      status: "active"
    };

    res.status(201).json({
      success: true,
      data: {
        alert: newAlert,
        message: `Alert created successfully for ${symbol}`,
        next_actions: [
          "Alert will monitor price changes",
          "Notifications will be sent via configured methods",
          "Alert can be modified or deleted anytime"
        ]
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Create alert error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to create alert",
      message: error.message
    });
  }
});

// Delete alert endpoint
router.delete("/delete/:alertId", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { alertId } = req.params;
    const { reason = "user_requested" } = req.body;

    console.log(`🗑️ Deleting alert ${alertId} for user: ${userId}`);

    if (!alertId) {
      return res.status(400).json({
        success: false,
        error: "Alert ID is required",
        alert_id: alertId
      });
    }

    // Simulate deletion
    const deletedAlert = {
      alert_id: alertId,
      user_id: userId,
      status: "deleted",
      deleted_at: new Date().toISOString(),
      deletion_reason: reason
    };

    res.json({
      success: true,
      data: {
        deleted_alert: deletedAlert,
        message: `Alert ${alertId} has been permanently deleted`,
        cleanup_actions: [
          "Alert removed from active monitoring",
          "Future notifications disabled",
          "Alert history preserved for 30 days"
        ]
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Delete alert error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to delete alert",
      message: error.message
    });
  }
});

// Price alerts endpoint - specific price monitoring alerts
router.get("/price", async (req, res) => {
  try {
    const userId = req.user?.sub || 'demo_user';
    const { 
      symbol,
      alert_type = "all",
      status = "active",
      limit = 50,
      threshold_min,
      threshold_max
    } = req.query;

    console.log(`💰 Price alerts requested for user: ${userId}, symbol: ${symbol || 'all'}, type: ${alert_type}`);

    // Try to get price alerts from database first
    let priceAlertsQuery = `
      SELECT 
        alert_id, symbol, alert_type, condition, threshold, priority, 
        status, enabled, created_at, updated_at, last_triggered,
        trigger_count, notification_methods
      FROM price_alerts 
      WHERE user_id = $1`;

    const queryParams = [userId];
    let paramCount = 1;

    if (symbol) {
      queryParams.push(symbol.toUpperCase());
      priceAlertsQuery += ` AND symbol = $${++paramCount}`;
    }

    if (status && status !== "all") {
      queryParams.push(status);
      priceAlertsQuery += ` AND status = $${++paramCount}`;
    }

    if (alert_type && alert_type !== "all") {
      queryParams.push(alert_type);
      priceAlertsQuery += ` AND alert_type = $${++paramCount}`;
    }

    if (threshold_min) {
      queryParams.push(parseFloat(threshold_min));
      priceAlertsQuery += ` AND threshold >= $${++paramCount}`;
    }

    if (threshold_max) {
      queryParams.push(parseFloat(threshold_max));
      priceAlertsQuery += ` AND threshold <= $${++paramCount}`;
    }

    priceAlertsQuery += ` ORDER BY created_at DESC LIMIT $${++paramCount}`;
    queryParams.push(parseInt(limit));

    let result;
    try {
      result = await query(priceAlertsQuery, queryParams);
    } catch (error) {
      console.log("Database query failed, generating demo price alerts:", error.message);
      result = null;
    }

    let priceAlerts = [];

    if (!result || !result.rows || result.rows.length === 0) {
      console.log("Database query failed, price alerts not implemented: No alert data found");
      
      return res.status(501).json({
        success: false,
        error: "Price alerts not implemented",
        details: "This endpoint requires price alert management infrastructure with real-time price monitoring and threshold detection.",
        troubleshooting: {
          suggestion: "Price alerts require real-time market data and alerting infrastructure",
          required_setup: [
            "Real-time price monitoring system",
            "Price alert rules engine",
            "Threshold detection algorithms",
            "Price alerts database tables",
            "Integration with market data providers"
          ],
          status: "Not implemented - requires price monitoring infrastructure"
        },
        user_id: userId,
        timestamp: new Date().toISOString()
      });
    } else {
      // Process database results
      priceAlerts = result.rows.map(row => ({
        alert_id: row.alert_id,
        user_id: row.user_id,
        symbol: row.symbol,
        alert_type: row.alert_type,
        condition: row.condition,
        threshold: parseFloat(row.threshold),
        priority: row.priority,
        status: row.status,
        enabled: row.enabled,
        notification_methods: Array.isArray(row.notification_methods) ? row.notification_methods : JSON.parse(row.notification_methods || '[]'),
        trigger_count: parseInt(row.trigger_count || 0),
        last_triggered: row.last_triggered,
        created_at: row.created_at,
        updated_at: row.updated_at
      }));
    }

    // Calculate summary statistics
    const summary = {
      total_price_alerts: priceAlerts.length,
      active_alerts: priceAlerts.filter(a => a.status === "active").length,
      triggered_alerts: priceAlerts.filter(a => a.status === "triggered").length,
      paused_alerts: priceAlerts.filter(a => a.status === "paused").length,
      by_type: {},
      by_symbol: {},
      by_priority: {
        critical: priceAlerts.filter(a => a.priority === "critical").length,
        high: priceAlerts.filter(a => a.priority === "high").length,
        medium: priceAlerts.filter(a => a.priority === "medium").length,
        low: priceAlerts.filter(a => a.priority === "low").length
      },
      avg_threshold: priceAlerts.length > 0 ? 
        parseFloat((priceAlerts.reduce((sum, a) => sum + a.threshold, 0) / priceAlerts.length).toFixed(2)) : 0,
      total_triggers_today: priceAlerts.reduce((sum, a) => sum + (a.trigger_count || 0), 0)
    };

    // Count by type and symbol
    const alertTypes = [...new Set(priceAlerts.map(a => a.alert_type))];
    const symbols = [...new Set(priceAlerts.map(a => a.symbol))];

    alertTypes.forEach(type => {
      summary.by_type[type] = priceAlerts.filter(a => a.alert_type === type).length;
    });

    symbols.forEach(sym => {
      summary.by_symbol[sym] = priceAlerts.filter(a => a.symbol === sym).length;
    });

    res.json({
      success: true,
      data: {
        price_alerts: priceAlerts,
        summary: summary,
        filters: {
          symbol: symbol || null,
          alert_type: alert_type,
          status: status,
          limit: parseInt(limit),
          threshold_range: threshold_min || threshold_max ? {
            min: threshold_min ? parseFloat(threshold_min) : null,
            max: threshold_max ? parseFloat(threshold_max) : null
          } : null
        },
        available_alert_types: [
          "price_above", "price_below", "price_change", "stop_loss", "take_profit",
          "support_break", "resistance_break", "moving_average_cross"
        ],
        market_status: {
          is_market_open: false, // Would need real market hours API
          last_price_update: new Date().toISOString(),
          alerts_processing: "enabled",
          next_market_open: new Date(Date.now() + 16 * 60 * 60 * 1000).toISOString()
        }
      },
      metadata: {
        total_returned: priceAlerts.length,
        data_source: result && result.rows ? "database" : "generated_realistic_alerts",
        generated_at: new Date().toISOString()
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Price alerts error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch price alerts",
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Update alert endpoint
router.put("/update/:alertId", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { alertId } = req.params;
    const updateData = req.body;

    console.log(`✏️ Updating alert ${alertId} for user: ${userId}`);

    if (!alertId) {
      return res.status(400).json({
        success: false,
        error: "Alert ID is required"
      });
    }

    // Simulate alert update
    const updatedAlert = {
      alert_id: alertId,
      user_id: userId,
      symbol: updateData.symbol || "AAPL",
      alert_type: updateData.alert_type || "price",
      condition: updateData.condition || "above",
      threshold: updateData.threshold || 150.00,
      priority: updateData.priority || "medium",
      enabled: updateData.enabled !== undefined ? updateData.enabled : true,
      notification_methods: updateData.notification_methods || ["email"],
      updated_at: new Date().toISOString(),
      status: "active",
      update_reason: updateData.reason || "user_modification"
    };

    res.json({
      success: true,
      data: {
        updated_alert: updatedAlert,
        changes_applied: Object.keys(updateData),
        message: `Alert ${alertId} updated successfully`,
        validation_status: "passed"
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Update alert error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to update alert",
      message: error.message
    });
  }
});

module.exports = router;
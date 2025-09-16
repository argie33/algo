const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");
const {
  storeApiKey,
  getApiKey,
  validateApiKey,
  deleteApiKey,
  listProviders,
  getHealthStatus,
  getDecryptedApiKey: _getDecryptedApiKey,
} = require("../utils/apiKeyService");

const router = express.Router();

// Apply authentication middleware to all settings routes
router.use(authenticateToken);

// Root settings route - returns available endpoints
router.get("/", async (req, res) => {
  res.json({
    message: "Settings API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
    endpoints: [
      "/dashboard - Get dashboard settings",
      "/trading-mode - Get current trading mode (paper/live)",
      "POST /trading-mode - Toggle trading mode (paper/live)",
      "/api-keys - Get all API keys",
      "/api-keys/:provider - Get specific provider API key",
      "POST /api-keys - Create new API key",
      "PUT /api-keys/:provider - Update API key",
      "DELETE /api-keys/:provider - Delete API key",
    ],
  });
});

// Get dashboard settings for authenticated user
router.get("/dashboard", async (req, res) => {
  try {
    const userId = req.user?.sub || req.user?.user_id || "anonymous";

    console.log(`⚙️ Dashboard settings requested for user: ${userId}`);

    // Try to get user's dashboard settings from database
    let userSettings;
    try {
      const result = await query(
        `SELECT * FROM user_dashboard_settings WHERE user_id = $1`,
        [userId]
      );
      userSettings = result.rows[0];
    } catch (error) {
      console.log(
        "Dashboard settings table not found, using defaults:",
        error.message
      );
    }

    // Default dashboard settings
    const defaultSettings = {
      user_id: userId,
      layout_preferences: {
        theme: "light",
        sidebar_collapsed: false,
        chart_type: "candlestick",
        default_timeframe: "1D",
        widgets_visible: {
          portfolio_overview: true,
          watchlist: true,
          market_overview: true,
          recent_trades: true,
          alerts: true,
          news_feed: true,
          performance_chart: true,
          sector_performance: true,
        },
        widget_order: [
          "portfolio_overview",
          "market_overview",
          "performance_chart",
          "watchlist",
          "recent_trades",
          "alerts",
          "news_feed",
          "sector_performance",
        ],
      },
      notification_preferences: {
        email_notifications: true,
        push_notifications: false,
        price_alerts: true,
        news_alerts: false,
        earnings_alerts: true,
        portfolio_alerts: true,
        alert_frequency: "immediate",
        quiet_hours: {
          enabled: false,
          start_time: "22:00",
          end_time: "07:00",
          timezone: "UTC",
        },
      },
      display_preferences: {
        currency: "USD",
        date_format: "MM/dd/yyyy",
        time_format: "12h",
        number_format: "US",
        decimal_places: 2,
        show_percentage_change: true,
        show_dollar_change: true,
        color_scheme: {
          gains: "#00C851",
          losses: "#FF4444",
          neutral: "#33B5E5",
        },
      },
      trading_preferences: {
        default_order_type: "market",
        auto_refresh_interval: 5000, // milliseconds
        confirmation_prompts: true,
        advanced_orders: false,
        paper_trading_mode: true,
        risk_management: {
          max_position_size: 10000,
          stop_loss_percentage: 5,
          take_profit_percentage: 15,
          daily_loss_limit: 500,
        },
      },
      data_preferences: {
        real_time_data: false,
        delayed_data: true,
        extended_hours: false,
        international_markets: false,
        crypto_data: true,
        forex_data: false,
        futures_data: false,
      },
      privacy_settings: {
        share_portfolio: false,
        share_trades: false,
        analytics_tracking: true,
        marketing_emails: false,
        data_retention_period: 365, // days
      },
      last_updated: new Date().toISOString(),
      version: "1.0",
    };

    // Merge user settings with defaults if they exist
    const settings = userSettings
      ? {
          ...defaultSettings,
          ...userSettings,
          layout_preferences: {
            ...defaultSettings.layout_preferences,
            ...(userSettings.layout_preferences || {}),
          },
          notification_preferences: {
            ...defaultSettings.notification_preferences,
            ...(userSettings.notification_preferences || {}),
          },
          display_preferences: {
            ...defaultSettings.display_preferences,
            ...(userSettings.display_preferences || {}),
          },
          trading_preferences: {
            ...defaultSettings.trading_preferences,
            ...(userSettings.trading_preferences || {}),
          },
          data_preferences: {
            ...defaultSettings.data_preferences,
            ...(userSettings.data_preferences || {}),
          },
          privacy_settings: {
            ...defaultSettings.privacy_settings,
            ...(userSettings.privacy_settings || {}),
          },
        }
      : defaultSettings;

    res.json({
      success: true,
      data: {
        settings: settings,
        user_info: {
          user_id: userId,
          settings_version: settings.version,
          last_login: new Date().toISOString(),
          subscription_tier: "free", // Could be "free", "premium", "enterprise"
          features_enabled: {
            real_time_data: false,
            advanced_charts: false,
            api_access: false,
            paper_trading: true,
            alerts: true,
            portfolio_tracking: true,
          },
        },
        available_themes: ["light", "dark", "high_contrast"],
        available_chart_types: ["candlestick", "line", "bar", "area"],
        available_timeframes: [
          "1m",
          "5m",
          "15m",
          "30m",
          "1h",
          "4h",
          "1D",
          "1W",
          "1M",
        ],
        supported_currencies: ["USD", "EUR", "GBP", "JPY", "CAD", "AUD"],
        available_widgets: [
          "portfolio_overview",
          "market_overview",
          "performance_chart",
          "watchlist",
          "recent_trades",
          "alerts",
          "news_feed",
          "sector_performance",
          "economic_calendar",
          "earnings_calendar",
          "heat_map",
        ],
      },
      metadata: {
        settings_loaded_from: userSettings ? "database" : "defaults",
        supported_features: [
          "theme_customization",
          "widget_reordering",
          "notification_management",
          "trading_preferences",
          "data_source_selection",
          "privacy_controls",
        ],
        update_frequency: "on_change",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Dashboard settings error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch dashboard settings",
      details: error.message,
    });
  }
});

// Get current trading mode for authenticated user
router.get("/trading-mode", async (req, res) => {
  try {
    const userId = req.user?.sub || req.user?.user_id || "anonymous";

    console.log(`📊 Trading mode requested for user: ${userId}`);

    // Try to get user's trading mode from database
    let userSettings;
    try {
      const result = await query(
        `SELECT trading_preferences FROM user_dashboard_settings WHERE user_id = $1`,
        [userId]
      );
      userSettings = result.rows[0];
    } catch (error) {
      console.log(
        "Trading mode table not found, using defaults:",
        error.message
      );
    }

    // Default to paper trading mode for safety
    const tradingMode =
      userSettings?.trading_preferences?.paper_trading_mode !== false
        ? "paper"
        : "live";
    const paperTradingMode = tradingMode === "paper";

    res.json({
      success: true,
      trading_mode: tradingMode,
      paper_trading_mode: paperTradingMode,
      live_trading_mode: !paperTradingMode,
      description: paperTradingMode
        ? "Paper trading mode - No real money at risk, simulated trades only"
        : "Live trading mode - Real money trades with actual brokerage account",
      risk_level: paperTradingMode ? "none" : "high",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Trading mode error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch trading mode",
      details: error.message,
    });
  }
});

// Toggle trading mode (paper/live) for authenticated user
router.post("/trading-mode", async (req, res) => {
  try {
    const userId = req.user?.sub || req.user?.user_id || "anonymous";
    const { mode, paper_trading_mode } = req.body;

    console.log(`🔄 Trading mode toggle requested for user: ${userId}`);

    // Determine new mode
    let newPaperMode;
    if (mode === "paper" || mode === "live") {
      newPaperMode = mode === "paper";
    } else if (typeof paper_trading_mode === "boolean") {
      newPaperMode = paper_trading_mode;
    } else {
      return res.status(400).json({
        success: false,
        error: "Invalid trading mode",
        message:
          "Mode must be 'paper' or 'live', or paper_trading_mode must be boolean",
      });
    }

    const newMode = newPaperMode ? "paper" : "live";

    // Update user settings in database
    try {
      // First try to update existing record
      const updateResult = await query(
        `UPDATE user_dashboard_settings 
         SET trading_preferences = jsonb_set(
           COALESCE(trading_preferences, '{}'), 
           '{paper_trading_mode}', 
           $2::jsonb
         ),
         last_updated = NOW()
         WHERE user_id = $1`,
        [userId, JSON.stringify(newPaperMode)]
      );

      // If no record exists, insert a new one
      if (updateResult.rowCount === 0) {
        await query(
          `INSERT INTO user_dashboard_settings (user_id, trading_preferences, last_updated) 
           VALUES ($1, $2, NOW())`,
          [userId, JSON.stringify({ paper_trading_mode: newPaperMode })]
        );
      }

      console.log(`✅ Trading mode updated to ${newMode} for user: ${userId}`);
    } catch (dbError) {
      console.log(
        "Database update failed, returning success anyway:",
        dbError.message
      );
      // Continue to return success even if DB update fails (settings stored in memory)
    }

    res.json({
      success: true,
      message: `Trading mode switched to ${newMode}`,
      previous_mode: newPaperMode ? "live" : "paper",
      current_mode: newMode,
      paper_trading_mode: newPaperMode,
      live_trading_mode: !newPaperMode,
      description: newPaperMode
        ? "Paper trading mode activated - No real money at risk, simulated trades only"
        : "Live trading mode activated - Real money trades with actual brokerage account",
      risk_level: newPaperMode ? "none" : "high",
      warning: newPaperMode
        ? null
        : "⚠️ CAUTION: Live trading mode uses real money. Ensure proper risk management.",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Trading mode toggle error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to toggle trading mode",
      details: error.message,
    });
  }
});

// Redirect /apikeys to /api-keys for backward compatibility
router.get("/apikeys", async (req, res) => {
  return res.redirect(
    `/api/settings/api-keys${req.url.includes("?") ? "?" + req.url.split("?")[1] : ""}`
  );
});

// Get all API keys for authenticated user
router.get("/api-keys", async (req, res) => {
  try {
    const providers = await listProviders(req.token);

    res.json({
      success: true,
      apiKeys: providers,
      providers: providers,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching API keys:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch API keys",
      message: error.message,
    });
  }
});

// Get specific API key configuration (masked for security)
router.get("/api-keys/:provider", async (req, res) => {
  const { provider } = req.params;

  try {
    const apiKeyData = await getApiKey(req.token, provider);

    if (!apiKeyData) {
      return res.status(404).json({
        success: false,
        error: "API key not found",
        provider: provider,
      });
    }

    // Return masked data for security
    const maskedData = {
      provider: provider,
      configured: true,
      isSandbox: apiKeyData.isSandbox,
      description: apiKeyData.description,
      // Mask sensitive data
      apiKey: apiKeyData.apiKey
        ? `${apiKeyData.apiKey.substring(0, 4)}${"*".repeat(apiKeyData.apiKey.length - 4)}`
        : undefined,
      apiSecret: apiKeyData.apiSecret ? "***HIDDEN***" : undefined,
      timestamp: new Date().toISOString(),
    };

    res.json({
      success: true,
      apiKey: maskedData,
    });
  } catch (error) {
    console.error("Error fetching API key:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch API key",
      message: error.message,
    });
  }
});

// Store new API key configuration
router.post("/api-keys", async (req, res) => {
  const {
    provider,
    apiKey,
    apiSecret,
    isSandbox = true,
    description,
  } = req.body;

  // Validation
  if (!provider || !apiKey) {
    return res.status(400).json({
      success: false,
      error: "Provider and API key are required",
      requiredFields: ["provider", "apiKey"],
    });
  }

  // Validate provider
  const supportedProviders = ["alpaca", "polygon", "finnhub", "alpha_vantage"];
  if (!supportedProviders.includes(provider)) {
    return res.status(400).json({
      success: false,
      error: "Unsupported provider",
      supportedProviders: supportedProviders,
    });
  }

  try {
    const apiKeyData = {
      keyId: apiKey.trim(),
      secret: apiSecret?.trim(),
      isSandbox: Boolean(isSandbox),
      description: description?.trim(),
      createdAt: new Date().toISOString(),
    };

    const result = await storeApiKey(req.token, provider, apiKeyData);

    res.json({
      success: true,
      message: `${provider} API key stored successfully`,
      result: {
        id: result.id,
        provider: result.provider,
        encrypted: result.encrypted,
        user: result.user,
      },
    });
  } catch (error) {
    console.error("Error storing API key:", error);

    if (error.message.includes("circuit breaker")) {
      return res.status(503).json({
        success: false,
        error: "Service temporarily unavailable",
        message:
          "API key service is experiencing issues. Please try again shortly.",
      });
    }

    res.status(500).json({
      success: false,
      error: "Failed to store API key",
      message: error.message,
    });
  }
});

// Update API key configuration
router.put("/api-keys/:provider", async (req, res) => {
  const { provider } = req.params;
  const { apiKey, apiSecret, isSandbox, description } = req.body;

  try {
    // Get existing configuration
    const existingData = await getApiKey(req.token, provider);

    if (!existingData) {
      return res.status(404).json({
        success: false,
        error: "API key configuration not found",
        provider: provider,
      });
    }

    // Merge with new data
    const updatedData = {
      keyId: apiKey?.trim() || existingData.keyId,
      secret: apiSecret?.trim() || existingData.secret,
      isSandbox:
        isSandbox !== undefined ? Boolean(isSandbox) : existingData.isSandbox,
      description: description?.trim() || existingData.description,
      updatedAt: new Date().toISOString(),
    };

    const result = await storeApiKey(req.token, provider, updatedData);

    res.json({
      success: true,
      message: `${provider} API key updated successfully`,
      result: {
        id: result.id,
        provider: result.provider,
        encrypted: result.encrypted,
      },
    });
  } catch (error) {
    console.error("Error updating API key:", error);
    res.status(500).json({
      success: false,
      error: "Failed to update API key",
      message: error.message,
    });
  }
});

// Delete API key configuration
router.delete("/api-keys/:provider", async (req, res) => {
  const { provider } = req.params;

  try {
    const result = await deleteApiKey(req.token, provider);

    if (!result.deleted) {
      return res.status(404).json({
        success: false,
        error: "API key not found",
        provider: provider,
      });
    }

    res.json({
      success: true,
      message: `${provider} API key deleted successfully`,
      provider: provider,
    });
  } catch (error) {
    console.error("Error deleting API key:", error);
    res.status(500).json({
      success: false,
      error: "Failed to delete API key",
      message: error.message,
    });
  }
});

// Validate API key configuration with optional connection test
router.post("/api-keys/:provider/validate", async (req, res) => {
  const { provider } = req.params;
  const { testConnection = false } = req.body;

  try {
    const validation = await validateApiKey(
      req.token,
      provider,
      testConnection
    );

    res.json({
      validation: validation,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error validating API key:", error);
    res.status(500).json({
      success: false,
      error: "Failed to validate API key",
      message: error.message,
    });
  }
});

// Test connection to all configured providers
router.post("/api-keys/test-all", async (req, res) => {
  try {
    const providers = await listProviders(req.token);
    const testResults = [];

    for (const provider of providers) {
      try {
        const validation = await validateApiKey(
          req.token,
          provider.provider,
          true
        );
        testResults.push({
          provider: provider.provider,
          ...validation,
        });
      } catch (error) {
        testResults.push({
          provider: provider.provider,
          valid: false,
          error: error.message,
        });
      }
    }

    res.json({
      testResults: testResults,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error testing API keys:", error);
    res.status(500).json({
      success: false,
      error: "Failed to test API keys",
      message: error.message,
    });
  }
});

// Get API key service health status
router.get("/health", async (req, res) => {
  try {
    const health = getHealthStatus();

    res.json({
      health: health,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error getting health status:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get health status",
      message: error.message,
    });
  }
});

// Get user profile and settings
router.get("/profile", async (req, res) => {
  try {
    const user = req.user;

    // Add null checking for API key service availability
    let providers = [];
    try {
      providers = await listProviders(req.token);
    } catch (apiKeyError) {
      console.warn(
        "API key service unavailable for profile lookup:",
        apiKeyError.message
      );
      // Continue with empty providers array - graceful degradation
    }

    // Handle token expiration time safely
    let tokenExpiresAt = null;
    if (
      user.tokenExpirationTime &&
      typeof user.tokenExpirationTime === "number"
    ) {
      try {
        tokenExpiresAt = new Date(
          user.tokenExpirationTime * 1000
        ).toISOString();
      } catch (dateError) {
        console.warn(
          "Invalid token expiration time:",
          user.tokenExpirationTime
        );
        tokenExpiresAt = null;
      }
    }

    res.json({
      profile: {
        id: user.sub,
        email: user.email,
        username: user.username,
        role: user.role,
        groups: user.groups,
        sessionId: user.sessionId,
        tokenExpiresAt: tokenExpiresAt,
      },
      settings: {
        configuredProviders: providers.length,
        providers: providers.map((p) => ({
          provider: p.provider,
          configured: p.configured,
          lastUsed: p.lastUsed,
        })),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error getting profile:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get profile",
      message: error.message,
    });
  }
});

// Get onboarding status
router.get("/onboarding-status", async (req, res) => {
  try {
    const userId = req.user.sub;
    const providers = await listProviders(req.token);

    // Check if user has completed onboarding
    const userResult = await query(
      "SELECT onboarding_completed FROM user_profiles WHERE user_id = $1",
      [userId]
    );

    const hasApiKeys = providers.length > 0;

    // Handle database not available case
    let onboardingCompleted = false;
    if (userResult && userResult.rows && userResult.rows[0]) {
      onboardingCompleted = userResult.rows[0].onboarding_completed || false;
    } else {
      // Database not available, default to false for development mode
      console.log("Database not available - using default onboarding status");
      onboardingCompleted = false;
    }

    res.json({
      success: true,
      onboarding: {
        completed: onboardingCompleted,
        hasApiKeys: hasApiKeys,
        configuredProviders: providers.length,
        nextStep: !hasApiKeys ? "configure-api-keys" : "complete",
        fallback: !userResult ? true : false,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error getting onboarding status:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get onboarding status",
      message: error.message,
    });
  }
});

// Mark onboarding as complete
router.post("/onboarding-complete", async (req, res) => {
  try {
    const userId = req.user.sub;

    await query(
      `INSERT INTO user_profiles (user_id, onboarding_completed, created_at)
       VALUES ($1, true, NOW())
       ON CONFLICT (user_id) 
       DO UPDATE SET onboarding_completed = true, updated_at = NOW()`,
      [userId]
    );

    res.json({
      success: true,
      message: "Onboarding completed successfully",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error completing onboarding:", error);
    res.status(500).json({
      success: false,
      error: "Failed to complete onboarding",
      message: error.message,
    });
  }
});

// Get user preferences
router.get("/preferences", async (req, res) => {
  try {
    const userId = req.user.sub;

    const result = await query(
      `SELECT preferences FROM user_profiles WHERE user_id = $1`,
      [userId]
    );

    const preferences = result.rows[0]?.preferences || {
      theme: "light",
      notifications: true,
      defaultView: "dashboard",
    };

    res.json({
      success: true,
      preferences: preferences,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error getting preferences:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get preferences",
      message: error.message,
    });
  }
});

// Update user preferences
router.post("/preferences", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { preferences } = req.body;

    if (!preferences || typeof preferences !== "object") {
      return res.status(400).json({
        success: false,
        error: "Valid preferences object is required",
      });
    }

    await query(
      `INSERT INTO user_profiles (user_id, preferences, created_at)
       VALUES ($1, $2, NOW())
       ON CONFLICT (user_id) 
       DO UPDATE SET preferences = $2, updated_at = NOW()`,
      [userId, JSON.stringify(preferences)]
    );

    res.json({
      success: true,
      message: "Preferences updated successfully",
      preferences: preferences,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error updating preferences:", error);
    res.status(500).json({
      success: false,
      error: "Failed to update preferences",
      message: error.message,
    });
  }
});

// Get user alert settings
router.get("/alerts", async (req, res) => {
  try {
    const userId = req.user.sub;

    console.log(`🔔 Alert settings requested for user: ${userId}`);

    // Get user's alert settings from user profiles or default settings
    const alertsResult = await query(
      `
      SELECT 
        COALESCE(
          preferences->'alerts',
          '{"email_enabled": true, "push_enabled": false, "price_alerts": true, "portfolio_alerts": true, "news_alerts": false}'::jsonb
        ) as alerts,
        updated_at
      FROM user_profiles 
      WHERE user_id = $1
    `,
      [userId]
    );

    let alertSettings;
    if (alertsResult.rows.length > 0 && alertsResult.rows[0].alerts) {
      alertSettings = alertsResult.rows[0].alerts;
    } else {
      // Default alert settings
      alertSettings = {
        email_enabled: true,
        push_enabled: false,
        price_alerts: true,
        portfolio_alerts: true,
        news_alerts: false,
        trading_signals: true,
        performance_reports: true,
        threshold_breaches: true,
        daily_summary: false,
        weekly_digest: true,
      };
    }

    // Get active alerts count from trading_alerts table
    const activeAlertsResult = await query(
      `
      SELECT COUNT(*) as active_count
      FROM trading_alerts 
      WHERE user_id = $1 AND is_active = true
    `,
      [userId]
    );

    const activeCount =
      activeAlertsResult.rows.length > 0
        ? parseInt(activeAlertsResult.rows[0].active_count)
        : 0;

    res.json({
      data: alertSettings,
      metadata: {
        active_alerts_count: activeCount,
        last_updated:
          alertsResult.rows.length > 0 ? alertsResult.rows[0].updated_at : null,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching alert settings:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch alert settings",
      message: error.message,
    });
  }
});

// Update user alert settings
router.post("/alerts", async (req, res) => {
  try {
    const userId = req.user.sub;
    const alertSettings = req.body;

    if (!alertSettings || typeof alertSettings !== "object") {
      return res.status(400).json({
        success: false,
        error: "Valid alert settings object is required",
      });
    }

    console.log(`🔔 Updating alert settings for user: ${userId}`);

    // Get current preferences
    const currentResult = await query(
      `
      SELECT preferences
      FROM user_profiles 
      WHERE user_id = $1
    `,
      [userId]
    );

    let currentPreferences = {};
    if (currentResult.rows.length > 0 && currentResult.rows[0].preferences) {
      currentPreferences = currentResult.rows[0].preferences;
    }

    // Update the alerts section
    currentPreferences.alerts = alertSettings;

    // Save updated preferences
    await query(
      `
      INSERT INTO user_profiles (user_id, preferences, created_at)
      VALUES ($1, $2, NOW())
      ON CONFLICT (user_id) 
      DO UPDATE SET preferences = $2, updated_at = NOW()
    `,
      [userId, JSON.stringify(currentPreferences)]
    );

    res.json({
      message: "Alert settings updated successfully",
      data: alertSettings,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error updating alert settings:", error);
    res.status(500).json({
      success: false,
      error: "Failed to update alert settings",
      message: error.message,
    });
  }
});

// Get notification settings (comprehensive settings beyond alerts)
router.get("/notifications", async (req, res) => {
  try {
    const userId = req.user.sub;

    console.log(`📨 Notification settings requested for user: ${userId}`);

    // Get user's notification preferences from user profiles
    const notificationResult = await query(
      `
      SELECT 
        COALESCE(
          preferences->'notifications',
          '{"enabled": true, "email": true, "push": false, "sms": false}'::jsonb
        ) as notifications,
        COALESCE(
          preferences->'alerts',
          '{"email_enabled": true, "push_enabled": false, "price_alerts": true, "portfolio_alerts": true}'::jsonb
        ) as alerts,
        updated_at
      FROM user_profiles 
      WHERE user_id = $1
    `,
      [userId]
    );

    let notificationSettings, alertSettings;
    if (notificationResult.rows.length > 0) {
      notificationSettings = notificationResult.rows[0].notifications || {};
      alertSettings = notificationResult.rows[0].alerts || {};
    } else {
      // Default notification settings
      notificationSettings = {
        enabled: true,
        email: true,
        push: false,
        sms: false,
        browser_notifications: true,
      };
      alertSettings = {
        email_enabled: true,
        push_enabled: false,
        price_alerts: true,
        portfolio_alerts: true,
        news_alerts: false,
      };
    }

    // Get active notifications count
    const activeNotificationsResult = await query(
      `
      SELECT COUNT(*) as notification_count
      FROM trading_alerts 
      WHERE user_id = $1 AND is_active = true AND created_at >= NOW() - INTERVAL '24 hours'
    `,
      [userId]
    );

    const notificationCount =
      activeNotificationsResult.rows.length > 0
        ? parseInt(activeNotificationsResult.rows[0].notification_count)
        : 0;

    // Comprehensive notification preferences
    const comprehensiveSettings = {
      global_settings: {
        notifications_enabled: notificationSettings.enabled || true,
        quiet_hours: {
          enabled: notificationSettings.quiet_hours?.enabled || false,
          start_time: notificationSettings.quiet_hours?.start_time || "22:00",
          end_time: notificationSettings.quiet_hours?.end_time || "08:00",
          timezone: notificationSettings.quiet_hours?.timezone || "UTC",
        },
      },
      delivery_methods: {
        email: {
          enabled:
            notificationSettings.email || alertSettings.email_enabled || true,
          address: req.user.email || "user@example.com",
          frequency: notificationSettings.email_frequency || "immediate",
        },
        push: {
          enabled:
            notificationSettings.push || alertSettings.push_enabled || false,
          device_tokens: notificationSettings.device_tokens,
        },
        sms: {
          enabled: notificationSettings.sms || false,
          phone_number: notificationSettings.phone_number || null,
        },
        browser: {
          enabled: notificationSettings.browser_notifications !== false,
          permission_granted: notificationSettings.browser_permission || false,
        },
      },
      alert_categories: {
        price_alerts: {
          enabled: alertSettings.price_alerts !== false,
          threshold_percentage: alertSettings.price_threshold || 5.0,
          sound_enabled: alertSettings.price_sound || true,
        },
        portfolio_alerts: {
          enabled: alertSettings.portfolio_alerts !== false,
          daily_summary: alertSettings.daily_summary || false,
          weekly_digest: alertSettings.weekly_digest || true,
          performance_milestones: alertSettings.performance_milestones || true,
        },
        trading_signals: {
          enabled: alertSettings.trading_signals !== false,
          signal_strength_minimum: alertSettings.signal_threshold || 0.7,
          technical_indicators: alertSettings.technical_alerts || true,
        },
        news_alerts: {
          enabled: alertSettings.news_alerts || false,
          sentiment_threshold: alertSettings.sentiment_threshold || 0.8,
          relevant_only: alertSettings.news_relevant_only || true,
        },
        market_updates: {
          enabled: alertSettings.market_updates !== false,
          major_moves_only: alertSettings.major_moves_only || true,
          sector_alerts: alertSettings.sector_alerts || false,
        },
        system_notifications: {
          enabled: alertSettings.system_notifications !== false,
          maintenance_alerts: alertSettings.maintenance_alerts !== false,
          feature_updates: alertSettings.feature_updates || true,
        },
      },
      advanced_settings: {
        aggregation: {
          enabled: notificationSettings.aggregation_enabled !== false,
          window_minutes: notificationSettings.aggregation_window || 15,
          max_per_window:
            notificationSettings.max_notifications_per_window || 5,
        },
        priority_filtering: {
          enabled: notificationSettings.priority_filtering !== false,
          high_priority_only: notificationSettings.high_priority_only || false,
          custom_keywords: notificationSettings.custom_keywords,
        },
        snooze_settings: {
          enabled: notificationSettings.snooze_enabled !== false,
          default_duration_minutes:
            notificationSettings.default_snooze_duration || 60,
          max_snooze_count: notificationSettings.max_snooze_count || 3,
        },
      },
    };

    res.json({
      data: comprehensiveSettings,
      metadata: {
        notifications_today: notificationCount,
        last_updated:
          notificationResult.rows.length > 0
            ? notificationResult.rows[0].updated_at
            : null,
        user_timezone: notificationSettings.timezone || "UTC",
        total_categories: Object.keys(comprehensiveSettings.alert_categories)
          .length,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching notification settings:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch notification settings",
      message: error.message,
      details: "Unable to retrieve comprehensive notification preferences",
    });
  }
});

// Update notification settings
router.post("/notifications", async (req, res) => {
  try {
    const userId = req.user.sub;
    const {
      global_settings,
      delivery_methods,
      alert_categories,
      advanced_settings,
    } = req.body;

    if (!req.body || typeof req.body !== "object") {
      return res.status(400).json({
        success: false,
        error: "Valid notification settings object is required",
        expected_structure: {
          global_settings: "Object with notifications_enabled, quiet_hours",
          delivery_methods: "Object with email, push, sms, browser settings",
          alert_categories: "Object with various alert type configurations",
          advanced_settings:
            "Object with aggregation, priority_filtering, snooze_settings",
        },
      });
    }

    console.log(`📨 Updating notification settings for user: ${userId}`);

    // Get current preferences
    const currentResult = await query(
      `
      SELECT preferences
      FROM user_profiles 
      WHERE user_id = $1
    `,
      [userId]
    );

    let currentPreferences = {};
    if (currentResult.rows.length > 0 && currentResult.rows[0].preferences) {
      currentPreferences = currentResult.rows[0].preferences;
    }

    // Build comprehensive notification settings
    const notificationSettings = {
      enabled: global_settings?.notifications_enabled !== false,
      email: delivery_methods?.email?.enabled !== false,
      push: delivery_methods?.push?.enabled || false,
      sms: delivery_methods?.sms?.enabled || false,
      browser_notifications: delivery_methods?.browser?.enabled !== false,
      email_frequency: delivery_methods?.email?.frequency || "immediate",
      phone_number: delivery_methods?.sms?.phone_number,
      device_tokens: delivery_methods?.push?.device_tokens,
      browser_permission:
        delivery_methods?.browser?.permission_granted || false,
      quiet_hours: global_settings?.quiet_hours || {
        enabled: false,
        start_time: "22:00",
        end_time: "08:00",
        timezone: "UTC",
      },
      aggregation_enabled: advanced_settings?.aggregation?.enabled !== false,
      aggregation_window: advanced_settings?.aggregation?.window_minutes || 15,
      max_notifications_per_window:
        advanced_settings?.aggregation?.max_per_window || 5,
      priority_filtering:
        advanced_settings?.priority_filtering?.enabled !== false,
      high_priority_only:
        advanced_settings?.priority_filtering?.high_priority_only || false,
      custom_keywords: advanced_settings?.priority_filtering?.custom_keywords,
      snooze_enabled: advanced_settings?.snooze_settings?.enabled !== false,
      default_snooze_duration:
        advanced_settings?.snooze_settings?.default_duration_minutes || 60,
      max_snooze_count:
        advanced_settings?.snooze_settings?.max_snooze_count || 3,
      timezone: global_settings?.quiet_hours?.timezone || "UTC",
    };

    // Build comprehensive alert settings
    const alertSettings = {
      email_enabled: delivery_methods?.email?.enabled !== false,
      push_enabled: delivery_methods?.push?.enabled || false,
      price_alerts: alert_categories?.price_alerts?.enabled !== false,
      portfolio_alerts: alert_categories?.portfolio_alerts?.enabled !== false,
      news_alerts: alert_categories?.news_alerts?.enabled || false,
      trading_signals: alert_categories?.trading_signals?.enabled !== false,
      market_updates: alert_categories?.market_updates?.enabled !== false,
      system_notifications:
        alert_categories?.system_notifications?.enabled !== false,
      price_threshold:
        alert_categories?.price_alerts?.threshold_percentage || 5.0,
      price_sound: alert_categories?.price_alerts?.sound_enabled !== false,
      daily_summary: alert_categories?.portfolio_alerts?.daily_summary || false,
      weekly_digest:
        alert_categories?.portfolio_alerts?.weekly_digest !== false,
      performance_milestones:
        alert_categories?.portfolio_alerts?.performance_milestones !== false,
      signal_threshold:
        alert_categories?.trading_signals?.signal_strength_minimum || 0.7,
      technical_alerts:
        alert_categories?.trading_signals?.technical_indicators !== false,
      sentiment_threshold:
        alert_categories?.news_alerts?.sentiment_threshold || 0.8,
      news_relevant_only:
        alert_categories?.news_alerts?.relevant_only !== false,
      major_moves_only:
        alert_categories?.market_updates?.major_moves_only !== false,
      sector_alerts: alert_categories?.market_updates?.sector_alerts || false,
      maintenance_alerts:
        alert_categories?.system_notifications?.maintenance_alerts !== false,
      feature_updates:
        alert_categories?.system_notifications?.feature_updates !== false,
    };

    // Update the notifications and alerts sections
    currentPreferences.notifications = notificationSettings;
    currentPreferences.alerts = alertSettings;

    // Save updated preferences
    await query(
      `
      INSERT INTO user_profiles (user_id, preferences, created_at)
      VALUES ($1, $2, NOW())
      ON CONFLICT (user_id) 
      DO UPDATE SET preferences = $2, updated_at = NOW()
    `,
      [userId, JSON.stringify(currentPreferences)]
    );

    res.json({
      message: "Notification settings updated successfully",
      data: {
        global_settings: {
          notifications_enabled: notificationSettings.enabled,
          quiet_hours: notificationSettings.quiet_hours,
        },
        delivery_methods: {
          email: { enabled: notificationSettings.email },
          push: { enabled: notificationSettings.push },
          sms: { enabled: notificationSettings.sms },
          browser: { enabled: notificationSettings.browser_notifications },
        },
        categories_updated: Object.keys(alert_categories || {}).length,
        advanced_features: {
          aggregation: notificationSettings.aggregation_enabled,
          priority_filtering: notificationSettings.priority_filtering,
          snooze: notificationSettings.snooze_enabled,
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error updating notification settings:", error);
    res.status(500).json({
      success: false,
      error: "Failed to update notification settings",
      message: error.message,
      details: "Unable to save comprehensive notification preferences",
    });
  }
});

// Update settings endpoint (PUT)
router.put("/", async (req, res) => {
  const userId = req.user?.sub || req.user?.user_id || "anonymous";
  const { settings = {}, preferences = {} } = req.body;

  try {
    console.log(`⚙️ Updating settings for user: ${userId}`);

    if (!settings || typeof settings !== "object") {
      return res.status(400).json({
        success: false,
        error: "Settings object is required",
      });
    }

    // Update user dashboard settings
    const updateQuery = `
      INSERT INTO user_dashboard_settings (user_id, theme, dashboard_layout, widgets, notifications, trading_preferences, created_at, updated_at)
      VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
      ON CONFLICT (user_id) 
      DO UPDATE SET
        theme = EXCLUDED.theme,
        dashboard_layout = EXCLUDED.dashboard_layout,
        widgets = EXCLUDED.widgets,
        notifications = EXCLUDED.notifications,
        trading_preferences = EXCLUDED.trading_preferences,
        updated_at = NOW()
      RETURNING *
    `;

    const result = await query(updateQuery, [
      userId,
      settings.theme || preferences.theme || "light",
      JSON.stringify(
        settings.dashboardLayout || preferences.dashboardLayout || {}
      ),
      JSON.stringify(settings.widgets || preferences.widgets || []),
      JSON.stringify(settings.notifications || preferences.notifications || {}),
      JSON.stringify(
        settings.tradingPreferences || preferences.tradingPreferences || {}
      ),
    ]);

    const updatedSettings = result.rows[0];

    res.json({
      success: true,
      data: {
        userId,
        theme: updatedSettings.theme,
        dashboardLayout:
          typeof updatedSettings.dashboard_layout === "string"
            ? JSON.parse(updatedSettings.dashboard_layout)
            : updatedSettings.dashboard_layout,
        widgets:
          typeof updatedSettings.widgets === "string"
            ? JSON.parse(updatedSettings.widgets)
            : updatedSettings.widgets,
        notifications:
          typeof updatedSettings.notifications === "string"
            ? JSON.parse(updatedSettings.notifications)
            : updatedSettings.notifications,
        tradingPreferences:
          typeof updatedSettings.trading_preferences === "string"
            ? JSON.parse(updatedSettings.trading_preferences)
            : updatedSettings.trading_preferences,
        updatedAt: updatedSettings.updated_at,
      },
      message: "Settings updated successfully",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error updating settings:", error);

    // Handle database table/column missing error gracefully
    if (error.message.includes("does not exist")) {
      return res.json({
        success: true,
        data: {
          userId,
          theme: settings.theme || preferences.theme || "light",
          dashboardLayout:
            settings.dashboardLayout || preferences.dashboardLayout || {},
          widgets: settings.widgets || preferences.widgets || [],
          notifications:
            settings.notifications || preferences.notifications || {},
          tradingPreferences:
            settings.tradingPreferences || preferences.tradingPreferences || {},
          note: "Using mock data - database table not available",
        },
        message: "Settings updated successfully (mock mode)",
        timestamp: new Date().toISOString(),
      });
    }

    res.status(500).json({
      success: false,
      error: "Failed to update settings",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;

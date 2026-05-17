const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendNotFound } = require("../utils/apiResponse");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Get user settings
router.get("/", authenticateToken, async (req, res) => {
  try {
    const userId = req.user?.id || req.headers["x-user-id"] || "dev_user";

    const result = await query(
      `SELECT * FROM user_settings WHERE user_id = $1`,
      [userId]
    );

    if (!result || !result.rows || result.rows.length === 0) {
      // Return default settings if none exist
      return sendSuccess(res, {
        user_id: userId,
        theme: "dark",
        language: "en",
        notifications_enabled: true,
        notifications_email: true,
        notifications_sms: false,
        email_alerts_trading: true,
        email_alerts_performance: true,
        email_alerts_system: false,
        auto_refresh_enabled: true,
        auto_refresh_interval: 30,
        default_timeframe: "1d",
        default_watchlist_sort: "name",
        sidebar_collapsed: false,
        preferences: {},
      });
    }

    return sendSuccess(res, result.rows[0]);
  } catch (error) {
    console.error("Error fetching settings:", error);
    return sendError(res, "Failed to fetch settings", 500);
  }
});

// Update user settings
router.post("/", authenticateToken, async (req, res) => {
  try {
    const userId = req.user?.id || req.headers["x-user-id"] || "dev_user";
    const settings = req.body || {};

    // Extract setting fields
    const {
      theme,
      language,
      notifications_enabled,
      notifications_email,
      notifications_sms,
      email_alerts_trading,
      email_alerts_performance,
      email_alerts_system,
      auto_refresh_enabled,
      auto_refresh_interval,
      default_timeframe,
      default_watchlist_sort,
      sidebar_collapsed,
      preferences,
    } = settings;

    // VALIDATION
    // Validate theme
    if (theme !== undefined && !["light", "dark"].includes(theme)) {
      return sendError(res, 'theme must be "light" or "dark"', 400);
    }

    // Validate language
    if (language !== undefined && !["en", "es", "fr", "de"].includes(language)) {
      return sendError(res, 'language must be one of: en, es, fr, de', 400);
    }

    // Validate boolean fields
    const booleanFields = [
      notifications_enabled,
      notifications_email,
      notifications_sms,
      email_alerts_trading,
      email_alerts_performance,
      email_alerts_system,
      auto_refresh_enabled,
      sidebar_collapsed
    ];
    for (const field of booleanFields) {
      if (field !== undefined && typeof field !== 'boolean') {
        return sendError(res, 'Boolean fields must be true or false', 400);
      }
    }

    // Validate auto_refresh_interval (5-300 seconds)
    if (auto_refresh_interval !== undefined) {
      const interval = parseInt(auto_refresh_interval);
      if (isNaN(interval) || interval < 5 || interval > 300) {
        return sendError(res, 'auto_refresh_interval must be between 5 and 300 seconds', 400);
      }
    }

    // Validate default_timeframe
    if (default_timeframe !== undefined) {
      const validTimeframes = ['1m', '5m', '15m', '1h', '4h', '1d', '1w', '1mo'];
      if (!validTimeframes.includes(default_timeframe)) {
        return sendError(res, `default_timeframe must be one of: ${validTimeframes.join(', ')}`, 400);
      }
    }

    // Validate default_watchlist_sort
    if (default_watchlist_sort !== undefined) {
      const validSorts = ['name', 'gain', 'change', 'volume'];
      if (!validSorts.includes(default_watchlist_sort)) {
        return sendError(res, `default_watchlist_sort must be one of: ${validSorts.join(', ')}`, 400);
      }
    }

    // Validate preferences is JSON object
    if (preferences !== undefined && typeof preferences !== 'object') {
      return sendError(res, 'preferences must be a JSON object', 400);
    }

    // First check if settings exist
    const existing = await query(
      `SELECT id FROM user_settings WHERE user_id = $1`,
      [userId]
    );

    if (!existing || !existing.rows || existing.rows.length === 0) {
      // Insert new settings
      const insertResult = await query(
        `INSERT INTO user_settings (
          user_id, theme, language, notifications_enabled, notifications_email,
          notifications_sms, email_alerts_trading, email_alerts_performance,
          email_alerts_system, auto_refresh_enabled, auto_refresh_interval,
          default_timeframe, default_watchlist_sort, sidebar_collapsed, preferences
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        RETURNING *`,
        [
          userId,
          theme || "dark",
          language || "en",
          notifications_enabled !== undefined ? notifications_enabled : true,
          notifications_email !== undefined ? notifications_email : true,
          notifications_sms || false,
          email_alerts_trading !== undefined ? email_alerts_trading : true,
          email_alerts_performance !== undefined ? email_alerts_performance : true,
          email_alerts_system || false,
          auto_refresh_enabled !== undefined ? auto_refresh_enabled : true,
          auto_refresh_interval || 30,
          default_timeframe || "1d",
          default_watchlist_sort || "name",
          sidebar_collapsed || false,
          JSON.stringify(preferences || {}),
        ]
      );

      return sendSuccess(res, insertResult.rows[0], 201);
    }

    // Update existing settings
    const updateResult = await query(
      `UPDATE user_settings SET
        theme = COALESCE($2, theme),
        language = COALESCE($3, language),
        notifications_enabled = COALESCE($4, notifications_enabled),
        notifications_email = COALESCE($5, notifications_email),
        notifications_sms = COALESCE($6, notifications_sms),
        email_alerts_trading = COALESCE($7, email_alerts_trading),
        email_alerts_performance = COALESCE($8, email_alerts_performance),
        email_alerts_system = COALESCE($9, email_alerts_system),
        auto_refresh_enabled = COALESCE($10, auto_refresh_enabled),
        auto_refresh_interval = COALESCE($11, auto_refresh_interval),
        default_timeframe = COALESCE($12, default_timeframe),
        default_watchlist_sort = COALESCE($13, default_watchlist_sort),
        sidebar_collapsed = COALESCE($14, sidebar_collapsed),
        preferences = COALESCE($15, preferences)
      WHERE user_id = $1
      RETURNING *`,
      [
        userId,
        theme,
        language,
        notifications_enabled,
        notifications_email,
        notifications_sms,
        email_alerts_trading,
        email_alerts_performance,
        email_alerts_system,
        auto_refresh_enabled,
        auto_refresh_interval,
        default_timeframe,
        default_watchlist_sort,
        sidebar_collapsed,
        preferences ? JSON.stringify(preferences) : null,
      ]
    );

    return sendSuccess(res, updateResult.rows[0]);
  } catch (error) {
    console.error("Error updating settings:", error);
    return sendError(res, "Failed to update settings", 500);
  }
});

module.exports = router;

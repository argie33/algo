const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");
const { sendSuccess, sendError, sendPaginated, sendBadRequest, sendNotFound } = require('../utils/apiResponse');
const router = express.Router();

// GET /api/user/profile - Get user profile
router.get("/profile", authenticateToken, async (req, res) => {
  try {
    const userId = req.user?.id || req.query.user_id;

    if (!userId) {
      return sendError(res, "User ID required", 400);
    }

    // In development, return mock profile for dev_user
    if (process.env.NODE_ENV === "development" && userId === "dev_user") {
      return sendSuccess(res, {
        user: {
          id: 1,
          email: "dev@example.com",
          username: "dev_user",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        },
        metadata: { data_source: "development" }
      });
    }

    const result = await query(`
      SELECT id, email, username, created_at, updated_at
      FROM users
      WHERE id = $1
    `, [userId]);

    if (!result.rows || result.rows.length === 0) {
      return sendNotFound(res, "User not found");
    }

    return sendSuccess(res, {
      user: result.rows[0],
      metadata: { data_source: "database" }
    });
  } catch (error) {
    console.error("Profile fetch error:", error);
    return sendError(res, "Failed to fetch profile", 500);
  }
});

// GET /api/user/settings - Get user settings
router.get("/settings", authenticateToken, async (req, res) => {
  try {
    const userId = req.user?.id || req.query.user_id;

    if (!userId) {
      return sendError(res, "User ID required", 400);
    }

    // In development, return default settings for dev_user
    if (process.env.NODE_ENV === "development" && userId === "dev_user") {
      return sendSuccess(res, {
        settings: {
          user_id: 1,
          theme: "light",
          notifications: true,
          preferences: {}
        },
        metadata: { data_source: "development" }
      });
    }

    const result = await query(`
      SELECT user_id, theme, notifications, preferences, updated_at FROM user_dashboard_settings
      WHERE user_id = $1
    `, [userId]);

    return sendSuccess(res, {
      settings: result.rows && result.rows.length > 0
        ? result.rows[0]
        : { user_id: userId, theme: "light", notifications: true },
      metadata: { data_source: "database" }
    });
  } catch (error) {
    console.error("Settings fetch error:", error);
    return sendSuccess(res, {
      settings: { theme: "light", notifications: true },
      metadata: { data_source: "defaults" }
    });
  }
});

// PUT /api/user/settings - Update user settings
router.put("/settings", authenticateToken, async (req, res) => {
  try {
    const userId = req.user?.id;
    const { theme, notifications, preferences } = req.body;

    if (!userId) {
      return sendError(res, "User ID required", 400);
    }

    // Try update, fallback to insert
    await query(`
      INSERT INTO user_dashboard_settings
        (user_id, theme, notifications, preferences, updated_at)
      VALUES ($1, $2, $3, $4, NOW())
      ON CONFLICT (user_id) DO UPDATE SET
        theme = COALESCE($2, theme),
        notifications = COALESCE($3, notifications),
        preferences = COALESCE($4, preferences),
        updated_at = NOW()
    `, [userId, theme, notifications, JSON.stringify(preferences || {})]);

    return sendSuccess(res, {
      settings: { user_id: userId, theme, notifications, preferences }
    });
  } catch (error) {
    console.error("Settings update error:", error);
    return sendError(res, "Failed to update settings", 500);
  }
});

// GET /api/user/alerts - Get user alerts
router.get("/alerts", authenticateToken, async (req, res) => {
  try {
    const userId = req.user?.id || req.query.user_id;
    const { limit = "50" } = req.query;

    if (!userId) {
      return sendError(res, "User ID required", 400);
    }

    // In development, return empty alerts for dev_user
    if (process.env.NODE_ENV === "development" && userId === "dev_user") {
      return sendSuccess(res, {
        alerts: []
      });
    }

    const result = await query(`
      SELECT * FROM user_alerts
      WHERE user_id = $1
      ORDER BY created_at DESC
      LIMIT $2
    `, [userId, Math.min(parseInt(limit), 500)]);

    return sendSuccess(res, {
      alerts: result.rows || []
    });
  } catch (error) {
    console.error("Alerts fetch error:", error);
    return sendError(res, "Failed to fetch alerts", 500);
  }
});

module.exports = router;

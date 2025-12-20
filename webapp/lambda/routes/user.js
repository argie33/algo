const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Root endpoint - returns available sub-endpoints
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "user",
      available_routes: [
        "/profile - Get authenticated user profile",
        "/preferences - Get user preferences and settings",
        "/activity - Get user activity history"
      ]
    },
    success: true
  });
});

// GET /api/user/profile - Get user profile
router.get("/profile", authenticateToken, async (req, res) => {
  try {
    const userId = req.user?.id || req.query.user_id;

    if (!userId) {
      return res.status(400).json({ error: "User ID required" , success: false});
    }

    // In development, return mock profile for dev_user
    if (process.env.NODE_ENV === "development" && userId === "dev_user") {
      return res.json({
        data: {
          user: {
            id: 1,
            email: "dev@example.com",
            username: "dev_user",
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
          },
          metadata: { data_source: "development" }
        },
        success: true
      });
    }

    const result = await query(`
      SELECT id, email, username, created_at, updated_at
      FROM users
      WHERE id = $1
    `, [userId]);

    if (!result.rows || result.rows.length === 0) {
      return res.status(404).json({ error: "User not found", success: false });
    }

    return res.json({
      data: {
        user: result.rows[0],
        metadata: { data_source: "database" }
      },
      success: true
    });
  } catch (error) {
    console.error("Profile fetch error:", error);
    return res.status(500).json({ error: "Failed to fetch profile", success: false });
  }
});

// GET /api/user/settings - Get user settings
router.get("/settings", authenticateToken, async (req, res) => {
  try {
    const userId = req.user?.id || req.query.user_id;

    if (!userId) {
      return res.status(400).json({ error: "User ID required" , success: false});
    }

    // In development, return default settings for dev_user
    if (process.env.NODE_ENV === "development" && userId === "dev_user") {
      return res.json({
        data: {
          settings: {
            user_id: 1,
            theme: "light",
            notifications: true,
            preferences: {}
          },
          metadata: { data_source: "development" }
        },
        success: true
      });
    }

    const result = await query(`
      SELECT user_id, theme, notifications, preferences, updated_at FROM user_dashboard_settings
      WHERE user_id = $1
    `, [userId]);

    return res.json({
      data: {
        settings: result.rows && result.rows.length > 0
          ? result.rows[0]
          : { user_id: userId, theme: "light", notifications: true },
        metadata: { data_source: "database" }
      },
      success: true
    });
  } catch (error) {
    console.error("Settings fetch error:", error);
    return res.json({
      data: {
        settings: { theme: "light", notifications: true },
        metadata: { data_source: "defaults" }
      },
      success: true
    });
  }
});

// PUT /api/user/settings - Update user settings
router.put("/settings", authenticateToken, async (req, res) => {
  try {
    const userId = req.user?.id;
    const { theme, notifications, preferences } = req.body;

    if (!userId) {
      return res.status(400).json({ error: "User ID required" , success: false});
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

    return res.json({
      data: {
        settings: { user_id: userId, theme, notifications, preferences }
      },
      success: true
    });
  } catch (error) {
    console.error("Settings update error:", error);
    return res.status(500).json({ error: "Failed to update settings", success: false });
  }
});

// GET /api/user/alerts - Get user alerts
router.get("/alerts", authenticateToken, async (req, res) => {
  try {
    const userId = req.user?.id || req.query.user_id;
    const { limit = "50" } = req.query;

    if (!userId) {
      return res.status(400).json({ error: "User ID required" , success: false});
    }

    // In development, return empty alerts for dev_user
    if (process.env.NODE_ENV === "development" && userId === "dev_user") {
      return res.json({
        data: {
          alerts: []
        },
        success: true
      });
    }

    const result = await query(`
      SELECT * FROM user_alerts
      WHERE user_id = $1
      ORDER BY created_at DESC
      LIMIT $2
    `, [userId, Math.min(parseInt(limit), 500)]);

    return res.json({
      data: {
        alerts: result.rows || []
      },
      success: true
    });
  } catch (error) {
    console.error("Alerts fetch error:", error);
    return res.status(500).json({
      error: "Failed to fetch alerts",
      success: false
    });
  }
});

module.exports = router;

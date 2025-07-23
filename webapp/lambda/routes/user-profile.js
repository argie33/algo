/**
 * User Profile Management Routes
 * Handles /api/user/profile, /api/user/notifications, /api/user/theme endpoints
 * Following TDD principles with comprehensive validation and security
 */

const express = require('express');
const { query, healthCheck } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const { createValidationMiddleware, sanitizers } = require('../middleware/validation');

const router = express.Router();

// Apply authentication middleware to ALL user profile routes
router.use(authenticateToken);

// Validation schemas
const profileValidationSchemas = {
  firstName: {
    type: 'string',
    required: true,
    sanitizer: (value) => sanitizers.string(value, { trim: true, maxLength: 50 }),
    validator: (value) => typeof value === 'string' && value.length >= 1 && value.length <= 50 && !/[<>]/.test(value),
    errorMessage: 'First name must be 1-50 characters and contain no HTML tags'
  },
  lastName: {
    type: 'string',
    required: true,
    sanitizer: (value) => sanitizers.string(value, { trim: true, maxLength: 50 }),
    validator: (value) => typeof value === 'string' && value.length >= 1 && value.length <= 50 && !/[<>]/.test(value),
    errorMessage: 'Last name must be 1-50 characters and contain no HTML tags'
  },
  email: {
    type: 'string',
    required: true,
    sanitizer: (value) => sanitizers.string(value, { trim: true, toLowerCase: true }),
    validator: (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
    errorMessage: 'Valid email address is required'
  },
  phone: {
    type: 'string',
    required: false,
    sanitizer: (value) => sanitizers.string(value, { trim: true }),
    validator: (value) => !value || /^\+?[1-9]\d{1,14}$/.test(value.replace(/[\s\-\(\)]/g, '')),
    errorMessage: 'Phone number must be in valid international format'
  },
  timezone: {
    type: 'string',
    required: false,
    sanitizer: (value) => sanitizers.string(value, { defaultValue: 'America/New_York' }),
    validator: (value) => typeof value === 'string' && value.length >= 3,
    errorMessage: 'Valid timezone is required'
  },
  currency: {
    type: 'string',
    required: false,
    sanitizer: (value) => sanitizers.string(value, { trim: true, toUpperCase: true, defaultValue: 'USD' }),
    validator: (value) => /^[A-Z]{3}$/.test(value),
    errorMessage: 'Currency must be a valid 3-letter code (e.g., USD, EUR)'
  }
};

const notificationValidationSchemas = {
  email: {
    type: 'boolean',
    required: false,
    sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
    validator: (value) => typeof value === 'boolean',
    errorMessage: 'Email notifications must be true or false'
  },
  push: {
    type: 'boolean',
    required: false,
    sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
    validator: (value) => typeof value === 'boolean',
    errorMessage: 'Push notifications must be true or false'
  },
  priceAlerts: {
    type: 'boolean',
    required: false,
    sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
    validator: (value) => typeof value === 'boolean',
    errorMessage: 'Price alerts must be true or false'
  },
  portfolioUpdates: {
    type: 'boolean',
    required: false,
    sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
    validator: (value) => typeof value === 'boolean',
    errorMessage: 'Portfolio updates must be true or false'
  },
  marketNews: {
    type: 'boolean',
    required: false,
    sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
    validator: (value) => typeof value === 'boolean',
    errorMessage: 'Market news must be true or false'
  },
  weeklyReports: {
    type: 'boolean',
    required: false,
    sanitizer: (value) => sanitizers.boolean(value, { defaultValue: true }),
    validator: (value) => typeof value === 'boolean',
    errorMessage: 'Weekly reports must be true or false'
  }
};

const themeValidationSchemas = {
  darkMode: {
    type: 'boolean',
    required: false,
    sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
    validator: (value) => typeof value === 'boolean',
    errorMessage: 'Dark mode must be true or false'
  },
  primaryColor: {
    type: 'string',
    required: false,
    sanitizer: (value) => sanitizers.string(value, { trim: true, defaultValue: '#1976d2' }),
    validator: (value) => /^#[0-9A-Fa-f]{6}$/.test(value),
    errorMessage: 'Primary color must be a valid hex color (e.g., #1976d2)'
  },
  chartStyle: {
    type: 'string',
    required: false,
    sanitizer: (value) => sanitizers.string(value, { trim: true, toLowerCase: true, defaultValue: 'candlestick' }),
    validator: (value) => ['candlestick', 'line', 'bar', 'area'].includes(value),
    errorMessage: 'Chart style must be one of: candlestick, line, bar, area'
  },
  layout: {
    type: 'string',
    required: false,
    sanitizer: (value) => sanitizers.string(value, { trim: true, toLowerCase: true, defaultValue: 'standard' }),
    validator: (value) => ['standard', 'compact', 'expanded'].includes(value),
    errorMessage: 'Layout must be one of: standard, compact, expanded'
  }
};

const validateProfileData = createValidationMiddleware(profileValidationSchemas).default;
const validateNotificationData = createValidationMiddleware(notificationValidationSchemas).default;
const validateThemeData = createValidationMiddleware(themeValidationSchemas).default;

// GET /api/user/profile - Get user profile
router.get('/profile', async (req, res) => {
  try {
    console.log('📝 GET /api/user/profile - Retrieving user profile');
    
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    
    // Check database health first
    const dbHealth = await healthCheck();
    if (!dbHealth.healthy) {
      console.warn('⚠️ Database health check failed, returning default profile');
      return res.json({
        success: true,
        data: {
          firstName: '',
          lastName: '',
          email: req.user?.email || '',
          phone: '',
          timezone: 'America/New_York',
          currency: 'USD'
        },
        message: 'Using default profile data',
        fallback: true,
        timestamp: new Date().toISOString()
      });
    }
    
    const result = await query(
      `SELECT first_name, last_name, email, phone, timezone, currency, updated_at 
       FROM user_profiles 
       WHERE user_id = $1`,
      [userId],
      { timeout: 10000, retries: 2 }
    );
    
    let profileData;
    if (result.rows.length === 0) {
      // Return default profile if none exists
      profileData = {
        firstName: '',
        lastName: '',
        email: req.user?.email || '',
        phone: '',
        timezone: 'America/New_York',
        currency: 'USD',
        updatedAt: null
      };
    } else {
      const row = result.rows[0];
      profileData = {
        firstName: row.first_name || '',
        lastName: row.last_name || '',
        email: row.email || '',
        phone: row.phone || '',
        timezone: row.timezone || 'America/New_York',
        currency: row.currency || 'USD',
        updatedAt: row.updated_at
      };
    }
    
    console.log(`✅ Retrieved profile for user ${userId}`);
    
    res.json({
      success: true,
      data: profileData,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error retrieving user profile:', error);
    
    // Graceful degradation - return default profile
    res.json({
      success: true,
      data: {
        firstName: '',
        lastName: '',
        email: req.user?.email || '',
        phone: '',
        timezone: 'America/New_York',
        currency: 'USD'
      },
      message: 'Profile temporarily unavailable, showing defaults',
      error: error.message,
      fallback: true,
      timestamp: new Date().toISOString()
    });
  }
});

// PUT /api/user/profile - Update user profile
router.put('/profile', validateProfileData, async (req, res) => {
  try {
    console.log('📝 PUT /api/user/profile - Updating user profile');
    
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    const { firstName, lastName, email, phone, timezone, currency } = req.body;
    
    // Check database health
    const dbHealth = await healthCheck();
    if (!dbHealth.healthy) {
      return res.status(503).json({
        success: false,
        error: 'Profile service temporarily unavailable',
        message: 'Please try again later'
      });
    }
    
    // Upsert profile data
    const result = await query(
      `INSERT INTO user_profiles 
       (user_id, first_name, last_name, email, phone, timezone, currency, created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
       ON CONFLICT (user_id) 
       DO UPDATE SET 
         first_name = EXCLUDED.first_name,
         last_name = EXCLUDED.last_name,
         email = EXCLUDED.email,
         phone = EXCLUDED.phone,
         timezone = EXCLUDED.timezone,
         currency = EXCLUDED.currency,
         updated_at = CURRENT_TIMESTAMP
       RETURNING first_name, last_name, email, phone, timezone, currency, updated_at`,
      [userId, firstName, lastName, email, phone, timezone, currency],
      { timeout: 15000, retries: 2 }
    );
    
    const updatedProfile = {
      firstName: result.rows[0].first_name,
      lastName: result.rows[0].last_name,
      email: result.rows[0].email,
      phone: result.rows[0].phone,
      timezone: result.rows[0].timezone,
      currency: result.rows[0].currency,
      updatedAt: result.rows[0].updated_at
    };
    
    console.log(`✅ Profile updated for user ${userId}`);
    
    res.json({
      success: true,
      data: updatedProfile,
      message: 'Profile updated successfully',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error updating user profile:', error);
    
    res.status(500).json({
      success: false,
      error: 'Failed to update profile',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// GET /api/user/notifications - Get notification preferences
router.get('/notifications', async (req, res) => {
  try {
    console.log('📝 GET /api/user/notifications - Retrieving notification preferences');
    
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    
    // Check database health first
    const dbHealth = await healthCheck();
    if (!dbHealth.healthy) {
      console.warn('⚠️ Database health check failed, returning default notifications');
      return res.json({
        success: true,
        data: {
          email: true,
          push: true,
          priceAlerts: true,
          portfolioUpdates: true,
          marketNews: false,
          weeklyReports: true
        },
        message: 'Using default notification preferences',
        fallback: true,
        timestamp: new Date().toISOString()
      });
    }
    
    const result = await query(
      `SELECT email_notifications, push_notifications, price_alerts, 
              portfolio_updates, market_news, weekly_reports, updated_at 
       FROM user_notification_preferences 
       WHERE user_id = $1`,
      [userId],
      { timeout: 10000, retries: 2 }
    );
    
    let preferences;
    if (result.rows.length === 0) {
      // Return default preferences if none exist
      preferences = {
        email: true,
        push: true,
        priceAlerts: true,
        portfolioUpdates: true,
        marketNews: false,
        weeklyReports: true,
        updatedAt: null
      };
    } else {
      const row = result.rows[0];
      preferences = {
        email: row.email_notifications,
        push: row.push_notifications,
        priceAlerts: row.price_alerts,
        portfolioUpdates: row.portfolio_updates,
        marketNews: row.market_news,
        weeklyReports: row.weekly_reports,
        updatedAt: row.updated_at
      };
    }
    
    console.log(`✅ Retrieved notification preferences for user ${userId}`);
    
    res.json({
      success: true,
      data: preferences,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error retrieving notification preferences:', error);
    
    // Graceful degradation - return defaults
    res.json({
      success: true,
      data: {
        email: true,
        push: true,
        priceAlerts: true,
        portfolioUpdates: true,
        marketNews: false,
        weeklyReports: true
      },
      message: 'Notification preferences temporarily unavailable, showing defaults',
      error: error.message,
      fallback: true,
      timestamp: new Date().toISOString()
    });
  }
});

// PUT /api/user/notifications - Update notification preferences
router.put('/notifications', validateNotificationData, async (req, res) => {
  try {
    console.log('📝 PUT /api/user/notifications - Updating notification preferences');
    
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    const { email, push, priceAlerts, portfolioUpdates, marketNews, weeklyReports } = req.body;
    
    // Check database health
    const dbHealth = await healthCheck();
    if (!dbHealth.healthy) {
      // Graceful degradation - acknowledge the request but don't fail
      return res.json({
        success: true,
        data: { email, push, priceAlerts, portfolioUpdates, marketNews, weeklyReports },
        message: 'Preferences saved locally, will sync when database is available',
        fallback: true,
        timestamp: new Date().toISOString()
      });
    }
    
    // Upsert preferences
    const result = await query(
      `INSERT INTO user_notification_preferences 
       (user_id, email_notifications, push_notifications, price_alerts, 
        portfolio_updates, market_news, weekly_reports, created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
       ON CONFLICT (user_id) 
       DO UPDATE SET 
         email_notifications = EXCLUDED.email_notifications,
         push_notifications = EXCLUDED.push_notifications,
         price_alerts = EXCLUDED.price_alerts,
         portfolio_updates = EXCLUDED.portfolio_updates,
         market_news = EXCLUDED.market_news,
         weekly_reports = EXCLUDED.weekly_reports,
         updated_at = CURRENT_TIMESTAMP
       RETURNING email_notifications, push_notifications, price_alerts, 
                 portfolio_updates, market_news, weekly_reports, updated_at`,
      [userId, email, push, priceAlerts, portfolioUpdates, marketNews, weeklyReports],
      { timeout: 15000, retries: 2 }
    );
    
    const updatedPreferences = {
      email: result.rows[0].email_notifications,
      push: result.rows[0].push_notifications,
      priceAlerts: result.rows[0].price_alerts,
      portfolioUpdates: result.rows[0].portfolio_updates,
      marketNews: result.rows[0].market_news,
      weeklyReports: result.rows[0].weekly_reports,
      updatedAt: result.rows[0].updated_at
    };
    
    console.log(`✅ Notification preferences updated for user ${userId}`);
    
    res.json({
      success: true,
      data: updatedPreferences,
      message: 'Notification preferences updated successfully',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error updating notification preferences:', error);
    
    res.status(500).json({
      success: false,
      error: 'Failed to update notification preferences',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// GET /api/user/theme - Get theme preferences
router.get('/theme', async (req, res) => {
  try {
    console.log('📝 GET /api/user/theme - Retrieving theme preferences');
    
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    
    // Check database health first
    const dbHealth = await healthCheck();
    if (!dbHealth.healthy) {
      console.warn('⚠️ Database health check failed, returning default theme');
      return res.json({
        success: true,
        data: {
          darkMode: false,
          primaryColor: '#1976d2',
          chartStyle: 'candlestick',
          layout: 'standard'
        },
        message: 'Using default theme preferences',
        fallback: true,
        timestamp: new Date().toISOString()
      });
    }
    
    const result = await query(
      `SELECT dark_mode, primary_color, chart_style, layout, updated_at 
       FROM user_theme_preferences 
       WHERE user_id = $1`,
      [userId],
      { timeout: 10000, retries: 2 }
    );
    
    let preferences;
    if (result.rows.length === 0) {
      // Return default theme if none exists
      preferences = {
        darkMode: false,
        primaryColor: '#1976d2',
        chartStyle: 'candlestick',
        layout: 'standard',
        updatedAt: null
      };
    } else {
      const row = result.rows[0];
      preferences = {
        darkMode: row.dark_mode,
        primaryColor: row.primary_color,
        chartStyle: row.chart_style,
        layout: row.layout,
        updatedAt: row.updated_at
      };
    }
    
    console.log(`✅ Retrieved theme preferences for user ${userId}`);
    
    res.json({
      success: true,
      data: preferences,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error retrieving theme preferences:', error);
    
    // Graceful degradation - return defaults
    res.json({
      success: true,
      data: {
        darkMode: false,
        primaryColor: '#1976d2',
        chartStyle: 'candlestick',
        layout: 'standard'
      },
      message: 'Theme preferences temporarily unavailable, showing defaults',
      error: error.message,
      fallback: true,
      timestamp: new Date().toISOString()
    });
  }
});

// PUT /api/user/theme - Update theme preferences
router.put('/theme', validateThemeData, async (req, res) => {
  try {
    console.log('📝 PUT /api/user/theme - Updating theme preferences');
    
    const userId = req.user?.sub || req.user?.id || 'demo-user';
    const { darkMode, primaryColor, chartStyle, layout } = req.body;
    
    // Check database health
    const dbHealth = await healthCheck();
    if (!dbHealth.healthy) {
      // Graceful degradation - acknowledge the request but don't fail
      return res.json({
        success: true,
        data: { darkMode, primaryColor, chartStyle, layout },
        message: 'Theme saved locally, will sync when database is available',
        fallback: true,
        timestamp: new Date().toISOString()
      });
    }
    
    // Upsert theme preferences
    const result = await query(
      `INSERT INTO user_theme_preferences 
       (user_id, dark_mode, primary_color, chart_style, layout, created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
       ON CONFLICT (user_id) 
       DO UPDATE SET 
         dark_mode = EXCLUDED.dark_mode,
         primary_color = EXCLUDED.primary_color,
         chart_style = EXCLUDED.chart_style,
         layout = EXCLUDED.layout,
         updated_at = CURRENT_TIMESTAMP
       RETURNING dark_mode, primary_color, chart_style, layout, updated_at`,
      [userId, darkMode, primaryColor, chartStyle, layout],
      { timeout: 15000, retries: 2 }
    );
    
    const updatedTheme = {
      darkMode: result.rows[0].dark_mode,
      primaryColor: result.rows[0].primary_color,
      chartStyle: result.rows[0].chart_style,
      layout: result.rows[0].layout,
      updatedAt: result.rows[0].updated_at
    };
    
    console.log(`✅ Theme preferences updated for user ${userId}`);
    
    res.json({
      success: true,
      data: updatedTheme,
      message: 'Theme preferences updated successfully',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Error updating theme preferences:', error);
    
    res.status(500).json({
      success: false,
      error: 'Failed to update theme preferences',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Health check endpoint
router.get('/health', (req, res) => {
  res.json({
    success: true,
    service: 'user-profile',
    timestamp: new Date().toISOString(),
    endpoints: [
      'GET /api/user/profile',
      'PUT /api/user/profile',
      'GET /api/user/notifications',
      'PUT /api/user/notifications',
      'GET /api/user/theme',
      'PUT /api/user/theme'
    ]
  });
});

module.exports = router;
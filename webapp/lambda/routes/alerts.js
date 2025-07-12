const express = require('express');
const router = express.Router();
const { authenticateToken } = require('../middleware/auth');
const WatchlistAlerts = require('../utils/watchlistAlerts');

// Apply authentication to all routes
router.use(authenticateToken);

// Get available alert types
router.get('/types', async (req, res) => {
  try {
    const alertTypes = [
      {
        type: 'price_above',
        name: 'Price Above Target',
        description: 'Alert when stock price goes above specified value'
      },
      {
        type: 'price_below',
        name: 'Price Below Target',
        description: 'Alert when stock price goes below specified value'
      },
      {
        type: 'volume_spike',
        name: 'Volume Spike',
        description: 'Alert when trading volume exceeds average by specified percentage'
      },
      {
        type: 'technical_signal',
        name: 'Technical Signal',
        description: 'Alert when technical indicators generate buy/sell signals'
      },
      {
        type: 'news_sentiment',
        name: 'News Sentiment',
        description: 'Alert when news sentiment changes significantly'
      },
      {
        type: 'earnings_announcement',
        name: 'Earnings Announcement',
        description: 'Alert before earnings announcements'
      }
    ];

    res.json({
      success: true,
      data: alertTypes,
      total: alertTypes.length
    });
  } catch (error) {
    console.error('Error fetching alert types:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch alert types'
    });
  }
});

// Get alert notifications
router.get('/notifications', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { limit = 20, offset = 0, unreadOnly = false } = req.query;

    // For now, return a basic structure
    // In a real implementation, this would fetch from a notifications table
    const notifications = await watchlistAlerts.getUserNotifications(userId, {
      limit: parseInt(limit),
      offset: parseInt(offset),
      unreadOnly: unreadOnly === 'true'
    });

    res.json({
      success: true,
      data: {
        notifications: notifications || [],
        pagination: {
          limit: parseInt(limit),
          offset: parseInt(offset),
          total: notifications?.length || 0
        }
      }
    });
  } catch (error) {
    console.error('Error fetching notifications:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch notifications',
      message: error.message
    });
  }
});

// Initialize watchlist alerts system
const watchlistAlerts = new WatchlistAlerts();

// Get user's alerts
router.get('/', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { symbol, isActive, alertType, limit = 50, offset = 0 } = req.query;

    const filters = {};
    if (symbol) filters.symbol = symbol;
    if (isActive !== undefined) filters.isActive = isActive === 'true';
    if (alertType) filters.alertType = alertType;

    const alerts = await watchlistAlerts.getUserAlerts(userId, filters);
    
    // Apply pagination
    const startIndex = parseInt(offset);
    const endIndex = startIndex + parseInt(limit);
    const paginatedAlerts = alerts.slice(startIndex, endIndex);

    res.json({
      success: true,
      data: {
        alerts: paginatedAlerts,
        pagination: {
          limit: parseInt(limit),
          offset: parseInt(offset),
          total: alerts.length,
          hasMore: endIndex < alerts.length
        }
      }
    });
  } catch (error) {
    console.error('Error fetching alerts:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch alerts',
      message: error.message
    });
  }
});

// Create new alert
router.post('/', async (req, res) => {
  try {
    const userId = req.user.sub;
    const alertConfig = {
      ...req.body,
      userId
    };

    const alert = await watchlistAlerts.createAlert(userId, alertConfig);

    res.json({
      success: true,
      data: alert,
      message: 'Alert created successfully'
    });
  } catch (error) {
    console.error('Error creating alert:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to create alert',
      message: error.message
    });
  }
});

// Update alert
router.put('/:alertId', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { alertId } = req.params;
    const updates = req.body;

    const alert = await watchlistAlerts.updateAlert(alertId, userId, updates);

    res.json({
      success: true,
      data: alert,
      message: 'Alert updated successfully'
    });
  } catch (error) {
    console.error('Error updating alert:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to update alert',
      message: error.message
    });
  }
});

// Delete alert
router.delete('/:alertId', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { alertId } = req.params;

    await watchlistAlerts.deleteAlert(alertId, userId);

    res.json({
      success: true,
      message: 'Alert deleted successfully'
    });
  } catch (error) {
    console.error('Error deleting alert:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to delete alert',
      message: error.message
    });
  }
});

// Get alert notifications
router.get('/notifications', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { limit = 50 } = req.query;

    const notifications = await watchlistAlerts.getAlertNotifications(userId, parseInt(limit));

    res.json({
      success: true,
      data: notifications
    });
  } catch (error) {
    console.error('Error fetching notifications:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch notifications',
      message: error.message
    });
  }
});

// Mark notification as read
router.put('/notifications/:notificationId/read', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { notificationId } = req.params;

    const notification = await watchlistAlerts.markNotificationAsRead(notificationId, userId);

    res.json({
      success: true,
      data: notification,
      message: 'Notification marked as read'
    });
  } catch (error) {
    console.error('Error marking notification as read:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to mark notification as read',
      message: error.message
    });
  }
});


// Test alert system
router.post('/test', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { symbol } = req.body;

    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: 'Symbol is required for testing'
      });
    }

    // Create a test alert that will trigger immediately
    const testAlert = {
      symbol: symbol.toUpperCase(),
      alertType: 'price_above',
      condition: 'greater',
      targetValue: 0.01, // Very low price to ensure trigger
      message: `Test alert for ${symbol.toUpperCase()}`,
      isActive: true
    };

    const alert = await watchlistAlerts.createAlert(userId, testAlert);
    
    // Process alerts immediately for testing
    await watchlistAlerts.processAlerts();

    res.json({
      success: true,
      data: alert,
      message: 'Test alert created and processed'
    });
  } catch (error) {
    console.error('Error testing alert:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to test alert',
      message: error.message
    });
  }
});

// Start alert processing (for admin/system use)
router.post('/start-processing', async (req, res) => {
  try {
    const { intervalMinutes = 5 } = req.body;
    
    watchlistAlerts.startAlertProcessing(intervalMinutes);
    
    res.json({
      success: true,
      message: `Alert processing started with ${intervalMinutes} minute intervals`
    });
  } catch (error) {
    console.error('Error starting alert processing:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to start alert processing',
      message: error.message
    });
  }
});

module.exports = router;
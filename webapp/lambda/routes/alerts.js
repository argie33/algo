const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const { query } = require('../utils/database');
const NotificationService = require('../services/notificationService');

const router = express.Router();

// Initialize notification service
const notificationService = new NotificationService();

// Root alerts endpoint for health checks
router.get('/', (req, res) => {
  res.json({
    success: true,
    data: {
      system: 'Alerts API',
      version: '1.0.0',
      status: 'operational',
      available_endpoints: [
        'GET /alerts - List user alerts',
        'GET /alerts/types - Alert type definitions',
        'GET /alerts/notifications - User notifications',
        'POST /alerts - Create new alert',
        'DELETE /alerts/:id - Delete alert'
      ],
      timestamp: new Date().toISOString()
    }
  });
});

// Apply authentication to all other routes
router.use(authenticateToken);

// Get alert types
router.get('/types', (req, res) => {
  try {
    const alertTypes = [
      {
        id: 'price_target',
        name: 'Price Target',
        description: 'Alert when stock reaches target price',
        category: 'price',
        parameters: ['symbol', 'target_price', 'condition'],
        conditions: ['above', 'below', 'crosses']
      },
      {
        id: 'volume_spike',
        name: 'Volume Spike',
        description: 'Alert on unusual trading volume',
        category: 'volume',
        parameters: ['symbol', 'volume_threshold', 'percentage'],
        conditions: ['above_average', 'percentage_increase']
      },
      {
        id: 'technical_indicator',
        name: 'Technical Indicator',
        description: 'Alert based on technical analysis signals',
        category: 'technical',
        parameters: ['symbol', 'indicator', 'condition', 'value'],
        conditions: ['overbought', 'oversold', 'breakout', 'breakdown']
      },
      {
        id: 'earnings_announcement',
        name: 'Earnings Announcement',
        description: 'Alert before earnings releases',
        category: 'fundamental',
        parameters: ['symbol', 'days_before'],
        conditions: ['upcoming', 'pre_market', 'after_market']
      },
      {
        id: 'analyst_upgrade',
        name: 'Analyst Rating Change',
        description: 'Alert on analyst upgrades/downgrades',
        category: 'analyst',
        parameters: ['symbol', 'rating_change'],
        conditions: ['upgrade', 'downgrade', 'any_change']
      },
      {
        id: 'news_sentiment',
        name: 'News Sentiment',
        description: 'Alert on significant news sentiment changes',
        category: 'sentiment',
        parameters: ['symbol', 'sentiment_score', 'threshold'],
        conditions: ['positive', 'negative', 'neutral']
      }
    ];

    res.json({
      success: true,
      data: alertTypes,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching alert types:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch alert types',
      details: error.message
    });
  }
});

// Get user notifications
router.get('/notifications', async (req, res) => {
  try {
    const userId = req.user.sub;
    const limit = parseInt(req.query.limit) || 50;
    const offset = parseInt(req.query.offset) || 0;
    const unreadOnly = req.query.unread === 'true';

    // Use real notification service
    const result = await notificationService.getUserNotifications(userId, {
      limit,
      offset,
      unreadOnly,
      type: req.query.type,
      priority: req.query.priority,
      category: req.query.category
    });

    res.json({
      success: true,
      data: result.notifications,
      pagination: result.pagination,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching notifications:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch notifications',
      details: error.message
    });
  }
});

module.exports = router;
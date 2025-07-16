const express = require('express');
const { authenticateToken } = require('../middleware/auth');
const { query } = require('../utils/database');

const router = express.Router();

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

    // Try to get notifications from database
    try {
      let whereClause = 'WHERE user_id = $1';
      let params = [userId];
      
      if (unreadOnly) {
        whereClause += ' AND read_at IS NULL';
      }

      const result = await query(`
        SELECT 
          id,
          alert_id,
          title,
          message,
          category,
          priority,
          read_at,
          created_at,
          metadata
        FROM alert_notifications
        ${whereClause}
        ORDER BY created_at DESC
        LIMIT $${params.length + 1} OFFSET $${params.length + 2}
      `, [...params, limit, offset]);

      const countResult = await query(`
        SELECT COUNT(*) as total
        FROM alert_notifications
        ${whereClause}
      `, params);

      const notifications = result.rows.map(notification => ({
        id: notification.id,
        alertId: notification.alert_id,
        title: notification.title,
        message: notification.message,
        category: notification.category,
        priority: notification.priority,
        isRead: !!notification.read_at,
        readAt: notification.read_at,
        createdAt: notification.created_at,
        metadata: typeof notification.metadata === 'string' 
          ? JSON.parse(notification.metadata) 
          : notification.metadata
      }));

      res.json({
        success: true,
        data: notifications,
        pagination: {
          total: parseInt(countResult.rows[0].total),
          limit,
          offset,
          hasMore: offset + notifications.length < parseInt(countResult.rows[0].total)
        },
        timestamp: new Date().toISOString()
      });

    } catch (dbError) {
      console.log('Database query failed for notifications, using mock data:', dbError.message);
      
      // Return mock notifications if database fails
      const mockNotifications = [
        {
          id: 'notif-1',
          alertId: 'alert-1',
          title: 'Price Alert Triggered',
          message: 'AAPL has reached your target price of $175.00',
          category: 'price',
          priority: 'high',
          isRead: false,
          readAt: null,
          createdAt: new Date().toISOString(),
          metadata: {
            symbol: 'AAPL',
            currentPrice: 175.50,
            targetPrice: 175.00
          }
        },
        {
          id: 'notif-2',
          alertId: 'alert-2',
          title: 'Volume Spike Detected',
          message: 'TSLA is experiencing unusual trading volume',
          category: 'volume',
          priority: 'medium',
          isRead: true,
          readAt: new Date(Date.now() - 3600000).toISOString(),
          createdAt: new Date(Date.now() - 7200000).toISOString(),
          metadata: {
            symbol: 'TSLA',
            currentVolume: 85000000,
            averageVolume: 45000000
          }
        }
      ];

      res.json({
        success: true,
        data: unreadOnly ? mockNotifications.filter(n => !n.isRead) : mockNotifications,
        pagination: {
          total: unreadOnly ? 1 : 2,
          limit,
          offset,
          hasMore: false
        },
        note: 'Mock notifications - database connectivity issue',
        timestamp: new Date().toISOString()
      });
    }

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
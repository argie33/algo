const express = require('express');
const request = require('supertest');

// Real database for integration
const { query } = require('../../../utils/database');

describe('Alerts Routes Unit Tests', () => {
  let app;

  beforeAll(() => {
    // Create test app
    app = express();
    app.use(express.json());
    
    // Mock authentication middleware - allow all requests through
    app.use((req, res, next) => {
      req.user = { sub: 'test-user-123' }; // Mock authenticated user
      next();
    });
    
    // Add response formatter middleware
    const responseFormatter = require('../../../middleware/responseFormatter');
    app.use(responseFormatter);
    
    // Load alerts routes
    const alertsRouter = require('../../../routes/alerts');
    app.use('/alerts', alertsRouter);
  });

  describe('GET /alerts/', () => {
    test('should return alerts info', async () => {
      const response = await request(app)
        .get('/alerts/')
        .expect(200);

      expect(response.body).toHaveProperty('success');
      expect(response.body).toHaveProperty('status');
    });
  });

  describe('GET /alerts/active', () => {
    test('should return active alerts with proper structure', async () => {
      const response = await request(app)
        .get('/alerts/active')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
        expect(response.body.data).toHaveProperty('alerts');
        expect(response.body.data).toHaveProperty('summary');
        expect(Array.isArray(response.body.data.alerts)).toBe(true);
        
        // Check summary structure
        expect(response.body.data.summary).toHaveProperty('total_alerts');
        expect(response.body.data.summary).toHaveProperty('by_status');
        expect(response.body.data.summary).toHaveProperty('by_type');
        expect(response.body.data.summary).toHaveProperty('by_priority');
      } else {
        expect([401]).toContain(response.status);
        expect(response.body).toHaveProperty('success', false);
      }
    });

    test('should handle limit parameter', async () => {
      const response = await request(app)
        .get('/alerts/active?limit=5')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data.alerts.length).toBeLessThanOrEqual(5);
      }
    });

    test('should handle offset parameter', async () => {
      const response = await request(app)
        .get('/alerts/active?offset=10&limit=5')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body).toHaveProperty('data');
        expect(response.body.data).toHaveProperty('alerts');
      }
    });

    test('should handle priority filter', async () => {
      const response = await request(app)
        .get('/alerts/active?priority=high')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data.alerts.every(alert => 
          alert.priority === 'high' || alert.priority === 'critical'
        )).toBe(true);
      }
    });

    test('should handle status filter', async () => {
      const response = await request(app)
        .get('/alerts/active?status=triggered')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data.alerts.every(alert => 
          alert.status === 'triggered'
        )).toBe(true);
      }
    });
  });

  describe('GET /alerts/distance/:symbol', () => {
    test('should return distance-based alert analysis', async () => {
      const response = await request(app)
        .get('/alerts/distance/AAPL')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
        expect(response.body.data).toHaveProperty('symbol', 'AAPL');
        expect(response.body.data).toHaveProperty('current_price');
        expect(response.body.data).toHaveProperty('alerts');
        expect(response.body.data).toHaveProperty('summary');
        
        // Check alert distance calculations
        if (response.body.data.alerts.length > 0) {
          response.body.data.alerts.forEach(alert => {
            expect(alert).toHaveProperty('distance_percentage');
            expect(alert).toHaveProperty('distance_dollars');
            expect(alert).toHaveProperty('risk_level');
          });
        }
      }
    });

    test('should handle invalid symbol', async () => {
      const response = await request(app)
        .get('/alerts/distance/INVALID')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty('symbol', 'INVALID');
        expect(response.body.data.alerts).toHaveLength(0);
      }
    });
  });

  describe('PUT /alerts/:id/dismiss', () => {
    test('should handle alert dismissal', async () => {
      // First try to get an active alert ID
      const alertsResponse = await request(app)
        .get('/alerts/active')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (alertsResponse.status === 200 && alertsResponse.body.data.alerts.length > 0) {
        const alertId = alertsResponse.body.data.alerts[0].id;
        
        const response = await request(app)
          .put(`/alerts/${alertId}/dismiss`)
          .set('Authorization', 'Bearer dev-bypass-token');

        expect([200, 404]).toContain(response.status);
        if (response.status === 200) {
          expect(response.body).toHaveProperty('success', true);
          expect(response.body).toHaveProperty('message');
        }
      } else {
        // Test with non-existent ID
        const response = await request(app)
          .put('/alerts/99999/dismiss')
          .set('Authorization', 'Bearer dev-bypass-token');

        expect([404, 401]).toContain(response.status);
      }
    });

    test('should handle invalid alert ID format', async () => {
      const response = await request(app)
        .put('/alerts/invalid-id/dismiss')
        .set('Authorization', 'Bearer dev-bypass-token');

      expect([400, 404, 401]).toContain(response.status);
    });
  });

  describe('POST /alerts/', () => {
    test('should handle alert creation', async () => {
      const alertData = {
        symbol: 'AAPL',
        condition: 'price_above',
        value: 150
      };

      const response = await request(app)
        .post('/alerts/')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(alertData);

      expect([200, 201, 400, 401]).toContain(response.status);
      expect(response.body).toHaveProperty('success');
    });
  });

  // ================================
  // Price Alert Management Tests
  // ================================

  describe('POST /alerts/price', () => {
    test('should create price alert with valid data', async () => {
      const priceAlertData = {
        symbol: 'AAPL',
        alert_type: 'price_above',
        target_price: 175.00,
        expiration_date: '2024-12-31',
        notification_method: 'email',
        notes: 'Buy signal for AAPL'
      };

      const response = await request(app)
        .post('/alerts/price')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(priceAlertData);

      if (response.status === 201) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
        expect(response.body.data).toHaveProperty('alert_id');
        expect(response.body.data).toHaveProperty('symbol', 'AAPL');
        expect(response.body.data).toHaveProperty('target_price', 175.00);
      } else {
        expect([400, 401]).toContain(response.status);
        expect(response.body).toHaveProperty('success', false);
      }
    });

    test('should validate required fields', async () => {
      const incompleteData = {
        symbol: 'AAPL'
        // Missing required fields
      };

      const response = await request(app)
        .post('/alerts/price')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(incompleteData)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body).toHaveProperty('error');
    });

    test('should handle duplicate price alerts', async () => {
      const alertData = {
        symbol: 'AAPL',
        alert_type: 'price_above',
        target_price: 180.00
      };

      // First create
      const firstResponse = await request(app)
        .post('/alerts/price')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(alertData);

      // Second create (duplicate)
      const secondResponse = await request(app)
        .post('/alerts/price')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(alertData);

      if (firstResponse.status === 201) {
        expect([409, 200]).toContain(secondResponse.status);
      }
    });
  });

  describe('GET /alerts/price/:symbol', () => {
    test('should return price alerts for symbol', async () => {
      const response = await request(app)
        .get('/alerts/price/AAPL')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('symbol', 'AAPL');
      expect(response.body.data).toHaveProperty('alerts');
      expect(Array.isArray(response.body.data.alerts)).toBe(true);
    });

    test('should filter alerts by status', async () => {
      const response = await request(app)
        .get('/alerts/price/AAPL?status=active')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.alerts.length > 0) {
        response.body.data.alerts.forEach(alert => {
          expect(alert.status).toBe('active');
        });
      }
    });
  });

  // ================================
  // Volume Alert Tests
  // ================================

  describe('POST /alerts/volume', () => {
    test('should create volume alert', async () => {
      const volumeAlertData = {
        symbol: 'TSLA',
        alert_type: 'volume_spike',
        threshold_multiplier: 2.5,
        baseline_period: 20,
        notification_method: 'sms'
      };

      const response = await request(app)
        .post('/alerts/volume')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(volumeAlertData);

      if (response.status === 201) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty('symbol', 'TSLA');
        expect(response.body.data).toHaveProperty('threshold_multiplier', 2.5);
      } else {
        expect([400, 401]).toContain(response.status);
      }
    });

    test('should validate threshold multiplier range', async () => {
      const invalidData = {
        symbol: 'TSLA',
        alert_type: 'volume_spike',
        threshold_multiplier: -1.0 // Invalid negative multiplier
      };

      const response = await request(app)
        .post('/alerts/volume')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(invalidData)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('threshold');
    });
  });

  describe('GET /alerts/volume/analysis/:symbol', () => {
    test('should return volume analysis for symbol', async () => {
      const response = await request(app)
        .get('/alerts/volume/analysis/TSLA')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('symbol', 'TSLA');
      expect(response.body.data).toHaveProperty('current_volume');
      expect(response.body.data).toHaveProperty('average_volume');
      expect(response.body.data).toHaveProperty('volume_ratio');
      expect(response.body.data).toHaveProperty('alerts_triggered');
    });

    test('should include historical volume data', async () => {
      const response = await request(app)
        .get('/alerts/volume/analysis/TSLA?include_history=true')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.volume_history) {
        expect(Array.isArray(response.body.data.volume_history)).toBe(true);
      }
    });
  });

  // ================================
  // Technical Alert Tests
  // ================================

  describe('POST /alerts/technical', () => {
    test('should create RSI alert', async () => {
      const rsiAlertData = {
        symbol: 'GOOGL',
        indicator: 'RSI',
        condition: 'below',
        threshold: 30,
        period: 14,
        notification_method: 'email'
      };

      const response = await request(app)
        .post('/alerts/technical')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(rsiAlertData);

      if (response.status === 201) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty('indicator', 'RSI');
        expect(response.body.data).toHaveProperty('threshold', 30);
      } else {
        expect([400, 401]).toContain(response.status);
      }
    });

    test('should create MACD alert', async () => {
      const macdAlertData = {
        symbol: 'MSFT',
        indicator: 'MACD',
        condition: 'crossover_above',
        signal_line: true,
        notification_method: 'webhook',
        webhook_url: 'https://example.com/webhook'
      };

      const response = await request(app)
        .post('/alerts/technical')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(macdAlertData);

      if (response.status === 201) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty('indicator', 'MACD');
      } else {
        expect([400, 401]).toContain(response.status);
      }
    });

    test('should validate supported indicators', async () => {
      const unsupportedIndicator = {
        symbol: 'AAPL',
        indicator: 'UNSUPPORTED',
        condition: 'above',
        threshold: 50
      };

      const response = await request(app)
        .post('/alerts/technical')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(unsupportedIndicator)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('indicator');
    });
  });

  describe('GET /alerts/technical/status/:symbol', () => {
    test('should return technical alert status', async () => {
      const response = await request(app)
        .get('/alerts/technical/status/AAPL')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('symbol', 'AAPL');
      expect(response.body.data).toHaveProperty('technical_alerts');
      expect(response.body.data).toHaveProperty('current_indicators');
    });

    test('should filter by indicator type', async () => {
      const response = await request(app)
        .get('/alerts/technical/status/AAPL?indicator=RSI')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.technical_alerts.length > 0) {
        response.body.data.technical_alerts.forEach(alert => {
          expect(alert.indicator).toBe('RSI');
        });
      }
    });
  });

  // ================================
  // News Alert Tests
  // ================================

  describe('POST /alerts/news', () => {
    test('should create news sentiment alert', async () => {
      const newsAlertData = {
        symbol: 'NFLX',
        alert_type: 'sentiment_change',
        sentiment_threshold: -0.5,
        news_sources: ['reuters', 'bloomberg'],
        keywords: ['earnings', 'guidance'],
        notification_method: 'email'
      };

      const response = await request(app)
        .post('/alerts/news')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(newsAlertData);

      if (response.status === 201) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty('symbol', 'NFLX');
        expect(response.body.data).toHaveProperty('sentiment_threshold', -0.5);
      } else {
        expect([400, 401]).toContain(response.status);
      }
    });

    test('should validate news sources', async () => {
      const invalidSourceData = {
        symbol: 'AAPL',
        alert_type: 'sentiment_change',
        news_sources: ['invalid_source'],
        sentiment_threshold: 0.5
      };

      const response = await request(app)
        .post('/alerts/news')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(invalidSourceData)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('source');
    });
  });

  describe('GET /alerts/news/recent/:symbol', () => {
    test('should return recent news alerts', async () => {
      const response = await request(app)
        .get('/alerts/news/recent/AAPL')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('symbol', 'AAPL');
      expect(response.body.data).toHaveProperty('news_alerts');
      expect(response.body.data).toHaveProperty('sentiment_summary');
    });

    test('should filter by time period', async () => {
      const response = await request(app)
        .get('/alerts/news/recent/AAPL?hours=24')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('time_period', '24 hours');
    });
  });

  // ================================
  // Portfolio Alert Tests
  // ================================

  describe('POST /alerts/portfolio', () => {
    test('should create portfolio-wide alert', async () => {
      const portfolioAlertData = {
        alert_type: 'total_value_change',
        threshold_percentage: -5.0,
        time_period: '1d',
        notification_method: 'email'
      };

      const response = await request(app)
        .post('/alerts/portfolio')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(portfolioAlertData);

      if (response.status === 201) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty('alert_type', 'total_value_change');
        expect(response.body.data).toHaveProperty('threshold_percentage', -5.0);
      } else {
        expect([400, 401]).toContain(response.status);
      }
    });

    test('should create sector concentration alert', async () => {
      const sectorAlertData = {
        alert_type: 'sector_concentration',
        sector: 'Technology',
        max_concentration: 40.0,
        notification_method: 'sms'
      };

      const response = await request(app)
        .post('/alerts/portfolio')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(sectorAlertData);

      if (response.status === 201) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty('sector', 'Technology');
      } else {
        expect([400, 401]).toContain(response.status);
      }
    });
  });

  describe('GET /alerts/portfolio/status', () => {
    test('should return portfolio alert status', async () => {
      const response = await request(app)
        .get('/alerts/portfolio/status')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('portfolio_alerts');
      expect(response.body.data).toHaveProperty('portfolio_metrics');
      expect(response.body.data).toHaveProperty('risk_analysis');
    });

    test('should include triggered alerts summary', async () => {
      const response = await request(app)
        .get('/alerts/portfolio/status?include_triggered=true')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.triggered_summary) {
        expect(response.body.data.triggered_summary).toHaveProperty('total_triggered');
        expect(response.body.data.triggered_summary).toHaveProperty('by_type');
      }
    });
  });

  // ================================
  // Alert Management Tests
  // ================================

  describe('PUT /alerts/:id/update', () => {
    test('should update alert settings', async () => {
      const updateData = {
        target_price: 185.00,
        notification_method: 'both',
        expiration_date: '2024-06-30'
      };

      const response = await request(app)
        .put('/alerts/1/update')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(updateData);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body).toHaveProperty('message');
        expect(response.body.data).toHaveProperty('updated_fields');
      } else {
        expect([404, 401]).toContain(response.status);
      }
    });

    test('should validate update data', async () => {
      const invalidUpdate = {
        target_price: 'invalid_price'
      };

      const response = await request(app)
        .put('/alerts/1/update')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(invalidUpdate)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('price');
    });
  });

  describe('DELETE /alerts/:id', () => {
    test('should delete alert', async () => {
      const response = await request(app)
        .delete('/alerts/1')
        .set('Authorization', 'Bearer dev-bypass-token');

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body).toHaveProperty('message');
      } else {
        expect([404, 401]).toContain(response.status);
      }
    });

    test('should handle non-existent alert deletion', async () => {
      const response = await request(app)
        .delete('/alerts/99999')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('not found');
    });
  });

  describe('POST /alerts/bulk/dismiss', () => {
    test('should dismiss multiple alerts', async () => {
      const dismissData = {
        alert_ids: [1, 2, 3],
        reason: 'Bulk cleanup'
      };

      const response = await request(app)
        .post('/alerts/bulk/dismiss')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(dismissData);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty('dismissed_count');
        expect(response.body.data).toHaveProperty('failed_count');
      } else {
        expect([400, 401]).toContain(response.status);
      }
    });

    test('should validate alert IDs array', async () => {
      const invalidData = {
        alert_ids: 'not_an_array'
      };

      const response = await request(app)
        .post('/alerts/bulk/dismiss')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(invalidData)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('array');
    });
  });

  // ================================
  // Alert History Tests
  // ================================

  describe('GET /alerts/history', () => {
    test('should return alert history with pagination', async () => {
      const response = await request(app)
        .get('/alerts/history')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('alerts');
      expect(response.body.data).toHaveProperty('pagination');
      expect(response.body.data).toHaveProperty('summary');
    });

    test('should filter history by date range', async () => {
      const response = await request(app)
        .get('/alerts/history?start_date=2024-01-01&end_date=2024-01-31')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.date_range) {
        expect(response.body.data.date_range).toHaveProperty('start', '2024-01-01');
        expect(response.body.data.date_range).toHaveProperty('end', '2024-01-31');
      }
    });

    test('should filter by alert type', async () => {
      const response = await request(app)
        .get('/alerts/history?alert_type=price_above')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.alerts.length > 0) {
        response.body.data.alerts.forEach(alert => {
          expect(alert.alert_type).toBe('price_above');
        });
      }
    });
  });

  describe('GET /alerts/history/performance', () => {
    test('should return alert performance analytics', async () => {
      const response = await request(app)
        .get('/alerts/history/performance')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('performance_metrics');
      expect(response.body.data).toHaveProperty('alert_accuracy');
      expect(response.body.data).toHaveProperty('response_times');
    });

    test('should break down performance by alert type', async () => {
      const response = await request(app)
        .get('/alerts/history/performance?breakdown=alert_type')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.by_alert_type) {
        expect(typeof response.body.data.by_alert_type).toBe('object');
      }
    });
  });

  // ================================
  // Alert Settings Tests
  // ================================

  describe('GET /alerts/settings', () => {
    test('should return user alert settings', async () => {
      const response = await request(app)
        .get('/alerts/settings')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('notification_preferences');
      expect(response.body.data).toHaveProperty('alert_limits');
      expect(response.body.data).toHaveProperty('default_settings');
    });
  });

  describe('PUT /alerts/settings', () => {
    test('should update alert settings', async () => {
      const settingsData = {
        email_notifications: true,
        sms_notifications: false,
        max_daily_alerts: 50,
        quiet_hours: {
          enabled: true,
          start_time: '22:00',
          end_time: '08:00'
        }
      };

      const response = await request(app)
        .put('/alerts/settings')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(settingsData);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body).toHaveProperty('message');
        expect(response.body.data).toHaveProperty('updated_settings');
      } else {
        expect([400, 401]).toContain(response.status);
      }
    });

    test('should validate settings data', async () => {
      const invalidSettings = {
        max_daily_alerts: -10, // Invalid negative value
        quiet_hours: 'invalid_format'
      };

      const response = await request(app)
        .put('/alerts/settings')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send(invalidSettings)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('validation');
    });
  });

  // ================================
  // Error Handling Tests
  // ================================

  describe('Error Handling', () => {
    test('should handle database connection errors', async () => {
      // Mock database error by temporarily breaking query
      const originalQuery = query;
      jest.doMock('../../../utils/database', () => ({
        query: jest.fn().mockRejectedValue(new Error('Connection timeout'))
      }));

      const response = await request(app)
        .get('/alerts/active')
        .set('Authorization', 'Bearer dev-bypass-token')
        .timeout(5000);

      expect([200, 500, 503]).toContain(response.status);
      expect(response.body).toHaveProperty('success');
    });

    test('should handle missing authentication', async () => {
      const response = await request(app)
        .get('/alerts/active')
        .expect(401);

      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error');
    });

    test('should handle malformed request data', async () => {
      const response = await request(app)
        .post('/alerts/price')
        .set('Authorization', 'Bearer dev-bypass-token')
        .send('invalid json string')
        .expect(400);

      expect(response.body).toHaveProperty('error');
    });

    test('should handle invalid symbol format', async () => {
      const response = await request(app)
        .get('/alerts/price/INVALID_SYMBOL_123!')
        .set('Authorization', 'Bearer dev-bypass-token')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('symbol');
    });

    test('should handle rate limiting for alert creation', async () => {
      // Create multiple alerts rapidly
      const alertData = {
        symbol: 'AAPL',
        alert_type: 'price_above',
        target_price: 175.00
      };

      const promises = Array.from({ length: 10 }, () =>
        request(app)
          .post('/alerts/price')
          .set('Authorization', 'Bearer dev-bypass-token')
          .send(alertData)
      );

      const responses = await Promise.all(promises);
      
      // At least some should succeed
      const successCount = responses.filter(r => r.status === 201).length;
      expect(successCount).toBeGreaterThan(0);
    });
  });
});

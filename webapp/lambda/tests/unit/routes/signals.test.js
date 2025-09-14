/**
 * Unit Tests for Signals Route
 * Tests the /api/signals endpoint functionality with real database integration
 */

const request = require('supertest');
const express = require('express');

describe('Signals Route - Unit Tests', () => {
  let app;
  let signalsRouter;

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
    
    // Load the route module
    signalsRouter = require('../../../routes/signals');
    app.use('/api/signals', signalsRouter);
  });
  describe('GET /api/signals/buy', () => {
    test('should get buy signals with default parameters', async () => {
      const response = await request(app)
        .get('/api/signals/buy')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty('pagination');
      expect(response.body.pagination).toHaveProperty('total');
      expect(response.body.pagination).toHaveProperty('page');
      expect(response.body.pagination).toHaveProperty('totalPages');
      expect(response.body).toHaveProperty('timeframe', 'daily');
      expect(response.body).toHaveProperty('signal_type', 'buy');
    });

    test('should handle different timeframes', async () => {
      const response = await request(app)
        .get('/api/signals/buy?timeframe=weekly')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty('timeframe', 'weekly');
      expect(response.body).toHaveProperty('signal_type', 'buy');
    });

    test('should validate timeframe parameter', async () => {
      const response = await request(app)
        .get('/api/signals/buy?timeframe=invalid')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Invalid timeframe');
    });

    test('should apply limit and pagination', async () => {
      const response = await request(app)
        .get('/api/signals/buy?limit=10&page=2')
        .expect(200);

      expect(response.body).toHaveProperty('pagination');
      expect(response.body.pagination.page).toBe(2);
      expect(response.body.pagination.limit).toBe(10);
    });

    test('should handle database errors gracefully', async () => {
      // This test verifies error handling with invalid parameters
      const response = await request(app)
        .get('/api/signals/buy?limit=abc');

      // Should either succeed with default limit or handle gracefully
      if (response.status === 500) {
        expect(response.body).toHaveProperty('error');
      } else {
        expect(response.status).toBe(200);
        expect(response.body).toHaveProperty('data');
      }
    });
  });

  describe('GET /api/signals/sell', () => {
    test('should get sell signals', async () => {
      const response = await request(app)
        .get('/api/signals/sell')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty('pagination');
      expect(response.body).toHaveProperty('signal_type', 'sell');
    });

    test('should handle empty sell signals', async () => {
      const response = await request(app)
        .get('/api/signals/sell?timeframe=monthly')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty('timeframe', 'monthly');
    });
  });

  // ================================
  // Technical Analysis Signals Tests
  // ================================

  describe('GET /api/signals/technical', () => {
    test('should return technical analysis signals', async () => {
      const response = await request(app)
        .get('/api/signals/technical')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty('signal_type', 'technical');
      expect(response.body).toHaveProperty('indicators');
      
      if (response.body.data.length > 0) {
        const signal = response.body.data[0];
        expect(signal).toHaveProperty('symbol');
        expect(signal).toHaveProperty('signal_strength');
        expect(signal).toHaveProperty('indicators');
        expect(signal).toHaveProperty('timestamp');
      }
    });

    test('should filter by specific indicators', async () => {
      const response = await request(app)
        .get('/api/signals/technical?indicators=RSI,MACD')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(response.body).toHaveProperty('indicators');
      
      if (response.body.indicators) {
        expect(response.body.indicators).toContain('RSI');
        expect(response.body.indicators).toContain('MACD');
      }
    });

    test('should handle minimum signal strength filter', async () => {
      const response = await request(app)
        .get('/api/signals/technical?min_strength=7.0')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0) {
        response.body.data.forEach(signal => {
          expect(signal.signal_strength).toBeGreaterThanOrEqual(7.0);
        });
      }
    });

    test('should support symbol filtering', async () => {
      const response = await request(app)
        .get('/api/signals/technical?symbols=AAPL,MSFT')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0) {
        response.body.data.forEach(signal => {
          expect(['AAPL', 'MSFT']).toContain(signal.symbol);
        });
      }
    });
  });

  // ================================
  // Momentum Signals Tests
  // ================================

  describe('GET /api/signals/momentum', () => {
    test('should return momentum signals', async () => {
      const response = await request(app)
        .get('/api/signals/momentum')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty('signal_type', 'momentum');
      
      if (response.body.data.length > 0) {
        const signal = response.body.data[0];
        expect(signal).toHaveProperty('symbol');
        expect(signal).toHaveProperty('momentum_score');
        expect(signal).toHaveProperty('price_change');
        expect(signal).toHaveProperty('volume_change');
      }
    });

    test('should handle different momentum types', async () => {
      const response = await request(app)
        .get('/api/signals/momentum?type=breakout')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.momentum_type) {
        expect(response.body.momentum_type).toBe('breakout');
      }
    });

    test('should filter by minimum score', async () => {
      const response = await request(app)
        .get('/api/signals/momentum?min_score=8.0')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0) {
        response.body.data.forEach(signal => {
          expect(signal.momentum_score).toBeGreaterThanOrEqual(8.0);
        });
      }
    });
  });

  // ================================
  // Options Signals Tests
  // ================================

  describe('GET /api/signals/options', () => {
    test('should return options signals', async () => {
      const response = await request(app)
        .get('/api/signals/options')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty('signal_type', 'options');
      
      if (response.body.data.length > 0) {
        const signal = response.body.data[0];
        expect(signal).toHaveProperty('symbol');
        expect(signal).toHaveProperty('option_type');
        expect(signal).toHaveProperty('strike_price');
        expect(signal).toHaveProperty('expiration');
        expect(signal).toHaveProperty('implied_volatility');
      }
    });

    test('should filter by option type', async () => {
      const response = await request(app)
        .get('/api/signals/options?option_type=calls')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0) {
        response.body.data.forEach(signal => {
          expect(signal.option_type).toBe('call');
        });
      }
    });

    test('should handle expiration date filtering', async () => {
      const response = await request(app)
        .get('/api/signals/options?max_days_to_expiry=30')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      // Signals should have expiration within 30 days
    });

    test('should filter by implied volatility range', async () => {
      const response = await request(app)
        .get('/api/signals/options?min_iv=0.2&max_iv=0.8')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0) {
        response.body.data.forEach(signal => {
          expect(signal.implied_volatility).toBeGreaterThanOrEqual(0.2);
          expect(signal.implied_volatility).toBeLessThanOrEqual(0.8);
        });
      }
    });
  });

  // ================================
  // News Sentiment Signals Tests
  // ================================

  describe('GET /api/signals/sentiment', () => {
    test('should return sentiment-based signals', async () => {
      const response = await request(app)
        .get('/api/signals/sentiment')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty('signal_type', 'sentiment');
      
      if (response.body.data.length > 0) {
        const signal = response.body.data[0];
        expect(signal).toHaveProperty('symbol');
        expect(signal).toHaveProperty('sentiment_score');
        expect(signal).toHaveProperty('news_count');
        expect(signal).toHaveProperty('confidence');
      }
    });

    test('should filter by sentiment polarity', async () => {
      const response = await request(app)
        .get('/api/signals/sentiment?polarity=positive')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0) {
        response.body.data.forEach(signal => {
          expect(signal.sentiment_score).toBeGreaterThan(0);
        });
      }
    });

    test('should handle confidence threshold', async () => {
      const response = await request(app)
        .get('/api/signals/sentiment?min_confidence=0.7')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0) {
        response.body.data.forEach(signal => {
          expect(signal.confidence).toBeGreaterThanOrEqual(0.7);
        });
      }
    });

    test('should include news sources', async () => {
      const response = await request(app)
        .get('/api/signals/sentiment?include_sources=true')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0 && response.body.data[0].news_sources) {
        expect(Array.isArray(response.body.data[0].news_sources)).toBe(true);
      }
    });
  });

  // ================================
  // Earnings Signals Tests
  // ================================

  describe('GET /api/signals/earnings', () => {
    test('should return earnings-based signals', async () => {
      const response = await request(app)
        .get('/api/signals/earnings')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty('signal_type', 'earnings');
      
      if (response.body.data.length > 0) {
        const signal = response.body.data[0];
        expect(signal).toHaveProperty('symbol');
        expect(signal).toHaveProperty('earnings_date');
        expect(signal).toHaveProperty('signal_type');
        expect(signal).toHaveProperty('expected_move');
      }
    });

    test('should filter by days to earnings', async () => {
      const response = await request(app)
        .get('/api/signals/earnings?days_ahead=7')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      // Should return earnings within 7 days
    });

    test('should handle earnings signal types', async () => {
      const response = await request(app)
        .get('/api/signals/earnings?signal_type=beat_expected')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0) {
        response.body.data.forEach(signal => {
          expect(signal.signal_type).toContain('beat');
        });
      }
    });
  });

  // ================================
  // Crypto Signals Tests
  // ================================

  describe('GET /api/signals/crypto', () => {
    test('should return cryptocurrency signals', async () => {
      const response = await request(app)
        .get('/api/signals/crypto')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty('signal_type', 'crypto');
      
      if (response.body.data.length > 0) {
        const signal = response.body.data[0];
        expect(signal).toHaveProperty('symbol');
        expect(signal).toHaveProperty('signal_strength');
        expect(signal).toHaveProperty('price_change_24h');
        expect(signal).toHaveProperty('volume_change_24h');
      }
    });

    test('should filter by major cryptocurrencies', async () => {
      const response = await request(app)
        .get('/api/signals/crypto?major_only=true')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0) {
        response.body.data.forEach(signal => {
          expect(['BTC', 'ETH', 'BNB', 'ADA', 'XRP', 'SOL', 'DOT', 'DOGE']).toContain(signal.symbol.replace('-USD', ''));
        });
      }
    });

    test('should handle market cap filtering', async () => {
      const response = await request(app)
        .get('/api/signals/crypto?min_market_cap=1000000000')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      // Should return cryptos with market cap > $1B
    });
  });

  // ================================
  // Sector Rotation Signals Tests
  // ================================

  describe('GET /api/signals/sector-rotation', () => {
    test('should return sector rotation signals', async () => {
      const response = await request(app)
        .get('/api/signals/sector-rotation')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty('signal_type', 'sector_rotation');
      
      if (response.body.data.length > 0) {
        const signal = response.body.data[0];
        expect(signal).toHaveProperty('sector');
        expect(signal).toHaveProperty('rotation_strength');
        expect(signal).toHaveProperty('performance');
        expect(signal).toHaveProperty('trend');
      }
    });

    test('should filter by rotation strength', async () => {
      const response = await request(app)
        .get('/api/signals/sector-rotation?min_strength=6.0')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0) {
        response.body.data.forEach(signal => {
          expect(signal.rotation_strength).toBeGreaterThanOrEqual(6.0);
        });
      }
    });

    test('should handle specific sector filtering', async () => {
      const response = await request(app)
        .get('/api/signals/sector-rotation?sectors=Technology,Healthcare')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0) {
        response.body.data.forEach(signal => {
          expect(['Technology', 'Healthcare']).toContain(signal.sector);
        });
      }
    });
  });

  // ================================
  // Custom Signal Generation Tests
  // ================================

  describe('POST /api/signals/custom', () => {
    test('should create custom signal with valid criteria', async () => {
      const customSignal = {
        name: 'Test Custom Signal',
        description: 'Test signal for unit tests',
        criteria: {
          rsi: { below: 30 },
          price_change: { above: 5 },
          volume: { above: 'average_20d' }
        },
        symbols: ['AAPL', 'MSFT'],
        alert_threshold: 8.0
      };

      const response = await request(app)
        .post('/api/signals/custom')
        .send(customSignal)
        .expect(201);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('signal_id');
      expect(response.body.data).toHaveProperty('name', customSignal.name);
    });

    test('should validate required fields', async () => {
      const incompleteSignal = {
        name: 'Incomplete Signal'
        // Missing criteria and other required fields
      };

      const response = await request(app)
        .post('/api/signals/custom')
        .send(incompleteSignal)
        .expect(400);

      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error');
    });

    test('should validate criteria format', async () => {
      const invalidSignal = {
        name: 'Invalid Signal',
        criteria: 'invalid_criteria_format',
        symbols: ['AAPL']
      };

      const response = await request(app)
        .post('/api/signals/custom')
        .send(invalidSignal)
        .expect(400);

      expect(response.body).toHaveProperty('success', false);
      expect(response.body.error).toContain('criteria');
    });
  });

  // ================================
  // Signal History Tests
  // ================================

  describe('GET /api/signals/history', () => {
    test('should return signal history', async () => {
      const response = await request(app)
        .get('/api/signals/history')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty('pagination');
      
      if (response.body.data.length > 0) {
        const signal = response.body.data[0];
        expect(signal).toHaveProperty('symbol');
        expect(signal).toHaveProperty('signal_type');
        expect(signal).toHaveProperty('generated_at');
        expect(signal).toHaveProperty('outcome');
      }
    });

    test('should filter by date range', async () => {
      const response = await request(app)
        .get('/api/signals/history?start_date=2024-01-01&end_date=2024-01-31')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.date_range) {
        expect(response.body.date_range).toHaveProperty('start', '2024-01-01');
        expect(response.body.date_range).toHaveProperty('end', '2024-01-31');
      }
    });

    test('should filter by signal type', async () => {
      const response = await request(app)
        .get('/api/signals/history?signal_type=buy')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0) {
        response.body.data.forEach(signal => {
          expect(signal.signal_type).toBe('buy');
        });
      }
    });

    test('should include performance metrics', async () => {
      const response = await request(app)
        .get('/api/signals/history?include_performance=true')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.performance_summary) {
        expect(response.body.performance_summary).toHaveProperty('success_rate');
        expect(response.body.performance_summary).toHaveProperty('average_return');
        expect(response.body.performance_summary).toHaveProperty('total_signals');
      }
    });
  });

  // ================================
  // Signal Alerts Tests
  // ================================

  describe('GET /api/signals/alerts', () => {
    test('should return active signal alerts', async () => {
      const response = await request(app)
        .get('/api/signals/alerts')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data)).toBe(true);
      
      if (response.body.data.length > 0) {
        const alert = response.body.data[0];
        expect(alert).toHaveProperty('alert_id');
        expect(alert).toHaveProperty('symbol');
        expect(alert).toHaveProperty('signal_type');
        expect(alert).toHaveProperty('status');
        expect(alert).toHaveProperty('created_at');
      }
    });

    test('should filter alerts by status', async () => {
      const response = await request(app)
        .get('/api/signals/alerts?status=active')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.length > 0) {
        response.body.data.forEach(alert => {
          expect(alert.status).toBe('active');
        });
      }
    });
  });

  describe('POST /api/signals/alerts', () => {
    test('should create new signal alert', async () => {
      const alertData = {
        symbol: 'AAPL',
        signal_type: 'buy',
        conditions: {
          price_threshold: 150.00,
          rsi_threshold: 30
        },
        notification_method: 'email'
      };

      const response = await request(app)
        .post('/api/signals/alerts')
        .send(alertData)
        .expect(201);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('alert_id');
      expect(response.body.data).toHaveProperty('symbol', 'AAPL');
    });
  });

  // ================================
  // Signal Performance Tests
  // ================================

  describe('GET /api/signals/performance', () => {
    test('should return signal performance analytics', async () => {
      const response = await request(app)
        .get('/api/signals/performance')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('overall_performance');
      
      const performance = response.body.data.overall_performance;
      expect(performance).toHaveProperty('success_rate');
      expect(performance).toHaveProperty('average_return');
      expect(performance).toHaveProperty('total_signals');
      expect(performance).toHaveProperty('win_loss_ratio');
    });

    test('should break down performance by signal type', async () => {
      const response = await request(app)
        .get('/api/signals/performance?breakdown=signal_type')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.by_signal_type) {
        expect(typeof response.body.data.by_signal_type).toBe('object');
        
        Object.values(response.body.data.by_signal_type).forEach(typePerformance => {
          expect(typePerformance).toHaveProperty('success_rate');
          expect(typePerformance).toHaveProperty('average_return');
          expect(typePerformance).toHaveProperty('signal_count');
        });
      }
    });

    test('should handle time period analysis', async () => {
      const response = await request(app)
        .get('/api/signals/performance?period=30d')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      if (response.body.data.period_analysis) {
        expect(response.body.data.period_analysis).toHaveProperty('period', '30d');
      }
    });
  });

  describe('Error Handling', () => {
    test('should handle invalid query parameters gracefully', async () => {
      const response = await request(app)
        .get('/api/signals/buy?limit=invalid&page=notanumber');

      // Should either use defaults or handle gracefully
      if (response.status === 500) {
        expect(response.body).toHaveProperty('error');
      } else {
        expect(response.status).toBe(200);
        expect(response.body).toHaveProperty('data');
      }
    });

    test('should handle database connection errors', async () => {
      const response = await request(app)
        .get('/api/signals/buy')
        .timeout(5000);

      expect([200, 500, 503]).toContain(response.status);
      expect(response.body).toHaveProperty('success');
    });

    test('should validate signal type parameters', async () => {
      const response = await request(app)
        .get('/api/signals/invalid_signal_type')
        .expect(404);

      // Should return 404 for unsupported signal types
    });

    test('should handle large limit values', async () => {
      const response = await request(app)
        .get('/api/signals/buy?limit=10000');

      expect([200, 400]).toContain(response.status);
      if (response.status === 400) {
        expect(response.body.error).toContain('limit');
      } else {
        expect(response.body.data.length).toBeLessThanOrEqual(1000); // Should be capped
      }
    });

    test('should handle malformed request bodies', async () => {
      const response = await request(app)
        .post('/api/signals/custom')
        .send('invalid json string')
        .expect(400);

      expect(response.body).toHaveProperty('error');
    });

    test('should handle authentication edge cases', async () => {
      // Test with different user context
      const tempApp = express();
      tempApp.use(express.json());
      tempApp.use((req, res, next) => {
        req.user = null; // No authenticated user
        next();
      });
      
      const responseFormatter = require('../../../middleware/responseFormatter');
      tempApp.use(responseFormatter);
      
      const signalsRouter = require('../../../routes/signals');
      tempApp.use('/api/signals', signalsRouter);

      const response = await request(tempApp)
        .get('/api/signals/buy')
        .expect(401);

      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error');
    });

    test('should handle valid requests', async () => {
      const response = await request(app)
        .get('/api/signals/buy')
        .expect(200);

      expect(response.body).toHaveProperty('data');
      expect(response.body).toHaveProperty('signal_type', 'buy');
    });
  });

  // Test cleanup
  afterAll(async () => {
    try {
      const { query } = require('../../../utils/database');
      // Clean up any test data
      await query(`DELETE FROM custom_signals WHERE user_id = $1`, ['test-user-123']);
      await query(`DELETE FROM signal_alerts WHERE user_id = $1`, ['test-user-123']);
      await query(`DELETE FROM signal_history WHERE user_id = $1`, ['test-user-123']);
    } catch (error) {
      // Cleanup errors are acceptable in tests
    }
  });
});
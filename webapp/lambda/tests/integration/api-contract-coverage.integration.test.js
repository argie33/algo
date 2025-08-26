/**
 * API Contract Coverage Integration Tests
 * 
 * Recreated from deleted contract tests to validate API endpoint contracts,
 * response schemas, error handling, and backward compatibility.
 * 
 * Tests ensure:
 * - Response structure consistency
 * - Data type validation
 * - Required field presence  
 * - Error response formats
 * - API versioning compliance
 */

const request = require('supertest');
const { app } = require('../../index');
const jwt = require('jsonwebtoken');

describe('API Contract Coverage Integration Tests', () => {
  const validUserId = 'contract-test-user';
  const validToken = jwt.sign({ sub: validUserId }, process.env.JWT_SECRET || 'test-secret', { expiresIn: '1h' });
  const invalidToken = 'invalid-token-format';
  
  let _testDatabase;

  beforeAll(async () => {
    _testDatabase = global.TEST_DATABASE || require('../testDatabase').createTestDatabase();
  });

  describe('Standard Response Format Contract', () => {
    test('successful responses follow standard format', async () => {
      const response = await request(app)
        .get('/health')
        .expect(200);

      // Validate standard success response structure
      expect(response.body).toMatchObject({
        success: true,
        data: expect.any(Object)
      });

      // Check for timestamp if present
      if (response.body.timestamp) {
        expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
        expect(response.body.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
      }
    });

    test('error responses follow standard format', async () => {
      const response = await request(app)
        .get('/api/nonexistent-endpoint')
        .expect(404);

      // Validate standard error response structure
      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });

      // Error message should be descriptive
      expect(response.body.error).toBeTruthy();
      expect(response.body.error.length).toBeGreaterThan(0);
    });

    test('authentication errors follow standard format', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${invalidToken}`)
        .expect(401);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });
    });
  });

  describe('Health Endpoint Contract', () => {
    test('/health endpoint response schema', async () => {
      const response = await request(app)
        .get('/health')
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          status: expect.any(String),
          services: expect.any(Object)
        })
      });

      // Check for optional fields that should be present for contract compliance
      if (response.body.data.uptime !== undefined) {
        expect(typeof response.body.data.uptime).toBe('string');
      }
      
      if (response.body.data.version !== undefined) {
        expect(response.body.data.version).toMatch(/^\d+\.\d+\.\d+$/);
      }
    });

    test('/health/database endpoint exists and responds', async () => {
      const response = await request(app)
        .get('/health/database');

      expect([200, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          data: expect.objectContaining({
            status: expect.stringMatching(/^(healthy|degraded)$/),
            responseTime: expect.any(Number)
          })
        });
      }
    });
  });

  describe('Portfolio Endpoints Contract', () => {
    test('/api/portfolio/holdings response structure', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${validToken}`);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          data: expect.any(Array)
        });

        // Validate holding structure if any holdings exist
        if (response.body.data.length > 0) {
          const holding = response.body.data[0];
          expect(holding).toMatchObject({
            symbol: expect.any(String),
            quantity: expect.any(Number),
            avgPrice: expect.any(Number)
          });
        }
      }
    });

    test('/api/portfolio/summary response structure', async () => {
      const response = await request(app)
        .get('/api/portfolio/summary')
        .set('Authorization', `Bearer ${validToken}`);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          data: expect.objectContaining({
            totalValue: expect.any(Number),
            totalGainLoss: expect.any(Number)
          })
        });
      }
    });

    test('/api/portfolio/analytics response structure', async () => {
      const response = await request(app)
        .get('/api/portfolio/analytics')
        .set('Authorization', `Bearer ${validToken}`);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          data: expect.any(Object)
        });

        // Check for expected analytics structure
        if (response.body.data.attribution) {
          expect(response.body.data.attribution).toMatchObject({
            sectorAttribution: expect.any(Array),
            stockAttribution: expect.any(Array)
          });
        }
      }
    });
  });

  describe('Market Data Endpoints Contract', () => {
    test('/api/market/overview response structure', async () => {
      const response = await request(app)
        .get('/api/market/overview');

      expect([200, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          data: expect.any(Object)
        });

        // Check for expected market overview fields
        const data = response.body.data;
        if (data.indices) {
          expect(data.indices).toBeInstanceOf(Array);
          if (data.indices.length > 0) {
            expect(data.indices[0]).toMatchObject({
              symbol: expect.any(String),
              price: expect.any(Number),
              change: expect.any(Number),
              changePercent: expect.any(Number)
            });
          }
        }
      }
    });

    test('/api/stocks/prices response structure', async () => {
      const response = await request(app)
        .get('/api/stocks/prices?symbol=AAPL');

      expect([200, 404, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          data: expect.any(Array)
        });

        if (response.body.data.length > 0) {
          const priceData = response.body.data[0];
          expect(priceData).toMatchObject({
            date: expect.any(String),
            price: expect.any(Number)
          });
        }
      }
    });
  });

  describe('Settings Endpoints Contract', () => {
    test('/api/settings/api-keys response structure', async () => {
      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`);

      expect([200, 401]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          data: expect.any(Object)
        });

        // Check for expected API keys structure
        if (response.body.data.apiKeys) {
          expect(response.body.data.apiKeys).toBeInstanceOf(Array);
        }
      }
    });

    test('POST /api/settings/api-keys accepts proper format', async () => {
      const apiKeyData = {
        provider: 'alpaca',
        keyId: 'test-key-id',
        secret: 'test-secret'
      };

      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .send(apiKeyData);

      expect([200, 400, 401]).toContain(response.status);

      // Should always return proper response format
      expect(response.body).toMatchObject({
        success: expect.any(Boolean)
      });

      if (!response.body.success) {
        expect(response.body.error).toBeTruthy();
      }
    });
  });

  describe('Trading Signals Contract', () => {
    test('/api/signals/buy response structure', async () => {
      const response = await request(app)
        .get('/api/signals/buy');

      expect([200, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          data: expect.any(Array),
          timeframe: expect.any(String),
          signal_type: 'buy'
        });

        if (response.body.data.length > 0) {
          const signal = response.body.data[0];
          expect(signal).toMatchObject({
            symbol: expect.any(String),
            signal: expect.any(Number),
            date: expect.any(String)
          });
        }
      }
    });

    test('/api/signals/sell response structure', async () => {
      const response = await request(app)
        .get('/api/signals/sell');

      expect([200, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          data: expect.any(Array),
          timeframe: expect.any(String),
          signal_type: 'sell'
        });
      }
    });
  });

  describe('Error Handling Contract', () => {
    test('400 Bad Request format', async () => {
      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .send({}); // Invalid empty body

      expect(response.status).toBe(400);
      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });
    });

    test('401 Unauthorized format', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .expect(401);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });
    });

    test('500 Internal Server Error format', async () => {
      // This test may not trigger a 500 in all environments
      const response = await request(app)
        .get('/api/test-internal-error-route-that-does-not-exist');

      // Should get 404 for non-existent route, but format should be consistent
      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String)
      });
    });
  });

  describe('Response Time Contract', () => {
    test('health endpoint responds within reasonable time', async () => {
      const startTime = Date.now();
      
      await request(app)
        .get('/health')
        .expect(200);
        
      const responseTime = Date.now() - startTime;
      
      // Health endpoint should respond within 5 seconds
      expect(responseTime).toBeLessThan(5000);
    });

    test('market overview responds within reasonable time', async () => {
      const startTime = Date.now();
      
      const response = await request(app)
        .get('/api/market/overview');
        
      const responseTime = Date.now() - startTime;
      
      // Market data should respond within 10 seconds
      expect(responseTime).toBeLessThan(10000);
      
      // Successful responses should be relatively fast
      if (response.status === 200) {
        expect(responseTime).toBeLessThan(3000);
      }
    });
  });
});
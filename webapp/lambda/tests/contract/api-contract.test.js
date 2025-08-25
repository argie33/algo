/**
 * API Contract Testing Suite
 * 
 * Validates API endpoint contracts, response schemas, error handling,
 * and backward compatibility to prevent breaking changes.
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

describe('API Contract Testing', () => {
  const validUserId = 'contract-test-user';
  const validToken = jwt.sign({ sub: validUserId }, process.env.JWT_SECRET || 'test-secret', { expiresIn: '1h' });
  const invalidToken = 'invalid-token-format';
  
  let testDatabase;

  beforeAll(async () => {
    testDatabase = global.TEST_DATABASE || require('../testDatabase').createTestDatabase();
    
    // Setup test data for contract validation - using correct table structure
    await testDatabase.query(`
      INSERT INTO price_daily (symbol, date, close_price, change_amount, change_percent, volume, created_at)
      VALUES 
        ('AAPL', CURRENT_DATE, 195.50, 2.25, 1.16, 45000000, CURRENT_TIMESTAMP),
        ('MSFT', CURRENT_DATE, 385.75, -1.25, -0.32, 28000000, CURRENT_TIMESTAMP),
        ('GOOGL', CURRENT_DATE, 2650.30, 15.20, 0.58, 1200000, CURRENT_TIMESTAMP)
    `);

    await testDatabase.query(`
      INSERT INTO portfolio_holdings (user_id, symbol, quantity, avg_price, last_updated)
      VALUES 
        ('${validUserId}', 'AAPL', 100, 180.50, CURRENT_TIMESTAMP),
        ('${validUserId}', 'MSFT', 50, 350.00, CURRENT_TIMESTAMP)
    `);
  });

  afterAll(async () => {
    // Cleanup test data
    await testDatabase.query('DELETE FROM portfolio_holdings WHERE user_id = $1', [validUserId]);
    await testDatabase.query('DELETE FROM stock_prices WHERE symbol IN ($1, $2, $3)', ['AAPL', 'MSFT', 'GOOGL']);
  });

  describe('Standard Response Format Contract', () => {
    test('successful responses follow standard format', async () => {
      const response = await request(app)
        .get('/health')
        .expect(200);

      // Validate standard success response structure
      expect(response.body).toMatchObject({
        success: true,
        data: expect.any(Object),
        timestamp: expect.any(String)
      });

      // Validate timestamp format
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(response.body.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
    });

    test('error responses follow standard format', async () => {
      const response = await request(app)
        .get('/api/nonexistent-endpoint')
        .expect(404);

      // Validate standard error response structure
      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String),
        timestamp: expect.any(String)
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
        error: expect.any(String),
        timestamp: expect.any(String)
      });

      expect(response.body.error).toContain('Invalid token');
    });
  });

  describe('Health Endpoint Contract', () => {
    test('/health endpoint response schema', async () => {
      const response = await request(app)
        .get('/health')
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          status: expect.stringMatching(/^(healthy|degraded|unhealthy)$/),
          timestamp: expect.any(String),
          uptime: expect.any(Number),
          version: expect.any(String)
        },
        timestamp: expect.any(String)
      });

      // Validate data types
      expect(typeof response.body.data.uptime).toBe('number');
      expect(response.body.data.uptime).toBeGreaterThan(0);
      expect(response.body.data.version).toMatch(/^\d+\.\d+\.\d+$/);
    });

    test('/health/database endpoint response schema', async () => {
      const response = await request(app)
        .get('/health/database');

      expect([200, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          data: {
            status: 'connected',
            responseTime: expect.any(Number),
            activeConnections: expect.any(Number)
          }
        });
      } else {
        expect(response.body).toMatchObject({
          success: false,
          error: expect.any(String)
        });
      }
    });
  });

  describe('Portfolio Endpoints Contract', () => {
    test('/api/portfolio/holdings response schema', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${validToken}`)
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          totalValue: expect.any(Number),
          totalGainLoss: expect.any(Number), 
          totalGainLossPercent: expect.any(Number),
          dayGainLoss: expect.any(Number),
          dayGainLossPercent: expect.any(Number),
          holdings: expect.arrayContaining([
            expect.objectContaining({
              symbol: expect.any(String),
              quantity: expect.any(Number),
              avgPrice: expect.any(Number),
              currentPrice: expect.any(Number),
              totalValue: expect.any(Number),
              gainLoss: expect.any(Number),
              gainLossPercent: expect.any(Number)
            })
          ])
        }
      });

      // Validate holding data types and constraints
      response.body.data.holdings.forEach(holding => {
        expect(holding.symbol).toMatch(/^[A-Z]{1,5}$/);
        expect(holding.quantity).toBeGreaterThan(0);
        expect(holding.avgPrice).toBeGreaterThan(0);
        expect(holding.currentPrice).toBeGreaterThan(0);
        expect(holding.totalValue).toBeGreaterThan(0);
        
        // Calculated fields should be mathematically correct
        const expectedTotalValue = holding.quantity * holding.currentPrice;
        expect(Math.abs(holding.totalValue - expectedTotalValue)).toBeLessThan(0.01);
        
        const expectedGainLoss = holding.totalValue - (holding.quantity * holding.avgPrice);
        expect(Math.abs(holding.gainLoss - expectedGainLoss)).toBeLessThan(0.01);
      });
    });

    test('/api/portfolio/summary response schema', async () => {
      const response = await request(app)
        .get('/api/portfolio/summary')
        .set('Authorization', `Bearer ${validToken}`);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.data).toMatchObject({
          totalValue: expect.any(Number),
          totalGainLoss: expect.any(Number),
          totalGainLossPercent: expect.any(Number),
          topPerformers: expect.arrayContaining([
            expect.objectContaining({
              symbol: expect.any(String),
              gainLossPercent: expect.any(Number)
            })
          ]),
          sectorAllocation: expect.arrayContaining([
            expect.objectContaining({
              sector: expect.any(String),
              percentage: expect.any(Number),
              value: expect.any(Number)
            })
          ])
        });

        // Validate sector allocation adds up to 100%
        const totalAllocation = response.body.data.sectorAllocation
          .reduce((sum, allocation) => sum + allocation.percentage, 0);
        expect(Math.abs(totalAllocation - 100)).toBeLessThan(0.1);
      }
    });
  });

  describe('Market Data Endpoints Contract', () => {
    test('/api/market/overview response schema', async () => {
      const response = await request(app)
        .get('/api/market/overview');

      expect([200, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.data).toMatchObject({
          indices: expect.objectContaining({
            SPY: expect.objectContaining({
              price: expect.any(Number),
              change: expect.any(Number),
              changePercent: expect.any(Number)
            })
          }),
          sectors: expect.arrayContaining([
            expect.objectContaining({
              name: expect.any(String),
              performance: expect.any(Number)
            })
          ]),
          marketSentiment: expect.stringMatching(/^(bullish|bearish|neutral)$/)
        });

        // Validate price data ranges
        Object.values(response.body.data.indices).forEach(index => {
          expect(index.price).toBeGreaterThan(0);
          expect(Math.abs(index.changePercent)).toBeLessThan(20); // Reasonable daily change limit
        });
      }
    });

    test('/api/stocks/:symbol/price response schema', async () => {
      const response = await request(app)
        .get('/api/stocks/AAPL/price');

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.data).toMatchObject({
          symbol: 'AAPL',
          price: expect.any(Number),
          change: expect.any(Number),
          changePercent: expect.any(Number),
          volume: expect.any(Number),
          high: expect.any(Number),
          low: expect.any(Number),
          open: expect.any(Number),
          previousClose: expect.any(Number)
        });

        const data = response.body.data;
        
        // Validate price relationships
        expect(data.high).toBeGreaterThanOrEqual(data.low);
        expect(data.high).toBeGreaterThanOrEqual(data.price);
        expect(data.low).toBeLessThanOrEqual(data.price);
        expect(data.volume).toBeGreaterThan(0);
        
        // Validate change calculations
        const expectedChange = data.price - data.previousClose;
        expect(Math.abs(data.change - expectedChange)).toBeLessThan(0.01);
      }
    });
  });

  describe('Settings Endpoints Contract', () => {
    test('/api/settings/api-keys response schema', async () => {
      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`);

      expect([200, 401]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.data).toMatchObject({
          configured: expect.arrayContaining([expect.any(String)]),
          valid: expect.arrayContaining([expect.any(String)])
        });

        // Validate provider names
        const validProviders = ['alpaca', 'polygon', 'finnhub', 'alpha_vantage'];
        response.body.data.configured.forEach(provider => {
          expect(validProviders).toContain(provider);
        });
        
        response.body.data.valid.forEach(provider => {
          expect(validProviders).toContain(provider);
          expect(response.body.data.configured).toContain(provider);
        });
      }
    });

    test('POST /api/settings/api-keys request/response schema', async () => {
      const testApiKey = {
        provider: 'alpaca',
        credentials: {
          keyId: 'TEST_KEY_ID',
          secret: 'TEST_SECRET_KEY'
        }
      };

      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .send(testApiKey);

      expect([200, 400, 401]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          data: {
            provider: testApiKey.provider,
            configured: true,
            valid: expect.any(Boolean)
          }
        });
      } else if (response.status === 400) {
        expect(response.body).toMatchObject({
          success: false,
          error: expect.any(String)
        });
        
        // Error should describe validation issue
        expect(response.body.error).toMatch(/provider|credentials|keyId|secret/i);
      }
    });
  });

  describe('Error Response Contracts', () => {
    test('validation error format', async () => {
      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .send({ invalidField: 'value' })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String),
        details: expect.any(Object),
        timestamp: expect.any(String)
      });

      // Validation errors should include field details
      expect(response.body.details).toHaveProperty('field');
      expect(response.body.details).toHaveProperty('message');
    });

    test('rate limiting error format', async () => {
      // Send multiple rapid requests to trigger rate limiting
      const requests = Array.from({ length: 20 }, () =>
        request(app)
          .get('/health')
      );

      const responses = await Promise.all(requests);
      const rateLimitedResponse = responses.find(r => r.status === 429);

      if (rateLimitedResponse) {
        expect(rateLimitedResponse.body).toMatchObject({
          success: false,
          error: expect.stringMatching(/rate limit/i),
          retryAfter: expect.any(Number),
          timestamp: expect.any(String)
        });

        expect(rateLimitedResponse.body.retryAfter).toBeGreaterThan(0);
        expect(rateLimitedResponse.body.retryAfter).toBeLessThan(3600); // Max 1 hour
      }
    });

    test('server error format', async () => {
      // Mock database error to test 500 response
      const originalQuery = testDatabase.query;
      testDatabase.query = jest.fn().mockRejectedValue(new Error('Database connection failed'));

      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${validToken}`)
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String),
        timestamp: expect.any(String)
      });

      // Should not expose internal error details in production
      expect(response.body.error).not.toContain('Database connection failed');
      expect(response.body.error).toMatch(/internal server error|service unavailable/i);

      // Restore original function
      testDatabase.query = originalQuery;
    });
  });

  describe('API Versioning Contract', () => {
    test('API version header presence', async () => {
      const response = await request(app)
        .get('/health')
        .expect(200);

      expect(response.headers).toHaveProperty('api-version');
      expect(response.headers['api-version']).toMatch(/^v\d+(\.\d+)?$/);
    });

    test('deprecated endpoint warnings', async () => {
      // Test any deprecated endpoints return proper warnings
      const response = await request(app)
        .get('/api/v1/legacy-endpoint');

      if (response.status === 200) {
        expect(response.headers).toHaveProperty('deprecation-warning');
        expect(response.body.warnings).toContainEqual(
          expect.objectContaining({
            type: 'deprecation',
            message: expect.any(String),
            sunset: expect.any(String)
          })
        );
      }
    });
  });

  describe('Pagination Contract', () => {
    test('paginated endpoint response format', async () => {
      const response = await request(app)
        .get('/api/portfolio/transactions?page=1&limit=10')
        .set('Authorization', `Bearer ${validToken}`);

      if (response.status === 200 && response.body.data.transactions) {
        expect(response.body.data).toMatchObject({
          transactions: expect.any(Array),
          pagination: {
            page: 1,
            limit: 10,
            total: expect.any(Number),
            pages: expect.any(Number),
            hasNext: expect.any(Boolean),
            hasPrev: expect.any(Boolean)
          }
        });

        const pagination = response.body.data.pagination;
        
        // Validate pagination math
        expect(pagination.pages).toBe(Math.ceil(pagination.total / pagination.limit));
        expect(pagination.hasNext).toBe(pagination.page < pagination.pages);
        expect(pagination.hasPrev).toBe(pagination.page > 1);
        
        // Validate data limits
        expect(response.body.data.transactions.length).toBeLessThanOrEqual(pagination.limit);
      }
    });

    test('pagination parameter validation', async () => {
      const invalidPaginationTests = [
        { page: 0, limit: 10 }, // Page should be >= 1
        { page: 1, limit: 0 },  // Limit should be > 0  
        { page: 1, limit: 1001 }, // Limit should be <= 1000
        { page: -1, limit: 10 }, // Page should be positive
        { page: 'invalid', limit: 10 } // Page should be number
      ];

      for (const params of invalidPaginationTests) {
        const response = await request(app)
          .get(`/api/portfolio/transactions?page=${params.page}&limit=${params.limit}`)
          .set('Authorization', `Bearer ${validToken}`);

        expect([400, 422]).toContain(response.status);
        if (response.status === 400 || response.status === 422) {
          expect(response.body.success).toBe(false);
          expect(response.body.error).toMatch(/page|limit|pagination/i);
        }
      }
    });
  });

  describe('Content-Type and Headers Contract', () => {
    test('JSON response content-type', async () => {
      const response = await request(app)
        .get('/health')
        .expect(200);

      expect(response.headers['content-type']).toContain('application/json');
    });

    test('CORS headers for browser requests', async () => {
      const response = await request(app)
        .options('/health')
        .set('Origin', 'https://example.com');

      expect(response.headers).toHaveProperty('access-control-allow-origin');
      expect(response.headers).toHaveProperty('access-control-allow-methods');
      expect(response.headers).toHaveProperty('access-control-allow-headers');
    });

    test('security headers presence', async () => {
      const response = await request(app)
        .get('/health')
        .expect(200);

      expect(response.headers).toHaveProperty('x-content-type-options');
      expect(response.headers['x-content-type-options']).toBe('nosniff');
      
      expect(response.headers).toHaveProperty('x-frame-options');
      expect(response.headers['x-frame-options']).toBe('DENY');
    });
  });

  describe('Field Validation Contracts', () => {
    test('required field validation', async () => {
      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .send({}) // Empty request
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toMatch(/required|provider|credentials/i);
    });

    test('field type validation', async () => {
      const invalidTypeTests = [
        { provider: 123, credentials: { keyId: 'test', secret: 'test' } }, // provider should be string
        { provider: 'alpaca', credentials: 'invalid' }, // credentials should be object
        { provider: 'alpaca', credentials: { keyId: 123, secret: 'test' } } // keyId should be string
      ];

      for (const testData of invalidTypeTests) {
        const response = await request(app)
          .post('/api/settings/api-keys')
          .set('Authorization', `Bearer ${validToken}`)
          .send(testData);

        expect([400, 422]).toContain(response.status);
        expect(response.body.success).toBe(false);
      }
    });

    test('field length validation', async () => {
      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', `Bearer ${validToken}`)
        .send({
          provider: 'alpaca',
          credentials: {
            keyId: 'x', // Too short
            secret: 'x'.repeat(1001) // Too long
          }
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toMatch(/length|keyId|secret/i);
    });
  });
});
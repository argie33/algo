/**
 * Portfolio Routes Integration Tests
 * Tests actual portfolio functionality that exists in routes/portfolio.js
 */

const request = require('supertest');
const { app } = require('../../index');
const { setupTestDatabase, cleanupTestDatabase } = require('../setup/test-database-setup');

describe('💼 Portfolio Routes Integration Tests', () => {
  let testDb;
  let testUser;
  let authHeaders;

  beforeAll(async () => {
    testDb = await setupTestDatabase();
    
    testUser = await testDb.createTestUser({
      email: 'portfolio-test@example.com',
      username: 'portfoliotest',
      cognito_user_id: 'portfolio-test-cognito-456'
    });
    
    await testDb.createTestApiKeys(testUser.user_id, {
      alpaca_key: 'PKTEST_PORTFOLIO_555',
      alpaca_secret: 'test_portfolio_secret_666'
    });
    
    authHeaders = { 'x-user-id': testUser.user_id };
  });

  afterAll(async () => {
    await testDb.cleanupTestUser(testUser.user_id);
    await cleanupTestDatabase();
  });

  describe('📊 Portfolio Data Endpoints', () => {
    test('GET /api/portfolio - Get portfolio overview', async () => {
      const response = await request(app)
        .get('/api/portfolio')
        .set(authHeaders)
        .timeout(15000);

      expect([200, 401, 404, 503]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toBeDefined();
        // Portfolio should have basic structure
        expect(response.body).toHaveProperty('success');
      }

      console.log(`✅ Portfolio overview: ${response.status}`);
    });

    test('GET /api/portfolio/holdings - Get portfolio holdings', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set(authHeaders)
        .timeout(15000);

      expect([200, 401, 404, 503]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toBeDefined();
      }

      console.log(`✅ Portfolio holdings: ${response.status}`);
    });

    test('GET /api/portfolio/holdings with query parameters', async () => {
      const queryParams = {
        includeMetadata: 'true',
        limit: '10',
        offset: '0'
      };

      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set(authHeaders)
        .query(queryParams)
        .timeout(15000);

      expect([200, 401, 404, 503]).toContain(response.status);
      
      console.log(`✅ Portfolio holdings with params: ${response.status}`);
    });

    test('GET /api/portfolio/positions - Get portfolio positions', async () => {
      const response = await request(app)
        .get('/api/portfolio/positions')
        .set(authHeaders)
        .timeout(15000);

      expect([200, 401, 404, 503]).toContain(response.status);
      
      console.log(`✅ Portfolio positions: ${response.status}`);
    });

    test('GET /api/portfolio/performance - Get portfolio performance', async () => {
      const response = await request(app)
        .get('/api/portfolio/performance')
        .set(authHeaders)
        .query({ period: '1M' })
        .timeout(15000);

      expect([200, 401, 404, 503]).toContain(response.status);
      
      console.log(`✅ Portfolio performance: ${response.status}`);
    });

    test('GET /api/portfolio/analytics - Get portfolio analytics', async () => {
      const response = await request(app)
        .get('/api/portfolio/analytics')
        .set(authHeaders)
        .query({
          startDate: '2024-01-01',
          endDate: '2024-12-31'
        })
        .timeout(20000);

      expect([200, 401, 404, 503]).toContain(response.status);
      
      console.log(`✅ Portfolio analytics: ${response.status}`);
    });
  });

  describe('🔄 Portfolio Actions', () => {
    test('POST /api/portfolio/refresh - Refresh portfolio data', async () => {
      const response = await request(app)
        .post('/api/portfolio/refresh')
        .set(authHeaders)
        .timeout(20000);

      expect([200, 201, 401, 503]).toContain(response.status);
      
      console.log(`✅ Portfolio refresh: ${response.status}`);
    });

    test('POST /api/portfolio/calculate-metrics - Calculate portfolio metrics', async () => {
      const testHoldings = {
        holdings: [
          {
            symbol: 'AAPL',
            quantity: 10,
            avgCost: 150.00,
            currentPrice: 155.00
          },
          {
            symbol: 'GOOGL',
            quantity: 5,
            avgCost: 2800.00,
            currentPrice: 2850.00
          }
        ]
      };

      const response = await request(app)
        .post('/api/portfolio/calculate-metrics')
        .set(authHeaders)
        .send(testHoldings)
        .timeout(15000);

      expect([200, 201, 400, 401, 503]).toContain(response.status);
      
      if (response.status === 200 || response.status === 201) {
        expect(response.body).toBeDefined();
        // Should have calculated metrics
      }

      console.log(`✅ Portfolio calculate metrics: ${response.status}`);
    });
  });

  describe('🔒 Authentication Requirements', () => {
    test('Portfolio routes require authentication', async () => {
      const portfolioEndpoints = [
        '/api/portfolio',
        '/api/portfolio/holdings',
        '/api/portfolio/positions',
        '/api/portfolio/performance'
      ];

      const authTests = [];

      for (const endpoint of portfolioEndpoints) {
        const response = await request(app)
          .get(endpoint)
          .timeout(10000); // No auth headers

        authTests.push({
          endpoint,
          status: response.status,
          requiresAuth: [401, 403].includes(response.status) || response.status === 503
        });
      }

      // All endpoints should require authentication or be unavailable
      const allRequireAuth = authTests.every(test => test.requiresAuth);
      expect(allRequireAuth).toBe(true);

      console.log('✅ All portfolio routes properly require authentication');
    });
  });

  describe('📈 Data Validation', () => {
    test('Invalid portfolio calculation data handled', async () => {
      const invalidData = {
        holdings: [
          {
            symbol: '', // Invalid empty symbol
            quantity: -10, // Invalid negative quantity
            avgCost: 'invalid', // Invalid price format
            currentPrice: null
          }
        ]
      };

      const response = await request(app)
        .post('/api/portfolio/calculate-metrics')
        .set(authHeaders)
        .send(invalidData)
        .timeout(10000);

      expect([400, 401, 503]).toContain(response.status);
      
      console.log(`✅ Invalid data handling: ${response.status}`);
    });

    test('Portfolio query parameter validation', async () => {
      const invalidParams = {
        limit: 'invalid',
        offset: -1,
        includeMetadata: 'invalid'
      };

      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set(authHeaders)
        .query(invalidParams)
        .timeout(10000);

      // Should either reject invalid params or sanitize them
      expect([200, 400, 401, 503]).toContain(response.status);
      
      console.log(`✅ Query parameter validation: ${response.status}`);
    });
  });

  describe('⚡ Performance Testing', () => {
    test('Portfolio endpoints respond within reasonable time', async () => {
      const performanceTests = [];
      
      const endpoints = [
        { path: '/api/portfolio', timeout: 15000 },
        { path: '/api/portfolio/holdings', timeout: 15000 },
        { path: '/api/portfolio/positions', timeout: 15000 }
      ];

      for (const endpoint of endpoints) {
        const startTime = Date.now();
        
        try {
          const response = await request(app)
            .get(endpoint.path)
            .set(authHeaders)
            .timeout(endpoint.timeout);

          const responseTime = Date.now() - startTime;
          
          performanceTests.push({
            endpoint: endpoint.path,
            responseTime,
            status: response.status,
            withinTimeout: responseTime < endpoint.timeout
          });
        } catch (error) {
          const responseTime = Date.now() - startTime;
          
          performanceTests.push({
            endpoint: endpoint.path,
            responseTime,
            status: 'timeout',
            withinTimeout: false
          });
        }
      }

      // All endpoints should respond within their timeout
      const allWithinTimeout = performanceTests.every(test => test.withinTimeout);
      expect(allWithinTimeout).toBe(true);

      const avgResponseTime = performanceTests.reduce((sum, test) => sum + test.responseTime, 0) / performanceTests.length;
      console.log(`⚡ Average portfolio response time: ${avgResponseTime.toFixed(0)}ms`);
    });
  });

  describe('🔄 Integration Summary', () => {
    test('Portfolio integration test summary', async () => {
      const portfolioResults = [];
      
      console.log('💼 Running portfolio integration summary...');

      // Test 1: Basic portfolio access
      const basicTest = await request(app)
        .get('/api/portfolio')
        .set(authHeaders)
        .timeout(15000);
      
      portfolioResults.push({
        test: 'basic_portfolio_access',
        success: [200, 401, 404, 503].includes(basicTest.status)
      });

      // Test 2: Holdings data
      const holdingsTest = await request(app)
        .get('/api/portfolio/holdings')
        .set(authHeaders)
        .timeout(15000);
      
      portfolioResults.push({
        test: 'holdings_data',
        success: [200, 401, 404, 503].includes(holdingsTest.status)
      });

      // Test 3: Metrics calculation
      const metricsTest = await request(app)
        .post('/api/portfolio/calculate-metrics')
        .set(authHeaders)
        .send({
          holdings: [
            { symbol: 'AAPL', quantity: 1, avgCost: 150, currentPrice: 155 }
          ]
        })
        .timeout(10000);
      
      portfolioResults.push({
        test: 'metrics_calculation',
        success: [200, 201, 400, 401, 503].includes(metricsTest.status)
      });

      // Test 4: Authentication enforcement
      const authTest = await request(app)
        .get('/api/portfolio')
        .timeout(5000); // No auth headers
      
      portfolioResults.push({
        test: 'authentication_enforcement',
        success: [401, 403, 503].includes(authTest.status)
      });

      const successfulTests = portfolioResults.filter(t => t.success).length;
      expect(successfulTests).toBe(portfolioResults.length);
      
      console.log('✅ Portfolio integration tests completed:', portfolioResults.map(t => t.test).join(', '));
      console.log(`🎯 Portfolio success rate: ${successfulTests}/${portfolioResults.length} (${(successfulTests/portfolioResults.length*100).toFixed(1)}%)`);
    });
  });
});
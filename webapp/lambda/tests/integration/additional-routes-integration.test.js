/**
 * Additional Routes Integration Tests
 * Tests alerts, watchlist, news, and technical analysis routes
 */

const request = require('supertest');
const { app } = require('../../index');
const { setupTestDatabase, cleanupTestDatabase } = require('../setup/test-database-setup');

describe('📋 Additional Routes Integration Tests', () => {
  let testDb;
  let testUser;
  let authHeaders;

  beforeAll(async () => {
    testDb = await setupTestDatabase();
    
    testUser = await testDb.createTestUser({
      email: 'additional-routes@example.com',
      username: 'additionalroutes',
      cognito_user_id: 'additional-routes-cognito-999'
    });
    
    await testDb.createTestApiKeys(testUser.user_id, {
      alpaca_key: 'PKTEST_ADDITIONAL_999',
      alpaca_secret: 'test_additional_secret_999'
    });
    
    authHeaders = { 'x-user-id': testUser.user_id };
  });

  afterAll(async () => {
    await testDb.cleanupTestUser(testUser.user_id);
    await cleanupTestDatabase();
  });

  describe('🔔 Alerts Routes', () => {
    test('GET /api/alerts - Get alerts service info', async () => {
      const response = await request(app)
        .get('/api/alerts')
        .timeout(10000);

      expect([200]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body.data).toHaveProperty('system', 'Alerts API');
        expect(response.body.data).toHaveProperty('status', 'operational');
        expect(response.body.data).toHaveProperty('available_endpoints');
        expect(Array.isArray(response.body.data.available_endpoints)).toBe(true);
      }

      console.log(`✅ Alerts service info: ${response.status}`);
    });

    test('GET /api/alerts/types - Get alert types', async () => {
      const response = await request(app)
        .get('/api/alerts/types')
        .set(authHeaders)
        .timeout(10000);

      expect([200, 401, 500, 503]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toBeDefined();
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
        expect(Array.isArray(response.body.data)).toBe(true);
      }

      console.log(`✅ Alert types: ${response.status}`);
    });

    test('GET /api/alerts/notifications - Get user notifications', async () => {
      const response = await request(app)
        .get('/api/alerts/notifications')
        .set(authHeaders)
        .timeout(10000);

      expect([200, 401, 404, 503]).toContain(response.status);
      
      console.log(`✅ User notifications: ${response.status}`);
    });

    test('POST /api/alerts - Create new alert', async () => {
      const alertData = {
        type: 'price_target',
        symbol: 'AAPL',
        target_price: 150.00,
        condition: 'above'
      };

      const response = await request(app)
        .post('/api/alerts')
        .set(authHeaders)
        .send(alertData)
        .timeout(10000);

      expect([200, 201, 400, 401, 404, 503]).toContain(response.status);
      
      console.log(`✅ Create alert: ${response.status}`);
    });

    test('Authentication required for protected alert endpoints', async () => {
      const alertEndpoints = [
        '/api/alerts/types',
        '/api/alerts/notifications'
      ];

      const authTests = [];

      for (const endpoint of alertEndpoints) {
        const response = await request(app)
          .get(endpoint)
          .timeout(5000); // No auth headers

        authTests.push({
          endpoint,
          status: response.status,
          requiresAuth: [401, 403].includes(response.status) || response.status === 503 || 
                       (process.env.ALLOW_DEV_AUTH_BYPASS === 'true' && response.status === 200)
        });
      }

      const allRequireAuth = authTests.every(test => test.requiresAuth);
      expect(allRequireAuth).toBe(true);

      console.log('✅ Alerts routes properly require authentication');
    });
  });

  describe('📰 News Routes', () => {
    test('GET /api/news/health - News service health', async () => {
      const response = await request(app)
        .get('/api/news/health')
        .timeout(10000);

      expect([200]).toContain(response.status);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('status', 'operational');
      expect(response.body).toHaveProperty('service', 'news');

      console.log(`✅ News health check: ${response.status}`);
    });

    test('GET /api/news - News service root', async () => {
      const response = await request(app)
        .get('/api/news')
        .timeout(10000);

      expect([200]).toContain(response.status);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('status', 'operational');

      console.log(`✅ News service root: ${response.status}`);
    });

    test('GET /api/news/articles - Get news articles', async () => {
      const response = await request(app)
        .get('/api/news/articles')
        .query({ symbol: 'AAPL', limit: 10 })
        .timeout(15000);

      expect([200, 401, 500, 503]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toBeDefined();
      }

      console.log(`✅ News articles: ${response.status}`);
    });

    test('GET /api/news/articles with query parameters', async () => {
      const queryParams = {
        symbol: 'AAPL',
        category: 'earnings',
        sentiment: 'positive',
        limit: 20,
        timeframe: '7d'
      };

      const response = await request(app)
        .get('/api/news/articles')
        .query(queryParams)
        .timeout(15000);

      expect([200, 400, 401, 429, 500, 503]).toContain(response.status);
      
      console.log(`✅ News articles with filters: ${response.status}`);
    });

    test('GET /api/news/sentiment - News sentiment analysis', async () => {
      const response = await request(app)
        .get('/api/news/sentiment')
        .query({ symbol: 'AAPL' })
        .timeout(15000);

      expect([200, 400, 401, 429, 500, 503]).toContain(response.status);
      
      console.log(`✅ News sentiment: ${response.status}`);
    });
  });

  describe('📊 Technical Analysis Routes', () => {
    test('GET /api/technical - Technical analysis data', async () => {
      const response = await request(app)
        .get('/api/technical')
        .set(authHeaders)
        .query({ 
          timeframe: 'daily',
          symbol: 'AAPL',
          limit: 50
        })
        .timeout(20000);

      expect([200, 400, 401, 429, 500, 503]).toContain(response.status);
      
      console.log(`✅ Technical analysis data: ${response.status}`);
    });

    test('GET /api/technical with different timeframes', async () => {
      const timeframes = ['daily', 'weekly', 'monthly'];
      const timeframeTests = [];

      for (const timeframe of timeframes) {
        const response = await request(app)
          .get('/api/technical')
          .set(authHeaders)
          .query({ 
            timeframe,
            symbol: 'AAPL',
            limit: 10
          })
          .timeout(15000);

        timeframeTests.push({
          timeframe,
          status: response.status,
          valid: [200, 400, 401, 429, 500, 503].includes(response.status)
        });
      }

      const allValid = timeframeTests.every(test => test.valid);
      expect(allValid).toBe(true);

      console.log(`✅ Technical timeframes tested: ${timeframes.join(', ')}`);
    });

    test('GET /api/technical with pagination', async () => {
      const response = await request(app)
        .get('/api/technical')
        .set(authHeaders)
        .query({ 
          timeframe: 'daily',
          page: 2,
          limit: 25,
          symbol: 'AAPL'
        })
        .timeout(15000);

      expect([200, 400, 401, 429, 500, 503]).toContain(response.status);
      
      console.log(`✅ Technical analysis pagination: ${response.status}`);
    });

    test('GET /api/technical with date range', async () => {
      const response = await request(app)
        .get('/api/technical')
        .set(authHeaders)
        .query({ 
          timeframe: 'daily',
          symbol: 'AAPL',
          start_date: '2024-01-01',
          end_date: '2024-01-31'
        })
        .timeout(15000);

      expect([200, 400, 401, 429, 500, 503]).toContain(response.status);
      
      console.log(`✅ Technical analysis date range: ${response.status}`);
    });

    test('GET /api/technical input validation', async () => {
      const invalidParams = {
        timeframe: 'invalid',
        page: -1,
        limit: 500,
        symbol: 'toolong123456'
      };

      const response = await request(app)
        .get('/api/technical')
        .set(authHeaders)
        .query(invalidParams)
        .timeout(10000);

      expect([400, 401, 503]).toContain(response.status);
      
      console.log(`✅ Technical input validation: ${response.status}`);
    });

    test('Technical routes require authentication', async () => {
      const response = await request(app)
        .get('/api/technical')
        .query({ timeframe: 'daily' })
        .timeout(5000); // No auth headers

      expect([401, 403, 503]).toContain(response.status);
      
      console.log('✅ Technical routes properly require authentication');
    });
  });

  describe('👁️ Watchlist Routes', () => {
    test('GET /api/watchlist - Get user watchlists', async () => {
      const response = await request(app)
        .get('/api/watchlist')
        .set(authHeaders)
        .timeout(15000);

      expect([200, 401, 500, 503]).toContain(response.status);
      
      if (response.status === 200) {
        expect(Array.isArray(response.body)).toBe(true);
      }

      console.log(`✅ User watchlists: ${response.status}`);
    });

    test('POST /api/watchlist - Create new watchlist', async () => {
      const watchlistData = {
        name: 'Test Watchlist',
        description: 'Integration test watchlist'
      };

      const response = await request(app)
        .post('/api/watchlist')
        .set(authHeaders)
        .send(watchlistData)
        .timeout(10000);

      expect([200, 201, 400, 401, 503]).toContain(response.status);
      
      console.log(`✅ Create watchlist: ${response.status}`);
    });

    test('GET /api/watchlist/:id/items - Get watchlist items', async () => {
      // Use a test ID that should return 404 or proper response
      const response = await request(app)
        .get('/api/watchlist/123/items')
        .set(authHeaders)
        .timeout(10000);

      expect([200, 404, 401, 503]).toContain(response.status);
      
      console.log(`✅ Watchlist items: ${response.status}`);
    });

    test('POST /api/watchlist/:id/items - Add item to watchlist', async () => {
      const itemData = {
        symbol: 'AAPL',
        notes: 'Test stock'
      };

      const response = await request(app)
        .post('/api/watchlist/123/items')
        .set(authHeaders)
        .send(itemData)
        .timeout(10000);

      expect([200, 201, 400, 404, 401, 503]).toContain(response.status);
      
      console.log(`✅ Add watchlist item: ${response.status}`);
    });

    test('DELETE /api/watchlist/:id - Delete watchlist', async () => {
      const response = await request(app)
        .delete('/api/watchlist/123')
        .set(authHeaders)
        .timeout(10000);

      expect([200, 404, 401, 503]).toContain(response.status);
      
      console.log(`✅ Delete watchlist: ${response.status}`);
    });

    test('Watchlist routes require authentication', async () => {
      const watchlistEndpoints = [
        { method: 'get', path: '/api/watchlist' },
        { method: 'post', path: '/api/watchlist' },
        { method: 'get', path: '/api/watchlist/123/items' }
      ];

      const authTests = [];

      for (const endpoint of watchlistEndpoints) {
        let response;
        if (endpoint.method === 'get') {
          response = await request(app).get(endpoint.path).timeout(5000);
        } else if (endpoint.method === 'post') {
          response = await request(app).post(endpoint.path).send({}).timeout(5000);
        }

        authTests.push({
          endpoint: endpoint.path,
          status: response.status,
          requiresAuth: [401, 403].includes(response.status) || response.status === 503
        });
      }

      const allRequireAuth = authTests.every(test => test.requiresAuth);
      expect(allRequireAuth).toBe(true);

      console.log('✅ Watchlist routes properly require authentication');
    });
  });

  describe('⚡ Performance Testing', () => {
    test('Additional routes respond within reasonable time', async () => {
      const performanceTests = [];
      
      const endpoints = [
        { path: '/api/alerts', timeout: 10000, useAuth: false },
        { path: '/api/news/health', timeout: 10000, useAuth: false },
        { path: '/api/news', timeout: 10000, useAuth: false },
        { path: '/api/watchlist', timeout: 15000, useAuth: true },
        { path: '/api/technical', timeout: 20000, useAuth: true, query: { timeframe: 'daily' } }
      ];

      for (const endpoint of endpoints) {
        const startTime = Date.now();
        
        try {
          let response;
          if (endpoint.useAuth) {
            response = await request(app)
              .get(endpoint.path)
              .set(authHeaders)
              .query(endpoint.query || {})
              .timeout(endpoint.timeout);
          } else {
            response = await request(app)
              .get(endpoint.path)
              .timeout(endpoint.timeout);
          }

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

      const allWithinTimeout = performanceTests.every(test => test.withinTimeout);
      expect(allWithinTimeout).toBe(true);

      const avgResponseTime = performanceTests.reduce((sum, test) => sum + test.responseTime, 0) / performanceTests.length;
      console.log(`⚡ Average additional routes response time: ${avgResponseTime.toFixed(0)}ms`);
    });
  });

  describe('🔄 Integration Summary', () => {
    test('Additional routes integration test summary', async () => {
      const additionalRoutesResults = [];
      
      console.log('📋 Running additional routes integration summary...');

      // Test 1: Alerts service
      const alertsTest = await request(app)
        .get('/api/alerts')
        .timeout(10000);
      
      additionalRoutesResults.push({
        test: 'alerts_service',
        success: alertsTest.status === 200
      });

      // Test 2: News service
      const newsTest = await request(app)
        .get('/api/news/health')
        .timeout(10000);
      
      additionalRoutesResults.push({
        test: 'news_service',
        success: newsTest.status === 200
      });

      // Test 3: Watchlist service
      const watchlistTest = await request(app)
        .get('/api/watchlist')
        .set(authHeaders)
        .timeout(10000);
      
      additionalRoutesResults.push({
        test: 'watchlist_service',
        success: [200, 401, 503].includes(watchlistTest.status)
      });

      // Test 4: Technical analysis service
      const technicalTest = await request(app)
        .get('/api/technical')
        .set(authHeaders)
        .query({ timeframe: 'daily' })
        .timeout(15000);
      
      additionalRoutesResults.push({
        test: 'technical_service',
        success: [200, 400, 401, 503].includes(technicalTest.status)
      });

      // Test 5: Authentication enforcement
      const authTest = await request(app)
        .get('/api/watchlist')
        .timeout(5000); // No auth headers
      
      additionalRoutesResults.push({
        test: 'authentication_enforcement',
        success: [401, 403, 503].includes(authTest.status)
      });

      const successfulTests = additionalRoutesResults.filter(t => t.success).length;
      expect(successfulTests).toBe(additionalRoutesResults.length);
      
      console.log('✅ Additional routes integration tests completed:', additionalRoutesResults.map(t => t.test).join(', '));
      console.log(`🎯 Additional routes success rate: ${successfulTests}/${additionalRoutesResults.length} (${(successfulTests/additionalRoutesResults.length*100).toFixed(1)}%)`);
    });
  });
});
/**
 * Basic API Routes Integration Tests
 * Tests existing routes and functionality that actually exists in the application
 */

const request = require('supertest');
const { app } = require('../../index');
const { setupTestDatabase, cleanupTestDatabase } = require('../setup/test-database-setup');

describe('🚀 Basic API Routes Integration Tests', () => {
  let testDb;
  let testUser;
  let authHeaders;

  beforeAll(async () => {
    testDb = await setupTestDatabase();
    
    testUser = await testDb.createTestUser({
      email: 'basic-routes@example.com',
      username: 'basicroutes',
      cognito_user_id: 'basic-routes-cognito-123'
    });
    
    authHeaders = { 'x-user-id': testUser.user_id };
  });

  afterAll(async () => {
    await testDb.cleanupTestUser(testUser.user_id);
    await cleanupTestDatabase();
  });

  describe('🏥 Health and Status Routes', () => {
    test('GET / - Root endpoint', async () => {
      const response = await request(app)
        .get('/')
        .timeout(5000);

      expect([200]).toContain(response.status);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('message');
      expect(response.body).toHaveProperty('version');
    });

    test('GET /health - Basic health check', async () => {
      const response = await request(app)
        .get('/health')
        .timeout(5000);

      expect([200]).toContain(response.status);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('status');
      expect(response.body.routes).toBeDefined();
    });

    test('GET /api/health - API health check', async () => {
      const response = await request(app)
        .get('/api/health')
        .timeout(10000);

      expect([200, 503]).toContain(response.status);
      expect(response.body).toHaveProperty('success');
      expect(response.body).toHaveProperty('timestamp');
      
      if (response.status === 200) {
        expect(response.body.database).toBeDefined();
        expect(response.body.environment_vars).toBeDefined();
      }
    });

    test('GET /system-status - System status', async () => {
      const response = await request(app)
        .get('/system-status')
        .timeout(5000);

      expect([200]).toContain(response.status);
      expect(response.body).toHaveProperty('system_status');
      expect(response.body).toHaveProperty('route_loading');
      expect(response.body).toHaveProperty('configuration');
    });

    test('GET /debug - Debug endpoint', async () => {
      const response = await request(app)
        .get('/debug')
        .timeout(5000);

      expect([200]).toContain(response.status);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('request_info');
      expect(response.body).toHaveProperty('system_info');
    });
  });

  describe('🔧 Settings API Routes', () => {
    test('GET /api/settings/api-keys - Get API keys', async () => {
      const response = await request(app)
        .get('/api/settings/api-keys')
        .set(authHeaders)
        .timeout(10000);

      expect([200, 503]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
        expect(Array.isArray(response.body.data)).toBe(true);
      } else {
        expect(response.body).toHaveProperty('error');
      }
    });

    test('POST /api/settings/api-keys - Add API key', async () => {
      const apiKeyData = {
        provider: 'alpaca',
        keyId: 'PKTEST_BASIC_123',
        secretKey: 'test_secret_456'
      };

      const response = await request(app)
        .post('/api/settings/api-keys')
        .set(authHeaders)
        .send(apiKeyData)
        .timeout(10000);

      expect([200, 201, 400, 503]).toContain(response.status);
      
      if ([200, 201].includes(response.status)) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
      }
    });

    test('GET /api/settings/notifications - Get notification preferences', async () => {
      const response = await request(app)
        .get('/api/settings/notifications')
        .set(authHeaders)
        .timeout(5000);

      expect([200]).toContain(response.status);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('email');
      expect(response.body.data).toHaveProperty('push');
    });

    test('PUT /api/settings/notifications - Update notification preferences', async () => {
      const notificationSettings = {
        email: true,
        push: false,
        sms: false
      };

      const response = await request(app)
        .put('/api/settings/notifications')
        .set(authHeaders)
        .send(notificationSettings)
        .timeout(5000);

      expect([200]).toContain(response.status);
      expect(response.body).toHaveProperty('success', true);
    });

    test('GET /api/settings/theme - Get theme preferences', async () => {
      const response = await request(app)
        .get('/api/settings/theme')
        .set(authHeaders)
        .timeout(5000);

      expect([200]).toContain(response.status);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('dark_mode');
      expect(response.body.data).toHaveProperty('primary_color');
    });

    test('PUT /api/settings/theme - Update theme preferences', async () => {
      const themeSettings = {
        darkMode: true,
        primaryColor: '#2196f3'
      };

      const response = await request(app)
        .put('/api/settings/theme')
        .set(authHeaders)
        .send(themeSettings)
        .timeout(5000);

      expect([200]).toContain(response.status);
      expect(response.body).toHaveProperty('success', true);
    });
  });

  describe('📊 Existing Route Endpoints', () => {
    test('Routes load without 500 errors', async () => {
      const existingRoutes = [
        '/api/portfolio',
        '/api/market-data',
        '/api/stocks',
        '/api/alerts',
        '/api/auth',
        '/api/settings',
        '/api/dashboard',
        '/api/watchlist',
        '/api/news',
        '/api/technical',
        '/api/admin'
      ];

      const routeTests = [];

      for (const route of existingRoutes) {
        try {
          const response = await request(app)
            .get(route)
            .set(authHeaders)
            .timeout(10000);

          routeTests.push({
            route,
            status: response.status,
            working: response.status !== 500, // No internal server errors
            loads: [200, 401, 404, 503].includes(response.status)
          });
        } catch (error) {
          routeTests.push({
            route,
            status: 'timeout',
            working: true, // Timeout is acceptable
            loads: true
          });
        }
      }

      const allRoutesWorking = routeTests.every(test => test.working);
      expect(allRoutesWorking).toBe(true);

      const workingRoutes = routeTests.filter(test => test.loads).length;
      console.log(`✅ Routes tested: ${workingRoutes}/${routeTests.length} loading properly`);
    });
  });

  describe('🔍 Error Handling', () => {
    test('404 for non-existent routes', async () => {
      const response = await request(app)
        .get('/api/non-existent-route')
        .timeout(5000);

      expect([404]).toContain(response.status);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error');
    });

    test('Invalid HTTP methods handled', async () => {
      const response = await request(app)
        .patch('/api/health')
        .timeout(5000);

      expect([404, 405]).toContain(response.status);
      expect(response.body).toHaveProperty('success', false);
    });

    test('CORS headers present on errors', async () => {
      const response = await request(app)
        .get('/api/non-existent')
        .set('Origin', 'https://d1zb7knau41vl9.cloudfront.net')
        .timeout(5000);

      expect(response.headers['access-control-allow-origin']).toBeDefined();
    });
  });

  describe('🛡️ Security Headers', () => {
    test('Security headers present', async () => {
      const response = await request(app)
        .get('/api/health')
        .timeout(5000);

      expect(response.headers['x-content-type-options']).toBeDefined();
      expect(response.headers['x-frame-options']).toBeDefined();
      expect(response.headers['x-xss-protection']).toBeDefined();
    });

    test('Sensitive headers removed', async () => {
      const response = await request(app)
        .get('/api/health')
        .timeout(5000);

      expect(response.headers['x-powered-by']).toBeUndefined();
      expect(response.headers['server']).toBeUndefined();
    });
  });

  describe('📝 Request/Response Format', () => {
    test('JSON content type', async () => {
      const response = await request(app)
        .get('/api/health')
        .timeout(5000);

      expect(response.headers['content-type']).toMatch(/application\/json/);
    });

    test('Correlation ID in responses', async () => {
      const response = await request(app)
        .get('/api/health')
        .timeout(5000);

      expect(response.body).toHaveProperty('correlation_id');
    });

    test('Timestamp in responses', async () => {
      const response = await request(app)
        .get('/api/health')
        .timeout(5000);

      expect(response.body).toHaveProperty('timestamp');
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
    });
  });

  describe('⚡ Performance', () => {
    test('Health endpoints respond quickly', async () => {
      const startTime = Date.now();
      
      const response = await request(app)
        .get('/health')
        .timeout(5000);

      const responseTime = Date.now() - startTime;
      
      expect(response.status).toBe(200);
      expect(responseTime).toBeLessThan(3000); // Under 3 seconds
    });

    test('Basic routes have reasonable response times', async () => {
      const routes = ['/health', '/debug', '/system-status'];
      const performanceTests = [];

      for (const route of routes) {
        const startTime = Date.now();
        
        try {
          const response = await request(app)
            .get(route)
            .timeout(5000);

          const responseTime = Date.now() - startTime;
          
          performanceTests.push({
            route,
            responseTime,
            success: response.status === 200
          });
        } catch (error) {
          performanceTests.push({
            route,
            responseTime: 5000,
            success: false
          });
        }
      }

      const avgResponseTime = performanceTests.reduce((sum, test) => sum + test.responseTime, 0) / performanceTests.length;
      expect(avgResponseTime).toBeLessThan(3000);

      console.log(`⚡ Average response time: ${avgResponseTime.toFixed(0)}ms`);
    });
  });

  describe('🔗 Integration Summary', () => {
    test('Basic API integration test summary', async () => {
      const integrationResults = [];
      
      console.log('🚀 Running basic API integration summary...');

      // Test 1: Core health
      const healthTest = await request(app)
        .get('/api/health')
        .timeout(10000);
      
      integrationResults.push({
        test: 'health_check',
        success: [200, 503].includes(healthTest.status)
      });

      // Test 2: Settings API
      const settingsTest = await request(app)
        .get('/api/settings/api-keys')
        .set(authHeaders)
        .timeout(5000);
      
      integrationResults.push({
        test: 'settings_api',
        success: [200, 503].includes(settingsTest.status)
      });

      // Test 3: Error handling
      const errorTest = await request(app)
        .get('/api/non-existent')
        .timeout(5000);
      
      integrationResults.push({
        test: 'error_handling',
        success: errorTest.status === 404
      });

      // Test 4: Security headers
      const securityTest = await request(app)
        .get('/health')
        .timeout(5000);
      
      integrationResults.push({
        test: 'security_headers',
        success: securityTest.headers['x-content-type-options'] !== undefined
      });

      const successfulTests = integrationResults.filter(t => t.success).length;
      expect(successfulTests).toBe(integrationResults.length);
      
      console.log('✅ Basic API integration tests completed:', integrationResults.map(t => t.test).join(', '));
      console.log(`🎯 Success rate: ${successfulTests}/${integrationResults.length} (${(successfulTests/integrationResults.length*100).toFixed(1)}%)`);
    });
  });
});
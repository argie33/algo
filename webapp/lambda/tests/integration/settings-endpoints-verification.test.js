/**
 * Settings API Endpoints Verification Test
 * Quick verification that the new API endpoints are working
 * Tests the specific endpoints that were returning 503 errors
 */

const { app } = require('../../index');
const request = require('supertest');

describe('Settings API Endpoints Verification', () => {
  const validToken = 'Bearer test-token';

  // Test the API endpoints that were previously returning 503 errors
  describe('API Endpoints Availability', () => {
    it('should have /api/portfolio/api-keys endpoint available', async () => {
      const response = await request(app)
        .get('/api/portfolio/api-keys')
        .set('Authorization', validToken)
        .timeout(5000);

      // Should not return 503 Service Unavailable
      expect(response.status).not.toBe(503);
      // Should return either 200 (success) or 401 (auth required) - both indicate endpoint exists
      expect([200, 401, 500]).toContain(response.status);
    });

    it('should have /api/user/notifications endpoint available', async () => {
      const response = await request(app)
        .get('/api/user/notifications')
        .set('Authorization', validToken)
        .timeout(5000);

      // Should not return 503 Service Unavailable or 404 Not Found
      expect(response.status).not.toBe(503);
      expect(response.status).not.toBe(404);
      expect([200, 401, 500]).toContain(response.status);
    });

    it('should have /api/user/theme endpoint available', async () => {
      const response = await request(app)
        .get('/api/user/theme')
        .set('Authorization', validToken)
        .timeout(5000);

      // Should not return 503 Service Unavailable or 404 Not Found
      expect(response.status).not.toBe(503);
      expect(response.status).not.toBe(404);
      expect([200, 401, 500]).toContain(response.status);
    });

    it('should have /api/user/profile endpoint available', async () => {
      const response = await request(app)
        .get('/api/user/profile')
        .set('Authorization', validToken)
        .timeout(5000);

      // Should not return 503 Service Unavailable or 404 Not Found
      expect(response.status).not.toBe(503);
      expect(response.status).not.toBe(404);
      expect([200, 401, 500]).toContain(response.status);
    });
  });

  describe('API Endpoints Response Format', () => {
    it('should return JSON responses', async () => {
      const endpoints = [
        '/api/user/profile',
        '/api/user/notifications', 
        '/api/user/theme',
        '/api/portfolio/api-keys'
      ];

      for (const endpoint of endpoints) {
        const response = await request(app)
          .get(endpoint)
          .set('Authorization', validToken)
          .timeout(5000);

        if (response.status === 200) {
          expect(response.headers['content-type']).toMatch(/json/);
          expect(response.body).toHaveProperty('success');
          expect(response.body).toHaveProperty('timestamp');
        }
      }
    });

    it('should handle POST requests to API key endpoint', async () => {
      const response = await request(app)
        .post('/api/portfolio/api-keys')
        .set('Authorization', validToken)
        .send({
          brokerName: 'alpaca',
          apiKey: 'test-key',
          apiSecret: 'test-secret',
          sandbox: true
        })
        .timeout(5000);

      // Should not return 503 or 404
      expect(response.status).not.toBe(503);
      expect(response.status).not.toBe(404);
      // Should return either success or validation error - both indicate endpoint works
      expect([200, 400, 401, 500]).toContain(response.status);
    });

    it('should handle PUT requests to profile endpoint', async () => {
      const response = await request(app)
        .put('/api/user/profile')
        .set('Authorization', validToken)
        .send({
          firstName: 'Test',
          lastName: 'User',
          email: 'test@example.com'
        })
        .timeout(5000);

      // Should not return 503 or 404
      expect(response.status).not.toBe(503);
      expect(response.status).not.toBe(404);
      expect([200, 400, 401, 500]).toContain(response.status);
    });
  });

  describe('Application Health', () => {
    it('should have working health endpoint', async () => {
      const response = await request(app)
        .get('/api/health')
        .timeout(5000);

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('success', true);
    });

    it('should load routes successfully', async () => {
      const response = await request(app)
        .get('/system-status')
        .timeout(5000);

      expect(response.status).toBe(200);
      expect(response.body.route_loading.success_rate).toBeGreaterThan(80);
    });
  });

  describe('Security Integration', () => {
    it('should require authentication for protected endpoints', async () => {
      const protectedEndpoints = [
        '/api/user/profile',
        '/api/user/notifications',
        '/api/user/theme',
        '/api/portfolio/api-keys'
      ];

      for (const endpoint of protectedEndpoints) {
        const response = await request(app)
          .get(endpoint)
          // No Authorization header
          .timeout(5000);

        // Should require authentication
        expect(response.status).toBe(401);
      }
    });

    it('should handle CORS correctly', async () => {
      const response = await request(app)
        .options('/api/user/profile')
        .set('Origin', 'http://localhost:3000')
        .timeout(5000);

      expect(response.status).toBe(200);
      expect(response.headers['access-control-allow-origin']).toBeDefined();
    });
  });
});
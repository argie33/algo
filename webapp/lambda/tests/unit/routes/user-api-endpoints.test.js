/**
 * Unit Tests for User API Endpoints - TDD Implementation
 * Tests /api/user/* and /api/portfolio/api-keys endpoints
 * Following TDD principles - write tests first, then implement
 */

const request = require('supertest');
const express = require('express');
const { app } = require('../../../index');

describe('User API Endpoints - TDD Tests', () => {
  let testApp;
  
  beforeEach(() => {
    // Use the actual app from index.js
    testApp = app;
  });

  describe('User Profile Endpoints', () => {
    describe('GET /api/user/profile', () => {
      it('should return user profile data with authentication', async () => {
        const response = await request(testApp)
          .get('/api/user/profile')
          .set('Authorization', 'Bearer test-token')
          .expect(200);

        expect(response.body).toMatchObject({
          success: true,
          data: expect.objectContaining({
            firstName: expect.any(String),
            lastName: expect.any(String),
            email: expect.any(String),
            timezone: expect.any(String),
            currency: expect.any(String)
          })
        });
      });

      it('should return 401 for unauthenticated requests', async () => {
        const response = await request(testApp)
          .get('/api/user/profile')
          .expect(401);

        expect(response.body).toMatchObject({
          success: false,
          error: expect.stringContaining('Authentication')
        });
      });
    });

    describe('PUT /api/user/profile', () => {
      it('should update user profile successfully', async () => {
        const profileData = {
          firstName: 'John',
          lastName: 'Doe',
          email: 'john.doe@example.com',
          phone: '+1234567890',
          timezone: 'America/New_York',
          currency: 'USD'
        };

        const response = await request(testApp)
          .put('/api/user/profile')
          .set('Authorization', 'Bearer test-token')
          .send(profileData)
          .expect(200);

        expect(response.body).toMatchObject({
          success: true,
          data: expect.objectContaining(profileData),
          message: expect.stringContaining('updated')
        });
      });

      it('should validate required fields', async () => {
        const response = await request(testApp)
          .put('/api/user/profile')
          .set('Authorization', 'Bearer test-token')
          .send({}) // Empty data
          .expect(400);

        expect(response.body).toMatchObject({
          success: false,
          error: expect.stringContaining('required')
        });
      });

      it('should validate email format', async () => {
        const response = await request(testApp)
          .put('/api/user/profile')
          .set('Authorization', 'Bearer test-token')
          .send({
            firstName: 'John',
            lastName: 'Doe',
            email: 'invalid-email'
          })
          .expect(400);

        expect(response.body).toMatchObject({
          success: false,
          error: expect.stringContaining('email')
        });
      });
    });
  });

  describe('User Notification Endpoints', () => {
    describe('GET /api/user/notifications', () => {
      it('should return user notification preferences', async () => {
        const response = await request(testApp)
          .get('/api/user/notifications')
          .set('Authorization', 'Bearer test-token')
          .expect(200);

        expect(response.body).toMatchObject({
          success: true,
          data: expect.objectContaining({
            email: expect.any(Boolean),
            push: expect.any(Boolean),
            priceAlerts: expect.any(Boolean),
            portfolioUpdates: expect.any(Boolean),
            marketNews: expect.any(Boolean),
            weeklyReports: expect.any(Boolean)
          })
        });
      });

      it('should return default preferences when none are set', async () => {
        const response = await request(testApp)
          .get('/api/user/notifications')
          .set('Authorization', 'Bearer test-token')
          .expect(200);

        expect(response.body.data).toMatchObject({
          email: true,
          push: true,
          priceAlerts: true,
          portfolioUpdates: true,
          marketNews: false,
          weeklyReports: true
        });
      });
    });

    describe('PUT /api/user/notifications', () => {
      it('should update notification preferences successfully', async () => {
        const preferences = {
          email: true,
          push: false,
          priceAlerts: true,
          portfolioUpdates: false,
          marketNews: true,
          weeklyReports: false
        };

        const response = await request(testApp)
          .put('/api/user/notifications')
          .set('Authorization', 'Bearer test-token')
          .send(preferences)
          .expect(200);

        expect(response.body).toMatchObject({
          success: true,
          data: expect.objectContaining(preferences),
          message: expect.stringContaining('updated')
        });
      });

      it('should handle partial updates', async () => {
        const response = await request(testApp)
          .put('/api/user/notifications')
          .set('Authorization', 'Bearer test-token')
          .send({ email: false })
          .expect(200);

        expect(response.body.data.email).toBe(false);
      });
    });
  });

  describe('User Theme Endpoints', () => {
    describe('GET /api/user/theme', () => {
      it('should return user theme preferences', async () => {
        const response = await request(testApp)
          .get('/api/user/theme')
          .set('Authorization', 'Bearer test-token')
          .expect(200);

        expect(response.body).toMatchObject({
          success: true,
          data: expect.objectContaining({
            darkMode: expect.any(Boolean),
            primaryColor: expect.any(String),
            chartStyle: expect.any(String),
            layout: expect.any(String)
          })
        });
      });
    });

    describe('PUT /api/user/theme', () => {
      it('should update theme preferences successfully', async () => {
        const themeData = {
          darkMode: true,
          primaryColor: '#1976d2',
          chartStyle: 'candlestick',
          layout: 'compact'
        };

        const response = await request(testApp)
          .put('/api/user/theme')
          .set('Authorization', 'Bearer test-token')
          .send(themeData)
          .expect(200);

        expect(response.body).toMatchObject({
          success: true,
          data: expect.objectContaining(themeData),
          message: expect.stringContaining('updated')
        });
      });

      it('should validate color format', async () => {
        const response = await request(testApp)
          .put('/api/user/theme')
          .set('Authorization', 'Bearer test-token')
          .send({ primaryColor: 'invalid-color' })
          .expect(400);

        expect(response.body).toMatchObject({
          success: false,
          error: expect.stringContaining('color')
        });
      });
    });
  });

  describe('Portfolio API Keys Endpoints', () => {
    describe('GET /api/portfolio/api-keys', () => {
      it('should return user API keys list', async () => {
        const response = await request(testApp)
          .get('/api/portfolio/api-keys')
          .set('Authorization', 'Bearer test-token')
          .expect(200);

        expect(response.body).toMatchObject({
          success: true,
          apiKeys: expect.any(Array)
        });
      });

      it('should mask sensitive API key data', async () => {
        const response = await request(testApp)
          .get('/api/portfolio/api-keys')
          .set('Authorization', 'Bearer test-token')
          .expect(200);

        if (response.body.apiKeys.length > 0) {
          const apiKey = response.body.apiKeys[0];
          expect(apiKey.apiKey).toMatch(/\*{3,}/); // Should contain masked characters
          expect(apiKey.apiSecret).toBeUndefined(); // Should not expose secret
        }
      });
    });

    describe('POST /api/portfolio/api-keys', () => {
      it('should add new API key successfully', async () => {
        const apiKeyData = {
          brokerName: 'alpaca',
          apiKey: 'test-api-key-123',
          apiSecret: 'test-secret-456',
          sandbox: true
        };

        const response = await request(testApp)
          .post('/api/portfolio/api-keys')
          .set('Authorization', 'Bearer test-token')
          .send(apiKeyData)
          .expect(200);

        expect(response.body).toMatchObject({
          success: true,
          message: expect.stringContaining('added'),
          data: expect.objectContaining({
            brokerName: apiKeyData.brokerName,
            sandbox: apiKeyData.sandbox
          })
        });

        // Should not return the actual secret
        expect(response.body.data.apiSecret).toBeUndefined();
      });

      it('should validate required fields', async () => {
        const response = await request(testApp)
          .post('/api/portfolio/api-keys')
          .set('Authorization', 'Bearer test-token')
          .send({}) // Missing required fields
          .expect(400);

        expect(response.body).toMatchObject({
          success: false,
          error: expect.stringContaining('required')
        });
      });

      it('should validate broker name', async () => {
        const response = await request(testApp)
          .post('/api/portfolio/api-keys')
          .set('Authorization', 'Bearer test-token')
          .send({
            brokerName: 'unsupported-broker',
            apiKey: 'test-key',
            apiSecret: 'test-secret'
          })
          .expect(400);

        expect(response.body).toMatchObject({
          success: false,
          error: expect.stringContaining('broker')
        });
      });

      it('should encrypt API secrets before storage', async () => {
        const apiKeyData = {
          brokerName: 'alpaca',
          apiKey: 'test-api-key-123',
          apiSecret: 'test-secret-456',
          sandbox: true
        };

        const response = await request(testApp)
          .post('/api/portfolio/api-keys')
          .set('Authorization', 'Bearer test-token')
          .send(apiKeyData)
          .expect(200);

        // Verify that the secret is not returned in plain text
        expect(response.body.data.apiSecret).toBeUndefined();
        expect(response.body.data.encryptedSecret).toBeUndefined();
      });
    });

    describe('DELETE /api/portfolio/api-keys/:brokerName', () => {
      it('should delete API key successfully', async () => {
        const response = await request(testApp)
          .delete('/api/portfolio/api-keys/alpaca')
          .set('Authorization', 'Bearer test-token')
          .expect(200);

        expect(response.body).toMatchObject({
          success: true,
          message: expect.stringContaining('deleted')
        });
      });

      it('should return 404 for non-existent API key', async () => {
        const response = await request(testApp)
          .delete('/api/portfolio/api-keys/non-existent')
          .set('Authorization', 'Bearer test-token')
          .expect(404);

        expect(response.body).toMatchObject({
          success: false,
          error: expect.stringContaining('not found')
        });
      });
    });

    describe('POST /api/portfolio/test-connection/:brokerName', () => {
      it('should test API connection successfully', async () => {
        const response = await request(testApp)
          .post('/api/portfolio/test-connection/alpaca')
          .set('Authorization', 'Bearer test-token')
          .expect(200);

        expect(response.body).toMatchObject({
          success: true,
          message: expect.stringContaining('connection'),
          data: expect.objectContaining({
            connected: expect.any(Boolean),
            accountInfo: expect.any(Object)
          })
        });
      });

      it('should handle connection failures gracefully', async () => {
        const response = await request(testApp)
          .post('/api/portfolio/test-connection/invalid-broker')
          .set('Authorization', 'Bearer test-token')
          .expect(400);

        expect(response.body).toMatchObject({
          success: false,
          error: expect.stringContaining('connection')
        });
      });
    });
  });

  describe('Authentication and Security', () => {
    it('should require authentication for all endpoints', async () => {
      const endpoints = [
        'GET /api/user/profile',
        'PUT /api/user/profile',
        'GET /api/user/notifications',
        'PUT /api/user/notifications',
        'GET /api/user/theme',
        'PUT /api/user/theme',
        'GET /api/portfolio/api-keys',
        'POST /api/portfolio/api-keys'
      ];

      for (const endpoint of endpoints) {
        const [method, path] = endpoint.split(' ');
        const response = await request(testApp)[method.toLowerCase()](path)
          .expect(401);

        expect(response.body).toMatchObject({
          success: false,
          error: expect.stringContaining('Authentication')
        });
      }
    });

    it('should validate JWT token format', async () => {
      const response = await request(app)
        .get('/api/user/profile')
        .set('Authorization', 'Bearer invalid-token')
        .expect(401);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.stringContaining('token')
      });
    });

    it('should rate limit API requests', async () => {
      // Make multiple rapid requests
      const promises = Array.from({ length: 20 }, () =>
        request(app)
          .get('/api/user/profile')
          .set('Authorization', 'Bearer test-token')
      );

      const responses = await Promise.all(promises);
      
      // At least one should be rate limited
      const rateLimited = responses.some(res => res.status === 429);
      expect(rateLimited).toBe(true);
    });
  });

  describe('Error Handling', () => {
    it('should handle database connection errors gracefully', async () => {
      // Mock database error
      const databaseConnectionManager = require('../../../utils/databaseConnectionManager');
      const originalQuery = databaseConnectionManager.query;
      databaseConnectionManager.query = jest.fn()
        .mockRejectedValue(new Error('Database connection failed'));

      const response = await request(app)
        .get('/api/user/profile')
        .set('Authorization', 'Bearer test-token')
        .expect(503);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.stringContaining('unavailable')
      });

      // Restore original function
      databaseConnectionManager.query = originalQuery;
    });

    it('should sanitize error messages in production', async () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = 'production';

      const response = await request(app)
        .get('/api/user/profile')
        .set('Authorization', 'Bearer test-token');

      // Should not expose internal error details in production
      if (!response.body.success) {
        expect(response.body.error).not.toMatch(/stack|trace|internal/i);
      }

      process.env.NODE_ENV = originalEnv;
    });
  });

  describe('Data Validation and Sanitization', () => {
    it('should sanitize input data to prevent XSS', async () => {
      const maliciousData = {
        firstName: '<script>alert("xss")</script>',
        lastName: 'Normal Name',
        email: 'test@example.com'
      };

      const response = await request(app)
        .put('/api/user/profile')
        .set('Authorization', 'Bearer test-token')
        .send(maliciousData)
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.stringContaining('Invalid')
      });
    });

    it('should validate SQL injection attempts', async () => {
      const sqlInjectionData = {
        firstName: "'; DROP TABLE users; --",
        lastName: 'Normal Name',
        email: 'test@example.com'
      };

      const response = await request(app)
        .put('/api/user/profile')
        .set('Authorization', 'Bearer test-token')
        .send(sqlInjectionData)
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.stringContaining('Invalid')
      });
    });
  });

  describe('Performance', () => {
    it('should respond within acceptable time limits', async () => {
      const startTime = Date.now();
      
      await request(app)
        .get('/api/user/profile')
        .set('Authorization', 'Bearer test-token');
      
      const responseTime = Date.now() - startTime;
      expect(responseTime).toBeLessThan(2000); // Should respond within 2 seconds
    });

    it('should handle concurrent requests efficiently', async () => {
      const concurrentRequests = 10;
      const promises = Array.from({ length: concurrentRequests }, () =>
        request(app)
          .get('/api/user/profile')
          .set('Authorization', 'Bearer test-token')
      );

      const startTime = Date.now();
      const responses = await Promise.all(promises);
      const totalTime = Date.now() - startTime;

      // All requests should complete successfully
      responses.forEach(response => {
        expect(response.status).toBeLessThan(500);
      });

      // Should handle concurrent requests efficiently
      expect(totalTime).toBeLessThan(5000); // Within 5 seconds
    });
  });
});
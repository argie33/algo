/**
 * Integration Tests for Route Loading
 * Tests that all routes load properly and don't return 503 errors
 */

const request = require('supertest');
const express = require('express');

describe('Route Loading Integration Tests', () => {
  let app;

  beforeAll(() => {
    // Create test express app similar to main index.js
    app = express();
    app.use(express.json());

    // Mock CORS middleware
    app.use((req, res, next) => {
      res.header('Access-Control-Allow-Origin', '*');
      res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
      res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
      if (req.method === 'OPTIONS') return res.status(200).end();
      next();
    });
  });

  describe('Core Routes Loading', () => {
    test('should load settings route without 503 error', async () => {
      try {
        const settingsRouter = require('../../routes/settings');
        app.use('/api/settings', settingsRouter);
        
        // Test that the route loads and responds (even if authentication fails)
        const response = await request(app)
          .get('/api/settings/api-keys')
          .expect((res) => {
            // Should not be 503 Service Unavailable
            expect(res.status).not.toBe(503);
            // Should be either 401 (auth required) or 200 (success)
           expect([200, 401]).toContain(res.status);
          });

        // If 503, the route failed to load
        if (response.status === 503) {
          expect(response.body.message).not.toContain('Route failed to load');
        }
      } catch (error) {
        fail(`Settings route failed to load: ${error.message}`);
      }
    });

    test('should load portfolio route without 503 error', async () => {
      try {
        const portfolioRouter = require('../../routes/portfolio');
        app.use('/api/portfolio', portfolioRouter);
        
        const response = await request(app)
          .get('/api/portfolio/api-keys')
          .expect((res) => {
            expect(res.status).not.toBe(503);
            expect([200, 401, 404]).toContain(res.status);
          });

        if (response.status === 503) {
          expect(response.body.message).not.toContain('Route failed to load');
        }
      } catch (error) {
        fail(`Portfolio route failed to load: ${error.message}`);
      }
    });

    test('should load user route without 503 error', async () => {
      try {
        const userRouter = require('../../routes/user');
        app.use('/api/user', userRouter);
        
        const response = await request(app)
          .get('/api/user/notifications')
          .expect((res) => {
            expect(res.status).not.toBe(503);
            expect([200, 401, 404]).toContain(res.status);
          });

        if (response.status === 503) {
          expect(response.body.message).not.toContain('Route failed to load');
        }
      } catch (error) {
        fail(`User route failed to load: ${error.message}`);
      }
    });

    test('should load cloudformation route without 503 error', async () => {
      try {
        const cloudformationRouter = require('../../routes/cloudformation');
        app.use('/api/config/cloudformation', cloudformationRouter);
        
        const response = await request(app)
          .get('/api/config/cloudformation')
          .expect((res) => {
            expect(res.status).not.toBe(503);
            // CloudFormation route might return 400 if no stackName provided
            expect([200, 400, 401]).toContain(res.status);
          });

        if (response.status === 503) {
          expect(response.body.message).not.toContain('Route failed to load');
        }
      } catch (error) {
        fail(`CloudFormation route failed to load: ${error.message}`);
      }
    });
  });

  describe('Route Error Handling', () => {
    test('should handle missing dependencies gracefully', () => {
      // Test that routes handle missing dependencies without crashing
      expect(() => {
        require('../../routes/settings');
      }).not.toThrow();

      expect(() => {
        require('../../routes/portfolio');
      }).not.toThrow();

      expect(() => {
        require('../../routes/user');
      }).not.toThrow();
    });

    test('should return proper error format for 503 responses', async () => {
      // Create a mock failing route
      const mockFailingRouter = express.Router();
      mockFailingRouter.get('/test', (req, res) => {
        res.status(503).json({
          success: false,
          error: 'Test service temporarily unavailable',
          message: 'Route failed to load - check logs for details',
          timestamp: new Date().toISOString()
        });
      });

      app.use('/api/mock-failing', mockFailingRouter);

      const response = await request(app)
        .get('/api/mock-failing/test')
        .expect(503);

      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error');
      expect(response.body).toHaveProperty('message');
      expect(response.body).toHaveProperty('timestamp');
    });
  });

  describe('Route Response Formats', () => {
    test('routes should return consistent response formats', async () => {
      // Test that loaded routes return consistent JSON structures
      const testRoutes = [
        { path: '/api/settings/api-keys', expectedStatus: [200, 401] },
        { path: '/api/config/cloudformation', expectedStatus: [200, 400, 401] }
      ];

      for (const route of testRoutes) {
        const response = await request(app).get(route.path);
        
        // Should not be 503 (route loading failure)
        expect(response.status).not.toBe(503);
        
        // Should return JSON
        expect(response.headers['content-type']).toMatch(/json/);
        
        // Should have consistent structure
        expect(response.body).toBeInstanceOf(Object);
        expect(response.body).toHaveProperty('success');
      }
    });
  });
});
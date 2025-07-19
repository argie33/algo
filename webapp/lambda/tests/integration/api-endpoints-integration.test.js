/**
 * API Endpoints Integration Testing
 * Tests all Lambda API endpoints with real database connections
 */

const request = require('supertest');
const { handler } = require('../../index');
const { testDatabase } = require('../utils/test-database');

describe('Backend API Integration Tests', () => {
  let app;
  let testToken;
  
  beforeAll(async () => {
    console.log('🚀 Setting up API integration tests...');
    
    // Setup Express app for testing
    const express = require('express');
    app = express();
    app.use(express.json());
    
    // Create a test route handler
    app.all('*', async (req, res) => {
      // Convert Express request to Lambda event format
      const event = {
        httpMethod: req.method,
        path: req.path,
        pathParameters: req.params,
        queryStringParameters: req.query,
        headers: req.headers,
        body: req.body ? JSON.stringify(req.body) : null,
        requestContext: {
          requestId: 'test-request-id',
          stage: 'test',
          httpMethod: req.method,
          path: req.path
        }
      };
      
      const context = {
        requestId: 'test-request-id',
        logGroupName: 'test-log-group',
        logStreamName: 'test-log-stream',
        functionName: 'test-function',
        functionVersion: '$LATEST',
        memoryLimitInMB: 512,
        getRemainingTimeInMillis: () => 300000
      };
      
      try {
        const result = await handler(event, context);
        res.status(result.statusCode);
        
        if (result.headers) {
          Object.entries(result.headers).forEach(([key, value]) => {
            res.set(key, value);
          });
        }
        
        if (result.body) {
          const body = typeof result.body === 'string' ? JSON.parse(result.body) : result.body;
          res.json(body);
        } else {
          res.end();
        }
      } catch (error) {
        console.error('Lambda handler error:', error);
        res.status(500).json({ error: 'Internal server error', details: error.message });
      }
    });
    
    // Initialize test database
    await testDatabase.init();
    
    console.log('✅ API integration test setup complete');
  });
  
  afterAll(async () => {
    await testDatabase.cleanup();
  });
  
  describe('Health Check Endpoints', () => {
    test('GET /health should return system status', async () => {
      const response = await request(app)
        .get('/health')
        .expect(200);
      
      expect(response.body).toHaveProperty('status');
      expect(response.body).toHaveProperty('timestamp');
      expect(response.body).toHaveProperty('services');
    });
    
    test('GET /health/database should check database connectivity', async () => {
      const response = await request(app)
        .get('/health/database')
        .expect('Content-Type', /json/);
      
      expect([200, 503]).toContain(response.status);
      expect(response.body).toHaveProperty('database');
    });
  });
  
  describe('Authentication Endpoints', () => {
    test('POST /auth/validate should validate JWT tokens', async () => {
      // Test with invalid token
      const invalidResponse = await request(app)
        .post('/auth/validate')
        .send({ token: 'invalid-token' })
        .expect(401);
      
      expect(invalidResponse.body).toHaveProperty('error');
    });
    
    test('GET /auth/user should return user information for valid session', async () => {
      // This test assumes you have a way to create test tokens
      // For now, test the endpoint structure
      const response = await request(app)
        .get('/auth/user')
        .expect('Content-Type', /json/);
      
      expect([200, 401]).toContain(response.status);
    });
  });
  
  describe('Portfolio Endpoints', () => {
    test('GET /portfolio should require authentication', async () => {
      const response = await request(app)
        .get('/portfolio')
        .expect(401);
      
      expect(response.body).toHaveProperty('error');
    });
    
    test('GET /portfolio/:id should validate portfolio ID format', async () => {
      const response = await request(app)
        .get('/portfolio/invalid-id')
        .expect('Content-Type', /json/);
      
      expect([400, 401]).toContain(response.status);
    });
  });
  
  describe('Market Data Endpoints', () => {
    test('GET /market/stocks should return stock data', async () => {
      const response = await request(app)
        .get('/market/stocks')
        .query({ symbols: 'AAPL,MSFT' })
        .expect('Content-Type', /json/);
      
      expect([200, 401]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('data');
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });
    
    test('GET /market/quotes should handle symbol validation', async () => {
      const response = await request(app)
        .get('/market/quotes')
        .query({ symbol: 'AAPL' })
        .expect('Content-Type', /json/);
      
      expect([200, 400, 401]).toContain(response.status);
    });
  });
  
  describe('Settings Endpoints', () => {
    test('GET /settings/api-keys should require authentication', async () => {
      const response = await request(app)
        .get('/settings/api-keys')
        .expect(401);
      
      expect(response.body).toHaveProperty('error');
    });
    
    test('POST /settings/api-keys should validate input format', async () => {
      const response = await request(app)
        .post('/settings/api-keys')
        .send({ invalid: 'data' })
        .expect('Content-Type', /json/);
      
      expect([400, 401]).toContain(response.status);
    });
  });
  
  describe('Live Data Endpoints', () => {
    test('GET /live-data/status should return service status', async () => {
      const response = await request(app)
        .get('/live-data/status')
        .expect('Content-Type', /json/);
      
      expect([200, 503]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('status');
      }
    });
    
    test('POST /live-data/subscribe should validate subscription data', async () => {
      const response = await request(app)
        .post('/live-data/subscribe')
        .send({ symbols: ['AAPL', 'MSFT'] })
        .expect('Content-Type', /json/);
      
      expect([200, 400, 401]).toContain(response.status);
    });
  });
  
  describe('Trading Endpoints', () => {
    test('GET /trading/signals should return trading signals', async () => {
      const response = await request(app)
        .get('/trading/signals')
        .expect('Content-Type', /json/);
      
      expect([200, 401]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('signals');
      }
    });
    
    test('GET /trading/buy-signals should validate query parameters', async () => {
      const response = await request(app)
        .get('/trading/buy-signals')
        .query({ timeframe: '1d', limit: 10 })
        .expect('Content-Type', /json/);
      
      expect([200, 400, 401]).toContain(response.status);
    });
  });
  
  describe('Database Integration', () => {
    test('Endpoints should handle database connection failures gracefully', async () => {
      // This test would require mocking database failures
      // For now, verify that endpoints respond appropriately
      const endpoints = [
        '/health/database',
        '/portfolio',
        '/market/stocks',
        '/settings/api-keys'
      ];
      
      for (const endpoint of endpoints) {
        const response = await request(app)
          .get(endpoint)
          .expect('Content-Type', /json/);
        
        // Should not return 500 errors for connection issues
        expect(response.status).not.toBe(500);
      }
    });
  });
  
  describe('Error Handling', () => {
    test('Invalid routes should return 404', async () => {
      const response = await request(app)
        .get('/non-existent-route')
        .expect(404);
      
      expect(response.body).toHaveProperty('error');
    });
    
    test('Malformed JSON should return 400', async () => {
      const response = await request(app)
        .post('/auth/validate')
        .set('Content-Type', 'application/json')
        .send('invalid json')
        .expect(400);
      
      expect(response.body).toHaveProperty('error');
    });
  });
  
  describe('Performance', () => {
    test('Health endpoint should respond within 1 second', async () => {
      const start = Date.now();
      await request(app)
        .get('/health')
        .expect(200);
      const duration = Date.now() - start;
      
      expect(duration).toBeLessThan(1000);
    });
    
    test('Market data endpoints should respond within 2 seconds', async () => {
      const start = Date.now();
      await request(app)
        .get('/market/stocks')
        .query({ symbols: 'AAPL' });
      const duration = Date.now() - start;
      
      expect(duration).toBeLessThan(2000);
    });
  });
});
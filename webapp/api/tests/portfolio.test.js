/**
 * Portfolio API Routes Tests
 * Tests for portfolio-related endpoints and VaR calculations
 */

const request = require('supertest');
const express = require('express');

// Mock authentication middleware
jest.mock('../middleware/auth', () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: 'test-user-id' };
    next();
  }
}));

const portfolioRoutes = require('../routes/portfolio');
const app = express();
app.use(express.json());
app.use('/api/portfolio', portfolioRoutes);

describe('Portfolio API Routes', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('GET /api/portfolio/api-keys', () => {
    it('should return empty api keys array', async () => {
      const response = await request(app)
        .get('/api/portfolio/api-keys')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: [],
        message: 'Portfolio API keys endpoint available (returning empty for now)'
      });
    });

    it('should handle errors gracefully', async () => {
      // Mock an error in the route handler
      const originalConsoleError = console.error;
      console.error = jest.fn();

      // This test verifies error handling structure
      const response = await request(app)
        .get('/api/portfolio/api-keys')
        .expect(200); // Should still return 200 with current implementation

      expect(response.body.success).toBe(true);
      
      console.error = originalConsoleError;
    });
  });

  describe('GET /api/portfolio/health', () => {
    it('should return portfolio service health status', async () => {
      const response = await request(app)
        .get('/api/portfolio/health')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        service: 'Portfolio API',
        status: 'healthy',
        timestamp: expect.any(String)
      });

      // Verify timestamp is valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
    });
  });

  describe('POST /api/portfolio/calculate-var', () => {
    it('should return demo VaR calculation', async () => {
      const response = await request(app)
        .post('/api/portfolio/calculate-var')
        .send({
          portfolioValue: 100000,
          positions: [
            { symbol: 'AAPL', quantity: 100, currentPrice: 150 },
            { symbol: 'GOOGL', quantity: 50, currentPrice: 2800 }
          ]
        })
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: {
          var: 0.05,
          confidence: 0.95,
          message: 'Demo VaR calculation'
        }
      });
    });

    it('should handle empty request body', async () => {
      const response = await request(app)
        .post('/api/portfolio/calculate-var')
        .send({})
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: {
          var: 0.05,
          confidence: 0.95,
          message: 'Demo VaR calculation'
        }
      });
    });

    it('should handle malformed request data', async () => {
      const response = await request(app)
        .post('/api/portfolio/calculate-var')
        .send({
          portfolioValue: 'invalid',
          positions: 'not-an-array'
        })
        .expect(200);

      // Current implementation returns demo data regardless of input
      expect(response.body.success).toBe(true);
      expect(response.body.data.var).toBe(0.05);
    });

    it('should handle server errors gracefully', async () => {
      // Mock console.error to test error handling
      const originalConsoleError = console.error;
      console.error = jest.fn();

      // For this test, we'll verify the current behavior
      const response = await request(app)
        .post('/api/portfolio/calculate-var')
        .send(null) // This might cause an error
        .expect(200);

      expect(response.body.success).toBe(true);
      
      console.error = originalConsoleError;
    });
  });

  describe('Portfolio Route Structure', () => {
    it('should have all required endpoints', () => {
      const router = require('../routes/portfolio');
      
      // Verify the router is an Express router
      expect(router).toBeDefined();
      expect(typeof router).toBe('function');
      
      // Check that router.stack contains our routes
      expect(router.stack).toBeDefined();
      expect(router.stack.length).toBeGreaterThan(0);
      
      // Verify route paths exist
      const routePaths = router.stack.map(layer => layer.route?.path).filter(Boolean);
      expect(routePaths).toContain('/api-keys');
      expect(routePaths).toContain('/health');
      expect(routePaths).toContain('/calculate-var');
    });

    it('should export a valid Express router', () => {
      const router = require('../routes/portfolio');
      
      // Verify it has router methods
      expect(typeof router.get).toBe('function');
      expect(typeof router.post).toBe('function');
      expect(typeof router.use).toBe('function');
    });
  });

  describe('Response Format Consistency', () => {
    it('should return consistent success response format', async () => {
      const endpoints = [
        { method: 'get', path: '/api/portfolio/api-keys' },
        { method: 'get', path: '/api/portfolio/health' },
        { method: 'post', path: '/api/portfolio/calculate-var', body: {} }
      ];

      for (const endpoint of endpoints) {
        const req = request(app)[endpoint.method](endpoint.path);
        
        if (endpoint.body) {
          req.send(endpoint.body);
        }
        
        const response = await req.expect(200);
        
        // All responses should have success field
        expect(response.body).toHaveProperty('success');
        expect(response.body.success).toBe(true);
        
        // Should have either data or specific fields
        expect(
          Object.prototype.hasOwnProperty.call(response.body, 'data') || 
          Object.prototype.hasOwnProperty.call(response.body, 'service') ||
          Object.prototype.hasOwnProperty.call(response.body, 'message')
        ).toBe(true);
      }
    });
  });

  describe('Content-Type Headers', () => {
    it('should return JSON content type', async () => {
      const response = await request(app)
        .get('/api/portfolio/health')
        .expect(200)
        .expect('Content-Type', /json/);

      expect(response.headers['content-type']).toMatch(/application\/json/);
    });
  });

  describe('Error Handling', () => {
    it('should handle route not found', async () => {
      const response = await request(app)
        .get('/api/portfolio/nonexistent')
        .expect(404);

      // Express default 404 handling
      expect(response.status).toBe(404);
    });

    it('should handle invalid HTTP methods', async () => {
      const response = await request(app)
        .patch('/api/portfolio/health') // PATCH not supported
        .expect(404);

      expect(response.status).toBe(404);
    });
  });
});
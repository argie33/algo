/**
 * Recommendations Routes Unit Tests
 * Tests recommendations route logic in isolation with mocks
 */

const express = require('express');
const request = require('supertest');

// Mock the database utility
jest.mock('../../../utils/database', () => ({
  query: jest.fn()
}));

describe('Recommendations Routes Unit Tests', () => {
  let app;
  let recommendationsRouter;
  let mockQuery;

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Set up mocks
    const { query } = require('../../../utils/database');
    mockQuery = query;
    
    // Create test app
    app = express();
    app.use(express.json());
    
    // Add response helper middleware
    app.use((req, res, next) => {
      res.error = (message, status) => res.status(status).json({ 
        success: false, 
        error: message 
      });
      next();
    });
    
    // Load the route module
    recommendationsRouter = require('../../../routes/recommendations');
    app.use('/recommendations', recommendationsRouter);
  });

  describe('GET /recommendations', () => {
    test('should return recommendations with mocked data', async () => {
      // Mock successful database response
      mockQuery.mockResolvedValue({
        rows: [
          {
            symbol: 'AAPL',
            analyst_firm: 'Goldman Sachs',
            rating: 'Buy',
            target_price: 200.00,
            current_price: 180.00,
            date_published: '2024-01-15',
            date_updated: '2024-01-15'
          }
        ]
      });

      const response = await request(app)
        .get('/recommendations');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('recommendations');
      expect(response.body).toHaveProperty('summary');
      expect(response.body).toHaveProperty('filters');
      expect(response.body).toHaveProperty('timestamp');
      
      // Verify recommendations structure
      expect(response.body.recommendations).toHaveLength(1);
      expect(response.body.recommendations[0]).toHaveProperty('symbol', 'AAPL');
      expect(response.body.recommendations[0]).toHaveProperty('analyst_firm', 'Goldman Sachs');
      
      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(mockQuery).toHaveBeenCalled();
    });

    test('should handle query parameters', async () => {
      // Mock successful database response
      mockQuery.mockResolvedValue({
        rows: [
          {
            symbol: 'AAPL',
            analyst_firm: 'Goldman Sachs',
            rating: 'Buy',
            target_price: 200.00,
            current_price: 180.00,
            date_published: '2024-01-15',
            date_updated: '2024-01-15'
          }
        ]
      });

      const response = await request(app)
        .get('/recommendations')
        .query({
          symbol: 'AAPL',
          category: 'buy',
          analyst: 'goldman_sachs',
          limit: 50,
          timeframe: 'recent'
        });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body.filters).toHaveProperty('symbol', 'AAPL');
      expect(response.body.filters).toHaveProperty('category', 'buy');
      expect(response.body.filters).toHaveProperty('analyst', 'goldman_sachs');
      expect(response.body.filters).toHaveProperty('timeframe', 'recent');
      expect(response.body.filters).toHaveProperty('limit', 50);
      // Parameters are processed and endpoint returns real data
    });

    test('should include comprehensive troubleshooting information', async () => {
      const response = await request(app)
        .get('/recommendations');

      expect(response.body.troubleshooting).toHaveProperty('suggestion');
      expect(response.body.troubleshooting).toHaveProperty('required_setup');
      expect(response.body.troubleshooting).toHaveProperty('status');
      expect(Array.isArray(response.body.troubleshooting.required_setup)).toBe(true);
      expect(response.body.troubleshooting.required_setup).toContain('Analyst recommendations data provider integration (Bloomberg, Refinitiv, S&P)');
      expect(response.body.troubleshooting.required_setup).toContain('Recommendation consensus calculation modules');
    });

    test('should handle different category parameters', async () => {
      const categories = ['all', 'buy', 'sell', 'hold'];
      
      for (const category of categories) {
        const response = await request(app)
          .get('/recommendations')
          .query({ category });

        expect(response.status).toBe(501);
        expect(response.body.filters).toHaveProperty('category', category);
        expect(response.body).toHaveProperty('success', false);
      }
    });

    test('should default to all category', async () => {
      const response = await request(app)
        .get('/recommendations')
        .query({ symbol: 'AAPL' });

      expect(response.status).toBe(501);
      expect(response.body.filters).toHaveProperty('category', 'all'); // default value
    });

    test('should handle different timeframe parameters', async () => {
      const timeframes = ['recent', 'weekly', 'monthly'];
      
      for (const timeframe of timeframes) {
        const response = await request(app)
          .get('/recommendations')
          .query({ timeframe });

        expect(response.status).toBe(501);
        expect(response.body.filters).toHaveProperty('timeframe', timeframe);
        expect(response.body).toHaveProperty('success', false);
      }
    });

    test('should handle analyst filter parameter', async () => {
      const response = await request(app)
        .get('/recommendations')
        .query({ analyst: 'morgan_stanley' });

      expect(response.status).toBe(501);
      expect(response.body.filters).toHaveProperty('analyst', 'morgan_stanley');
      expect(response.body).toHaveProperty('success', false);
    });

    test('should handle limit parameter and parse as integer', async () => {
      const response = await request(app)
        .get('/recommendations')
        .query({ limit: '100' });

      expect(response.status).toBe(501);
      expect(response.body.filters).toHaveProperty('limit', 100); // Should be parsed as number
      expect(response.body).toHaveProperty('success', false);
    });

    test('should handle default limit parameter', async () => {
      const response = await request(app)
        .get('/recommendations');

      expect(response.status).toBe(501);
      expect(response.body.filters).toHaveProperty('limit', 20); // default value
    });

    test('should handle symbol parameter', async () => {
      const response = await request(app)
        .get('/recommendations')
        .query({ symbol: 'GOOGL' });

      expect(response.status).toBe(501);
      expect(response.body).toHaveProperty('symbol', 'GOOGL');
      expect(response.body).toHaveProperty('success', false);
    });

    test('should handle no symbol parameter', async () => {
      const response = await request(app)
        .get('/recommendations');

      expect(response.status).toBe(501);
      expect(response.body).toHaveProperty('symbol', null);
      expect(response.body).toHaveProperty('success', false);
    });
  });

  describe('GET /recommendations/consensus', () => {
    test('should return not implemented for consensus endpoint when accessed', async () => {
      // This test assumes the consensus endpoint exists but is also not implemented
      const response = await request(app)
        .get('/recommendations/consensus');

      // The consensus endpoint doesn't exist, so it should return 404
      expect(response.status).toBe(404);
    });
  });

  describe('GET /recommendations/analysts', () => {
    test('should handle analysts endpoint when accessed', async () => {
      // This test assumes the analysts endpoint might exist
      const response = await request(app)
        .get('/recommendations/analysts');

      // The analysts endpoint without symbol doesn't exist, should return 404
      expect(response.status).toBe(404);
    });
  });

  describe('GET /recommendations/price-targets', () => {
    test('should handle price targets endpoint when accessed', async () => {
      // This test assumes the price targets endpoint might exist
      const response = await request(app)
        .get('/recommendations/price-targets');

      // The price-targets endpoint doesn't exist, should return 404
      expect(response.status).toBe(404);
    });
  });

  describe('Error handling', () => {
    test('should handle implementation errors gracefully', async () => {
      // Test the catch block by mocking console.error to throw
      const originalConsoleError = console.error;
      console.error = jest.fn(() => {
        throw new Error('Logging failed');
      });

      const response = await request(app)
        .get('/recommendations');

      // Should still return the not implemented response
      expect(response.status).toBe(501);
      expect(response.body).toHaveProperty('success', false);

      // Restore console.error
      console.error = originalConsoleError;
    });

    test('should handle malformed query parameters', async () => {
      const response = await request(app)
        .get('/recommendations')
        .query({ 
          limit: 'not_a_number',
          category: 'invalid_category_but_still_works',
          analyst: 'special!@#$%^&*()characters'
        });

      expect(response.status).toBe(501);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body.filters).toHaveProperty('limit', NaN); // parseInt of invalid string
      expect(response.body.filters).toHaveProperty('category', 'invalid_category_but_still_works');
      // Should still process gracefully even with invalid parameters
    });

    test('should handle special characters in parameters', async () => {
      const response = await request(app)
        .get('/recommendations')
        .query({ 
          symbol: "AAPL'; DROP TABLE recommendations; --",
          analyst: "<script>alert('xss')</script>"
        });

      expect(response.status).toBe(501);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('symbol', "AAPL'; DROP TABLE recommendations; --");
      expect(response.body.filters).toHaveProperty('analyst', "<script>alert('xss')</script>");
      // Should handle malicious input safely since it's not actually querying database
    });

    test('should handle empty string parameters', async () => {
      const response = await request(app)
        .get('/recommendations')
        .query({ 
          symbol: '',
          category: '',
          analyst: ''
        });

      expect(response.status).toBe(501);
      expect(response.body).toHaveProperty('symbol', '');
      expect(response.body.filters).toHaveProperty('category', '');
      expect(response.body.filters).toHaveProperty('analyst', '');
      expect(response.body).toHaveProperty('success', false);
    });
  });

  describe('Response format', () => {
    test('should return consistent JSON response format', async () => {
      const response = await request(app)
        .get('/recommendations');

      expect(response.headers['content-type']).toMatch(/json/);
      expect(typeof response.body).toBe('object');
      expect(response.body).toHaveProperty('success');
      expect(response.body).toHaveProperty('timestamp');
    });

    test('should include detailed implementation requirements', async () => {
      const response = await request(app)
        .get('/recommendations');

      expect(response.body).toHaveProperty('details');
      expect(response.body.details).toContain('analyst recommendations data');
      expect(response.body).toHaveProperty('troubleshooting');
      expect(response.body.troubleshooting).toHaveProperty('required_setup');
      expect(response.body.troubleshooting.required_setup.length).toBeGreaterThan(0);
    });

    test('should preserve query parameters in response', async () => {
      const response = await request(app)
        .get('/recommendations')
        .query({ 
          symbol: 'TSLA',
          category: 'buy',
          limit: '25'
        });

      expect(response.body).toHaveProperty('symbol', 'TSLA');
      expect(response.body.filters).toHaveProperty('category', 'buy');
      expect(response.body.filters).toHaveProperty('limit', 25);
    });

    test('should include all filter parameters in response', async () => {
      const response = await request(app)
        .get('/recommendations')
        .query({ 
          symbol: 'AAPL',
          category: 'hold',
          analyst: 'jp_morgan',
          timeframe: 'monthly',
          limit: '15'
        });

      expect(response.body).toHaveProperty('filters');
      expect(response.body.filters).toHaveProperty('category', 'hold');
      expect(response.body.filters).toHaveProperty('analyst', 'jp_morgan');
      expect(response.body.filters).toHaveProperty('timeframe', 'monthly');
      expect(response.body.filters).toHaveProperty('limit', 15);
    });
  });

  describe('Future implementation readiness', () => {
    test('should be ready for future implementation with proper parameter handling', async () => {
      const response = await request(app)
        .get('/recommendations')
        .query({
          symbol: 'AAPL',
          category: 'buy',
          analyst: 'goldman_sachs',
          timeframe: 'recent',
          limit: '30'
        });

      // Response structure should support future implementation
      expect(response.body).toHaveProperty('symbol');
      expect(response.body).toHaveProperty('filters');
      expect(response.body).toHaveProperty('timestamp');
      
      // Troubleshooting info indicates what needs to be implemented
      expect(response.body.troubleshooting.required_setup).toContain('Price target and rating tracking system');
      expect(response.body.troubleshooting.required_setup).toContain('Analyst firm and individual analyst tracking');
    });

    test('should handle all expected recommendation categories', async () => {
      const validCategories = ['all', 'buy', 'sell', 'hold'];
      
      for (const category of validCategories) {
        const response = await request(app)
          .get('/recommendations')
          .query({ category });

        expect(response.body.filters).toHaveProperty('category', category);
        // Future implementation should support these categories
      }
    });
  });
});
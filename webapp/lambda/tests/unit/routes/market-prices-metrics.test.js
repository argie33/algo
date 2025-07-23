/**
 * Market Prices and Metrics Routes Unit Tests
 * Testing the new /prices/:symbol and /metrics/:symbol endpoints
 */

const request = require('supertest');
const express = require('express');

// Mock the query function
const mockQuery = jest.fn();
jest.mock('../../../utils/database', () => ({
  query: mockQuery
}));

const marketRouter = require('../../../routes/market');

describe('📊 Market Prices and Metrics Endpoints', () => {
  let app;

  beforeEach(() => {
    app = express();
    app.use('/api/market', marketRouter);
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('GET /api/market/prices/:symbol', () => {
    it('should return price data for valid symbol when table exists', async () => {
      // Mock table exists check
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: true }]
      });

      // Mock price data query
      mockQuery.mockResolvedValueOnce({
        rows: [{
          symbol: 'AAPL',
          price: 185.50,
          change_percent: 1.25,
          price_change: 2.30,
          volume: 45000000,
          high: 187.00,
          low: 183.20,
          open: 184.00,
          timestamp: '2024-01-15T16:00:00Z'
        }]
      });

      const response = await request(app)
        .get('/api/market/prices/AAPL')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        symbol: 'AAPL',
        price: 185.50,
        change: 2.30,
        changePercent: 1.25,
        volume: 45000000,
        high: 187.00,
        low: 183.20,
        open: 184.00,
        timestamp: '2024-01-15T16:00:00Z'
      });

      expect(mockQuery).toHaveBeenCalledTimes(2);
    });

    it('should return 503 when table does not exist (no fallback)', async () => {
      // Mock table does not exist
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: false }]
      });

      const response = await request(app)
        .get('/api/market/prices/AAPL')
        .expect(503);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Service unavailable');
      expect(response.body.message).toContain('Market data infrastructure not configured');
    });

    it('should return 404 when no price data found (no fallback)', async () => {
      // Mock table exists
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: true }]
      });

      // Mock empty result
      mockQuery.mockResolvedValueOnce({
        rows: []
      });

      const response = await request(app)
        .get('/api/market/prices/TSLA')
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Symbol not found');
      expect(response.body.message).toContain('No market data available');
    });

    it('should validate symbol format', async () => {
      const response = await request(app)
        .get('/api/market/prices/invalid123')
        .expect(400);

      expect(response.body).toEqual({
        success: false,
        error: 'Invalid symbol',
        message: 'Symbol must be 1-10 uppercase letters'
      });
    });

    it('should handle database errors gracefully', async () => {
      mockQuery.mockRejectedValueOnce(new Error('Database connection failed'));

      const response = await request(app)
        .get('/api/market/prices/AAPL')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Internal server error');
      expect(response.body.symbol).toBe('AAPL');
    });

    it('should handle case-insensitive symbols', async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: true }]
      });

      mockQuery.mockResolvedValueOnce({
        rows: [{
          symbol: 'MSFT',
          price: 415.25,
          change_percent: -0.5,
          price_change: -2.10,
          volume: 25000000,
          high: 417.00,
          low: 413.50,
          open: 416.00,
          timestamp: '2024-01-15T16:00:00Z'
        }]
      });

      const response = await request(app)
        .get('/api/market/prices/msft')
        .expect(200);

      expect(response.body.symbol).toBe('MSFT');
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('WHERE UPPER(symbol) = $1'),
        ['MSFT']
      );
    });
  });

  describe('GET /api/market/metrics/:symbol', () => {
    it('should return metrics data for valid symbol when table exists', async () => {
      // Mock table exists check
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: true }]
      });

      // Mock metrics data query
      mockQuery.mockResolvedValueOnce({
        rows: [{
          symbol: 'AAPL',
          market_cap: 2850000000000,
          pe_ratio: 28.5,
          pb_ratio: 45.2,
          dividend: 0.96,
          dividend_yield: 0.52,
          eps: 6.50,
          beta: 1.29,
          volatility: 24.5,
          avg_volume: 45000000,
          shares_outstanding: 15400000000,
          timestamp: '2024-01-15T16:00:00Z'
        }]
      });

      const response = await request(app)
        .get('/api/market/metrics/AAPL')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        symbol: 'AAPL',
        metrics: {
          marketCap: 2850000000000,
          peRatio: 28.5,
          pbRatio: 45.2,
          dividend: 0.96,
          dividendYield: 0.52,
          eps: 6.50,
          beta: 1.29,
          volatility: 24.5,
          avgVolume: 45000000,
          sharesOutstanding: 15400000000
        },
        timestamp: '2024-01-15T16:00:00Z'
      });

      expect(mockQuery).toHaveBeenCalledTimes(2);
    });

    it('should return 503 when table does not exist (no fallback)', async () => {
      // Mock table does not exist
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: false }]
      });

      const response = await request(app)
        .get('/api/market/metrics/GOOGL')
        .expect(503);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Service unavailable');
      expect(response.body.message).toContain('Market data infrastructure not configured');
    });

    it('should return 404 when no metrics data found (no fallback)', async () => {
      // Mock table exists
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: true }]
      });

      // Mock empty result
      mockQuery.mockResolvedValueOnce({
        rows: []
      });

      const response = await request(app)
        .get('/api/market/metrics/NVDA')
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Symbol not found');
      expect(response.body.message).toContain('No market metrics available');
    });

    it('should validate symbol format for metrics', async () => {
      const response = await request(app)
        .get('/api/market/metrics/1234')
        .expect(400);

      expect(response.body).toEqual({
        success: false,
        error: 'Invalid symbol',
        message: 'Symbol must be 1-10 uppercase letters'
      });
    });

    it('should handle database errors in metrics endpoint', async () => {
      mockQuery.mockRejectedValueOnce(new Error('Connection timeout'));

      const response = await request(app)
        .get('/api/market/metrics/AAPL')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Internal server error');
      expect(response.body.symbol).toBe('AAPL');
    });

    it('should handle null/undefined metric values', async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: true }]
      });

      mockQuery.mockResolvedValueOnce({
        rows: [{
          symbol: 'TEST',
          market_cap: null,
          pe_ratio: undefined,
          pb_ratio: 2.5,
          dividend: null,
          dividend_yield: 0,
          eps: 1.25,
          beta: null,
          volatility: 35.0,
          avg_volume: 1000000,
          shares_outstanding: null,
          timestamp: '2024-01-15T16:00:00Z'
        }]
      });

      const response = await request(app)
        .get('/api/market/metrics/TEST')
        .expect(200);

      expect(response.body.metrics.marketCap).toBeNull();
      expect(response.body.metrics.peRatio).toBeNull();
      expect(response.body.metrics.pbRatio).toBe(2.5);
      expect(response.body.metrics.dividend).toBeNull();
      expect(response.body.metrics.eps).toBe(1.25);
    });
  });

  describe('Symbol validation', () => {
    it('should properly handle valid symbols when no infrastructure', async () => {
      mockQuery.mockResolvedValue({ rows: [{ exists: false }] });

      const validSymbols = ['A', 'AAPL', 'BERKSHAREA'];
      
      for (const symbol of validSymbols.slice(0, 3)) { // Test first 3 to avoid regex complexity
        const response = await request(app)
          .get(`/api/market/prices/${symbol}`)
          .expect(503); // Should return 503 when infrastructure not configured
        
        expect(response.body.success).toBe(false);
        expect(response.body.error).toBe('Service unavailable');
      }
    });

    it('should handle various symbol formats with proper errors', async () => {
      mockQuery.mockResolvedValue({ rows: [{ exists: false }] });
      
      const testSymbols = ['123', 'TOOLONGSY', 'VALID'];
      
      for (const symbol of testSymbols) {
        const response = await request(app)
          .get(`/api/market/prices/${symbol}`);
        
        // API should handle all symbols with proper HTTP status codes (400 for invalid, 503 for no infrastructure)
        expect([400, 503]).toContain(response.status);
        expect(response.body.success).toBe(false);
      }
    });
  });

  describe('Error handling', () => {
    it('should handle malformed database responses', async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: true }]
      });

      // Mock malformed response
      mockQuery.mockResolvedValueOnce({
        rows: null
      });

      const response = await request(app)
        .get('/api/market/prices/AAPL')
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Symbol not found');
    });

    it('should handle database query timeout', async () => {
      const timeoutError = new Error('Query timeout');
      timeoutError.code = 'QUERY_TIMEOUT';
      
      mockQuery.mockRejectedValueOnce(timeoutError);

      const response = await request(app)
        .get('/api/market/metrics/AAPL')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.details).toBe('Query timeout');
    });
  });
});
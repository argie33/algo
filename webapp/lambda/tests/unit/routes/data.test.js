/**
 * Data Routes Unit Tests
 * Tests data route logic in isolation with mocks
 */

const express = require('express');
const request = require('supertest');

// Mock the database utility
jest.mock('../../../utils/database', () => ({
  query: jest.fn()
}));

describe('Data Routes Unit Tests', () => {
  let app;
  let dataRouter;
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
      res.notFound = (message) => res.status(404).json({ 
        success: false, 
        error: message 
      });
      res.serverError = (message, details) => res.status(500).json({
        success: false,
        error: message,
        details
      });
      res.validationError = (message) => res.status(400).json({
        success: false,
        error: message
      });
      next();
    });
    
    // Load the route module
    dataRouter = require('../../../routes/data');
    app.use('/data', dataRouter);
  });

  describe('GET /data', () => {
    test('should return data API information', async () => {
      const response = await request(app)
        .get('/data');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('message', 'Data API - Ready');
      expect(response.body).toHaveProperty('status', 'operational');
      expect(response.body).toHaveProperty('timestamp');
      expect(response.body).toHaveProperty('endpoints');
      expect(Array.isArray(response.body.endpoints)).toBe(true);
      expect(response.body.endpoints).toHaveLength(4);
      expect(mockQuery).not.toHaveBeenCalled(); // Info endpoint doesn't use database
    });

    test('should handle errors gracefully', async () => {
      // Mock console.error to throw (simulate error in try block)
      const originalConsoleLog = console.log;
      console.log = jest.fn(() => {
        throw new Error('Unexpected error');
      });

      const response = await request(app)
        .get('/data');

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'Failed to get data API information');

      // Restore console.log
      console.log = originalConsoleLog;
    });
  });

  describe('GET /data/:symbol', () => {
    test('should return comprehensive data for a symbol', async () => {
      const mockPriceData = {
        symbol: 'AAPL',
        date: '2024-01-15',
        open: 180.50,
        high: 185.25,
        low: 179.75,
        close: 184.82,
        adj_close: 184.82,
        volume: 45678900
      };

      const mockTechnicalData = {
        symbol: 'AAPL',
        date: '2024-01-15',
        rsi: 65.34,
        macd: 2.15,
        macd_signal: 1.89,
        macd_hist: 0.26,
        sma_20: 182.45,
        sma_50: 175.60,
        ema_4: 183.20,
        ema_9: 181.75,
        ema_21: 180.30,
        bbands_upper: 188.50,
        bbands_lower: 176.40,
        bbands_middle: 182.45,
        adx: 25.80,
        atr: 3.45
      };

      // Mock both database queries
      mockQuery
        .mockResolvedValueOnce({ rows: [mockPriceData] })  // price query
        .mockResolvedValueOnce({ rows: [mockTechnicalData] }); // technical query

      const response = await request(app)
        .get('/data/aapl');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('symbol', 'AAPL');
      expect(response.body).toHaveProperty('price', mockPriceData);
      expect(response.body).toHaveProperty('technical', mockTechnicalData);
      expect(response.body).toHaveProperty('timestamp');
      
      expect(mockQuery).toHaveBeenCalledTimes(2);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('SELECT symbol, date, open, high, low, close, adj_close, volume'),
        ['AAPL']
      );
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('SELECT symbol, date, rsi, macd'),
        ['AAPL']
      );
    });

    test('should handle symbol case conversion', async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/data/tsla');

      expect(mockQuery).toHaveBeenCalledWith(expect.any(String), ['TSLA']);
    });

    test('should return 404 when no data found', async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] }) // price query
        .mockResolvedValueOnce({ rows: [] }); // technical query

      const response = await request(app)
        .get('/data/INVALID');

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'No data available for symbol INVALID');
    });

    test('should return data when only price data exists', async () => {
      const mockPriceData = { symbol: 'AAPL', close: 150.00 };

      mockQuery
        .mockResolvedValueOnce({ rows: [mockPriceData] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/data/aapl');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('price', mockPriceData);
      expect(response.body).toHaveProperty('technical', null);
    });

    test('should return data when only technical data exists', async () => {
      const mockTechnicalData = { symbol: 'AAPL', rsi: 65.5 };

      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [mockTechnicalData] });

      const response = await request(app)
        .get('/data/aapl');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('price', null);
      expect(response.body).toHaveProperty('technical', mockTechnicalData);
    });

    test('should handle database errors', async () => {
      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      const response = await request(app)
        .get('/data/aapl');

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'Failed to retrieve data for AAPL');
      expect(response.body.details).toHaveProperty('symbol', 'AAPL');
      expect(response.body.details).toHaveProperty('error', 'Database connection failed');
      expect(response.body.details).toHaveProperty('service', 'data-api');
    });
  });

  describe('GET /data/historical/:symbol', () => {
    test('should return historical data for a symbol', async () => {
      const mockHistoricalData = [
        {
          symbol: 'AAPL',
          date: '2024-01-15',
          open: 180.50,
          high: 185.25,
          low: 179.75,
          close: 184.82,
          adj_close: 184.82,
          volume: 45678900
        },
        {
          symbol: 'AAPL',
          date: '2024-01-14',
          open: 178.20,
          high: 182.50,
          low: 177.80,
          close: 180.95,
          adj_close: 180.95,
          volume: 52341000
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockHistoricalData });

      const response = await request(app)
        .get('/data/historical/aapl');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('symbol', 'AAPL');
      expect(response.body).toHaveProperty('data', mockHistoricalData);
      expect(response.body).toHaveProperty('count', 2);
      expect(response.body).toHaveProperty('parameters');
      
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('ORDER BY date DESC LIMIT'),
        ['AAPL', 50]
      );
    });

    test('should handle query parameters', async () => {
      mockQuery.mockResolvedValue({ rows: [{ symbol: 'AAPL' }] });

      const response = await request(app)
        .get('/data/historical/aapl')
        .query({
          start: '2024-01-01',
          end: '2024-01-31',
          limit: '25'
        });

      expect(response.body.parameters).toEqual({
        start: '2024-01-01',
        end: '2024-01-31',
        limit: '25'
      });

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('AND date >= $2'),
        ['AAPL', '2024-01-01', '2024-01-31', 25]
      );
    });

    test('should handle start parameter only', async () => {
      mockQuery.mockResolvedValue({ rows: [{ symbol: 'AAPL' }] });

      await request(app)
        .get('/data/historical/aapl')
        .query({ start: '2024-01-01' });

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('AND date >= $2'),
        ['AAPL', '2024-01-01', 50]
      );
    });

    test('should handle end parameter only', async () => {
      mockQuery.mockResolvedValue({ rows: [{ symbol: 'AAPL' }] });

      await request(app)
        .get('/data/historical/aapl')
        .query({ end: '2024-01-31' });

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('AND date <= $2'),
        ['AAPL', '2024-01-31', 50]
      );
    });

    test('should return 404 when no historical data found', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/data/historical/INVALID');

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty('error', 'No historical data available for symbol INVALID');
    });

    test('should handle database errors', async () => {
      mockQuery.mockRejectedValue(new Error('Query timeout'));

      const response = await request(app)
        .get('/data/historical/aapl');

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty('error', 'Failed to retrieve historical data for AAPL');
      expect(response.body.details).toHaveProperty('error', 'Query timeout');
    });
  });

  describe('GET /data/realtime/:symbol', () => {
    test('should return real-time data for a symbol', async () => {
      const mockRealtimeData = {
        symbol: 'AAPL',
        date: '2024-01-15',
        open: 180.50,
        high: 185.25,
        low: 179.75,
        close: 184.82,
        adj_close: 184.82,
        volume: 45678900
      };

      mockQuery.mockResolvedValue({ rows: [mockRealtimeData] });

      const response = await request(app)
        .get('/data/realtime/aapl');

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('symbol', 'AAPL');
      expect(response.body).toHaveProperty('data');
      expect(response.body.data).toHaveProperty('real_time', false);
      expect(response.body.data).toHaveProperty('last_updated');
      expect(response.body).toHaveProperty('disclaimer', 'Real-time data feed not implemented - showing latest historical data');
      
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('ORDER BY date DESC LIMIT 1'),
        ['AAPL']
      );
    });

    test('should return 404 when no real-time data found', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/data/realtime/INVALID');

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty('error', 'No real-time data available for symbol INVALID');
    });

    test('should add real_time flag and last_updated timestamp', async () => {
      const mockData = { symbol: 'AAPL', close: 150.00 };
      mockQuery.mockResolvedValue({ rows: [mockData] });

      const response = await request(app)
        .get('/data/realtime/aapl');

      expect(response.body.data.real_time).toBe(false);
      expect(response.body.data.last_updated).toBeDefined();
      expect(new Date(response.body.data.last_updated)).toBeInstanceOf(Date);
    });

    test('should handle database errors', async () => {
      mockQuery.mockRejectedValue(new Error('Connection lost'));

      const response = await request(app)
        .get('/data/realtime/aapl');

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty('error', 'Failed to retrieve real-time data for AAPL');
      expect(response.body.details).toHaveProperty('error', 'Connection lost');
    });
  });

  describe('GET /data/bulk', () => {
    test('should return bulk data for multiple symbols', async () => {
      const mockBulkData = [
        { symbol: 'AAPL', close: 184.82, date: '2024-01-15' },
        { symbol: 'GOOGL', close: 145.30, date: '2024-01-15' },
        { symbol: 'MSFT', close: 384.52, date: '2024-01-15' }
      ];

      mockQuery.mockResolvedValue({ rows: mockBulkData });

      const response = await request(app)
        .get('/data/bulk')
        .query({ symbols: 'aapl,googl,msft' });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('requested_symbols', ['AAPL', 'GOOGL', 'MSFT']);
      expect(response.body).toHaveProperty('found_symbols', ['AAPL', 'GOOGL', 'MSFT']);
      expect(response.body).toHaveProperty('data');
      expect(response.body).toHaveProperty('count', 3);
      
      expect(response.body.data).toHaveProperty('AAPL');
      expect(response.body.data).toHaveProperty('GOOGL');
      expect(response.body.data).toHaveProperty('MSFT');
      
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('WHERE symbol = ANY($1)'),
        [['AAPL', 'GOOGL', 'MSFT']]
      );
    });

    test('should handle symbols with spaces and case conversion', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/data/bulk')
        .query({ symbols: ' aapl , googl , msft ' });

      expect(response.body.requested_symbols).toEqual(['AAPL', 'GOOGL', 'MSFT']);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        [['AAPL', 'GOOGL', 'MSFT']]
      );
    });

    test('should return 400 when symbols parameter is missing', async () => {
      const response = await request(app)
        .get('/data/bulk');

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty('error', 'symbols parameter is required');
      expect(mockQuery).not.toHaveBeenCalled();
    });

    test('should handle partial results', async () => {
      const mockPartialData = [
        { symbol: 'AAPL', close: 184.82 }
        // INVALID symbol not found
      ];

      mockQuery.mockResolvedValue({ rows: mockPartialData });

      const response = await request(app)
        .get('/data/bulk')
        .query({ symbols: 'aapl,invalid' });

      expect(response.body.requested_symbols).toEqual(['AAPL', 'INVALID']);
      expect(response.body.found_symbols).toEqual(['AAPL']);
      expect(response.body.count).toBe(1);
      expect(response.body.data).toHaveProperty('AAPL');
      expect(response.body.data).not.toHaveProperty('INVALID');
    });

    test('should handle database errors', async () => {
      mockQuery.mockRejectedValue(new Error('Database timeout'));

      const response = await request(app)
        .get('/data/bulk')
        .query({ symbols: 'aapl,googl' });

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty('error', 'Failed to retrieve bulk data');
      expect(response.body.details).toHaveProperty('requested_symbols', ['AAPL', 'GOOGL']);
      expect(response.body.details).toHaveProperty('error', 'Database timeout');
    });
  });

  describe('Edge cases and error handling', () => {
    test('should handle special characters in symbols', async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get('/data/TEST@123');

      expect(mockQuery).toHaveBeenCalledWith(expect.any(String), ['TEST@123']);
    });

    test('should handle very large limit parameters', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/data/historical/aapl')
        .query({ limit: '999999' });

      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        ['AAPL', 999999]
      );
    });

    test('should handle non-numeric limit parameters', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/data/historical/aapl')
        .query({ limit: 'invalid' });

      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        ['AAPL', NaN]
      );
    });

    test('should handle SQL injection attempts in bulk symbols', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/data/bulk')
        .query({ symbols: "AAPL'; DROP TABLE price_daily; --" });

      // Should still process safely since we're using parameterized queries
      expect(response.status).toBe(200);
      expect(response.body.requested_symbols).toEqual(["AAPL'; DROP TABLE PRICE_DAILY; --"]);
    });
  });

  describe('Response format validation', () => {
    test('should return consistent JSON response format', async () => {
      const response = await request(app)
        .get('/data');

      expect(response.headers['content-type']).toMatch(/json/);
      expect(typeof response.body).toBe('object');
      expect(response.body).toHaveProperty('timestamp');
    });

    test('should include timestamp in ISO format', async () => {
      const response = await request(app)
        .get('/data');

      expect(response.body.timestamp).toBeDefined();
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(response.body.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
    });

    test('should preserve data structure for symbol endpoint', async () => {
      const mockPrice = { symbol: 'AAPL', close: 150.00 };
      const mockTechnical = { symbol: 'AAPL', rsi: 65.0 };

      mockQuery
        .mockResolvedValueOnce({ rows: [mockPrice] })
        .mockResolvedValueOnce({ rows: [mockTechnical] });

      const response = await request(app)
        .get('/data/aapl');

      expect(response.body).toMatchObject({
        symbol: 'AAPL',
        price: mockPrice,
        technical: mockTechnical,
        timestamp: expect.any(String)
      });
    });
  });
});
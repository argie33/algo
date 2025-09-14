/**
 * Unit Tests for Price Route
 * Tests the /api/price endpoint functionality with mocked dependencies
 */

const request = require('supertest');
const express = require('express');

// Mock database queries
const mockQuery = jest.fn();
jest.mock('../../../utils/database', () => ({
  query: mockQuery
}));

// Create test app
const app = express();
app.use(express.json());

// Add response formatter middleware for proper res.error, res.success methods
const responseFormatter = require("../../../middleware/responseFormatter");
app.use(responseFormatter);

app.use('/api/price', require('../../../routes/price'));

describe('Price Route - Unit Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('GET /api/price/', () => {
    test('should return API overview', async () => {
      const response = await request(app)
        .get('/api/price/')
        .expect(200);

      expect(response.body.message).toBe('Price API - Ready');
      expect(response.body.status).toBe('operational');
      expect(response.body.endpoints).toBeDefined();
      expect(Array.isArray(response.body.endpoints)).toBe(true);
      expect(response.body.timestamp).toBeDefined();
    });
  });

  describe('GET /api/price/ping', () => {
    test('should return health status', async () => {
      const response = await request(app)
        .get('/api/price/ping')
        .expect(200);

      expect(response.body.status).toBe('ok');
      expect(response.body.endpoint).toBe('price');
      expect(response.body.timestamp).toBeDefined();
    });
  });

  describe('GET /api/price/:symbol', () => {
    test('should get current price for valid symbol', async () => {
      const mockPriceData = [
        {
          symbol: 'AAPL',
          date: '2024-01-15',
          open: 150.00,
          high: 155.00,
          low: 148.00,
          close: 153.50,
          adj_close: 153.50,
          volume: 1000000
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockPriceData });

      const response = await request(app)
        .get('/api/price/AAPL')
        .expect(200);

      expect(response.body.symbol).toBe('AAPL');
      expect(response.body.data.current_price).toBe(153.50);
      expect(response.body.data.open).toBe(150.00);
      expect(response.body.data.close).toBe(153.50);
      expect(response.body.timestamp).toBeDefined();
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('FROM price_daily'),
        ['AAPL']
      );
    });

    test('should handle symbol not found', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/api/price/INVALID')
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('not found');
    });

    test('should handle database errors', async () => {
      mockQuery.mockRejectedValue(new Error('Database connection failed'));

      const response = await request(app)
        .get('/api/price/AAPL')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBeDefined();
    });
  });

  describe('GET /api/price/:symbol/intraday', () => {
    test('should return intraday data with default 5min interval', async () => {
      const mockIntradayData = [
        {
          timestamp: '2024-01-15T09:30:00.000Z',
          price: 150.25,
          volume: 50000
        },
        {
          timestamp: '2024-01-15T09:35:00.000Z',
          price: 150.75,
          volume: 45000
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockIntradayData });

      const response = await request(app)
        .get('/api/price/AAPL/intraday')
        .expect(200);

      expect(response.body.symbol).toBe('AAPL');
      expect(response.body.data.interval).toBe('5min');
      expect(Array.isArray(response.body.data.intraday_data)).toBe(true);
      expect(response.body.data.intraday_data).toHaveLength(2);
      expect(response.body.data.intraday_data[0]).toHaveProperty('timestamp');
      expect(response.body.data.intraday_data[0]).toHaveProperty('price');
      expect(response.body.data.intraday_data[0]).toHaveProperty('volume');
    });

    test('should handle different intervals', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/api/price/AAPL/intraday?interval=1min')
        .expect(200);

      expect(response.body.data.interval).toBe('1min');
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining('1 minutes'),
        expect.anything()
      );
    });

    test('should validate interval parameter', async () => {
      const response = await request(app)
        .get('/api/price/AAPL/intraday?interval=invalid')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Invalid interval');
    });
  });

  describe('GET /api/price/futures/:symbol', () => {
    test('should return futures pricing data', async () => {
      const mockFuturesData = [
        {
          symbol: 'CLZ24',
          underlying_symbol: 'CL',
          contract_month: 'December 2024',
          expiry_date: '2024-12-19',
          current_price: 85.50,
          theoretical_price: 85.75,
          carry_cost: 0.25,
          convenience_yield: 0.05,
          days_to_expiry: 45
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockFuturesData });

      const response = await request(app)
        .get('/api/price/futures/CLZ24')
        .expect(200);

      expect(response.body.symbol).toBe('CLZ24');
      expect(response.body.data).toHaveProperty('contract_details');
      expect(response.body.data).toHaveProperty('pricing_analysis');
      expect(response.body.data.contract_details).toHaveProperty('underlying_symbol');
      expect(response.body.data.pricing_analysis).toHaveProperty('theoretical_price');
      expect(response.body.data.pricing_analysis).toHaveProperty('carry_cost');
    });

    test('should handle non-existent futures contract', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/api/price/futures/INVALID')
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Futures contract not found');
    });
  });

  describe('GET /api/price/:symbol/prediction', () => {
    test('should return price prediction analysis', async () => {
      const mockPredictionData = [
        {
          symbol: 'AAPL',
          current_price: 150.00,
          avg_volume: 45000000,
          volatility: 0.25,
          trend_score: 75,
          support_level: 145.00,
          resistance_level: 155.00
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockPredictionData });

      const response = await request(app)
        .get('/api/price/AAPL/prediction')
        .expect(200);

      expect(response.body.symbol).toBe('AAPL');
      expect(response.body.data).toHaveProperty('current_analysis');
      expect(response.body.data).toHaveProperty('price_targets');
      expect(response.body.data).toHaveProperty('risk_metrics');
      expect(response.body.data).toHaveProperty('technical_indicators');
      expect(response.body.data.current_analysis).toHaveProperty('current_price');
      expect(response.body.data.price_targets).toHaveProperty('target_1d');
      expect(response.body.data.risk_metrics).toHaveProperty('volatility');
    });

    test('should handle different timeframes', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/api/price/AAPL/prediction?timeframe=1w')
        .expect(200);

      expect(response.body.data.timeframe).toBe('1w');
    });

    test('should validate timeframe parameter', async () => {
      const response = await request(app)
        .get('/api/price/AAPL/prediction?timeframe=invalid')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Invalid timeframe');
    });
  });

  describe('GET /api/price/:symbol/alerts', () => {
    test('should return price alert recommendations', async () => {
      const mockAlertData = [
        {
          symbol: 'AAPL',
          current_price: 150.00,
          support_level: 145.00,
          resistance_level: 155.00,
          volatility: 0.25
        }
      ];

      mockQuery.mockResolvedValue({ rows: mockAlertData });

      const response = await request(app)
        .get('/api/price/AAPL/alerts')
        .expect(200);

      expect(response.body.symbol).toBe('AAPL');
      expect(response.body.data).toHaveProperty('current_price');
      expect(response.body.data).toHaveProperty('recommended_alerts');
      expect(response.body.data).toHaveProperty('alert_zones');
      expect(Array.isArray(response.body.data.recommended_alerts)).toBe(true);
    });
  });

  describe('POST /api/price/batch', () => {
    test('should handle batch price requests', async () => {
      const mockBatchData = [
        { symbol: 'AAPL', close_price: 150.00 },
        { symbol: 'MSFT', close_price: 375.00 },
        { symbol: 'GOOGL', close_price: 140.00 }
      ];

      mockQuery.mockResolvedValue({ rows: mockBatchData });

      const response = await request(app)
        .post('/api/price/batch')
        .send({ symbols: ['AAPL', 'MSFT', 'GOOGL'] })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('prices');
      expect(response.body.data).toHaveProperty('summary');
      expect(Object.keys(response.body.data.prices)).toHaveLength(3);
      expect(response.body.data.prices).toHaveProperty('AAPL');
      expect(response.body.data.prices).toHaveProperty('MSFT');
      expect(response.body.data.prices).toHaveProperty('GOOGL');
    });

    test('should validate batch request body', async () => {
      const response = await request(app)
        .post('/api/price/batch')
        .send({}) // Missing symbols array
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('symbols array is required');
    });

    test('should limit batch size', async () => {
      const tooManySymbols = Array.from({ length: 101 }, (_, i) => `STOCK${i}`);
      
      const response = await request(app)
        .post('/api/price/batch')
        .send({ symbols: tooManySymbols })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Maximum 100 symbols allowed');
    });
  });
});
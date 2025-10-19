/**
 * Scores API Value Inputs Integration Test
 * Tests that the /api/scores endpoints return raw valuation input values
 *
 * Coverage: P1 - Market Data Services
 * Strategy: Integration test for API endpoints with real database
 */

const request = require('supertest');
const app = require('../../../server');

// Use REAL database - DO NOT mock, use real data from loaders
// jest.mock("../../../utils/database", ...);

// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),
  authorizeAdmin: jest.fn((req, res, next) => next()),
  checkApiKey: jest.fn((req, res, next) => next()),
}));

describe('Scores API - Value Inputs Integration', () => {
  describe('GET /api/scores (list endpoint)', () => {
    beforeEach(() => {
      jest.clearAllMocks();
    });
    it('should return stocks with complete value_inputs object structure', async () => {
      const response = await request(app)
        .get('/api/scores')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.stocks).toBeInstanceOf(Array);

      if (response.body.data.stocks.length > 0) {
        const stock = response.body.data.stocks[0];

        // Verify value_inputs object structure
        expect(stock).toHaveProperty('value_inputs');
        expect(stock.value_inputs).toBeInstanceOf(Object);

        // Verify all required fields exist (may be null if no data)
        // These fields match the actual loader schema from loadstockscores.py
        const requiredFields = [
          'stock_pe', 'stock_pb', 'stock_ev_ebitda',
          'sector_pe', 'sector_pb', 'sector_ev_ebitda',
          'earnings_growth_pct', 'peg_ratio'
        ];

        requiredFields.forEach(field => {
          expect(stock.value_inputs).toHaveProperty(field);
        });
      }
    });

    it('should calculate PEG ratio correctly when data exists', async () => {
      const response = await request(app)
        .get('/api/scores')
        .expect(200);

      const stocksWithPEGData = response.body.data.stocks.filter(s =>
        s.value_inputs?.stock_pe &&
        s.value_inputs?.earnings_growth_pct &&
        s.value_inputs.earnings_growth_pct > 0
      );

      if (stocksWithPEGData.length > 0) {
        const stock = stocksWithPEGData[0];
        const expectedPEG = stock.value_inputs.stock_pe / stock.value_inputs.earnings_growth_pct;
        expect(stock.value_inputs.peg_ratio).toBeCloseTo(expectedPEG, 1);
      }
    });

    it('should have price metrics data when available', async () => {
      const response = await request(app)
        .get('/api/scores')
        .expect(200);

      const stocksWithPriceData = response.body.data.stocks.filter(s =>
        s.value_inputs?.stock_pe !== null ||
        s.value_inputs?.stock_pb !== null
      );

      if (stocksWithPriceData.length > 0) {
        const stock = stocksWithPriceData[0];
        // Verify at least some price valuation metrics exist
        expect(stock.value_inputs).toHaveProperty('stock_pe');
        expect(stock.value_inputs).toHaveProperty('stock_pb');
      }
    });
  });

  describe('GET /api/scores/:symbol (detail endpoint)', () => {
    it('should return nested value inputs in factors.value.inputs', async () => {
      const response = await request(app)
        .get('/api/scores/AAPL')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('factors');
      expect(response.body.data.factors).toHaveProperty('value');
      expect(response.body.data.factors.value).toHaveProperty('inputs');

      const inputs = response.body.data.factors.value.inputs;

      // Verify structure (actual fields from loader schema)
      const requiredFields = [
        'stock_pe', 'stock_pb', 'stock_ev_ebitda',
        'sector_pe', 'sector_pb', 'sector_ev_ebitda',
        'peg_ratio'
      ];

      requiredFields.forEach(field => {
        expect(inputs).toHaveProperty(field);
      });
    });

    it('should include value score alongside inputs', async () => {
      const response = await request(app)
        .get('/api/scores/AAPL')
        .expect(200);

      const value = response.body.data.factors.value;

      expect(value).toHaveProperty('score');
      expect(value).toHaveProperty('inputs');

      // Verify score is a number
      expect(typeof value.score).toBe('number');

      // Verify inputs object contains expected fields
      expect(value.inputs).toHaveProperty('stock_pe');
      expect(value.inputs).toHaveProperty('peg_ratio');
    });
  });

  describe('Momentum Inputs Integration', () => {
    it('should return momentum input values (RSI, ROC, Mansfield)', async () => {
      const response = await request(app)
        .get('/api/scores/AAPL')
        .expect(200);

      const momentum = response.body.data.factors.momentum;

      expect(momentum).toHaveProperty('components');
      expect(momentum.components).toHaveProperty('rsi');
      expect(momentum.components).toHaveProperty('roc_10d');
      expect(momentum.components).toHaveProperty('roc_60d');
      expect(momentum.components).toHaveProperty('roc_120d');
      expect(momentum.components).toHaveProperty('mansfield_rs');
    });
  });

  describe('Data Type Validation', () => {
    it('should return numbers for all numeric value inputs when present', async () => {
      const response = await request(app)
        .get('/api/scores')
        .expect(200);

      const stocksWithData = response.body.data.stocks.filter(s => s.value_inputs?.stock_pe !== null);

      if (stocksWithData.length > 0) {
        const stock = stocksWithData[0];

        if (stock.value_inputs.stock_pe !== null) {
          expect(typeof stock.value_inputs.stock_pe).toBe('number');
        }
        if (stock.value_inputs.sector_pe !== null) {
          expect(typeof stock.value_inputs.sector_pe).toBe('number');
        }
        if (stock.value_inputs.peg_ratio !== null) {
          expect(typeof stock.value_inputs.peg_ratio).toBe('number');
        }
      }
    });
  });
});

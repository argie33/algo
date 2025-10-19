/**
 * Scores API Quality and Growth Inputs Integration Test
 * Tests that the /api/scores endpoints return raw quality and growth input values
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
    if (!req.headers.authorization) {
      return res.status(401).json({ error: "No authorization header" });
    }
    req.user = { sub: "test-user-123", role: "user" };
    next();
  }),
  authorizeAdmin: jest.fn((req, res, next) => next()),
  checkApiKey: jest.fn((req, res, next) => next()),
}));

// Import the mocked database
const { query } = require("../../../utils/database");

describe('Scores API - Quality and Growth Inputs Integration', () => {
  describe('GET /api/scores (list endpoint)', () => {
    beforeEach(() => {
      jest.clearAllMocks();
    });
    it('should return stocks with complete quality_inputs object structure', async () => {
      const response = await request(app)
        .get('/api/scores')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.stocks).toBeInstanceOf(Array);

      if (response.body.data.stocks.length > 0) {
        const stock = response.body.data.stocks[0];

        // Verify quality_inputs object structure
        expect(stock).toHaveProperty('quality_inputs');
        expect(stock.quality_inputs).toBeInstanceOf(Object);

        // Verify all required fields exist (may be null if no data)
        // These fields match the actual loader schema from loadqualitymetrics.py
        const requiredQualityFields = [
          'current_ratio',
          'debt_to_equity',
          'fcf_to_net_income',
          'profit_margin_pct',
          'return_on_equity_pct'
        ];

        requiredQualityFields.forEach(field => {
          expect(stock.quality_inputs).toHaveProperty(field);
        });
      }
    });

    it('should return stocks with complete growth_inputs object structure', async () => {
      const response = await request(app)
        .get('/api/scores')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.stocks).toBeInstanceOf(Array);

      if (response.body.data.stocks.length > 0) {
        const stock = response.body.data.stocks[0];

        // Verify growth_inputs object structure
        expect(stock).toHaveProperty('growth_inputs');
        expect(stock.growth_inputs).toBeInstanceOf(Object);

        // Verify all required fields exist (may be null if no data)
        const requiredGrowthFields = [
          'revenue_growth_3y_cagr',
          'eps_growth_3y_cagr',
          'operating_income_growth_yoy',
          'roe_trend',
          'sustainable_growth_rate',
          'fcf_growth_yoy',
          'net_income_growth_yoy',
          'gross_margin_trend',
          'operating_margin_trend',
          'net_margin_trend',
          'quarterly_growth_momentum',
          'asset_growth_yoy'
        ];

        requiredGrowthFields.forEach(field => {
          expect(stock.growth_inputs).toHaveProperty(field);
        });
      }
    });

    it('should validate quality metrics data types when present', async () => {
      const response = await request(app)
        .get('/api/scores')
        .expect(200);

      const stocksWithQualityData = response.body.data.stocks.filter(s =>
        s.quality_inputs?.current_ratio !== null
      );

      if (stocksWithQualityData.length > 0) {
        const stock = stocksWithQualityData[0];

        // Verify numeric types for quality metrics (actual fields from loader schema)
        if (stock.quality_inputs.current_ratio !== null) {
          expect(typeof stock.quality_inputs.current_ratio).toBe('number');
        }
        if (stock.quality_inputs.debt_to_equity !== null) {
          expect(typeof stock.quality_inputs.debt_to_equity).toBe('number');
        }
        if (stock.quality_inputs.fcf_to_net_income !== null) {
          expect(typeof stock.quality_inputs.fcf_to_net_income).toBe('number');
        }
        if (stock.quality_inputs.profit_margin_pct !== null) {
          expect(typeof stock.quality_inputs.profit_margin_pct).toBe('number');
        }
        if (stock.quality_inputs.return_on_equity_pct !== null) {
          expect(typeof stock.quality_inputs.return_on_equity_pct).toBe('number');
        }
      }
    });

    it('should validate growth metrics data types when present', async () => {
      const response = await request(app)
        .get('/api/scores')
        .expect(200);

      const stocksWithGrowthData = response.body.data.stocks.filter(s =>
        s.growth_inputs?.revenue_growth_3y_cagr !== null
      );

      if (stocksWithGrowthData.length > 0) {
        const stock = stocksWithGrowthData[0];

        // Verify numeric types for growth metrics
        if (stock.growth_inputs.revenue_growth_3y_cagr !== null) {
          expect(typeof stock.growth_inputs.revenue_growth_3y_cagr).toBe('number');
        }
        if (stock.growth_inputs.eps_growth_3y_cagr !== null) {
          expect(typeof stock.growth_inputs.eps_growth_3y_cagr).toBe('number');
        }
        if (stock.growth_inputs.operating_income_growth_yoy !== null) {
          expect(typeof stock.growth_inputs.operating_income_growth_yoy).toBe('number');
        }
        if (stock.growth_inputs.roe_trend !== null) {
          expect(typeof stock.growth_inputs.roe_trend).toBe('number');
        }
        if (stock.growth_inputs.sustainable_growth_rate !== null) {
          expect(typeof stock.growth_inputs.sustainable_growth_rate).toBe('number');
        }
        if (stock.growth_inputs.fcf_growth_yoy !== null) {
          expect(typeof stock.growth_inputs.fcf_growth_yoy).toBe('number');
        }
      }
    });
  });

  describe('GET /api/scores/:symbol (detail endpoint)', () => {
    it('should return nested quality inputs in factors.quality.inputs', async () => {
      const response = await request(app)
        .get('/api/scores/AAPL')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('factors');
      expect(response.body.data.factors).toHaveProperty('quality');
      expect(response.body.data.factors.quality).toHaveProperty('inputs');

      const inputs = response.body.data.factors.quality.inputs;

      // Verify structure (fields from loadqualitymetrics.py schema)
      const requiredFields = [
        'fcf_to_net_income',
        'debt_to_equity',
        'current_ratio',
        'return_on_equity_pct',
        'profit_margin_pct'
      ];

      requiredFields.forEach(field => {
        expect(inputs).toHaveProperty(field);
      });
    });

    it('should return nested growth inputs in factors.growth.inputs', async () => {
      const response = await request(app)
        .get('/api/scores/AAPL')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('factors');
      expect(response.body.data.factors).toHaveProperty('growth');
      expect(response.body.data.factors.growth).toHaveProperty('inputs');

      const inputs = response.body.data.factors.growth.inputs;

      // Verify structure (all 12 growth metrics)
      const requiredFields = [
        'revenue_growth_3y_cagr',
        'eps_growth_3y_cagr',
        'operating_income_growth_yoy',
        'roe_trend',
        'sustainable_growth_rate',
        'fcf_growth_yoy',
        'net_income_growth_yoy',
        'gross_margin_trend',
        'operating_margin_trend',
        'net_margin_trend',
        'quarterly_growth_momentum',
        'asset_growth_yoy'
      ];

      requiredFields.forEach(field => {
        expect(inputs).toHaveProperty(field);
      });
    });

    it('should include quality score alongside inputs', async () => {
      const response = await request(app)
        .get('/api/scores/AAPL')
        .expect(200);

      const quality = response.body.data.factors.quality;

      expect(quality).toHaveProperty('score');
      expect(quality).toHaveProperty('inputs');

      // Quality score should be a number
      expect(typeof quality.score).toBe('number');
    });

    it('should include growth score alongside inputs', async () => {
      const response = await request(app)
        .get('/api/scores/AAPL')
        .expect(200);

      const growth = response.body.data.factors.growth;

      expect(growth).toHaveProperty('score');
      expect(growth).toHaveProperty('inputs');

      // Growth score should be a number
      expect(typeof growth.score).toBe('number');
    });
  });

  describe('Quality Metrics Validation', () => {
    it('should have reasonable ranges for quality metrics when present', async () => {
      const response = await request(app)
        .get('/api/scores')
        .expect(200);

      const stocksWithQualityData = response.body.data.stocks.filter(s =>
        s.quality_inputs?.current_ratio !== null
      );

      if (stocksWithQualityData.length > 0) {
        const stock = stocksWithQualityData[0];

        // Current ratio should typically be positive
        if (stock.quality_inputs.current_ratio !== null) {
          expect(stock.quality_inputs.current_ratio).toBeGreaterThan(0);
        }

        // Profit margin should be a reasonable percentage (-100 to 100)
        if (stock.quality_inputs.profit_margin_pct !== null) {
          expect(stock.quality_inputs.profit_margin_pct).toBeGreaterThan(-100);
          expect(stock.quality_inputs.profit_margin_pct).toBeLessThan(100);
        }
      }
    });
  });

  describe('Growth Metrics Validation', () => {
    it('should have reasonable ranges for growth metrics when present', async () => {
      const response = await request(app)
        .get('/api/scores')
        .expect(200);

      const stocksWithGrowthData = response.body.data.stocks.filter(s =>
        s.growth_inputs?.revenue_growth_3y_cagr !== null
      );

      if (stocksWithGrowthData.length > 0) {
        const stock = stocksWithGrowthData[0];

        // Growth rates should be within reasonable ranges (-100% to 1000%)
        if (stock.growth_inputs.revenue_growth_3y_cagr !== null) {
          expect(stock.growth_inputs.revenue_growth_3y_cagr).toBeGreaterThan(-100);
          expect(stock.growth_inputs.revenue_growth_3y_cagr).toBeLessThan(1000);
        }

        if (stock.growth_inputs.eps_growth_3y_cagr !== null) {
          expect(stock.growth_inputs.eps_growth_3y_cagr).toBeGreaterThan(-100);
          expect(stock.growth_inputs.eps_growth_3y_cagr).toBeLessThan(1000);
        }
      }
    });
  });
});

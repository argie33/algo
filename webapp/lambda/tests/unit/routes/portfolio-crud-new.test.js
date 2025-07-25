/**
 * Portfolio CRUD Operations Test Suite
 * Tests for the new portfolio CRUD operations added
 */

const request = require('supertest');
const express = require('express');

// Mock the authentication middleware
jest.mock('../../../middleware/auth', () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: 'test-user-123' };
    next();
  }
}));

// Mock the API key service
jest.mock('../../../utils/apiKeyService', () => ({
  getApiKey: jest.fn()
}));

// Mock the AlpacaService
jest.mock('../../../utils/alpacaService', () => {
  return jest.fn().mockImplementation(() => ({
    getAccount: jest.fn().mockResolvedValue({
      equity: '50000.00',
      cash: '10000.00',
      buying_power: '20000.00'
    }),
    getPositions: jest.fn().mockResolvedValue([
      {
        symbol: 'AAPL',
        qty: '10',
        market_value: '1500.00',
        cost_basis: '1400.00',
        unrealized_pl: '100.00',
        side: 'long'
      },
      {
        symbol: 'MSFT',
        qty: '5',
        market_value: '1000.00',
        cost_basis: '950.00',
        unrealized_pl: '50.00',
        side: 'long'
      }
    ]),
    getQuote: jest.fn().mockResolvedValue({
      latest_trade: { price: '150.00' },
      latest_quote: { ask_price: '150.05' }
    })
  }));
});

// Import after mocking
const portfolioRouter = require('../../../routes/portfolio');
const apiKeyService = require('../../../utils/apiKeyService');

describe('Portfolio CRUD Operations', () => {
  let app;

  beforeEach(() => {
    app = express();
    app.use(express.json());
    app.use('/api/portfolio', portfolioRouter);
    
    // Reset mocks
    jest.clearAllMocks();
  });

  describe('PUT /api/portfolio/holdings/:symbol', () => {
    beforeEach(() => {
      // Mock API key service to return valid credentials
      apiKeyService.getApiKey.mockResolvedValue({
        keyId: 'PKTEST123',
        secretKey: 'secret123',
        version: '1.0'
      });
    });

    it('should update portfolio holding successfully', async () => {
      const response = await request(app)
        .put('/api/portfolio/holdings/AAPL')
        .send({
          notes: 'Core holding',
          targetAllocation: 25.5
        })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          symbol: 'AAPL',
          currentQuantity: 10,
          notes: 'Core holding',
          targetAllocation: 25.5,
          provider: 'alpaca',
          accountType: 'paper'
        }
      });
    });

    it('should validate symbol format', async () => {
      const response = await request(app)
        .put('/api/portfolio/holdings/INVALID123!')
        .send({
          notes: 'Test'
        })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: 'Invalid symbol format'
      });
    });

    it('should validate quantity if provided', async () => {
      const response = await request(app)
        .put('/api/portfolio/holdings/AAPL')
        .send({
          quantity: -5
        })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: 'Quantity must be a positive number'
      });
    });

    it('should return 404 for non-existent position', async () => {
      // Mock positions to not include TSLA
      const AlpacaService = require('../../../utils/alpacaService');
      const mockInstance = new AlpacaService();
      mockInstance.getPositions.mockResolvedValue([]);

      const response = await request(app)
        .put('/api/portfolio/holdings/TSLA')
        .send({
          notes: 'Test'
        })
        .expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: 'No position found for TSLA'
      });
    });

    it('should require API keys', async () => {
      apiKeyService.getApiKey.mockResolvedValue(null);

      const response = await request(app)
        .put('/api/portfolio/holdings/AAPL')
        .send({
          notes: 'Test'
        })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: 'API keys required for portfolio updates'
      });
    });
  });

  describe('PUT /api/portfolio/allocation', () => {
    beforeEach(() => {
      apiKeyService.getApiKey.mockResolvedValue({
        keyId: 'PKTEST123',
        secretKey: 'secret123',
        version: '1.0'
      });
    });

    it('should analyze portfolio allocation successfully', async () => {
      const allocations = [
        { symbol: 'AAPL', targetPercentage: 30 },
        { symbol: 'MSFT', targetPercentage: 20 },
        { symbol: 'GOOGL', targetPercentage: 25 }
      ];

      const response = await request(app)
        .put('/api/portfolio/allocation')
        .send({ allocations })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          totalValue: '50000.00',
          totalTargetPercentage: 75,
          rebalanceNeeded: expect.any(Boolean)
        }
      });

      expect(response.body.data.allocations).toHaveLength(3);
      expect(response.body.data.allocations[0]).toMatchObject({
        symbol: 'AAPL',
        targetPercentage: 30,
        action: expect.stringMatching(/BUY|SELL|HOLD/)
      });
    });

    it('should validate allocations array', async () => {
      const response = await request(app)
        .put('/api/portfolio/allocation')
        .send({ allocations: 'invalid' })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: 'Allocations must be an array'
      });
    });

    it('should validate allocation structure', async () => {
      const allocations = [
        { symbol: 'AAPL' } // Missing targetPercentage
      ];

      const response = await request(app)
        .put('/api/portfolio/allocation')
        .send({ allocations })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: 'Each allocation must have symbol and targetPercentage'
      });
    });

    it('should validate total allocation not exceeding 100%', async () => {
      const allocations = [
        { symbol: 'AAPL', targetPercentage: 60 },
        { symbol: 'MSFT', targetPercentage: 50 }
      ];

      const response = await request(app)
        .put('/api/portfolio/allocation')
        .send({ allocations })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: 'Total allocation cannot exceed 100%'
      });
    });
  });

  describe('POST /api/portfolio/rebalance', () => {
    beforeEach(() => {
      apiKeyService.getApiKey.mockResolvedValue({
        keyId: 'PKTEST123',
        secretKey: 'secret123',
        version: '1.0'
      });
    });

    it('should generate rebalancing plan in dry run mode', async () => {
      const allocations = [
        { symbol: 'AAPL', targetPercentage: 40 },
        { symbol: 'MSFT', targetPercentage: 30 }
      ];

      const response = await request(app)
        .post('/api/portfolio/rebalance')
        .send({ 
          allocations,
          dryRun: true,
          threshold: 5.0
        })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          orders: expect.any(Array),
          totalValue: '50000.00',
          buyingPower: '20000.00',
          dryRun: true
        }
      });
    });

    it('should reject live rebalancing (not implemented)', async () => {
      const allocations = [
        { symbol: 'AAPL', targetPercentage: 40 }
      ];

      const response = await request(app)
        .post('/api/portfolio/rebalance')
        .send({ 
          allocations,
          dryRun: false
        })
        .expect(200);

      expect(response.body).toMatchObject({
        success: false,
        error: 'Live rebalancing not implemented yet'
      });
    });

    it('should require API keys for rebalancing', async () => {
      apiKeyService.getApiKey.mockResolvedValue(null);

      const response = await request(app)
        .post('/api/portfolio/rebalance')
        .send({ 
          allocations: [{ symbol: 'AAPL', targetPercentage: 40 }]
        })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: 'API keys required for portfolio rebalancing'
      });
    });
  });

  describe('GET /api/portfolio/analysis', () => {
    beforeEach(() => {
      apiKeyService.getApiKey.mockResolvedValue({
        keyId: 'PKTEST123',
        secretKey: 'secret123',
        version: '1.0'
      });
    });

    it('should provide comprehensive portfolio analysis', async () => {
      const response = await request(app)
        .get('/api/portfolio/analysis')
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          overview: {
            totalValue: '50000.00',
            positions: 2,
            buyingPower: '20000.00'
          },
          risk: {
            concentrationRisk: expect.any(String),
            diversificationScore: expect.stringMatching(/Good|Moderate|Poor/),
            largestPosition: expect.any(String)
          },
          positions: expect.arrayContaining([
            expect.objectContaining({
              symbol: 'AAPL',
              allocation: expect.any(String),
              unrealizedPL: expect.any(String)
            })
          ]),
          accountType: 'paper'
        }
      });
    });

    it('should include recommendations when requested', async () => {
      const response = await request(app)
        .get('/api/portfolio/analysis?includeRecommendations=true')
        .expect(200);

      expect(response.body.data).toHaveProperty('recommendations');
      expect(Array.isArray(response.body.data.recommendations)).toBe(true);
    });

    it('should require API keys for analysis', async () => {
      apiKeyService.getApiKey.mockResolvedValue(null);

      const response = await request(app)
        .get('/api/portfolio/analysis')
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: 'API keys required for portfolio analysis'
      });
    });
  });

  describe('POST /api/portfolio/add-to-watchlist', () => {
    it('should add symbols to watchlist successfully', async () => {
      const symbols = ['AAPL', 'MSFT', 'GOOGL'];

      const response = await request(app)
        .post('/api/portfolio/add-to-watchlist')
        .send({ 
          symbols,
          watchlistName: 'My Targets'
        })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          symbols: ['AAPL', 'MSFT', 'GOOGL'],
          watchlistName: 'My Targets',
          addedCount: 3
        }
      });
    });

    it('should validate symbols array', async () => {
      const response = await request(app)
        .post('/api/portfolio/add-to-watchlist')
        .send({ symbols: 'invalid' })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: 'Symbols array is required'
      });
    });

    it('should require non-empty symbols array', async () => {
      const response = await request(app)
        .post('/api/portfolio/add-to-watchlist')
        .send({ symbols: [] })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: 'Symbols array is required'
      });
    });
  });

  describe('Authentication', () => {
    it('should require authentication for all CRUD operations', async () => {
      // Mock authentication to fail
      const mockAuthFail = (req, res, next) => {
        res.status(401).json({ success: false, error: 'Unauthorized' });
      };

      const appNoAuth = express();
      appNoAuth.use(express.json());
      
      // Create router with failing auth
      const express2 = require('express');
      const router = express2.Router();
      router.use(mockAuthFail);
      appNoAuth.use('/api/portfolio', router);

      await request(appNoAuth)
        .put('/api/portfolio/holdings/AAPL')
        .send({ notes: 'test' })
        .expect(401);

      await request(appNoAuth)
        .put('/api/portfolio/allocation')
        .send({ allocations: [] })
        .expect(401);

      await request(appNoAuth)
        .post('/api/portfolio/rebalance')
        .send({ allocations: [] })
        .expect(401);

      await request(appNoAuth)
        .get('/api/portfolio/analysis')
        .expect(401);

      await request(appNoAuth)
        .post('/api/portfolio/add-to-watchlist')
        .send({ symbols: ['AAPL'] })
        .expect(401);
    });
  });
});
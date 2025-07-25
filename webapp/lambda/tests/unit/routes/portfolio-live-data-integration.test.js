/**
 * Portfolio Live Data Integration Tests - HIGH PRIORITY #2
 * Tests what the Portfolio page actually does with API keys in production
 */
const request = require('supertest');
const jwt = require('jsonwebtoken');

// Mock dependencies
jest.mock('../../../utils/apiKeyService');
jest.mock('../../../utils/alpacaService');
jest.mock('../../../middleware/auth');

const mockApiKeyService = require('../../../utils/apiKeyService');
const MockAlpacaService = require('../../../utils/alpacaService');
const { authenticateToken } = require('../../../middleware/auth');

describe('Portfolio Live Data Integration', () => {
  let app;
  let mockAlpaca;

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Mock authentication
    authenticateToken.mockImplementation((req, res, next) => {
      req.user = { sub: 'test-user-123' };
      next();
    });

    // Mock Alpaca service
    mockAlpaca = {
      getAccount: jest.fn(),
      getPositions: jest.fn(),
      getBarsV2: jest.fn()
    };
    MockAlpacaService.mockReturnValue(mockAlpaca);

    app = require('../../../index');
  });

  describe('GET /api/portfolio - What Dashboard Actually Shows', () => {
    test('should fetch live account data from Alpaca when API keys exist', async () => {
      // Mock API key service to return Alpaca credentials
      mockApiKeyService.getApiKey.mockResolvedValue({
        keyId: 'PKTEST123456789',
        secretKey: 'test-secret-key-123',
        version: '2.0'
      });

      // Mock Alpaca account response (what Portfolio page actually displays)
      mockAlpaca.getAccount.mockResolvedValue({
        portfolioValue: 50000.00,
        equity: 48500.00,
        buyingPower: 25000.00,
        status: 'ACTIVE',
        daytradeCount: 2
      });

      const response = await request(app)
        .get('/api/portfolio')
        .expect(200);

      // Verify it calls API key service for user's Alpaca keys
      expect(mockApiKeyService.getApiKey).toHaveBeenCalledWith('test-user-123', 'alpaca');
      
      // Verify it creates Alpaca service with user's credentials
      expect(MockAlpacaService).toHaveBeenCalledWith({
        apiKey: 'PKTEST123456789',
        apiSecret: 'test-secret-key-123',
        isSandbox: false // v2.0 = live trading
      });

      // Verify it fetches live account data
      expect(mockAlpaca.getAccount).toHaveBeenCalled();

      // Verify response contains live data (what Dashboard shows)
      expect(response.body.data.summary).toMatchObject({
        total_market_value: 50000.00,
        total_equity: 48500.00
      });

      expect(response.body.data.metadata).toMatchObject({
        account_type: 'live',
        last_sync: expect.any(String)
      });
    });

    test('should show default values when no API keys configured', async () => {
      // Mock no API keys found
      mockApiKeyService.getApiKey.mockResolvedValue(null);

      const response = await request(app)
        .get('/api/portfolio')
        .expect(200);

      // Should not call Alpaca service
      expect(MockAlpacaService).not.toHaveBeenCalled();
      expect(mockAlpaca.getAccount).not.toHaveBeenCalled();

      // Should return default portfolio values
      expect(response.body.data.summary.total_market_value).toBe(0);
      expect(response.body.data.metadata.account_type).toBe('demo');
    });

    test('should handle Alpaca API failures gracefully', async () => {
      mockApiKeyService.getApiKey.mockResolvedValue({
        keyId: 'PKTEST123456789',
        secretKey: 'test-secret-key-123'
      });

      // Mock Alpaca API failure
      mockAlpaca.getAccount.mockRejectedValue(new Error('Alpaca API unavailable'));

      const response = await request(app)
        .get('/api/portfolio')
        .expect(200);

      // Should still return successful response with fallback data
      expect(response.body.success).toBe(true);
      expect(response.body.data.summary.total_market_value).toBe(0);
      expect(response.body.data.metadata.data_source).toBe('database_fallback');
    });
  });

  describe('GET /api/portfolio/positions - What Portfolio Page Shows', () => {
    test('should fetch live positions from Alpaca', async () => {
      mockApiKeyService.getApiKey.mockResolvedValue({
        keyId: 'PKTEST123456789',
        secretKey: 'test-secret-key-123'
      });

      // Mock Alpaca positions (what Portfolio holdings table shows)
      mockAlpaca.getPositions.mockResolvedValue([
        {
          symbol: 'AAPL',
          qty: 10,
          market_value: 1500.00,
          avg_entry_price: 145.00,
          unrealized_pl: 50.00,
          side: 'long'
        },
        {
          symbol: 'GOOGL',
          qty: 5,
          market_value: 2500.00,
          avg_entry_price: 490.00,
          unrealized_pl: -50.00,
          side: 'long'
        }
      ]);

      const response = await request(app)
        .get('/api/portfolio/positions')
        .expect(200);

      expect(mockAlpaca.getPositions).toHaveBeenCalled();
      
      // Verify response matches what Portfolio table displays
      expect(response.body.data.positions).toHaveLength(2);
      expect(response.body.data.positions[0]).toMatchObject({
        symbol: 'AAPL',
        quantity: 10,
        market_value: 1500.00,
        unrealized_pnl: 50.00
      });
    });
  });

  describe('POST /api/portfolio/import - Import from Broker', () => {
    test('should import portfolio data from Alpaca broker', async () => {
      mockApiKeyService.getApiKey.mockResolvedValue({
        keyId: 'PKTEST123456789',
        secretKey: 'test-secret-key-123'
      });

      mockAlpaca.getPositions.mockResolvedValue([
        {
          symbol: 'TSLA',
          qty: 15,
          market_value: 3000.00,
          avg_entry_price: 195.00,
          side: 'long'
        }
      ]);

      const response = await request(app)
        .post('/api/portfolio/import')
        .send({ source: 'alpaca' })
        .expect(200);

      expect(mockAlpaca.getPositions).toHaveBeenCalled();
      expect(response.body.data.imported_positions).toHaveLength(1);
      expect(response.body.data.imported_positions[0].symbol).toBe('TSLA');
    });

    test('should require API keys for portfolio import', async () => {
      mockApiKeyService.getApiKey.mockResolvedValue(null);

      const response = await request(app)
        .post('/api/portfolio/import')
        .send({ source: 'alpaca' })
        .expect(400);

      expect(response.body.error).toContain('API keys required');
      expect(mockAlpaca.getPositions).not.toHaveBeenCalled();
    });
  });

  describe('Sandbox vs Live Trading Detection', () => {
    test('should use sandbox mode for v1.0 API keys', async () => {
      mockApiKeyService.getApiKey.mockResolvedValue({
        keyId: 'PKTEST123456789',
        secretKey: 'test-secret-key-123',
        version: '1.0' // v1.0 = sandbox
      });

      await request(app).get('/api/portfolio');

      expect(MockAlpacaService).toHaveBeenCalledWith({
        apiKey: 'PKTEST123456789',
        apiSecret: 'test-secret-key-123',
        isSandbox: true // Should detect sandbox mode
      });
    });

    test('should use live mode for v2.0 API keys', async () => {
      mockApiKeyService.getApiKey.mockResolvedValue({
        keyId: 'PKREAL987654321',
        secretKey: 'real-secret-key-456',
        version: '2.0' // v2.0 = live trading
      });

      await request(app).get('/api/portfolio');

      expect(MockAlpacaService).toHaveBeenCalledWith({
        apiKey: 'PKREAL987654321',
        apiSecret: 'real-secret-key-456',
        isSandbox: false // Should detect live mode
      });
    });
  });
});
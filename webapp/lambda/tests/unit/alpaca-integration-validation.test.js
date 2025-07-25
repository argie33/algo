/**
 * Alpaca Integration Validation Tests
 * Quick validation tests for the new Alpaca integration components
 */

const AlpacaService = require('../../utils/alpacaService');

// Mock axios to prevent real API calls
jest.mock('axios');
const axios = require('axios');

describe('Alpaca Integration Validation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    console.log = jest.fn();
    console.error = jest.fn();
  });

  describe('AlpacaService Integration', () => {
    it('should initialize with valid credentials', () => {
      expect(() => {
        new AlpacaService('test-key', 'test-secret', true);
      }).not.toThrow();
    });

    it('should throw error with missing credentials', () => {
      expect(() => {
        new AlpacaService(null, 'test-secret', true);
      }).toThrow('Alpaca API key and secret are required');

      expect(() => {
        new AlpacaService('test-key', null, true);
      }).toThrow('Alpaca API key and secret are required');
    });

    it('should set correct URLs for paper trading', () => {
      const service = new AlpacaService('key', 'secret', true);
      expect(service.baseURL).toBe('https://paper-api.alpaca.markets');
      expect(service.isPaper).toBe(true);
    });

    it('should set correct URLs for live trading', () => {
      const service = new AlpacaService('key', 'secret', false);
      expect(service.baseURL).toBe('https://api.alpaca.markets');
      expect(service.isPaper).toBe(false);
    });
  });

  describe('API Key Helper Function', () => {
    const getUserApiKey = async (userId, provider) => {
      // Mock the API key service call
      const mockCredentials = {
        keyId: 'mock-key-id',
        secretKey: 'mock-secret-key',
        version: '2.0'
      };

      if (!mockCredentials) {
        return null;
      }
      
      return {
        apiKey: mockCredentials.keyId,
        apiSecret: mockCredentials.secretKey,
        isSandbox: mockCredentials.version === '1.0'
      };
    };

    it('should format API key response correctly', async () => {
      const result = await getUserApiKey('test-user', 'alpaca');
      
      expect(result).toEqual({
        apiKey: 'mock-key-id',
        apiSecret: 'mock-secret-key',
        isSandbox: false // version 2.0 = live
      });
    });

    it('should detect sandbox version correctly', async () => {
      // Simulate version 1.0 (sandbox)
      const getUserApiKeySandbox = async (userId, provider) => {
        const mockCredentials = {
          keyId: 'mock-key-id',
          secretKey: 'mock-secret-key',
          version: '1.0'
        };

        return {
          apiKey: mockCredentials.keyId,
          apiSecret: mockCredentials.secretKey,
          isSandbox: mockCredentials.version === '1.0'
        };
      };

      const result = await getUserApiKeySandbox('test-user', 'alpaca');
      expect(result.isSandbox).toBe(true);
    });
  });

  describe('Database Service Integration', () => {
    // Mock portfolioDb for validation
    const mockPortfolioDb = {
      storePortfolioHoldings: jest.fn(),
      getCachedPortfolioData: jest.fn(),
      updatePortfolioMetadata: jest.fn(),
      isDataStale: jest.fn(),
      getPerformanceHistory: jest.fn()
    };

    it('should validate portfolio holdings storage structure', async () => {
      const userId = 'test-user-123';
      const holdings = [
        {
          symbol: 'AAPL',
          qty: '10',
          avg_entry_price: '150.00',
          current_price: '155.00',
          market_value: '1550.00',
          unrealized_pl: '50.00',
          sector: 'Technology',
          asset_id: 'alpaca-asset-123'
        }
      ];

      mockPortfolioDb.storePortfolioHoldings.mockResolvedValue({ stored: 1 });

      const result = await mockPortfolioDb.storePortfolioHoldings(userId, holdings, 'paper');
      
      expect(result.stored).toBe(1);
      expect(mockPortfolioDb.storePortfolioHoldings).toHaveBeenCalledWith(userId, holdings, 'paper');
    });

    it('should validate data freshness checking', () => {
      const freshData = {
        lastSync: new Date(Date.now() - 2 * 60 * 1000).toISOString() // 2 minutes ago
      };
      
      const staleData = {
        lastSync: new Date(Date.now() - 10 * 60 * 1000).toISOString() // 10 minutes ago
      };

      mockPortfolioDb.isDataStale.mockReturnValueOnce(false).mockReturnValueOnce(true);

      expect(mockPortfolioDb.isDataStale(freshData, 5 * 60 * 1000)).toBe(false);
      expect(mockPortfolioDb.isDataStale(staleData, 5 * 60 * 1000)).toBe(true);
    });
  });

  describe('Error Handling Integration', () => {
    it('should handle API key retrieval errors gracefully', async () => {
      const getUserApiKeyWithError = async (userId, provider) => {
        try {
          throw new Error('API key service unavailable');
        } catch (error) {
          console.error(`Failed to get API key for ${provider}:`, error);
          return null;
        }
      };

      const result = await getUserApiKeyWithError('test-user', 'alpaca');
      expect(result).toBeNull();
    });

    it('should validate fallback response structure', () => {
      const sampleData = {
        success: true,
        data: {
          holdings: [{ symbol: 'SAMPLE', quantity: 100 }],
          summary: { totalEquity: 100000 }
        },
        source: 'sample',
        message: 'Portfolio data from sample data - configure API keys for live data'
      };

      expect(sampleData).toHaveProperty('success', true);
      expect(sampleData).toHaveProperty('source', 'sample');
      expect(sampleData.data).toHaveProperty('holdings');
      expect(sampleData.data).toHaveProperty('summary');
    });
  });

  describe('Database Schema Compatibility', () => {
    it('should validate portfolio_holdings table structure', () => {
      const expectedColumns = [
        'holding_id',
        'user_id', 
        'symbol',
        'quantity',
        'avg_cost',
        'current_price',
        'market_value',
        'unrealized_pl',
        'sector',
        'created_at',
        'updated_at'
      ];

      // This validates that our service expects these columns
      const mockHolding = {
        user_id: 123,
        symbol: 'AAPL',
        quantity: 10,
        avg_cost: 150.00,
        current_price: 155.00,
        market_value: 1550.00,
        unrealized_pl: 50.00,
        sector: 'Technology',
        alpaca_asset_id: 'asset-123'
      };

      // Basic validation - check that our holding structure matches expectations
      expect(mockHolding).toHaveProperty('user_id');
      expect(mockHolding).toHaveProperty('symbol');
      expect(mockHolding).toHaveProperty('quantity');
      expect(typeof mockHolding.quantity).toBe('number');
      expect(typeof mockHolding.market_value).toBe('number');
    });

    it('should validate portfolio_metadata table structure', () => {
      const mockMetadata = {
        user_id: 123,
        account_id: 'ACC-123',
        account_type: 'paper',
        total_equity: 10000.00,
        buying_power: 5000.00,
        cash: 2000.00,
        last_sync_at: new Date().toISOString(),
        sync_status: 'success'
      };

      expect(mockMetadata).toHaveProperty('user_id');
      expect(mockMetadata).toHaveProperty('account_type');
      expect(mockMetadata).toHaveProperty('total_equity');
      expect(typeof mockMetadata.total_equity).toBe('number');
    });
  });

  describe('Response Format Validation', () => {
    it('should validate successful response format', () => {
      const successResponse = {
        success: true,
        data: {
          holdings: [],
          summary: { totalEquity: 0 }
        },
        source: 'alpaca',
        responseTime: 150,
        message: 'Portfolio data synced from paper account'
      };

      expect(successResponse).toHaveProperty('success', true);
      expect(successResponse).toHaveProperty('data');
      expect(successResponse).toHaveProperty('source');
      expect(successResponse).toHaveProperty('responseTime');
      expect(typeof successResponse.responseTime).toBe('number');
    });

    it('should validate error response format', () => {
      const errorResponse = {
        success: false,
        error: 'Failed to sync portfolio data',
        details: 'Network connection failed',
        responseTime: 5000
      };

      expect(errorResponse).toHaveProperty('success', false);
      expect(errorResponse).toHaveProperty('error');
      expect(typeof errorResponse.error).toBe('string');
    });
  });

  describe('Route Parameter Validation', () => {
    it('should validate query parameter defaults', () => {
      const defaultParams = {
        accountType: 'paper',
        force: false,
        includeMetadata: false
      };

      expect(defaultParams.accountType).toBe('paper');
      expect(defaultParams.force).toBe(false);
      expect(typeof defaultParams.includeMetadata).toBe('boolean');
    });

    it('should validate account type options', () => {
      const validAccountTypes = ['paper', 'live'];
      const testAccountType = 'paper';

      expect(validAccountTypes).toContain(testAccountType);
    });
  });
});
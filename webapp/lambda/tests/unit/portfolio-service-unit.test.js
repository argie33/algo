/**
 * Portfolio Service Pure Unit Tests
 * Tests portfolio service without external dependencies (no database, no API calls)
 */

// Mock all external dependencies
jest.mock('../../utils/database', () => ({
  query: jest.fn(),
  transaction: jest.fn(),
  healthCheck: jest.fn()
}));

jest.mock('../../utils/logger', () => ({
  info: jest.fn(),
  error: jest.fn(),
  warn: jest.fn(),
  debug: jest.fn()
}));

// Create mock AlpacaService constructor
const mockGetPositions = jest.fn().mockResolvedValue([]);
const mockGetAccount = jest.fn().mockResolvedValue({
  account_number: 'TEST123',
  account_type: 'margin',
  equity: 50000.00,
  buying_power: 25000.00,
  cash: 5000.00,
  daytrade_count: 2
});

jest.mock('../../utils/alpacaService', () => {
  return jest.fn().mockImplementation((apiKey, apiSecret, isPaper) => ({
    getPositions: mockGetPositions,
    getAccount: mockGetAccount
  }));
});

jest.mock('../../utils/portfolioSyncService', () => ({}));

const { query, transaction, healthCheck } = require('../../utils/database');
const logger = require('../../utils/logger');

// Import portfolio service after mocking dependencies
const portfolioService = require('../../services/portfolioService');

describe('Portfolio Service Pure Unit Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetPositions.mockClear();
    mockGetAccount.mockClear();
  });

  describe('Service Initialization', () => {
    test('should initialize without AlpacaService API keys', () => {
      // This test verifies that the service can be instantiated without API keys
      expect(portfolioService).toBeDefined();
      expect(portfolioService.alpacaService).toBeNull();
    });

    test('should initialize AlpacaService on demand', () => {
      const alpacaService = portfolioService.getAlpacaService('test-key', 'test-secret', true);
      expect(alpacaService).toBeDefined();
    });

    test('should not initialize AlpacaService without API keys', () => {
      // Call getAlpacaService without arguments (undefined keys)
      const alpacaService = portfolioService.getAlpacaService(undefined, undefined);
      expect(alpacaService).toBeNull();
    });
  });

  describe('Database Operations (Mocked)', () => {
    test('should retrieve user portfolio with mocked database', async () => {
      // Mock database response
      query.mockResolvedValueOnce({
        rows: [
          {
            symbol: 'AAPL',
            quantity: '100',
            avg_cost: '150.00',
            current_price: '155.00',
            market_value: '15500.00',
            unrealized_pl: '500.00',
            sector: 'Technology',
            created_at: new Date(),
            updated_at: new Date()
          }
        ]
      });

      query.mockResolvedValueOnce({
        rows: [
          {
            account_id: 'TEST123',
            account_type: 'margin',
            total_equity: '50000.00',
            buying_power: '25000.00',
            cash: '5000.00',
            day_trade_count: '2',
            last_sync_at: new Date(),
            sync_status: 'synced',
            created_at: new Date(),
            updated_at: new Date()
          }
        ]
      });

      const portfolio = await portfolioService.getUserPortfolio('test-user-123');
      
      expect(portfolio).toBeDefined();
      expect(portfolio.userId).toBe('test-user-123');
      expect(portfolio.holdings).toHaveLength(1);
      expect(portfolio.holdings[0].symbol).toBe('AAPL');
      expect(portfolio.summary.totalPositions).toBe(1);
      expect(portfolio.summary.totalMarketValue).toBe(15500);
      expect(logger.info).toHaveBeenCalledWith('Retrieving portfolio for user test-user-123');
    });

    test('should update portfolio holdings with mocked database', async () => {
      const mockTransaction = jest.fn().mockImplementation(async (callback) => {
        const mockClient = {
          query: jest.fn().mockResolvedValue({ rows: [] })
        };
        return await callback(mockClient);
      });

      transaction.mockImplementation(mockTransaction);

      const holdings = [
        {
          symbol: 'AAPL',
          quantity: 100,
          avgCost: 150.00,
          currentPrice: 155.00,
          marketValue: 15500.00,
          unrealizedPL: 500.00,
          sector: 'Technology'
        }
      ];

      const result = await portfolioService.updatePortfolioHoldings('test-user-123', holdings);
      
      expect(result.success).toBe(true);
      expect(result.updatedPositions).toBe(1);
      expect(transaction).toHaveBeenCalled();
      expect(logger.info).toHaveBeenCalledWith('Updating portfolio holdings for user test-user-123: 1 positions');
    });

    test('should save portfolio metadata with mocked database', async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const metadata = {
        accountId: 'TEST123456',
        accountType: 'margin',
        totalEquity: 50000.00,
        buyingPower: 25000.00,
        cash: 5000.00,
        dayTradeCount: 2
      };

      const result = await portfolioService.savePortfolioMetadata('test-user-123', metadata);
      
      expect(result.success).toBe(true);
      expect(query).toHaveBeenCalled();
      expect(logger.info).toHaveBeenCalledWith('Saving portfolio metadata for user test-user-123');
    });

    test('should return health check status', async () => {
      healthCheck.mockResolvedValueOnce({
        status: 'connected',
        database: 'financial_platform_test'
      });

      const health = await portfolioService.healthCheck();
      
      expect(health.status).toBe('healthy');
      expect(health.service).toBe('portfolio');
      expect(health.database).toBeDefined();
      expect(health.timestamp).toBeDefined();
    });
  });

  describe('AlpacaService Integration', () => {
    test('should sync portfolio from broker with valid API keys', async () => {
      // Mock transaction for database operations
      const mockTransaction = jest.fn().mockImplementation(async (callback) => {
        const mockClient = {
          query: jest.fn().mockResolvedValue({ rows: [] })
        };
        return await callback(mockClient);
      });

      transaction.mockImplementation(mockTransaction);
      query.mockResolvedValue({ rows: [] });

      const brokerApiKeys = {
        key: 'test-key',
        secret: 'test-secret',
        isPaper: true
      };

      const result = await portfolioService.syncPortfolioFromBroker('test-user-123', brokerApiKeys);
      
      expect(result.success).toBe(true);
      expect(result.source).toBe('alpaca');
      expect(logger.info).toHaveBeenCalledWith('Syncing portfolio from broker for user test-user-123');
    });

    test('should fail to sync portfolio without API keys', async () => {
      const brokerApiKeys = { key: undefined, secret: undefined };

      await expect(portfolioService.syncPortfolioFromBroker('test-user-123', brokerApiKeys))
        .rejects.toThrow('Failed to initialize Alpaca service with provided API keys');
    });
  });

  describe('Error Handling', () => {
    test('should handle database errors gracefully', async () => {
      query.mockRejectedValueOnce(new Error('Database connection failed'));

      await expect(portfolioService.getUserPortfolio('test-user-123'))
        .rejects.toThrow('Failed to retrieve portfolio: Database connection failed');
      
      expect(logger.error).toHaveBeenCalledWith('Error retrieving user portfolio:', expect.any(Object));
    });

    test('should handle transaction errors gracefully', async () => {
      transaction.mockRejectedValueOnce(new Error('Transaction failed'));

      const holdings = [
        {
          symbol: 'AAPL',
          quantity: 100,
          avgCost: 150.00,
          currentPrice: 155.00,
          marketValue: 15500.00,
          unrealizedPL: 500.00,
          sector: 'Technology'
        }
      ];

      await expect(portfolioService.updatePortfolioHoldings('test-user-123', holdings))
        .rejects.toThrow('Failed to update portfolio holdings: Transaction failed');
      
      expect(logger.error).toHaveBeenCalledWith('Error updating portfolio holdings:', expect.any(Object));
    });
  });
});
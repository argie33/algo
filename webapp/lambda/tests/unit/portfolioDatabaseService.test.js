/**
 * Unit Tests for Portfolio Database Service
 * Tests core database operations for portfolio data storage and retrieval
 */

const PortfolioDatabaseService = require('../../utils/portfolioDatabaseService');

// Mock database module
jest.mock('../../utils/database', () => ({
  query: jest.fn(),
  transaction: jest.fn()
}));

const { query, transaction } = require('../../utils/database');

describe('PortfolioDatabaseService', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    console.log = jest.fn(); // Mock console.log
    console.error = jest.fn(); // Mock console.error
  });

  describe('storePortfolioHoldings', () => {
    it('should store portfolio holdings successfully', async () => {
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
        },
        {
          symbol: 'TSLA',
          qty: '5',
          avg_entry_price: '200.00',
          current_price: '210.00',
          market_value: '1050.00', 
          unrealized_pl: '50.00',
          sector: 'Automotive',
          asset_id: 'alpaca-asset-456'
        }
      ];

      transaction.mockResolvedValue([
        { rowCount: 1 },
        { rowCount: 1 }
      ]);

      const result = await PortfolioDatabaseService.storePortfolioHoldings(userId, holdings, 'paper');

      expect(result.stored).toBe(2);
      expect(transaction).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            text: expect.stringContaining('INSERT INTO portfolio_holdings'),
            values: expect.arrayContaining([userId, 'AAPL'])
          }),
          expect.objectContaining({
            text: expect.stringContaining('INSERT INTO portfolio_holdings'),
            values: expect.arrayContaining([userId, 'TSLA'])
          })
        ])
      );
    });

    it('should handle empty holdings array', async () => {
      const userId = 'test-user-123';
      const holdings = [];

      const result = await PortfolioDatabaseService.storePortfolioHoldings(userId, holdings, 'paper');

      expect(result.stored).toBe(0);
      expect(transaction).not.toHaveBeenCalled();
    });

    it('should handle null holdings', async () => {
      const userId = 'test-user-123';
      const holdings = null;

      const result = await PortfolioDatabaseService.storePortfolioHoldings(userId, holdings, 'paper');

      expect(result.stored).toBe(0);
      expect(transaction).not.toHaveBeenCalled();
    });

    it('should handle database errors', async () => {
      const userId = 'test-user-123';
      const holdings = [{ symbol: 'AAPL', qty: '10' }];

      transaction.mockRejectedValue(new Error('Database connection failed'));

      await expect(
        PortfolioDatabaseService.storePortfolioHoldings(userId, holdings, 'paper')
      ).rejects.toThrow('Failed to store portfolio holdings: Database connection failed');
    });
  });

  describe('getCachedPortfolioData', () => {
    it('should retrieve cached portfolio data successfully', async () => {
      const userId = 'test-user-123';
      const mockRows = [
        {
          symbol: 'AAPL',
          quantity: '10',
          avg_cost: '150.00',
          current_price: '155.00',
          market_value: '1550.00',
          unrealized_pl: '50.00',
          sector: 'Technology',
          alpaca_asset_id: 'asset-123',
          updated_at: '2023-01-01T12:00:00Z',
          total_equity: '10000.00',
          buying_power: '5000.00',
          cash: '2000.00',
          last_sync_at: '2023-01-01T12:00:00Z',
          account_type: 'paper',
          account_id: 'account-123'
        }
      ];

      query.mockResolvedValue({ rows: mockRows });

      const result = await PortfolioDatabaseService.getCachedPortfolioData(userId, 'paper');

      expect(result).toEqual({
        holdings: [
          {
            symbol: 'AAPL',
            quantity: 10,
            avgCost: 150,
            currentPrice: 155,
            marketValue: 1550,
            unrealizedPL: 50,
            sector: 'Technology',
            lastUpdated: '2023-01-01T12:00:00Z',
            alpacaAssetId: 'asset-123'
          }
        ],
        summary: {
          totalEquity: 10000,
          buyingPower: 5000,
          cash: 2000,
          accountType: 'paper',
          accountId: 'account-123',
          totalValue: 1550,
          totalPL: 50,
          positionCount: 1
        },
        lastSync: '2023-01-01T12:00:00Z',
        dataSource: 'database'
      });

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('SELECT'),
        [userId]
      );
    });

    it('should return null for empty results', async () => {
      const userId = 'test-user-123';
      query.mockResolvedValue({ rows: [] });

      const result = await PortfolioDatabaseService.getCachedPortfolioData(userId, 'paper');

      expect(result).toBeNull();
    });

    it('should handle database errors', async () => {
      const userId = 'test-user-123';
      query.mockRejectedValue(new Error('Database query failed'));

      await expect(
        PortfolioDatabaseService.getCachedPortfolioData(userId, 'paper')
      ).rejects.toThrow('Failed to get cached portfolio data: Database query failed');
    });
  });

  describe('updatePortfolioMetadata', () => {
    it('should update portfolio metadata successfully', async () => {
      const userId = 'test-user-123';
      const accountData = {
        account_number: 'ACC123',
        id: 'ACC123',
        equity: '10000.00',
        buying_power: '5000.00',
        cash: '2000.00'
      };
      const accountType = 'paper';

      const mockResult = {
        rows: [{
          user_id: userId,
          account_id: 'ACC123',
          total_equity: '10000.00'
        }]
      };

      query.mockResolvedValue(mockResult);

      const result = await PortfolioDatabaseService.updatePortfolioMetadata(userId, accountData, accountType);

      expect(result).toEqual(mockResult.rows[0]);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO portfolio_metadata'),
        expect.arrayContaining([userId, 'ACC123', accountType])
      );
    });

    it('should handle database errors', async () => {
      const userId = 'test-user-123';
      const accountData = { equity: '10000.00' };
      const accountType = 'paper';

      query.mockRejectedValue(new Error('Database update failed'));

      await expect(
        PortfolioDatabaseService.updatePortfolioMetadata(userId, accountData, accountType)
      ).rejects.toThrow('Failed to update portfolio metadata: Database update failed');
    });
  });

  describe('isDataStale', () => {
    it('should return true for null data', () => {
      const result = PortfolioDatabaseService.isDataStale(null);
      expect(result).toBe(true);
    });

    it('should return true for data without lastSync', () => {
      const data = { holdings: [] };
      const result = PortfolioDatabaseService.isDataStale(data);
      expect(result).toBe(true);
    });

    it('should return true for stale data', () => {
      const data = {
        lastSync: new Date(Date.now() - 10 * 60 * 1000).toISOString() // 10 minutes ago
      };
      const maxAge = 5 * 60 * 1000; // 5 minutes
      
      const result = PortfolioDatabaseService.isDataStale(data, maxAge);
      expect(result).toBe(true);
    });

    it('should return false for fresh data', () => {
      const data = {
        lastSync: new Date(Date.now() - 2 * 60 * 1000).toISOString() // 2 minutes ago
      };
      const maxAge = 5 * 60 * 1000; // 5 minutes
      
      const result = PortfolioDatabaseService.isDataStale(data, maxAge);
      expect(result).toBe(false);
    });
  });

  describe('getPerformanceHistory', () => {
    it('should retrieve performance history successfully', async () => {
      const userId = 'test-user-123';
      const days = 30;
      
      const mockRows = [
        {
          date: '2023-01-01',
          total_value: '10000.00',
          total_cost: '9500.00',
          unrealized_pl: '500.00',
          realized_pl: '100.00',
          cash_value: '2000.00',
          position_count: 5
        }
      ];

      query.mockResolvedValue({ rows: mockRows });

      const result = await PortfolioDatabaseService.getPerformanceHistory(userId, days);

      expect(result).toEqual([
        {
          date: '2023-01-01',
          totalValue: 10000,
          totalCost: 9500,
          unrealizedPL: 500,
          realizedPL: 100,
          cashValue: 2000,
          positionCount: 5
        }
      ]);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('SELECT * FROM portfolio_performance_history'),
        [userId]
      );
    });

    it('should handle database errors', async () => {
      const userId = 'test-user-123';
      query.mockRejectedValue(new Error('Database query failed'));

      await expect(
        PortfolioDatabaseService.getPerformanceHistory(userId, 30)
      ).rejects.toThrow('Failed to get performance history: Database query failed');
    });
  });

  describe('storePerformanceSnapshot', () => {
    it('should store performance snapshot successfully', async () => {
      const userId = 'test-user-123';
      const performanceData = {
        totalValue: '10000.00',
        totalCost: '9500.00',
        unrealizedPL: '500.00',
        realizedPL: '100.00',
        cashValue: '2000.00',
        positionCount: '5'
      };

      query.mockResolvedValue({ rowCount: 1 });

      const result = await PortfolioDatabaseService.storePerformanceSnapshot(userId, performanceData);

      expect(result).toBe(1);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('INSERT INTO portfolio_performance_history'),
        expect.arrayContaining([userId, 10000, 9500, 500, 100, 2000, 5])
      );
    });

    it('should handle database errors', async () => {
      const userId = 'test-user-123';
      const performanceData = { totalValue: '10000.00' };

      query.mockRejectedValue(new Error('Database insert failed'));

      await expect(
        PortfolioDatabaseService.storePerformanceSnapshot(userId, performanceData)
      ).rejects.toThrow('Failed to store performance snapshot: Database insert failed');
    });
  });

  describe('cleanupOldData', () => {
    it('should cleanup old data successfully', async () => {
      const userId = 'test-user-123';
      const daysToKeep = 30;

      query.mockResolvedValue({ rowCount: 5 });

      const result = await PortfolioDatabaseService.cleanupOldData(userId, daysToKeep);

      expect(result).toBe(5);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining('DELETE FROM portfolio_performance_history'),
        [userId]
      );
    });

    it('should handle database errors', async () => {
      const userId = 'test-user-123';
      query.mockRejectedValue(new Error('Database cleanup failed'));

      await expect(
        PortfolioDatabaseService.cleanupOldData(userId, 30)
      ).rejects.toThrow('Failed to cleanup old data: Database cleanup failed');
    });
  });

  describe('formatPortfolioResponse', () => {
    it('should format empty response correctly', () => {
      const result = PortfolioDatabaseService.formatPortfolioResponse([]);
      expect(result).toBeNull();
    });

    it('should format portfolio response correctly', () => {
      const rows = [
        {
          symbol: 'AAPL',
          quantity: '10',
          avg_cost: '150.00',
          current_price: '155.00',
          market_value: '1550.00',
          unrealized_pl: '50.00',
          sector: 'Technology',
          updated_at: '2023-01-01T12:00:00Z',
          alpaca_asset_id: 'asset-123',
          total_equity: '10000.00',
          buying_power: '5000.00',
          cash: '2000.00',
          account_type: 'paper',
          account_id: 'account-123',
          last_sync_at: '2023-01-01T12:00:00Z'
        }
      ];

      const result = PortfolioDatabaseService.formatPortfolioResponse(rows);

      expect(result).toEqual({
        holdings: [
          {
            symbol: 'AAPL',
            quantity: 10,
            avgCost: 150,
            currentPrice: 155,
            marketValue: 1550,
            unrealizedPL: 50,
            sector: 'Technology',
            lastUpdated: '2023-01-01T12:00:00Z',
            alpacaAssetId: 'asset-123'
          }
        ],
        summary: {
          totalEquity: 10000,
          buyingPower: 5000,
          cash: 2000,
          accountType: 'paper',
          accountId: 'account-123',
          totalValue: 1550,
          totalPL: 50,
          positionCount: 1
        },
        lastSync: '2023-01-01T12:00:00Z',
        dataSource: 'database'
      });
    });

    it('should handle rows without symbols (metadata-only)', () => {
      const rows = [
        {
          symbol: null,
          total_equity: '10000.00',
          buying_power: '5000.00',
          cash: '2000.00',
          account_type: 'paper',
          account_id: 'account-123',
          last_sync_at: '2023-01-01T12:00:00Z'
        }
      ];

      const result = PortfolioDatabaseService.formatPortfolioResponse(rows);

      expect(result.holdings).toEqual([]);
      expect(result.summary.totalEquity).toBe(10000);
    });
  });
});
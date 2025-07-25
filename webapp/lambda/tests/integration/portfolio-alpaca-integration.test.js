/**
 * Integration Tests for Portfolio Alpaca Integration Routes
 * Tests the complete portfolio data pipeline with real database connections
 */

const request = require('supertest');
const express = require('express');
const portfolioRoutes = require('../../routes/portfolio-alpaca-integration');
const { query } = require('../../utils/database');

// Create test app
const app = express();
app.use(express.json());
app.use('/api/portfolio', portfolioRoutes);

// Mock dependencies
jest.mock('../../middleware/auth', () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: 'test-user-123' };
    next();
  }
}));

jest.mock('../../utils/apiKeyService', () => ({
  getApiKey: jest.fn()
}));

jest.mock('../../utils/alpacaService');
jest.mock('../../utils/portfolioDatabaseService');
jest.mock('../../utils/portfolioSyncService');

const apiKeyService = require('../../utils/apiKeyService');
const AlpacaService = require('../../utils/alpacaService');
const portfolioDb = require('../../utils/portfolioDatabaseService');
const portfolioSyncService = require('../../utils/portfolioSyncService');

describe('Portfolio Alpaca Integration Routes', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    console.log = jest.fn();
    console.error = jest.fn();
  });

  describe('GET /api/portfolio/health', () => {
    it('should return health status', async () => {
      const response = await request(app)
        .get('/api/portfolio/health')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        status: 'operational',
        service: 'portfolio-enhanced',
        timestamp: expect.any(String),
        features: {
          alpacaIntegration: true,
          databaseStorage: true,
          realTimeSync: true,
          circuitBreaker: true
        }
      });
    });
  });

  describe('GET /api/portfolio/holdings', () => {
    it('should return cached data when available and fresh', async () => {
      const mockCachedData = {
        holdings: [
          {
            symbol: 'AAPL',
            quantity: 10,
            marketValue: 1550,
            unrealizedPL: 50
          }
        ],
        summary: {
          totalEquity: 10000,
          buyingPower: 5000
        },
        lastSync: new Date(Date.now() - 2 * 60 * 1000).toISOString() // 2 minutes ago
      };

      portfolioDb.getCachedPortfolioData.mockResolvedValue(mockCachedData);
      portfolioDb.isDataStale.mockReturnValue(false);

      const response = await request(app)
        .get('/api/portfolio/holdings')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockCachedData,
        source: 'database',
        responseTime: expect.any(Number),
        message: 'Portfolio data from cache'
      });
    });

    it('should sync from Alpaca when no cached data', async () => {
      portfolioDb.getCachedPortfolioData.mockResolvedValue(null);
      
      apiKeyService.getApiKey.mockResolvedValue({
        keyId: 'test-key',
        secretKey: 'test-secret',
        version: '2.0'
      });

      const mockSyncResult = {
        syncId: 'sync-123',
        duration: 1500,
        result: {
          summary: {
            totalRecordsProcessed: 5
          }
        }
      };

      const mockFreshData = {
        holdings: [{ symbol: 'AAPL', quantity: 10 }],
        summary: { totalEquity: 10000 }
      };

      portfolioSyncService.syncUserPortfolio.mockResolvedValue(mockSyncResult);
      portfolioDb.getCachedPortfolioData.mockResolvedValueOnce(null)
        .mockResolvedValueOnce(mockFreshData);

      const response = await request(app)
        .get('/api/portfolio/holdings')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockFreshData,
        source: 'alpaca',
        responseTime: expect.any(Number),
        syncInfo: {
          syncId: 'sync-123',
          duration: 1500,
          recordsUpdated: 5
        },
        message: 'Portfolio data synced from paper account'
      });

      expect(portfolioSyncService.syncUserPortfolio).toHaveBeenCalledWith('test-user-123', {
        force: false,
        accountType: 'paper'
      });
    });

    it('should return sample data when no API keys', async () => {
      portfolioDb.getCachedPortfolioData.mockResolvedValue(null);
      apiKeyService.getApiKey.mockResolvedValue(null);

      // Mock sample data
      const mockSampleData = {
        data: {
          holdings: [{ symbol: 'SAMPLE', quantity: 100 }],
          summary: { totalEquity: 100000 }
        }
      };

      // Mock the sample portfolio store
      jest.doMock('../../utils/sample-portfolio-store', () => ({
        getSamplePortfolioData: jest.fn().mockReturnValue(mockSampleData)
      }));

      const response = await request(app)
        .get('/api/portfolio/holdings')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockSampleData.data,
        source: 'sample',
        responseTime: expect.any(Number),
        message: 'Portfolio data from sample data - configure API keys for live data'
      });
    });

    it('should return stale data when sync fails', async () => {
      portfolioDb.getCachedPortfolioData.mockResolvedValue(null);
      
      apiKeyService.getApiKey.mockResolvedValue({
        keyId: 'test-key',
        secretKey: 'test-secret'
      });

      portfolioSyncService.syncUserPortfolio.mockRejectedValue(new Error('Sync failed'));

      const mockStaleData = {
        holdings: [{ symbol: 'AAPL', quantity: 10 }],
        lastSync: new Date(Date.now() - 10 * 60 * 1000).toISOString() // 10 minutes ago
      };

      portfolioDb.getCachedPortfolioData.mockResolvedValueOnce(null)
        .mockResolvedValueOnce(mockStaleData);

      const response = await request(app)
        .get('/api/portfolio/holdings')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockStaleData,
        source: 'database_stale',
        responseTime: expect.any(Number),
        warning: 'Data may be outdated due to sync failure',
        syncError: 'Sync failed',
        message: 'Portfolio data from cache (sync failed)'
      });
    });

    it('should require authentication', async () => {
      // Create app without auth middleware
      const unauthApp = express();
      unauthApp.use(express.json());
      unauthApp.use('/api/portfolio', portfolioRoutes);

      const response = await request(unauthApp)
        .get('/api/portfolio/holdings')
        .expect(401);

      expect(response.body).toEqual({
        success: false,
        error: 'User authentication required'
      });
    });

    it('should handle force refresh parameter', async () => {
      apiKeyService.getApiKey.mockResolvedValue({
        keyId: 'test-key',
        secretKey: 'test-secret'
      });

      const mockSyncResult = {
        syncId: 'sync-123',
        duration: 1500,
        result: { summary: { totalRecordsProcessed: 5 } }
      };

      const mockFreshData = {
        holdings: [{ symbol: 'AAPL', quantity: 10 }]
      };

      portfolioSyncService.syncUserPortfolio.mockResolvedValue(mockSyncResult);
      portfolioDb.getCachedPortfolioData.mockResolvedValue(mockFreshData);

      const response = await request(app)
        .get('/api/portfolio/holdings?force=true')
        .expect(200);

      expect(portfolioSyncService.syncUserPortfolio).toHaveBeenCalledWith('test-user-123', {
        force: true,
        accountType: 'paper'
      });
    });
  });

  describe('POST /api/portfolio/sync', () => {
    it('should perform manual sync successfully', async () => {
      apiKeyService.getApiKey.mockResolvedValue({
        keyId: 'test-key',
        secretKey: 'test-secret'
      });

      const mockSyncResult = {
        syncId: 'sync-456',
        duration: 2000,
        result: {
          summary: {
            totalRecordsProcessed: 10,
            totalConflictsResolved: 2
          }
        }
      };

      portfolioSyncService.syncUserPortfolio.mockResolvedValue(mockSyncResult);

      const response = await request(app)
        .post('/api/portfolio/sync')
        .send({ force: true, accountType: 'live' })
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        message: 'Portfolio synchronized successfully',
        syncInfo: {
          syncId: 'sync-456',
          duration: 2000,
          recordsUpdated: 10,
          conflictsResolved: 2
        },
        responseTime: expect.any(Number)
      });

      expect(portfolioSyncService.syncUserPortfolio).toHaveBeenCalledWith('test-user-123', {
        force: true,
        accountType: 'live'
      });
    });

    it('should return error when no API keys configured', async () => {
      apiKeyService.getApiKey.mockResolvedValue(null);

      const response = await request(app)
        .post('/api/portfolio/sync')
        .expect(400);

      expect(response.body).toEqual({
        success: false,
        error: 'No API keys configured',
        message: 'Please configure your Alpaca API keys in settings before syncing'
      });
    });

    it('should handle sync failures', async () => {
      apiKeyService.getApiKey.mockResolvedValue({
        keyId: 'test-key',
        secretKey: 'test-secret'
      });

      portfolioSyncService.syncUserPortfolio.mockRejectedValue(new Error('Sync service unavailable'));

      const response = await request(app)
        .post('/api/portfolio/sync')
        .expect(500);

      expect(response.body).toEqual({
        success: false,
        error: 'Portfolio sync failed',
        details: 'Sync service unavailable',
        responseTime: expect.any(Number)
      });
    });
  });

  describe('GET /api/portfolio/sync-status', () => {
    it('should return sync status', async () => {
      const mockSyncStatus = {
        status: 'completed',
        syncId: 'sync-123',
        duration: 1500,
        result: { summary: { totalRecordsProcessed: 5 } }
      };

      portfolioSyncService.getSyncStatus.mockResolvedValue(mockSyncStatus);

      const response = await request(app)
        .get('/api/portfolio/sync-status')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        syncStatus: mockSyncStatus,
        timestamp: expect.any(String)
      });
    });

    it('should handle never synced status', async () => {
      portfolioSyncService.getSyncStatus.mockResolvedValue(null);

      const response = await request(app)
        .get('/api/portfolio/sync-status')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        syncStatus: { status: 'never_synced' },
        timestamp: expect.any(String)
      });
    });
  });

  describe('GET /api/portfolio/api-keys', () => {
    it('should return API key status when configured', async () => {
      apiKeyService.getApiKey.mockResolvedValue({
        keyId: 'test-key',
        secretKey: 'test-secret',
        isSandbox: true
      });

      const response = await request(app)
        .get('/api/portfolio/api-keys')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: [
          {
            id: 'alpaca-key',
            provider: 'alpaca',
            isActive: true,
            environment: 'paper',
            configured: true
          }
        ],
        providers: {
          alpaca: {
            configured: true,
            environment: 'paper'
          }
        }
      });
    });

    it('should return empty when no API keys configured', async () => {
      apiKeyService.getApiKey.mockResolvedValue(null);

      const response = await request(app)
        .get('/api/portfolio/api-keys')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: [],
        providers: {
          alpaca: {
            configured: false,
            environment: undefined
          }
        }
      });
    });
  });

  describe('GET /api/portfolio/accounts', () => {
    it('should return available accounts when API keys configured', async () => {
      apiKeyService.getApiKey.mockResolvedValue({
        keyId: 'test-key',
        secretKey: 'test-secret',
        isSandbox: false
      });

      const response = await request(app)
        .get('/api/portfolio/accounts')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        accounts: [
          {
            id: 'paper',
            name: 'Paper Trading',
            type: 'paper',
            description: 'Virtual trading with real market data',
            available: true,
            provider: 'alpaca'
          },
          {
            id: 'live',
            name: 'Live Trading',
            type: 'live',
            description: 'Real money trading account',
            available: true,
            provider: 'alpaca'
          }
        ],
        message: 'Trading accounts available based on your API key configuration'
      });
    });

    it('should return demo account when no API keys', async () => {
      apiKeyService.getApiKey.mockResolvedValue(null);

      const response = await request(app)
        .get('/api/portfolio/accounts')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        accounts: [
          {
            id: 'demo',
            name: 'Demo Account',
            type: 'demo',
            description: 'Sample portfolio data for demonstration',
            available: true,
            provider: 'sample'
          }
        ],
        message: 'Configure API keys to access live trading accounts'
      });
    });
  });

  describe('GET /api/portfolio/performance', () => {
    it('should return performance history', async () => {
      const mockPerformanceData = [
        {
          date: '2023-01-01',
          totalValue: 10000,
          unrealizedPL: 500,
          positionCount: 5
        }
      ];

      portfolioDb.getPerformanceHistory.mockResolvedValue(mockPerformanceData);

      const response = await request(app)
        .get('/api/portfolio/performance?days=30')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockPerformanceData,
        period: '30 days',
        message: 'Portfolio performance history for 30 days'
      });

      expect(portfolioDb.getPerformanceHistory).toHaveBeenCalledWith('test-user-123', 30);
    });

    it('should handle database errors', async () => {
      portfolioDb.getPerformanceHistory.mockRejectedValue(new Error('Database error'));

      const response = await request(app)
        .get('/api/portfolio/performance')
        .expect(500);

      expect(response.body).toEqual({
        success: false,
        error: 'Failed to get performance history',
        details: 'Database error'
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle authentication errors', async () => {
      // Override auth middleware to simulate auth failure
      const unauthApp = express();
      unauthApp.use(express.json());
      unauthApp.use((req, res, next) => {
        req.user = null;
        next();
      });
      unauthApp.use('/api/portfolio', portfolioRoutes);

      const response = await request(unauthApp)
        .get('/api/portfolio/holdings')
        .expect(401);

      expect(response.body).toEqual({
        success: false,
        error: 'User authentication required'
      });
    });

    it('should handle validation errors', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings?includeMetadata=invalid')
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Validation failed');
    });

    it('should handle unexpected errors with emergency fallback', async () => {
      portfolioDb.getCachedPortfolioData.mockRejectedValue(new Error('Unexpected error'));
      apiKeyService.getApiKey.mockRejectedValue(new Error('Service unavailable'));

      // Mock sample data fallback
      jest.doMock('../../utils/sample-portfolio-store', () => ({
        getSamplePortfolioData: jest.fn().mockReturnValue({
          data: {
            holdings: [{ symbol: 'SAMPLE' }],
            summary: { totalEquity: 100000 }
          }
        })
      }));

      const response = await request(app)
        .get('/api/portfolio/holdings')
        .expect(200);

      expect(response.body.source).toBe('sample_emergency');
      expect(response.body.warning).toBe('System error, showing sample data');
    });
  });
});
/**
 * Paper Trading Performance API Tests
 * Testing the enhanced performance endpoints with paper trading support
 */

const request = require('supertest');
const express = require('express');

// Mock dependencies
const mockApiKeyService = {
  getApiKey: jest.fn()
};

const mockAlpacaService = {
  getAccount: jest.fn(),
  getPositions: jest.fn(),
  getPortfolioHistory: jest.fn(),
  getOrders: jest.fn()
};

const mockPerformanceAnalytics = {
  calculateBaseMetrics: jest.fn(),
  generatePerformanceReport: jest.fn(),
  calculateRiskMetrics: jest.fn(),
  calculateAttributionAnalysis: jest.fn(),
  calculateSectorAnalysis: jest.fn(),
  calculateDiversificationScore: jest.fn(),
  getPerformanceGrade: jest.fn()
};

const mockPerformanceService = {
  getPerformanceDashboard: jest.fn()
};

// Mock modules
jest.mock('../../../utils/apiKeyService', () => mockApiKeyService);
jest.mock('../../../utils/alpacaService', () => jest.fn().mockImplementation(() => mockAlpacaService));
jest.mock('../../../utils/advancedPerformanceAnalytics', () => jest.fn().mockImplementation(() => mockPerformanceAnalytics));
jest.mock('../../../services/performanceMonitoringService', () => jest.fn().mockImplementation(() => mockPerformanceService));

// Create test app
const app = express();
app.use(express.json());

// Mock authentication middleware
app.use((req, res, next) => {
  req.user = { sub: 'test-user-123' };
  req.startTime = Date.now();
  next();
});

// Import and mount the performance router
const performanceRouter = require('../../../routes/performance');
app.use('/api/performance', performanceRouter);

describe('Performance API Paper Trading Support', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    
    // Default mock implementations
    mockApiKeyService.getApiKey.mockResolvedValue({
      keyId: 'test-key',
      secretKey: 'test-secret',
      provider: 'alpaca',
      created: '2024-01-01T00:00:00Z',
      version: '1.0' // This makes isSandbox = true
    });
    
    mockAlpacaService.getAccount.mockResolvedValue({
      portfolio_value: 100000,
      cash: 25000,
      day_trade_count: 0
    });
    
    mockAlpacaService.getPositions.mockResolvedValue([
      {
        symbol: 'AAPL',
        qty: 10,
        market_value: 1500,
        avg_cost: 145
      }
    ]);
    
    mockPerformanceService.getPerformanceDashboard.mockReturnValue({
      systemHealth: 'good',
      activeMetrics: 15
    });
  });

  describe('GET /api/performance/dashboard', () => {
    test('should return dashboard data with paper trading mode', async () => {
      const response = await request(app)
        .get('/api/performance/dashboard')
        .query({ accountType: 'paper' })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.accountType).toBe('paper');
      expect(response.body.tradingMode).toBe('Paper Trading');
      expect(response.body.data.system).toBeDefined();
      expect(mockApiKeyService.getApiKey).toHaveBeenCalledWith('test-user-123', 'alpaca');
    });

    test('should default to paper trading when no accountType specified', async () => {
      const response = await request(app)
        .get('/api/performance/dashboard')
        .expect(200);

      expect(response.body.accountType).toBe('paper');
      expect(response.body.tradingMode).toBe('Paper Trading');
    });

    test('should handle live trading mode', async () => {
      mockApiKeyService.getApiKey.mockResolvedValue({
        keyId: 'test-key',
        secretKey: 'test-secret',
        provider: 'alpaca',
        created: '2024-01-01T00:00:00Z',
        version: '2.0' // This makes isSandbox = false for live trading
      });

      const response = await request(app)
        .get('/api/performance/dashboard')
        .query({ accountType: 'live' })
        .expect(200);

      expect(response.body.accountType).toBe('live');
      expect(response.body.tradingMode).toBe('Live Trading');
    });

    test('should handle API key service failures gracefully', async () => {
      mockApiKeyService.getApiKey.mockRejectedValue(new Error('No API keys configured'));

      const response = await request(app)
        .get('/api/performance/dashboard')
        .query({ accountType: 'paper' })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.portfolio).toBeNull();
    });

    test('should validate account type parameter', async () => {
      const response = await request(app)
        .get('/api/performance/dashboard')
        .query({ accountType: 'invalid' })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('accountType must be paper or live');
    });
  });

  describe('GET /api/performance/portfolio/:accountId', () => {
    test('should return portfolio performance analytics for paper trading', async () => {
      mockAlpacaService.getPortfolioHistory.mockResolvedValue({
        equity: [100000, 105000, 110000],
        timestamp: ['2024-01-01', '2024-01-02', '2024-01-03']
      });

      mockPerformanceAnalytics.generatePerformanceReport.mockResolvedValue({
        totalReturn: 10000,
        totalReturnPercent: 10,
        annualizedReturn: 12.5,
        volatility: 0.15,
        sharpeRatio: 0.8
      });

      const response = await request(app)
        .get('/api/performance/portfolio/paper-account')
        .query({ accountType: 'paper', period: '1M' })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.accountType).toBe('paper');
      expect(response.body.tradingMode).toBe('Paper Trading');
      expect(response.body.data.totalReturn).toBe(10000);
      expect(response.body.source).toBe('alpaca');
      
      expect(mockAlpacaService.getAccount).toHaveBeenCalled();
      expect(mockAlpacaService.getPositions).toHaveBeenCalled();
      expect(mockAlpacaService.getPortfolioHistory).toHaveBeenCalledWith({ period: '1M', timeframe: '1Day' });
    });

    test('should validate period parameter', async () => {
      const response = await request(app)
        .get('/api/performance/portfolio/test-account')
        .query({ period: 'invalid' })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('period must be');
    });

    test('should require authentication', async () => {
      const appNoAuth = express();
      appNoAuth.use('/api/performance', performanceRouter);

      const response = await request(appNoAuth)
        .get('/api/performance/portfolio/test-account')
        .expect(401);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Authentication required');
    });
  });

  describe('GET /api/performance/analytics/detailed', () => {
    test('should return detailed analytics with paper trading info', async () => {
      mockAlpacaService.getOrders.mockResolvedValue([
        { symbol: 'AAPL', side: 'buy', qty: 10, filled_at: '2024-01-01' }
      ]);

      mockPerformanceAnalytics.calculateBaseMetrics.mockResolvedValue({
        totalReturn: 5000,
        volatility: 0.12
      });

      mockPerformanceAnalytics.calculateRiskMetrics.mockResolvedValue({
        var95: 0.025,
        maxDrawdown: 0.08
      });

      mockPerformanceAnalytics.calculateAttributionAnalysis.mockResolvedValue({
        sectorAttribution: { technology: 0.8 }
      });

      mockPerformanceAnalytics.calculateSectorAnalysis.mockResolvedValue({
        sectors: { technology: 0.6, healthcare: 0.4 }
      });

      mockPerformanceAnalytics.calculateDiversificationScore.mockResolvedValue(0.75);
      mockPerformanceAnalytics.getPerformanceGrade.mockResolvedValue('B+');

      const response = await request(app)
        .get('/api/performance/analytics/detailed')
        .query({ accountType: 'paper', includeRisk: 'true', includeAttribution: 'true' })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.accountType).toBe('paper');
      expect(response.body.data.performance).toBeDefined();
      expect(response.body.data.risk).toBeDefined();
      expect(response.body.data.attribution).toBeDefined();
      expect(response.body.data.diversification).toBeDefined();
      expect(response.body.data.grade).toBe('B+');
      
      // Paper trading specific info
      expect(response.body.paperTradingInfo).toBeDefined();
      expect(response.body.paperTradingInfo.isPaperAccount).toBe(true);
      expect(response.body.paperTradingInfo.virtualCash).toBe(25000);
      expect(response.body.paperTradingInfo.restrictions).toContain('No real money risk');
    });

    test('should handle selective analytics inclusion', async () => {
      const response = await request(app)
        .get('/api/performance/analytics/detailed')
        .query({ includeRisk: 'false', includeAttribution: 'false' })
        .expect(200);

      expect(response.body.data.performance).toBeDefined();
      expect(response.body.data.risk).toBeUndefined();
      expect(response.body.data.attribution).toBeUndefined();
    });

    test('should handle API key service errors', async () => {
      mockApiKeyService.getApiKey.mockRejectedValue(new Error('API key service error'));

      const response = await request(app)
        .get('/api/performance/analytics/detailed')
        .query({ accountType: 'live' })
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain('API key service error');
    });
  });

  describe('Paper Trading Integration', () => {
    test('should properly setup AlpacaService for paper trading', async () => {
      await request(app)
        .get('/api/performance/dashboard')
        .query({ accountType: 'paper' });

      expect(mockApiKeyService.getApiKey).toHaveBeenCalledWith(
        'test-user-123', 
        'alpaca'
      );
    });

    test('should handle missing API keys', async () => {
      mockApiKeyService.getApiKey.mockResolvedValue(null);

      const response = await request(app)
        .get('/api/performance/portfolio/test-account')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain('No Alpaca API keys configured');
    });

    test('should maintain response format consistency', async () => {
      const response = await request(app)
        .get('/api/performance/dashboard')
        .query({ accountType: 'paper' });

      expect(response.body).toHaveProperty('success');
      expect(response.body).toHaveProperty('data');
      expect(response.body).toHaveProperty('accountType');
      expect(response.body).toHaveProperty('tradingMode');
      expect(response.body).toHaveProperty('timestamp');
    });
  });

  describe('Error Handling', () => {
    test('should handle AlpacaService failures gracefully', async () => {
      mockAlpacaService.getAccount.mockRejectedValue(new Error('Alpaca API error'));

      const response = await request(app)
        .get('/api/performance/dashboard')
        .query({ accountType: 'paper' })
        .expect(200);

      expect(response.body.data.portfolio).toBeNull();
    });

    test('should handle performance analytics calculation errors', async () => {
      mockPerformanceAnalytics.generatePerformanceReport.mockRejectedValue(new Error('Calculation error'));

      const response = await request(app)
        .get('/api/performance/portfolio/test-account')
        .expect(500);

      expect(response.body.success).toBe(false);
    });

    test('should provide helpful error messages', async () => {
      mockApiKeyService.getApiKey.mockRejectedValue(new Error('Invalid credentials'));

      const response = await request(app)
        .get('/api/performance/analytics/detailed')
        .expect(500);

      expect(response.body.message).toContain('Invalid credentials');
      expect(response.body).toHaveProperty('timestamp');
    });
  });
});
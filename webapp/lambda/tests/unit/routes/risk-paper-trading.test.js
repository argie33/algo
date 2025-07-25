/**
 * Paper Trading Risk API Tests
 * Testing the enhanced risk endpoints with paper trading support
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
  getPortfolioHistory: jest.fn()
};

const mockRiskEngine = {
  calculatePortfolioRisk: jest.fn(),
  calculateVaR: jest.fn(),
  performStressTest: jest.fn(),
  calculateCorrelationMatrix: jest.fn(),
  calculateRiskAttribution: jest.fn(),
  startRealTimeMonitoring: jest.fn(),
  stopRealTimeMonitoring: jest.fn(),
  getMonitoringStatus: jest.fn()
};

// Mock database query function
const mockQuery = jest.fn();

// Mock modules
jest.mock('../../../utils/apiKeyService', () => mockApiKeyService);
jest.mock('../../../utils/alpacaService', () => jest.fn().mockImplementation(() => mockAlpacaService));
jest.mock('../../../utils/riskEngine', () => jest.fn().mockImplementation(() => mockRiskEngine));
jest.mock('../../../utils/database', () => ({ query: mockQuery }));

// Create test app
const app = express();
app.use(express.json());

// Mock authentication middleware
app.use((req, res, next) => {
  req.user = { sub: 'test-user-123' };
  next();
});

// Import and mount the risk router
const riskRouter = require('../../../routes/risk');
app.use('/api/risk', riskRouter);

describe('Risk API Paper Trading Support', () => {
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
        avg_cost: 145,
        unrealized_pl: 50
      },
      {
        symbol: 'GOOGL',
        qty: 5,
        market_value: 1200,
        avg_cost: 240,
        unrealized_pl: -25
      }
    ]);
    
    mockAlpacaService.getPortfolioHistory.mockResolvedValue({
      equity: [100000, 102000, 99000, 105000],
      timestamp: ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04']
    });
  });

  describe('GET /api/risk/portfolio/:portfolioId', () => {
    test('should calculate portfolio risk metrics for paper trading', async () => {
      mockRiskEngine.calculatePortfolioRisk.mockResolvedValue({
        var_95: 0.025,
        var_99: 0.035,
        volatility: 0.15,
        beta: 1.2,
        sharpe_ratio: 0.85,
        max_drawdown: 0.08,
        correlation_risk: 0.6
      });

      const response = await request(app)
        .get('/api/risk/portfolio/paper-portfolio')
        .query({ accountType: 'paper', timeframe: '1M', confidence_level: 0.95 })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.accountType).toBe('paper');
      expect(response.body.tradingMode).toBe('Paper Trading');
      expect(response.body.data.portfolioId).toBe('paper-test-user-123');
      expect(response.body.data.riskMetrics.var_95).toBe(0.025);
      expect(response.body.data.accountInfo.totalValue).toBe(100000);
      
      // Paper trading specific info
      expect(response.body.paperTradingInfo).toBeDefined();
      expect(response.body.paperTradingInfo.isPaperAccount).toBe(true);
      expect(response.body.paperTradingInfo.virtualCash).toBe(25000);
      expect(response.body.paperTradingInfo.restrictions).toContain('Simulated risk calculations');
      
      expect(mockRiskEngine.calculatePortfolioRisk).toHaveBeenCalledWith(
        expect.objectContaining({
          positions: expect.any(Array),
          portfolioHistory: expect.any(Object),
          account: expect.any(Object),
          accountType: 'paper'
        }),
        '1M',
        0.95
      );
    });

    test('should handle empty portfolio gracefully', async () => {
      mockAlpacaService.getPositions.mockResolvedValue([]);

      const response = await request(app)
        .get('/api/risk/portfolio/empty-portfolio')
        .query({ accountType: 'paper' })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.riskMetrics.message).toBe('No positions found for risk analysis');
      expect(response.body.data.riskMetrics.positionCount).toBe(0);
    });

    test('should validate timeframe parameter', async () => {
      const response = await request(app)
        .get('/api/risk/portfolio/test-portfolio')
        .query({ timeframe: 'invalid' })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('timeframe must be');
    });

    test('should validate confidence level parameter', async () => {
      const response = await request(app)
        .get('/api/risk/portfolio/test-portfolio')
        .query({ confidence_level: 1.5 })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('confidence_level must be between 0.8 and 0.99');
    });
  });

  describe('GET /api/risk/var', () => {
    test('should calculate Value at Risk for paper trading', async () => {
      mockRiskEngine.calculateVaR.mockResolvedValue({
        var_95: 0.023,
        var_99: 0.032,
        expected_shortfall: 0.041,
        confidence_level: 0.95,
        method: 'historical',
        portfolio_value: 100000,
        daily_var: 2300,
        annualized_var: 0.145
      });

      const response = await request(app)
        .get('/api/risk/var')
        .query({ 
          accountType: 'paper', 
          method: 'historical', 
          confidence_level: 0.95,
          time_horizon: 1,
          lookback_days: 252
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.accountType).toBe('paper');
      expect(response.body.tradingMode).toBe('Paper Trading');
      expect(response.body.data.var_95).toBe(0.023);
      expect(response.body.data.parameters.method).toBe('historical');
      expect(response.body.data.parameters.confidence_level).toBe(0.95);
      expect(response.body.data.accountInfo.positionCount).toBe(2);
      
      // Paper trading specific info
      expect(response.body.paperTradingInfo).toBeDefined();
      expect(response.body.paperTradingInfo.virtualRisk).toBe(true);
      expect(response.body.paperTradingInfo.disclaimer).toBe('VaR calculations based on simulated portfolio data');
      
      expect(mockRiskEngine.calculateVaR).toHaveBeenCalledWith(
        expect.objectContaining({
          positions: expect.any(Array),
          portfolioHistory: expect.any(Object),
          accountType: 'paper'
        }),
        'historical',
        0.95,
        1,
        252
      );
    });

    test('should handle empty portfolio for VaR calculation', async () => {
      mockAlpacaService.getPositions.mockResolvedValue([]);

      const response = await request(app)
        .get('/api/risk/var')
        .query({ accountType: 'paper' })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.var).toBe(0);
      expect(response.body.data.message).toBe('No positions found for VaR analysis');
    });

    test('should validate VaR method parameter', async () => {
      const response = await request(app)
        .get('/api/risk/var')
        .query({ method: 'invalid_method' })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('method must be historical, parametric, or monte_carlo');
    });

    test('should validate time horizon parameter', async () => {
      const response = await request(app)
        .get('/api/risk/var')
        .query({ time_horizon: 50 })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('time_horizon must be between 1 and 30 days');
    });

    test('should validate lookback days parameter', async () => {
      const response = await request(app)
        .get('/api/risk/var')
        .query({ lookback_days: 10 })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('lookback_days must be between 30 and 1000');
    });
  });

  describe('GET /api/risk/dashboard', () => {
    test('should return risk dashboard with paper trading support', async () => {
      mockRiskEngine.calculatePortfolioRisk.mockResolvedValue({
        var_95: 0.028,
        volatility: 0.16,
        beta: 1.1,
        sharpe_ratio: 0.75,
        max_drawdown: 0.09
      });

      // Mock database queries for alerts and market indicators
      mockQuery
        .mockResolvedValueOnce({ rows: [{ severity: 'medium', count: '2' }] }) // alerts query
        .mockResolvedValueOnce({ rows: [
          { indicator_name: 'VIX', current_value: 22.5, risk_level: 'medium', last_updated: '2024-01-01' }
        ]}); // market indicators query

      const response = await request(app)
        .get('/api/risk/dashboard')
        .query({ accountType: 'paper' })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.accountType).toBe('paper');
      expect(response.body.tradingMode).toBe('Paper Trading');
      expect(response.body.data.portfolio.id).toBe('paper-test-user-123');
      expect(response.body.data.portfolio.name).toBe('Paper Trading Account');
      expect(response.body.data.portfolio.riskMetrics.var95).toBe(0.028);
      expect(response.body.data.alert_counts.medium).toBe(2);
      expect(response.body.data.market_indicators).toHaveLength(1);
      expect(response.body.data.summary.account_type).toBe('paper');
      
      // Paper trading specific info
      expect(response.body.paperTradingInfo).toBeDefined();
      expect(response.body.paperTradingInfo.virtualRisk).toBe(true);
      expect(response.body.paperTradingInfo.disclaimer).toBe('All risk calculations are based on simulated trading data');
    });

    test('should handle risk calculation failures gracefully', async () => {
      mockRiskEngine.calculatePortfolioRisk.mockRejectedValue(new Error('Risk calculation failed'));

      const response = await request(app)
        .get('/api/risk/dashboard')
        .query({ accountType: 'paper' })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.portfolio.riskMetrics).toBeNull();
    });

    test('should classify risk levels correctly', async () => {
      mockRiskEngine.calculatePortfolioRisk.mockResolvedValue({
        var_95: 0.06 // High risk (>0.05)
      });

      const response = await request(app)
        .get('/api/risk/dashboard')
        .query({ accountType: 'paper' })
        .expect(200);

      expect(response.body.data.portfolio.riskLevel).toBe('high');
      expect(response.body.data.summary.high_risk_portfolios).toBe(1);
    });
  });

  describe('Paper Trading Integration', () => {
    test('should properly setup AlpacaService for paper trading', async () => {
      await request(app)
        .get('/api/risk/dashboard')
        .query({ accountType: 'paper' });

      expect(mockApiKeyService.getApiKey).toHaveBeenCalledWith(
        'test-user-123', 
        'alpaca'
      );
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
        .get('/api/risk/var')
        .query({ accountType: 'live' })
        .expect(200);

      expect(response.body.accountType).toBe('live');
      expect(response.body.tradingMode).toBe('Live Trading');
      expect(response.body.paperTradingInfo).toBeUndefined();
    });

    test('should handle missing API keys', async () => {
      mockApiKeyService.getApiKey.mockResolvedValue(null);

      const response = await request(app)
        .get('/api/risk/portfolio/test-portfolio')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain('No Alpaca API keys configured');
    });

    test('should handle API key service errors', async () => {
      mockApiKeyService.getApiKey.mockRejectedValue(new Error('API key service error'));

      const response = await request(app)
        .get('/api/risk/var')
        .query({ accountType: 'live' })
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain('API key service error');
    });
  });

  describe('Response Format Consistency', () => {
    test('should maintain consistent response format across endpoints', async () => {
      mockRiskEngine.calculatePortfolioRisk.mockResolvedValue({ var_95: 0.02 });
      
      const response = await request(app)
        .get('/api/risk/portfolio/test-portfolio')
        .query({ accountType: 'paper' });

      expect(response.body).toHaveProperty('success');
      expect(response.body).toHaveProperty('data');
      expect(response.body).toHaveProperty('accountType');
      expect(response.body).toHaveProperty('tradingMode');
      expect(response.body).toHaveProperty('source');
      expect(response.body).toHaveProperty('timestamp');
    });

    test('should include paper trading information consistently', async () => {
      mockRiskEngine.calculateVaR.mockResolvedValue({ var_95: 0.02 });
      
      const response = await request(app)
        .get('/api/risk/var')
        .query({ accountType: 'paper' });

      expect(response.body.paperTradingInfo).toBeDefined();
      expect(response.body.paperTradingInfo.isPaperAccount).toBe(true);
      expect(response.body.paperTradingInfo.virtualRisk).toBe(true);
    });
  });

  describe('Error Handling', () => {
    test('should handle AlpacaService failures gracefully', async () => {
      mockAlpacaService.getAccount.mockRejectedValue(new Error('Alpaca API error'));

      const response = await request(app)
        .get('/api/risk/dashboard')
        .query({ accountType: 'paper' })
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain('Alpaca API error');
    });

    test('should handle risk engine calculation errors', async () => {
      mockRiskEngine.calculatePortfolioRisk.mockRejectedValue(new Error('Risk calculation failed'));

      const response = await request(app)
        .get('/api/risk/portfolio/test-portfolio')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain('Risk calculation failed');
    });

    test('should provide helpful error messages with timestamp', async () => {
      mockApiKeyService.getApiKey.mockRejectedValue(new Error('Invalid credentials'));

      const response = await request(app)
        .get('/api/risk/var')
        .expect(500);

      expect(response.body.message).toContain('Invalid credentials');
      expect(response.body).toHaveProperty('timestamp');
    });
  });
});
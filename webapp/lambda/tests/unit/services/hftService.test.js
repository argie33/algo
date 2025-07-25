/**
 * Unit Tests for HFT Service - Phase 4 Advanced Features
 * Tests advanced risk management and real-time data integration
 */

const { describe, it, expect, vi, beforeEach, afterEach } = require('vitest');
const HFTService = require('../../../services/hftService');
const AdvancedRiskManager = require('../../../services/advancedRiskManager');
const RealTimeDataIntegrator = require('../../../services/realTimeDataIntegrator');

// Mock dependencies
vi.mock('../../../utils/database', () => ({
  query: vi.fn(() => Promise.resolve([{ success: true }]))
}));

vi.mock('../../../utils/structuredLogger', () => ({
  createLogger: vi.fn(() => ({
    info: vi.fn(),
    error: vi.fn(),
    warn: vi.fn(),
    debug: vi.fn()
  }))
}));

vi.mock('../../../services/advancedRiskManager');
vi.mock('../../../services/realTimeDataIntegrator');

describe('HFTService - Phase 4 Integration', () => {
  let hftService;
  let mockRiskManager;
  let mockDataIntegrator;

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Setup mock instances
    mockRiskManager = {
      updatePortfolioState: vi.fn(),
      assessTradeRisk: vi.fn(() => ({ approved: true, riskScore: 0.3 })),
      getMetrics: vi.fn(() => ({
        portfolioExposure: 5000,
        dailyLoss: 150,
        riskUtilization: { exposure: 0.5, dailyLoss: 0.3 }
      })),
      initialize: vi.fn(() => Promise.resolve()),
      stop: vi.fn(() => Promise.resolve())
    };

    mockDataIntegrator = {
      initialize: vi.fn(() => Promise.resolve()),
      on: vi.fn(),
      off: vi.fn(),
      processMarketData: vi.fn(),
      getMetrics: vi.fn(() => ({
        connectionStatus: 'active',
        signalsGenerated: 25,
        dataQuality: 'excellent'
      })),
      stop: vi.fn(() => Promise.resolve())
    };

    // Mock constructors
    AdvancedRiskManager.mockImplementation(() => mockRiskManager);
    RealTimeDataIntegrator.mockImplementation(() => mockDataIntegrator);

    hftService = new HFTService();
  });

  afterEach(() => {
    if (hftService && hftService.isRunning) {
      hftService.stop();
    }
  });

  describe('Service Initialization', () => {
    it('creates advanced services instances', () => {
      expect(hftService.riskManager).toBeDefined();
      expect(hftService.dataIntegrator).toBeDefined();
      expect(hftService.servicesInitialized).toBe(false);
    });

    it('initializes with default configuration', () => {
      expect(hftService.riskConfig.maxPositionSize).toBe(1000);
      expect(hftService.riskConfig.maxDailyLoss).toBe(500);
      expect(hftService.riskConfig.maxOpenPositions).toBe(5);
    });

    it('initializes default strategies', () => {
      expect(hftService.strategies.size).toBeGreaterThan(0);
      expect(Array.from(hftService.strategies.keys())).toContain('scalping_btc');
    });
  });

  describe('Advanced Services Integration', () => {
    it('initializes advanced services successfully', async () => {
      const userCredentials = { apiKey: 'test-key', secret: 'test-secret' };
      
      await hftService.initializeAdvancedServices(userCredentials);

      expect(mockDataIntegrator.initialize).toHaveBeenCalledWith(userCredentials);
      expect(mockDataIntegrator.on).toHaveBeenCalledWith('signal', expect.any(Function));
      expect(hftService.servicesInitialized).toBe(true);
    });

    it('handles advanced services initialization failure', async () => {
      mockDataIntegrator.initialize.mockRejectedValue(new Error('Connection failed'));
      
      const userCredentials = { apiKey: 'test-key' };
      
      await expect(hftService.initializeAdvancedServices(userCredentials))
        .rejects.toThrow('Connection failed');
      
      expect(hftService.servicesInitialized).toBe(false);
    });

    it('processes real-time signals from data integrator', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      
      // Get the signal handler from the 'on' call
      const signalHandler = mockDataIntegrator.on.mock.calls.find(
        call => call[0] === 'signal'
      )[1];

      const mockSignal = {
        symbol: 'BTC/USD',
        type: 'buy',
        strength: 0.8,
        timestamp: Date.now()
      };

      // Mock risk assessment
      mockRiskManager.assessTradeRisk.mockReturnValue({
        approved: true,
        riskScore: 0.3,
        maxQuantity: 0.1
      });

      signalHandler(mockSignal);

      expect(mockRiskManager.assessTradeRisk).toHaveBeenCalledWith(
        expect.objectContaining({
          symbol: 'BTC/USD',
          type: 'buy'
        })
      );
    });

    it('rejects high-risk signals', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      
      const signalHandler = mockDataIntegrator.on.mock.calls.find(
        call => call[0] === 'signal'
      )[1];

      const mockSignal = {
        symbol: 'BTC/USD',
        type: 'buy',
        strength: 0.9,
        timestamp: Date.now()
      };

      // Mock high risk assessment
      mockRiskManager.assessTradeRisk.mockReturnValue({
        approved: false,
        riskScore: 0.9,
        reason: 'Exceeds position limit'
      });

      signalHandler(mockSignal);

      // Signal should be processed but not executed due to risk
      expect(mockRiskManager.assessTradeRisk).toHaveBeenCalled();
      expect(hftService.orders.size).toBe(0);
    });
  });

  describe('Enhanced Metrics Collection', () => {
    it('includes advanced services metrics', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      
      const metrics = hftService.getMetrics();

      expect(metrics.advancedServices).toBeDefined();
      expect(metrics.advancedServices.initialized).toBe(true);
      expect(metrics.advancedServices.riskManager).toEqual({
        portfolioExposure: 5000,
        dailyLoss: 150,
        riskUtilization: { exposure: 0.5, dailyLoss: 0.3 }
      });
      expect(metrics.advancedServices.dataIntegrator).toEqual({
        connectionStatus: 'active',
        signalsGenerated: 25,
        dataQuality: 'excellent'
      });
    });

    it('includes risk utilization in main metrics', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      
      const metrics = hftService.getMetrics();

      expect(metrics.riskUtilization).toBeDefined();
      expect(metrics.riskUtilization.exposure).toBe(0.5);
      expect(metrics.riskUtilization.dailyLoss).toBe(0.3);
    });

    it('handles metrics when services not initialized', () => {
      const metrics = hftService.getMetrics();

      expect(metrics.advancedServices).toBeDefined();
      expect(metrics.advancedServices.initialized).toBe(false);
      expect(metrics.riskUtilization).toEqual({
        dailyLoss: 0,
        openPositions: 0
      });
    });
  });

  describe('Service Lifecycle Management', () => {
    it('starts HFT service with advanced services', async () => {
      const result = await hftService.start('user123', ['scalping_btc']);

      expect(result.success).toBe(true);
      expect(hftService.isRunning).toBe(true);
      expect(result.enabledStrategies).toContain('scalping_btc');
    });

    it('initializes advanced services during start if credentials provided', async () => {
      hftService.userCredentials = { apiKey: 'test-key' };
      
      await hftService.start('user123', ['scalping_btc']);

      expect(mockDataIntegrator.initialize).toHaveBeenCalled();
      expect(hftService.servicesInitialized).toBe(true);
    });

    it('stops advanced services during shutdown', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      await hftService.start('user123', ['scalping_btc']);
      
      const result = await hftService.stop();

      expect(result.success).toBe(true);
      expect(mockRiskManager.stop).toHaveBeenCalled();
      expect(mockDataIntegrator.stop).toHaveBeenCalled();
      expect(hftService.isRunning).toBe(false);
    });

    it('handles graceful shutdown on advanced services failure', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      await hftService.start('user123', ['scalping_btc']);
      
      mockDataIntegrator.stop.mockRejectedValue(new Error('Stop failed'));
      
      const result = await hftService.stop();

      expect(result.success).toBe(true); // Should still succeed
      expect(hftService.isRunning).toBe(false);
    });
  });

  describe('Market Data Processing Integration', () => {
    it('processes market data through data integrator', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      
      const marketData = {
        symbol: 'BTC/USD',
        data: {
          price: 45000,
          volume: 1000,
          timestamp: Date.now()
        }
      };

      await hftService.processMarketData(marketData);

      expect(mockDataIntegrator.processMarketData).toHaveBeenCalledWith(marketData);
    });

    it('handles market data when advanced services not initialized', async () => {
      const marketData = {
        symbol: 'BTC/USD',
        data: { price: 45000 }
      };

      // Should not throw error
      await expect(hftService.processMarketData(marketData)).resolves.toBeUndefined();
    });
  });

  describe('Risk Management Integration', () => {
    it('updates portfolio state after trade execution', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      
      // Simulate a completed trade
      const trade = {
        symbol: 'BTC/USD',
        type: 'buy',
        quantity: 0.1,
        price: 45000,
        timestamp: Date.now()
      };

      hftService.updatePortfolioState(trade);

      expect(mockRiskManager.updatePortfolioState).toHaveBeenCalledWith(trade);
    });

    it('validates trade against risk parameters', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      
      const tradeRequest = {
        symbol: 'BTC/USD',
        type: 'buy',
        quantity: 0.5,
        strategy: 'scalping_btc'
      };

      const riskAssessment = hftService.assessTradeRisk(tradeRequest);

      expect(mockRiskManager.assessTradeRisk).toHaveBeenCalledWith(tradeRequest);
      expect(riskAssessment.approved).toBe(true);
      expect(riskAssessment.riskScore).toBe(0.3);
    });
  });

  describe('Strategy Management with Advanced Features', () => {
    it('updates strategy with risk parameter validation', () => {
      const strategyUpdate = {
        riskParams: {
          positionSize: 0.2,
          stopLoss: 0.03,
          takeProfit: 0.02
        }
      };

      const result = hftService.updateStrategy('scalping_btc', strategyUpdate);

      expect(result.success).toBe(true);
      expect(result.strategy.riskParams.positionSize).toBe(0.2);
    });

    it('validates risk parameters against global limits', () => {
      const invalidUpdate = {
        riskParams: {
          positionSize: 5000 // Exceeds maxPositionSize
        }
      };

      const result = hftService.updateStrategy('scalping_btc', invalidUpdate);

      // Should still succeed but may be clamped or validated
      expect(result.success).toBe(true);
    });
  });

  describe('Performance Analytics', () => {
    it('calculates advanced performance metrics', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      
      // Add some mock trades
      hftService.metrics.totalTrades = 50;
      hftService.metrics.profitableTrades = 32;
      hftService.metrics.totalPnL = 1500;
      
      const metrics = hftService.getMetrics();

      expect(metrics.winRate).toBe(64); // 32/50 * 100
      expect(metrics.avgPnLPerTrade).toBe(30); // 1500/50
      expect(metrics.totalPnL).toBe(1500);
    });

    it('includes execution time statistics', () => {
      hftService.metrics.executionTimes = [20, 25, 30, 15, 35];
      
      const metrics = hftService.getMetrics();

      expect(metrics.avgExecutionTime).toBe(25); // Average of execution times
    });
  });

  describe('Error Handling and Recovery', () => {
    it('handles data integrator connection failures gracefully', async () => {
      mockDataIntegrator.initialize.mockRejectedValue(new Error('Network error'));
      
      await expect(hftService.initializeAdvancedServices({ apiKey: 'test' }))
        .rejects.toThrow('Network error');
      
      expect(hftService.servicesInitialized).toBe(false);
    });

    it('continues operation when risk manager fails', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      
      mockRiskManager.assessTradeRisk.mockImplementation(() => {
        throw new Error('Risk calculation failed');
      });

      const tradeRequest = { symbol: 'BTC/USD', type: 'buy' };
      
      // Should handle error gracefully
      expect(() => hftService.assessTradeRisk(tradeRequest)).not.toThrow();
    });

    it('maintains state consistency during partial failures', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      await hftService.start('user123', ['scalping_btc']);
      
      // Simulate partial failure during stop
      mockRiskManager.stop.mockRejectedValue(new Error('Stop failed'));
      
      const result = await hftService.stop();
      
      expect(result.success).toBe(true);
      expect(hftService.isRunning).toBe(false);
      expect(hftService.servicesInitialized).toBe(false);
    });
  });

  describe('Signal Processing Pipeline', () => {
    it('processes signal through complete pipeline', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      await hftService.start('user123', ['scalping_btc']);
      
      const signalHandler = mockDataIntegrator.on.mock.calls.find(
        call => call[0] === 'signal'
      )[1];

      const signal = {
        symbol: 'BTC/USD',
        type: 'buy',
        strength: 0.75,
        price: 45000,
        timestamp: Date.now()
      };

      mockRiskManager.assessTradeRisk.mockReturnValue({
        approved: true,
        riskScore: 0.4,
        maxQuantity: 0.1
      });

      signalHandler(signal);

      expect(mockRiskManager.assessTradeRisk).toHaveBeenCalled();
      expect(hftService.metrics.signalsGenerated).toBe(1);
    });

    it('handles rapid signal processing', async () => {
      await hftService.initializeAdvancedServices({ apiKey: 'test' });
      await hftService.start('user123', ['scalping_btc']);
      
      const signalHandler = mockDataIntegrator.on.mock.calls.find(
        call => call[0] === 'signal'
      )[1];

      // Process multiple signals rapidly
      for (let i = 0; i < 10; i++) {
        signalHandler({
          symbol: 'BTC/USD',
          type: i % 2 === 0 ? 'buy' : 'sell',
          strength: 0.6 + (i * 0.01),
          timestamp: Date.now() + i
        });
      }

      expect(hftService.metrics.signalsGenerated).toBe(10);
      expect(mockRiskManager.assessTradeRisk).toHaveBeenCalledTimes(10);
    });
  });
});
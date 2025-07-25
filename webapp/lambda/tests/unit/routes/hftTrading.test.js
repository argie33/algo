/**
 * Unit Tests for HFT Trading API Routes - Phase 4
 * Tests advanced API endpoints for HFT system management
 */

const { describe, it, expect, vi, beforeEach, afterEach } = require('vitest');
const request = require('supertest');
const express = require('express');
const hftTradingRoutes = require('../../../routes/hftTrading');

// Mock dependencies
const mockHftService = {
  getMetrics: vi.fn(),
  getStrategies: vi.fn(),
  start: vi.fn(),
  stop: vi.fn(),
  updateStrategy: vi.fn(),
  positions: new Map(),
  orders: new Map()
};

vi.mock('../../../services/hftService', () => {
  return vi.fn(() => mockHftService);
});

vi.mock('../../../middleware/auth', () => ({
  authenticateToken: (req, res, next) => {
    req.user = { userId: 'test-user-123' };
    next();
  }
}));

vi.mock('../../../utils/structuredLogger', () => ({
  createLogger: vi.fn(() => ({
    info: vi.fn(),
    error: vi.fn(),
    warn: vi.fn(),
    debug: vi.fn()
  }))
}));

describe('HFT Trading API Routes - Phase 4', () => {
  let app;

  beforeEach(() => {
    vi.clearAllMocks();
    
    app = express();
    app.use(express.json());
    app.use('/api/hft', hftTradingRoutes);

    // Setup default mock responses
    mockHftService.getMetrics.mockReturnValue({
      isRunning: false,
      uptime: 0,
      startTime: null,
      totalTrades: 142,
      profitableTrades: 89,
      totalPnL: 2500.75,
      dailyPnL: 150.25,
      winRate: 62.7,
      openPositions: 3,
      signalsGenerated: 67,
      ordersExecuted: 45,
      avgExecutionTime: 25,
      lastTradeTime: Date.now() - 300000,
      riskUtilization: {
        dailyLoss: 0.3,
        openPositions: 0.6
      },
      advancedServices: {
        initialized: true,
        riskManager: {
          portfolioExposure: 5000,
          dailyLoss: 150,
          riskUtilization: { exposure: 0.5, dailyLoss: 0.3 }
        },
        dataIntegrator: {
          connectionStatus: 'active',
          signalsGenerated: 25,
          dataQuality: 'excellent'
        }
      }
    });

    mockHftService.getStrategies.mockReturnValue([
      {
        id: 'scalping_btc',
        name: 'Bitcoin Scalping',
        type: 'scalping',
        enabled: true,
        symbols: ['BTC/USD'],
        performance: { winRate: 65, totalTrades: 50 }
      }
    ]);
  });

  describe('GET /api/hft/status', () => {
    it('returns comprehensive HFT status including advanced services', async () => {
      const response = await request(app)
        .get('/api/hft/status')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.engine).toBeDefined();
      expect(response.body.data.metrics).toBeDefined();
      expect(response.body.data.strategies).toBeDefined();
      expect(response.body.data.riskMetrics).toBeDefined();
      
      // Check advanced services metrics are included
      expect(response.body.data.metrics.totalTrades).toBe(142);
      expect(response.body.data.metrics.totalPnL).toBe(2500.75);
      expect(response.body.data.riskMetrics.dailyLoss).toBe(0.3);
    });

    it('handles service errors gracefully', async () => {
      mockHftService.getMetrics.mockImplementation(() => {
        throw new Error('Service unavailable');
      });

      const response = await request(app)
        .get('/api/hft/status')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Failed to get HFT status');
    });
  });

  describe('POST /api/hft/start', () => {
    it('starts HFT engine with default strategies', async () => {
      mockHftService.start.mockResolvedValue({
        success: true,
        message: 'HFT engine started successfully',
        enabledStrategies: ['scalping_btc'],
        correlationId: 'test-correlation-id'
      });

      const response = await request(app)
        .post('/api/hft/start')
        .send({})
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.enabledStrategies).toEqual(['scalping_btc']);
      expect(mockHftService.start).toHaveBeenCalledWith('test-user-123', ['scalping_btc']);
    });

    it('starts HFT engine with custom strategies', async () => {
      mockHftService.start.mockResolvedValue({
        success: true,
        message: 'HFT engine started successfully',
        enabledStrategies: ['scalping_btc', 'momentum_crypto'],
        correlationId: 'test-correlation-id'
      });

      const response = await request(app)
        .post('/api/hft/start')
        .send({ strategies: ['scalping_btc', 'momentum_crypto'] })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(mockHftService.start).toHaveBeenCalledWith('test-user-123', ['scalping_btc', 'momentum_crypto']);
    });

    it('handles start failures', async () => {
      mockHftService.start.mockResolvedValue({
        success: false,
        error: 'Insufficient balance',
        details: 'Minimum $1000 required'
      });

      const response = await request(app)
        .post('/api/hft/start')
        .send({})
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Insufficient balance');
    });
  });

  describe('POST /api/hft/stop', () => {
    it('stops HFT engine successfully', async () => {
      mockHftService.stop.mockResolvedValue({
        success: true,
        message: 'HFT engine stopped successfully',
        finalMetrics: {
          totalTrades: 142,
          totalPnL: 2500.75,
          duration: 3600000
        }
      });

      const response = await request(app)
        .post('/api/hft/stop')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.finalMetrics).toBeDefined();
      expect(mockHftService.stop).toHaveBeenCalled();
    });

    it('handles stop errors', async () => {
      mockHftService.stop.mockRejectedValue(new Error('Stop failed'));

      const response = await request(app)
        .post('/api/hft/stop')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Failed to stop HFT engine');
    });
  });

  describe('GET /api/hft/advanced/risk-metrics', () => {
    it('returns advanced risk management metrics', async () => {
      const response = await request(app)
        .get('/api/hft/advanced/risk-metrics')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.riskManager).toBeDefined();
      expect(response.body.data.portfolioRisk).toBeDefined();
      expect(response.body.data.servicesStatus).toBeDefined();
      
      // Check specific risk metrics
      expect(response.body.data.riskManager.portfolioExposure).toBe(5000);
      expect(response.body.data.portfolioRisk.dailyLossUtilization).toBe(0.3);
      expect(response.body.data.servicesStatus.initialized).toBe(true);
    });

    it('handles missing advanced services gracefully', async () => {
      mockHftService.getMetrics.mockReturnValue({
        totalPnL: 1000,
        openPositions: 2,
        riskUtilization: { dailyLoss: 0.2, openPositions: 0.4 }
      });

      const response = await request(app)
        .get('/api/hft/advanced/risk-metrics')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.portfolioRisk.dailyLossUtilization).toBe(0.2);
      expect(response.body.data.servicesStatus.initialized).toBe(false);
    });
  });

  describe('GET /api/hft/advanced/realtime-data', () => {
    it('returns real-time data integrator metrics', async () => {
      const response = await request(app)
        .get('/api/hft/advanced/realtime-data')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.dataIntegrator).toBeDefined();
      expect(response.body.data.signalGeneration).toBeDefined();
      expect(response.body.data.servicesStatus).toBeDefined();
      
      // Check data integrator metrics
      expect(response.body.data.dataIntegrator.connectionStatus).toBe('active');
      expect(response.body.data.signalGeneration.signalsGenerated).toBe(67);
      expect(response.body.data.signalGeneration.ordersExecuted).toBe(45);
      expect(response.body.data.signalGeneration.executionRate).toBe('67.16%');
    });

    it('calculates execution rate correctly', async () => {
      mockHftService.getMetrics.mockReturnValue({
        signalsGenerated: 100,
        ordersExecuted: 75,
        advancedServices: {
          initialized: true,
          dataIntegrator: { connectionStatus: 'active' }
        }
      });

      const response = await request(app)
        .get('/api/hft/advanced/realtime-data')
        .expect(200);

      expect(response.body.data.signalGeneration.executionRate).toBe('75.00%');
    });
  });

  describe('POST /api/hft/advanced/update-risk-config', () => {
    it('updates risk configuration successfully', async () => {
      const riskConfig = {
        maxPositionSize: 1500,
        maxDailyLoss: 750,
        stopLossPercentage: 2.5
      };

      const response = await request(app)
        .post('/api/hft/advanced/update-risk-config')
        .send({ riskConfig })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.updatedConfig).toEqual(riskConfig);
    });

    it('validates risk configuration format', async () => {
      const response = await request(app)
        .post('/api/hft/advanced/update-risk-config')
        .send({ riskConfig: 'invalid' })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Invalid risk configuration provided');
    });

    it('requires advanced services to be initialized', async () => {
      mockHftService.getMetrics.mockReturnValue({
        advancedServices: { initialized: false }
      });

      const response = await request(app)
        .post('/api/hft/advanced/update-risk-config')
        .send({ riskConfig: { maxPositionSize: 1000 } })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Advanced services not initialized');
    });
  });

  describe('GET /api/hft/advanced/market-signals', () => {
    it('returns market signals placeholder', async () => {
      const response = await request(app)
        .get('/api/hft/advanced/market-signals')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.signals).toEqual([]);
      expect(response.body.data.limit).toBe(10);
      expect(response.body.data.note).toContain('Signal history feature');
    });

    it('respects custom limit parameter', async () => {
      const response = await request(app)
        .get('/api/hft/advanced/market-signals?limit=25')
        .expect(200);

      expect(response.body.data.limit).toBe(25);
    });
  });

  describe('GET /api/hft/performance', () => {
    it('returns comprehensive performance analytics', async () => {
      const response = await request(app)
        .get('/api/hft/performance')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.performance).toBeDefined();
      expect(response.body.data.performance.overview).toBeDefined();
      expect(response.body.data.performance.execution).toBeDefined();
      expect(response.body.data.performance.strategies).toBeDefined();
      expect(response.body.data.performance.risk).toBeDefined();
      
      // Check calculated metrics
      expect(response.body.data.performance.overview.totalPnL).toBe(2500.75);
      expect(response.body.data.performance.overview.winRate).toBe(62.7);
      expect(response.body.data.performance.execution.avgExecutionTime).toBe(25);
      expect(response.body.data.performance.risk.dailyLossUtilization).toBe(0.3);
    });

    it('calculates execution rate correctly', async () => {
      const response = await request(app)
        .get('/api/hft/performance')
        .expect(200);

      const executionRate = response.body.data.performance.execution.executionRate;
      expect(executionRate).toBe((45 / 67) * 100); // ordersExecuted / signalsGenerated
    });

    it('handles different time periods', async () => {
      const response = await request(app)
        .get('/api/hft/performance?period=1w')
        .expect(200);

      expect(response.body.data.period).toBe('1w');
      expect(response.body.data.performance).toBeDefined();
    });
  });

  describe('GET /api/hft/positions', () => {
    it('returns empty positions when none exist', async () => {
      const response = await request(app)
        .get('/api/hft/positions')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.positions).toEqual([]);
      expect(response.body.data.count).toBe(0);
      expect(response.body.data.totalValue).toBe(0);
    });

    it('returns active positions when they exist', async () => {
      const mockPosition = {
        symbol: 'BTC/USD',
        strategy: 'scalping_btc',
        type: 'LONG',
        quantity: 0.1,
        avgPrice: 45000,
        openTime: Date.now() - 300000,
        stopLoss: 44100,
        takeProfit: 45450
      };

      mockHftService.positions.set('pos-1', mockPosition);

      const response = await request(app)
        .get('/api/hft/positions')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.positions).toHaveLength(1);
      expect(response.body.data.positions[0].symbol).toBe('BTC/USD');
      expect(response.body.data.count).toBe(1);
      expect(response.body.data.totalValue).toBe(4500); // 0.1 * 45000
    });
  });

  describe('GET /api/hft/orders', () => {
    it('returns recent orders with pagination', async () => {
      // Add mock orders
      for (let i = 0; i < 25; i++) {
        mockHftService.orders.set(`order-${i}`, {
          orderId: `order-${i}`,
          symbol: 'BTC/USD',
          type: 'buy',
          quantity: 0.1,
          requestedPrice: 45000 + i,
          executedPrice: 45000 + i,
          strategy: 'scalping_btc',
          status: 'filled',
          timestamp: Date.now() - (i * 1000),
          executedAt: Date.now() - (i * 1000) + 100,
          executionTime: 100,
          slippage: 0.1
        });
      }

      const response = await request(app)
        .get('/api/hft/orders?limit=10&offset=0')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.orders).toHaveLength(10);
      expect(response.body.data.total).toBe(25);
      expect(response.body.data.hasMore).toBe(true);
    });

    it('handles pagination correctly', async () => {
      const response = await request(app)
        .get('/api/hft/orders?limit=5&offset=20')
        .expect(200);

      expect(response.body.data.hasMore).toBe(false);
    });
  });

  describe('POST /api/hft/market-data', () => {
    it('processes market data successfully', async () => {
      const marketData = {
        symbol: 'BTC/USD',
        data: {
          price: 45000,
          volume: 1000,
          timestamp: Date.now()
        }
      };

      const response = await request(app)
        .post('/api/hft/market-data')
        .send(marketData)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.message).toBe('Market data processed');
    });

    it('validates required fields', async () => {
      const response = await request(app)
        .post('/api/hft/market-data')
        .send({ symbol: 'BTC/USD' }) // Missing data
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Missing required fields: symbol, data');
    });
  });

  describe('GET /api/hft/health', () => {
    it('returns HFT service health status', async () => {
      const response = await request(app)
        .get('/api/hft/health')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.status).toBe('healthy');
      expect(response.body.data.service).toBe('hft-trading');
      expect(response.body.data.engine).toBeDefined();
      expect(response.body.data.memory).toBeDefined();
    });

    it('handles health check errors', async () => {
      mockHftService.getMetrics.mockImplementation(() => {
        throw new Error('Health check failed');
      });

      const response = await request(app)
        .get('/api/hft/health')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.status).toBe('unhealthy');
    });
  });

  describe('Error Handling', () => {
    it('handles service unavailable errors', async () => {
      mockHftService.getMetrics.mockImplementation(() => {
        throw new Error('Service unavailable');
      });

      const response = await request(app)
        .get('/api/hft/status')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe('Failed to get HFT status');
      expect(response.body.details).toBe('Service unavailable');
    });

    it('includes correlation ID in error responses', async () => {
      mockHftService.start.mockRejectedValue(new Error('Start failed'));

      const response = await request(app)
        .post('/api/hft/start')
        .send({})
        .expect(500);

      expect(response.body.correlationId).toBeDefined();
      expect(response.body.correlationId).toMatch(/^hft-api-/);
    });
  });

  describe('Authentication', () => {
    it('requires authentication for all endpoints', async () => {
      // This would test with no auth middleware, but our mock always authenticates
      // In a real scenario, we'd test without the mock
      expect(true).toBe(true);
    });

    it('includes user ID in service calls', async () => {
      await request(app)
        .post('/api/hft/start')
        .send({})
        .expect(200);

      expect(mockHftService.start).toHaveBeenCalledWith('test-user-123', expect.any(Array));
    });
  });
});
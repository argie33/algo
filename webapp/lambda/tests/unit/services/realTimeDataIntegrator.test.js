/**
 * Unit Tests for Real-Time Data Integrator - Phase 4
 * Tests WebSocket connections, signal processing, and market data integration
 */

const { describe, it, expect, vi, beforeEach, afterEach } = require('vitest');
const RealTimeDataIntegrator = require('../../../services/realTimeDataIntegrator');
const EventEmitter = require('events');

// Mock WebSocket
class MockWebSocket extends EventEmitter {
  constructor(url) {
    super();
    this.url = url;
    this.readyState = 1; // OPEN
    this.CONNECTING = 0;
    this.OPEN = 1;
    this.CLOSING = 2;
    this.CLOSED = 3;
  }

  send(data) {
    this.lastSentData = data;
  }

  close() {
    this.readyState = this.CLOSED;
    this.emit('close');
  }
}

// Mock dependencies
vi.mock('ws', () => ({
  default: MockWebSocket
}));

vi.mock('../../../utils/structuredLogger', () => ({
  createLogger: vi.fn(() => ({
    info: vi.fn(),
    error: vi.fn(),
    warn: vi.fn(),
    debug: vi.fn()
  }))
}));

describe('RealTimeDataIntegrator - Phase 4', () => {
  let dataIntegrator;
  let mockWebSocket;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    
    dataIntegrator = new RealTimeDataIntegrator();
    
    // Mock WebSocket constructor to return our mock
    global.WebSocket = MockWebSocket;
  });

  afterEach(() => {
    vi.useRealTimers();
    if (dataIntegrator) {
      dataIntegrator.stop();
    }
  });

  describe('Initialization', () => {
    it('initializes with default configuration', () => {
      expect(dataIntegrator.config.reconnectDelay).toBe(5000);
      expect(dataIntegrator.config.maxReconnectAttempts).toBe(5);
      expect(dataIntegrator.config.heartbeatInterval).toBe(30000);
      expect(dataIntegrator.connections).toBeInstanceOf(Map);
      expect(dataIntegrator.subscriptions).toBeInstanceOf(Set);
    });

    it('initializes with custom configuration', () => {
      const customConfig = {
        reconnectDelay: 3000,
        maxReconnectAttempts: 3,
        heartbeatInterval: 20000
      };
      
      const integrator = new RealTimeDataIntegrator(customConfig);
      
      expect(integrator.config.reconnectDelay).toBe(3000);
      expect(integrator.config.maxReconnectAttempts).toBe(3);
      expect(integrator.config.heartbeatInterval).toBe(20000);
    });

    it('sets up performance metrics tracking', () => {
      expect(dataIntegrator.metrics.messagesReceived).toBe(0);
      expect(dataIntegrator.metrics.signalsGenerated).toBe(0);
      expect(dataIntegrator.metrics.latencyStats.count).toBe(0);
      expect(dataIntegrator.metrics.dataQuality.score).toBe(100);
    });
  });

  describe('Connection Management', () => {
    it('establishes WebSocket connection successfully', async () => {
      const credentials = {
        apiKey: 'test-api-key',
        secret: 'test-secret'
      };

      const promise = dataIntegrator.initialize(credentials);
      
      // Simulate connection open
      setTimeout(() => {
        const connection = Array.from(dataIntegrator.connections.values())[0];
        if (connection && connection.ws) {
          connection.ws.emit('open');
        }
      }, 10);

      await promise;

      expect(dataIntegrator.isConnected).toBe(true);
      expect(dataIntegrator.connections.size).toBe(1);
    });

    it('handles connection failures', async () => {
      const credentials = { apiKey: 'invalid-key' };

      const promise = dataIntegrator.initialize(credentials);
      
      // Simulate connection error
      setTimeout(() => {
        const connection = Array.from(dataIntegrator.connections.values())[0];
        if (connection && connection.ws) {
          connection.ws.emit('error', new Error('Connection failed'));
        }
      }, 10);

      await expect(promise).rejects.toThrow('Connection failed');
    });

    it('implements connection retry logic', async () => {
      const credentials = { apiKey: 'test-key' };
      
      let connectionAttempts = 0;
      const originalConnect = dataIntegrator.connectToProvider;
      dataIntegrator.connectToProvider = vi.fn().mockImplementation(() => {
        connectionAttempts++;
        if (connectionAttempts < 3) {
          throw new Error('Connection failed');
        }
        return originalConnect.call(dataIntegrator, 'alpaca', credentials);
      });

      await dataIntegrator.initialize(credentials);
      
      expect(connectionAttempts).toBe(3);
    });

    it('manages multiple provider connections', async () => {
      const credentials = {
        alpaca: { apiKey: 'alpaca-key' },
        polygon: { apiKey: 'polygon-key' }
      };

      await dataIntegrator.initialize(credentials);

      expect(dataIntegrator.connections.size).toBe(2);
      expect(dataIntegrator.connections.has('alpaca')).toBe(true);
      expect(dataIntegrator.connections.has('polygon')).toBe(true);
    });
  });

  describe('Market Data Processing', () => {
    beforeEach(async () => {
      const credentials = { apiKey: 'test-key' };
      await dataIntegrator.initialize(credentials);
    });

    it('processes incoming market data messages', () => {
      const mockData = {
        T: 't', // Trade message
        S: 'AAPL',
        p: 150.25,
        s: 100,
        t: Date.now() * 1000000 // nanoseconds
      };

      const connection = Array.from(dataIntegrator.connections.values())[0];
      connection.ws.emit('message', JSON.stringify([mockData]));

      expect(dataIntegrator.metrics.messagesReceived).toBe(1);
    });

    it('generates trading signals from market data', (done) => {
      const mockData = {
        T: 't',
        S: 'BTC/USD',
        p: 45000,
        s: 1000,
        t: Date.now() * 1000000
      };

      dataIntegrator.on('signal', (signal) => {
        expect(signal.symbol).toBe('BTC/USD');
        expect(signal.type).toBeDefined();
        expect(signal.strength).toBeGreaterThan(0);
        expect(signal.price).toBe(45000);
        done();
      });

      const connection = Array.from(dataIntegrator.connections.values())[0];
      connection.ws.emit('message', JSON.stringify([mockData]));
    });

    it('calculates signal strength based on market conditions', () => {
      const highVolumeData = {
        T: 't',
        S: 'AAPL',
        p: 150.25,
        s: 10000, // High volume
        t: Date.now() * 1000000
      };

      const signalStrength = dataIntegrator.calculateSignalStrength(highVolumeData, {});
      expect(signalStrength).toBeGreaterThan(0.5);
    });

    it('filters out low-quality signals', () => {
      const lowQualityData = {
        T: 't',
        S: 'PENNY',
        p: 0.01,
        s: 10, // Very low volume
        t: Date.now() * 1000000
      };

      const signalStrength = dataIntegrator.calculateSignalStrength(lowQualityData, {});
      expect(signalStrength).toBeLessThan(0.3);
    });

    it('tracks data quality metrics', () => {
      const goodData = {
        T: 't',
        S: 'AAPL',
        p: 150.25,
        s: 1000,
        t: Date.now() * 1000000
      };

      const incompleteData = {
        T: 't',
        S: 'AAPL',
        // Missing price and size
        t: Date.now() * 1000000
      };

      dataIntegrator.updateDataQuality(goodData);
      dataIntegrator.updateDataQuality(incompleteData);

      expect(dataIntegrator.metrics.dataQuality.score).toBeLessThan(100);
      expect(dataIntegrator.metrics.dataQuality.totalMessages).toBe(2);
    });
  });

  describe('Subscription Management', () => {
    beforeEach(async () => {
      const credentials = { apiKey: 'test-key' };
      await dataIntegrator.initialize(credentials);
    });

    it('subscribes to symbol data feeds', () => {
      const symbols = ['AAPL', 'GOOGL', 'MSFT'];
      
      dataIntegrator.subscribe(symbols);

      expect(dataIntegrator.subscriptions.size).toBe(3);
      symbols.forEach(symbol => {
        expect(dataIntegrator.subscriptions.has(symbol)).toBe(true);
      });
    });

    it('sends subscription messages to WebSocket', () => {
      const symbols = ['BTC/USD'];
      
      dataIntegrator.subscribe(symbols);

      const connection = Array.from(dataIntegrator.connections.values())[0];
      expect(connection.ws.lastSentData).toContain('BTC/USD');
    });

    it('unsubscribes from symbol data feeds', () => {
      dataIntegrator.subscribe(['AAPL', 'GOOGL']);
      expect(dataIntegrator.subscriptions.size).toBe(2);

      dataIntegrator.unsubscribe(['AAPL']);
      expect(dataIntegrator.subscriptions.size).toBe(1);
      expect(dataIntegrator.subscriptions.has('GOOGL')).toBe(true);
    });

    it('handles duplicate subscriptions gracefully', () => {
      dataIntegrator.subscribe(['AAPL']);
      dataIntegrator.subscribe(['AAPL']); // Duplicate

      expect(dataIntegrator.subscriptions.size).toBe(1);
    });
  });

  describe('Signal Generation', () => {
    beforeEach(async () => {
      const credentials = { apiKey: 'test-key' };
      await dataIntegrator.initialize(credentials);
    });

    it('generates buy signals on price momentum', (done) => {
      const symbolHistory = new Map();
      symbolHistory.set('AAPL', {
        prices: [148, 149, 150, 151], // Upward trend
        volumes: [1000, 1100, 1200, 1300],
        lastUpdate: Date.now() - 5000
      });
      
      dataIntegrator.symbolHistory = symbolHistory;

      dataIntegrator.on('signal', (signal) => {
        expect(signal.type).toBe('buy');
        expect(signal.strength).toBeGreaterThan(0.5);
        done();
      });

      const tradeData = {
        T: 't',
        S: 'AAPL',
        p: 152, // Higher than trend
        s: 1400,
        t: Date.now() * 1000000
      };

      const connection = Array.from(dataIntegrator.connections.values())[0];
      connection.ws.emit('message', JSON.stringify([tradeData]));
    });

    it('generates sell signals on price decline', (done) => {
      const symbolHistory = new Map();
      symbolHistory.set('AAPL', {
        prices: [155, 154, 153, 152], // Downward trend
        volumes: [1000, 1100, 1200, 1300],
        lastUpdate: Date.now() - 5000
      });
      
      dataIntegrator.symbolHistory = symbolHistory;

      dataIntegrator.on('signal', (signal) => {
        expect(signal.type).toBe('sell');
        expect(signal.strength).toBeGreaterThan(0.5);
        done();
      });

      const tradeData = {
        T: 't',
        S: 'AAPL',
        p: 151, // Lower than trend
        s: 1400,
        t: Date.now() * 1000000
      };

      const connection = Array.from(dataIntegrator.connections.values())[0];
      connection.ws.emit('message', JSON.stringify([tradeData]));
    });

    it('includes technical indicators in signals', (done) => {
      dataIntegrator.on('signal', (signal) => {
        expect(signal.indicators).toBeDefined();
        expect(signal.indicators.rsi).toBeDefined();
        expect(signal.indicators.momentum).toBeDefined();
        expect(signal.indicators.volumeRatio).toBeDefined();
        done();
      });

      const tradeData = {
        T: 't',
        S: 'AAPL',
        p: 150,
        s: 2000,
        t: Date.now() * 1000000
      };

      const connection = Array.from(dataIntegrator.connections.values())[0];
      connection.ws.emit('message', JSON.stringify([tradeData]));
    });
  });

  describe('Performance Monitoring', () => {
    beforeEach(async () => {
      const credentials = { apiKey: 'test-key' };
      await dataIntegrator.initialize(credentials);
    });

    it('tracks message processing latency', () => {
      const tradeData = {
        T: 't',
        S: 'AAPL',
        p: 150,
        s: 1000,
        t: (Date.now() - 50) * 1000000 // 50ms ago
      };

      const connection = Array.from(dataIntegrator.connections.values())[0];
      connection.ws.emit('message', JSON.stringify([tradeData]));

      expect(dataIntegrator.metrics.latencyStats.count).toBe(1);
      expect(dataIntegrator.metrics.latencyStats.avg).toBeGreaterThan(0);
    });

    it('calculates throughput metrics', () => {
      // Send multiple messages
      for (let i = 0; i < 10; i++) {
        const tradeData = {
          T: 't',
          S: 'AAPL',
          p: 150 + i,
          s: 1000,
          t: Date.now() * 1000000
        };

        const connection = Array.from(dataIntegrator.connections.values())[0];
        connection.ws.emit('message', JSON.stringify([tradeData]));
      }

      expect(dataIntegrator.metrics.messagesReceived).toBe(10);
      expect(dataIntegrator.metrics.throughput.messagesPerSecond).toBeGreaterThan(0);
    });

    it('monitors connection health', () => {
      const healthMetrics = dataIntegrator.getHealthMetrics();

      expect(healthMetrics.connectionStatus).toBe('active');
      expect(healthMetrics.connections.total).toBe(1);
      expect(healthMetrics.connections.healthy).toBe(1);
      expect(healthMetrics.subscriptions.active).toBe(0);
    });
  });

  describe('Error Handling', () => {
    beforeEach(async () => {
      const credentials = { apiKey: 'test-key' };
      await dataIntegrator.initialize(credentials);
    });

    it('handles malformed WebSocket messages', () => {
      const connection = Array.from(dataIntegrator.connections.values())[0];
      
      // Should not throw
      expect(() => {
        connection.ws.emit('message', 'invalid json');
      }).not.toThrow();

      expect(dataIntegrator.metrics.errors.parseErrors).toBe(1);
    });

    it('handles connection drops gracefully', async () => {
      const connection = Array.from(dataIntegrator.connections.values())[0];
      
      // Simulate connection drop
      connection.ws.readyState = connection.ws.CLOSED;
      connection.ws.emit('close');

      // Should attempt reconnection
      vi.advanceTimersByTime(6000); // Advance past reconnect delay

      expect(dataIntegrator.metrics.errors.connectionDrops).toBe(1);
    });

    it('limits reconnection attempts', async () => {
      const connection = Array.from(dataIntegrator.connections.values())[0];
      
      // Mock failed reconnections
      dataIntegrator.connectToProvider = vi.fn().mockRejectedValue(new Error('Failed'));

      // Simulate multiple connection drops
      for (let i = 0; i < 10; i++) {
        connection.ws.emit('close');
        vi.advanceTimersByTime(6000);
      }

      // Should stop trying after max attempts
      expect(dataIntegrator.connectToProvider).toHaveBeenCalledTimes(5); // maxReconnectAttempts
    });

    it('handles data processing errors gracefully', () => {
      // Mock error in signal generation
      const originalMethod = dataIntegrator.generateTradingSignal;
      dataIntegrator.generateTradingSignal = vi.fn().mockImplementation(() => {
        throw new Error('Signal generation failed');
      });

      const tradeData = {
        T: 't',
        S: 'AAPL',
        p: 150,
        s: 1000,
        t: Date.now() * 1000000
      };

      const connection = Array.from(dataIntegrator.connections.values())[0];
      
      expect(() => {
        connection.ws.emit('message', JSON.stringify([tradeData]));
      }).not.toThrow();

      expect(dataIntegrator.metrics.errors.processingErrors).toBe(1);
    });
  });

  describe('Heartbeat and Connection Maintenance', () => {
    beforeEach(async () => {
      const credentials = { apiKey: 'test-key' };
      await dataIntegrator.initialize(credentials);
    });

    it('sends periodic heartbeat messages', () => {
      const connection = Array.from(dataIntegrator.connections.values())[0];
      
      // Advance time to trigger heartbeat
      vi.advanceTimersByTime(31000); // Past heartbeat interval

      expect(connection.ws.lastSentData).toContain('ping');
    });

    it('detects stale connections', () => {
      const connection = Array.from(dataIntegrator.connections.values())[0];
      
      // Simulate no messages for extended period
      connection.lastActivity = Date.now() - 120000; // 2 minutes ago
      
      vi.advanceTimersByTime(31000);

      expect(dataIntegrator.metrics.warnings.staleConnections).toBe(1);
    });
  });

  describe('Metrics and Reporting', () => {
    beforeEach(async () => {
      const credentials = { apiKey: 'test-key' };
      await dataIntegrator.initialize(credentials);
    });

    it('provides comprehensive metrics', () => {
      const metrics = dataIntegrator.getMetrics();

      expect(metrics.messagesReceived).toBeDefined();
      expect(metrics.signalsGenerated).toBeDefined();
      expect(metrics.latencyStats).toBeDefined();
      expect(metrics.throughput).toBeDefined();
      expect(metrics.dataQuality).toBeDefined();
      expect(metrics.errors).toBeDefined();
      expect(metrics.connections).toBeDefined();
    });

    it('resets metrics when requested', () => {
      // Generate some metrics
      dataIntegrator.metrics.messagesReceived = 100;
      dataIntegrator.metrics.signalsGenerated = 50;

      dataIntegrator.resetMetrics();

      expect(dataIntegrator.metrics.messagesReceived).toBe(0);
      expect(dataIntegrator.metrics.signalsGenerated).toBe(0);
      expect(dataIntegrator.metrics.latencyStats.count).toBe(0);
    });
  });

  describe('Shutdown and Cleanup', () => {
    it('closes all connections on shutdown', async () => {
      const credentials = {
        alpaca: { apiKey: 'alpaca-key' },
        polygon: { apiKey: 'polygon-key' }
      };
      
      await dataIntegrator.initialize(credentials);
      expect(dataIntegrator.connections.size).toBe(2);

      await dataIntegrator.stop();

      expect(dataIntegrator.isConnected).toBe(false);
      expect(dataIntegrator.connections.size).toBe(0);
      expect(dataIntegrator.subscriptions.size).toBe(0);
    });

    it('clears all timers and intervals', async () => {
      const credentials = { apiKey: 'test-key' };
      await dataIntegrator.initialize(credentials);

      const clearIntervalSpy = vi.spyOn(global, 'clearInterval');
      const clearTimeoutSpy = vi.spyOn(global, 'clearTimeout');

      await dataIntegrator.stop();

      expect(clearIntervalSpy).toHaveBeenCalled();
      expect(clearTimeoutSpy).toHaveBeenCalled();
    });

    it('handles shutdown errors gracefully', async () => {
      const credentials = { apiKey: 'test-key' };
      await dataIntegrator.initialize(credentials);

      const connection = Array.from(dataIntegrator.connections.values())[0];
      connection.ws.close = vi.fn().mockImplementation(() => {
        throw new Error('Close failed');
      });

      // Should not throw
      await expect(dataIntegrator.stop()).resolves.toBeUndefined();
    });
  });
});
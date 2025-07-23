/**
 * Live Data Service Integration Tests
 * Tests real WebSocket connectivity, authentication flow, and end-to-end functionality
 */

import { vi } from 'vitest';
import liveDataService, { LiveDataService } from '../../../services/liveDataService.js';
import { PERFORMANCE_CONFIG } from '../../../config/environment.js';

// Mock WebSocket with more realistic behavior for integration tests
class MockWebSocketServer {
  constructor() {
    this.clients = new Set();
    this.isRunning = false;
  }
  
  start() {
    this.isRunning = true;
  }
  
  stop() {
    this.isRunning = false;
    this.clients.forEach(client => client.close());
    this.clients.clear();
  }
  
  addClient(ws) {
    this.clients.add(ws);
  }
  
  removeClient(ws) {
    this.clients.delete(ws);
  }
  
  broadcast(message) {
    const data = JSON.stringify(message);
    this.clients.forEach(client => {
      if (client.readyState === WebSocket.OPEN) {
        client.simulateMessage(message);
      }
    });
  }
  
  sendToClient(ws, message) {
    if (ws.readyState === WebSocket.OPEN) {
      ws.simulateMessage(message);
    }
  }
}

const mockServer = new MockWebSocketServer();

// Enhanced WebSocket mock for integration testing
global.WebSocket = class MockWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = WebSocket.CONNECTING;
    this.binaryType = 'blob';
    this.onopen = null;
    this.onclose = null;
    this.onmessage = null;
    this.onerror = null;
    this.sentMessages = [];
    
    // Add to mock server
    mockServer.addClient(this);
    
    // Simulate connection with authentication validation
    setTimeout(() => {
      if (this.url.includes('token=') && this.url.includes('userId=')) {
        this.readyState = WebSocket.OPEN;
        if (this.onopen) {
          this.onopen({ type: 'open' });
        }
      } else {
        this.readyState = WebSocket.CLOSED;
        if (this.onerror) {
          this.onerror({ error: new Error('Authentication failed'), type: 'error' });
        }
      }
    }, 10);
  }
  
  send(data) {
    this.sentMessages.push(JSON.parse(data));
    
    // Simulate server responses
    const message = JSON.parse(data);
    setTimeout(() => {
      switch (message.action) {
        case 'ping':
          this.simulateMessage({
            type: 'pong',
            timestamp: Date.now()
          });
          break;
          
        case 'subscribe':
          this.simulateMessage({
            type: 'subscribed',
            channel: message.channel,
            symbols: message.symbols,
            success: true
          });
          
          // Send initial market data
          if (message.channel === 'market_data' && message.symbols) {
            message.symbols.forEach(symbol => {
              setTimeout(() => {
                this.simulateMessage({
                  type: 'market_data',
                  symbol: symbol,
                  data: {
                    price: 100 + Math.random() * 100,
                    volume: Math.floor(Math.random() * 1000000),
                    timestamp: Date.now()
                  }
                });
              }, 50);
            });
          }
          break;
          
        case 'unsubscribe':
          this.simulateMessage({
            type: 'unsubscribed',
            channel: message.channel,
            symbols: message.symbols,
            success: true
          });
          break;
      }
    }, 5);
  }
  
  close(code = 1000, reason = '') {
    this.readyState = WebSocket.CLOSED;
    mockServer.removeClient(this);
    if (this.onclose) {
      this.onclose({ code, reason, type: 'close' });
    }
  }
  
  simulateMessage(data) {
    if (this.onmessage && this.readyState === WebSocket.OPEN) {
      this.onmessage({ data: JSON.stringify(data), type: 'message' });
    }
  }
  
  simulateError(error) {
    if (this.onerror) {
      this.onerror({ error, type: 'error' });
    }
  }
};

global.WebSocket.CONNECTING = 0;
global.WebSocket.OPEN = 1;
global.WebSocket.CLOSING = 2;
global.WebSocket.CLOSED = 3;

// Mock environment with WebSocket enabled
vi.mock('../../../config/environment.js', () => ({
  PERFORMANCE_CONFIG: {
    websocket: {
      enabled: true,
      url: 'wss://test-api.protrade.com/ws',
      reconnectInterval: 1000,
      maxReconnectAttempts: 3,
      heartbeatInterval: 5000,
      connectionTimeout: 5000,
      messageTimeout: 2000,
      autoConnect: false,
      enableHealthCheck: true,
      healthCheckInterval: 2000
    }
  }
}));

// Mock localStorage with authentication token
const localStorageMock = {
  getItem: vi.fn((key) => {
    if (key === 'accessToken' || key === 'authToken') {
      return 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXItMTIzIiwidXNlcklkIjoidGVzdC11c2VyLTEyMyIsImV4cCI6MTYzMjE2MDAwMH0.signature';
    }
    return null;
  }),
  setItem: vi.fn(),
  clear: vi.fn()
};
global.localStorage = localStorageMock;

// Mock JWT decoding
global.atob = vi.fn((str) => {
  return JSON.stringify({ sub: 'test-user-123', userId: 'test-user-123', exp: 1632160000 });
});

describe('Live Data Service Integration Tests', () => {
  let service;
  
  beforeAll(() => {
    mockServer.start();
  });
  
  afterAll(() => {
    mockServer.stop();
  });
  
  beforeEach(() => {
    vi.clearAllMocks();
    service = new LiveDataService();
    vi.clearAllTimers();
  });
  
  afterEach(() => {
    service.cleanup();
    vi.clearAllTimers();
  });

  describe('End-to-End Connection Flow', () => {
    test('completes full authentication and connection flow', async () => {
      const connectedSpy = vi.fn();
      const configErrorSpy = vi.fn();
      
      service.on('connected', connectedSpy);
      service.on('configurationError', configErrorSpy);
      
      await service.connect('test-user-123');
      await new Promise(resolve => setTimeout(resolve, 30));
      
      expect(configErrorSpy).not.toHaveBeenCalled();
      expect(connectedSpy).toHaveBeenCalled();
      expect(service.isConnected()).toBe(true);
      expect(service.ws.url).toContain('userId=test-user-123');
      expect(service.ws.url).toContain('token=');
    });

    test('handles authentication failure gracefully', async () => {
      // Mock invalid token
      localStorageMock.getItem.mockReturnValue(null);
      
      const authErrorSpy = vi.fn();
      service.on('authenticationError', authErrorSpy);
      
      await service.connect();
      
      expect(authErrorSpy).toHaveBeenCalledWith('Authentication token required for WebSocket connection');
      expect(service.isConnected()).toBe(false);
    });
  });

  describe('Real-Time Market Data Flow', () => {
    beforeEach(async () => {
      await service.connect('test-user-123');
      await new Promise(resolve => setTimeout(resolve, 30));
    });

    test('subscribes and receives real-time market data', async () => {
      const marketDataSpy = vi.fn();
      const subscribedSpy = vi.fn();
      
      service.on('marketData', marketDataSpy);
      service.on('subscribed', subscribedSpy);
      
      service.subscribe(['AAPL', 'MSFT'], 'market_data');
      
      // Wait for subscription confirmation and initial data
      await new Promise(resolve => setTimeout(resolve, 100));
      
      expect(subscribedSpy).toHaveBeenCalledWith({
        type: 'subscribed',
        channel: 'market_data',
        symbols: ['AAPL', 'MSFT'],
        success: true
      });
      
      // Should receive market data for both symbols
      expect(marketDataSpy).toHaveBeenCalledWith({
        symbol: 'AAPL',
        data: expect.objectContaining({
          price: expect.any(Number),
          volume: expect.any(Number),
          timestamp: expect.any(Number)
        })
      });
      
      expect(marketDataSpy).toHaveBeenCalledWith({
        symbol: 'MSFT',
        data: expect.objectContaining({
          price: expect.any(Number),
          volume: expect.any(Number),
          timestamp: expect.any(Number)
        })
      });
      
      // Check that data is cached
      const aaplData = service.getMarketData('AAPL');
      const msftData = service.getMarketData('MSFT');
      
      expect(aaplData).toBeTruthy();
      expect(msftData).toBeTruthy();
      expect(aaplData.price).toBeGreaterThan(0);
      expect(msftData.price).toBeGreaterThan(0);
    });

    test('handles symbol-specific market data events', async () => {
      const aaplDataSpy = vi.fn();
      const msftDataSpy = vi.fn();
      
      service.on('marketData:AAPL', aaplDataSpy);
      service.on('marketData:MSFT', msftDataSpy);
      
      service.subscribe(['AAPL', 'MSFT']);
      
      await new Promise(resolve => setTimeout(resolve, 100));
      
      expect(aaplDataSpy).toHaveBeenCalledWith(expect.objectContaining({
        price: expect.any(Number),
        volume: expect.any(Number)
      }));
      
      expect(msftDataSpy).toHaveBeenCalledWith(expect.objectContaining({
        price: expect.any(Number),
        volume: expect.any(Number)
      }));
    });

    test('unsubscribes from market data', async () => {
      const unsubscribedSpy = vi.fn();
      service.on('unsubscribed', unsubscribedSpy);
      
      // First subscribe
      service.subscribe(['AAPL']);
      await new Promise(resolve => setTimeout(resolve, 50));
      
      // Then unsubscribe
      service.unsubscribe(['AAPL']);
      await new Promise(resolve => setTimeout(resolve, 50));
      
      expect(unsubscribedSpy).toHaveBeenCalledWith({
        type: 'unsubscribed',
        channel: 'market_data',
        symbols: ['AAPL'],
        success: true
      });
      
      expect(service.subscriptions.has('AAPL')).toBe(false);
    });
  });

  describe('Portfolio Data Integration', () => {
    beforeEach(async () => {
      await service.connect('test-user-123');
      await new Promise(resolve => setTimeout(resolve, 30));
    });

    test('subscribes to portfolio updates', async () => {
      const portfolioUpdateSpy = vi.fn();
      const portfolioSpecificSpy = vi.fn();
      
      service.on('portfolioUpdate', portfolioUpdateSpy);
      service.subscribeToPortfolio('test-user-123', 'api-key-456', portfolioSpecificSpy);
      
      await new Promise(resolve => setTimeout(resolve, 50));
      
      // Simulate server sending portfolio update
      mockServer.sendToClient(service.ws, {
        type: 'portfolio_update',
        userId: 'test-user-123',
        apiKeyId: 'api-key-456',
        portfolio: {
          totalValue: 125000,
          dayChange: 2500,
          positions: [
            { symbol: 'AAPL', shares: 100, value: 15000 },
            { symbol: 'MSFT', shares: 50, value: 10000 }
          ]
        }
      });
      
      await new Promise(resolve => setTimeout(resolve, 20));
      
      expect(portfolioUpdateSpy).toHaveBeenCalledWith({
        userId: 'test-user-123',
        apiKeyId: 'api-key-456',
        portfolio: expect.objectContaining({
          totalValue: 125000,
          dayChange: 2500,
          positions: expect.any(Array)
        })
      });
      
      expect(portfolioSpecificSpy).toHaveBeenCalledWith({
        type: 'portfolio_update',
        data: expect.objectContaining({
          totalValue: 125000,
          dayChange: 2500
        })
      });
    });

    test('handles portfolio holdings updates', async () => {
      const holdingsUpdateSpy = vi.fn();
      service.on('portfolioHoldings', holdingsUpdateSpy);
      
      await service.connect();
      await new Promise(resolve => setTimeout(resolve, 30));
      
      // Simulate holdings update
      mockServer.sendToClient(service.ws, {
        type: 'portfolio_holdings',
        userId: 'test-user-123',
        apiKeyId: 'api-key-456',
        holdings: [
          { symbol: 'AAPL', shares: 100, avgCost: 140.50, currentPrice: 150.25 },
          { symbol: 'MSFT', shares: 50, avgCost: 180.00, currentPrice: 200.75 }
        ]
      });
      
      await new Promise(resolve => setTimeout(resolve, 20));
      
      expect(holdingsUpdateSpy).toHaveBeenCalledWith({
        userId: 'test-user-123',
        apiKeyId: 'api-key-456',
        holdings: expect.arrayContaining([
          expect.objectContaining({ symbol: 'AAPL', shares: 100 }),
          expect.objectContaining({ symbol: 'MSFT', shares: 50 })
        ])
      });
    });
  });

  describe('Heartbeat and Connection Health', () => {
    beforeEach(async () => {
      await service.connect('test-user-123');
      await new Promise(resolve => setTimeout(resolve, 30));
    });

    test('sends heartbeat pings and receives pongs', async () => {
      const pongSpy = vi.fn();
      service.on('pong', pongSpy);
      
      // Manually trigger heartbeat
      service.sendMessage({
        action: 'ping',
        timestamp: Date.now()
      });
      
      await new Promise(resolve => setTimeout(resolve, 30));
      
      expect(pongSpy).toHaveBeenCalledWith(expect.objectContaining({
        type: 'pong',
        latency: expect.any(Number),
        timestamp: expect.any(Number)
      }));
      
      expect(service.metrics.lastLatency).toBeGreaterThan(0);
      expect(service.metrics.lastPongTime).toBeTruthy();
    });

    test('maintains connection quality metrics', async () => {
      // Send multiple pings to establish quality baseline
      for (let i = 0; i < 3; i++) {
        service.sendMessage({ action: 'ping', timestamp: Date.now() });
        await new Promise(resolve => setTimeout(resolve, 30));
      }
      
      const metrics = service.getMetrics();
      
      expect(metrics.avgLatency).toBeGreaterThan(0);
      expect(metrics.messagesReceived).toBeGreaterThanOrEqual(3);
      expect(metrics.messagesSent).toBeGreaterThanOrEqual(3);
      expect(metrics.connectionQuality).toBeTruthy();
      expect(metrics.isHealthy).toBe(true);
    });
  });

  describe('Error Recovery and Resilience', () => {
    test('recovers from temporary connection loss', async () => {
      vi.useFakeTimers();
      
      await service.connect('test-user-123');
      await new Promise(resolve => setTimeout(resolve, 30));
      
      expect(service.isConnected()).toBe(true);
      
      const reconnectingSpy = vi.fn();
      const connectedSpy = vi.fn();
      
      service.on('reconnecting', reconnectingSpy);
      service.on('connected', connectedSpy);
      
      // Enable auto-reconnect for this test
      service.config.enableAutoReconnect = true;
      
      // Simulate connection loss
      service.ws.close(1006, 'Connection lost');
      
      expect(service.isConnected()).toBe(false);
      
      // Fast-forward to trigger reconnection
      vi.advanceTimersByTime(1000);
      
      // Allow reconnection to complete
      await new Promise(resolve => setTimeout(resolve, 50));
      
      expect(reconnectingSpy).toHaveBeenCalled();
      
      vi.useRealTimers();
    });

    test('handles server error messages gracefully', async () => {
      await service.connect('test-user-123');
      await new Promise(resolve => setTimeout(resolve, 30));
      
      const serverErrorSpy = vi.fn();
      service.on('serverError', serverErrorSpy);
      
      // Simulate server error
      mockServer.sendToClient(service.ws, {
        type: 'error',
        code: 'RATE_LIMIT_EXCEEDED',
        message: 'Too many requests. Please slow down.',
        retryAfter: 60
      });
      
      await new Promise(resolve => setTimeout(resolve, 20));
      
      expect(serverErrorSpy).toHaveBeenCalledWith({
        type: 'error',
        code: 'RATE_LIMIT_EXCEEDED',
        message: 'Too many requests. Please slow down.',
        retryAfter: 60
      });
    });
  });

  describe('Performance and Scalability', () => {
    beforeEach(async () => {
      await service.connect('test-user-123');
      await new Promise(resolve => setTimeout(resolve, 30));
    });

    test('handles high-frequency market data updates', async () => {
      const marketDataSpy = vi.fn();
      service.on('marketData', marketDataSpy);
      
      service.subscribe(['AAPL']);
      await new Promise(resolve => setTimeout(resolve, 50));
      
      // Simulate rapid market data updates
      const updates = 50;
      for (let i = 0; i < updates; i++) {
        mockServer.sendToClient(service.ws, {
          type: 'market_data',
          symbol: 'AAPL',
          data: {
            price: 150 + Math.random() * 10,
            volume: Math.floor(Math.random() * 1000000),
            timestamp: Date.now() + i
          }
        });
      }
      
      await new Promise(resolve => setTimeout(resolve, 100));
      
      expect(marketDataSpy).toHaveBeenCalledTimes(updates + 1); // +1 for initial subscription data
      expect(service.metrics.messagesReceived).toBeGreaterThanOrEqual(updates);
      expect(service.marketData.get('AAPL')).toBeTruthy();
    });

    test('manages memory efficiently with large datasets', async () => {
      // Subscribe to multiple symbols
      const symbols = Array.from({ length: 20 }, (_, i) => `STOCK${i}`);
      service.subscribe(symbols);
      
      await new Promise(resolve => setTimeout(resolve, 50));
      
      // Simulate data for all symbols
      symbols.forEach(symbol => {
        mockServer.sendToClient(service.ws, {
          type: 'market_data',
          symbol: symbol,
          data: {
            price: Math.random() * 100,
            volume: Math.floor(Math.random() * 1000000),
            timestamp: Date.now()
          }
        });
      });
      
      await new Promise(resolve => setTimeout(resolve, 100));
      
      expect(service.marketData.size).toBe(symbols.length);
      expect(service.subscriptions.size).toBe(symbols.length);
      
      const metrics = service.getMetrics();
      expect(metrics.cachedSymbols).toBe(symbols.length);
      expect(metrics.subscriptionsCount).toBe(symbols.length);
    });
  });

  describe('Configuration Integration', () => {
    test('respects configuration settings', () => {
      expect(service.config.wsUrl).toBe('wss://test-api.protrade.com/ws');
      expect(service.config.heartbeatInterval).toBe(5000);
      expect(service.config.connectionTimeout).toBe(5000);
      expect(service.config.maxReconnectAttempts).toBe(3);
      expect(service.config.enableAutoReconnect).toBe(false);
      expect(service.config.enableConnectionHealthCheck).toBe(true);
    });

    test('validates configuration on startup', () => {
      const health = service.healthCheck();
      
      expect(health.config.wsUrl).toBe('configured');
      expect(health.config.autoReconnect).toBe(false);
      expect(health.config.healthCheck).toBe(true);
    });
  });

  describe('Data Persistence and Caching', () => {
    beforeEach(async () => {
      await service.connect('test-user-123');
      await new Promise(resolve => setTimeout(resolve, 30));
    });

    test('maintains data consistency across updates', async () => {
      service.subscribe(['AAPL']);
      await new Promise(resolve => setTimeout(resolve, 50));
      
      // Send multiple updates for the same symbol
      const updates = [
        { price: 150.00, volume: 1000000 },
        { price: 150.50, volume: 1200000 },
        { price: 151.00, volume: 1500000 }
      ];
      
      for (const update of updates) {
        mockServer.sendToClient(service.ws, {
          type: 'market_data',
          symbol: 'AAPL',
          data: { ...update, timestamp: Date.now() }
        });
        await new Promise(resolve => setTimeout(resolve, 10));
      }
      
      const latestData = service.getMarketData('AAPL');
      expect(latestData.price).toBe(151.00);
      expect(latestData.volume).toBe(1500000);
      expect(latestData.receivedAt).toBeTruthy();
    });

    test('handles data staleness correctly', async () => {
      service.subscribe(['AAPL']);
      await new Promise(resolve => setTimeout(resolve, 50));
      
      // Get initial data
      let data = service.getMarketData('AAPL');
      expect(service.isDataStale('AAPL', 60000)).toBe(false);
      
      // Manually set old timestamp to simulate stale data
      data.receivedAt = Date.now() - 120000; // 2 minutes ago
      
      expect(service.isDataStale('AAPL', 60000)).toBe(true);
    });
  });
});
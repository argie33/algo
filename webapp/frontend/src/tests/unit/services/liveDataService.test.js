/**
 * Live Data Service Unit Tests
 * Tests WebSocket connectivity, message handling, and real-time data functionality
 */

import liveDataService, { LiveDataService } from '../../../services/liveDataService.js';
import { PERFORMANCE_CONFIG } from '../../../config/environment.js';

// Mock WebSocket
global.WebSocket = class MockWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = WebSocket.CONNECTING;
    this.binaryType = 'blob';
    this.onopen = null;
    this.onclose = null;
    this.onmessage = null;
    this.onerror = null;
    
    // Mock constants
    MockWebSocket.CONNECTING = 0;
    MockWebSocket.OPEN = 1;
    MockWebSocket.CLOSING = 2;
    MockWebSocket.CLOSED = 3;
    
    // Simulate connection after a short delay
    setTimeout(() => {
      this.readyState = WebSocket.OPEN;
      if (this.onopen) {
        this.onopen({ type: 'open' });
      }
    }, 10);
  }
  
  send(data) {
    this.lastSentMessage = data;
  }
  
  close(code = 1000, reason = '') {
    this.readyState = WebSocket.CLOSED;
    if (this.onclose) {
      this.onclose({ code, reason, type: 'close' });
    }
  }
  
  // Helper method to simulate receiving a message
  simulateMessage(data) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data), type: 'message' });
    }
  }
  
  // Helper method to simulate an error
  simulateError(error) {
    if (this.onerror) {
      this.onerror({ error, type: 'error' });
    }
  }
};

// Add static constants to the class
global.WebSocket.CONNECTING = 0;
global.WebSocket.OPEN = 1;
global.WebSocket.CLOSING = 2;
global.WebSocket.CLOSED = 3;

import { vi } from 'vitest';

// Mock environment configuration
vi.mock('../../../config/environment.js', () => ({
  PERFORMANCE_CONFIG: {
    websocket: {
      enabled: true,
      url: 'wss://test-api.protrade.com/ws',
      reconnectInterval: 1000,
      maxReconnectAttempts: 3,
      heartbeatInterval: 10000,
      connectionTimeout: 5000,
      messageTimeout: 2000,
      autoConnect: false,
      enableHealthCheck: true,
      healthCheckInterval: 2000
    }
  }
}));

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  clear: vi.fn()
};
global.localStorage = localStorageMock;

// Mock atob for JWT decoding
global.atob = vi.fn((str) => {
  // Mock JWT payload
  if (str === 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9') {
    return JSON.stringify({ sub: 'test-user-123', userId: 'test-user-123' });
  }
  return Buffer.from(str, 'base64').toString();
});

describe('LiveDataService', () => {
  let service;
  
  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.getItem.mockReturnValue('test.token.here');
    
    // Create a fresh instance for each test
    service = new LiveDataService();
    
    // Clear any existing timers
    vi.clearAllTimers();
  });
  
  afterEach(() => {
    service.cleanup();
    vi.clearAllTimers();
  });

  describe('Service Initialization', () => {
    test('initializes with correct default configuration from environment', () => {
      expect(service.config.wsUrl).toBe('wss://test-api.protrade.com/ws');
      expect(service.config.heartbeatInterval).toBe(10000);
      expect(service.config.connectionTimeout).toBe(5000);
      expect(service.config.maxReconnectAttempts).toBe(3);
      expect(service.config.enableAutoReconnect).toBe(false);
      expect(service.config.enableConnectionHealthCheck).toBe(true);
    });

    test('initializes with empty data structures', () => {
      expect(service.subscriptions.size).toBe(0);
      expect(service.marketData.size).toBe(0);
      expect(service.messageQueue.length).toBe(0);
      expect(service.connected).toBe(false);
      expect(service.connecting).toBe(false);
    });

    test('initializes metrics correctly', () => {
      const metrics = service.getMetrics();
      expect(metrics.messagesReceived).toBe(0);
      expect(metrics.messagesSent).toBe(0);
      expect(metrics.reconnectCount).toBe(0);
      expect(metrics.errorCount).toBe(0);
      expect(metrics.connectionQuality).toBe('unknown');
    });
  });

  describe('Connection Management', () => {
    test('connects successfully with valid configuration', async () => {
      const connectPromise = service.connect('test-user');
      
      await new Promise(resolve => setTimeout(resolve, 20)); // Wait for connection
      
      expect(service.connected).toBe(true);
      expect(service.connecting).toBe(false);
      expect(service.ws).toBeTruthy();
      expect(service.ws.url).toContain('wss://test-api.protrade.com/ws');
    });

    test('includes authentication token in WebSocket URL', async () => {
      localStorageMock.getItem.mockReturnValue('test.eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.signature');
      
      await service.connect('test-user');
      await new Promise(resolve => setTimeout(resolve, 20));
      
      expect(service.ws.url).toContain('userId=test-user');
      expect(service.ws.url).toContain('token=test.eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.signature');
    });

    test('handles missing WebSocket URL configuration', async () => {
      const mockConfig = { ...PERFORMANCE_CONFIG };
      mockConfig.websocket.url = null;
      service.config.wsUrl = null;
      
      const configErrorSpy = vi.fn();
      service.on('configurationError', configErrorSpy);
      
      await service.connect();
      
      expect(configErrorSpy).toHaveBeenCalledWith('WebSocket URL not configured');
      expect(service.connected).toBe(false);
    });

    test('handles missing authentication token', async () => {
      localStorageMock.getItem.mockReturnValue(null);
      
      const authErrorSpy = vi.fn();
      service.on('authenticationError', authErrorSpy);
      
      await service.connect();
      
      expect(authErrorSpy).toHaveBeenCalledWith('Authentication token required for WebSocket connection');
      expect(service.connected).toBe(false);
    });

    test('disconnects properly', async () => {
      await service.connect();
      await new Promise(resolve => setTimeout(resolve, 20));
      
      const disconnectedSpy = vi.fn();
      service.on('disconnected', disconnectedSpy);
      
      service.disconnect();
      
      expect(service.connected).toBe(false);
      expect(service.connecting).toBe(false);
      expect(disconnectedSpy).toHaveBeenCalled();
    });
  });

  describe('Message Handling', () => {
    beforeEach(async () => {
      await service.connect();
      await new Promise(resolve => setTimeout(resolve, 20));
    });

    test('handles market data messages', () => {
      const marketDataSpy = vi.fn();
      service.on('marketData', marketDataSpy);
      
      const mockMarketData = {
        type: 'market_data',
        symbol: 'AAPL',
        data: {
          price: 150.25,
          volume: 1000000,
          timestamp: Date.now()
        }
      };
      
      service.ws.simulateMessage(mockMarketData);
      
      expect(marketDataSpy).toHaveBeenCalledWith({
        symbol: 'AAPL',
        data: mockMarketData.data
      });
      
      // Check that data is cached
      const cachedData = service.getMarketData('AAPL');
      expect(cachedData.price).toBe(150.25);
      expect(cachedData.receivedAt).toBeTruthy();
    });

    test('handles portfolio update messages', () => {
      const portfolioUpdateSpy = vi.fn();
      service.on('portfolioUpdate', portfolioUpdateSpy);
      
      const mockPortfolioUpdate = {
        type: 'portfolio_update',
        userId: 'test-user',
        apiKeyId: 'api-key-123',
        portfolio: {
          totalValue: 100000,
          dayChange: 1500,
          positions: []
        }
      };
      
      service.ws.simulateMessage(mockPortfolioUpdate);
      
      expect(portfolioUpdateSpy).toHaveBeenCalledWith({
        userId: 'test-user',
        apiKeyId: 'api-key-123',
        portfolio: mockPortfolioUpdate.portfolio
      });
    });

    test('handles pong messages and calculates latency', () => {
      const pongSpy = vi.fn();
      service.on('pong', pongSpy);
      
      // Simulate sending a ping first
      service.sendMessage({ action: 'ping', timestamp: Date.now() });
      
      // Wait a bit then simulate pong
      setTimeout(() => {
        service.ws.simulateMessage({
          type: 'pong',
          timestamp: Date.now()
        });
      }, 10);
      
      setTimeout(() => {
        expect(pongSpy).toHaveBeenCalled();
        expect(service.metrics.lastLatency).toBeGreaterThan(0);
      }, 20);
    });

    test('handles invalid JSON messages gracefully', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      // Simulate invalid JSON
      if (service.ws.onmessage) {
        service.ws.onmessage({ data: 'invalid json{', type: 'message' });
      }
      
      expect(service.metrics.messagesDropped).toBe(1);
      expect(consoleSpy).toHaveBeenCalledWith('Failed to parse WebSocket message:', expect.any(Error));
      
      consoleSpy.mockRestore();
    });
  });

  describe('Subscription Management', () => {
    beforeEach(async () => {
      await service.connect();
      await new Promise(resolve => setTimeout(resolve, 20));
    });

    test('subscribes to market data symbols', () => {
      service.subscribe(['AAPL', 'MSFT'], 'market_data');
      
      expect(service.subscriptions.has('AAPL')).toBe(true);
      expect(service.subscriptions.has('MSFT')).toBe(true);
      
      // Check that subscription message was sent
      const lastMessage = JSON.parse(service.ws.lastSentMessage);
      expect(lastMessage.action).toBe('subscribe');
      expect(lastMessage.channel).toBe('market_data');
      expect(lastMessage.symbols).toEqual(['AAPL', 'MSFT']);
    });

    test('subscribes to portfolio updates', () => {
      const portfolioCallback = vi.fn();
      service.subscribeToPortfolio('test-user', 'api-key-123', portfolioCallback);
      
      const subscriptionKey = 'portfolio:test-user:api-key-123';
      expect(service.subscriptions.has(subscriptionKey)).toBe(true);
      
      // Check that subscription message was sent
      const lastMessage = JSON.parse(service.ws.lastSentMessage);
      expect(lastMessage.action).toBe('subscribe');
      expect(lastMessage.channel).toBe('portfolio');
      expect(lastMessage.userId).toBe('test-user');
      expect(lastMessage.apiKeyId).toBe('api-key-123');
    });

    test('unsubscribes from symbols', () => {
      service.subscribe(['AAPL', 'MSFT']);
      service.unsubscribe(['AAPL']);
      
      expect(service.subscriptions.has('AAPL')).toBe(false);
      expect(service.subscriptions.has('MSFT')).toBe(true);
      
      // Check that unsubscription message was sent
      const lastMessage = JSON.parse(service.ws.lastSentMessage);
      expect(lastMessage.action).toBe('unsubscribe');
      expect(lastMessage.symbols).toEqual(['AAPL']);
    });

    test('unsubscribes from portfolio updates', () => {
      const portfolioCallback = vi.fn();
      service.subscribeToPortfolio('test-user', 'api-key-123', portfolioCallback);
      service.unsubscribeFromPortfolio('test-user', 'api-key-123');
      
      const subscriptionKey = 'portfolio:test-user:api-key-123';
      expect(service.subscriptions.has(subscriptionKey)).toBe(false);
      
      // Check that unsubscription message was sent
      const lastMessage = JSON.parse(service.ws.lastSentMessage);
      expect(lastMessage.action).toBe('unsubscribe');
      expect(lastMessage.channel).toBe('portfolio');
    });
  });

  describe('Data Access Methods', () => {
    beforeEach(async () => {
      await service.connect();
      await new Promise(resolve => setTimeout(resolve, 20));
    });

    test('gets market data for symbol', () => {
      // Add some mock data
      service.marketData.set('AAPL', {
        price: 150.25,
        volume: 1000000,
        receivedAt: Date.now()
      });
      
      const data = service.getMarketData('AAPL');
      expect(data.price).toBe(150.25);
      expect(data.volume).toBe(1000000);
    });

    test('gets latest price for symbol', () => {
      service.marketData.set('AAPL', {
        price: 150.25,
        volume: 1000000,
        receivedAt: Date.now()
      });
      
      const price = service.getLatestPrice('AAPL');
      expect(price).toBe(150.25);
    });

    test('returns null for non-existent symbol', () => {
      const data = service.getMarketData('NONEXISTENT');
      const price = service.getLatestPrice('NONEXISTENT');
      
      expect(data).toBeUndefined();
      expect(price).toBeNull();
    });

    test('checks if data is stale', () => {
      const now = Date.now();
      
      // Fresh data
      service.marketData.set('AAPL', {
        price: 150.25,
        receivedAt: now
      });
      
      // Stale data
      service.marketData.set('MSFT', {
        price: 200.50,
        receivedAt: now - 120000 // 2 minutes ago
      });
      
      expect(service.isDataStale('AAPL', 60000)).toBe(false); // 1 minute threshold
      expect(service.isDataStale('MSFT', 60000)).toBe(true);  // 1 minute threshold
      expect(service.isDataStale('NONEXISTENT')).toBe(true);
    });
  });

  describe('Connection Status and Health', () => {
    test('reports correct connection status', async () => {
      expect(service.getConnectionStatus()).toBe('DISCONNECTED');
      expect(service.isConnected()).toBe(false);
      
      const connectPromise = service.connect();
      expect(service.getConnectionStatus()).toBe('CONNECTING');
      
      await new Promise(resolve => setTimeout(resolve, 20));
      expect(service.getConnectionStatus()).toBe('CONNECTED');
      expect(service.isConnected()).toBe(true);
    });

    test('provides comprehensive health check', () => {
      const health = service.healthCheck();
      
      expect(health).toHaveProperty('connected');
      expect(health).toHaveProperty('connecting');
      expect(health).toHaveProperty('lastActivity');
      expect(health).toHaveProperty('metrics');
      expect(health).toHaveProperty('subscriptions');
      expect(health).toHaveProperty('connectionQuality');
      expect(health).toHaveProperty('config');
      
      expect(health.config.wsUrl).toBe('configured');
      expect(health.config.autoReconnect).toBe(false);
      expect(health.config.healthCheck).toBe(true);
    });

    test('calculates connection quality score', () => {
      // Test different quality levels
      service.metrics.connectionQuality = 'excellent';
      expect(service.getConnectionQualityScore()).toBe(100);
      
      service.metrics.connectionQuality = 'good';
      expect(service.getConnectionQualityScore()).toBe(80);
      
      service.metrics.connectionQuality = 'fair';
      expect(service.getConnectionQualityScore()).toBe(60);
      
      service.metrics.connectionQuality = 'poor';
      expect(service.getConnectionQualityScore()).toBe(40);
      
      service.metrics.connectionQuality = 'unknown';
      expect(service.getConnectionQualityScore()).toBe(0);
    });
  });

  describe('Reconnection Logic', () => {
    test('attempts to reconnect after connection loss', async () => {
      vi.useFakeTimers();
      
      service.config.enableAutoReconnect = true;
      await service.connect();
      await new Promise(resolve => setTimeout(resolve, 20));
      
      const reconnectingSpy = vi.fn();
      service.on('reconnecting', reconnectingSpy);
      
      // Simulate connection loss
      service.ws.close(1006, 'Connection lost'); // Abnormal closure
      
      // Fast-forward timers to trigger reconnection
      vi.advanceTimersByTime(1000);
      
      expect(reconnectingSpy).toHaveBeenCalled();
      expect(service.reconnectAttempts).toBe(1);
      
      vi.useRealTimers();
    });

    test('stops reconnecting after max attempts', async () => {
      vi.useFakeTimers();
      
      service.config.enableAutoReconnect = true;
      service.maxReconnectAttempts = 2;
      
      const maxAttemptsReachedSpy = vi.fn();
      service.on('maxReconnectAttemptsReached', maxAttemptsReachedSpy);
      
      // Simulate multiple failed reconnection attempts
      service.reconnectAttempts = 2;
      service.scheduleReconnect();
      
      expect(maxAttemptsReachedSpy).toHaveBeenCalledWith({
        attempts: 2,
        maxAttempts: 2,
        lastError: undefined
      });
      
      vi.useRealTimers();
    });
  });

  describe('Message Queue Management', () => {
    test('queues messages when not connected', () => {
      const message = { action: 'subscribe', symbols: ['AAPL'] };
      service.sendMessage(message);
      
      expect(service.messageQueue.length).toBe(1);
      expect(service.messageQueue[0]).toEqual(message);
    });

    test('processes message queue when connected', async () => {
      const message1 = { action: 'subscribe', symbols: ['AAPL'] };
      const message2 = { action: 'subscribe', symbols: ['MSFT'] };
      
      // Queue messages while disconnected
      service.sendMessage(message1);
      service.sendMessage(message2);
      
      expect(service.messageQueue.length).toBe(2);
      
      // Connect and process queue
      await service.connect();
      await new Promise(resolve => setTimeout(resolve, 20));
      
      expect(service.messageQueue.length).toBe(0);
      expect(service.metrics.messagesSent).toBeGreaterThan(0);
    });

    test('limits message queue size', () => {
      service.config.maxMessageQueueSize = 2;
      
      service.sendMessage({ action: 'test1' });
      service.sendMessage({ action: 'test2' });
      service.sendMessage({ action: 'test3' }); // Should be dropped
      
      expect(service.messageQueue.length).toBe(2);
      expect(service.metrics.messagesDropped).toBe(1);
    });
  });

  describe('Performance Metrics', () => {
    test('tracks message statistics', async () => {
      await service.connect();
      await new Promise(resolve => setTimeout(resolve, 20));
      
      // Send some messages
      service.sendMessage({ action: 'ping' });
      service.sendMessage({ action: 'subscribe', symbols: ['AAPL'] });
      
      expect(service.metrics.messagesSent).toBe(2);
      
      // Simulate receiving messages
      service.ws.simulateMessage({ type: 'pong' });
      service.ws.simulateMessage({ type: 'market_data', symbol: 'AAPL', data: {} });
      
      expect(service.metrics.messagesReceived).toBe(2);
    });

    test('calculates average latency', () => {
      service.updateAverageLatency(100);
      expect(service.metrics.avgLatency).toBe(100);
      
      service.updateAverageLatency(200);
      expect(service.metrics.avgLatency).toBe(110); // 100 * 0.9 + 200 * 0.1
    });

    test('provides comprehensive metrics', async () => {
      await service.connect();
      await new Promise(resolve => setTimeout(resolve, 20));
      
      const metrics = service.getMetrics();
      
      expect(metrics).toHaveProperty('messagesReceived');
      expect(metrics).toHaveProperty('messagesSent');
      expect(metrics).toHaveProperty('avgLatency');
      expect(metrics).toHaveProperty('connectionUptime');
      expect(metrics).toHaveProperty('subscriptionsCount');
      expect(metrics).toHaveProperty('cachedSymbols');
      expect(metrics).toHaveProperty('messageQueueSize');
      expect(metrics).toHaveProperty('connectionQualityScore');
      expect(metrics).toHaveProperty('isHealthy');
      
      expect(typeof metrics.connectionUptime).toBe('number');
      expect(typeof metrics.isHealthy).toBe('boolean');
    });
  });

  describe('Cleanup and Resource Management', () => {
    test('cleans up resources properly', async () => {
      await service.connect();
      await new Promise(resolve => setTimeout(resolve, 20));
      
      // Add some data and subscriptions
      service.subscribe(['AAPL', 'MSFT']);
      service.marketData.set('AAPL', { price: 150 });
      
      service.cleanup();
      
      expect(service.connected).toBe(false);
      expect(service.subscriptions.size).toBe(0);
      expect(service.marketData.size).toBe(0);
      expect(service.messageQueue.length).toBe(0);
    });

    test('handles cleanup when already disconnected', () => {
      expect(() => service.cleanup()).not.toThrow();
      expect(service.connected).toBe(false);
    });
  });

  describe('Error Handling', () => {
    test('handles WebSocket errors gracefully', async () => {
      const errorSpy = vi.fn();
      service.on('error', errorSpy);
      
      await service.connect();
      await new Promise(resolve => setTimeout(resolve, 20));
      
      const mockError = new Error('WebSocket connection failed');
      service.ws.simulateError(mockError);
      
      expect(errorSpy).toHaveBeenCalled();
      expect(service.metrics.errorCount).toBe(1);
      expect(service.metrics.connectionQuality).toBe('poor');
    });

    test('handles server error messages', async () => {
      await service.connect();
      await new Promise(resolve => setTimeout(resolve, 20));
      
      const serverErrorSpy = vi.fn();
      service.on('serverError', serverErrorSpy);
      
      service.ws.simulateMessage({
        type: 'error',
        code: 'INVALID_TOKEN',
        message: 'Authentication token is invalid'
      });
      
      expect(serverErrorSpy).toHaveBeenCalledWith({
        type: 'error',
        code: 'INVALID_TOKEN',
        message: 'Authentication token is invalid'
      });
    });
  });
});

describe('Live Data Service Integration', () => {
  test('singleton instance is properly configured', () => {
    expect(liveDataService).toBeInstanceOf(LiveDataService);
    expect(liveDataService.config.wsUrl).toBe('wss://test-api.protrade.com/ws');
  });

  test('service can be imported and used directly', () => {
    expect(typeof liveDataService.connect).toBe('function');
    expect(typeof liveDataService.subscribe).toBe('function');
    expect(typeof liveDataService.getMarketData).toBe('function');
    expect(typeof liveDataService.healthCheck).toBe('function');
  });
});
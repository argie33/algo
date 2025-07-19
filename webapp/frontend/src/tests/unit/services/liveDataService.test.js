/**
 * Live Data Service Unit Tests
 * Tests for WebSocket-based real-time market data service
 */

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { LiveDataService } from '../../../services/liveDataService';

// Mock WebSocket
class MockWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = WebSocket.CONNECTING;
    this.onopen = null;
    this.onclose = null;
    this.onerror = null;
    this.onmessage = null;
    this.sentMessages = [];
    
    // Simulate connection after a short delay
    setTimeout(() => {
      this.readyState = WebSocket.OPEN;
      if (this.onopen) {
        this.onopen({ type: 'open' });
      }
    }, 10);
  }
  
  send(data) {
    this.sentMessages.push(data);
  }
  
  close(code = 1000, reason = '') {
    this.readyState = WebSocket.CLOSED;
    if (this.onclose) {
      this.onclose({ code, reason, type: 'close' });
    }
  }
  
  // Test helper to simulate incoming messages
  simulateMessage(data) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) });
    }
  }
  
  // Test helper to simulate errors
  simulateError(error) {
    if (this.onerror) {
      this.onerror({ error, type: 'error' });
    }
  }
}

// Mock global WebSocket
global.WebSocket = MockWebSocket;
global.WebSocket.CONNECTING = 0;
global.WebSocket.OPEN = 1;
global.WebSocket.CLOSING = 2;
global.WebSocket.CLOSED = 3;

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};
global.localStorage = localStorageMock;

describe('LiveDataService', () => {
  let service;

  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.getItem.mockReturnValue('mock-jwt-token.payload.signature');
    
    // Create new service instance for each test
    service = new LiveDataService();
    service.config.wsUrl = 'ws://localhost:8080/ws';
  });

  afterEach(() => {
    if (service) {
      service.cleanup();
    }
  });

  describe('Connection Management', () => {
    test('should initialize with correct default state', () => {
      expect(service.connected).toBe(false);
      expect(service.connecting).toBe(false);
      expect(service.reconnectAttempts).toBe(0);
      expect(service.subscriptions.size).toBe(0);
    });

    test('should connect successfully with valid token', async () => {
      const connectPromise = new Promise((resolve) => {
        service.on('connected', resolve);
      });

      await service.connect('test-user');
      
      const result = await connectPromise;
      
      expect(service.connected).toBe(true);
      expect(service.connecting).toBe(false);
      expect(result.reconnectAttempts).toBe(0);
    });

    test('should handle connection without token', async () => {
      localStorageMock.getItem.mockReturnValue(null);
      
      const errorPromise = new Promise((resolve) => {
        service.on('authenticationError', resolve);
      });

      await service.connect();
      
      const error = await errorPromise;
      expect(error).toBe('Authentication token required for WebSocket connection');
      expect(service.connected).toBe(false);
    });

    test('should handle connection without WebSocket URL', async () => {
      service.config.wsUrl = null;
      
      const errorPromise = new Promise((resolve) => {
        service.on('configurationError', resolve);
      });

      await service.connect();
      
      const error = await errorPromise;
      expect(error).toBe('WebSocket URL not configured');
      expect(service.connected).toBe(false);
    });

    test('should disconnect cleanly', async () => {
      await service.connect('test-user');
      
      const disconnectPromise = new Promise((resolve) => {
        service.on('disconnected', resolve);
      });

      service.disconnect();
      
      const result = await disconnectPromise;
      expect(result.reason).toBe('client_disconnect');
      expect(service.connected).toBe(false);
    });
  });

  describe('Message Handling', () => {
    beforeEach(async () => {
      await service.connect('test-user');
      await new Promise(resolve => service.on('connected', resolve));
    });

    test('should handle market data messages', () => {
      const marketDataCallback = vi.fn();
      service.on('marketData', marketDataCallback);

      const mockData = {
        type: 'market_data',
        symbol: 'AAPL',
        data: {
          price: 150.25,
          volume: 1000000,
          timestamp: Date.now()
        }
      };

      service.ws.simulateMessage(mockData);

      expect(marketDataCallback).toHaveBeenCalledWith({
        symbol: 'AAPL',
        data: mockData.data
      });
      
      expect(service.getMarketData('AAPL')).toMatchObject(mockData.data);
    });

    test('should handle portfolio update messages', () => {
      const portfolioCallback = vi.fn();
      service.on('portfolioUpdate', portfolioCallback);

      const mockData = {
        type: 'portfolio_update',
        userId: 'test-user',
        apiKeyId: 'api-key-1',
        portfolio: {
          totalValue: 100000,
          dayChange: 1250.50
        }
      };

      service.ws.simulateMessage(mockData);

      expect(portfolioCallback).toHaveBeenCalledWith({
        userId: 'test-user',
        apiKeyId: 'api-key-1',
        portfolio: mockData.portfolio
      });
    });

    test('should handle pong messages and calculate latency', () => {
      const pongCallback = vi.fn();
      service.on('pong', pongCallback);

      // Simulate ping sent
      service.metrics.lastPingTime = Date.now() - 50;

      const mockPong = {
        type: 'pong',
        timestamp: Date.now()
      };

      service.ws.simulateMessage(mockPong);

      expect(pongCallback).toHaveBeenCalled();
      expect(service.metrics.lastLatency).toBeGreaterThan(0);
      expect(service.metrics.lastLatency).toBeLessThan(100);
    });

    test('should handle invalid JSON messages gracefully', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      // Simulate invalid JSON
      if (service.ws.onmessage) {
        service.ws.onmessage({ data: 'invalid json{' });
      }

      expect(consoleSpy).toHaveBeenCalledWith(
        'Failed to parse WebSocket message:',
        expect.any(Error)
      );
      expect(service.metrics.messagesDropped).toBe(1);
      
      consoleSpy.mockRestore();
    });
  });

  describe('Subscription Management', () => {
    beforeEach(async () => {
      await service.connect('test-user');
      await new Promise(resolve => service.on('connected', resolve));
    });

    test('should subscribe to market data', () => {
      service.subscribe(['AAPL', 'GOOGL']);

      expect(service.subscriptions.has('AAPL')).toBe(true);
      expect(service.subscriptions.has('GOOGL')).toBe(true);
      
      const sentMessage = JSON.parse(service.ws.sentMessages[service.ws.sentMessages.length - 1]);
      expect(sentMessage.action).toBe('subscribe');
      expect(sentMessage.symbols).toEqual(['AAPL', 'GOOGL']);
    });

    test('should subscribe to portfolio updates', () => {
      const callback = vi.fn();
      service.subscribeToPortfolio('test-user', 'api-key-1', callback);

      const subscriptionKey = 'portfolio:test-user:api-key-1';
      expect(service.subscriptions.has(subscriptionKey)).toBe(true);
      
      const sentMessage = JSON.parse(service.ws.sentMessages[service.ws.sentMessages.length - 1]);
      expect(sentMessage.action).toBe('subscribe');
      expect(sentMessage.channel).toBe('portfolio');
      expect(sentMessage.userId).toBe('test-user');
      expect(sentMessage.apiKeyId).toBe('api-key-1');
    });

    test('should unsubscribe from market data', () => {
      service.subscribe(['AAPL']);
      service.unsubscribe(['AAPL']);

      expect(service.subscriptions.has('AAPL')).toBe(false);
      
      const sentMessage = JSON.parse(service.ws.sentMessages[service.ws.sentMessages.length - 1]);
      expect(sentMessage.action).toBe('unsubscribe');
      expect(sentMessage.symbols).toEqual(['AAPL']);
    });

    test('should unsubscribe from portfolio updates', () => {
      const callback = vi.fn();
      service.subscribeToPortfolio('test-user', 'api-key-1', callback);
      service.unsubscribeFromPortfolio('test-user', 'api-key-1');

      const subscriptionKey = 'portfolio:test-user:api-key-1';
      expect(service.subscriptions.has(subscriptionKey)).toBe(false);
    });
  });

  describe('Message Queue', () => {
    test('should queue messages when disconnected', () => {
      service.sendMessage({ action: 'test', data: 'queued' });

      expect(service.messageQueue).toHaveLength(1);
      expect(service.messageQueue[0].action).toBe('test');
    });

    test('should process message queue when connected', async () => {
      // Queue message while disconnected
      service.sendMessage({ action: 'test', data: 'queued' });
      expect(service.messageQueue).toHaveLength(1);

      // Connect and wait for queue processing
      await service.connect('test-user');
      await new Promise(resolve => service.on('connected', resolve));

      // Wait for queue processing
      await new Promise(resolve => setTimeout(resolve, 20));

      expect(service.messageQueue).toHaveLength(0);
      expect(service.ws.sentMessages).toContain(
        JSON.stringify({ action: 'test', data: 'queued' })
      );
    });

    test('should drop messages when queue is full', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      
      // Fill queue beyond limit
      for (let i = 0; i < service.config.maxMessageQueueSize + 1; i++) {
        service.sendMessage({ action: 'test', id: i });
      }

      expect(service.messageQueue).toHaveLength(service.config.maxMessageQueueSize);
      expect(consoleSpy).toHaveBeenCalledWith(
        '⚠️ Message queue full, dropping message:',
        'test'
      );
      expect(service.metrics.messagesDropped).toBeGreaterThan(0);
      
      consoleSpy.mockRestore();
    });
  });

  describe('Reconnection Logic', () => {
    test('should attempt reconnection on unexpected disconnect', async () => {
      await service.connect('test-user');
      await new Promise(resolve => service.on('connected', resolve));

      const reconnectingPromise = new Promise((resolve) => {
        service.on('reconnecting', resolve);
      });

      // Simulate unexpected disconnect
      service.ws.close(1006, 'Abnormal closure');

      const reconnectEvent = await reconnectingPromise;
      expect(reconnectEvent.attempt).toBe(1);
      expect(reconnectEvent.maxAttempts).toBe(service.maxReconnectAttempts);
    });

    test('should not reconnect on normal disconnect', async () => {
      await service.connect('test-user');
      await new Promise(resolve => service.on('connected', resolve));

      const reconnectingSpy = vi.fn();
      service.on('reconnecting', reconnectingSpy);

      // Simulate normal disconnect
      service.disconnect();
      
      // Wait a bit to ensure no reconnection
      await new Promise(resolve => setTimeout(resolve, 100));
      
      expect(reconnectingSpy).not.toHaveBeenCalled();
    });

    test('should give up after max reconnection attempts', async () => {
      service.maxReconnectAttempts = 2;
      
      const maxAttemptsPromise = new Promise((resolve) => {
        service.on('maxReconnectAttemptsReached', resolve);
      });

      // Simulate connection failures
      for (let i = 0; i < 3; i++) {
        service.reconnectAttempts = i;
        service.scheduleReconnect();
      }

      const result = await maxAttemptsPromise;
      expect(result.attempts).toBe(2);
      expect(result.maxAttempts).toBe(2);
    });
  });

  describe('Data Access', () => {
    beforeEach(async () => {
      await service.connect('test-user');
      await new Promise(resolve => service.on('connected', resolve));
      
      // Add some test data
      service.marketData.set('AAPL', {
        price: 150.25,
        volume: 1000000,
        receivedAt: Date.now()
      });
    });

    test('should get market data for symbol', () => {
      const data = service.getMarketData('AAPL');
      expect(data.price).toBe(150.25);
      expect(data.volume).toBe(1000000);
    });

    test('should get latest price for symbol', () => {
      const price = service.getLatestPrice('AAPL');
      expect(price).toBe(150.25);
    });

    test('should return null for unknown symbol', () => {
      const price = service.getLatestPrice('UNKNOWN');
      expect(price).toBeNull();
    });

    test('should detect stale data', () => {
      // Set old timestamp
      service.marketData.set('STALE', {
        price: 100,
        receivedAt: Date.now() - 120000 // 2 minutes ago
      });

      expect(service.isDataStale('STALE', 60000)).toBe(true);
      expect(service.isDataStale('AAPL', 60000)).toBe(false);
    });

    test('should get all market data', () => {
      const allData = service.getAllMarketData();
      expect(allData.AAPL).toBeDefined();
      expect(allData.AAPL.price).toBe(150.25);
    });
  });

  describe('Health Monitoring', () => {
    test('should provide connection status', () => {
      expect(service.getConnectionStatus()).toBe('DISCONNECTED');
      
      service.connecting = true;
      expect(service.getConnectionStatus()).toBe('CONNECTING');
      
      service.connecting = false;
      service.connected = true;
      expect(service.getConnectionStatus()).toBe('CONNECTED');
    });

    test('should provide comprehensive metrics', () => {
      const metrics = service.getMetrics();
      
      expect(metrics).toHaveProperty('messagesReceived');
      expect(metrics).toHaveProperty('messagesDropped');
      expect(metrics).toHaveProperty('avgLatency');
      expect(metrics).toHaveProperty('connectionUptime');
      expect(metrics).toHaveProperty('subscriptionsCount');
      expect(metrics).toHaveProperty('connectionQuality');
      expect(metrics).toHaveProperty('isHealthy');
    });

    test('should perform health check', () => {
      const health = service.healthCheck();
      
      expect(health).toHaveProperty('connected');
      expect(health).toHaveProperty('metrics');
      expect(health).toHaveProperty('subscriptions');
      expect(health).toHaveProperty('connectionQuality');
      expect(health).toHaveProperty('config');
    });

    test('should update connection quality based on latency', () => {
      service.updateConnectionQuality(50);
      expect(service.metrics.connectionQuality).toBe('excellent');
      
      service.updateConnectionQuality(200);
      expect(service.metrics.connectionQuality).toBe('good');
      
      service.updateConnectionQuality(800);
      expect(service.metrics.connectionQuality).toBe('fair');
      
      service.updateConnectionQuality(1500);
      expect(service.metrics.connectionQuality).toBe('poor');
    });
  });

  describe('Cleanup', () => {
    test('should cleanup all resources', async () => {
      await service.connect('test-user');
      service.subscribe(['AAPL']);
      
      const eventSpy = vi.fn();
      service.on('test', eventSpy);
      
      service.cleanup();
      
      expect(service.connected).toBe(false);
      expect(service.marketData.size).toBe(0);
      expect(service.events).toEqual({});
      expect(service.messageQueue).toHaveLength(0);
    });
  });

  describe('Error Handling', () => {
    test('should handle WebSocket errors gracefully', async () => {
      const errorPromise = new Promise((resolve) => {
        service.on('error', resolve);
      });

      await service.connect('test-user');
      
      // Simulate WebSocket error
      const mockError = new Error('Network error');
      service.ws.simulateError(mockError);

      const errorEvent = await errorPromise;
      expect(errorEvent.error).toBe(mockError);
      expect(service.metrics.errorCount).toBeGreaterThan(0);
    });

    test('should handle message send failures', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      // Mock send to throw error
      service.ws = {
        send: vi.fn(() => { throw new Error('Send failed'); })
      };
      service.connected = true;

      service.sendMessage({ action: 'test' });

      expect(consoleSpy).toHaveBeenCalledWith(
        'Failed to send message:',
        expect.any(Error)
      );
      expect(service.metrics.messagesDropped).toBe(1);
      
      consoleSpy.mockRestore();
    });
  });

  describe('Batch Operations', () => {
    beforeEach(async () => {
      await service.connect('test-user');
      await new Promise(resolve => service.on('connected', resolve));
    });

    test('should handle batch subscribe operations', () => {
      const symbols = ['AAPL', 'GOOGL', 'MSFT', 'AMZN'];
      service.subscribeBatch(symbols);

      symbols.forEach(symbol => {
        expect(service.subscriptions.has(symbol)).toBe(true);
      });
      
      const sentMessage = JSON.parse(service.ws.sentMessages[service.ws.sentMessages.length - 1]);
      expect(sentMessage.symbols).toEqual(symbols);
    });

    test('should handle batch unsubscribe operations', () => {
      const symbols = ['AAPL', 'GOOGL'];
      service.subscribe(symbols);
      service.unsubscribeBatch(symbols);

      symbols.forEach(symbol => {
        expect(service.subscriptions.has(symbol)).toBe(false);
      });
    });
  });
});
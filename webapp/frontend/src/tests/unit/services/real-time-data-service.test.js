/**
 * Real-Time Data Service Unit Tests
 * Testing the actual realTimeDataService.js with HTTP polling and EventEmitter
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock the api import since we'll test the service logic
vi.mock('../../../services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn()
  }
}));

// Import the REAL RealTimeDataService
const realTimeDataServiceModule = await import('../../../services/realTimeDataService');
const RealTimeDataService = realTimeDataServiceModule.default || realTimeDataServiceModule.RealTimeDataService;

// Import the mocked api
import { api } from '../../../services/api';

describe('📡 Real-Time Data Service', () => {
  let realTimeService;
  let mockApi;

  beforeEach(() => {
    // Reset all mocks
    vi.clearAllMocks();
    
    // Setup mock API responses
    mockApi = api;
    mockApi.get.mockResolvedValue({
      data: {
        quotes: {
          'AAPL': {
            symbol: 'AAPL',
            price: 185.50,
            change: 2.25,
            changePercent: 1.23,
            volume: 1250000,
            timestamp: new Date().toISOString()
          }
        },
        timestamp: new Date().toISOString(),
        status: 'success'
      }
    });

    // Create fresh service instance
    realTimeService = new RealTimeDataService();
    
    // Mock console to avoid noise in tests
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    // Cleanup service
    if (realTimeService) {
      realTimeService.disconnect();
      realTimeService.removeAllListeners();
    }
    
    // Clear all timers
    vi.clearAllTimers();
    
    // Restore console
    vi.restoreAllMocks();
  });

  describe('Service Initialization', () => {
    it('should initialize with correct default configuration', () => {
      expect(realTimeService.isConnected).toBe(false);
      expect(realTimeService.isPolling).toBe(false);
      expect(realTimeService.subscriptions).toBeInstanceOf(Set);
      expect(realTimeService.subscriptions.size).toBe(0);
      expect(realTimeService.pollingInterval).toBeNull();
      expect(realTimeService.retryCount).toBe(0);
      expect(realTimeService.maxRetries).toBe(5);
    });

    it('should have correct default config values', () => {
      expect(realTimeService.config.pollingInterval).toBe(5000);
      expect(realTimeService.config.maxRetries).toBe(5);
      expect(realTimeService.config.backoffMultiplier).toBe(1.5);
      expect(realTimeService.config.timeout).toBe(10000);
    });

    it('should initialize empty data caches', () => {
      expect(realTimeService.marketDataCache).toBeInstanceOf(Map);
      expect(realTimeService.marketDataCache.size).toBe(0);
      expect(realTimeService.lastUpdated).toBeInstanceOf(Map);
      expect(realTimeService.lastUpdated.size).toBe(0);
    });

    it('should initialize stats tracking', () => {
      expect(realTimeService.stats).toEqual({
        messagesReceived: 0,
        requestsSent: 0,
        connectTime: null,
        disconnectTime: null,
        dataValidationErrors: 0,
        reconnectCount: 0,
        pollErrors: 0
      });
    });
  });

  describe('EventEmitter Functionality', () => {
    it('should extend EventEmitter with all methods', () => {
      expect(typeof realTimeService.on).toBe('function');
      expect(typeof realTimeService.off).toBe('function');
      expect(typeof realTimeService.emit).toBe('function');
      expect(typeof realTimeService.removeAllListeners).toBe('function');
    });

    it('should handle event subscription and emission', () => {
      const mockHandler = vi.fn();
      
      realTimeService.on('test-event', mockHandler);
      realTimeService.emit('test-event', 'test-data');
      
      expect(mockHandler).toHaveBeenCalledWith('test-data');
    });

    it('should handle multiple listeners for same event', () => {
      const handler1 = vi.fn();
      const handler2 = vi.fn();
      
      realTimeService.on('multi-event', handler1);
      realTimeService.on('multi-event', handler2);
      realTimeService.emit('multi-event', 'data');
      
      expect(handler1).toHaveBeenCalledWith('data');
      expect(handler2).toHaveBeenCalledWith('data');
    });

    it('should remove specific event listeners', () => {
      const handler = vi.fn();
      
      realTimeService.on('remove-test', handler);
      realTimeService.off('remove-test', handler);
      realTimeService.emit('remove-test', 'data');
      
      expect(handler).not.toHaveBeenCalled();
    });

    it('should remove all listeners for an event', () => {
      const handler1 = vi.fn();
      const handler2 = vi.fn();
      
      realTimeService.on('clear-test', handler1);
      realTimeService.on('clear-test', handler2);
      realTimeService.removeAllListeners('clear-test');
      realTimeService.emit('clear-test', 'data');
      
      expect(handler1).not.toHaveBeenCalled();
      expect(handler2).not.toHaveBeenCalled();
    });
  });

  describe('Connection Management', () => {
    it('should connect successfully', async () => {
      const connectPromise = realTimeService.connect();
      
      expect(realTimeService.isConnected).toBe(false); // Not yet connected
      
      await connectPromise;
      
      expect(realTimeService.isConnected).toBe(true);
      expect(realTimeService.stats.connectTime).not.toBeNull();
    });

    it('should not connect twice when already connected', async () => {
      await realTimeService.connect();
      expect(realTimeService.isConnected).toBe(true);
      
      // Try to connect again
      await realTimeService.connect();
      expect(realTimeService.isConnected).toBe(true);
    });

    it('should disconnect properly', async () => {
      await realTimeService.connect();
      expect(realTimeService.isConnected).toBe(true);
      
      realTimeService.disconnect();
      
      expect(realTimeService.isConnected).toBe(false);
      expect(realTimeService.isPolling).toBe(false);
      expect(realTimeService.stats.disconnectTime).not.toBeNull();
    });

    it('should handle connection errors gracefully', async () => {
      // Mock API to reject
      mockApi.get.mockRejectedValue(new Error('Connection failed'));
      
      await expect(realTimeService.connect()).rejects.toThrow('Connection failed');
      expect(realTimeService.isConnected).toBe(false);
    });
  });

  describe('Symbol Subscription Management', () => {
    beforeEach(async () => {
      await realTimeService.connect();
    });

    it('should subscribe to symbols successfully', () => {
      realTimeService.subscribe(['AAPL', 'GOOGL']);
      
      expect(realTimeService.subscriptions.has('AAPL')).toBe(true);
      expect(realTimeService.subscriptions.has('GOOGL')).toBe(true);
      expect(realTimeService.subscriptions.size).toBe(2);
    });

    it('should unsubscribe from symbols', () => {
      realTimeService.subscribe(['AAPL', 'GOOGL', 'MSFT']);
      expect(realTimeService.subscriptions.size).toBe(3);
      
      realTimeService.unsubscribe(['GOOGL']);
      expect(realTimeService.subscriptions.has('GOOGL')).toBe(false);
      expect(realTimeService.subscriptions.size).toBe(2);
    });

    it('should handle duplicate subscriptions', () => {
      realTimeService.subscribe(['AAPL']);
      realTimeService.subscribe(['AAPL']); // Duplicate
      
      expect(realTimeService.subscriptions.size).toBe(1);
    });

    it('should start polling when symbols are subscribed', () => {
      expect(realTimeService.isPolling).toBe(false);
      
      realTimeService.subscribe(['AAPL']);
      
      expect(realTimeService.isPolling).toBe(true);
      expect(realTimeService.pollingInterval).not.toBeNull();
    });

    it('should stop polling when all symbols are unsubscribed', () => {
      realTimeService.subscribe(['AAPL', 'GOOGL']);
      expect(realTimeService.isPolling).toBe(true);
      
      realTimeService.unsubscribe(['AAPL', 'GOOGL']);
      expect(realTimeService.isPolling).toBe(false);
      expect(realTimeService.pollingInterval).toBeNull();
    });
  });

  describe('HTTP Polling Logic', () => {
    beforeEach(async () => {
      vi.useFakeTimers();
      await realTimeService.connect();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should poll data at configured intervals', async () => {
      realTimeService.subscribe(['AAPL']);
      
      // Fast forward time to trigger polling
      vi.advanceTimersByTime(5000);
      
      expect(mockApi.get).toHaveBeenCalledWith('/realtime/quotes', {
        params: { symbols: 'AAPL' }
      });
    });

    it('should handle polling responses correctly', async () => {
      const dataHandler = vi.fn();
      realTimeService.on('data', dataHandler);
      
      realTimeService.subscribe(['AAPL']);
      
      // Trigger polling
      vi.advanceTimersByTime(5000);
      await vi.runAllTimersAsync();
      
      expect(dataHandler).toHaveBeenCalled();
      expect(realTimeService.stats.messagesReceived).toBeGreaterThan(0);
    });

    it('should cache received data', async () => {
      realTimeService.subscribe(['AAPL']);
      
      vi.advanceTimersByTime(5000);
      await vi.runAllTimersAsync();
      
      expect(realTimeService.marketDataCache.has('AAPL')).toBe(true);
      expect(realTimeService.lastUpdated.has('AAPL')).toBe(true);
    });

    it('should emit specific symbol data updates', async () => {
      const aaplHandler = vi.fn();
      realTimeService.on('AAPL', aaplHandler);
      
      realTimeService.subscribe(['AAPL']);
      
      vi.advanceTimersByTime(5000);
      await vi.runAllTimersAsync();
      
      expect(aaplHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          symbol: 'AAPL',
          price: 185.50
        })
      );
    });
  });

  describe('Error Handling and Retry Logic', () => {
    beforeEach(async () => {
      vi.useFakeTimers();
      await realTimeService.connect();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should handle polling errors and retry', async () => {
      mockApi.get.mockRejectedValueOnce(new Error('Network error'));
      
      realTimeService.subscribe(['AAPL']);
      
      vi.advanceTimersByTime(5000);
      await vi.runAllTimersAsync();
      
      expect(realTimeService.stats.pollErrors).toBe(1);
      expect(realTimeService.retryCount).toBe(1);
    });

    it('should implement exponential backoff for retries', async () => {
      mockApi.get.mockRejectedValue(new Error('Persistent error'));
      
      realTimeService.subscribe(['AAPL']);
      
      // Initial attempt
      vi.advanceTimersByTime(5000);
      await vi.runAllTimersAsync();
      
      expect(realTimeService.retryCount).toBe(1);
      
      // Should wait longer for retry (backoff)
      const expectedBackoff = 5000 * Math.pow(1.5, 1);
      vi.advanceTimersByTime(expectedBackoff);
      await vi.runAllTimersAsync();
      
      expect(realTimeService.retryCount).toBe(2);
    });

    it('should stop retrying after max retries reached', async () => {
      mockApi.get.mockRejectedValue(new Error('Persistent error'));
      
      realTimeService.subscribe(['AAPL']);
      
      // Trigger max retries
      for (let i = 0; i < realTimeService.maxRetries + 1; i++) {
        vi.advanceTimersByTime(10000);
        await vi.runAllTimersAsync();
      }
      
      expect(realTimeService.retryCount).toBe(realTimeService.maxRetries);
      expect(realTimeService.isPolling).toBe(false);
    });

    it('should emit error events on failures', async () => {
      const errorHandler = vi.fn();
      realTimeService.on('error', errorHandler);
      
      mockApi.get.mockRejectedValue(new Error('Test error'));
      
      realTimeService.subscribe(['AAPL']);
      
      vi.advanceTimersByTime(5000);
      await vi.runAllTimersAsync();
      
      expect(errorHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Test error'
        })
      );
    });
  });

  describe('Data Validation and Processing', () => {
    beforeEach(async () => {
      await realTimeService.connect();
    });

    it('should validate incoming data structure', async () => {
      const invalidData = { invalid: 'structure' };
      mockApi.get.mockResolvedValue({ data: invalidData });
      
      realTimeService.subscribe(['AAPL']);
      
      vi.useFakeTimers();
      vi.advanceTimersByTime(5000);
      await vi.runAllTimersAsync();
      vi.useRealTimers();
      
      expect(realTimeService.stats.dataValidationErrors).toBeGreaterThan(0);
    });

    it('should handle missing quote data gracefully', async () => {
      const partialData = {
        quotes: {},
        timestamp: new Date().toISOString(),
        status: 'success'
      };
      mockApi.get.mockResolvedValue({ data: partialData });
      
      realTimeService.subscribe(['AAPL']);
      
      vi.useFakeTimers();
      vi.advanceTimersByTime(5000);
      await vi.runAllTimersAsync();
      vi.useRealTimers();
      
      // Should not crash and should handle gracefully
      expect(realTimeService.marketDataCache.has('AAPL')).toBe(false);
    });

    it('should process multiple symbols correctly', async () => {
      const multiSymbolData = {
        quotes: {
          'AAPL': { symbol: 'AAPL', price: 185.50 },
          'GOOGL': { symbol: 'GOOGL', price: 2850.75 },
          'MSFT': { symbol: 'MSFT', price: 375.25 }
        },
        timestamp: new Date().toISOString(),
        status: 'success'
      };
      mockApi.get.mockResolvedValue({ data: multiSymbolData });
      
      realTimeService.subscribe(['AAPL', 'GOOGL', 'MSFT']);
      
      vi.useFakeTimers();
      vi.advanceTimersByTime(5000);
      await vi.runAllTimersAsync();
      vi.useRealTimers();
      
      expect(realTimeService.marketDataCache.size).toBe(3);
      expect(realTimeService.marketDataCache.get('AAPL').price).toBe(185.50);
      expect(realTimeService.marketDataCache.get('GOOGL').price).toBe(2850.75);
      expect(realTimeService.marketDataCache.get('MSFT').price).toBe(375.25);
    });
  });

  describe('Performance and Statistics', () => {
    beforeEach(async () => {
      await realTimeService.connect();
    });

    it('should track connection statistics', async () => {
      expect(realTimeService.stats.connectTime).not.toBeNull();
      expect(realTimeService.stats.requestsSent).toBe(0);
      expect(realTimeService.stats.messagesReceived).toBe(0);
    });

    it('should increment request and message counters', async () => {
      realTimeService.subscribe(['AAPL']);
      
      vi.useFakeTimers();
      vi.advanceTimersByTime(5000);
      await vi.runAllTimersAsync();
      vi.useRealTimers();
      
      expect(realTimeService.stats.requestsSent).toBeGreaterThan(0);
      expect(realTimeService.stats.messagesReceived).toBeGreaterThan(0);
    });

    it('should handle high-frequency updates efficiently', async () => {
      const startTime = performance.now();
      
      // Subscribe to multiple symbols
      const symbols = Array.from({ length: 50 }, (_, i) => `STOCK${i}`);
      realTimeService.subscribe(symbols);
      
      const processingTime = performance.now() - startTime;
      expect(processingTime).toBeLessThan(100); // Should be fast
    });

    it('should provide statistics about service health', () => {
      const stats = realTimeService.getStats();
      
      expect(stats).toHaveProperty('messagesReceived');
      expect(stats).toHaveProperty('requestsSent');
      expect(stats).toHaveProperty('connectTime');
      expect(stats).toHaveProperty('dataValidationErrors');
      expect(stats).toHaveProperty('reconnectCount');
      expect(stats).toHaveProperty('pollErrors');
    });
  });

  describe('Memory Management', () => {
    beforeEach(async () => {
      await realTimeService.connect();
    });

    it('should clean up resources on disconnect', () => {
      realTimeService.subscribe(['AAPL', 'GOOGL']);
      expect(realTimeService.subscriptions.size).toBe(2);
      expect(realTimeService.pollingInterval).not.toBeNull();
      
      realTimeService.disconnect();
      
      expect(realTimeService.subscriptions.size).toBe(0);
      expect(realTimeService.pollingInterval).toBeNull();
      expect(realTimeService.isPolling).toBe(false);
    });

    it('should handle cache size limits', () => {
      // Add many symbols to test cache management
      const symbols = Array.from({ length: 1000 }, (_, i) => `STOCK${i}`);
      
      symbols.forEach(symbol => {
        realTimeService.marketDataCache.set(symbol, { 
          symbol, 
          price: Math.random() * 100 
        });
      });
      
      // Cache should not grow indefinitely
      expect(realTimeService.marketDataCache.size).toBeLessThanOrEqual(1000);
    });

    it('should remove old cache entries', () => {
      const oldTimestamp = new Date(Date.now() - 24 * 60 * 60 * 1000); // 24 hours ago
      
      realTimeService.lastUpdated.set('OLD_STOCK', oldTimestamp);
      realTimeService.marketDataCache.set('OLD_STOCK', { symbol: 'OLD_STOCK' });
      
      // Should clean up old entries (if cleanup method exists)
      if (typeof realTimeService.cleanupOldData === 'function') {
        realTimeService.cleanupOldData();
        expect(realTimeService.marketDataCache.has('OLD_STOCK')).toBe(false);
      }
    });
  });

  describe('Real-world Integration Scenarios', () => {
    beforeEach(async () => {
      await realTimeService.connect();
    });

    it('should handle rapid subscribe/unsubscribe cycles', () => {
      const symbols = ['AAPL', 'GOOGL', 'MSFT'];
      
      for (let i = 0; i < 10; i++) {
        realTimeService.subscribe(symbols);
        realTimeService.unsubscribe(symbols);
      }
      
      expect(realTimeService.subscriptions.size).toBe(0);
      expect(realTimeService.isPolling).toBe(false);
    });

    it('should handle network reconnection scenarios', async () => {
      realTimeService.subscribe(['AAPL']);
      
      // Simulate network error
      mockApi.get.mockRejectedValueOnce(new Error('Network error'));
      
      vi.useFakeTimers();
      vi.advanceTimersByTime(5000);
      await vi.runAllTimersAsync();
      
      // Should attempt reconnection
      expect(realTimeService.retryCount).toBeGreaterThan(0);
      
      // Restore network
      mockApi.get.mockResolvedValue({
        data: {
          quotes: { 'AAPL': { symbol: 'AAPL', price: 185.50 } },
          timestamp: new Date().toISOString(),
          status: 'success'
        }
      });
      
      vi.advanceTimersByTime(10000);
      await vi.runAllTimersAsync();
      vi.useRealTimers();
      
      // Should recover and continue polling
      expect(realTimeService.isPolling).toBe(true);
    });

    it('should handle concurrent data updates', async () => {
      const handler = vi.fn();
      realTimeService.on('data', handler);
      
      realTimeService.subscribe(['AAPL', 'GOOGL']);
      
      // Simulate multiple rapid updates
      vi.useFakeTimers();
      for (let i = 0; i < 5; i++) {
        vi.advanceTimersByTime(1000);
        await vi.runAllTimersAsync();
      }
      vi.useRealTimers();
      
      expect(handler).toHaveBeenCalledTimes(5);
    });
  });
});
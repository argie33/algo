/**
 * Real RealTimeDataService Unit Tests
 * Testing the actual realTimeDataService.js with HTTP polling, EventEmitter, and connection management
 * CRITICAL COMPONENT - Known to have connection and polling issues
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock the API service
vi.mock('../../../services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn()
  }
}));

// Import the REAL RealTimeDataService
import realTimeDataService from '../../../services/realTimeDataService';
import { api } from '../../../services/api';

describe('📡 Real RealTimeDataService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    
    // Reset service state
    realTimeDataService.isConnected = false;
    realTimeDataService.isPolling = false;
    realTimeDataService.subscriptions.clear();
    realTimeDataService.marketDataCache.clear();
    realTimeDataService.lastUpdated.clear();
    realTimeDataService.retryCount = 0;
    realTimeDataService.stats = {
      messagesReceived: 0,
      requestsSent: 0,
      connectTime: null,
      disconnectTime: null,
      dataValidationErrors: 0,
      reconnectCount: 0,
      pollErrors: 0
    };
    
    // Clear any existing interval
    if (realTimeDataService.pollingInterval) {
      clearInterval(realTimeDataService.pollingInterval);
      realTimeDataService.pollingInterval = null;
    }
    
    // Mock API responses
    api.post.mockResolvedValue({ data: { success: true } });
    api.delete.mockResolvedValue({ data: { success: true } });
    api.get.mockResolvedValue({
      data: {
        success: true,
        data: {
          data: {
            'AAPL': {
              symbol: 'AAPL',
              price: 185.50,
              change: 2.25,
              changePercent: 1.23,
              volume: 1250000,
              timestamp: Date.now()
            }
          }
        }
      }
    });

    // Mock console to avoid noise
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    
    // Clean up any intervals
    if (realTimeDataService.pollingInterval) {
      clearInterval(realTimeDataService.pollingInterval);
      realTimeDataService.pollingInterval = null;
    }
  });

  describe('Service Initialization', () => {
    it('should initialize with correct default configuration', () => {
      expect(realTimeDataService.config).toEqual({
        pollingInterval: 5000,
        maxRetries: 5,
        backoffMultiplier: 1.5,
        timeout: 10000
      });
      
      expect(realTimeDataService.subscriptions).toBeInstanceOf(Set);
      expect(realTimeDataService.marketDataCache).toBeInstanceOf(Map);
      expect(realTimeDataService.lastUpdated).toBeInstanceOf(Map);
      expect(realTimeDataService.maxRetries).toBe(5);
    });

    it('should extend EventEmitter with correct methods', () => {
      expect(typeof realTimeDataService.on).toBe('function');
      expect(typeof realTimeDataService.off).toBe('function');
      expect(typeof realTimeDataService.emit).toBe('function');
      expect(typeof realTimeDataService.removeAllListeners).toBe('function');
    });

    it('should initialize with disconnected state', () => {
      expect(realTimeDataService.isConnected).toBe(false);
      expect(realTimeDataService.isPolling).toBe(false);
      expect(realTimeDataService.retryCount).toBe(0);
      expect(realTimeDataService.subscriptions.size).toBe(0);
    });

    it('should initialize with empty caches', () => {
      expect(realTimeDataService.marketDataCache.size).toBe(0);
      expect(realTimeDataService.lastUpdated.size).toBe(0);
    });
  });

  describe('EventEmitter Implementation', () => {
    it('should add and trigger event listeners', () => {
      const mockListener = vi.fn();
      
      realTimeDataService.on('test_event', mockListener);
      realTimeDataService.emit('test_event', 'test_data');
      
      expect(mockListener).toHaveBeenCalledWith('test_data');
    });

    it('should remove specific event listeners', () => {
      const mockListener1 = vi.fn();
      const mockListener2 = vi.fn();
      
      realTimeDataService.on('test_event', mockListener1);
      realTimeDataService.on('test_event', mockListener2);
      
      realTimeDataService.off('test_event', mockListener1);
      realTimeDataService.emit('test_event');
      
      expect(mockListener1).not.toHaveBeenCalled();
      expect(mockListener2).toHaveBeenCalled();
    });

    it('should remove all listeners for an event', () => {
      const mockListener1 = vi.fn();
      const mockListener2 = vi.fn();
      
      realTimeDataService.on('test_event', mockListener1);
      realTimeDataService.on('test_event', mockListener2);
      
      realTimeDataService.removeAllListeners('test_event');
      realTimeDataService.emit('test_event');
      
      expect(mockListener1).not.toHaveBeenCalled();
      expect(mockListener2).not.toHaveBeenCalled();
    });

    it('should handle multiple listeners for same event', () => {
      const mockListener1 = vi.fn();
      const mockListener2 = vi.fn();
      const mockListener3 = vi.fn();
      
      realTimeDataService.on('multi_test', mockListener1);
      realTimeDataService.on('multi_test', mockListener2);
      realTimeDataService.on('multi_test', mockListener3);
      
      realTimeDataService.emit('multi_test', 'data');
      
      expect(mockListener1).toHaveBeenCalledWith('data');
      expect(mockListener2).toHaveBeenCalledWith('data');
      expect(mockListener3).toHaveBeenCalledWith('data');
    });
  });

  describe('Connection Management', () => {
    it('should connect successfully', async () => {
      const connectListener = vi.fn();
      realTimeDataService.on('connected', connectListener);
      
      await realTimeDataService.connect();
      
      expect(realTimeDataService.isConnected).toBe(true);
      expect(realTimeDataService.stats.connectTime).toBeInstanceOf(Date);
      expect(realTimeDataService.retryCount).toBe(0);
      expect(connectListener).toHaveBeenCalled();
    });

    it('should not connect if already connected', async () => {
      realTimeDataService.isConnected = true;
      
      const result = await realTimeDataService.connect();
      
      expect(result).toBeUndefined();
    });

    it('should disconnect successfully', () => {
      realTimeDataService.isConnected = true;
      realTimeDataService.isPolling = true;
      
      const disconnectListener = vi.fn();
      realTimeDataService.on('disconnected', disconnectListener);
      
      realTimeDataService.disconnect();
      
      expect(realTimeDataService.isConnected).toBe(false);
      expect(realTimeDataService.isPolling).toBe(false);
      expect(realTimeDataService.stats.disconnectTime).toBeInstanceOf(Date);
      expect(disconnectListener).toHaveBeenCalled();
    });

    it('should not disconnect if already disconnected', () => {
      realTimeDataService.isConnected = false;
      
      realTimeDataService.disconnect();
      
      // Should handle gracefully without errors
      expect(realTimeDataService.isConnected).toBe(false);
    });

    it('should start polling when connecting with existing subscriptions', async () => {
      realTimeDataService.subscriptions.add('AAPL');
      realTimeDataService.subscriptions.add('MSFT');
      
      await realTimeDataService.connect();
      
      expect(realTimeDataService.isPolling).toBe(true);
      expect(realTimeDataService.pollingInterval).not.toBeNull();
    });
  });

  describe('Subscription Management', () => {
    beforeEach(async () => {
      await realTimeDataService.connect();
    });

    it('should subscribe to single symbol successfully', async () => {
      const subscribeListener = vi.fn();
      realTimeDataService.on('subscribed', subscribeListener);
      
      const result = await realTimeDataService.subscribeMarketData('AAPL');
      
      expect(result).toBe(true);
      expect(realTimeDataService.subscriptions.has('AAPL')).toBe(true);
      expect(api.post).toHaveBeenCalledWith('/api/websocket/subscribe', {
        symbols: ['AAPL'],
        dataTypes: ['quotes']
      });
      expect(subscribeListener).toHaveBeenCalledWith({
        symbols: ['AAPL'],
        channels: ['quotes']
      });
    });

    it('should subscribe to multiple symbols', async () => {
      const symbols = ['AAPL', 'MSFT', 'GOOGL'];
      
      const result = await realTimeDataService.subscribeMarketData(symbols, ['quotes', 'trades']);
      
      expect(result).toBe(true);
      expect(realTimeDataService.subscriptions.has('AAPL')).toBe(true);
      expect(realTimeDataService.subscriptions.has('MSFT')).toBe(true);
      expect(realTimeDataService.subscriptions.has('GOOGL')).toBe(true);
      expect(api.post).toHaveBeenCalledWith('/api/websocket/subscribe', {
        symbols: symbols,
        dataTypes: ['quotes', 'trades']
      });
    });

    it('should handle subscription API failures', async () => {
      api.post.mockRejectedValue(new Error('Subscription failed'));
      
      const errorListener = vi.fn();
      realTimeDataService.on('error', errorListener);
      
      const result = await realTimeDataService.subscribeMarketData('FAIL');
      
      expect(result).toBe(false);
      expect(errorListener).toHaveBeenCalledWith(expect.any(Error));
    });

    it('should start polling after successful subscription', async () => {
      expect(realTimeDataService.isPolling).toBe(false);
      
      await realTimeDataService.subscribeMarketData('AAPL');
      
      expect(realTimeDataService.isPolling).toBe(true);
      expect(realTimeDataService.pollingInterval).not.toBeNull();
    });

    it('should normalize symbol case to uppercase', async () => {
      await realTimeDataService.subscribeMarketData('aapl');
      
      expect(realTimeDataService.subscriptions.has('AAPL')).toBe(true);
      expect(realTimeDataService.subscriptions.has('aapl')).toBe(false);
    });

    it('should unsubscribe from symbols successfully', async () => {
      await realTimeDataService.subscribeMarketData(['AAPL', 'MSFT']);
      
      const unsubscribeListener = vi.fn();
      realTimeDataService.on('unsubscribed', unsubscribeListener);
      
      const result = await realTimeDataService.unsubscribe('AAPL');
      
      expect(result).toBe(true);
      expect(realTimeDataService.subscriptions.has('AAPL')).toBe(false);
      expect(realTimeDataService.subscriptions.has('MSFT')).toBe(true);
      expect(api.delete).toHaveBeenCalledWith('/api/websocket/subscribe', {
        data: { symbols: ['AAPL'] }
      });
      expect(unsubscribeListener).toHaveBeenCalledWith({ symbols: ['AAPL'] });
    });

    it('should stop polling when no subscriptions remain', async () => {
      await realTimeDataService.subscribeMarketData('AAPL');
      expect(realTimeDataService.isPolling).toBe(true);
      
      await realTimeDataService.unsubscribe('AAPL');
      
      expect(realTimeDataService.isPolling).toBe(false);
      expect(realTimeDataService.pollingInterval).toBeNull();
    });

    it('should handle unsubscribe API failures', async () => {
      await realTimeDataService.subscribeMarketData('AAPL');
      
      api.delete.mockRejectedValue(new Error('Unsubscribe failed'));
      
      const errorListener = vi.fn();
      realTimeDataService.on('error', errorListener);
      
      const result = await realTimeDataService.unsubscribe('AAPL');
      
      expect(result).toBe(false);
      expect(errorListener).toHaveBeenCalledWith(expect.any(Error));
    });
  });

  describe('Polling Mechanism', () => {
    beforeEach(async () => {
      await realTimeDataService.connect();
      await realTimeDataService.subscribeMarketData(['AAPL', 'MSFT']);
    });

    it('should poll market data at correct intervals', async () => {
      expect(api.get).toHaveBeenCalledWith('/api/websocket/stream/AAPL,MSFT', {
        timeout: 10000
      });
      
      // Fast forward to next poll interval
      vi.advanceTimersByTime(5000);
      
      expect(api.get).toHaveBeenCalledTimes(2);
    });

    it('should process successful market data responses', async () => {
      const marketDataListener = vi.fn();
      const symbolDataListener = vi.fn();
      
      realTimeDataService.on('marketData', marketDataListener);
      realTimeDataService.on('marketData_AAPL', symbolDataListener);
      
      // Trigger initial poll
      await vi.advanceTimersByTime(1000);
      
      expect(realTimeDataService.stats.messagesReceived).toBe(1);
      expect(realTimeDataService.stats.requestsSent).toBe(1);
      expect(marketDataListener).toHaveBeenCalled();
      expect(symbolDataListener).toHaveBeenCalled();
    });

    it('should cache market data correctly', async () => {
      await vi.advanceTimersByTime(1000);
      
      const cachedData = realTimeDataService.getMarketData('AAPL');
      
      expect(cachedData).toEqual(expect.objectContaining({
        symbol: 'AAPL',
        price: 185.50,
        change: 2.25,
        changePercent: 1.23,
        receivedAt: expect.any(Number)
      }));
      
      expect(realTimeDataService.lastUpdated.has('AAPL')).toBe(true);
    });

    it('should not poll when disconnected', async () => {
      realTimeDataService.disconnect();
      
      const initialCallCount = api.get.mock.calls.length;
      
      vi.advanceTimersByTime(10000);
      
      expect(api.get).toHaveBeenCalledTimes(initialCallCount);
    });

    it('should not poll when no subscriptions exist', () => {
      realTimeDataService.subscriptions.clear();
      realTimeDataService.startPolling();
      
      expect(realTimeDataService.isPolling).toBe(false);
    });

    it('should handle invalid polling responses', async () => {
      api.get.mockResolvedValue({ data: { success: false } });
      
      vi.advanceTimersByTime(5000);
      
      expect(console.warn).toHaveBeenCalledWith(
        '⚠️ Invalid response from market data polling:',
        { success: false }
      );
    });
  });

  describe('Error Handling and Retry Logic', () => {
    beforeEach(async () => {
      await realTimeDataService.connect();
      await realTimeDataService.subscribeMarketData('AAPL');
    });

    it('should handle polling errors with retry logic', async () => {
      api.get.mockRejectedValue(new Error('Network error'));
      
      vi.advanceTimersByTime(5000); // Trigger poll
      
      expect(realTimeDataService.stats.pollErrors).toBe(1);
      expect(realTimeDataService.retryCount).toBe(1);
      
      // Should retry after backoff delay
      const expectedDelay = 5000 * Math.pow(1.5, 1);
      vi.advanceTimersByTime(expectedDelay);
      
      expect(api.get).toHaveBeenCalledTimes(2);
    });

    it('should stop polling after max retries', async () => {
      api.get.mockRejectedValue(new Error('Persistent error'));
      
      const errorListener = vi.fn();
      realTimeDataService.on('error', errorListener);
      
      // Trigger polls that will fail
      for (let i = 0; i <= realTimeDataService.config.maxRetries; i++) {
        vi.advanceTimersByTime(5000);
        await vi.advanceTimersByTime(1000);
      }
      
      expect(realTimeDataService.retryCount).toBe(realTimeDataService.config.maxRetries);
      expect(realTimeDataService.isPolling).toBe(false);
      expect(errorListener).toHaveBeenCalled();
    });

    it('should handle authentication errors by disconnecting', async () => {
      api.get.mockRejectedValue({
        response: { status: 401 }
      });
      
      const errorListener = vi.fn();
      realTimeDataService.on('error', errorListener);
      
      vi.advanceTimersByTime(5000);
      
      expect(realTimeDataService.isConnected).toBe(false);
      expect(errorListener).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Authentication required'
        })
      );
    });

    it('should reset retry count on successful poll', async () => {
      // First, cause failures to increase retry count
      api.get.mockRejectedValueOnce(new Error('Temporary error'));
      vi.advanceTimersByTime(5000);
      
      expect(realTimeDataService.retryCount).toBe(1);
      
      // Then succeed
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: { data: { 'AAPL': { symbol: 'AAPL', price: 185.50 } } }
        }
      });
      
      const retryDelay = 5000 * Math.pow(1.5, 1);
      vi.advanceTimersByTime(retryDelay);
      
      expect(realTimeDataService.retryCount).toBe(0);
    });

    it('should handle malformed market data gracefully', async () => {
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: null // Malformed data
        }
      });
      
      expect(() => {
        vi.advanceTimersByTime(5000);
      }).not.toThrow();
    });
  });

  describe('Data Management and Caching', () => {
    beforeEach(async () => {
      await realTimeDataService.connect();
      await realTimeDataService.subscribeMarketData(['AAPL', 'MSFT']);
      await vi.advanceTimersByTime(1000);
    });

    it('should get cached market data for specific symbol', () => {
      const aaplData = realTimeDataService.getMarketData('AAPL');
      const msftData = realTimeDataService.getMarketData('MSFT');
      const noData = realTimeDataService.getMarketData('GOOGL');
      
      expect(aaplData).toBeDefined();
      expect(aaplData.symbol).toBe('AAPL');
      expect(msftData).toBeUndefined(); // Not in mock response
      expect(noData).toBeUndefined();
    });

    it('should handle case-insensitive symbol lookup', () => {
      const aaplData1 = realTimeDataService.getMarketData('AAPL');
      const aaplData2 = realTimeDataService.getMarketData('aapl');
      
      expect(aaplData1).toEqual(aaplData2);
    });

    it('should get all cached market data', () => {
      const allData = realTimeDataService.getAllMarketData();
      
      expect(allData).toBeInstanceOf(Object);
      expect(allData.AAPL).toBeDefined();
    });

    it('should detect stale data correctly', () => {
      const isStaleImmediate = realTimeDataService.isDataStale('AAPL', 60000);
      expect(isStaleImmediate).toBe(false);
      
      const isStaleShortWindow = realTimeDataService.isDataStale('AAPL', 1);
      expect(isStaleShortWindow).toBe(true);
      
      const isStaleNonExistent = realTimeDataService.isDataStale('NONEXISTENT');
      expect(isStaleNonExistent).toBe(true);
    });

    it('should clear cache correctly', () => {
      expect(realTimeDataService.marketDataCache.size).toBeGreaterThan(0);
      expect(realTimeDataService.lastUpdated.size).toBeGreaterThan(0);
      
      realTimeDataService.clearCache();
      
      expect(realTimeDataService.marketDataCache.size).toBe(0);
      expect(realTimeDataService.lastUpdated.size).toBe(0);
    });

    it('should process market data with error symbols correctly', () => {
      const mockDataWithErrors = {
        data: {
          'AAPL': { symbol: 'AAPL', price: 185.50 },
          'ERROR_SYMBOL': { error: 'Symbol not found' }
        }
      };
      
      realTimeDataService.processMarketData(mockDataWithErrors);
      
      expect(realTimeDataService.getMarketData('AAPL')).toBeDefined();
      expect(realTimeDataService.getMarketData('ERROR_SYMBOL')).toBeUndefined();
    });
  });

  describe('Service Status and Statistics', () => {
    it('should provide accurate statistics', async () => {
      await realTimeDataService.connect();
      await realTimeDataService.subscribeMarketData(['AAPL', 'MSFT']);
      await vi.advanceTimersByTime(1000);
      
      const stats = realTimeDataService.getStats();
      
      expect(stats).toEqual(expect.objectContaining({
        messagesReceived: expect.any(Number),
        requestsSent: expect.any(Number),
        isConnected: true,
        isPolling: true,
        subscriptions: 2,
        cachedSymbols: expect.any(Number),
        retryCount: 0,
        connectTime: expect.any(Date),
        pollErrors: 0
      }));
    });

    it('should get current subscriptions list', async () => {
      await realTimeDataService.connect();
      await realTimeDataService.subscribeMarketData(['AAPL', 'MSFT', 'GOOGL']);
      
      const subscriptions = realTimeDataService.getSubscriptions();
      
      expect(subscriptions).toEqual(expect.arrayContaining(['AAPL', 'MSFT', 'GOOGL']));
      expect(subscriptions).toHaveLength(3);
    });

    it('should get connection status correctly', async () => {
      expect(realTimeDataService.getConnectionStatus()).toBe('DISCONNECTED');
      
      await realTimeDataService.connect();
      expect(realTimeDataService.getConnectionStatus()).toBe('CONNECTED');
      
      await realTimeDataService.subscribeMarketData('AAPL');
      expect(realTimeDataService.getConnectionStatus()).toBe('POLLING');
    });
  });

  describe('Backend Integration Methods', () => {
    it('should get user subscriptions from backend', async () => {
      api.get.mockResolvedValue({
        data: {
          data: {
            symbols: ['AAPL', 'MSFT', 'GOOGL']
          }
        }
      });
      
      const subscriptions = await realTimeDataService.getUserSubscriptions();
      
      expect(api.get).toHaveBeenCalledWith('/api/websocket/subscriptions');
      expect(subscriptions).toEqual(['AAPL', 'MSFT', 'GOOGL']);
    });

    it('should handle getUserSubscriptions API failure', async () => {
      api.get.mockRejectedValue(new Error('API failed'));
      
      const subscriptions = await realTimeDataService.getUserSubscriptions();
      
      expect(subscriptions).toEqual([]);
      expect(console.error).toHaveBeenCalledWith(
        '❌ Failed to get user subscriptions:',
        expect.any(Error)
      );
    });

    it('should get health status from backend', async () => {
      const mockHealthData = {
        status: 'healthy',
        uptime: 12345,
        connections: 42
      };
      
      api.get.mockResolvedValue({
        data: { data: mockHealthData }
      });
      
      const health = await realTimeDataService.getHealthStatus();
      
      expect(api.get).toHaveBeenCalledWith('/api/websocket/health');
      expect(health).toEqual(mockHealthData);
    });

    it('should handle getHealthStatus API failure', async () => {
      api.get.mockRejectedValue(new Error('Health check failed'));
      
      const health = await realTimeDataService.getHealthStatus();
      
      expect(health).toEqual({
        status: 'error',
        error: 'Health check failed'
      });
    });
  });

  describe('Edge Cases and Memory Management', () => {
    it('should handle large numbers of subscriptions efficiently', async () => {
      await realTimeDataService.connect();
      
      const symbols = Array.from({ length: 1000 }, (_, i) => `STOCK${i}`);
      
      const startTime = performance.now();
      await realTimeDataService.subscribeMarketData(symbols);
      const duration = performance.now() - startTime;
      
      expect(duration).toBeLessThan(100); // Should complete within 100ms
      expect(realTimeDataService.subscriptions.size).toBe(1000);
    });

    it('should handle rapid subscribe/unsubscribe cycles', async () => {
      await realTimeDataService.connect();
      
      for (let i = 0; i < 10; i++) {
        await realTimeDataService.subscribeMarketData(`STOCK${i}`);
        await realTimeDataService.unsubscribe(`STOCK${i}`);
      }
      
      expect(realTimeDataService.subscriptions.size).toBe(0);
      expect(realTimeDataService.isPolling).toBe(false);
    });

    it('should handle polling with very large datasets', async () => {
      const largeDataset = {};
      for (let i = 0; i < 5000; i++) {
        largeDataset[`STOCK${i}`] = {
          symbol: `STOCK${i}`,
          price: Math.random() * 1000,
          timestamp: Date.now()
        };
      }
      
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: { data: largeDataset }
        }
      });
      
      await realTimeDataService.connect();
      await realTimeDataService.subscribeMarketData('AAPL');
      
      const startTime = performance.now();
      vi.advanceTimersByTime(5000);
      const duration = performance.now() - startTime;
      
      expect(duration).toBeLessThan(1000); // Should process within 1 second
      expect(realTimeDataService.marketDataCache.size).toBe(5000);
    });

    it('should handle concurrent polling requests safely', async () => {
      await realTimeDataService.connect();
      await realTimeDataService.subscribeMarketData('AAPL');
      
      // Simulate multiple concurrent polls
      const promises = [];
      for (let i = 0; i < 5; i++) {
        promises.push(realTimeDataService.pollMarketData());
      }
      
      await Promise.all(promises);
      
      // Should handle gracefully without errors
      expect(realTimeDataService.stats.requestsSent).toBeGreaterThan(0);
    });

    it('should cleanup resources on disconnect', () => {
      realTimeDataService.isConnected = true;
      realTimeDataService.isPolling = true;
      realTimeDataService.pollingInterval = setInterval(() => {}, 1000);
      
      realTimeDataService.disconnect();
      
      expect(realTimeDataService.isConnected).toBe(false);
      expect(realTimeDataService.isPolling).toBe(false);
      expect(realTimeDataService.pollingInterval).toBeNull();
    });
  });

  describe('Real-World Scenario Testing', () => {
    it('should handle network reconnection scenario', async () => {
      await realTimeDataService.connect();
      await realTimeDataService.subscribeMarketData('AAPL');
      
      // Simulate network failure
      api.get.mockRejectedValue(new Error('Network unavailable'));
      vi.advanceTimersByTime(5000);
      
      expect(realTimeDataService.stats.pollErrors).toBe(1);
      
      // Simulate network recovery
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: { data: { 'AAPL': { symbol: 'AAPL', price: 186.00 } } }
        }
      });
      
      const retryDelay = 5000 * Math.pow(1.5, 1);
      vi.advanceTimersByTime(retryDelay);
      
      expect(realTimeDataService.retryCount).toBe(0); // Should reset on success
      expect(realTimeDataService.getMarketData('AAPL').price).toBe(186.00);
    });

    it('should handle partial subscription failures', async () => {
      await realTimeDataService.connect();
      
      // First subscription succeeds
      api.post.mockResolvedValueOnce({ data: { success: true } });
      await realTimeDataService.subscribeMarketData('AAPL');
      
      // Second subscription fails
      api.post.mockRejectedValueOnce(new Error('Symbol not found'));
      const result = await realTimeDataService.subscribeMarketData('INVALID');
      
      expect(realTimeDataService.subscriptions.has('AAPL')).toBe(true);
      expect(realTimeDataService.subscriptions.has('INVALID')).toBe(false);
      expect(result).toBe(false);
    });

    it('should handle mixed market data with valid and invalid symbols', () => {
      const mixedData = {
        data: {
          'AAPL': { symbol: 'AAPL', price: 185.50 },
          'MSFT': { symbol: 'MSFT', price: 375.00 },
          'INVALID': { error: 'Symbol not found' },
          'GOOGL': { symbol: 'GOOGL', price: 2850.00 }
        }
      };
      
      realTimeDataService.processMarketData(mixedData);
      
      expect(realTimeDataService.getMarketData('AAPL')).toBeDefined();
      expect(realTimeDataService.getMarketData('MSFT')).toBeDefined();
      expect(realTimeDataService.getMarketData('GOOGL')).toBeDefined();
      expect(realTimeDataService.getMarketData('INVALID')).toBeUndefined();
    });
  });
});
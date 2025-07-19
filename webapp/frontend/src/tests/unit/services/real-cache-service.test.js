/**
 * Real Cache Service Unit Tests
 * Testing the actual cacheService.js with memory management and localStorage persistence
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock localStorage
const localStorageMock = {
  store: new Map(),
  getItem: vi.fn((key) => localStorageMock.store.get(key) || null),
  setItem: vi.fn((key, value) => localStorageMock.store.set(key, value)),
  removeItem: vi.fn((key) => localStorageMock.store.delete(key)),
  clear: vi.fn(() => localStorageMock.store.clear()),
  get length() { return localStorageMock.store.size; },
  key: vi.fn((index) => Array.from(localStorageMock.store.keys())[index] || null),
  keys: vi.fn(() => Array.from(localStorageMock.store.keys()))
};

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true
});

// Import the REAL CacheService after localStorage mock
import cacheService, { CacheConfigs } from '../../../services/cacheService';

describe('💾 Real Cache Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    
    // Clear cache and localStorage before each test
    cacheService.clear();
    localStorageMock.store.clear();
    
    // Reset stats
    cacheService.stats = {
      hits: 0,
      misses: 0,
      sets: 0,
      evictions: 0,
      lastCleanup: Date.now()
    };

    // Mock console to avoid noise
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe('Service Initialization', () => {
    it('should initialize with correct default settings', () => {
      expect(cacheService.maxSize).toBe(1000);
      expect(cacheService.defaultTTL).toBe(5 * 60 * 1000); // 5 minutes
      expect(cacheService.cache).toBeInstanceOf(Map);
      expect(cacheService.timestamps).toBeInstanceOf(Map);
    });

    it('should initialize with empty cache', () => {
      expect(cacheService.cache.size).toBe(0);
      expect(cacheService.timestamps.size).toBe(0);
    });

    it('should have initial stats with zero values', () => {
      expect(cacheService.stats.hits).toBe(0);
      expect(cacheService.stats.misses).toBe(0);
      expect(cacheService.stats.sets).toBe(0);
      expect(cacheService.stats.evictions).toBe(0);
    });
  });

  describe('Cache Key Generation', () => {
    it('should generate simple keys without parameters', () => {
      const key = cacheService.generateKey('stock_quote');
      expect(key).toBe('stock_quote');
    });

    it('should generate keys with parameters', () => {
      const key = cacheService.generateKey('stock_quote', { symbol: 'AAPL', interval: '1d' });
      expect(key).toBe('stock_quote?interval=1d&symbol=AAPL');
    });

    it('should sort parameters for consistent keys', () => {
      const key1 = cacheService.generateKey('data', { b: '2', a: '1' });
      const key2 = cacheService.generateKey('data', { a: '1', b: '2' });
      expect(key1).toBe(key2);
      expect(key1).toBe('data?a=1&b=2');
    });

    it('should handle empty parameters object', () => {
      const key = cacheService.generateKey('test', {});
      expect(key).toBe('test');
    });

    it('should handle special characters in parameters', () => {
      const key = cacheService.generateKey('search', { query: 'AAPL+MSFT', type: 'stock&option' });
      expect(key).toBe('search?query=AAPL+MSFT&type=stock&option');
    });
  });

  describe('Basic Cache Operations', () => {
    it('should set and get cache entries', () => {
      const testData = { symbol: 'AAPL', price: 185.50 };
      
      const success = cacheService.set('test_key', testData);
      expect(success).toBe(true);
      
      const retrieved = cacheService.get('test_key');
      expect(retrieved).toEqual(testData);
      
      expect(cacheService.stats.sets).toBe(1);
      expect(cacheService.stats.hits).toBe(1);
      expect(cacheService.stats.misses).toBe(0);
    });

    it('should return null for non-existent keys', () => {
      const result = cacheService.get('non_existent_key');
      
      expect(result).toBeNull();
      expect(cacheService.stats.misses).toBe(1);
      expect(cacheService.stats.hits).toBe(0);
    });

    it('should check if key exists', () => {
      cacheService.set('existing_key', 'test_value');
      
      expect(cacheService.has('existing_key')).toBe(true);
      expect(cacheService.has('non_existing_key')).toBe(false);
    });

    it('should delete cache entries', () => {
      cacheService.set('delete_me', 'test_value');
      expect(cacheService.has('delete_me')).toBe(true);
      
      const deleted = cacheService.delete('delete_me');
      expect(deleted).toBe(true);
      expect(cacheService.has('delete_me')).toBe(false);
    });

    it('should clear all cache entries', () => {
      cacheService.set('key1', 'value1');
      cacheService.set('key2', 'value2');
      cacheService.set('key3', 'value3');
      
      expect(cacheService.cache.size).toBe(3);
      
      cacheService.clear();
      
      expect(cacheService.cache.size).toBe(0);
      expect(cacheService.timestamps.size).toBe(0);
    });
  });

  describe('TTL and Expiration', () => {
    it('should expire entries after TTL', () => {
      const shortTTL = 1000; // 1 second
      cacheService.set('expiring_key', 'test_value', shortTTL);
      
      expect(cacheService.get('expiring_key')).toBe('test_value');
      
      // Fast forward time past TTL
      vi.advanceTimersByTime(1100);
      
      expect(cacheService.get('expiring_key')).toBeNull();
      expect(cacheService.stats.misses).toBe(1);
    });

    it('should use default TTL when not specified', () => {
      cacheService.set('default_ttl_key', 'test_value');
      
      const entry = cacheService.cache.get('default_ttl_key');
      expect(entry.ttl).toBe(cacheService.defaultTTL);
    });

    it('should correctly identify expired entries', () => {
      const entry = {
        value: 'test',
        timestamp: Date.now() - 6000, // 6 seconds ago
        ttl: 5000 // 5 second TTL
      };
      
      expect(cacheService.isExpired(entry)).toBe(true);
      
      const freshEntry = {
        value: 'test',
        timestamp: Date.now() - 3000, // 3 seconds ago
        ttl: 5000 // 5 second TTL
      };
      
      expect(cacheService.isExpired(freshEntry)).toBe(false);
    });

    it('should handle entries with infinite TTL', () => {
      cacheService.set('permanent_key', 'permanent_value', Infinity);
      
      // Fast forward a very long time
      vi.advanceTimersByTime(365 * 24 * 60 * 60 * 1000); // 1 year
      
      expect(cacheService.get('permanent_key')).toBe('permanent_value');
    });
  });

  describe('Memory Management and Eviction', () => {
    it('should evict oldest entries when cache is full', () => {
      // Set max size to small number for testing
      const originalMaxSize = cacheService.maxSize;
      cacheService.maxSize = 3;
      
      cacheService.set('key1', 'value1');
      vi.advanceTimersByTime(100);
      cacheService.set('key2', 'value2');
      vi.advanceTimersByTime(100);
      cacheService.set('key3', 'value3');
      
      expect(cacheService.cache.size).toBe(3);
      
      // This should trigger eviction
      cacheService.set('key4', 'value4');
      
      expect(cacheService.cache.size).toBeLessThanOrEqual(3);
      expect(cacheService.stats.evictions).toBeGreaterThan(0);
      
      // Restore original max size
      cacheService.maxSize = originalMaxSize;
    });

    it('should estimate memory usage', () => {
      cacheService.set('test_key', { data: 'test_value', number: 123, array: [1, 2, 3] });
      
      const memoryUsage = cacheService.estimateMemoryUsage();
      
      expect(memoryUsage).toBeGreaterThan(0);
      expect(typeof memoryUsage).toBe('number');
    });

    it('should track access counts and last access times', () => {
      cacheService.set('access_test', 'test_value');
      
      // Access the entry multiple times
      cacheService.get('access_test');
      cacheService.get('access_test');
      cacheService.get('access_test');
      
      const entry = cacheService.cache.get('access_test');
      expect(entry.accessCount).toBe(3);
      expect(entry.lastAccess).toBeCloseTo(Date.now(), -2);
    });

    it('should get most accessed items', () => {
      cacheService.set('item1', 'value1');
      cacheService.set('item2', 'value2');
      cacheService.set('item3', 'value3');
      
      // Access items different amounts
      cacheService.get('item1'); // 1 access
      cacheService.get('item2'); cacheService.get('item2'); // 2 accesses
      cacheService.get('item3'); cacheService.get('item3'); cacheService.get('item3'); // 3 accesses
      
      const mostAccessed = cacheService.getMostAccessed(2);
      
      expect(mostAccessed).toHaveLength(2);
      expect(mostAccessed[0].key).toBe('item3');
      expect(mostAccessed[0].accessCount).toBe(3);
      expect(mostAccessed[1].key).toBe('item2');
      expect(mostAccessed[1].accessCount).toBe(2);
    });
  });

  describe('Cleanup and Maintenance', () => {
    it('should clean up expired entries', () => {
      const shortTTL = 1000;
      const longTTL = 10000;
      
      cacheService.set('short_lived', 'expires_soon', shortTTL);
      cacheService.set('long_lived', 'stays_alive', longTTL);
      
      expect(cacheService.cache.size).toBe(2);
      
      // Fast forward past short TTL but not long TTL
      vi.advanceTimersByTime(1500);
      
      cacheService.cleanup();
      
      expect(cacheService.cache.size).toBe(1);
      expect(cacheService.has('short_lived')).toBe(false);
      expect(cacheService.has('long_lived')).toBe(true);
    });

    it('should perform automatic cleanup at intervals', () => {
      const cleanupSpy = vi.spyOn(cacheService, 'cleanup');
      
      cacheService.set('expiring_key', 'value', 1000);
      
      // Fast forward to trigger automatic cleanup
      vi.advanceTimersByTime(5 * 60 * 1000 + 100); // 5 minutes + buffer
      
      expect(cleanupSpy).toHaveBeenCalled();
    });

    it('should update lastCleanup timestamp', () => {
      const initialCleanup = cacheService.stats.lastCleanup;
      
      vi.advanceTimersByTime(1000);
      cacheService.cleanup();
      
      expect(cacheService.stats.lastCleanup).toBeGreaterThan(initialCleanup);
    });
  });

  describe('LocalStorage Persistence', () => {
    it('should persist entries to localStorage when requested', () => {
      const testData = { symbol: 'AAPL', price: 185.50 };
      
      cacheService.set('persistent_key', testData, 60000, true);
      
      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'cache_persistent_key',
        expect.stringContaining('"value":{"symbol":"AAPL","price":185.5}')
      );
    });

    it('should not persist entries when persist is false', () => {
      cacheService.set('temp_key', 'temp_value', 60000, false);
      
      expect(localStorageMock.setItem).not.toHaveBeenCalledWith(
        'cache_temp_key',
        expect.any(String)
      );
    });

    it('should load persistent entries from localStorage on initialization', () => {
      const persistentData = {
        value: { symbol: 'MSFT', price: 375.00 },
        timestamp: Date.now() - 1000,
        ttl: 300000
      };
      
      localStorageMock.store.set('cache_loaded_key', JSON.stringify(persistentData));
      
      // Simulate loading
      cacheService.loadPersistentCache();
      
      const loaded = cacheService.get('loaded_key');
      expect(loaded).toEqual(persistentData.value);
    });

    it('should not load expired entries from localStorage', () => {
      const expiredData = {
        value: { symbol: 'EXPIRED', price: 100.00 },
        timestamp: Date.now() - 400000, // Way past expiration
        ttl: 300000 // 5 minutes
      };
      
      localStorageMock.store.set('cache_expired_key', JSON.stringify(expiredData));
      
      cacheService.loadPersistentCache();
      
      const loaded = cacheService.get('expired_key');
      expect(loaded).toBeNull();
      expect(localStorageMock.removeItem).toHaveBeenCalledWith('cache_expired_key');
    });

    it('should remove from localStorage when deleting cache entry', () => {
      cacheService.set('delete_persistent', 'value', 60000, true);
      
      cacheService.delete('delete_persistent');
      
      expect(localStorageMock.removeItem).toHaveBeenCalledWith('cache_delete_persistent');
    });

    it('should clear localStorage when clearing cache', () => {
      localStorageMock.store.set('cache_item1', 'data1');
      localStorageMock.store.set('cache_item2', 'data2');
      localStorageMock.store.set('other_item', 'other_data');
      
      cacheService.clear();
      
      expect(localStorageMock.removeItem).toHaveBeenCalledWith('cache_item1');
      expect(localStorageMock.removeItem).toHaveBeenCalledWith('cache_item2');
      expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('other_item');
    });

    it('should handle localStorage errors gracefully', () => {
      localStorageMock.setItem.mockImplementation(() => {
        throw new Error('localStorage is full');
      });
      
      // Should not throw
      expect(() => {
        cacheService.set('error_key', 'value', 60000, true);
      }).not.toThrow();
      
      expect(console.warn).toHaveBeenCalledWith('Failed to persist to localStorage:', expect.any(Error));
    });
  });

  describe('API Call Caching', () => {
    it('should cache API call results', async () => {
      const mockApiCall = vi.fn().mockResolvedValue({ data: 'api_result' });
      
      const result1 = await cacheService.cacheApiCall('api_key', mockApiCall, 60000);
      const result2 = await cacheService.cacheApiCall('api_key', mockApiCall, 60000);
      
      expect(mockApiCall).toHaveBeenCalledTimes(1);
      expect(result1).toEqual({ data: 'api_result' });
      expect(result2).toEqual({ data: 'api_result' });
    });

    it('should handle API call failures', async () => {
      const mockApiCall = vi.fn().mockRejectedValue(new Error('API failed'));
      
      await expect(cacheService.cacheApiCall('failing_api', mockApiCall)).rejects.toThrow('API failed');
      
      expect(console.error).toHaveBeenCalledWith('API call failed:', expect.any(Error));
    });

    it('should implement refresh strategy', async () => {
      const mockApiCall = vi.fn()
        .mockResolvedValueOnce({ data: 'first_result' })
        .mockResolvedValueOnce({ data: 'refreshed_result' });
      
      // Initial call
      const result1 = await cacheService.getWithRefresh('refresh_key', mockApiCall, 10000, 0.5);
      expect(result1).toEqual({ data: 'first_result' });
      
      // Fast forward past refresh threshold but not expiration
      vi.advanceTimersByTime(6000); // 60% of TTL
      
      // Should return cached data but trigger background refresh
      const result2 = await cacheService.getWithRefresh('refresh_key', mockApiCall, 10000, 0.5);
      expect(result2).toEqual({ data: 'first_result' });
      
      // Allow background refresh to complete
      await vi.runAllTimersAsync();
      
      // Next call should return refreshed data
      const result3 = cacheService.get('refresh_key');
      expect(result3).toEqual({ data: 'refreshed_result' });
      
      expect(mockApiCall).toHaveBeenCalledTimes(2);
    });

    it('should handle background refresh failures gracefully', async () => {
      const mockApiCall = vi.fn()
        .mockResolvedValueOnce({ data: 'initial_data' })
        .mockRejectedValueOnce(new Error('Refresh failed'));
      
      await cacheService.getWithRefresh('bg_refresh_key', mockApiCall, 10000, 0.1);
      
      // Trigger background refresh
      vi.advanceTimersByTime(2000);
      await cacheService.getWithRefresh('bg_refresh_key', mockApiCall, 10000, 0.1);
      
      await vi.runAllTimersAsync();
      
      expect(console.warn).toHaveBeenCalledWith('Background refresh failed:', expect.any(Error));
      
      // Original data should still be available
      const data = cacheService.get('bg_refresh_key');
      expect(data).toEqual({ data: 'initial_data' });
    });
  });

  describe('Cache Statistics and Monitoring', () => {
    it('should track hit rate correctly', () => {
      cacheService.set('stats_key', 'value');
      
      // 3 hits
      cacheService.get('stats_key');
      cacheService.get('stats_key');
      cacheService.get('stats_key');
      
      // 2 misses
      cacheService.get('non_existent_1');
      cacheService.get('non_existent_2');
      
      const stats = cacheService.getStats();
      
      expect(stats.hits).toBe(3);
      expect(stats.misses).toBe(2);
      expect(stats.hitRate).toBe(60); // 3/(3+2) * 100
      expect(stats.sets).toBe(1);
    });

    it('should handle zero hits and misses for hit rate', () => {
      const stats = cacheService.getStats();
      
      expect(stats.hitRate).toBe(0);
    });

    it('should track cache size and memory usage', () => {
      cacheService.set('memory_test_1', { data: 'test1' });
      cacheService.set('memory_test_2', { data: 'test2' });
      
      const stats = cacheService.getStats();
      
      expect(stats.size).toBe(2);
      expect(stats.maxSize).toBe(cacheService.maxSize);
      expect(stats.memoryUsage).toBeGreaterThan(0);
    });
  });

  describe('Cache Configuration Constants', () => {
    it('should export cache configurations for different data types', () => {
      expect(CacheConfigs.STOCK_QUOTE.ttl).toBe(30 * 1000);
      expect(CacheConfigs.STOCK_QUOTE.persist).toBe(false);
      
      expect(CacheConfigs.STOCK_HISTORY.ttl).toBe(5 * 60 * 1000);
      expect(CacheConfigs.STOCK_HISTORY.persist).toBe(true);
      
      expect(CacheConfigs.COMPANY_INFO.ttl).toBe(24 * 60 * 60 * 1000);
      expect(CacheConfigs.COMPANY_INFO.persist).toBe(true);
      
      expect(CacheConfigs.WATCHLIST.ttl).toBe(Infinity);
      expect(CacheConfigs.WATCHLIST.persist).toBe(true);
    });
  });

  describe('Service Lifecycle Management', () => {
    it('should properly destroy service and cleanup resources', () => {
      const clearIntervalSpy = vi.spyOn(global, 'clearInterval');
      
      cacheService.set('cleanup_test', 'value');
      expect(cacheService.cache.size).toBe(1);
      
      cacheService.destroy();
      
      expect(clearIntervalSpy).toHaveBeenCalled();
      expect(cacheService.cache.size).toBe(0);
    });
  });

  describe('Edge Cases and Error Handling', () => {
    it('should handle null and undefined values correctly', () => {
      cacheService.set('null_value', null);
      cacheService.set('undefined_value', undefined);
      cacheService.set('false_value', false);
      cacheService.set('zero_value', 0);
      cacheService.set('empty_string', '');
      
      expect(cacheService.get('null_value')).toBeNull();
      expect(cacheService.get('undefined_value')).toBeUndefined();
      expect(cacheService.get('false_value')).toBe(false);
      expect(cacheService.get('zero_value')).toBe(0);
      expect(cacheService.get('empty_string')).toBe('');
    });

    it('should handle complex nested objects', () => {
      const complexObject = {
        array: [1, 2, { nested: true }],
        object: { deep: { very: { deep: 'value' } } },
        date: new Date(),
        regexp: /test/g,
        func: function() { return 'test'; }
      };
      
      cacheService.set('complex_key', complexObject);
      const retrieved = cacheService.get('complex_key');
      
      expect(retrieved.array).toEqual(complexObject.array);
      expect(retrieved.object).toEqual(complexObject.object);
    });

    it('should handle very large cache keys', () => {
      const longKey = 'a'.repeat(1000);
      cacheService.set(longKey, 'test_value');
      
      expect(cacheService.get(longKey)).toBe('test_value');
    });

    it('should handle concurrent operations safely', async () => {
      const promises = [];
      
      // Simulate concurrent set operations
      for (let i = 0; i < 100; i++) {
        promises.push(Promise.resolve(cacheService.set(`concurrent_${i}`, `value_${i}`)));
      }
      
      await Promise.all(promises);
      
      expect(cacheService.cache.size).toBe(100);
      
      // Verify all values are correct
      for (let i = 0; i < 100; i++) {
        expect(cacheService.get(`concurrent_${i}`)).toBe(`value_${i}`);
      }
    });
  });
});
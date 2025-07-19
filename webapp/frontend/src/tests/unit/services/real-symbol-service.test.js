/**
 * Real Symbol Service Unit Tests
 * Testing the actual symbolService.js with API integration and caching
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock the API service
vi.mock('../../../services/api', () => ({
  api: {
    get: vi.fn()
  }
}));

// Import the REAL SymbolService
import symbolService from '../../../services/symbolService';
import { api } from '../../../services/api';

describe('🔤 Real Symbol Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Clear the service cache before each test
    symbolService.clearCache();
    
    // Mock console to avoid noise
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Service Initialization', () => {
    it('should initialize with fallback symbols for all categories', () => {
      expect(symbolService.fallbacks).toEqual({
        popular: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ'],
        tech: ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'AMD', 'CRM', 'INTC', 'ORCL'],
        etf: ['SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'GLD', 'TLT'],
        options: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'SPY', 'QQQ'],
        crypto: ['BTC', 'ETH', 'ADA', 'DOT', 'LINK', 'UNI', 'AAVE'],
        all: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'NFLX', 'SPY', 'QQQ', 'IWM', 'DIA']
      });
    });

    it('should initialize with empty cache', () => {
      expect(symbolService.cache.size).toBe(0);
    });

    it('should have cache timeout of 30 minutes', () => {
      expect(symbolService.cacheTimeout).toBe(30 * 60 * 1000);
    });
  });

  describe('Cache Management', () => {
    it('should generate correct cache keys', () => {
      const key1 = symbolService.getCacheKey('popular', { limit: 20 });
      const key2 = symbolService.getCacheKey('tech', { limit: 15, sector: 'Technology' });
      const key3 = symbolService.getCacheKey('popular', { limit: 20 });

      expect(key1).toBe('symbols_popular_{"limit":20}');
      expect(key2).toBe('symbols_tech_{"limit":15,"sector":"Technology"}');
      expect(key1).toBe(key3); // Same params should generate same key
    });

    it('should validate cache entries correctly', () => {
      const validEntry = {
        data: ['AAPL', 'MSFT'],
        timestamp: Date.now() - 1000 // 1 second ago
      };

      const expiredEntry = {
        data: ['AAPL', 'MSFT'],
        timestamp: Date.now() - (31 * 60 * 1000) // 31 minutes ago
      };

      expect(symbolService.isCacheValid(validEntry)).toBe(true);
      expect(symbolService.isCacheValid(expiredEntry)).toBe(false);
      expect(symbolService.isCacheValid(null)).toBe(false);
      expect(symbolService.isCacheValid(undefined)).toBe(false);
    });

    it('should clear cache correctly', () => {
      symbolService.cache.set('test_key', { data: ['AAPL'], timestamp: Date.now() });
      expect(symbolService.cache.size).toBe(1);

      symbolService.clearCache();
      expect(symbolService.cache.size).toBe(0);
    });

    it('should provide accurate cache statistics', () => {
      const now = Date.now();
      
      // Add valid entry
      symbolService.cache.set('valid', {
        data: ['AAPL'],
        timestamp: now - 1000
      });

      // Add expired entry
      symbolService.cache.set('expired', {
        data: ['MSFT'],
        timestamp: now - (31 * 60 * 1000)
      });

      const stats = symbolService.getCacheStats();

      expect(stats.totalEntries).toBe(2);
      expect(stats.validEntries).toBe(1);
      expect(stats.expiredEntries).toBe(1);
      expect(stats.cacheTimeout).toBe(30 * 60 * 1000);
    });
  });

  describe('API Response Extraction', () => {
    it('should extract symbols from stocks array format', () => {
      const response = {
        data: {
          stocks: [
            { symbol: 'AAPL', name: 'Apple Inc.' },
            { symbol: 'MSFT', name: 'Microsoft Corp.' },
            { symbol: 'GOOGL', name: 'Alphabet Inc.' }
          ]
        }
      };

      const symbols = symbolService.extractSymbolsFromResponse(response);
      expect(symbols).toEqual(['AAPL', 'MSFT', 'GOOGL']);
    });

    it('should extract symbols from data array format', () => {
      const response = {
        data: {
          data: [
            { symbol: 'TSLA' },
            { symbol: 'NVDA' },
            { symbol: 'AMD' }
          ]
        }
      };

      const symbols = symbolService.extractSymbolsFromResponse(response);
      expect(symbols).toEqual(['TSLA', 'NVDA', 'AMD']);
    });

    it('should extract symbols from direct array format', () => {
      const response = {
        data: ['AAPL', 'MSFT', 'GOOGL']
      };

      const symbols = symbolService.extractSymbolsFromResponse(response);
      expect(symbols).toEqual(['AAPL', 'MSFT', 'GOOGL']);
    });

    it('should extract symbols from symbols array format', () => {
      const response = {
        data: {
          symbols: ['SPY', 'QQQ', 'IWM', 'DIA']
        }
      };

      const symbols = symbolService.extractSymbolsFromResponse(response);
      expect(symbols).toEqual(['SPY', 'QQQ', 'IWM', 'DIA']);
    });

    it('should filter out invalid symbols', () => {
      const response = {
        data: {
          symbols: [
            'AAPL',      // Valid
            'MSFT',      // Valid
            '',          // Invalid - empty
            'TOOLONG',   // Invalid - too long
            '123',       // Invalid - numbers
            'A@PL',      // Invalid - special chars
            null,        // Invalid - null
            undefined,   // Invalid - undefined
            'GE'         // Valid - short but acceptable
          ]
        }
      };

      const symbols = symbolService.extractSymbolsFromResponse(response);
      expect(symbols).toEqual(['AAPL', 'MSFT', 'GE']);
    });

    it('should handle empty or malformed responses', () => {
      expect(symbolService.extractSymbolsFromResponse({})).toEqual([]);
      expect(symbolService.extractSymbolsFromResponse({ data: null })).toEqual([]);
      expect(symbolService.extractSymbolsFromResponse({ data: {} })).toEqual([]);
      expect(symbolService.extractSymbolsFromResponse(null)).toEqual([]);
    });
  });

  describe('Popular Symbols Fetching', () => {
    it('should fetch popular symbols from API successfully', async () => {
      const mockResponse = {
        data: {
          stocks: [
            { symbol: 'AAPL' },
            { symbol: 'MSFT' },
            { symbol: 'GOOGL' },
            { symbol: 'TSLA' },
            { symbol: 'NVDA' }
          ]
        }
      };

      api.get.mockResolvedValue(mockResponse);

      const symbols = await symbolService.getSymbols('popular', { limit: 5 });

      expect(api.get).toHaveBeenCalledWith('/api/stocks/popular');
      expect(symbols).toEqual(['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']);
    });

    it('should try multiple endpoints for popular symbols', async () => {
      api.get
        .mockRejectedValueOnce(new Error('First endpoint failed'))
        .mockRejectedValueOnce(new Error('Second endpoint failed'))
        .mockResolvedValue({
          data: {
            stocks: [{ symbol: 'AAPL' }, { symbol: 'MSFT' }]
          }
        });

      const symbols = await symbolService.getSymbols('popular', { limit: 10 });

      expect(api.get).toHaveBeenCalledTimes(3);
      expect(symbols).toEqual(['AAPL', 'MSFT']);
    });

    it('should return fallback symbols when all endpoints fail', async () => {
      api.get.mockRejectedValue(new Error('All endpoints failed'));

      const symbols = await symbolService.getSymbols('popular', { limit: 5 });

      expect(symbols).toEqual(['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']);
    });

    it('should use cached popular symbols when available', async () => {
      const cachedSymbols = ['CACHED1', 'CACHED2', 'CACHED3'];
      
      // Manually add to cache
      const cacheKey = symbolService.getCacheKey('popular', { limit: 20 });
      symbolService.cache.set(cacheKey, {
        data: cachedSymbols,
        timestamp: Date.now()
      });

      const symbols = await symbolService.getSymbols('popular');

      expect(api.get).not.toHaveBeenCalled();
      expect(symbols).toEqual(cachedSymbols);
    });
  });

  describe('Tech Symbols Fetching', () => {
    it('should fetch tech symbols and filter for known tech stocks', async () => {
      const mockResponse = {
        data: {
          stocks: [
            { symbol: 'AAPL' },  // Known tech
            { symbol: 'MSFT' },  // Known tech
            { symbol: 'XOM' },   // Not tech
            { symbol: 'GOOGL' }, // Known tech
            { symbol: 'JPM' }    // Not tech
          ]
        }
      };

      api.get.mockResolvedValue(mockResponse);

      const symbols = await symbolService.getSymbols('tech', { limit: 10 });

      expect(symbols).toEqual(['AAPL', 'MSFT', 'GOOGL']);
    });

    it('should return fallback tech symbols when API fails', async () => {
      api.get.mockRejectedValue(new Error('Tech symbols API failed'));

      const symbols = await symbolService.getSymbols('tech', { limit: 5 });

      expect(symbols).toEqual(['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'AMD']);
    });
  });

  describe('ETF Symbols Fetching', () => {
    it('should fetch ETF symbols and filter for known ETFs', async () => {
      const mockResponse = {
        data: {
          stocks: [
            { symbol: 'SPY' },   // Known ETF
            { symbol: 'AAPL' },  // Not ETF
            { symbol: 'QQQ' },   // Known ETF
            { symbol: 'IWM' },   // Known ETF
            { symbol: 'MSFT' }   // Not ETF
          ]
        }
      };

      api.get.mockResolvedValue(mockResponse);

      const symbols = await symbolService.getSymbols('etf', { limit: 10 });

      expect(symbols).toEqual(['SPY', 'QQQ', 'IWM']);
    });

    it('should return fallback ETF symbols when API fails', async () => {
      api.get.mockRejectedValue(new Error('ETF symbols API failed'));

      const symbols = await symbolService.getSymbols('etf', { limit: 4 });

      expect(symbols).toEqual(['SPY', 'QQQ', 'IWM', 'DIA']);
    });
  });

  describe('Options Symbols Fetching', () => {
    it('should fetch options-tradeable symbols', async () => {
      const mockResponse = {
        data: {
          stocks: [
            { symbol: 'AAPL' },
            { symbol: 'MSFT' },
            { symbol: 'TSLA' },
            { symbol: 'SPY' }
          ]
        }
      };

      api.get.mockResolvedValue(mockResponse);

      const symbols = await symbolService.getSymbols('options', { limit: 10 });

      expect(api.get).toHaveBeenCalledWith('/api/stocks?optionable=true&limit=10');
      expect(symbols).toEqual(['AAPL', 'MSFT', 'TSLA', 'SPY']);
    });

    it('should return fallback options symbols when API fails', async () => {
      api.get.mockRejectedValue(new Error('Options symbols API failed'));

      const symbols = await symbolService.getSymbols('options', { limit: 5 });

      expect(symbols).toEqual(['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']);
    });
  });

  describe('All Symbols Fetching with Filters', () => {
    it('should fetch all symbols with sector filter', async () => {
      const mockResponse = {
        data: {
          stocks: [
            { symbol: 'AAPL' },
            { symbol: 'MSFT' },
            { symbol: 'GOOGL' }
          ]
        }
      };

      api.get.mockResolvedValue(mockResponse);

      const symbols = await symbolService.getSymbols('all', {
        limit: 10,
        sector: 'Technology',
        minMarketCap: 1000000000
      });

      expect(api.get).toHaveBeenCalledWith('/api/stocks?limit=10&sector=Technology&min_market_cap=1000000000');
      expect(symbols).toEqual(['AAPL', 'MSFT', 'GOOGL']);
    });

    it('should fetch all symbols with market cap filters', async () => {
      const mockResponse = {
        data: {
          stocks: [
            { symbol: 'AAPL' },
            { symbol: 'MSFT' }
          ]
        }
      };

      api.get.mockResolvedValue(mockResponse);

      const symbols = await symbolService.getSymbols('all', {
        limit: 5,
        minMarketCap: 500000000,
        maxMarketCap: 2000000000000
      });

      expect(api.get).toHaveBeenCalledWith('/api/stocks?limit=5&min_market_cap=500000000&max_market_cap=2000000000000');
      expect(symbols).toEqual(['AAPL', 'MSFT']);
    });
  });

  describe('Convenience Methods', () => {
    beforeEach(() => {
      api.get.mockResolvedValue({
        data: {
          stocks: [
            { symbol: 'AAPL' },
            { symbol: 'MSFT' },
            { symbol: 'GOOGL' },
            { symbol: 'TSLA' },
            { symbol: 'NVDA' }
          ]
        }
      });
    });

    it('should get dashboard symbols with correct limit', async () => {
      const symbols = await symbolService.getDashboardSymbols();
      
      expect(symbols).toHaveLength(5);
      expect(symbols).toEqual(['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']);
    });

    it('should get watchlist symbols with correct limit', async () => {
      const symbols = await symbolService.getWatchlistSymbols();
      
      expect(symbols).toHaveLength(5);
      expect(symbols).toEqual(['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']);
    });

    it('should get options symbols list', async () => {
      const symbols = await symbolService.getOptionsSymbolsList();
      
      expect(symbols).toHaveLength(5);
      expect(symbols).toEqual(['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']);
    });

    it('should get tech stock symbols', async () => {
      api.get.mockResolvedValue({
        data: {
          stocks: [
            { symbol: 'AAPL' },
            { symbol: 'MSFT' },
            { symbol: 'GOOGL' },
            { symbol: 'NVDA' }
          ]
        }
      });

      const symbols = await symbolService.getTechStockSymbols();
      
      expect(symbols).toEqual(['AAPL', 'MSFT', 'GOOGL', 'NVDA']);
    });

    it('should get ETF symbols list', async () => {
      api.get.mockResolvedValue({
        data: {
          stocks: [
            { symbol: 'SPY' },
            { symbol: 'QQQ' },
            { symbol: 'IWM' }
          ]
        }
      });

      const symbols = await symbolService.getETFSymbolsList();
      
      expect(symbols).toEqual(['SPY', 'QQQ', 'IWM']);
    });
  });

  describe('Force Refresh Functionality', () => {
    it('should ignore cache when forceRefresh is true', async () => {
      const cachedSymbols = ['CACHED1', 'CACHED2'];
      const freshSymbols = ['FRESH1', 'FRESH2'];
      
      // Add to cache
      const cacheKey = symbolService.getCacheKey('popular', { limit: 20 });
      symbolService.cache.set(cacheKey, {
        data: cachedSymbols,
        timestamp: Date.now()
      });

      // Mock fresh API response
      api.get.mockResolvedValue({
        data: {
          stocks: freshSymbols.map(symbol => ({ symbol }))
        }
      });

      const symbols = await symbolService.getSymbols('popular', { forceRefresh: true });

      expect(api.get).toHaveBeenCalled();
      expect(symbols).toEqual(freshSymbols);
    });

    it('should update cache after force refresh', async () => {
      const freshSymbols = ['FRESH1', 'FRESH2'];
      
      api.get.mockResolvedValue({
        data: {
          stocks: freshSymbols.map(symbol => ({ symbol }))
        }
      });

      await symbolService.getSymbols('popular', { forceRefresh: true });

      const cacheKey = symbolService.getCacheKey('popular', { limit: 20 });
      const cachedEntry = symbolService.cache.get(cacheKey);
      
      expect(cachedEntry.data).toEqual(freshSymbols);
      expect(cachedEntry.timestamp).toBeCloseTo(Date.now(), -2); // Within 100ms
    });
  });

  describe('Error Handling and Resilience', () => {
    it('should handle network timeouts gracefully', async () => {
      api.get.mockRejectedValue(new Error('Network timeout'));

      const symbols = await symbolService.getSymbols('popular');

      expect(symbols).toEqual(symbolService.fallbacks.popular);
    });

    it('should handle malformed API responses', async () => {
      api.get.mockResolvedValue({
        data: 'invalid response format'
      });

      const symbols = await symbolService.getSymbols('popular');

      expect(symbols).toEqual(symbolService.fallbacks.popular);
    });

    it('should handle API responses with no symbols', async () => {
      api.get.mockResolvedValue({
        data: {
          stocks: []
        }
      });

      const symbols = await symbolService.getSymbols('popular');

      expect(symbols).toEqual(symbolService.fallbacks.popular);
    });

    it('should handle undefined symbol type gracefully', async () => {
      api.get.mockResolvedValue({
        data: {
          stocks: [{ symbol: 'AAPL' }, { symbol: 'MSFT' }]
        }
      });

      const symbols = await symbolService.getSymbols('unknown_type');

      // Should default to popular symbols
      expect(symbols).toEqual(['AAPL', 'MSFT']);
    });
  });

  describe('Performance and Optimization', () => {
    it('should handle large symbol datasets efficiently', async () => {
      const largeDataset = Array.from({ length: 5000 }, (_, i) => ({
        symbol: `STOCK${i.toString().padStart(4, '0')}`
      }));

      api.get.mockResolvedValue({
        data: { stocks: largeDataset }
      });

      const startTime = performance.now();
      
      const symbols = await symbolService.getSymbols('all', { limit: 100 });
      
      const processingTime = performance.now() - startTime;

      expect(processingTime).toBeLessThan(100); // Should process within 100ms
      expect(symbols).toHaveLength(100);
    });

    it('should limit returned symbols to specified limit', async () => {
      const mockSymbols = Array.from({ length: 100 }, (_, i) => ({
        symbol: `STOCK${i}`
      }));

      api.get.mockResolvedValue({
        data: { stocks: mockSymbols }
      });

      const symbols = await symbolService.getSymbols('popular', { limit: 15 });

      expect(symbols).toHaveLength(15);
    });

    it('should handle concurrent requests efficiently', async () => {
      api.get.mockResolvedValue({
        data: {
          stocks: [{ symbol: 'AAPL' }, { symbol: 'MSFT' }]
        }
      });

      const promises = [
        symbolService.getSymbols('popular'),
        symbolService.getSymbols('tech'),
        symbolService.getSymbols('etf'),
        symbolService.getSymbols('options')
      ];

      const results = await Promise.all(promises);

      expect(results).toHaveLength(4);
      results.forEach(symbols => {
        expect(Array.isArray(symbols)).toBe(true);
        expect(symbols.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Cache Expiration and Cleanup', () => {
    it('should not use expired cache entries', async () => {
      const expiredSymbols = ['EXPIRED1', 'EXPIRED2'];
      const freshSymbols = ['FRESH1', 'FRESH2'];
      
      // Add expired entry to cache
      const cacheKey = symbolService.getCacheKey('popular', { limit: 20 });
      symbolService.cache.set(cacheKey, {
        data: expiredSymbols,
        timestamp: Date.now() - (31 * 60 * 1000) // 31 minutes ago
      });

      // Mock fresh API response
      api.get.mockResolvedValue({
        data: {
          stocks: freshSymbols.map(symbol => ({ symbol }))
        }
      });

      const symbols = await symbolService.getSymbols('popular');

      expect(api.get).toHaveBeenCalled();
      expect(symbols).toEqual(freshSymbols);
    });

    it('should track multiple cache entries correctly', () => {
      const now = Date.now();
      
      symbolService.cache.set('key1', { data: [], timestamp: now - 1000 });
      symbolService.cache.set('key2', { data: [], timestamp: now - (31 * 60 * 1000) });
      symbolService.cache.set('key3', { data: [], timestamp: now - 2000 });

      const stats = symbolService.getCacheStats();

      expect(stats.totalEntries).toBe(3);
      expect(stats.validEntries).toBe(2);
      expect(stats.expiredEntries).toBe(1);
    });
  });
});
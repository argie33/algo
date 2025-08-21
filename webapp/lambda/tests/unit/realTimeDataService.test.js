const RealTimeDataService = require('../../utils/realTimeDataService');

// Mock dependencies
jest.mock('../../utils/alpacaService');
jest.mock('../../utils/apiKeyServiceResilient');

const AlpacaService = require('../../utils/alpacaService');
const apiKeyService = require('../../utils/apiKeyServiceResilient');

describe('RealTimeDataService', () => {
  let realTimeService;
  let mockAlpacaService;

  beforeEach(() => {
    jest.clearAllMocks();
    
    mockAlpacaService = {
      getBars: jest.fn(),
      getLatestQuote: jest.fn(),
      getMarketStatus: jest.fn()
    };

    AlpacaService.mockImplementation(() => mockAlpacaService);
    apiKeyService.getApiKeys = jest.fn();
    
    realTimeService = new RealTimeDataService();
    
    // Mock Date.now for consistent testing
    jest.spyOn(Date, 'now').mockReturnValue(1640995200000); // 2022-01-01 00:00:00
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('constructor', () => {
    test('should initialize with default settings', () => {
      expect(realTimeService.cacheTimeout).toBe(30000);
      expect(realTimeService.rateLimitDelay).toBe(1000);
      expect(realTimeService.watchedSymbols.has('AAPL')).toBe(true);
      expect(realTimeService.indexSymbols.has('SPY')).toBe(true);
      expect(realTimeService.cache).toBeInstanceOf(Map);
    });

    test('should initialize with common symbols', () => {
      const expectedSymbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META'];
      expectedSymbols.forEach(symbol => {
        expect(realTimeService.watchedSymbols.has(symbol)).toBe(true);
      });
    });

    test('should initialize with market indices', () => {
      const expectedIndices = ['SPY', 'QQQ', 'DIA', 'IWM', 'VIX'];
      expectedIndices.forEach(symbol => {
        expect(realTimeService.indexSymbols.has(symbol)).toBe(true);
      });
    });
  });

  describe('rateLimit', () => {
    test('should not delay if enough time has passed', async () => {
      realTimeService.lastRequestTime = Date.now() - 2000; // 2 seconds ago
      
      const start = Date.now();
      await realTimeService.rateLimit();
      const end = Date.now();
      
      expect(end - start).toBeLessThan(100); // Should be immediate
      expect(realTimeService.lastRequestTime).toBe(Date.now());
    });

    test('should delay if not enough time has passed', async () => {
      realTimeService.lastRequestTime = Date.now() - 500; // 0.5 seconds ago
      
      const start = Date.now();
      await realTimeService.rateLimit();
      const end = Date.now();
      
      expect(end - start).toBeGreaterThanOrEqual(500);
    });

    test('should update last request time', async () => {
      const initialTime = realTimeService.lastRequestTime;
      await realTimeService.rateLimit();
      
      expect(realTimeService.lastRequestTime).toBeGreaterThan(initialTime);
    });
  });

  describe('getCachedOrFetch', () => {
    test('should return cached data if not expired', async () => {
      const cacheKey = 'test-key';
      const cachedData = { value: 'cached', timestamp: Date.now() };
      realTimeService.cache.set(cacheKey, cachedData);

      const fetchFunction = jest.fn();
      
      const result = await realTimeService.getCachedOrFetch(cacheKey, fetchFunction);
      
      expect(result).toBe('cached');
      expect(fetchFunction).not.toHaveBeenCalled();
    });

    test('should fetch fresh data if cache expired', async () => {
      const cacheKey = 'test-key';
      const expiredData = { value: 'cached', timestamp: Date.now() - 60000 }; // 1 minute ago
      realTimeService.cache.set(cacheKey, expiredData);

      const freshData = 'fresh';
      const fetchFunction = jest.fn().mockResolvedValue(freshData);
      
      const result = await realTimeService.getCachedOrFetch(cacheKey, fetchFunction);
      
      expect(result).toBe('fresh');
      expect(fetchFunction).toHaveBeenCalledTimes(1);
    });

    test('should fetch fresh data if no cache exists', async () => {
      const cacheKey = 'new-key';
      const freshData = 'fresh';
      const fetchFunction = jest.fn().mockResolvedValue(freshData);
      
      const result = await realTimeService.getCachedOrFetch(cacheKey, fetchFunction);
      
      expect(result).toBe('fresh');
      expect(fetchFunction).toHaveBeenCalledTimes(1);
    });

    test('should cache the fetched data', async () => {
      const cacheKey = 'test-key';
      const freshData = 'fresh';
      const fetchFunction = jest.fn().mockResolvedValue(freshData);
      
      await realTimeService.getCachedOrFetch(cacheKey, fetchFunction);
      
      const cachedEntry = realTimeService.cache.get(cacheKey);
      expect(cachedEntry.value).toBe('fresh');
      expect(cachedEntry.timestamp).toBe(Date.now());
    });

    test('should handle fetch function errors', async () => {
      const cacheKey = 'error-key';
      const error = new Error('Fetch failed');
      const fetchFunction = jest.fn().mockRejectedValue(error);
      
      await expect(realTimeService.getCachedOrFetch(cacheKey, fetchFunction)).rejects.toThrow('Fetch failed');
    });
  });

  describe('getQuote', () => {
    const mockQuoteData = {
      symbol: 'AAPL',
      price: 150.00,
      bid: 149.95,
      ask: 150.05,
      timestamp: Date.now()
    };

    test('should get quote for valid symbol', async () => {
      apiKeyService.getApiKeys.mockResolvedValue({
        alpaca_key: 'test-key',
        alpaca_secret: 'test-secret'
      });
      mockAlpacaService.getLatestQuote.mockResolvedValue(mockQuoteData);

      const result = await realTimeService.getQuote('AAPL');

      expect(result).toEqual(mockQuoteData);
      expect(mockAlpacaService.getLatestQuote).toHaveBeenCalledWith('AAPL');
    });

    test('should handle API key service errors', async () => {
      apiKeyService.getApiKeys.mockRejectedValue(new Error('No API keys'));

      await expect(realTimeService.getQuote('AAPL')).rejects.toThrow('No API keys');
    });

    test('should handle invalid symbols', async () => {
      await expect(realTimeService.getQuote()).rejects.toThrow();
      await expect(realTimeService.getQuote('')).rejects.toThrow();
      await expect(realTimeService.getQuote(null)).rejects.toThrow();
    });

    test('should validate symbol format', async () => {
      await expect(realTimeService.getQuote('invalid-symbol')).rejects.toThrow();
      await expect(realTimeService.getQuote('123')).rejects.toThrow();
      await expect(realTimeService.getQuote('TOOLONGSYMBOL')).rejects.toThrow();
    });
  });

  describe('getMarketIndices', () => {
    const mockIndicesData = [
      { symbol: 'SPY', price: 450.00, change: 2.50, changePercent: 0.56 },
      { symbol: 'QQQ', price: 380.00, change: -1.20, changePercent: -0.31 },
      { symbol: 'DIA', price: 350.00, change: 0.80, changePercent: 0.23 }
    ];

    test('should get market indices data', async () => {
      apiKeyService.getApiKeys.mockResolvedValue({
        alpaca_key: 'test-key',
        alpaca_secret: 'test-secret'
      });
      
      mockAlpacaService.getBars.mockResolvedValue(mockIndicesData);

      const result = await realTimeService.getMarketIndices();

      expect(result).toEqual(mockIndicesData);
      expect(mockAlpacaService.getBars).toHaveBeenCalled();
    });

    test('should use caching for market indices', async () => {
      const cacheKey = 'market_indices';
      realTimeService.cache.set(cacheKey, {
        value: mockIndicesData,
        timestamp: Date.now()
      });

      const result = await realTimeService.getMarketIndices();

      expect(result).toEqual(mockIndicesData);
      expect(apiKeyService.getApiKeys).not.toHaveBeenCalled();
    });
  });

  describe('getTopMovers', () => {
    const mockMoversData = {
      gainers: [
        { symbol: 'STOCK1', change: 5.25, changePercent: 10.5 },
        { symbol: 'STOCK2', change: 3.80, changePercent: 8.2 }
      ],
      losers: [
        { symbol: 'STOCK3', change: -4.20, changePercent: -12.1 },
        { symbol: 'STOCK4', change: -2.15, changePercent: -6.8 }
      ]
    };

    test('should get top movers data', async () => {
      apiKeyService.getApiKeys.mockResolvedValue({
        alpaca_key: 'test-key',
        alpaca_secret: 'test-secret'
      });
      
      mockAlpacaService.getBars.mockResolvedValue(mockMoversData);

      const result = await realTimeService.getTopMovers();

      expect(result).toEqual(mockMoversData);
    });

    test('should handle empty movers data', async () => {
      apiKeyService.getApiKeys.mockResolvedValue({
        alpaca_key: 'test-key',
        alpaca_secret: 'test-secret'
      });
      
      mockAlpacaService.getBars.mockResolvedValue({ gainers: [], losers: [] });

      const result = await realTimeService.getTopMovers();

      expect(result.gainers).toEqual([]);
      expect(result.losers).toEqual([]);
    });
  });

  describe('addWatchedSymbol', () => {
    test('should add symbol to watched list', () => {
      realTimeService.addWatchedSymbol('NFLX');
      
      expect(realTimeService.watchedSymbols.has('NFLX')).toBe(true);
    });

    test('should handle duplicate symbols', () => {
      const initialSize = realTimeService.watchedSymbols.size;
      
      realTimeService.addWatchedSymbol('AAPL'); // Already exists
      
      expect(realTimeService.watchedSymbols.size).toBe(initialSize);
    });

    test('should validate symbol format before adding', () => {
      expect(() => realTimeService.addWatchedSymbol('')).toThrow();
      expect(() => realTimeService.addWatchedSymbol(null)).toThrow();
      expect(() => realTimeService.addWatchedSymbol('123')).toThrow();
    });
  });

  describe('clearCache', () => {
    test('should clear all cached data', () => {
      realTimeService.cache.set('key1', 'value1');
      realTimeService.cache.set('key2', 'value2');
      
      realTimeService.clearCache();
      
      expect(realTimeService.cache.size).toBe(0);
    });

    test('should reset market status cache', () => {
      realTimeService.marketStatus = 'open';
      realTimeService.marketStatusUpdatedAt = Date.now();
      
      realTimeService.clearCache();
      
      expect(realTimeService.marketStatus).toBe(null);
      expect(realTimeService.marketStatusUpdatedAt).toBe(0);
    });
  });
});
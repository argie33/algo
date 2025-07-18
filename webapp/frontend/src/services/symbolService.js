// Symbol Service - Centralized symbol management from database
// Replaces hardcoded symbol arrays throughout the application

import { api } from './api';

class SymbolService {
  constructor() {
    this.cache = new Map();
    this.cacheTimeout = 30 * 60 * 1000; // 30 minutes
    
    // Fallback symbols for different use cases
    this.fallbacks = {
      popular: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ'],
      tech: ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'AMD', 'CRM', 'INTC', 'ORCL'],
      etf: ['SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'GLD', 'TLT'],
      options: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'SPY', 'QQQ'],
      crypto: ['BTC', 'ETH', 'ADA', 'DOT', 'LINK', 'UNI', 'AAVE'],
      all: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'NFLX', 'SPY', 'QQQ', 'IWM', 'DIA']
    };
  }

  // Get cache key for different symbol types
  getCacheKey(type = 'popular', filters = {}) {
    const key = `symbols_${type}_${JSON.stringify(filters)}`;
    return key;
  }

  // Check if cache is valid
  isCacheValid(cacheEntry) {
    if (!cacheEntry) return false;
    return Date.now() - cacheEntry.timestamp < this.cacheTimeout;
  }

  // Get symbols from cache or API
  async getSymbols(type = 'popular', options = {}) {
    const {
      limit = 20,
      sector = null,
      minMarketCap = null,
      maxMarketCap = null,
      forceRefresh = false
    } = options;

    const cacheKey = this.getCacheKey(type, { limit, sector, minMarketCap, maxMarketCap });
    
    // Return cached data if valid and not forcing refresh
    if (!forceRefresh && this.isCacheValid(this.cache.get(cacheKey))) {
      console.log(`📦 [SymbolService] Returning cached symbols for ${type}`);
      return this.cache.get(cacheKey).data;
    }

    try {
      console.log(`🔤 [SymbolService] Fetching ${type} symbols from API...`);
      
      let symbols = [];
      
      switch (type) {
        case 'popular':
          symbols = await this.getPopularSymbols(limit, options);
          break;
        case 'tech':
          symbols = await this.getTechSymbols(limit, options);
          break;
        case 'etf':
          symbols = await this.getETFSymbols(limit, options);
          break;
        case 'options':
          symbols = await this.getOptionsSymbols(limit, options);
          break;
        case 'all':
          symbols = await this.getAllSymbols(limit, options);
          break;
        default:
          symbols = await this.getPopularSymbols(limit, options);
      }

      // Cache the result
      this.cache.set(cacheKey, {
        data: symbols,
        timestamp: Date.now()
      });

      console.log(`🔤 [SymbolService] Retrieved ${symbols.length} ${type} symbols`);
      return symbols;

    } catch (error) {
      console.error(`❌ [SymbolService] Failed to fetch ${type} symbols:`, error);
      
      // Return fallback symbols for the requested type
      const fallbackSymbols = this.fallbacks[type] || this.fallbacks.popular;
      console.log(`🔤 [SymbolService] Using fallback symbols for ${type}:`, fallbackSymbols);
      return fallbackSymbols;
    }
  }

  // Get popular symbols from database
  async getPopularSymbols(limit = 20, options = {}) {
    const endpoints = [
      '/api/stocks/popular',
      '/api/stocks?popular=true',
      '/stocks/popular',
      `/stocks?limit=${limit}&popular=true`,
      `/api/stocks?limit=${limit}`
    ];

    return await this.tryEndpoints(endpoints, limit);
  }

  // Get tech sector symbols
  async getTechSymbols(limit = 20, options = {}) {
    const endpoints = [
      `/api/stocks?sector=Technology&limit=${limit}`,
      `/stocks?sector=Technology&limit=${limit}`,
      `/api/stocks?limit=${limit * 2}` // Get more and filter client-side
    ];

    const symbols = await this.tryEndpoints(endpoints, limit);
    
    // If we got generic symbols, prefer known tech symbols
    if (symbols.length > 0) {
      const techSymbols = symbols.filter(symbol => 
        this.fallbacks.tech.includes(symbol) || 
        symbol.match(/^(AAPL|MSFT|GOOGL|NVDA|AMD|CRM|INTC|ORCL|META|NFLX)$/i)
      );
      return techSymbols.length > 0 ? techSymbols.slice(0, limit) : symbols.slice(0, limit);
    }
    
    return this.fallbacks.tech.slice(0, limit);
  }

  // Get ETF symbols
  async getETFSymbols(limit = 20, options = {}) {
    const endpoints = [
      `/api/stocks?type=ETF&limit=${limit}`,
      `/stocks?type=ETF&limit=${limit}`,
      `/api/stocks?symbol=SPY,QQQ,IWM,DIA,VTI,GLD,TLT`
    ];

    const symbols = await this.tryEndpoints(endpoints, limit);
    
    // Filter for known ETFs if we got generic results
    if (symbols.length > 0) {
      const etfSymbols = symbols.filter(symbol => 
        symbol.match(/^(SPY|QQQ|IWM|DIA|VTI|GLD|TLT|EWJ|FXI|VEA|VWO|XLF|XLK|XLE)$/i)
      );
      return etfSymbols.length > 0 ? etfSymbols.slice(0, limit) : symbols.slice(0, limit);
    }
    
    return this.fallbacks.etf.slice(0, limit);
  }

  // Get options-tradeable symbols
  async getOptionsSymbols(limit = 20, options = {}) {
    const endpoints = [
      `/api/stocks?optionable=true&limit=${limit}`,
      `/stocks?optionable=true&limit=${limit}`,
      `/api/stocks?liquid=true&limit=${limit}`
    ];

    return await this.tryEndpoints(endpoints, limit, 'options');
  }

  // Get all symbols with optional filters
  async getAllSymbols(limit = 50, options = {}) {
    const { sector, minMarketCap, maxMarketCap } = options;
    
    let queryParams = new URLSearchParams();
    queryParams.append('limit', limit.toString());
    
    if (sector) queryParams.append('sector', sector);
    if (minMarketCap) queryParams.append('min_market_cap', minMarketCap);
    if (maxMarketCap) queryParams.append('max_market_cap', maxMarketCap);

    const endpoints = [
      `/api/stocks?${queryParams.toString()}`,
      `/stocks?${queryParams.toString()}`,
      `/api/stocks?limit=${limit}`
    ];

    return await this.tryEndpoints(endpoints, limit, 'all');
  }

  // Try multiple endpoints until one succeeds
  async tryEndpoints(endpoints, limit, fallbackType = 'popular') {
    let lastError = null;

    for (const endpoint of endpoints) {
      try {
        console.log(`🔤 [SymbolService] Trying endpoint: ${endpoint}`);
        const response = await api.get(endpoint);
        
        // Extract symbols from various response formats
        let symbols = this.extractSymbolsFromResponse(response);
        
        if (symbols.length > 0) {
          console.log(`🔤 [SymbolService] SUCCESS with endpoint: ${endpoint} (${symbols.length} symbols)`);
          return symbols.slice(0, limit);
        }
        
      } catch (error) {
        console.log(`🔤 [SymbolService] FAILED endpoint: ${endpoint}`, error.message);
        lastError = error;
        continue;
      }
    }

    console.error('🔤 [SymbolService] All endpoints failed:', lastError);
    return this.fallbacks[fallbackType] || this.fallbacks.popular;
  }

  // Extract symbols from API response in various formats
  extractSymbolsFromResponse(response) {
    let symbols = [];

    if (response.data) {
      // Handle different response structures
      if (Array.isArray(response.data.stocks)) {
        symbols = response.data.stocks.map(stock => stock.symbol || stock).filter(Boolean);
      } else if (Array.isArray(response.data.data)) {
        symbols = response.data.data.map(stock => stock.symbol || stock).filter(Boolean);
      } else if (Array.isArray(response.data)) {
        symbols = response.data.map(stock => stock.symbol || stock).filter(Boolean);
      } else if (response.data.symbols && Array.isArray(response.data.symbols)) {
        symbols = response.data.symbols.filter(Boolean);
      }
    }

    // Ensure we have valid symbols
    symbols = symbols.filter(symbol => 
      typeof symbol === 'string' && 
      symbol.length >= 1 && 
      symbol.length <= 5 &&
      /^[A-Z]+$/i.test(symbol)
    );

    return symbols;
  }

  // Get symbols for specific use cases
  async getDashboardSymbols() {
    return await this.getSymbols('popular', { limit: 10 });
  }

  async getWatchlistSymbols() {
    return await this.getSymbols('popular', { limit: 20 });
  }

  async getOptionsSymbolsList() {
    return await this.getSymbols('options', { limit: 20 });
  }

  async getTechStockSymbols() {
    return await this.getSymbols('tech', { limit: 15 });
  }

  async getETFSymbolsList() {
    return await this.getSymbols('etf', { limit: 10 });
  }

  // Clear cache
  clearCache() {
    this.cache.clear();
    console.log('🔤 [SymbolService] Cache cleared');
  }

  // Get cache stats
  getCacheStats() {
    const now = Date.now();
    let validEntries = 0;
    let expiredEntries = 0;

    for (const [key, entry] of this.cache.entries()) {
      if (now - entry.timestamp < this.cacheTimeout) {
        validEntries++;
      } else {
        expiredEntries++;
      }
    }

    return {
      totalEntries: this.cache.size,
      validEntries,
      expiredEntries,
      cacheTimeout: this.cacheTimeout
    };
  }
}

// Export singleton instance
export const symbolService = new SymbolService();
export default symbolService;
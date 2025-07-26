/**
 * Enhanced Crypto Data Service
 * 
 * Comprehensive cryptocurrency data service with multi-provider support,
 * intelligent fallbacks, real-time data, and production-grade error handling
 */

const axios = require('axios');
const { query } = require('../utils/database');
const { getTimeout } = require('../utils/timeoutManager');

class EnhancedCryptoDataService {
  constructor() {
    this.providers = {
      coingecko: {
        baseUrl: 'https://api.coingecko.com/api/v3',
        rateLimit: 50, // requests per minute
        priority: 1,
        endpoints: {
          simple_price: '/simple/price',
          coins_markets: '/coins/markets',
          global: '/global',
          fear_greed: '/simple/supported_vs_currencies',
          historical: '/coins/{id}/market_chart'
        }
      },
      coinbase: {
        baseUrl: 'https://api.pro.coinbase.com',
        rateLimit: 10,
        priority: 2,
        endpoints: {
          ticker: '/products/{symbol}/ticker',
          candles: '/products/{symbol}/candles',
          stats: '/products/{symbol}/stats'
        }
      },
      binance: {
        baseUrl: 'https://api.binance.com/api/v3',
        rateLimit: 1200,
        priority: 3,
        endpoints: {
          ticker: '/ticker/24hr',
          klines: '/klines',
          trades: '/trades'
        }
      }
    };

    this.cache = new Map();
    this.cacheTimeout = 30000; // 30 seconds
    this.fallbackChain = ['coingecko', 'coinbase', 'binance'];
    this.requestCounts = new Map();
    this.lastReset = Date.now();
    
    console.log('🚀 Enhanced Crypto Data Service initialized');
  }

  /**
   * Get live cryptocurrency market data with intelligent fallbacks
   */
  async getMarketData(symbols = [], vs_currency = 'usd', options = {}) {
    const cacheKey = `market_${symbols.join(',')}_${vs_currency}`;
    
    // Check cache first
    const cached = this.getFromCache(cacheKey);
    if (cached && !options.forceRefresh) {
      console.log('📦 Returning cached market data');
      return { success: true, data: cached, source: 'cache' };
    }

    // Try providers in priority order
    for (const providerName of this.fallbackChain) {
      try {
        console.log(`🔄 Attempting ${providerName} for market data`);
        
        if (!this.canMakeRequest(providerName)) {
          console.log(`⏳ Rate limit reached for ${providerName}, trying next provider`);
          continue;
        }

        const data = await this.fetchMarketDataFromProvider(providerName, symbols, vs_currency);
        
        // Cache successful response
        this.setCache(cacheKey, data);
        this.recordRequest(providerName);
        
        console.log(`✅ Market data fetched successfully from ${providerName}`);
        return { 
          success: true, 
          data, 
          source: providerName,
          timestamp: new Date().toISOString()
        };

      } catch (error) {
        console.error(`❌ ${providerName} failed:`, error.message);
        
        // Continue to next provider
        if (providerName === this.fallbackChain[this.fallbackChain.length - 1]) {
          // Last provider failed, return cached data if available
          const staleData = this.getFromCache(cacheKey, true);
          if (staleData) {
            return {
              success: true,
              data: staleData,
              source: 'stale_cache',
              warning: 'Using cached data due to provider unavailability'
            };
          }
          
          throw new Error('All crypto data providers unavailable');
        }
      }
    }
  }

  /**
   * Get real-time price data for specific symbols
   */
  async getRealTimePrices(symbols, vs_currency = 'usd') {
    try {
      // Primary: CoinGecko simple price endpoint
      const response = await this.makeRequest('coingecko', '/simple/price', {
        ids: symbols.join(','),
        vs_currencies: vs_currency,
        include_24hr_change: true,
        include_24hr_vol: true,
        include_last_updated_at: true
      });

      const formattedData = Object.entries(response).map(([id, data]) => ({
        id,
        symbol: id.toUpperCase(),
        current_price: data[vs_currency],
        price_change_24h: data[`${vs_currency}_24h_change`],
        total_volume: data[`${vs_currency}_24h_vol`],
        last_updated: new Date(data.last_updated_at * 1000).toISOString()
      }));

      return {
        success: true,
        data: formattedData,
        source: 'coingecko',
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('Real-time prices fetch failed:', error);
      throw new CryptoDataError('REALTIME_PRICES_FAILED', error.message);
    }
  }

  /**
   * Get historical price data for charts
   */
  async getHistoricalData(symbol, days = 1, interval = 'hourly') {
    const cacheKey = `historical_${symbol}_${days}_${interval}`;
    
    try {
      // Check cache for historical data (longer cache time)
      const cached = this.getFromCache(cacheKey, false, 300000); // 5 minutes cache
      if (cached) {
        return { success: true, data: cached, source: 'cache' };
      }

      // CoinGecko historical data
      const response = await this.makeRequest('coingecko', `/coins/${symbol}/market_chart`, {
        vs_currency: 'usd',
        days: days,
        interval: interval
      });

      const formatChartData = (prices) => {
        return prices.map(([timestamp, price]) => ({
          timestamp: new Date(timestamp).toISOString(),
          price: price,
          time: new Date(timestamp).getTime()
        }));
      };

      const chartData = {
        prices: formatChartData(response.prices || []),
        market_caps: formatChartData(response.market_caps || []),
        total_volumes: formatChartData(response.total_volumes || [])
      };

      this.setCache(cacheKey, chartData, 300000);
      
      return {
        success: true,
        data: chartData,
        source: 'coingecko',
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('Historical data fetch failed:', error);
      throw new CryptoDataError('HISTORICAL_DATA_FAILED', error.message);
    }
  }

  /**
   * Get comprehensive market overview
   */
  async getMarketOverview() {
    try {
      const [globalData, topCoins, fearGreed] = await Promise.allSettled([
        this.getGlobalMarketData(),
        this.getTopCryptocurrencies(50),
        this.getFearGreedIndex()
      ]);

      const overview = {
        global: globalData.status === 'fulfilled' ? globalData.value : null,
        top_cryptocurrencies: topCoins.status === 'fulfilled' ? topCoins.value : [],
        fear_greed_index: fearGreed.status === 'fulfilled' ? fearGreed.value : null,
        timestamp: new Date().toISOString()
      };

      // Add market sentiment analysis
      overview.market_sentiment = this.analyzeMarketSentiment(overview);
      
      return {
        success: true,
        data: overview,
        warnings: this.getProviderWarnings([globalData, topCoins, fearGreed])
      };

    } catch (error) {
      console.error('Market overview fetch failed:', error);
      throw new CryptoDataError('MARKET_OVERVIEW_FAILED', error.message);
    }
  }

  /**
   * Get Fear and Greed Index from multiple sources
   */
  async getFearGreedIndex() {
    try {
      // Try Alternative.me API first
      const response = await axios.get('https://api.alternative.me/fng/', {
        timeout: getTimeout('market_data', 'quick')
      });

      if (response.data && response.data.data && response.data.data[0]) {
        const fngData = response.data.data[0];
        return {
          value: parseInt(fngData.value),
          value_classification: fngData.value_classification,
          timestamp: fngData.timestamp
        };
      }

      throw new Error('Invalid Fear and Greed response');

    } catch (error) {
      console.error('Fear and Greed Index fetch failed:', error);
      
      // Fallback to calculated sentiment from market data
      return this.calculateFallbackSentiment();
    }
  }

  /**
   * Get global cryptocurrency market statistics
   */
  async getGlobalMarketData() {
    try {
      const response = await this.makeRequest('coingecko', '/global');
      
      if (response.data) {
        return {
          total_market_cap: response.data.total_market_cap?.usd || 0,
          total_volume_24h: response.data.total_volume?.usd || 0,
          btc_dominance: response.data.market_cap_percentage?.btc || 0,
          eth_dominance: response.data.market_cap_percentage?.eth || 0,
          active_cryptocurrencies: response.data.active_cryptocurrencies || 0,
          markets: response.data.markets || 0,
          market_cap_change_24h_percentage: response.data.market_cap_change_percentage_24h_usd || 0
        };
      }

      throw new Error('Invalid global data response');

    } catch (error) {
      console.error('Global market data fetch failed:', error);
      throw new CryptoDataError('GLOBAL_DATA_FAILED', error.message);
    }
  }

  /**
   * Get top cryptocurrencies by market cap
   */
  async getTopCryptocurrencies(limit = 50, vs_currency = 'usd') {
    try {
      const response = await this.makeRequest('coingecko', '/coins/markets', {
        vs_currency: vs_currency,
        order: 'market_cap_desc',
        per_page: limit,
        page: 1,
        sparkline: false,
        price_change_percentage: '1h,24h,7d'
      });

      if (Array.isArray(response)) {
        return response.map(coin => ({
          id: coin.id,
          symbol: coin.symbol.toUpperCase(),
          name: coin.name,
          image: coin.image,
          current_price: coin.current_price,
          market_cap: coin.market_cap,
          market_cap_rank: coin.market_cap_rank,
          fully_diluted_valuation: coin.fully_diluted_valuation,
          total_volume: coin.total_volume,
          high_24h: coin.high_24h,
          low_24h: coin.low_24h,
          price_change_24h: coin.price_change_24h,
          price_change_percentage_24h: coin.price_change_percentage_24h,
          price_change_percentage_1h_in_currency: coin.price_change_percentage_1h_in_currency,
          price_change_percentage_7d_in_currency: coin.price_change_percentage_7d_in_currency,
          circulating_supply: coin.circulating_supply,
          total_supply: coin.total_supply,
          max_supply: coin.max_supply,
          ath: coin.ath,
          ath_change_percentage: coin.ath_change_percentage,
          atl: coin.atl,
          atl_change_percentage: coin.atl_change_percentage,
          last_updated: coin.last_updated
        }));
      }

      throw new Error('Invalid market data response');

    } catch (error) {
      console.error('Top cryptocurrencies fetch failed:', error);
      throw new CryptoDataError('TOP_CRYPTO_FAILED', error.message);
    }
  }

  /**
   * Provider-specific data fetching
   */
  async fetchMarketDataFromProvider(providerName, symbols, vs_currency) {
    switch (providerName) {
      case 'coingecko':
        return await this.fetchCoinGeckoData(symbols, vs_currency);
      case 'coinbase':
        return await this.fetchCoinbaseData(symbols, vs_currency);
      case 'binance':
        return await this.fetchBinanceData(symbols, vs_currency);
      default:
        throw new Error(`Unknown provider: ${providerName}`);
    }
  }

  async fetchCoinGeckoData(symbols, vs_currency) {
    const response = await this.makeRequest('coingecko', '/coins/markets', {
      vs_currency: vs_currency,
      ids: symbols.join(','),
      order: 'market_cap_desc',
      per_page: symbols.length,
      page: 1,
      sparkline: false,
      price_change_percentage: '1h,24h,7d'
    });

    return response;
  }

  async fetchCoinbaseData(symbols, vs_currency) {
    // Coinbase Pro API implementation
    const results = [];
    
    for (const symbol of symbols) {
      try {
        const ticker = await this.makeRequest('coinbase', `/products/${symbol.toUpperCase()}-${vs_currency.toUpperCase()}/ticker`);
        const stats = await this.makeRequest('coinbase', `/products/${symbol.toUpperCase()}-${vs_currency.toUpperCase()}/stats`);
        
        results.push({
          id: symbol,
          symbol: symbol.toUpperCase(),
          current_price: parseFloat(ticker.price),
          total_volume: parseFloat(stats.volume),
          price_change_24h: parseFloat(ticker.price) - parseFloat(stats.open),
          high_24h: parseFloat(stats.high),
          low_24h: parseFloat(stats.low)
        });
      } catch (error) {
        console.error(`Coinbase data failed for ${symbol}:`, error.message);
      }
    }
    
    return results;
  }

  async fetchBinanceData(symbols, vs_currency) {
    // Binance API implementation
    const response = await this.makeRequest('binance', '/ticker/24hr');
    
    return response
      .filter(ticker => symbols.some(symbol => 
        ticker.symbol.toLowerCase().includes(symbol.toLowerCase())
      ))
      .map(ticker => ({
        id: ticker.symbol.toLowerCase(),
        symbol: ticker.symbol,
        current_price: parseFloat(ticker.lastPrice),
        price_change_24h: parseFloat(ticker.priceChange),
        price_change_percentage_24h: parseFloat(ticker.priceChangePercent),
        high_24h: parseFloat(ticker.highPrice),
        low_24h: parseFloat(ticker.lowPrice),
        total_volume: parseFloat(ticker.volume)
      }));
  }

  /**
   * Make HTTP request to provider with error handling
   */
  async makeRequest(providerName, endpoint, params = {}) {
    const provider = this.providers[providerName];
    if (!provider) {
      throw new Error(`Unknown provider: ${providerName}`);
    }

    const url = `${provider.baseUrl}${endpoint}`;
    const config = {
      method: 'GET',
      url,
      params,
      timeout: getTimeout('market_data', 'realtime'),
      headers: {
        'User-Agent': 'AlgoTradingPlatform/1.0',
        'Accept': 'application/json'
      }
    };

    try {
      const response = await axios(config);
      return response.data;
    } catch (error) {
      if (error.response) {
        throw new CryptoDataError(
          'API_ERROR',
          `${providerName} API error: ${error.response.status} - ${error.response.statusText}`,
          { 
            provider: providerName,
            status: error.response.status,
            endpoint 
          }
        );
      } else if (error.code === 'ENOTFOUND' || error.code === 'ECONNREFUSED') {
        throw new CryptoDataError(
          'NETWORK_ERROR',
          `Network error connecting to ${providerName}`,
          { provider: providerName }
        );
      } else if (error.code === 'ETIMEDOUT') {
        throw new CryptoDataError(
          'TIMEOUT_ERROR',
          `Request timeout for ${providerName}`,
          { provider: providerName }
        );
      } else {
        throw new CryptoDataError(
          'REQUEST_FAILED',
          error.message,
          { provider: providerName }
        );
      }
    }
  }

  /**
   * Rate limiting management
   */
  canMakeRequest(providerName) {
    const now = Date.now();
    
    // Reset counters every minute
    if (now - this.lastReset > 60000) {
      this.requestCounts.clear();
      this.lastReset = now;
    }

    const provider = this.providers[providerName];
    const currentCount = this.requestCounts.get(providerName) || 0;
    
    return currentCount < provider.rateLimit;
  }

  recordRequest(providerName) {
    const currentCount = this.requestCounts.get(providerName) || 0;
    this.requestCounts.set(providerName, currentCount + 1);
  }

  /**
   * Cache management
   */
  getFromCache(key, allowStale = false, customTimeout = null) {
    const cached = this.cache.get(key);
    if (!cached) return null;

    const timeout = customTimeout || this.cacheTimeout;
    const isStale = Date.now() - cached.timestamp > timeout;
    
    if (isStale && !allowStale) return null;
    
    return cached.data;
  }

  setCache(key, data, customTimeout = null) {
    this.cache.set(key, {
      data,
      timestamp: Date.now()
    });

    // Clean old cache entries
    if (this.cache.size > 100) {
      const oldestKey = this.cache.keys().next().value;
      this.cache.delete(oldestKey);
    }
  }

  /**
   * Market sentiment analysis
   */
  analyzeMarketSentiment(overview) {
    const sentiment = {
      overall: 'neutral',
      confidence: 0.5,
      indicators: {}
    };

    if (overview.fear_greed_index) {
      const fng = overview.fear_greed_index.value;
      sentiment.indicators.fear_greed = {
        value: fng,
        signal: fng > 75 ? 'extreme_greed' : fng > 55 ? 'greed' : fng > 45 ? 'neutral' : fng > 25 ? 'fear' : 'extreme_fear'
      };
    }

    if (overview.global) {
      const marketCapChange = overview.global.market_cap_change_24h_percentage;
      sentiment.indicators.market_cap_trend = {
        value: marketCapChange,
        signal: marketCapChange > 5 ? 'very_bullish' : marketCapChange > 2 ? 'bullish' : marketCapChange > -2 ? 'neutral' : marketCapChange > -5 ? 'bearish' : 'very_bearish'
      };
    }

    // Calculate overall sentiment
    const signals = Object.values(sentiment.indicators).map(ind => ind.signal);
    const bullishCount = signals.filter(s => s.includes('bullish') || s.includes('greed')).length;
    const bearishCount = signals.filter(s => s.includes('bearish') || s.includes('fear')).length;
    
    if (bullishCount > bearishCount) {
      sentiment.overall = 'bullish';
      sentiment.confidence = (bullishCount / signals.length);
    } else if (bearishCount > bullishCount) {
      sentiment.overall = 'bearish';
      sentiment.confidence = (bearishCount / signals.length);
    }

    return sentiment;
  }

  /**
   * Fallback sentiment calculation when Fear & Greed API is unavailable
   */
  async calculateFallbackSentiment() {
    try {
      // Calculate based on Bitcoin and major crypto movements
      const majorCryptos = await this.getRealTimePrices(['bitcoin', 'ethereum', 'binancecoin']);
      
      const avgChange = majorCryptos.data.reduce((sum, crypto) => 
        sum + crypto.price_change_24h, 0) / majorCryptos.data.length;
      
      let value, classification;
      
      if (avgChange > 10) {
        value = 85; classification = 'Extreme Greed';
      } else if (avgChange > 5) {
        value = 70; classification = 'Greed';
      } else if (avgChange > -5) {
        value = 50; classification = 'Neutral';
      } else if (avgChange > -10) {
        value = 30; classification = 'Fear';
      } else {
        value = 15; classification = 'Extreme Fear';
      }

      return {
        value,
        value_classification: classification,
        timestamp: Date.now(),
        calculated: true,
        note: 'Calculated from major crypto price movements'
      };

    } catch (error) {
      // Ultimate fallback
      return {
        value: 50,
        value_classification: 'Neutral',
        timestamp: Date.now(),
        calculated: true,
        note: 'Default neutral sentiment - data unavailable'
      };
    }
  }

  /**
   * Get provider warnings for partial failures
   */
  getProviderWarnings(results) {
    const warnings = [];
    
    results.forEach((result, index) => {
      if (result.status === 'rejected') {
        const providers = ['global data', 'top cryptocurrencies', 'fear & greed index'];
        warnings.push(`Failed to fetch ${providers[index]}: ${result.reason.message}`);
      }
    });

    return warnings;
  }

  /**
   * Health check for all providers
   */
  async healthCheck() {
    const health = {
      status: 'healthy',
      providers: {},
      cache: {
        size: this.cache.size,
        lastReset: new Date(this.lastReset).toISOString()
      },
      timestamp: new Date().toISOString()
    };

    for (const [name, provider] of Object.entries(this.providers)) {
      try {
        const startTime = Date.now();
        
        // Simple health check request
        switch (name) {
          case 'coingecko':
            await this.makeRequest(name, '/ping');
            break;
          case 'coinbase':
            await this.makeRequest(name, '/time');
            break;
          case 'binance':
            await this.makeRequest(name, '/ping');
            break;
        }
        
        health.providers[name] = {
          status: 'healthy',
          responseTime: Date.now() - startTime,
          requestCount: this.requestCounts.get(name) || 0,
          rateLimit: provider.rateLimit
        };
        
      } catch (error) {
        health.providers[name] = {
          status: 'unhealthy',
          error: error.message,
          requestCount: this.requestCounts.get(name) || 0
        };
        health.status = 'degraded';
      }
    }

    return health;
  }
}

/**
 * Custom error class for crypto data operations
 */
class CryptoDataError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = 'CryptoDataError';
    this.code = code;
    this.details = details;
    this.timestamp = new Date().toISOString();
  }
}

// Export singleton instance
module.exports = new EnhancedCryptoDataService();
module.exports.CryptoDataError = CryptoDataError;
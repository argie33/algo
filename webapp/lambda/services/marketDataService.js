/**
 * Market Data Service - Live API Connections for Real-Time Financial Data
 * Provides real-time and historical market data from multiple sources
 * Integrates with existing timeout helpers and circuit breakers
 */

const logger = require('../utils/logger');
const { query, healthCheck } = require('../utils/database');
const timeoutHelper = require('../utils/timeoutHelper');
const yfinance = require('yfinance');

class MarketDataService {
  constructor() {
    this.dataSources = {
      yfinance: true,     // Yahoo Finance (free)
      alpaca: false,      // Alpaca (requires API key)
      polygon: false,     // Polygon.io (requires API key)
      iex: false          // IEX Cloud (requires API key)
    };
    
    this.cache = new Map();
    this.cacheTimeout = 60000; // 1 minute cache for quotes
    this.retryConfig = {
      maxRetries: 3,
      retryDelay: 1000,
      exponentialBackoff: true
    };
  }

  /**
   * Get real-time quote for a single symbol
   */
  async getQuote(symbol) {
    try {
      logger.info(`Getting quote for symbol: ${symbol}`);
      
      // Check cache first
      const cacheKey = `quote_${symbol}`;
      const cached = this.getCachedData(cacheKey);
      if (cached) {
        logger.debug(`Returning cached quote for ${symbol}`);
        return cached;
      }

      // Fetch from primary data source (Yahoo Finance)
      const quote = await this.fetchQuoteFromYahoo(symbol);
      
      // Cache the result
      this.setCachedData(cacheKey, quote);
      
      logger.info(`Successfully retrieved quote for ${symbol}: $${quote.price}`);
      return quote;

    } catch (error) {
      logger.error('Error getting quote:', {
        symbol,
        error: error.message,
        stack: error.stack
      });
      throw new Error(`Failed to get quote for ${symbol}: ${error.message}`);
    }
  }

  /**
   * Get real-time quotes for multiple symbols
   */
  async getQuotes(symbols) {
    try {
      logger.info(`Getting quotes for ${symbols.length} symbols`);
      
      const quotes = {};
      const uncachedSymbols = [];
      
      // Check cache for each symbol
      for (const symbol of symbols) {
        const cacheKey = `quote_${symbol}`;
        const cached = this.getCachedData(cacheKey);
        if (cached) {
          quotes[symbol] = cached;
        } else {
          uncachedSymbols.push(symbol);
        }
      }
      
      // Fetch uncached symbols in batches
      if (uncachedSymbols.length > 0) {
        const batchSize = 10; // Process in batches to avoid rate limits
        const batches = this.createBatches(uncachedSymbols, batchSize);
        
        for (const batch of batches) {
          const batchQuotes = await this.fetchQuotesFromYahoo(batch);
          
          // Add to results and cache
          for (const [symbol, quote] of Object.entries(batchQuotes)) {
            quotes[symbol] = quote;
            this.setCachedData(`quote_${symbol}`, quote);
          }
          
          // Small delay between batches to be respectful to API
          if (batches.indexOf(batch) < batches.length - 1) {
            await timeoutHelper.delay(200);
          }
        }
      }
      
      logger.info(`Successfully retrieved ${Object.keys(quotes).length} quotes`);
      return quotes;

    } catch (error) {
      logger.error('Error getting quotes:', {
        symbolCount: symbols.length,
        error: error.message,
        stack: error.stack
      });
      throw new Error(`Failed to get quotes: ${error.message}`);
    }
  }

  /**
   * Get historical data for a symbol
   */
  async getHistoricalData(symbol, options = {}) {
    const {
      period = '1y',     // 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
      interval = '1d',   // 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
      includeAdjusted = true
    } = options;

    try {
      logger.info(`Getting historical data for ${symbol}: ${period} / ${interval}`);
      
      // Check cache for historical data (longer cache time)
      const cacheKey = `historical_${symbol}_${period}_${interval}`;
      const cached = this.getCachedData(cacheKey, 300000); // 5 minute cache
      if (cached) {
        logger.debug(`Returning cached historical data for ${symbol}`);
        return cached;
      }

      const historicalData = await timeoutHelper.executeWithRetry(
        () => this.fetchHistoricalFromYahoo(symbol, period, interval, includeAdjusted),
        this.retryConfig
      );
      
      // Cache the result
      this.setCachedData(cacheKey, historicalData, 300000);
      
      logger.info(`Retrieved ${historicalData.length} historical data points for ${symbol}`);
      return historicalData;

    } catch (error) {
      logger.error('Error getting historical data:', {
        symbol,
        period,
        interval,
        error: error.message,
        stack: error.stack
      });
      throw new Error(`Failed to get historical data for ${symbol}: ${error.message}`);
    }
  }

  /**
   * Get market data for portfolio optimization
   */
  async getPortfolioMarketData(symbols, options = {}) {
    try {
      logger.info(`Getting portfolio market data for ${symbols.length} symbols`);
      
      const {
        includeHistorical = true,
        historicalPeriod = '1y',
        includeVolatility = true,
        includeBeta = true
      } = options;

      const marketData = {};
      
      // Get current quotes
      const quotes = await this.getQuotes(symbols);
      
      // Add quotes to market data
      for (const [symbol, quote] of Object.entries(quotes)) {
        marketData[symbol] = {
          ...quote,
          symbol
        };
      }
      
      // Get historical data if requested
      if (includeHistorical) {
        logger.info('Fetching historical data for portfolio symbols');
        
        const historicalPromises = symbols.map(async (symbol) => {
          try {
            const historical = await this.getHistoricalData(symbol, {
              period: historicalPeriod,
              interval: '1d'
            });
            
            if (marketData[symbol]) {
              marketData[symbol].historical = historical;
              
              if (includeVolatility) {
                marketData[symbol].volatility = this.calculateVolatility(historical);
              }
              
              if (includeBeta) {
                // For now, set a default beta. In a real implementation,
                // you would calculate beta against a market index
                marketData[symbol].beta = 1.0;
              }
            }
          } catch (error) {
            logger.warn(`Failed to get historical data for ${symbol}:`, error.message);
            // Continue with other symbols
          }
        });
        
        await Promise.allSettled(historicalPromises);
      }
      
      logger.info(`Portfolio market data complete: ${Object.keys(marketData).length} symbols processed`);
      return marketData;

    } catch (error) {
      logger.error('Error getting portfolio market data:', {
        symbolCount: symbols.length,
        error: error.message,
        stack: error.stack
      });
      throw new Error(`Failed to get portfolio market data: ${error.message}`);
    }
  }

  /**
   * Search for symbols/companies
   */
  async searchSymbols(query, limit = 10) {
    try {
      logger.info(`Searching symbols for query: ${query}`);
      
      // For Yahoo Finance, we can search using their API
      // This is a simplified implementation
      const searchResults = await this.searchSymbolsYahoo(query, limit);
      
      logger.info(`Found ${searchResults.length} symbols for query: ${query}`);
      return searchResults;

    } catch (error) {
      logger.error('Error searching symbols:', {
        query,
        error: error.message,
        stack: error.stack
      });
      throw new Error(`Failed to search symbols: ${error.message}`);
    }
  }

  /**
   * Get market status (open/closed)
   */
  async getMarketStatus() {
    try {
      const now = new Date();
      const nyTime = new Date(now.toLocaleString("en-US", {timeZone: "America/New_York"}));
      const dayOfWeek = nyTime.getDay(); // 0 = Sunday, 6 = Saturday
      const hour = nyTime.getHours();
      const minute = nyTime.getMinutes();
      const currentTime = hour * 60 + minute; // Convert to minutes since midnight
      
      // Market hours: 9:30 AM - 4:00 PM EST, Monday-Friday
      const marketOpen = 9 * 60 + 30;  // 9:30 AM in minutes
      const marketClose = 16 * 60;     // 4:00 PM in minutes
      
      const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5;
      const isMarketHours = currentTime >= marketOpen && currentTime < marketClose;
      const isOpen = isWeekday && isMarketHours;
      
      // Calculate next market open/close
      let nextChange;
      if (isOpen) {
        // Market is open, next change is close today
        const closeToday = new Date(nyTime);
        closeToday.setHours(16, 0, 0, 0);
        nextChange = {
          event: 'close',
          timestamp: closeToday.toISOString()
        };
      } else {
        // Market is closed, calculate next open
        let nextOpen = new Date(nyTime);
        nextOpen.setHours(9, 30, 0, 0);
        
        // If it's after market close today or weekend, next open is next weekday
        if (currentTime >= marketClose || dayOfWeek === 0 || dayOfWeek === 6) {
          // Find next Monday
          const daysUntilMonday = dayOfWeek === 0 ? 1 : (8 - dayOfWeek);
          nextOpen.setDate(nextOpen.getDate() + daysUntilMonday);
        }
        
        nextChange = {
          event: 'open',
          timestamp: nextOpen.toISOString()
        };
      }
      
      return {
        isOpen,
        currentTime: nyTime.toISOString(),
        timezone: 'America/New_York',
        nextChange,
        regularHours: {
          open: '09:30',
          close: '16:00'
        }
      };

    } catch (error) {
      logger.error('Error getting market status:', error);
      throw new Error(`Failed to get market status: ${error.message}`);
    }
  }

  /**
   * Save market data to database for historical tracking
   */
  async saveMarketDataSnapshot(symbols, marketData) {
    try {
      logger.info(`Saving market data snapshot for ${symbols.length} symbols`);
      
      const snapshot = {
        timestamp: new Date(),
        symbolCount: symbols.length,
        data: marketData
      };
      
      await query(`
        INSERT INTO market_data_snapshots (
          timestamp, symbol_count, data, created_at
        ) VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
      `, [snapshot.timestamp, snapshot.symbolCount, JSON.stringify(snapshot.data)]);
      
      logger.info('Market data snapshot saved successfully');
      return { success: true, timestamp: snapshot.timestamp };

    } catch (error) {
      logger.error('Error saving market data snapshot:', error);
      // Don't throw - this is not critical for functionality
      return { success: false, error: error.message };
    }
  }

  // Private helper methods

  /**
   * Fetch quote from Yahoo Finance
   */
  async fetchQuoteFromYahoo(symbol) {
    try {
      const result = await timeoutHelper.executeWithTimeout(async () => {
        // Using yfinance library for Yahoo Finance data
        const stock = yfinance.stock(symbol);
        const quote = await stock.getQuote();
        
        return {
          symbol,
          price: quote.regularMarketPrice,
          change: quote.regularMarketChange,
          changePercent: quote.regularMarketChangePercent,
          volume: quote.regularMarketVolume,
          marketCap: quote.marketCap,
          peRatio: quote.trailingPE,
          high52Week: quote.fiftyTwoWeekHigh,
          low52Week: quote.fiftyTwoWeekLow,
          timestamp: new Date().toISOString(),
          source: 'yahoo'
        };
      }, 10000); // 10 second timeout
      
      return result;
      
    } catch (error) {
      logger.error(`Yahoo Finance fetch failed for ${symbol}:`, error);
      throw new Error(`Yahoo Finance API error: ${error.message}`);
    }
  }

  /**
   * Fetch quotes for multiple symbols from Yahoo Finance
   */
  async fetchQuotesFromYahoo(symbols) {
    try {
      const quotes = {};
      
      // Process symbols individually for better error handling
      const promises = symbols.map(async (symbol) => {
        try {
          const quote = await this.fetchQuoteFromYahoo(symbol);
          quotes[symbol] = quote;
        } catch (error) {
          logger.warn(`Failed to fetch quote for ${symbol}:`, error.message);
          // Add a placeholder with error info
          quotes[symbol] = {
            symbol,
            error: error.message,
            timestamp: new Date().toISOString(),
            source: 'yahoo'
          };
        }
      });
      
      await Promise.allSettled(promises);
      return quotes;
      
    } catch (error) {
      logger.error('Batch quote fetch failed:', error);
      throw new Error(`Batch quote fetch error: ${error.message}`);
    }
  }

  /**
   * Fetch historical data from Yahoo Finance
   */
  async fetchHistoricalFromYahoo(symbol, period, interval, includeAdjusted) {
    try {
      const stock = yfinance.stock(symbol);
      const history = await stock.getHistory({
        period,
        interval,
        includeAdjusted
      });
      
      // Convert to our standard format
      return history.map(row => ({
        date: row.date,
        open: row.open,
        high: row.high,
        low: row.low,
        close: row.close,
        adjustedClose: includeAdjusted ? row.adjClose : row.close,
        volume: row.volume
      }));
      
    } catch (error) {
      logger.error(`Historical data fetch failed for ${symbol}:`, error);
      throw new Error(`Historical data API error: ${error.message}`);
    }
  }

  /**
   * Search symbols using Yahoo Finance
   */
  async searchSymbolsYahoo(query, limit) {
    try {
      // This is a simplified implementation
      // In a real implementation, you'd use Yahoo Finance search API
      const searchResults = [
        {
          symbol: query.toUpperCase(),
          name: `${query.toUpperCase()} Company`,
          exchange: 'NASDAQ',
          type: 'stock'
        }
      ];
      
      return searchResults.slice(0, limit);
      
    } catch (error) {
      logger.error('Symbol search failed:', error);
      throw new Error(`Symbol search error: ${error.message}`);
    }
  }

  /**
   * Calculate volatility from historical data
   */
  calculateVolatility(historicalData) {
    if (!historicalData || historicalData.length < 2) {
      return null;
    }
    
    // Calculate daily returns
    const returns = [];
    for (let i = 1; i < historicalData.length; i++) {
      const prevClose = historicalData[i - 1].close;
      const currentClose = historicalData[i].close;
      if (prevClose > 0) {
        returns.push((currentClose - prevClose) / prevClose);
      }
    }
    
    if (returns.length === 0) {
      return null;
    }
    
    // Calculate standard deviation (volatility)
    const mean = returns.reduce((sum, ret) => sum + ret, 0) / returns.length;
    const variance = returns.reduce((sum, ret) => sum + Math.pow(ret - mean, 2), 0) / returns.length;
    const dailyVolatility = Math.sqrt(variance);
    
    // Annualize volatility (assuming 252 trading days per year)
    const annualizedVolatility = dailyVolatility * Math.sqrt(252);
    
    return {
      daily: dailyVolatility,
      annualized: annualizedVolatility
    };
  }

  /**
   * Cache management
   */
  getCachedData(key, maxAge = this.cacheTimeout) {
    const cached = this.cache.get(key);
    if (cached) {
      const age = Date.now() - cached.timestamp;
      if (age < maxAge) {
        return cached.data;
      } else {
        this.cache.delete(key);
      }
    }
    return null;
  }

  setCachedData(key, data, maxAge = this.cacheTimeout) {
    this.cache.set(key, {
      data,
      timestamp: Date.now()
    });
    
    // Clean up old cache entries periodically
    if (this.cache.size > 1000) {
      this.cleanupCache();
    }
  }

  cleanupCache() {
    const now = Date.now();
    for (const [key, cached] of this.cache.entries()) {
      if (now - cached.timestamp > this.cacheTimeout * 2) {
        this.cache.delete(key);
      }
    }
  }

  /**
   * Utility method to create batches
   */
  createBatches(array, batchSize) {
    const batches = [];
    for (let i = 0; i < array.length; i += batchSize) {
      batches.push(array.slice(i, i + batchSize));
    }
    return batches;
  }

  /**
   * Health check for market data service
   */
  async healthCheck() {
    try {
      // Test with a simple quote fetch
      const testQuote = await this.getQuote('AAPL');
      
      return {
        status: 'healthy',
        service: 'market-data',
        dataSources: this.dataSources,
        cacheSize: this.cache.size,
        testQuote: {
          symbol: testQuote.symbol,
          price: testQuote.price,
          timestamp: testQuote.timestamp
        },
        timestamp: new Date().toISOString()
      };
      
    } catch (error) {
      return {
        status: 'unhealthy',
        service: 'market-data',
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }
}

// Create and export singleton instance
const marketDataService = new MarketDataService();

module.exports = marketDataService;
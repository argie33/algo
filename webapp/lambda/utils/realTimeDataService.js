/**
 * Real-Time Data Service
 *
 * Comprehensive service to replace mock data throughout the application
 * Integrates with Alpaca and other data providers for live market data
 *
 * Features:
 * - Real-time quotes and trades
 * - Market indices tracking
 * - Sector performance analysis
 * - Market sentiment indicators
 * - Robust error handling and fallback mechanisms
 */

const AlpacaService = require("./alpacaService");
const { getDecryptedApiKey } = require("./apiKeyService");

class RealTimeDataService {
  constructor() {
    this.cache = new Map();
    this.cacheTimeout = 30000; // 30 seconds
    this.rateLimitDelay = 1000; // 1 second between requests
    this.lastRequestTime = 0;

    // Initialize with common symbols
    this.watchedSymbols = new Set([
      "AAPL",
      "MSFT",
      "GOOGL",
      "AMZN",
      "TSLA",
      "NVDA",
      "META",
    ]);
    this.indexSymbols = new Set(["SPY", "QQQ", "DIA", "IWM", "VIX"]);

    // Market status cache
    this.marketStatus = null;
    this.marketStatusUpdatedAt = 0;

    if (process.env.NODE_ENV !== "test") {
      console.log("🚀 Real-Time Data Service initialized");
    }
  }

  /**
   * Rate limiting helper
   */
  async rateLimit() {
    const now = Date.now();
    const timeSinceLastRequest = now - this.lastRequestTime;

    if (timeSinceLastRequest < this.rateLimitDelay) {
      const delay = this.rateLimitDelay - timeSinceLastRequest;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }

    this.lastRequestTime = Date.now();
  }

  /**
   * Get cached data or fetch fresh data
   */
  async getCachedOrFetch(cacheKey, fetchFunction, ttl = this.cacheTimeout) {
    const cached = this.cache.get(cacheKey);
    const now = Date.now();

    if (cached && now - cached.timestamp < ttl) {
      return cached.data;
    }

    try {
      await this.rateLimit();
      const data = await fetchFunction();

      this.cache.set(cacheKey, {
        data,
        timestamp: now,
      });

      return data;
    } catch (error) {
      console.error(`Failed to fetch data for ${cacheKey}:`, error.message);

      // Return stale cache if available
      if (cached) {
        console.warn(`Using stale cache for ${cacheKey}`);
        return cached.data;
      }

      throw error;
    }
  }

  /**
   * Get user's Alpaca service instance
   */
  async getUserAlpacaService(userId) {
    if (!userId) {
      throw new Error("User ID is required for Alpaca service");
    }

    console.log(
      `🔑 Getting Alpaca credentials for user ${userId.substring(0, 8)}...`
    );

    const credentials = await getDecryptedApiKey(userId, "alpaca");
    if (!credentials) {
      throw new Error("No Alpaca API credentials configured for user");
    }

    console.log(
      `✅ Alpaca credentials found for user ${userId.substring(0, 8)}...`
    );

    return new AlpacaService(
      credentials.apiKey,
      credentials.apiSecret,
      credentials.isSandbox || false
    );
  }

  /**
   * Get live market data for symbols using user's credentials
   */
  async getLiveMarketData(userId, symbols = []) {
    try {
      const alpacaService = await this.getUserAlpacaService(userId);
      const symbolList =
        symbols.length > 0 ? symbols : Array.from(this.watchedSymbols);

      console.log(
        `📊 Fetching live market data for ${symbolList.length} symbols`
      );

      const marketData = {};
      let successCount = 0;
      let errorCount = 0;

      for (const symbol of symbolList.slice(0, 20)) {
        // Limit to 20 symbols
        try {
          const cacheKey = `quote:${symbol}:${userId.substring(0, 8)}`;

          const quote = await this.getCachedOrFetch(cacheKey, async () => {
            const quoteData = await alpacaService.getLatestQuote(symbol);
            if (!quoteData) {
              throw new Error(`No quote data for ${symbol}`);
            }
            return quoteData;
          });

          if (quote) {
            marketData[symbol] = {
              symbol,
              price: (quote.bidPrice + quote.askPrice) / 2,
              bidPrice: quote.bidPrice,
              askPrice: quote.askPrice,
              bidSize: quote.bidSize,
              askSize: quote.askSize,
              spread: quote.askPrice - quote.bidPrice,
              timestamp: quote.timestamp,
              exchange: quote.exchange,
              dataSource: "alpaca",
            };
            successCount++;
          }
        } catch (error) {
          console.error(`Failed to get quote for ${symbol}:`, error.message);
          marketData[symbol] = {
            symbol,
            error: error.message,
            dataSource: "alpaca",
            timestamp: new Date().toISOString(),
          };
          errorCount++;
        }
      }

      console.log(
        `✅ Market data fetch completed: ${successCount} successful, ${errorCount} errors`
      );

      return {
        data: marketData,
        metadata: {
          symbolCount: symbolList.length,
          successCount,
          errorCount,
          dataProvider: "alpaca",
          timestamp: new Date().toISOString(),
        },
      };
    } catch (error) {
      console.error("Failed to get live market data:", error.message);
      throw new Error(`Live market data unavailable: ${error.message}`);
    }
  }

  /**
   * Get historical price for change calculation
   */
  async getHistoricalPrice(alpacaService, symbol, daysBack = 1) {
    try {
      const cacheKey = `historical:${symbol}:${daysBack}d`;

      return await this.getCachedOrFetch(
        cacheKey,
        async () => {
          const endDate = new Date();
          const startDate = new Date();
          startDate.setDate(startDate.getDate() - daysBack);

          const bars = await alpacaService.getBars(symbol, {
            start: startDate.toISOString().split("T")[0],
            end: endDate.toISOString().split("T")[0],
            timeframe: "1Day",
            adjustment: "raw",
            limit: daysBack,
          });

          if (bars && bars.length > 0) {
            // Return the closing price from the requested days back
            const targetBar = bars[bars.length - daysBack] || bars[0];
            return targetBar.ClosePrice || targetBar.c || targetBar.close;
          }

          return null;
        },
        300000
      ); // Cache for 5 minutes
    } catch (error) {
      console.warn(
        `Failed to get historical price for ${symbol}:`,
        error.message
      );
      return null;
    }
  }

  /**
   * Calculate price change and percentage
   */
  calculatePriceChange(currentPrice, historicalPrice) {
    if (!historicalPrice || historicalPrice <= 0) {
      return { change: 0, changePercent: 0 };
    }

    const change = currentPrice - historicalPrice;
    const changePercent = (change / historicalPrice) * 100;

    return {
      change: parseFloat(change.toFixed(2)),
      changePercent: parseFloat(changePercent.toFixed(2)),
    };
  }

  /**
   * Get market indices data with real change calculations
   */
  async getMarketIndices(userId) {
    try {
      const alpacaService = await this.getUserAlpacaService(userId);
      const indices = {};

      console.log("📈 Fetching market indices data with historical changes");

      for (const symbol of this.indexSymbols) {
        try {
          const cacheKey = `index:${symbol}:${userId.substring(0, 8)}`;

          const [quote, historicalPrice] = await Promise.allSettled([
            this.getCachedOrFetch(cacheKey, async () => {
              return await alpacaService.getLatestQuote(symbol);
            }),
            this.getHistoricalPrice(alpacaService, symbol, 1),
          ]);

          if (quote.status === "fulfilled" && quote.value) {
            const currentPrice =
              (quote.value.bidPrice + quote.value.askPrice) / 2;
            const yesterdayPrice =
              historicalPrice.status === "fulfilled"
                ? historicalPrice.value
                : null;
            const priceChange = this.calculatePriceChange(
              currentPrice,
              yesterdayPrice
            );

            indices[symbol] = {
              symbol,
              name: this.getIndexName(symbol),
              value: parseFloat(currentPrice.toFixed(2)),
              change: priceChange.change,
              changePercent: priceChange.changePercent,
              timestamp: quote.value.timestamp,
              dataSource: "alpaca",
              historicalDataAvailable: !!yesterdayPrice,
            };
          }
        } catch (error) {
          console.error(
            `Failed to get index data for ${symbol}:`,
            error.message
          );
          indices[symbol] = {
            symbol,
            name: this.getIndexName(symbol),
            error: error.message,
            timestamp: new Date().toISOString(),
          };
        }
      }

      return indices;
    } catch (error) {
      console.error("Failed to get market indices:", error.message);
      throw new Error(`Market indices unavailable: ${error.message}`);
    }
  }

  /**
   * Get market status using user's credentials
   */
  async getMarketStatus(userId) {
    try {
      const now = Date.now();

      // Use cached market status if fresh (market status doesn't change frequently)
      if (this.marketStatus && now - this.marketStatusUpdatedAt < 60000) {
        return this.marketStatus;
      }

      const alpacaService = await this.getUserAlpacaService(userId);

      console.log("🕐 Fetching market status");

      const marketClock = await alpacaService.getMarketClock();

      this.marketStatus = {
        isOpen: marketClock.isOpen,
        timestamp: marketClock.timestamp,
        nextOpen: marketClock.nextOpen,
        nextClose: marketClock.nextClose,
        timezone: marketClock.timezone,
        sessionType: this.determineSessionType(marketClock),
        dataSource: "alpaca",
      };

      this.marketStatusUpdatedAt = now;

      return this.marketStatus;
    } catch (error) {
      console.error("Failed to get market status:", error.message);

      // Return fallback market status
      return {
        isOpen: false,
        timestamp: new Date().toISOString(),
        nextOpen: null,
        nextClose: null,
        timezone: "America/New_York",
        sessionType: "unknown",
        error: error.message,
        dataSource: "fallback",
      };
    }
  }

  /**
   * Get comprehensive market overview
   */
  async getMarketOverview(userId, options = {}) {
    try {
      const { includeIndices = true, includeWatchlist = true } = options;

      console.log("🌐 Fetching comprehensive market overview");

      const [marketStatus, marketData, indices] = await Promise.allSettled([
        this.getMarketStatus(userId),
        includeWatchlist
          ? this.getLiveMarketData(userId)
          : Promise.resolve(null),
        includeIndices ? this.getMarketIndices(userId) : Promise.resolve(null),
      ]);

      return {
        marketStatus:
          marketStatus.status === "fulfilled" ? marketStatus.value : null,
        watchlistData:
          marketData.status === "fulfilled" ? marketData.value : null,
        indices: indices.status === "fulfilled" ? indices.value : null,
        timestamp: new Date().toISOString(),
        dataProvider: "alpaca",
        errors: [
          marketStatus.status === "rejected"
            ? { section: "marketStatus", error: marketStatus.reason?.message }
            : null,
          marketData.status === "rejected"
            ? { section: "marketData", error: marketData.reason?.message }
            : null,
          indices.status === "rejected"
            ? { section: "indices", error: indices.reason?.message }
            : null,
        ].filter(Boolean),
      };
    } catch (error) {
      console.error("Failed to get market overview:", error.message);
      throw new Error(`Market overview unavailable: ${error.message}`);
    }
  }

  /**
   * Get sector performance with real change calculations
   */
  async getSectorPerformance(userId) {
    try {
      console.log(
        "🏢 Fetching sector performance data with historical changes"
      );

      // Track major sector ETFs with real change calculations
      const sectorETFs = {
        XLK: "Technology",
        XLV: "Healthcare",
        XLF: "Financials",
        XLY: "Consumer Discretionary",
        XLP: "Consumer Staples",
        XLE: "Energy",
        XLI: "Industrials",
        XLB: "Materials",
        XLU: "Utilities",
        XLRE: "Real Estate",
      };

      const alpacaService = await this.getUserAlpacaService(userId);
      const sectorData = [];

      for (const [etfSymbol, sectorName] of Object.entries(sectorETFs)) {
        try {
          const cacheKey = `sector:${etfSymbol}:${userId.substring(0, 8)}`;

          const [quote, historicalPrice] = await Promise.allSettled([
            this.getCachedOrFetch(cacheKey, async () => {
              return await alpacaService.getLatestQuote(etfSymbol);
            }),
            this.getHistoricalPrice(alpacaService, etfSymbol, 1),
          ]);

          if (quote.status === "fulfilled" && quote.value) {
            const currentPrice =
              (quote.value.bidPrice + quote.value.askPrice) / 2;
            const yesterdayPrice =
              historicalPrice.status === "fulfilled"
                ? historicalPrice.value
                : null;
            const priceChange = this.calculatePriceChange(
              currentPrice,
              yesterdayPrice
            );

            sectorData.push({
              sector: sectorName,
              etfSymbol: etfSymbol,
              price: parseFloat(currentPrice.toFixed(2)),
              change: priceChange.change,
              changePercent: priceChange.changePercent,
              timestamp: quote.value.timestamp,
              dataSource: "alpaca",
              historicalDataAvailable: !!yesterdayPrice,
              performance: this.categorizeSectorPerformance(
                priceChange.changePercent
              ),
            });
          }
        } catch (error) {
          console.error(
            `Failed to get sector data for ${sectorName}:`,
            error.message
          );
          sectorData.push({
            sector: sectorName,
            etfSymbol: etfSymbol,
            error: error.message,
            timestamp: new Date().toISOString(),
          });
        }
      }

      // Sort by performance for better analysis
      sectorData.sort(
        (a, b) => (b.changePercent || -999) - (a.changePercent || -999)
      );

      return {
        sectors: sectorData,
        summary: this.calculateSectorSummary(sectorData),
        timestamp: new Date().toISOString(),
      };
    } catch (error) {
      console.error("Failed to get sector performance:", error.message);
      throw new Error(`Sector performance unavailable: ${error.message}`);
    }
  }

  /**
   * Categorize sector performance for better analysis
   */
  categorizeSectorPerformance(changePercent) {
    if (changePercent >= 2) return "strong-outperform";
    if (changePercent >= 1) return "outperform";
    if (changePercent >= -1) return "neutral";
    if (changePercent >= -2) return "underperform";
    return "strong-underperform";
  }

  /**
   * Calculate sector performance summary
   */
  calculateSectorSummary(sectorData) {
    const validSectors = sectorData.filter(
      (s) => !s.error && typeof s.changePercent === "number"
    );

    if (validSectors.length === 0) {
      return { error: "No valid sector data available" };
    }

    const totalSectors = validSectors.length;
    const gaining = validSectors.filter((s) => s.changePercent > 0).length;
    const declining = validSectors.filter((s) => s.changePercent < 0).length;
    const unchanged = totalSectors - gaining - declining;

    const avgChange =
      validSectors.reduce((sum, s) => sum + s.changePercent, 0) / totalSectors;
    const bestSector = validSectors[0]; // Already sorted by performance
    const worstSector = validSectors[validSectors.length - 1];

    return {
      totalSectors,
      gaining,
      declining,
      unchanged,
      averageChange: parseFloat(avgChange.toFixed(2)),
      bestPerformer: bestSector
        ? {
            sector: bestSector.sector,
            change: bestSector.changePercent,
          }
        : null,
      worstPerformer: worstSector
        ? {
            sector: worstSector.sector,
            change: worstSector.changePercent,
          }
        : null,
      marketSentiment: this.determineSectorSentiment(
        gaining,
        declining,
        totalSectors
      ),
    };
  }

  /**
   * Determine overall market sentiment from sector performance
   */
  determineSectorSentiment(gaining, declining, total) {
    const gainingRatio = gaining / total;

    if (gainingRatio >= 0.7) return "bullish";
    if (gainingRatio >= 0.6) return "moderately-bullish";
    if (gainingRatio >= 0.4) return "mixed";
    if (gainingRatio >= 0.3) return "moderately-bearish";
    return "bearish";
  }

  /**
   * Helper methods
   */
  getIndexName(symbol) {
    const names = {
      SPY: "S&P 500",
      QQQ: "NASDAQ 100",
      DIA: "Dow Jones",
      IWM: "Russell 2000",
      VIX: "VIX Volatility",
    };
    return names[symbol] || symbol;
  }

  determineSessionType(marketClock) {
    if (!marketClock.isOpen) {
      return "closed";
    }

    const now = new Date();
    const hour = now.getHours();

    if (hour < 9 || (hour === 9 && now.getMinutes() < 30)) {
      return "pre-market";
    } else if (hour >= 16) {
      return "after-hours";
    } else {
      return "regular";
    }
  }

  /**
   * Clear cache (useful for testing or manual refresh)
   */
  clearCache() {
    this.cache.clear();
    this.marketStatus = null;
    this.marketStatusUpdatedAt = 0;
    console.log("🧹 Cache cleared");
  }

  /**
   * Get cache statistics
   */
  getCacheStats() {
    const now = Date.now();
    let freshEntries = 0;
    let staleEntries = 0;

    for (const [_key, value] of this.cache.entries()) {
      if (now - value.timestamp < this.cacheTimeout) {
        freshEntries++;
      } else {
        staleEntries++;
      }
    }

    return {
      totalEntries: this.cache.size,
      freshEntries,
      staleEntries,
      cacheTimeout: this.cacheTimeout,
      lastCleared: this.marketStatusUpdatedAt,
    };
  }
}

// Export singleton instance
const realTimeDataService = new RealTimeDataService();

module.exports = realTimeDataService;

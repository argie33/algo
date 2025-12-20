import AsyncStorage from '@react-native-async-storage/async-storage';

export interface OfflinePortfolioData {
  holdings: any[];
  totalValue: number;
  dayChange: number;
  dayChangePercent: number;
  lastSync: string;
}

export interface OfflineMarketData {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  timestamp: string;
}

export class OfflineDataService {
  private static syncInterval: NodeJS.Timeout | null = null;

  /**
   * Initialize offline data service
   */
  static async initialize(): Promise<void> {
    try {
      // Start background sync
      await this.startBackgroundSync();
      console.log('Offline data service initialized');
    } catch (error) {
      console.error('Failed to initialize offline data service:', error);
      throw error;
    }
  }

  /**
   * Cache portfolio data for offline access
   */
  static async cachePortfolioData(portfolioData: any): Promise<void> {
    try {
      const cacheData = {
        holdings: portfolioData.holdings || [],
        totalValue: portfolioData.equity || 0,
        dayChange: portfolioData.day_change || 0,
        dayChangePercent: portfolioData.day_change_percent || 0,
        lastSync: new Date().toISOString(),
      };

      await AsyncStorage.setItem('cachedPortfolioData', JSON.stringify(cacheData));
      console.log('Portfolio data cached successfully');
    } catch (error) {
      console.error('Failed to cache portfolio data:', error);
    }
  }

  /**
   * Get cached portfolio data
   */
  static async getCachedPortfolioData(): Promise<OfflinePortfolioData | null> {
    try {
      const cachedData = await AsyncStorage.getItem('cachedPortfolioData');
      if (!cachedData) return null;

      return JSON.parse(cachedData);
    } catch (error) {
      console.error('Failed to get cached portfolio data:', error);
      return null;
    }
  }

  /**
   * Cache market data for offline access
   */
  static async cacheMarketData(marketData: OfflineMarketData[]): Promise<void> {
    try {
      const marketDataMap: Record<string, OfflineMarketData> = {};
      marketData.forEach(data => {
        marketDataMap[data.symbol] = data;
      });

      await AsyncStorage.setItem('cachedMarketData', JSON.stringify(marketDataMap));
      console.log(`Cached market data for ${marketData.length} symbols`);
    } catch (error) {
      console.error('Failed to cache market data:', error);
    }
  }

  /**
   * Get cached market data for a symbol
   */
  static async getCachedMarketData(symbol: string): Promise<OfflineMarketData | null> {
    try {
      const cachedData = await AsyncStorage.getItem('cachedMarketData');
      if (!cachedData) return null;

      const marketDataMap = JSON.parse(cachedData);
      return marketDataMap[symbol] || null;
    } catch (error) {
      console.error('Failed to get cached market data:', error);
      return null;
    }
  }

  /**
   * Get all cached market data
   */
  static async getAllCachedMarketData(): Promise<OfflineMarketData[]> {
    try {
      const cachedData = await AsyncStorage.getItem('cachedMarketData');
      if (!cachedData) return [];

      const marketDataMap = JSON.parse(cachedData);
      return Object.values(marketDataMap);
    } catch (error) {
      console.error('Failed to get all cached market data:', error);
      return [];
    }
  }

  /**
   * Check if device is online (simplified - always return true for now)
   */
  static async isOnline(): Promise<boolean> {
    // TODO: Implement network connectivity check
    return true;
  }

  /**
   * Sync data with server when online
   */
  static async syncWithServer(): Promise<void> {
    try {
      const isOnline = await this.isOnline();
      if (!isOnline) {
        console.log('Device is offline, skipping sync');
        return;
      }

      // Get auth token
      const authToken = await AsyncStorage.getItem('authToken');
      if (!authToken) {
        console.log('No auth token, skipping sync');
        return;
      }

      // TODO: Implement actual API calls
      console.log('Data sync completed (mock)');
    } catch (error) {
      console.error('Failed to sync with server:', error);
    }
  }

  /**
   * Start background sync process
   */
  private static async startBackgroundSync(): Promise<void> {
    // Sync every 5 minutes when app is active
    this.syncInterval = setInterval(async () => {
      await this.syncWithServer();
    }, 5 * 60 * 1000);

    // Initial sync
    await this.syncWithServer();
  }

  /**
   * Stop background sync
   */
  static stopBackgroundSync(): void {
    if (this.syncInterval) {
      clearInterval(this.syncInterval);
      this.syncInterval = null;
    }
  }

  /**
   * Clear all cached data
   */
  static async clearCache(): Promise<void> {
    try {
      await AsyncStorage.removeItem('cachedPortfolioData');
      await AsyncStorage.removeItem('cachedMarketData');
      console.log('Cache cleared successfully');
    } catch (error) {
      console.error('Failed to clear cache:', error);
    }
  }

  /**
   * Get cache statistics
   */
  static async getCacheStats(): Promise<{
    portfolioItems: number;
    marketDataItems: number;
    lastSync: string | null;
  }> {
    try {
      const portfolioData = await this.getCachedPortfolioData();
      const marketData = await this.getAllCachedMarketData();

      return {
        portfolioItems: portfolioData?.holdings?.length || 0,
        marketDataItems: marketData.length,
        lastSync: portfolioData?.lastSync || null,
      };
    } catch (error) {
      console.error('Failed to get cache stats:', error);
      return { portfolioItems: 0, marketDataItems: 0, lastSync: null };
    }
  }
}
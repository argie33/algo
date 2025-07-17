import AsyncStorage from '@react-native-async-storage/async-storage';
import SQLite from 'react-native-sqlite-storage';
import NetInfo from '@react-native-community/netinfo';

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
  private static db: SQLite.SQLiteDatabase | null = null;
  private static syncInterval: NodeJS.Timeout | null = null;

  /**
   * Initialize offline data service and SQLite database
   */
  static async initialize(): Promise<void> {
    try {
      // Enable SQLite debugging
      SQLite.enablePromise(true);
      SQLite.DEBUG(true);

      // Open database
      this.db = await SQLite.openDatabase({
        name: 'FinancialPlatform.db',
        location: 'default',
      });

      // Create tables
      await this.createTables();

      // Start background sync
      await this.startBackgroundSync();

      console.log('Offline data service initialized');
    } catch (error) {
      console.error('Failed to initialize offline data service:', error);
      throw error;
    }
  }

  /**
   * Create necessary database tables
   */
  private static async createTables(): Promise<void> {
    if (!this.db) throw new Error('Database not initialized');

    const createPortfolioTable = `
      CREATE TABLE IF NOT EXISTS portfolio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        quantity REAL NOT NULL,
        avg_cost REAL NOT NULL,
        current_price REAL NOT NULL,
        market_value REAL NOT NULL,
        day_change REAL NOT NULL,
        day_change_percent REAL NOT NULL,
        last_updated TEXT NOT NULL
      );
    `;

    const createMarketDataTable = `
      CREATE TABLE IF NOT EXISTS market_data (
        symbol TEXT PRIMARY KEY,
        price REAL NOT NULL,
        change_amount REAL NOT NULL,
        change_percent REAL NOT NULL,
        volume INTEGER NOT NULL,
        high REAL,
        low REAL,
        open REAL,
        previous_close REAL,
        last_updated TEXT NOT NULL
      );
    `;

    const createWatchlistTable = `
      CREATE TABLE IF NOT EXISTS watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL UNIQUE,
        added_date TEXT NOT NULL,
        alerts_enabled INTEGER DEFAULT 0,
        target_price REAL,
        stop_loss REAL
      );
    `;

    const createOrderHistoryTable = `
      CREATE TABLE IF NOT EXISTS order_history (
        id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        quantity REAL NOT NULL,
        price REAL NOT NULL,
        order_type TEXT NOT NULL,
        status TEXT NOT NULL,
        filled_qty REAL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
    `;

    await this.db.executeSql(createPortfolioTable);
    await this.db.executeSql(createMarketDataTable);
    await this.db.executeSql(createWatchlistTable);
    await this.db.executeSql(createOrderHistoryTable);
  }

  /**
   * Cache portfolio data for offline access
   */
  static async cachePortfolioData(portfolioData: any): Promise<void> {
    if (!this.db) throw new Error('Database not initialized');

    try {
      // Clear existing portfolio data
      await this.db.executeSql('DELETE FROM portfolio');

      // Insert new portfolio data
      for (const holding of portfolioData.holdings) {
        await this.db.executeSql(
          `INSERT INTO portfolio 
           (symbol, quantity, avg_cost, current_price, market_value, day_change, day_change_percent, last_updated)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
          [
            holding.symbol,
            holding.qty,
            holding.avg_cost,
            holding.current_price,
            holding.market_value,
            holding.unrealized_pl,
            holding.unrealized_plpc,
            new Date().toISOString(),
          ]
        );
      }

      // Cache summary data
      await AsyncStorage.setItem('cachedPortfolioSummary', JSON.stringify({
        totalValue: portfolioData.equity,
        dayChange: portfolioData.day_change,
        dayChangePercent: portfolioData.day_change_percent,
        lastSync: new Date().toISOString(),
      }));

      console.log('Portfolio data cached successfully');
    } catch (error) {
      console.error('Failed to cache portfolio data:', error);
    }
  }

  /**
   * Get cached portfolio data
   */
  static async getCachedPortfolioData(): Promise<OfflinePortfolioData | null> {
    if (!this.db) return null;

    try {
      // Get holdings from database
      const [result] = await this.db.executeSql('SELECT * FROM portfolio ORDER BY market_value DESC');
      const holdings = [];

      for (let i = 0; i < result.rows.length; i++) {
        holdings.push(result.rows.item(i));
      }

      // Get summary data
      const summaryData = await AsyncStorage.getItem('cachedPortfolioSummary');
      if (!summaryData) return null;

      const summary = JSON.parse(summaryData);

      return {
        holdings,
        totalValue: summary.totalValue,
        dayChange: summary.dayChange,
        dayChangePercent: summary.dayChangePercent,
        lastSync: summary.lastSync,
      };
    } catch (error) {
      console.error('Failed to get cached portfolio data:', error);
      return null;
    }
  }

  /**
   * Cache market data for offline access
   */
  static async cacheMarketData(marketData: OfflineMarketData[]): Promise<void> {
    if (!this.db) throw new Error('Database not initialized');

    try {
      for (const data of marketData) {
        await this.db.executeSql(
          `INSERT OR REPLACE INTO market_data 
           (symbol, price, change_amount, change_percent, volume, last_updated)
           VALUES (?, ?, ?, ?, ?, ?)`,
          [
            data.symbol,
            data.price,
            data.change,
            data.changePercent,
            data.volume,
            data.timestamp,
          ]
        );
      }

      console.log(`Cached market data for ${marketData.length} symbols`);
    } catch (error) {
      console.error('Failed to cache market data:', error);
    }
  }

  /**
   * Get cached market data for a symbol
   */
  static async getCachedMarketData(symbol: string): Promise<OfflineMarketData | null> {
    if (!this.db) return null;

    try {
      const [result] = await this.db.executeSql(
        'SELECT * FROM market_data WHERE symbol = ?',
        [symbol]
      );

      if (result.rows.length === 0) return null;

      const row = result.rows.item(0);
      return {
        symbol: row.symbol,
        price: row.price,
        change: row.change_amount,
        changePercent: row.change_percent,
        volume: row.volume,
        timestamp: row.last_updated,
      };
    } catch (error) {
      console.error('Failed to get cached market data:', error);
      return null;
    }
  }

  /**
   * Get all cached market data
   */
  static async getAllCachedMarketData(): Promise<OfflineMarketData[]> {
    if (!this.db) return [];

    try {
      const [result] = await this.db.executeSql('SELECT * FROM market_data ORDER BY symbol');
      const marketData: OfflineMarketData[] = [];

      for (let i = 0; i < result.rows.length; i++) {
        const row = result.rows.item(i);
        marketData.push({
          symbol: row.symbol,
          price: row.price,
          change: row.change_amount,
          changePercent: row.change_percent,
          volume: row.volume,
          timestamp: row.last_updated,
        });
      }

      return marketData;
    } catch (error) {
      console.error('Failed to get all cached market data:', error);
      return [];
    }
  }

  /**
   * Check if device is online
   */
  static async isOnline(): Promise<boolean> {
    const netInfo = await NetInfo.fetch();
    return netInfo.isConnected && netInfo.isInternetReachable;
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

      // Sync portfolio data
      await this.syncPortfolioData(authToken);

      // Sync market data for watchlist symbols
      await this.syncMarketDataForWatchlist(authToken);

      console.log('Data sync completed');
    } catch (error) {
      console.error('Failed to sync with server:', error);
    }
  }

  /**
   * Sync portfolio data with server
   */
  private static async syncPortfolioData(authToken: string): Promise<void> {
    try {
      const response = await fetch('https://api.yourplatform.com/api/portfolio/holdings', {
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const portfolioData = await response.json();
        await this.cachePortfolioData(portfolioData.data);
      }
    } catch (error) {
      console.error('Failed to sync portfolio data:', error);
    }
  }

  /**
   * Sync market data for watchlist symbols
   */
  private static async syncMarketDataForWatchlist(authToken: string): Promise<void> {
    if (!this.db) return;

    try {
      // Get watchlist symbols
      const [result] = await this.db.executeSql('SELECT symbol FROM watchlist');
      const symbols: string[] = [];

      for (let i = 0; i < result.rows.length; i++) {
        symbols.push(result.rows.item(i).symbol);
      }

      if (symbols.length === 0) return;

      // Fetch market data for symbols
      const response = await fetch('https://api.yourplatform.com/api/market-data/quotes', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ symbols }),
      });

      if (response.ok) {
        const marketData = await response.json();
        await this.cacheMarketData(marketData.data);
      }
    } catch (error) {
      console.error('Failed to sync market data:', error);
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
    if (!this.db) return;

    try {
      await this.db.executeSql('DELETE FROM portfolio');
      await this.db.executeSql('DELETE FROM market_data');
      await this.db.executeSql('DELETE FROM order_history');
      await AsyncStorage.removeItem('cachedPortfolioSummary');

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
    if (!this.db) return { portfolioItems: 0, marketDataItems: 0, lastSync: null };

    try {
      const [portfolioResult] = await this.db.executeSql('SELECT COUNT(*) as count FROM portfolio');
      const [marketResult] = await this.db.executeSql('SELECT COUNT(*) as count FROM market_data');
      
      const summaryData = await AsyncStorage.getItem('cachedPortfolioSummary');
      const lastSync = summaryData ? JSON.parse(summaryData).lastSync : null;

      return {
        portfolioItems: portfolioResult.rows.item(0).count,
        marketDataItems: marketResult.rows.item(0).count,
        lastSync,
      };
    } catch (error) {
      console.error('Failed to get cache stats:', error);
      return { portfolioItems: 0, marketDataItems: 0, lastSync: null };
    }
  }
}
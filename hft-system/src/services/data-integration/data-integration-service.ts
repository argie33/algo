import { BaseService, EarningsData, FinancialStatement, TechnicalIndicators } from '../../types';
import { Config } from '../../config';
import { Logger } from 'pino';
import { Pool, PoolClient } from 'pg';

export interface DataIntegrationConfig {
  refreshInterval: number;
  batchSize: number;
  cacheTimeout: number;
  maxRetries: number;
}

/**
 * Data Integration Service
 * Connects to existing fundamental data infrastructure and provides real-time access
 */
export class DataIntegrationService extends BaseService {
  private dbPool: Pool;
  private cache: Map<string, any> = new Map();
  private lastUpdate: Map<string, number> = new Map();
  
  private readonly integrationConfig: DataIntegrationConfig = {
    refreshInterval: 60000, // 1 minute
    batchSize: 100,
    cacheTimeout: 300000, // 5 minutes
    maxRetries: 3
  };

  constructor(config: Config, logger: Logger) {
    super('DataIntegrationService', config, logger);
    
    // Initialize database connection pool
    this.dbPool = new Pool({
      host: config.database.host,
      port: config.database.port,
      database: config.database.database,
      user: config.database.username,
      password: config.database.password,
      ssl: config.database.ssl,
      max: config.database.maxConnections,
      connectionTimeoutMillis: config.database.connectionTimeout,
      idleTimeoutMillis: 30000,
      query_timeout: 10000
    });
  }

  async initialize(): Promise<void> {
    this.logger.info('Initializing Data Integration Service...');
    
    try {
      // Test database connection
      const client = await this.dbPool.connect();
      await client.query('SELECT NOW()');
      client.release();
      
      this.logger.info('Database connection established');
      
      // Load initial data
      await this.loadFundamentalData();
      await this.loadTechnicalData();
      await this.loadEarningsData();
      
      this.logger.info('Data Integration Service initialized successfully');
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to initialize Data Integration Service');
      throw error;
    }
  }

  async start(): Promise<void> {
    if (this.isRunning) return;
    
    this.logger.info('Starting Data Integration Service...');
    this.isRunning = true;
    
    // Start periodic data refresh
    this.startDataRefresh();
    
    this.logger.info('Data Integration Service started successfully');
  }

  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.logger.info('Stopping Data Integration Service...');
    this.isRunning = false;
    
    // Close database connections
    await this.dbPool.end();
    
    this.logger.info('Data Integration Service stopped');
  }

  /**
   * Get fundamental data for a symbol
   */
  async getFundamentalData(symbol: string): Promise<FinancialStatement | null> {
    const cacheKey = `fundamental_${symbol}`;
    
    // Check cache first
    if (this.isCacheValid(cacheKey)) {
      return this.cache.get(cacheKey);
    }
    
    try {
      const query = `
        SELECT 
          symbol,
          fiscal_date_ending,
          reported_currency,
          total_revenue,
          cost_of_revenue,
          gross_profit,
          operating_income,
          net_income,
          total_assets,
          total_liabilities,
          shareholders_equity,
          operating_cash_flow,
          capital_expenditures,
          free_cash_flow
        FROM financial_statements 
        WHERE symbol = $1 
        ORDER BY fiscal_date_ending DESC 
        LIMIT 1
      `;
      
      const result = await this.dbPool.query(query, [symbol]);
      
      if (result.rows.length > 0) {
        const data = result.rows[0] as FinancialStatement;
        this.cache.set(cacheKey, data);
        this.lastUpdate.set(cacheKey, Date.now());
        return data;
      }
      
      return null;
      
    } catch (error) {
      this.logger.error({ error, symbol }, 'Failed to get fundamental data');
      return null;
    }
  }

  /**
   * Get technical indicators for a symbol
   */
  async getTechnicalIndicators(symbol: string): Promise<TechnicalIndicators | null> {
    const cacheKey = `technical_${symbol}`;
    
    // Check cache first
    if (this.isCacheValid(cacheKey)) {
      return this.cache.get(cacheKey);
    }
    
    try {
      const query = `
        SELECT 
          symbol,
          date,
          sma_20,
          sma_50,
          sma_200,
          ema_12,
          ema_26,
          rsi_14,
          macd,
          macd_signal,
          macd_histogram,
          bb_upper,
          bb_middle,
          bb_lower,
          volume,
          price
        FROM technicals_daily 
        WHERE symbol = $1 
        ORDER BY date DESC 
        LIMIT 1
      `;
      
      const result = await this.dbPool.query(query, [symbol]);
      
      if (result.rows.length > 0) {
        const data = result.rows[0] as TechnicalIndicators;
        this.cache.set(cacheKey, data);
        this.lastUpdate.set(cacheKey, Date.now());
        return data;
      }
      
      return null;
      
    } catch (error) {
      this.logger.error({ error, symbol }, 'Failed to get technical indicators');
      return null;
    }
  }

  /**
   * Get earnings data for a symbol
   */
  async getEarningsData(symbol: string): Promise<EarningsData | null> {
    const cacheKey = `earnings_${symbol}`;
    
    // Check cache first
    if (this.isCacheValid(cacheKey)) {
      return this.cache.get(cacheKey);
    }
    
    try {
      const query = `
        SELECT 
          symbol,
          fiscal_date_ending,
          reported_date,
          reported_eps,
          estimated_eps,
          surprise,
          surprise_percentage
        FROM earnings_data 
        WHERE symbol = $1 
        ORDER BY reported_date DESC 
        LIMIT 1
      `;
      
      const result = await this.dbPool.query(query, [symbol]);
      
      if (result.rows.length > 0) {
        const data = result.rows[0] as EarningsData;
        this.cache.set(cacheKey, data);
        this.lastUpdate.set(cacheKey, Date.now());
        return data;
      }
      
      return null;
      
    } catch (error) {
      this.logger.error({ error, symbol }, 'Failed to get earnings data');
      return null;
    }
  }

  /**
   * Get analyst recommendations for a symbol
   */
  async getAnalystRecommendations(symbol: string): Promise<any[] | null> {
    const cacheKey = `analyst_${symbol}`;
    
    // Check cache first
    if (this.isCacheValid(cacheKey)) {
      return this.cache.get(cacheKey);
    }
    
    try {
      const query = `
        SELECT 
          symbol,
          analyst_firm,
          recommendation,
          price_target,
          updated_date,
          previous_recommendation
        FROM analyst_recommendations 
        WHERE symbol = $1 
        ORDER BY updated_date DESC 
        LIMIT 10
      `;
      
      const result = await this.dbPool.query(query, [symbol]);
      
      if (result.rows.length > 0) {
        const data = result.rows;
        this.cache.set(cacheKey, data);
        this.lastUpdate.set(cacheKey, Date.now());
        return data;
      }
      
      return null;
      
    } catch (error) {
      this.logger.error({ error, symbol }, 'Failed to get analyst recommendations');
      return null;
    }
  }

  /**
   * Get price history for a symbol
   */
  async getPriceHistory(symbol: string, days: number = 30): Promise<any[] | null> {
    const cacheKey = `price_history_${symbol}_${days}`;
    
    // Check cache first
    if (this.isCacheValid(cacheKey)) {
      return this.cache.get(cacheKey);
    }
    
    try {
      const query = `
        SELECT 
          symbol,
          date,
          open,
          high,
          low,
          close,
          adjusted_close,
          volume
        FROM price_daily 
        WHERE symbol = $1 
        ORDER BY date DESC 
        LIMIT $2
      `;
      
      const result = await this.dbPool.query(query, [symbol, days]);
      
      if (result.rows.length > 0) {
        const data = result.rows;
        this.cache.set(cacheKey, data);
        this.lastUpdate.set(cacheKey, Date.now());
        return data;
      }
      
      return null;
      
    } catch (error) {
      this.logger.error({ error, symbol, days }, 'Failed to get price history');
      return null;
    }
  }

  /**
   * Get financial ratios for a symbol
   */
  async getFinancialRatios(symbol: string): Promise<any | null> {
    const cacheKey = `ratios_${symbol}`;
    
    // Check cache first
    if (this.isCacheValid(cacheKey)) {
      return this.cache.get(cacheKey);
    }
    
    try {
      // Calculate ratios from financial statements
      const fundamentals = await this.getFundamentalData(symbol);
      const priceData = await this.getPriceHistory(symbol, 1);
      
      if (!fundamentals || !priceData || priceData.length === 0) {
        return null;
      }
      
      const currentPrice = priceData[0].close;
      const marketCap = currentPrice * 1000000; // Simplified - would need shares outstanding
      
      const ratios = {
        symbol,
        pe_ratio: fundamentals.net_income > 0 ? marketCap / (fundamentals.net_income * 4) : null,
        price_to_book: fundamentals.shareholders_equity > 0 ? marketCap / fundamentals.shareholders_equity : null,
        debt_to_equity: fundamentals.shareholders_equity > 0 ? fundamentals.total_liabilities / fundamentals.shareholders_equity : null,
        current_ratio: null, // Would need current assets/liabilities breakdown
        roe: fundamentals.shareholders_equity > 0 ? fundamentals.net_income / fundamentals.shareholders_equity : null,
        roa: fundamentals.total_assets > 0 ? fundamentals.net_income / fundamentals.total_assets : null,
        gross_margin: fundamentals.total_revenue > 0 ? fundamentals.gross_profit / fundamentals.total_revenue : null,
        operating_margin: fundamentals.total_revenue > 0 ? fundamentals.operating_income / fundamentals.total_revenue : null,
        net_margin: fundamentals.total_revenue > 0 ? fundamentals.net_income / fundamentals.total_revenue : null,
        updated_at: Date.now()
      };
      
      this.cache.set(cacheKey, ratios);
      this.lastUpdate.set(cacheKey, Date.now());
      return ratios;
      
    } catch (error) {
      this.logger.error({ error, symbol }, 'Failed to calculate financial ratios');
      return null;
    }
  }

  /**
   * Get comprehensive symbol data (all data types combined)
   */
  async getSymbolData(symbol: string): Promise<any> {
    try {
      const [fundamentals, technicals, earnings, analysts, priceHistory, ratios] = await Promise.all([
        this.getFundamentalData(symbol),
        this.getTechnicalIndicators(symbol),
        this.getEarningsData(symbol),
        this.getAnalystRecommendations(symbol),
        this.getPriceHistory(symbol, 5),
        this.getFinancialRatios(symbol)
      ]);

      return {
        symbol,
        fundamentals,
        technicals,
        earnings,
        analysts,
        priceHistory,
        ratios,
        updated_at: Date.now()
      };
      
    } catch (error) {
      this.logger.error({ error, symbol }, 'Failed to get comprehensive symbol data');
      return null;
    }
  }

  /**
   * Load fundamental data for all symbols
   */
  private async loadFundamentalData(): Promise<void> {
    try {
      const symbols = this.config.getEnabledSymbols().map(s => s.symbol);
      
      for (const symbol of symbols) {
        await this.getFundamentalData(symbol);
      }
      
      this.logger.info({ count: symbols.length }, 'Fundamental data loaded');
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to load fundamental data');
    }
  }

  /**
   * Load technical data for all symbols
   */
  private async loadTechnicalData(): Promise<void> {
    try {
      const symbols = this.config.getEnabledSymbols().map(s => s.symbol);
      
      for (const symbol of symbols) {
        await this.getTechnicalIndicators(symbol);
      }
      
      this.logger.info({ count: symbols.length }, 'Technical data loaded');
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to load technical data');
    }
  }

  /**
   * Load earnings data for all symbols
   */
  private async loadEarningsData(): Promise<void> {
    try {
      const symbols = this.config.getEnabledSymbols().map(s => s.symbol);
      
      for (const symbol of symbols) {
        await this.getEarningsData(symbol);
      }
      
      this.logger.info({ count: symbols.length }, 'Earnings data loaded');
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to load earnings data');
    }
  }

  /**
   * Start periodic data refresh
   */
  private startDataRefresh(): void {
    setInterval(async () => {
      try {
        await this.refreshAllData();
      } catch (error) {
        this.logger.error({ error }, 'Failed to refresh data');
      }
    }, this.integrationConfig.refreshInterval);
  }

  /**
   * Refresh all cached data
   */
  private async refreshAllData(): Promise<void> {
    await Promise.all([
      this.loadFundamentalData(),
      this.loadTechnicalData(),
      this.loadEarningsData()
    ]);
    
    this.logger.debug('All data refreshed');
  }

  /**
   * Check if cache entry is valid
   */
  private isCacheValid(key: string): boolean {
    const lastUpdateTime = this.lastUpdate.get(key);
    if (!lastUpdateTime) return false;
    
    const age = Date.now() - lastUpdateTime;
    return age < this.integrationConfig.cacheTimeout;
  }

  /**
   * Clear cache entry
   */
  private clearCache(key: string): void {
    this.cache.delete(key);
    this.lastUpdate.delete(key);
  }

  /**
   * Clear all cache
   */
  clearAllCache(): void {
    this.cache.clear();
    this.lastUpdate.clear();
    this.logger.info('All cache cleared');
  }

  /**
   * Get cache statistics
   */
  getCacheStats(): any {
    return {
      cacheSize: this.cache.size,
      cacheKeys: Array.from(this.cache.keys()),
      oldestEntry: Math.min(...Array.from(this.lastUpdate.values())),
      newestEntry: Math.max(...Array.from(this.lastUpdate.values())),
      hitRate: 0 // Would need to track hits/misses
    };
  }

  /**
   * Execute custom query
   */
  async executeQuery(query: string, params: any[] = []): Promise<any[]> {
    try {
      const result = await this.dbPool.query(query, params);
      return result.rows;
    } catch (error) {
      this.logger.error({ error, query }, 'Failed to execute custom query');
      throw error;
    }
  }

  /**
   * Get database connection status
   */
  getDatabaseStatus(): any {
    return {
      totalConnections: this.dbPool.totalCount,
      idleConnections: this.dbPool.idleCount,
      waitingConnections: this.dbPool.waitingCount,
      connected: true
    };
  }
}

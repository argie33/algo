import { z } from 'zod';

// Validation schemas
const TradingSymbolSchema = z.object({
  symbol: z.string(),
  exchange: z.string(),
  assetClass: z.enum(['stock', 'etf', 'option', 'crypto']),
  enabled: z.boolean().default(true),
  maxPositionSize: z.number().positive(),
  tickSize: z.number().positive(),
  multiplier: z.number().positive().default(1)
});

const DatabaseConfigSchema = z.object({
  host: z.string(),
  port: z.number().int().positive(),
  database: z.string(),
  username: z.string(),
  password: z.string(),
  ssl: z.boolean().default(true),
  maxConnections: z.number().int().positive().default(20),
  connectionTimeout: z.number().int().positive().default(30000)
});

const RedisConfigSchema = z.object({
  host: z.string(),
  port: z.number().int().positive().default(6379),
  password: z.string().optional(),
  db: z.number().int().min(0).default(0),
  maxRetriesPerRequest: z.number().int().positive().default(3),
  retryDelayOnFailover: z.number().int().positive().default(100)
});

const AlpacaConfigSchema = z.object({
  keyId: z.string(),
  secretKey: z.string(),
  baseUrl: z.string().url(),
  dataUrl: z.string().url().optional(),
  paper: z.boolean().default(false)
});

const RiskLimitsSchema = z.object({
  maxPositionSize: z.number().positive(),
  maxPortfolioValue: z.number().positive(),
  maxDailyLoss: z.number().positive(),
  maxDrawdown: z.number().positive(),
  concentrationLimit: z.number().min(0).max(1),
  leverageLimit: z.number().positive(),
  maxOrderSize: z.number().positive()
});

const PerformanceTargetsSchema = z.object({
  maxLatencyMs: z.number().positive().default(20),
  maxOrderProcessingMs: z.number().positive().default(5),
  targetThroughput: z.number().positive().default(10000),
  targetUptime: z.number().min(0.99).max(1).default(0.9999)
});

const AnalyticsConfigSchema = z.object({
  enabled: z.boolean().default(true),
  realTimeAnalytics: z.boolean().default(true),
  historicalRetention: z.number().positive().default(30), // days
  performanceCalculationInterval: z.number().positive().default(5000), // ms
  riskCalculationInterval: z.number().positive().default(1000), // ms
  alertThresholds: z.object({
    maxDrawdown: z.number().positive().default(10000),
    maxDailyLoss: z.number().positive().default(5000),
    maxPositionSize: z.number().positive().default(100000),
    minSharpeRatio: z.number().default(0.5)
  })
});

const ConfigSchema = z.object({
  // Environment
  environment: z.enum(['development', 'staging', 'production']),
  logLevel: z.enum(['debug', 'info', 'warn', 'error']),
  
  // Trading
  symbols: z.array(TradingSymbolSchema),
  tradingHours: z.object({
    start: z.string(),
    end: z.string(),
    timezone: z.string().default('America/New_York')
  }),
  
  // External services
  alpaca: AlpacaConfigSchema,
  database: DatabaseConfigSchema,
  redis: RedisConfigSchema,
  
  // Risk management
  riskLimits: RiskLimitsSchema,
  
  // Performance targets
  performance: PerformanceTargetsSchema,
  
  // AWS configuration
  aws: z.object({
    region: z.string().default('us-east-1'),
    secretsManagerPrefix: z.string().default('hft-system'),
    cloudWatchNamespace: z.string().default('HFT-System')
  }),
  
  // Monitoring
  monitoring: z.object({
    healthCheckInterval: z.number().positive().default(5000),
    metricsInterval: z.number().positive().default(1000),
    alertThresholds: z.object({
      latencyMs: z.number().positive().default(50),
      errorRate: z.number().min(0).max(1).default(0.01),
      memoryUsage: z.number().min(0).max(1).default(0.8)
    })
  }),

  // Analytics configuration
  analytics: z.object({
    enabled: z.boolean().default(true),
    realTimeAnalytics: z.boolean().default(true),
    historicalRetention: z.number().positive().default(30), // days
    performanceCalculationInterval: z.number().positive().default(5000), // ms
    riskCalculationInterval: z.number().positive().default(1000), // ms
    alertThresholds: z.object({
      maxDrawdown: z.number().positive().default(10000),
      maxDailyLoss: z.number().positive().default(5000),
      maxPositionSize: z.number().positive().default(100000),
      minSharpeRatio: z.number().default(0.5)
    })
  })
});

export type TradingSymbol = z.infer<typeof TradingSymbolSchema>;
export type DatabaseConfig = z.infer<typeof DatabaseConfigSchema>;
export type RedisConfig = z.infer<typeof RedisConfigSchema>;
export type AlpacaConfig = z.infer<typeof AlpacaConfigSchema>;
export type RiskLimits = z.infer<typeof RiskLimitsSchema>;
export type PerformanceTargets = z.infer<typeof PerformanceTargetsSchema>;
export type ConfigType = z.infer<typeof ConfigSchema>;

/**
 * Configuration management class
 */
export class Config {
  private config: ConfigType;
  
  constructor() {
    this.config = this.loadConfig();
  }
  
  private loadConfig(): ConfigType {
    const config = {
      environment: process.env.NODE_ENV || 'development',
      logLevel: process.env.LOG_LEVEL || 'info',
      
      symbols: this.loadTradingSymbols(),
      
      tradingHours: {
        start: process.env.TRADING_START || '09:30',
        end: process.env.TRADING_END || '16:00',
        timezone: process.env.TRADING_TIMEZONE || 'America/New_York'
      },
      
      alpaca: {
        keyId: process.env.ALPACA_KEY_ID || '',
        secretKey: process.env.ALPACA_SECRET_KEY || '',
        baseUrl: process.env.ALPACA_BASE_URL || 'https://paper-api.alpaca.markets',
        dataUrl: process.env.ALPACA_DATA_URL || 'wss://stream.data.alpaca.markets/v2/iex',
        paper: process.env.ALPACA_PAPER === 'true'
      },
      
      database: {
        host: process.env.DB_HOST || 'localhost',
        port: parseInt(process.env.DB_PORT || '5432'),
        database: process.env.DB_NAME || 'hft_system',
        username: process.env.DB_USER || 'hft_user',
        password: process.env.DB_PASSWORD || '',
        ssl: process.env.DB_SSL === 'true',
        maxConnections: parseInt(process.env.DB_MAX_CONNECTIONS || '20'),
        connectionTimeout: parseInt(process.env.DB_CONNECTION_TIMEOUT || '30000')
      },
      
      redis: {
        host: process.env.REDIS_HOST || 'localhost',
        port: parseInt(process.env.REDIS_PORT || '6379'),
        password: process.env.REDIS_PASSWORD,
        db: parseInt(process.env.REDIS_DB || '0'),
        maxRetriesPerRequest: parseInt(process.env.REDIS_MAX_RETRIES || '3'),
        retryDelayOnFailover: parseInt(process.env.REDIS_RETRY_DELAY || '100')
      },
      
      riskLimits: {
        maxPositionSize: parseFloat(process.env.MAX_POSITION_SIZE || '100000'),
        maxPortfolioValue: parseFloat(process.env.MAX_PORTFOLIO_VALUE || '1000000'),
        maxDailyLoss: parseFloat(process.env.MAX_DAILY_LOSS || '10000'),
        maxDrawdown: parseFloat(process.env.MAX_DRAWDOWN || '0.05'),
        concentrationLimit: parseFloat(process.env.CONCENTRATION_LIMIT || '0.2'),
        leverageLimit: parseFloat(process.env.LEVERAGE_LIMIT || '2.0'),
        maxOrderSize: parseFloat(process.env.MAX_ORDER_SIZE || '10000')
      },
      
      performance: {
        maxLatencyMs: parseInt(process.env.MAX_LATENCY_MS || '20'),
        maxOrderProcessingMs: parseInt(process.env.MAX_ORDER_PROCESSING_MS || '5'),
        targetThroughput: parseInt(process.env.TARGET_THROUGHPUT || '10000'),
        targetUptime: parseFloat(process.env.TARGET_UPTIME || '0.9999')
      },
      
      aws: {
        region: process.env.AWS_REGION || 'us-east-1',
        secretsManagerPrefix: process.env.AWS_SECRETS_PREFIX || 'hft-system',
        cloudWatchNamespace: process.env.CLOUDWATCH_NAMESPACE || 'HFT-System'
      },
      
      monitoring: {
        healthCheckInterval: parseInt(process.env.HEALTH_CHECK_INTERVAL || '5000'),
        metricsInterval: parseInt(process.env.METRICS_INTERVAL || '1000'),
        alertThresholds: {
          latencyMs: parseInt(process.env.ALERT_LATENCY_MS || '50'),
          errorRate: parseFloat(process.env.ALERT_ERROR_RATE || '0.01'),
          memoryUsage: parseFloat(process.env.ALERT_MEMORY_USAGE || '0.8')
        }
      },

      analytics: {
        enabled: process.env.ANALYTICS_ENABLED === 'true',
        realTimeAnalytics: process.env.REAL_TIME_ANALYTICS === 'true',
        historicalRetention: parseInt(process.env.HISTORICAL_RETENTION_DAYS || '30'),
        performanceCalculationInterval: parseInt(process.env.PERFORMANCE_CALC_INTERVAL_MS || '5000'),
        riskCalculationInterval: parseInt(process.env.RISK_CALC_INTERVAL_MS || '1000'),
        alertThresholds: {
          maxDrawdown: parseFloat(process.env.ALERT_MAX_DRAWDOWN || '10000'),
          maxDailyLoss: parseFloat(process.env.ALERT_MAX_DAILY_LOSS || '5000'),
          maxPositionSize: parseFloat(process.env.ALERT_MAX_POSITION_SIZE || '100000'),
          minSharpeRatio: parseFloat(process.env.ALERT_MIN_SHARPE_RATIO || '0.5')
        }
      }
    };
    
    // Validate configuration
    const result = ConfigSchema.safeParse(config);
    if (!result.success) {
      throw new Error(`Invalid configuration: ${result.error.message}`);
    }
    
    return result.data;
  }
  
  private loadTradingSymbols(): TradingSymbol[] {
    // Default symbols for testing
    const defaultSymbols: TradingSymbol[] = [
      {
        symbol: 'SPY',
        exchange: 'ARCA',
        assetClass: 'etf',
        enabled: true,
        maxPositionSize: 50000,
        tickSize: 0.01,
        multiplier: 1
      },
      {
        symbol: 'QQQ',
        exchange: 'NASDAQ',
        assetClass: 'etf',
        enabled: true,
        maxPositionSize: 50000,
        tickSize: 0.01,
        multiplier: 1
      },
      {
        symbol: 'AAPL',
        exchange: 'NASDAQ',
        assetClass: 'stock',
        enabled: true,
        maxPositionSize: 30000,
        tickSize: 0.01,
        multiplier: 1
      },
      {
        symbol: 'TSLA',
        exchange: 'NASDAQ',
        assetClass: 'stock',
        enabled: true,
        maxPositionSize: 25000,
        tickSize: 0.01,
        multiplier: 1
      },
      {
        symbol: 'NVDA',
        exchange: 'NASDAQ',
        assetClass: 'stock',
        enabled: true,
        maxPositionSize: 25000,
        tickSize: 0.01,
        multiplier: 1
      }
    ];
    
    // TODO: Load from environment or external config
    const symbolsConfig = process.env.TRADING_SYMBOLS;
    if (symbolsConfig) {
      try {
        return JSON.parse(symbolsConfig);
      } catch (error) {
        console.warn('Failed to parse TRADING_SYMBOLS, using defaults');
      }
    }
    
    return defaultSymbols;
  }
  
  // Getters for configuration sections
  get environment(): string {
    return this.config.environment;
  }
  
  get logLevel(): string {
    return this.config.logLevel;
  }
  
  get symbols(): TradingSymbol[] {
    return this.config.symbols;
  }
  
  get alpaca(): AlpacaConfig {
    return this.config.alpaca;
  }
  
  get database(): DatabaseConfig {
    return this.config.database;
  }
  
  get redis(): RedisConfig {
    return this.config.redis;
  }
  
  get riskLimits(): RiskLimits {
    return this.config.riskLimits;
  }
  
  get performance(): PerformanceTargets {
    return this.config.performance;
  }
  
  get aws(): any {
    return this.config.aws;
  }
  
  get monitoring(): any {
    return this.config.monitoring;
  }
  
  get tradingHours(): any {
    return this.config.tradingHours;
  }
  
  get analytics(): any {
    return this.config.analytics;
  }
  
  /**
   * Check if currently in trading hours
   */
  isMarketOpen(): boolean {
    const now = new Date();
    const tz = this.config.tradingHours.timezone;
    
    // TODO: Implement proper market hours check with timezone support
    const hour = now.getHours();
    const minute = now.getMinutes();
    const currentTime = hour * 100 + minute;
    
    const [startHour, startMin] = this.config.tradingHours.start.split(':').map(Number);
    const [endHour, endMin] = this.config.tradingHours.end.split(':').map(Number);
    
    const startTime = startHour * 100 + startMin;
    const endTime = endHour * 100 + endMin;
    
    return currentTime >= startTime && currentTime <= endTime;
  }
  
  /**
   * Get configuration for a specific symbol
   */
  getSymbolConfig(symbol: string): TradingSymbol | undefined {
    return this.config.symbols.find(s => s.symbol === symbol);
  }
  
  /**
   * Get all enabled symbols
   */
  getEnabledSymbols(): TradingSymbol[] {
    return this.config.symbols.filter(s => s.enabled);
  }
}

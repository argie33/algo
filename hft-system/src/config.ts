import { Config } from './types';

export const config: Config = {
  alpaca: {
    keyId: process.env.ALPACA_KEY_ID || '',
    secretKey: process.env.ALPACA_SECRET_KEY || '',
    baseUrl: process.env.ALPACA_BASE_URL || 'https://paper-api.alpaca.markets',
    dataUrl: process.env.ALPACA_DATA_URL || 'wss://stream.data.alpaca.markets/v2/iex',
    paper: process.env.ALPACA_PAPER === 'true' || true
  },
  database: {
    host: process.env.DB_HOST || 'localhost',
    port: parseInt(process.env.DB_PORT || '5432'),
    database: process.env.DB_NAME || 'stocks',
    username: process.env.DB_USER || 'postgres',
    password: process.env.DB_PASSWORD || ''
  },
  redis: {
    host: process.env.REDIS_HOST || 'localhost',
    port: parseInt(process.env.REDIS_PORT || '6379'),
    password: process.env.REDIS_PASSWORD
  },
  trading: {
    symbols: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA'],
    maxPositionSize: 100000, // $100K per position
    maxPortfolioValue: 1000000, // $1M total
    riskLimits: {
      maxDrawdown: 0.05, // 5%
      maxLeverage: 2.0
    }
  },
  strategies: {
    momentum: {
      enabled: true,
      lookback: 20, // 20 periods
      threshold: 0.02 // 2% threshold
    },
    meanReversion: {
      enabled: true,
      lookback: 10,
      threshold: 0.015 // 1.5% threshold
    }
  }
};

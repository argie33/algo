/**
 * Database schema validation utility
 * Provides comprehensive validation for database operations and schema integrity
 */

const { query } = require("./database");
const logger = require("./logger");

/**
 * Schema definitions for database tables
 */
const tableSchemas = {
  stocks: {
    required: ["symbol", "name"],
    columns: {
      symbol: { type: "VARCHAR", maxLength: 10, unique: true },
      name: { type: "VARCHAR", maxLength: 200 },
      sector: { type: "VARCHAR", maxLength: 100 },
      industry: { type: "VARCHAR", maxLength: 100 },
      market_cap: { type: "BIGINT", min: 0 },
      price: { type: "DECIMAL", precision: 10, scale: 2, min: 0 },
      volume: { type: "BIGINT", min: 0 },
      pe_ratio: { type: "DECIMAL", precision: 8, scale: 2 },
      eps: { type: "DECIMAL", precision: 8, scale: 2 },
      dividend_yield: { type: "DECIMAL", precision: 5, scale: 4 },
      beta: { type: "DECIMAL", precision: 6, scale: 3 },
      exchange: { type: "VARCHAR", maxLength: 20 },
      country: { type: "VARCHAR", maxLength: 50 },
      currency: { type: "VARCHAR", maxLength: 3 },
      is_active: { type: "BOOLEAN", default: true },
      last_updated: { type: "TIMESTAMP" },
    },
  },

  stock_prices: {
    required: ["symbol", "date", "close"],
    columns: {
      symbol: { type: "VARCHAR", maxLength: 10 },
      date: { type: "DATE" },
      open: { type: "DECIMAL", precision: 10, scale: 2, min: 0 },
      high: { type: "DECIMAL", precision: 10, scale: 2, min: 0 },
      low: { type: "DECIMAL", precision: 10, scale: 2, min: 0 },
      close: { type: "DECIMAL", precision: 10, scale: 2, min: 0 },
      volume: { type: "BIGINT", min: 0 },
      adjusted_close: { type: "DECIMAL", precision: 10, scale: 2, min: 0 },
    },
    indexes: ["symbol", "date"],
    primaryKey: ["symbol", "date"],
  },

  watchlists: {
    required: ["user_id", "name"],
    columns: {
      id: { type: "SERIAL", primaryKey: true },
      user_id: { type: "VARCHAR", maxLength: 50 },
      name: { type: "VARCHAR", maxLength: 100 },
      description: { type: "TEXT" },
      is_public: { type: "BOOLEAN", default: false },
      created_at: { type: "TIMESTAMP", default: "NOW()" },
      updated_at: { type: "TIMESTAMP", default: "NOW()" },
    },
    indexes: ["user_id"],
  },

  watchlist_items: {
    required: ["watchlist_id", "symbol"],
    columns: {
      id: { type: "SERIAL", primaryKey: true },
      watchlist_id: { type: "INTEGER" },
      symbol: { type: "VARCHAR", maxLength: 10 },
      added_at: { type: "TIMESTAMP", default: "NOW()" },
      notes: { type: "TEXT" },
    },
    indexes: ["watchlist_id", "symbol"],
    foreignKeys: {
      watchlist_id: { table: "watchlists", column: "id" },
    },
  },

  technical_data_daily: {
    required: ["symbol", "date"],
    columns: {
      symbol: { type: "VARCHAR", maxLength: 50 },
      date: { type: "TIMESTAMP" },
      rsi: { type: "DOUBLE PRECISION" },
      macd: { type: "DOUBLE PRECISION" },
      macd_signal: { type: "DOUBLE PRECISION" },
      macd_hist: { type: "DOUBLE PRECISION" },
      mom: { type: "DOUBLE PRECISION" },
      roc: { type: "DOUBLE PRECISION" },
      adx: { type: "DOUBLE PRECISION" },
      plus_di: { type: "DOUBLE PRECISION" },
      minus_di: { type: "DOUBLE PRECISION" },
      atr: { type: "DOUBLE PRECISION" },
      ad: { type: "DOUBLE PRECISION" },
      cmf: { type: "DOUBLE PRECISION" },
      mfi: { type: "DOUBLE PRECISION" },
      td_sequential: { type: "DOUBLE PRECISION" },
      td_combo: { type: "DOUBLE PRECISION" },
      marketwatch: { type: "DOUBLE PRECISION" },
      dm: { type: "DOUBLE PRECISION" },
      sma_10: { type: "DOUBLE PRECISION" },
      sma_20: { type: "DOUBLE PRECISION" },
      sma_50: { type: "DOUBLE PRECISION" },
      sma_150: { type: "DOUBLE PRECISION" },
      sma_200: { type: "DOUBLE PRECISION" },
      ema_4: { type: "DOUBLE PRECISION" },
      ema_9: { type: "DOUBLE PRECISION" },
      ema_21: { type: "DOUBLE PRECISION" },
      bbands_lower: { type: "DOUBLE PRECISION" },
      bbands_middle: { type: "DOUBLE PRECISION" },
      bbands_upper: { type: "DOUBLE PRECISION" },
      pivot_high: { type: "DOUBLE PRECISION" },
      pivot_low: { type: "DOUBLE PRECISION" },
      pivot_high_triggered: { type: "DOUBLE PRECISION" },
      pivot_low_triggered: { type: "DOUBLE PRECISION" },
      fetched_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["symbol", "date"],
    primaryKey: ["symbol", "date"],
  },

  technical_data_weekly: {
    required: ["symbol", "date"],
    columns: {
      symbol: { type: "VARCHAR", maxLength: 50 },
      date: { type: "TIMESTAMP" },
      rsi: { type: "DOUBLE PRECISION" },
      macd: { type: "DOUBLE PRECISION" },
      macd_signal: { type: "DOUBLE PRECISION" },
      macd_hist: { type: "DOUBLE PRECISION" },
      mom: { type: "DOUBLE PRECISION" },
      roc: { type: "DOUBLE PRECISION" },
      adx: { type: "DOUBLE PRECISION" },
      plus_di: { type: "DOUBLE PRECISION" },
      minus_di: { type: "DOUBLE PRECISION" },
      atr: { type: "DOUBLE PRECISION" },
      ad: { type: "DOUBLE PRECISION" },
      cmf: { type: "DOUBLE PRECISION" },
      mfi: { type: "DOUBLE PRECISION" },
      td_sequential: { type: "DOUBLE PRECISION" },
      td_combo: { type: "DOUBLE PRECISION" },
      marketwatch: { type: "DOUBLE PRECISION" },
      dm: { type: "DOUBLE PRECISION" },
      sma_10: { type: "DOUBLE PRECISION" },
      sma_20: { type: "DOUBLE PRECISION" },
      sma_50: { type: "DOUBLE PRECISION" },
      sma_150: { type: "DOUBLE PRECISION" },
      sma_200: { type: "DOUBLE PRECISION" },
      ema_4: { type: "DOUBLE PRECISION" },
      ema_9: { type: "DOUBLE PRECISION" },
      ema_21: { type: "DOUBLE PRECISION" },
      bbands_lower: { type: "DOUBLE PRECISION" },
      bbands_middle: { type: "DOUBLE PRECISION" },
      bbands_upper: { type: "DOUBLE PRECISION" },
      pivot_high: { type: "DOUBLE PRECISION" },
      pivot_low: { type: "DOUBLE PRECISION" },
      pivot_high_triggered: { type: "DOUBLE PRECISION" },
      pivot_low_triggered: { type: "DOUBLE PRECISION" },
      fetched_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["symbol", "date"],
    primaryKey: ["symbol", "date"],
  },

  technical_data_monthly: {
    required: ["symbol", "date"],
    columns: {
      symbol: { type: "VARCHAR", maxLength: 50 },
      date: { type: "TIMESTAMP" },
      rsi: { type: "DOUBLE PRECISION" },
      macd: { type: "DOUBLE PRECISION" },
      macd_signal: { type: "DOUBLE PRECISION" },
      macd_hist: { type: "DOUBLE PRECISION" },
      mom: { type: "DOUBLE PRECISION" },
      roc: { type: "DOUBLE PRECISION" },
      adx: { type: "DOUBLE PRECISION" },
      plus_di: { type: "DOUBLE PRECISION" },
      minus_di: { type: "DOUBLE PRECISION" },
      atr: { type: "DOUBLE PRECISION" },
      ad: { type: "DOUBLE PRECISION" },
      cmf: { type: "DOUBLE PRECISION" },
      mfi: { type: "DOUBLE PRECISION" },
      td_sequential: { type: "DOUBLE PRECISION" },
      td_combo: { type: "DOUBLE PRECISION" },
      marketwatch: { type: "DOUBLE PRECISION" },
      dm: { type: "DOUBLE PRECISION" },
      sma_10: { type: "DOUBLE PRECISION" },
      sma_20: { type: "DOUBLE PRECISION" },
      sma_50: { type: "DOUBLE PRECISION" },
      sma_150: { type: "DOUBLE PRECISION" },
      sma_200: { type: "DOUBLE PRECISION" },
      ema_4: { type: "DOUBLE PRECISION" },
      ema_9: { type: "DOUBLE PRECISION" },
      ema_21: { type: "DOUBLE PRECISION" },
      bbands_lower: { type: "DOUBLE PRECISION" },
      bbands_middle: { type: "DOUBLE PRECISION" },
      bbands_upper: { type: "DOUBLE PRECISION" },
      pivot_high: { type: "DOUBLE PRECISION" },
      pivot_low: { type: "DOUBLE PRECISION" },
      pivot_high_triggered: { type: "DOUBLE PRECISION" },
      pivot_low_triggered: { type: "DOUBLE PRECISION" },
      fetched_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["symbol", "date"],
    primaryKey: ["symbol", "date"],
  },

  earnings_reports: {
    required: ["symbol", "report_date"],
    columns: {
      symbol: { type: "VARCHAR", maxLength: 10 },
      report_date: { type: "DATE" },
      quarter: { type: "INTEGER", min: 1, max: 4 },
      year: { type: "INTEGER", min: 1900 },
      revenue: { type: "BIGINT" },
      net_income: { type: "BIGINT" },
      eps_reported: { type: "DECIMAL", precision: 8, scale: 2 },
      eps_estimate: { type: "DECIMAL", precision: 8, scale: 2 },
      surprise_percent: { type: "DECIMAL", precision: 6, scale: 2 },
    },
    indexes: ["symbol", "report_date"],
    primaryKey: ["symbol", "report_date"],
  },


  price_daily: {
    required: ["symbol", "date"],
    columns: {
      id: { type: "SERIAL", primaryKey: true },
      symbol: { type: "VARCHAR", maxLength: 10 },
      date: { type: "DATE" },
      open: { type: "DOUBLE PRECISION" },
      high: { type: "DOUBLE PRECISION" },
      low: { type: "DOUBLE PRECISION" },
      close: { type: "DOUBLE PRECISION" },
      adj_close: { type: "DOUBLE PRECISION" },
      volume: { type: "BIGINT" },
      dividends: { type: "DOUBLE PRECISION" },
      stock_splits: { type: "DOUBLE PRECISION" },
      fetched_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["symbol", "date"],
    primaryKey: ["id"],
  },

  user_api_keys: {
    required: ["user_id", "broker_name", "encrypted_api_key"],
    columns: {
      user_id: { type: "VARCHAR", maxLength: 50 },
      broker_name: { type: "VARCHAR", maxLength: 50 },
      encrypted_api_key: { type: "TEXT" },
      encrypted_api_secret: { type: "TEXT" },
      key_iv: { type: "VARCHAR", maxLength: 32 },
      key_auth_tag: { type: "VARCHAR", maxLength: 32 },
      secret_iv: { type: "VARCHAR", maxLength: 32 },
      secret_auth_tag: { type: "VARCHAR", maxLength: 32 },
      is_sandbox: { type: "BOOLEAN", default: true },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
      updated_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
      last_used: { type: "TIMESTAMP" },
    },
    indexes: ["user_id", "broker_name"],
    primaryKey: ["user_id", "broker_name"],
  },

  portfolio_metadata: {
    required: ["user_id", "broker"],
    columns: {
      user_id: { type: "VARCHAR", maxLength: 50 },
      broker: { type: "VARCHAR", maxLength: 50 },
      total_value: { type: "DECIMAL", precision: 15, scale: 2, default: 0 },
      total_cash: { type: "DECIMAL", precision: 15, scale: 2, default: 0 },
      total_pnl: { type: "DECIMAL", precision: 15, scale: 2, default: 0 },
      total_pnl_percent: {
        type: "DECIMAL",
        precision: 10,
        scale: 4,
        default: 0,
      },
      day_pnl: { type: "DECIMAL", precision: 15, scale: 2, default: 0 },
      day_pnl_percent: { type: "DECIMAL", precision: 10, scale: 4, default: 0 },
      positions_count: { type: "INTEGER", default: 0 },
      buying_power: { type: "DECIMAL", precision: 15, scale: 2, default: 0 },
      account_status: { type: "VARCHAR", maxLength: 50, default: "active" },
      environment: { type: "VARCHAR", maxLength: 20, default: "live" },
      imported_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
      last_sync: { type: "TIMESTAMP" },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
      updated_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["user_id", "broker"],
    primaryKey: ["user_id", "broker"],
  },

  portfolio_holdings: {
    required: ["user_id", "symbol", "broker"],
    columns: {
      user_id: { type: "VARCHAR", maxLength: 50 },
      symbol: { type: "VARCHAR", maxLength: 20 },
      quantity: { type: "DECIMAL", precision: 15, scale: 6 },
      market_value: { type: "DECIMAL", precision: 15, scale: 2 },
      cost_basis: { type: "DECIMAL", precision: 15, scale: 2 },
      pnl: { type: "DECIMAL", precision: 15, scale: 2, default: 0 },
      pnl_percent: { type: "DECIMAL", precision: 10, scale: 4, default: 0 },
      weight: { type: "DECIMAL", precision: 10, scale: 4, default: 0 },
      sector: { type: "VARCHAR", maxLength: 100 },
      current_price: { type: "DECIMAL", precision: 12, scale: 4 },
      average_cost: { type: "DECIMAL", precision: 12, scale: 4 },
      day_change: { type: "DECIMAL", precision: 15, scale: 2, default: 0 },
      day_change_percent: {
        type: "DECIMAL",
        precision: 10,
        scale: 4,
        default: 0,
      },
      exchange: { type: "VARCHAR", maxLength: 50 },
      asset_class: { type: "VARCHAR", maxLength: 50, default: "equity" },
      broker: { type: "VARCHAR", maxLength: 50 },
      last_updated: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["user_id", "symbol", "broker"],
    primaryKey: ["user_id", "symbol", "broker"],
  },

  portfolio_performance: {
    required: ["user_id", "date", "broker"],
    columns: {
      user_id: { type: "VARCHAR", maxLength: 50 },
      date: { type: "DATE" },
      total_value: { type: "DECIMAL", precision: 15, scale: 2 },
      daily_pnl: { type: "DECIMAL", precision: 15, scale: 2, default: 0 },
      daily_pnl_percent: {
        type: "DECIMAL",
        precision: 10,
        scale: 4,
        default: 0,
      },
      total_pnl: { type: "DECIMAL", precision: 15, scale: 2, default: 0 },
      total_pnl_percent: {
        type: "DECIMAL",
        precision: 10,
        scale: 4,
        default: 0,
      },
      benchmark_return: {
        type: "DECIMAL",
        precision: 10,
        scale: 4,
        default: 0,
      },
      alpha: { type: "DECIMAL", precision: 10, scale: 4, default: 0 },
      beta: { type: "DECIMAL", precision: 10, scale: 4, default: 1 },
      sharpe_ratio: { type: "DECIMAL", precision: 10, scale: 4, default: 0 },
      max_drawdown: { type: "DECIMAL", precision: 10, scale: 4, default: 0 },
      volatility: { type: "DECIMAL", precision: 10, scale: 4, default: 0 },
      broker: { type: "VARCHAR", maxLength: 50 },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["user_id", "date", "broker"],
    primaryKey: ["user_id", "date", "broker"],
  },

  portfolio_transactions: {
    required: ["user_id", "symbol", "broker"],
    columns: {
      user_id: { type: "VARCHAR", maxLength: 50 },
      external_id: { type: "VARCHAR", maxLength: 100 },
      symbol: { type: "VARCHAR", maxLength: 20 },
      transaction_type: { type: "VARCHAR", maxLength: 50 },
      side: { type: "VARCHAR", maxLength: 10 },
      quantity: { type: "DECIMAL", precision: 15, scale: 6 },
      price: { type: "DECIMAL", precision: 12, scale: 4 },
      amount: { type: "DECIMAL", precision: 15, scale: 2 },
      transaction_date: { type: "TIMESTAMP" },
      description: { type: "TEXT" },
      broker: { type: "VARCHAR", maxLength: 50 },
      status: { type: "VARCHAR", maxLength: 20, default: "completed" },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
      updated_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["user_id", "symbol", "external_id"],
    primaryKey: ["user_id", "external_id", "broker"],
  },

  trading_alerts: {
    required: ["user_id", "symbol"],
    columns: {
      user_id: { type: "VARCHAR", maxLength: 50 },
      symbol: { type: "VARCHAR", maxLength: 20 },
      alert_type: { type: "VARCHAR", maxLength: 50 },
      condition_type: { type: "VARCHAR", maxLength: 20 },
      target_value: { type: "DECIMAL", precision: 12, scale: 4 },
      current_value: { type: "DECIMAL", precision: 12, scale: 4 },
      is_active: { type: "BOOLEAN", default: true },
      is_triggered: { type: "BOOLEAN", default: false },
      triggered_at: { type: "TIMESTAMP" },
      message: { type: "TEXT" },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
      updated_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["user_id", "symbol", "is_active"],
  },

  user_profiles: {
    required: ["user_id"],
    columns: {
      user_id: { type: "VARCHAR", maxLength: 255, primaryKey: true },
      onboarding_completed: { type: "BOOLEAN", default: false },
      preferences: { type: "JSONB", default: "'{}'" },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
      updated_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["user_id"],
  },

  // Core stock data tables
  stock_symbols: {
    required: ["symbol"],
    columns: {
      symbol: { type: "VARCHAR", maxLength: 10, primaryKey: true },
      name: { type: "VARCHAR", maxLength: 200 },
      exchange: { type: "VARCHAR", maxLength: 20 },
      type: { type: "VARCHAR", maxLength: 10 },
      sector: { type: "VARCHAR", maxLength: 100 },
      industry: { type: "VARCHAR", maxLength: 100 },
      currency: { type: "VARCHAR", maxLength: 3 },
      country: { type: "VARCHAR", maxLength: 50 },
      market_cap: { type: "BIGINT" },
      is_active: { type: "BOOLEAN", default: true },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
      updated_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["symbol", "exchange", "sector"],
  },

  market_data: {
    required: ["symbol"],
    columns: {
      symbol: { type: "VARCHAR", maxLength: 20 },
      name: { type: "VARCHAR", maxLength: 255 },
      date: { type: "DATE" },
      price: { type: "DECIMAL", precision: 12, scale: 4 },
      volume: { type: "BIGINT" },
      market_cap: { type: "BIGINT" },
      return_1d: { type: "DECIMAL", precision: 8, scale: 6 },
      return_5d: { type: "DECIMAL", precision: 8, scale: 6 },
      return_1m: { type: "DECIMAL", precision: 8, scale: 6 },
      return_3m: { type: "DECIMAL", precision: 8, scale: 6 },
      return_6m: { type: "DECIMAL", precision: 8, scale: 6 },
      return_1y: { type: "DECIMAL", precision: 8, scale: 6 },
      volatility_30d: { type: "DECIMAL", precision: 8, scale: 6 },
      volatility_90d: { type: "DECIMAL", precision: 8, scale: 6 },
      volatility_1y: { type: "DECIMAL", precision: 8, scale: 6 },
      fetched_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["symbol", "date"],
  },

  price_daily: {
    required: ["symbol", "date"],
    columns: {
      symbol: { type: "VARCHAR", maxLength: 10 },
      date: { type: "DATE" },
      open: { type: "DECIMAL", precision: 10, scale: 2 },
      high: { type: "DECIMAL", precision: 10, scale: 2 },
      low: { type: "DECIMAL", precision: 10, scale: 2 },
      close: { type: "DECIMAL", precision: 10, scale: 2 },
      volume: { type: "BIGINT" },
      adj_close: { type: "DECIMAL", precision: 10, scale: 2 },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["symbol", "date"],
    primaryKey: ["symbol", "date"],
  },

  company_profile: {
    required: ["ticker"],
    columns: {
      ticker: { type: "VARCHAR", maxLength: 10, primaryKey: true },
      name: { type: "VARCHAR", maxLength: 200 },
      sector: { type: "VARCHAR", maxLength: 100 },
      industry: { type: "VARCHAR", maxLength: 100 },
      country: { type: "VARCHAR", maxLength: 50 },
      exchange: { type: "VARCHAR", maxLength: 20 },
      currency: { type: "VARCHAR", maxLength: 3 },
      market_cap: { type: "BIGINT" },
      employees: { type: "INTEGER" },
      founded: { type: "INTEGER" },
      description: { type: "TEXT" },
      website: { type: "VARCHAR", maxLength: 200 },
      ceo: { type: "VARCHAR", maxLength: 100 },
      headquarters: { type: "VARCHAR", maxLength: 100 },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
      updated_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["ticker", "sector", "exchange"],
  },

  earnings_reports: {
    required: ["symbol", "report_date"],
    columns: {
      id: { type: "SERIAL", primaryKey: true },
      symbol: { type: "VARCHAR", maxLength: 10 },
      report_date: { type: "DATE" },
      period: { type: "VARCHAR", maxLength: 10 },
      eps_estimate: { type: "DECIMAL", precision: 8, scale: 2 },
      eps_reported: { type: "DECIMAL", precision: 8, scale: 2 },
      surprise_percent: { type: "DECIMAL", precision: 8, scale: 2 },
      revenue_estimate: { type: "BIGINT" },
      revenue_reported: { type: "BIGINT" },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["symbol", "report_date"],
  },

  fear_greed_index: {
    required: ["value"],
    columns: {
      id: { type: "SERIAL", primaryKey: true },
      value: { type: "INTEGER" },
      classification: { type: "VARCHAR", maxLength: 20 },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["created_at"],
  },

  aaii_sentiment: {
    required: ["bullish", "bearish", "neutral"],
    columns: {
      id: { type: "SERIAL", primaryKey: true },
      bullish: { type: "DECIMAL", precision: 5, scale: 2 },
      bearish: { type: "DECIMAL", precision: 5, scale: 2 },
      neutral: { type: "DECIMAL", precision: 5, scale: 2 },
      spread: { type: "DECIMAL", precision: 6, scale: 2 },
      date: { type: "DATE" },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["date", "created_at"],
  },

  naaim: {
    required: ["exposure"],
    columns: {
      id: { type: "SERIAL", primaryKey: true },
      exposure: { type: "DECIMAL", precision: 6, scale: 2 },
      date: { type: "DATE" },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["date", "created_at"],
  },

  economic_data: {
    required: ["indicator", "value"],
    columns: {
      id: { type: "SERIAL", primaryKey: true },
      indicator: { type: "VARCHAR", maxLength: 50 },
      value: { type: "DECIMAL", precision: 15, scale: 6 },
      date: { type: "DATE" },
      frequency: { type: "VARCHAR", maxLength: 20 },
      unit: { type: "VARCHAR", maxLength: 50 },
      source: { type: "VARCHAR", maxLength: 50 },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["indicator", "date"],
  },

  comprehensive_scores: {
    required: ["symbol"],
    columns: {
      id: { type: "SERIAL", primaryKey: true },
      symbol: { type: "VARCHAR", maxLength: 10 },
      calculation_date: { type: "DATE" },
      overall_score: { type: "DECIMAL", precision: 5, scale: 2 },
      growth_score: { type: "DECIMAL", precision: 5, scale: 2 },
      value_score: { type: "DECIMAL", precision: 5, scale: 2 },
      momentum_score: { type: "DECIMAL", precision: 5, scale: 2 },
      quality_score: { type: "DECIMAL", precision: 5, scale: 2 },
      profitability_score: { type: "DECIMAL", precision: 5, scale: 2 },
      financial_strength_score: { type: "DECIMAL", precision: 5, scale: 2 },
      data_completeness: { type: "DECIMAL", precision: 5, scale: 2 },
      created_at: { type: "TIMESTAMP", default: "CURRENT_TIMESTAMP" },
    },
    indexes: ["symbol", "calculation_date"],
  },
};

class SchemaValidator {
  constructor() {
    this.schemas = tableSchemas;
  }

  /**
   * Validate data against table schema
   */
  validateData(tableName, data) {
    const schema = this.schemas[tableName];
    if (!schema) {
      return {
        valid: false,
        isValid: false,
        errors: [`Unknown table schema: ${tableName}`],
        errorDetails: [],
        data: {},
      };
    }

    const errors = [];
    const validatedData = {};

    // Check required fields
    for (const requiredField of schema.required) {
      if (data[requiredField] === undefined || data[requiredField] === null) {
        errors.push({
          field: requiredField,
          message: `Required field "${requiredField}" is missing`,
          code: "REQUIRED_FIELD_MISSING",
        });
      }
    }

    // Validate each field
    for (const [fieldName, fieldValue] of Object.entries(data)) {
      const columnDef = schema.columns[fieldName];
      if (!columnDef) {
        errors.push({
          field: fieldName,
          message: `Unknown field "${fieldName}" for table "${tableName}"`,
          code: "UNKNOWN_FIELD",
        });
        continue;
      }

      const fieldErrors = this.validateField(fieldName, fieldValue, columnDef);
      errors.push(...fieldErrors);

      if (fieldErrors.length === 0) {
        validatedData[fieldName] = this.sanitizeFieldValue(
          fieldValue,
          columnDef
        );
      }
    }

    return {
      valid: errors.length === 0,
      isValid: errors.length === 0, // Add alias for backwards compatibility
      errors: errors.map(err => err.message), // Convert to string array for tests
      errorDetails: errors, // Keep detailed errors for advanced usage
      data: validatedData,
    };
  }

  /**
   * Validate individual field
   */
  validateField(fieldName, value, columnDef) {
    const errors = [];

    // Skip validation for null values unless required
    if (value === null || value === undefined) {
      return errors;
    }

    // Type validation
    switch (columnDef.type) {
      case "VARCHAR":
        if (typeof value !== "string") {
          errors.push({
            field: fieldName,
            message: `Field "${fieldName}" must be a string`,
            code: "INVALID_TYPE",
          });
        } else if (columnDef.maxLength && value.length > columnDef.maxLength) {
          errors.push({
            field: fieldName,
            message: `Field "${fieldName}" exceeds maximum length of ${columnDef.maxLength} characters`,
            code: "EXCEEDS_MAX_LENGTH",
          });
        }
        break;

      case "INTEGER":
      case "SERIAL":
        if (!Number.isInteger(Number(value))) {
          errors.push({
            field: fieldName,
            message: `Field "${fieldName}" must be an integer`,
            code: "INVALID_TYPE",
          });
        } else {
          const numValue = Number(value);
          if (columnDef.min !== undefined && numValue < columnDef.min) {
            errors.push({
              field: fieldName,
              message: `Field "${fieldName}" must be at least ${columnDef.min}`,
              code: "BELOW_MINIMUM",
            });
          }
          if (columnDef.max !== undefined && numValue > columnDef.max) {
            errors.push({
              field: fieldName,
              message: `Field "${fieldName}" must be at most ${columnDef.max}`,
              code: "ABOVE_MAXIMUM",
            });
          }
        }
        break;

      case "BIGINT":
        if (!Number.isInteger(Number(value))) {
          errors.push({
            field: fieldName,
            message: `Field "${fieldName}" must be a big integer`,
            code: "INVALID_TYPE",
          });
        } else if (
          columnDef.min !== undefined &&
          Number(value) < columnDef.min
        ) {
          errors.push({
            field: fieldName,
            message: `Field "${fieldName}" must be at least ${columnDef.min}`,
            code: "BELOW_MINIMUM",
          });
        }
        break;

      case "DECIMAL":
        if (isNaN(Number(value))) {
          errors.push({
            field: fieldName,
            message: `Field "${fieldName}" must be a number`,
            code: "INVALID_TYPE",
          });
        } else {
          const numValue = Number(value);
          if (columnDef.min !== undefined && numValue < columnDef.min) {
            errors.push({
              field: fieldName,
              message: `Field "${fieldName}" must be at least ${columnDef.min}`,
              code: "BELOW_MINIMUM",
            });
          }
          if (columnDef.max !== undefined && numValue > columnDef.max) {
            errors.push({
              field: fieldName,
              message: `Field "${fieldName}" must be at most ${columnDef.max}`,
              code: "ABOVE_MAXIMUM",
            });
          }
          
          // Check precision constraints
          if (columnDef.precision && columnDef.scale !== undefined) {
            const valueStr = String(value);
            const decimalParts = valueStr.split('.');
            const integerPart = decimalParts[0];
            const decimalPart = decimalParts[1] || '';
            
            const maxIntegerDigits = columnDef.precision - columnDef.scale;
            
            if (integerPart.length > maxIntegerDigits || decimalPart.length > columnDef.scale) {
              errors.push({
                field: fieldName,
                message: `Field "${fieldName}" exceeds precision constraints (${columnDef.precision},${columnDef.scale})`,
                code: "PRECISION_EXCEEDED",
              });
            }
          }
        }
        break;

      case "BOOLEAN":
        if (
          typeof value !== "boolean" &&
          value !== "true" &&
          value !== "false" &&
          value !== 1 &&
          value !== 0
        ) {
          errors.push({
            field: fieldName,
            message: `Field "${fieldName}" must be a boolean value`,
            code: "INVALID_TYPE",
          });
        }
        break;

      case "DATE":
        if (isNaN(Date.parse(value))) {
          errors.push({
            field: fieldName,
            message: `Field "${fieldName}" must be a valid date format`,
            code: "INVALID_DATE",
          });
        }
        break;

      case "TIMESTAMP":
        if (isNaN(Date.parse(value))) {
          errors.push({
            field: fieldName,
            message: `Field "${fieldName}" must be a valid timestamp`,
            code: "INVALID_TIMESTAMP",
          });
        }
        break;

      case "TEXT":
        if (typeof value !== "string") {
          errors.push({
            field: fieldName,
            message: `Field "${fieldName}" must be a string`,
            code: "INVALID_TYPE",
          });
        }
        break;
    }

    return errors;
  }

  /**
   * Sanitize field value according to column definition
   */
  sanitizeFieldValue(value, columnDef) {
    if (value === null || value === undefined) {
      return null;
    }

    switch (columnDef.type) {
      case "VARCHAR":
      case "TEXT":
        return String(value).trim();

      case "INTEGER":
      case "SERIAL":
      case "BIGINT":
        return Number(value);

      case "DECIMAL":
        return parseFloat(value);

      case "BOOLEAN":
        if (typeof value === "boolean") return value;
        if (value === "true" || value === 1) return true;
        if (value === "false" || value === 0) return false;
        return Boolean(value);

      case "DATE":
      case "TIMESTAMP":
        return new Date(value).toISOString();

      default:
        return value;
    }
  }

  /**
   * Validate table exists and has correct structure
   */
  async validateTableStructure(tableName) {
    try {
      const schema = this.schemas[tableName];
      if (!schema) {
        throw new Error(`No schema defined for table: ${tableName}`);
      }

      // Check if table exists
      const tableExists = await query(
        `
        SELECT EXISTS (
          SELECT FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name = $1
        )
      `,
        [tableName]
      );

      if (!tableExists.rows[0].exists) {
        return {
          valid: false,
          errors: [`Table '${tableName}' does not exist`],
        };
      }

      // Get actual table structure
      const columns = await query(
        `
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
      `,
        [tableName]
      );

      const actualColumns = new Set(columns.rows.map((col) => col.column_name));
      const expectedColumns = new Set(Object.keys(schema.columns));

      const errors = [];

      // Check for missing columns
      for (const expectedCol of expectedColumns) {
        if (!actualColumns.has(expectedCol)) {
          errors.push(
            `Missing column '${expectedCol}' in table '${tableName}'`
          );
        }
      }

      // Check for extra columns (warning only)
      for (const actualCol of actualColumns) {
        if (!expectedColumns.has(actualCol) && actualCol !== "id") {
          logger.warn(
            `Extra column '${actualCol}' found in table '${tableName}'`
          );
        }
      }

      return {
        valid: errors.length === 0,
        errors: errors,
        actualColumns: Array.from(actualColumns),
        expectedColumns: Array.from(expectedColumns),
      };
    } catch (error) {
      logger.error("Schema validation error", { error, tableName });
      return {
        valid: false,
        errors: [`Schema validation failed: ${error.message}`],
      };
    }
  }

  /**
   * Validate database integrity
   */
  async validateDatabaseIntegrity() {
    const results = {};
    const overallErrors = [];

    for (const tableName of Object.keys(this.schemas)) {
      try {
        const validation = await this.validateTableStructure(tableName);
        results[tableName] = validation;

        if (!validation.valid) {
          overallErrors.push(...validation.errors);
        }
      } catch (error) {
        results[tableName] = {
          valid: false,
          errors: [error.message],
        };
        overallErrors.push(`Table '${tableName}': ${error.message}`);
      }
    }

    return {
      valid: overallErrors.length === 0,
      errors: overallErrors,
      tableResults: results,
      checkedAt: new Date().toISOString(),
    };
  }

  /**
   * Generate CREATE TABLE statement from schema
   */
  generateCreateTableSQL(tableName) {
    const schema = this.schemas[tableName];
    if (!schema) {
      throw new Error(`Unknown table schema: ${tableName}`);
    }

    let sql = `CREATE TABLE IF NOT EXISTS ${tableName} (\n`;
    const columnDefinitions = [];

    for (const [columnName, columnDef] of Object.entries(schema.columns)) {
      let definition = `  ${columnName} ${columnDef.type}`;

      if (columnDef.type === "VARCHAR" && columnDef.maxLength) {
        definition += `(${columnDef.maxLength})`;
      }

      if (columnDef.type === "DECIMAL" && columnDef.precision) {
        definition += `(${columnDef.precision}${columnDef.scale ? "," + columnDef.scale : ""})`;
      }

      if (columnDef.unique) {
        definition += " UNIQUE";
      }

      if ((schema.required && schema.required.includes(columnName)) || (columnDef.nullable === false && columnDef.type !== "SERIAL")) {
        definition += " NOT NULL";
      }

      if (columnDef.primaryKey) {
        definition += " PRIMARY KEY";
      }

      if (columnDef.default !== undefined) {
        if (typeof columnDef.default === 'boolean') {
          definition += ` DEFAULT ${columnDef.default}`;
        } else {
          definition += ` DEFAULT ${columnDef.default}`;
        }
      }

      // Add CHECK constraints for min values
      if (columnDef.min !== undefined && (columnDef.type === "BIGINT" || columnDef.type === "DECIMAL" || columnDef.type === "INTEGER")) {
        definition += ` CHECK (${columnName} >= ${columnDef.min})`;
      }

      columnDefinitions.push(definition);
    }

    sql += columnDefinitions.join(",\n");

    // Add primary key constraint if defined
    if (schema.primaryKey && Array.isArray(schema.primaryKey)) {
      sql += `,\n  PRIMARY KEY (${schema.primaryKey.join(", ")})`;
    }

    sql += "\n);";

    // Add indexes
    if (schema.indexes) {
      for (const index of schema.indexes) {
        const indexColumns = Array.isArray(index) ? index.join(", ") : index;
        sql += `\n\nCREATE INDEX IF NOT EXISTS idx_${tableName}_${indexColumns.replace(/[^a-zA-Z0-9]/g, "_")} ON ${tableName} (${indexColumns});`;
      }
    }

    return sql;
  }

  /**
   * Get schema definition for a table
   */
  getTableSchema(tableName) {
    return this.schemas[tableName] || null;
  }

  /**
   * List all available table schemas
   */
  listTables() {
    return Object.keys(this.schemas);
  }

  /**
   * Sanitize input to prevent SQL injection and clean data
   */
  sanitizeInput(input) {
    if (input === null || input === undefined) {
      return input;
    }

    if (Array.isArray(input)) {
      return input.map(item => this.sanitizeInput(item));
    }

    if (typeof input === 'object') {
      const sanitized = {};
      for (const [key, value] of Object.entries(input)) {
        sanitized[key] = this.sanitizeInput(value);
      }
      return sanitized;
    }

    if (typeof input === 'string') {
      // Remove potential SQL injection attempts
      return input
        .trim()
        .replace(/['"`;\\]/g, '') // Remove quotes, semicolons, backslashes
        .replace(/--/g, '') // Remove SQL comment syntax
        .replace(/\b(DROP|DELETE|INSERT|UPDATE|SELECT|UNION|EXEC|EXECUTE)\b/gi, ''); // Remove SQL keywords
    }

    // Preserve numbers and booleans as-is
    return input;
  }

  /**
   * Map schema type to PostgreSQL data type
   */
  mapSchemaTypeToPostgresType(schemaType) {
    const typeMap = {
      'VARCHAR': 'character varying',
      'TEXT': 'text',
      'INTEGER': 'integer',
      'BIGINT': 'bigint',
      'DECIMAL': 'numeric',
      'BOOLEAN': 'boolean',
      'DATE': 'date',
      'TIMESTAMP': 'timestamp without time zone',
      'SERIAL': 'integer'
    };
    return typeMap[schemaType];
  }

  /**
   * Check if table exists in database
   */
  async validateTableExists(tableName) {
    try {
      const tableExists = await query(
        `SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = $1 AND table_name = $2)`,
        ["public", tableName]
      );
      return tableExists.rows[0].exists;
    } catch (error) {
      logger.error("Error validating table existence:", error);
      throw error;
    }
  }

  /**
   * Validate table columns against schema
   */
  async validateColumns(tableName) {
    const schema = this.schemas[tableName];
    if (!schema) {
      throw new Error(`Unknown table schema: ${tableName}`);
    }

    try {
      const columns = await query(
        `SELECT column_name, data_type, is_nullable, column_default
         FROM information_schema.columns 
         WHERE table_schema = 'public' AND table_name = $1`,
        [tableName]
      );

      const actualColumns = new Set(columns.rows.map((col) => col.column_name));
      const expectedColumns = new Set(Object.keys(schema.columns));
      const missingColumns = [];
      const extraColumns = [];
      const mismatchedTypes = [];

      // Check for missing columns
      for (const expectedCol of expectedColumns) {
        if (!actualColumns.has(expectedCol)) {
          missingColumns.push(expectedCol);
        }
      }

      // Check for extra columns (excluding common auto-generated columns)
      for (const actualCol of actualColumns) {
        if (!expectedColumns.has(actualCol) && 
            !['id', 'created_at', 'updated_at'].includes(actualCol)) {
          extraColumns.push(actualCol);
        }
      }

      // Check for type mismatches
      for (const column of columns.rows) {
        const expectedColumnDef = schema.columns[column.column_name];
        if (expectedColumnDef) {
          const expectedType = this.mapSchemaTypeToPostgresType(expectedColumnDef.type);
          if (expectedType && column.data_type !== expectedType) {
            mismatchedTypes.push({
              column: column.column_name,
              expected: expectedColumnDef.type,
              actual: column.data_type,
            });
          }
        }
      }

      return {
        valid: missingColumns.length === 0 && mismatchedTypes.length === 0,
        isValid: missingColumns.length === 0 && mismatchedTypes.length === 0,
        missingColumns,
        mismatchedTypes,
        extraColumns,
        actualColumns: Array.from(actualColumns),
        expectedColumns: Array.from(expectedColumns)
      };
    } catch (error) {
      logger.error(`Error validating columns for ${tableName}:`, error);
      throw error;
    }
  }

  /**
   * Validate table indexes
   */
  async validateIndexes(tableName) {
    const schema = this.schemas[tableName];
    if (!schema || !schema.indexes) {
      return { valid: true, missingIndexes: [], actualIndexes: [] };
    }

    try {
      const indexes = await query(
        `SELECT indexname FROM pg_indexes WHERE tablename = $1`,
        [tableName]
      );

      const actualIndexes = indexes.rows.map(row => row.indexname);
      const expectedIndexes = schema.indexes.map(index => 
        Array.isArray(index) ? `${tableName}_${index.join('_')}_idx` : `${tableName}_${index}_idx`
      );
      
      const missingIndexes = expectedIndexes.filter(expected => 
        !actualIndexes.some(actual => actual.includes(expected.replace(`${tableName}_`, '').replace('_idx', '')))
      );

      return {
        valid: missingIndexes.length === 0,
        isValid: missingIndexes.length === 0,
        missingIndexes,
        actualIndexes,
        expectedIndexes
      };
    } catch (error) {
      logger.error(`Error validating indexes for ${tableName}:`, error);
      throw error;
    }
  }

  /**
   * Safe query execution with database availability checking
   * Returns null gracefully when database is unavailable instead of throwing errors
   */
  async safeQuery(queryText, params = []) {
    try {
      const result = await query(queryText, params);
      return result;
    } catch (error) {
      logger.warn("Safe query failed, database may be unavailable", { 
        error: error.message, 
        queryText: queryText.substring(0, 100) + (queryText.length > 100 ? '...' : '')
      });
      // Return null when database is unavailable - caller should handle gracefully
      return null;
    }
  }
}

// Export singleton instance
const schemaValidator = new SchemaValidator();

module.exports = {
  validateData: (tableName, data) =>
    schemaValidator.validateData(tableName, data),
  validateTableStructure: (tableName) =>
    schemaValidator.validateTableStructure(tableName),
  validateDatabaseIntegrity: () => schemaValidator.validateDatabaseIntegrity(),
  generateCreateTableSQL: (tableName) =>
    schemaValidator.generateCreateTableSQL(tableName),
  getTableSchema: (tableName) => schemaValidator.getTableSchema(tableName),
  listTables: () => schemaValidator.listTables(),
  sanitizeInput: (input) => schemaValidator.sanitizeInput(input),
  validateTableExists: (tableName) => schemaValidator.validateTableExists(tableName),
  validateColumns: (tableName) => schemaValidator.validateColumns(tableName),
  validateIndexes: (tableName) => schemaValidator.validateIndexes(tableName),
  safeQuery: (queryText, params) => schemaValidator.safeQuery(queryText, params),
  schemas: tableSchemas,
};

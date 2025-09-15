const {
  SecretsManagerClient,
  GetSecretValueCommand,
} = require("@aws-sdk/client-secrets-manager");
const { Pool } = require("pg");

// Configure AWS SDK v3
const secretsManager = new SecretsManagerClient({
  region:
    process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || "us-east-1",
});

// Connection pool instance
let pool = null;
let dbInitialized = false;
let initPromise = null;

// Database configuration cache
let dbConfig = null;

// Simple query result cache for performance optimization
const queryCache = new Map();
const CACHE_TTL = 30000; // 30 seconds TTL for frequently accessed data

// SSL Configuration Fix Applied - v2.2.0
// Fixed SSL configuration to match working ECS patterns with DB_SSL environment variable support

/**
 * Get database configuration from AWS Secrets Manager or environment variables
 */
async function getDbConfig() {
  if (dbConfig) {
    return dbConfig;
  }

  try {
    const secretArn = process.env.DB_SECRET_ARN;

    // If we have a secret ARN, use Secrets Manager
    if (secretArn) {
      try {
        console.log("Getting DB credentials from Secrets Manager...");
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        const result = await secretsManager.send(command);

        console.log(
          "Secrets Manager response type:",
          typeof result.SecretString
        );
        console.log(
          "Secrets Manager response preview:",
          result.SecretString?.substring(0, 100)
        );
        console.log(
          "First 5 characters:",
          JSON.stringify(result.SecretString?.substring(0, 5))
        );
        console.log("Is string?", typeof result.SecretString === "string");
        console.log("Full SecretString:", result.SecretString);

        let secret;

        // Enhanced debugging and parsing logic
        console.log("=== SECRET DEBUGGING ===");
        console.log("result keys:", Object.keys(result));
        console.log("result.SecretString exists:", "SecretString" in result);
        console.log("result.SecretBinary exists:", "SecretBinary" in result);

        // Check if SecretString is already an object (parsed by AWS SDK)
        if (
          typeof result.SecretString === "object" &&
          result.SecretString !== null
        ) {
          console.log("SecretString is already an object, using directly");
          secret = result.SecretString;
        } else if (typeof result.SecretString === "string") {
          console.log("SecretString is a string, attempting to parse");
          try {
            secret = JSON.parse(result.SecretString);
            console.log("Successfully parsed SecretString as JSON");
          } catch (parseError) {
            console.error("Failed to parse SecretString as JSON:", parseError);
            console.error("Raw SecretString type:", typeof result.SecretString);
            console.error(
              "Raw SecretString length:",
              result.SecretString?.length
            );
            console.error(
              "Raw SecretString (escaped):",
              JSON.stringify(result.SecretString)
            );

            // Try to identify the issue more specifically
            if (
              result.SecretString.startsWith("o") ||
              result.SecretString.startsWith("[o")
            ) {
              console.error(
                'SecretString appears to start with "o" which might indicate an object literal'
              );
              console.error(
                "This suggests the secret might be malformed or contain JavaScript object syntax instead of JSON"
              );
            }

            throw new Error(
              `Secret parsing failed: ${parseError.message}. Raw value type: ${typeof result.SecretString}, length: ${result.SecretString?.length}`
            );
          }
        } else if (result.SecretString === undefined && result.SecretBinary) {
          console.log(
            "SecretString is undefined but SecretBinary exists, trying to decode"
          );
          try {
            const decoded = Buffer.from(result.SecretBinary, "base64").toString(
              "utf-8"
            );
            console.log("Decoded SecretBinary:", decoded);
            secret = JSON.parse(decoded);
          } catch (decodeError) {
            console.error("Failed to decode SecretBinary:", decodeError);
            throw new Error(
              `Secret binary decoding failed: ${decodeError.message}`
            );
          }
        } else {
          console.error("Unexpected secret format:", {
            secretStringType: typeof result.SecretString,
            secretStringValue: result.SecretString,
            secretBinaryExists: !!result.SecretBinary,
          });
          throw new Error(
            `Unexpected SecretString type: ${typeof result.SecretString}`
          );
        }

        dbConfig = {
          host: secret.host || process.env.DB_ENDPOINT,
          port: parseInt(secret.port) || 5432,
          user: secret.username,
          password: secret.password,
          database: secret.dbname,
          max: parseInt(process.env.DB_POOL_MAX) || 5,
          idleTimeoutMillis:
            parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
          connectionTimeoutMillis:
            parseInt(process.env.DB_CONNECT_TIMEOUT) || 10000,
          ssl:
            process.env.DB_SSL === "false"
              ? false
              : {
                  rejectUnauthorized: false,
                },
        };

        console.log(
          `Database config loaded from Secrets Manager: ${dbConfig.host}:${dbConfig.port}/${dbConfig.database}`
        );
        return dbConfig;
      } catch (secretError) {
        console.warn(
          "Failed to get secrets from Secrets Manager, falling back to environment variables:",
          secretError.message
        );
      }
    }

    // Fallback to environment variables if available
    if (process.env.DB_HOST || process.env.DB_ENDPOINT) {
      console.log("Using database config from environment variables");

      const host = process.env.DB_HOST || process.env.DB_ENDPOINT;
      const user = process.env.DB_USER || process.env.DB_USERNAME || "postgres";
      const database =
        process.env.DB_NAME || process.env.DB_DATABASE || "postgres";

      if (!host) {
        throw new Error("DB_HOST is required when using environment variables");
      }

      dbConfig = {
        host,
        port: parseInt(process.env.DB_PORT) || 5432,
        user,
        password: process.env.DB_PASSWORD,
        database,
        // Optimized connection pool settings based on testing insights
        max: parseInt(process.env.DB_POOL_MAX) || 10, // Increased from 5 for better concurrency
        min: parseInt(process.env.DB_POOL_MIN) || 2, // Maintain minimum connections
        idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
        connectionTimeoutMillis:
          parseInt(process.env.DB_CONNECT_TIMEOUT) || 5000, // Reduced from 10s for faster failures
        acquireTimeoutMillis: parseInt(process.env.DB_ACQUIRE_TIMEOUT) || 5000, // Prevent hanging requests
        createTimeoutMillis: parseInt(process.env.DB_CREATE_TIMEOUT) || 5000, // Connection creation timeout
        reapIntervalMillis: parseInt(process.env.DB_REAP_INTERVAL) || 1000, // Pool maintenance interval
        createRetryIntervalMillis:
          parseInt(process.env.DB_RETRY_INTERVAL) || 200, // Retry interval on failure
        ssl:
          process.env.DB_SSL === "false"
            ? false
            : {
                rejectUnauthorized: false,
              },
      };

      console.log(
        `Database config loaded from environment: ${dbConfig.host}:${dbConfig.port}/${dbConfig.database}`
      );
      return dbConfig;
    }

    // If no configuration is available, return null to indicate no database
    console.warn(
      "No database configuration found. Set DB_SECRET_ARN or DB_HOST environment variables."
    );
    return null;
  } catch (error) {
    console.error("Error getting DB config:", error);
    return null;
  }
}

/**
 * Initialize database connection pool
 */
async function initializeDatabase() {
  if (initPromise) return initPromise;
  if (dbInitialized && pool) return pool;

  initPromise = (async () => {
    let config = null;
    try {
      console.log("Initializing database connection pool...");
      config = await getDbConfig();

      if (!config) {
        const error = new Error(
          "Database configuration missing. Please set DB environment variables or DB_SECRET_ARN."
        );
        console.warn(
          "No database configuration available. API will run in fallback mode with mock data."
        );
        dbInitialized = false;
        pool = null;
        throw error;
      }

      pool = new Pool(config);
      const client = await pool.connect();
      await client.query("SELECT NOW()");
      client.release();
      dbInitialized = true;
      console.log("✅ Database connection pool initialized successfully");

      // Initialize database schema if needed
      await initializeSchema();

      pool.on("error", (err) => {
        console.error("Database pool error:", err);
        dbInitialized = false;
      });
      return pool;
    } catch (error) {
      dbInitialized = false;
      pool = null;
      // Attach config and env info to the error for debugging
      if (typeof config === "undefined") config = null;
      error.config = config;
      error.env = {
        DB_SECRET_ARN: process.env.DB_SECRET_ARN,
        DB_ENDPOINT: process.env.DB_ENDPOINT,
        DB_HOST: process.env.DB_HOST,
        DB_PORT: process.env.DB_PORT,
        DB_NAME: process.env.DB_NAME,
        DB_USER: process.env.DB_USER,
      };
      console.warn(
        "Database initialization failed. API will run in fallback mode:",
        {
          error: error.message,
          config: config,
          env: error.env,
        }
      );
      return null; // Return null instead of throwing error
    } finally {
      initPromise = null;
    }
  })();

  return initPromise;
}

/**
 * Initialize database schema by creating missing tables
 */
async function initializeSchema() {
  try {
    console.log("Initializing database schema...");

    // Create essential tables matching exactly your Python loader structures
    const tables = [
      {
        name: "stock_symbols",
        sql: `CREATE TABLE IF NOT EXISTS stock_symbols (
          symbol            VARCHAR(50),
          exchange          VARCHAR(100),
          security_name     TEXT,
          cqs_symbol        VARCHAR(50),
          market_category   VARCHAR(50),
          test_issue        CHAR(1),
          financial_status  VARCHAR(50),
          round_lot_size    INT,
          etf               CHAR(1),
          secondary_symbol  VARCHAR(50)
        )`,
      },
      {
        name: "company_profile",
        sql: `CREATE TABLE IF NOT EXISTS company_profile (
          symbol VARCHAR(10) UNIQUE NOT NULL,
          name VARCHAR(200),
          sector VARCHAR(100),
          industry VARCHAR(100),
          market_cap BIGINT,
          description TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )`,
      },
      {
        name: "technical_data_daily",
        sql: `CREATE TABLE IF NOT EXISTS technical_data_daily (
          symbol          VARCHAR(50),
          date            TIMESTAMP,
          rsi             DOUBLE PRECISION,
          macd            DOUBLE PRECISION,
          macd_signal     DOUBLE PRECISION,
          macd_hist       DOUBLE PRECISION,
          mom             DOUBLE PRECISION,
          roc             DOUBLE PRECISION,
          adx             DOUBLE PRECISION,
          plus_di         DOUBLE PRECISION,
          minus_di        DOUBLE PRECISION,
          atr             DOUBLE PRECISION,
          ad              DOUBLE PRECISION,
          cmf             DOUBLE PRECISION,
          mfi             DOUBLE PRECISION,
          td_sequential   DOUBLE PRECISION,
          td_combo        DOUBLE PRECISION,
          marketwatch     DOUBLE PRECISION,
          dm              DOUBLE PRECISION,
          sma_10          DOUBLE PRECISION,
          sma_20          DOUBLE PRECISION,
          sma_50          DOUBLE PRECISION,
          sma_150         DOUBLE PRECISION,
          sma_200         DOUBLE PRECISION,
          ema_4           DOUBLE PRECISION,
          ema_9           DOUBLE PRECISION,
          ema_21          DOUBLE PRECISION,
          bbands_lower    DOUBLE PRECISION,
          bbands_middle   DOUBLE PRECISION,
          bbands_upper    DOUBLE PRECISION,
          bb_lower        DOUBLE PRECISION,
          bb_upper        DOUBLE PRECISION,
          pivot_high      DOUBLE PRECISION,
          pivot_low       DOUBLE PRECISION,
          pivot_high_triggered DOUBLE PRECISION,
          pivot_low_triggered DOUBLE PRECISION,
          fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (symbol, date)
        )`,
      },
      {
        name: "technical_data_weekly",
        sql: `CREATE TABLE IF NOT EXISTS technical_data_weekly (
          symbol          VARCHAR(50),
          date            TIMESTAMP,
          rsi             DOUBLE PRECISION,
          macd            DOUBLE PRECISION,
          macd_signal     DOUBLE PRECISION,
          macd_hist       DOUBLE PRECISION,
          mom             DOUBLE PRECISION,
          roc             DOUBLE PRECISION,
          adx             DOUBLE PRECISION,
          plus_di         DOUBLE PRECISION,
          minus_di        DOUBLE PRECISION,
          atr             DOUBLE PRECISION,
          ad              DOUBLE PRECISION,
          cmf             DOUBLE PRECISION,
          mfi             DOUBLE PRECISION,
          td_sequential   DOUBLE PRECISION,
          td_combo        DOUBLE PRECISION,
          marketwatch     DOUBLE PRECISION,
          dm              DOUBLE PRECISION,
          sma_10          DOUBLE PRECISION,
          sma_20          DOUBLE PRECISION,
          sma_50          DOUBLE PRECISION,
          sma_150         DOUBLE PRECISION,
          sma_200         DOUBLE PRECISION,
          ema_4           DOUBLE PRECISION,
          ema_9           DOUBLE PRECISION,
          ema_21          DOUBLE PRECISION,
          bbands_lower    DOUBLE PRECISION,
          bbands_middle   DOUBLE PRECISION,
          bbands_upper    DOUBLE PRECISION,
          pivot_high      DOUBLE PRECISION,
          pivot_low       DOUBLE PRECISION,
          pivot_high_triggered DOUBLE PRECISION,
          pivot_low_triggered DOUBLE PRECISION,
          fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (symbol, date)
        )`,
      },
      {
        name: "technical_data_monthly",
        sql: `CREATE TABLE IF NOT EXISTS technical_data_monthly (
          symbol          VARCHAR(50),
          date            TIMESTAMP,
          rsi             DOUBLE PRECISION,
          macd            DOUBLE PRECISION,
          macd_signal     DOUBLE PRECISION,
          macd_hist       DOUBLE PRECISION,
          mom             DOUBLE PRECISION,
          roc             DOUBLE PRECISION,
          adx             DOUBLE PRECISION,
          plus_di         DOUBLE PRECISION,
          minus_di        DOUBLE PRECISION,
          atr             DOUBLE PRECISION,
          ad              DOUBLE PRECISION,
          cmf             DOUBLE PRECISION,
          mfi             DOUBLE PRECISION,
          td_sequential   DOUBLE PRECISION,
          td_combo        DOUBLE PRECISION,
          marketwatch     DOUBLE PRECISION,
          dm              DOUBLE PRECISION,
          sma_10          DOUBLE PRECISION,
          sma_20          DOUBLE PRECISION,
          sma_50          DOUBLE PRECISION,
          sma_150         DOUBLE PRECISION,
          sma_200         DOUBLE PRECISION,
          ema_4           DOUBLE PRECISION,
          ema_9           DOUBLE PRECISION,
          ema_21          DOUBLE PRECISION,
          bbands_lower    DOUBLE PRECISION,
          bbands_middle   DOUBLE PRECISION,
          bbands_upper    DOUBLE PRECISION,
          pivot_high      DOUBLE PRECISION,
          pivot_low       DOUBLE PRECISION,
          pivot_high_triggered DOUBLE PRECISION,
          pivot_low_triggered DOUBLE PRECISION,
          fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (symbol, date)
        )`,
      },
      {
        name: "stocks",
        sql: `CREATE TABLE IF NOT EXISTS stocks (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(10) NOT NULL UNIQUE,
          name VARCHAR(255),
          sector VARCHAR(100),
          industry VARCHAR(100),
          market_cap NUMERIC,
          price NUMERIC,
          dividend_yield NUMERIC,
          beta NUMERIC,
          exchange VARCHAR(50),
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )`,
      },
      {
        name: "price_daily",
        sql: `CREATE TABLE IF NOT EXISTS price_daily (
          symbol VARCHAR(10) NOT NULL,
          date DATE NOT NULL,
          open_price DECIMAL(10,4),
          high_price DECIMAL(10,4),
          low_price DECIMAL(10,4),
          close DECIMAL(10,4),
          volume BIGINT,
          change_percent DECIMAL(8,4),
          dividends DECIMAL(8,4) DEFAULT 0,
          splits DECIMAL(8,4) DEFAULT 0,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (symbol, date)
        )`,
      },
      {
        name: "portfolio_holdings",
        sql: `CREATE TABLE IF NOT EXISTS portfolio_holdings (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          symbol VARCHAR(10) NOT NULL,
          quantity NUMERIC NOT NULL DEFAULT 0,
          average_cost NUMERIC NOT NULL DEFAULT 0,
          current_price NUMERIC DEFAULT 0,
          total_value NUMERIC DEFAULT 0,
          unrealized_pnl NUMERIC DEFAULT 0,
          realized_pnl NUMERIC DEFAULT 0,
          position_type VARCHAR(20) DEFAULT 'long',
          position_status VARCHAR(20) DEFAULT 'open',
          sector VARCHAR(50),
          last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(user_id, symbol)
        )`,
      },
      {
        name: "portfolio_performance",
        sql: `CREATE TABLE IF NOT EXISTS portfolio_performance (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          date DATE NOT NULL,
          total_value NUMERIC NOT NULL DEFAULT 0,
          daily_pnl NUMERIC DEFAULT 0,
          total_pnl NUMERIC DEFAULT 0,
          total_pnl_percent NUMERIC DEFAULT 0,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(user_id, date)
        )`,
      },
      {
        name: "buy_sell_daily",
        sql: `CREATE TABLE IF NOT EXISTS buy_sell_daily (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(10) NOT NULL,
          date DATE NOT NULL,
          signal VARCHAR(10),
          price NUMERIC,
          position_value NUMERIC DEFAULT 0,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(symbol, date)
        )`,
      },
      {
        name: "buy_sell_weekly",
        sql: `CREATE TABLE IF NOT EXISTS buy_sell_weekly (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(10) NOT NULL,
          date DATE NOT NULL,
          signal VARCHAR(10),
          price NUMERIC,
          position_value NUMERIC DEFAULT 0,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(symbol, date)
        )`,
      },
      {
        name: "buy_sell_monthly",
        sql: `CREATE TABLE IF NOT EXISTS buy_sell_monthly (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(10) NOT NULL,
          date DATE NOT NULL,
          signal VARCHAR(10),
          price NUMERIC,
          position_value NUMERIC DEFAULT 0,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(symbol, date)
        )`,
      },
      {
        name: "portfolio_transactions",
        sql: `CREATE TABLE IF NOT EXISTS portfolio_transactions (
          transaction_id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          symbol VARCHAR(10) NOT NULL,
          transaction_type VARCHAR(20) NOT NULL, -- 'BUY', 'SELL', 'DIVIDEND', etc.
          quantity NUMERIC NOT NULL,
          price NUMERIC NOT NULL,
          amount NUMERIC NOT NULL, -- total transaction amount
          commission NUMERIC DEFAULT 0,
          transaction_date DATE NOT NULL,
          settlement_date DATE,
          description TEXT,
          account_id VARCHAR(100),
          broker VARCHAR(50),
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )`,
      },
      {
        name: "technical_indicators",
        sql: `CREATE TABLE IF NOT EXISTS technical_indicators (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(10) NOT NULL,
          date DATE NOT NULL,
          historical_volatility_20d DOUBLE PRECISION,
          historical_volatility_60d DOUBLE PRECISION,
          beta DOUBLE PRECISION,
          correlation_spy DOUBLE PRECISION,
          volume_avg_20d BIGINT,
          price_52w_high DOUBLE PRECISION,
          price_52w_low DOUBLE PRECISION,
          rsi_14 DOUBLE PRECISION,
          macd DOUBLE PRECISION,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(symbol, date)
        )`,
      },
      {
        name: "market_sentiment",
        sql: `CREATE TABLE IF NOT EXISTS market_sentiment (
          id SERIAL PRIMARY KEY,
          value DOUBLE PRECISION NOT NULL,
          classification VARCHAR(50) NOT NULL,
          data_source VARCHAR(100),
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )`,
      },
      {
        name: "price_alerts",
        sql: `CREATE TABLE IF NOT EXISTS price_alerts (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          symbol VARCHAR(10) NOT NULL,
          alert_type VARCHAR(50) NOT NULL,
          condition_type VARCHAR(50) NOT NULL,
          condition VARCHAR(50) NOT NULL DEFAULT 'above',
          threshold_value DECIMAL(12,4) NOT NULL,
          target_price DECIMAL(12,4),
          current_value DECIMAL(12,4),
          current_price DECIMAL(12,4),
          priority VARCHAR(20) DEFAULT 'medium',
          status VARCHAR(20) DEFAULT 'active',
          message TEXT,
          notification_methods JSONB DEFAULT '["email"]',
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          last_triggered TIMESTAMP WITH TIME ZONE,
          triggered_at TIMESTAMP WITH TIME ZONE,
          trigger_count INTEGER DEFAULT 0
        )`,
      },
      {
        name: "risk_alerts",
        sql: `CREATE TABLE IF NOT EXISTS risk_alerts (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          symbol VARCHAR(10) NOT NULL,
          alert_type VARCHAR(50) NOT NULL,
          condition VARCHAR(50) NOT NULL,
          threshold_value DECIMAL(12,4) NOT NULL,
          current_value DECIMAL(12,4),
          severity VARCHAR(20) DEFAULT 'medium',
          status VARCHAR(20) DEFAULT 'active',
          message TEXT,
          notification_methods JSONB DEFAULT '["email"]',
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          triggered_at TIMESTAMP WITH TIME ZONE,
          last_check TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )`,
      },
      {
        name: "stock_scores",
        sql: `CREATE TABLE IF NOT EXISTS stock_scores (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(10) NOT NULL,
          date DATE NOT NULL,
          composite_score DECIMAL(5,3),
          quality_score DECIMAL(5,3),
          value_score DECIMAL(5,3),
          growth_score DECIMAL(5,3),
          momentum_score DECIMAL(5,3),
          sentiment DECIMAL(5,3),
          positioning_score DECIMAL(5,3),
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(symbol, date)
        )`,
      },
      {
        name: "key_metrics",
        sql: `CREATE TABLE IF NOT EXISTS key_metrics (
          id SERIAL PRIMARY KEY,
          ticker VARCHAR(10) NOT NULL,
          market_cap BIGINT,
          pe_ratio DECIMAL(8,3),
          peg_ratio DECIMAL(8,3),
          price_to_book DECIMAL(8,3),
          price_to_sales DECIMAL(8,3),
          debt_to_equity DECIMAL(8,3),
          return_on_equity DECIMAL(8,3),
          return_on_assets DECIMAL(8,3),
          current_ratio DECIMAL(8,3),
          quick_ratio DECIMAL(8,3),
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )`,
      },
      {
        name: "dividend_calendar",
        sql: `CREATE TABLE IF NOT EXISTS dividend_calendar (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(10) NOT NULL,
          company_name VARCHAR(255),
          ex_dividend_date DATE,
          payment_date DATE,
          record_date DATE,
          dividend_amount DECIMAL(10,6),
          dividend_yield DECIMAL(6,3),
          dividend_type VARCHAR(50) DEFAULT 'regular',
          frequency VARCHAR(20),
          announcement_date DATE,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          CONSTRAINT unique_dividend_entry UNIQUE (symbol, ex_dividend_date)
        )`,
      },
      {
        name: "trading_strategies",
        sql: `CREATE TABLE IF NOT EXISTS trading_strategies (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255),
          strategy_name VARCHAR(255) NOT NULL,
          strategy_type VARCHAR(50) NOT NULL,
          description TEXT,
          strategy_description TEXT,
          strategy_code TEXT,
          backtest_id VARCHAR(255),
          risk_settings JSONB,
          hft_config JSONB,
          deployment_status VARCHAR(50) DEFAULT 'draft',
          parameters JSONB,
          status VARCHAR(20) DEFAULT 'active',
          performance_metrics JSONB,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          last_executed TIMESTAMP WITH TIME ZONE
        )`,
      },
      {
        name: "user_risk_limits",
        sql: `CREATE TABLE IF NOT EXISTS user_risk_limits (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          max_drawdown DECIMAL(5,2) DEFAULT 20.0,
          max_position_size DECIMAL(5,2) DEFAULT 25.0,
          stop_loss_percentage DECIMAL(5,2) DEFAULT 5.0,
          max_leverage DECIMAL(5,2) DEFAULT 2.0,
          max_correlation DECIMAL(3,2) DEFAULT 0.70,
          risk_tolerance_level VARCHAR(20) DEFAULT 'moderate',
          max_daily_loss DECIMAL(5,2) DEFAULT 2.0,
          max_monthly_loss DECIMAL(5,2) DEFAULT 10.0,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          CONSTRAINT unique_user_risk_limits UNIQUE (user_id)
        )`,
      },
      {
        name: "trade_history",
        sql: `CREATE TABLE IF NOT EXISTS trade_history (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          symbol VARCHAR(10) NOT NULL,
          action VARCHAR(10) NOT NULL,
          side VARCHAR(10) NOT NULL,
          quantity NUMERIC NOT NULL,
          price NUMERIC NOT NULL,
          total_amount NUMERIC NOT NULL,
          realized_pnl NUMERIC DEFAULT 0,
          trade_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          order_type VARCHAR(20) DEFAULT 'market',
          notes TEXT
        )`,
      },
      {
        name: "portfolio_summary",
        sql: `CREATE TABLE IF NOT EXISTS portfolio_summary (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL UNIQUE,
          total_value NUMERIC DEFAULT 0,
          unrealized_pnl NUMERIC DEFAULT 0,
          realized_pnl NUMERIC DEFAULT 0,
          total_positions INTEGER DEFAULT 0,
          last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )`,
      },
      {
        name: "user_dashboard_settings",
        sql: `CREATE TABLE IF NOT EXISTS user_dashboard_settings (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          widget_config JSONB,
          layout_config JSONB,
          theme VARCHAR(20) DEFAULT 'light',
          notifications_enabled BOOLEAN DEFAULT true,
          refresh_interval INTEGER DEFAULT 30,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          CONSTRAINT unique_user_settings UNIQUE (user_id)
        )`,
      },
      {
        name: "portfolio_metadata",
        sql: `CREATE TABLE IF NOT EXISTS portfolio_metadata (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          broker VARCHAR(50) NOT NULL,
          last_rebalance_date TIMESTAMP WITH TIME ZONE,
          rebalance_count INTEGER DEFAULT 0,
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          CONSTRAINT unique_user_broker_metadata UNIQUE (user_id, broker)
        )`,
      },
      {
        name: "swing_trading_signals",
        sql: `CREATE TABLE IF NOT EXISTS swing_trading_signals (
          id SERIAL PRIMARY KEY,
          symbol VARCHAR(10) NOT NULL,
          signal VARCHAR(10) NOT NULL CHECK (signal IN ('BUY', 'SELL')),
          entry_price DECIMAL(12,4),
          stop_loss DECIMAL(12,4),
          target_price DECIMAL(12,4),
          risk_reward_ratio DECIMAL(6,2),
          date DATE NOT NULL,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )`,
      },
      {
        name: "economic_data",
        sql: `CREATE TABLE IF NOT EXISTS economic_data (
          id SERIAL PRIMARY KEY,
          series_id VARCHAR(50) NOT NULL,
          date DATE NOT NULL,
          value DECIMAL(15,6),
          description TEXT,
          data_source VARCHAR(100) DEFAULT 'FRED',
          category VARCHAR(50),
          frequency VARCHAR(20) DEFAULT 'monthly',
          units VARCHAR(50),
          seasonal_adjustment VARCHAR(50),
          created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(series_id, date)
        )`,
      },
    ];

    // Create tables
    for (const table of tables) {
      try {
        await query(table.sql);
        console.log(`✅ Created/verified table: ${table.name}`);
      } catch (error) {
        console.warn(
          `⚠️  Warning creating table ${table.name}:`,
          error.message
        );
      }
    }

    // Insert initial data for stock_symbols
    await insertInitialData();

    console.log("✅ Database schema initialization completed");
  } catch (error) {
    console.error("Schema initialization error:", error);
    // Don't throw - let the application continue with existing tables
  }
}

/**
 * Insert initial data for essential tables
 */
async function insertInitialData() {
  try {
    // Insert sample stock symbols if the table is empty
    const countResult = await query(
      "SELECT COUNT(*) as count FROM stock_symbols"
    );
    const count = parseInt(countResult.rows[0].count);

    if (count === 0) {
      console.log("Inserting initial stock symbols data...");

      const insertSQL = `
                INSERT INTO stock_symbols (symbol, name, exchange) VALUES
                ('AAPL', 'Apple Inc.', 'NASDAQ'),
                ('MSFT', 'Microsoft Corporation', 'NASDAQ'),
                ('GOOGL', 'Alphabet Inc.', 'NASDAQ'),
                ('AMZN', 'Amazon.com Inc.', 'NASDAQ'),
                ('TSLA', 'Tesla Inc.', 'NASDAQ'),
                ('META', 'Meta Platforms Inc.', 'NASDAQ'),
                ('NVDA', 'NVIDIA Corporation', 'NASDAQ'),
                ('NFLX', 'Netflix Inc.', 'NASDAQ'),
                ('JPM', 'JPMorgan Chase & Co.', 'NYSE'),
                ('JNJ', 'Johnson & Johnson', 'NYSE'),
                ('V', 'Visa Inc.', 'NYSE'),
                ('PG', 'Procter & Gamble Co.', 'NYSE'),
                ('UNH', 'UnitedHealth Group Inc.', 'NYSE'),
                ('HD', 'The Home Depot Inc.', 'NYSE'),
                ('DIS', 'The Walt Disney Company', 'NYSE'),
                ('SPY', 'SPDR S&P 500 ETF Trust', 'NYSE'),
                ('QQQ', 'Invesco QQQ Trust', 'NASDAQ'),
                ('VTI', 'Vanguard Total Stock Market ETF', 'NYSE'),
                ('IWM', 'iShares Russell 2000 ETF', 'NYSE'),
                ('GLD', 'SPDR Gold Shares', 'NYSE')
                ON CONFLICT (symbol) DO UPDATE SET
                    name = EXCLUDED.name,
                    exchange = EXCLUDED.exchange
            `;

      await query(insertSQL);
      console.log("✅ Initial stock symbols data inserted");
    }

    // Insert sample price data if the table is empty
    const priceCountResult = await query(
      "SELECT COUNT(*) as count FROM price_daily"
    );
    const priceCount = parseInt(priceCountResult.rows[0].count);

    if (priceCount === 0) {
      console.log("Inserting initial price data...");

      const insertPriceSQL = `
                INSERT INTO price_daily (symbol, date, open_price, high_price, low_price, close, adj_close, volume, change_amount, change_percent) VALUES
                ('AAPL', CURRENT_DATE - INTERVAL '1 day', 175.20, 178.45, 174.80, 177.25, 177.25, 45000000, 2.05, 1.17),
                ('MSFT', CURRENT_DATE - INTERVAL '1 day', 420.50, 425.30, 418.75, 423.80, 423.80, 22000000, 3.30, 0.78),
                ('GOOGL', CURRENT_DATE - INTERVAL '1 day', 142.80, 145.25, 141.90, 144.75, 144.75, 28000000, 1.95, 1.37),
                ('AMZN', CURRENT_DATE - INTERVAL '1 day', 148.30, 151.20, 147.60, 150.40, 150.40, 35000000, 2.10, 1.42),
                ('TSLA', CURRENT_DATE - INTERVAL '1 day', 245.60, 252.80, 243.10, 250.25, 250.25, 85000000, 4.65, 1.89),
                ('SPY', CURRENT_DATE - INTERVAL '1 day', 445.20, 447.80, 444.30, 446.95, 446.95, 65000000, 1.75, 0.39),
                ('QQQ', CURRENT_DATE - INTERVAL '1 day', 385.40, 388.60, 384.20, 387.30, 387.30, 42000000, 1.90, 0.49)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open_price = EXCLUDED.open_price,
                    high_price = EXCLUDED.high_price,
                    low_price = EXCLUDED.low_price,
                    close = EXCLUDED.close,
                    adj_close = EXCLUDED.adj_close,
                    volume = EXCLUDED.volume,
                    change_amount = EXCLUDED.change_amount,
                    change_percent = EXCLUDED.change_percent
            `;

      await query(insertPriceSQL);
      console.log("✅ Initial price data inserted");
    }

    // Insert sample stocks data if the table is empty
    const stocksCountResult = await query(
      "SELECT COUNT(*) as count FROM stocks"
    );
    const stocksCount = parseInt(stocksCountResult.rows[0].count);

    if (stocksCount === 0) {
      console.log("Inserting initial stocks data...");

      const insertStocksSQL = `
        INSERT INTO stocks (symbol, name, sector, industry, market_cap, price, dividend_yield, beta, exchange) VALUES
        ('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics', 3000000000000, 177.25, 0.52, 1.28, 'NASDAQ'),
        ('MSFT', 'Microsoft Corporation', 'Technology', 'Software', 2800000000000, 423.80, 0.68, 0.90, 'NASDAQ'),
        ('GOOGL', 'Alphabet Inc.', 'Technology', 'Internet Services', 1800000000000, 144.75, 0.00, 1.05, 'NASDAQ'),
        ('AMZN', 'Amazon.com Inc.', 'Technology', 'E-commerce', 1500000000000, 150.40, 0.00, 1.33, 'NASDAQ'),
        ('TSLA', 'Tesla Inc.', 'Automotive', 'Electric Vehicles', 800000000000, 250.25, 0.00, 2.29, 'NASDAQ'),
        ('SPY', 'SPDR S&P 500 ETF Trust', 'ETF', 'Exchange Traded Fund', 400000000000, 446.95, 1.30, 1.00, 'NYSE'),
        ('QQQ', 'Invesco QQQ Trust', 'ETF', 'Exchange Traded Fund', 200000000000, 387.30, 0.50, 1.15, 'NASDAQ'),
        ('JPM', 'JPMorgan Chase & Co.', 'Financial Services', 'Banking', 500000000000, 185.50, 2.50, 1.18, 'NYSE'),
        ('JNJ', 'Johnson & Johnson', 'Healthcare', 'Pharmaceuticals', 420000000000, 165.20, 2.90, 0.70, 'NYSE'),
        ('UNH', 'UnitedHealth Group Inc.', 'Healthcare', 'Insurance', 480000000000, 520.75, 1.20, 0.82, 'NYSE')
        ON CONFLICT (symbol) DO UPDATE SET
            name = EXCLUDED.name,
            sector = EXCLUDED.sector,
            industry = EXCLUDED.industry,
            market_cap = EXCLUDED.market_cap,
            price = EXCLUDED.price,
            dividend_yield = EXCLUDED.dividend_yield,
            beta = EXCLUDED.beta,
            exchange = EXCLUDED.exchange,
            updated_at = CURRENT_TIMESTAMP
      `;

      await query(insertStocksSQL);
      console.log("✅ Initial stocks data inserted");
    }

    // Insert sample economic data if the table is empty
    const economicCountResult = await query(
      "SELECT COUNT(*) as count FROM economic_data"
    );
    const economicCount = parseInt(economicCountResult.rows[0].count);

    if (economicCount === 0) {
      console.log("Inserting initial economic data...");

      const insertEconomicSQL = `
        INSERT INTO economic_data (series_id, date, value, description, category, frequency) VALUES
        ('GDP', '2024-12-01', 22996.1, 'Gross Domestic Product', 'growth', 'quarterly'),
        ('GDP', '2024-09-01', 22875.4, 'Gross Domestic Product', 'growth', 'quarterly'),
        ('GDP', '2024-06-01', 22734.8, 'Gross Domestic Product', 'growth', 'quarterly'),
        ('GDP', '2024-03-01', 22658.3, 'Gross Domestic Product', 'growth', 'quarterly'),
        ('CPI', '2024-12-01', 310.3, 'Consumer Price Index', 'inflation', 'monthly'),
        ('CPI', '2024-11-01', 309.7, 'Consumer Price Index', 'inflation', 'monthly'),
        ('CPI', '2024-10-01', 309.1, 'Consumer Price Index', 'inflation', 'monthly'),
        ('CPI', '2024-09-01', 308.5, 'Consumer Price Index', 'inflation', 'monthly'),
        ('UNEMPLOYMENT', '2024-12-01', 4.1, 'Unemployment Rate', 'employment', 'monthly'),
        ('UNEMPLOYMENT', '2024-11-01', 4.0, 'Unemployment Rate', 'employment', 'monthly'),
        ('UNEMPLOYMENT', '2024-10-01', 3.9, 'Unemployment Rate', 'employment', 'monthly'),
        ('UNEMPLOYMENT', '2024-09-01', 4.0, 'Unemployment Rate', 'employment', 'monthly'),
        ('FEDERAL_FUNDS', '2024-12-01', 5.25, 'Federal Funds Rate', 'monetary', 'monthly'),
        ('FEDERAL_FUNDS', '2024-11-01', 5.25, 'Federal Funds Rate', 'monetary', 'monthly'),
        ('FEDERAL_FUNDS', '2024-10-01', 5.25, 'Federal Funds Rate', 'monetary', 'monthly'),
        ('FEDERAL_FUNDS', '2024-09-01', 5.25, 'Federal Funds Rate', 'monetary', 'monthly'),
        ('INFLATION', '2024-12-01', 2.4, 'Core Inflation Rate', 'inflation', 'monthly'),
        ('INFLATION', '2024-11-01', 2.3, 'Core Inflation Rate', 'inflation', 'monthly'),
        ('INFLATION', '2024-10-01', 2.2, 'Core Inflation Rate', 'inflation', 'monthly'),
        ('INFLATION', '2024-09-01', 2.1, 'Core Inflation Rate', 'inflation', 'monthly'),
        ('HOUSING_STARTS', '2024-12-01', 1485000, 'Housing Starts', 'housing', 'monthly'),
        ('HOUSING_STARTS', '2024-11-01', 1472000, 'Housing Starts', 'housing', 'monthly'),
        ('HOUSING_STARTS', '2024-10-01', 1458000, 'Housing Starts', 'housing', 'monthly'),
        ('HOUSING_STARTS', '2024-09-01', 1445000, 'Housing Starts', 'housing', 'monthly'),
        ('RETAIL_SALES', '2024-12-01', 695.2, 'Retail Sales', 'trade', 'monthly'),
        ('RETAIL_SALES', '2024-11-01', 689.5, 'Retail Sales', 'trade', 'monthly'),
        ('RETAIL_SALES', '2024-10-01', 684.3, 'Retail Sales', 'trade', 'monthly'),
        ('RETAIL_SALES', '2024-09-01', 678.9, 'Retail Sales', 'trade', 'monthly')
        ON CONFLICT (series_id, date) DO UPDATE SET
            value = EXCLUDED.value,
            description = EXCLUDED.description,
            category = EXCLUDED.category,
            frequency = EXCLUDED.frequency,
            updated_at = CURRENT_TIMESTAMP
      `;

      await query(insertEconomicSQL);
      console.log("✅ Initial economic data inserted");
    }
  } catch (error) {
    console.warn("Warning inserting initial data:", error.message);
    // Don't throw - let the application continue
  }
}

/**
 * Get the connection pool instance
 */
function getPool() {
  if (!pool || !dbInitialized) {
    throw new Error(
      "Database not initialized. Call initializeDatabase() first."
    );
  }
  return pool;
}

/**
 * Execute a database query with performance monitoring and optimization
 */
async function query(text, params = []) {
  try {
    // Ensure database is initialized
    if (!dbInitialized || !pool) {
      console.log("Database not initialized, attempting initialization...");
      const result = await initializeDatabase();
      if (!result || !pool) {
        // Database is not available, return null for graceful degradation
        console.warn(
          "Database not available - operation will return null for graceful fallback"
        );
        return null;
      }
    }

    // Check if pool is still valid
    if (!pool) {
      console.warn(
        "Database connection pool not available - returning null for graceful fallback"
      );
      return null;
    }

    const start = Date.now();
    const result = await pool.query(text, params);
    const duration = Date.now() - start;

    // Enhanced performance monitoring based on testing insights
    if (duration > 5000) {
      console.error(`⚠️ VERY SLOW QUERY detected (${duration}ms):`, {
        query: text.slice(0, 150) + (text.length > 150 ? "..." : ""),
        rows: result.rowCount,
        duration: `${duration}ms`,
      });
    } else if (duration > 1000) {
      console.warn(`⏱️ Slow query (${duration}ms):`, {
        query: text.slice(0, 100) + (text.length > 100 ? "..." : ""),
        rows: result.rowCount,
        duration: `${duration}ms`,
      });
    } else if (process.env.NODE_ENV === "development" && duration > 500) {
      console.log(`📊 Query performance (${duration}ms):`, {
        query: text.slice(0, 80) + (text.length > 80 ? "..." : ""),
        rows: result.rowCount,
      });
    }

    return result;
  } catch (error) {
    console.error("Database query error:", {
      error: error.message,
      query: text.slice(0, 100) + (text.length > 100 ? "..." : ""),
      params: params?.length ? `${params.length} parameters` : "no parameters",
      code: error.code,
    });

    // Enhanced error classification for better debugging
    if (
      error.message.includes("connect") ||
      error.message.includes("ENOTFOUND") ||
      error.message.includes("ECONNREFUSED") ||
      error.message.includes("timeout") ||
      error.code === "ETIMEDOUT" ||
      error.code === "ECONNRESET" ||
      error.code === "ECONNABORTED"
    ) {
      console.warn(
        "Database connection error - returning null for graceful fallback"
      );
      return null;
    }

    // For other errors, still throw to maintain error handling for genuine issues
    throw error;
  }
}

/**
 * Execute a cached query for frequently accessed data
 * Only use for read-only queries with relatively stable data
 */
async function cachedQuery(text, params = [], cacheTtl = CACHE_TTL) {
  // Create cache key from query and parameters
  const cacheKey = `${text}|${JSON.stringify(params)}`;

  // Check if we have a cached result
  const cached = queryCache.get(cacheKey);
  if (cached && Date.now() - cached.timestamp < cacheTtl) {
    return cached.result;
  }

  // Execute the query
  const result = await query(text, params);

  // Cache the result if it's not null (database available)
  if (result !== null) {
    queryCache.set(cacheKey, {
      result,
      timestamp: Date.now(),
    });

    // Clean up old cache entries periodically
    if (queryCache.size > 100) {
      const now = Date.now();
      for (const [key, entry] of queryCache.entries()) {
        if (now - entry.timestamp > cacheTtl * 2) {
          queryCache.delete(key);
        }
      }
    }
  }

  return result;
}

/**
 * Clear query cache (useful for testing or after data updates)
 */
function clearQueryCache() {
  queryCache.clear();
}

/**
 * Execute a transaction
 */
async function transaction(callback) {
  const client = await getPool().connect();

  try {
    await client.query("BEGIN");
    const result = await callback(client);
    await client.query("COMMIT");
    return result;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}

/**
 * Close database connections (for cleanup)
 */
async function closeDatabase() {
  if (pool) {
    // console.log('Closing database connections...');
    await pool.end();
    pool = null;
    dbInitialized = false;
    dbConfig = null;
    // console.log('Database connections closed');
  }
}

/**
 * Health check for database
 */
async function healthCheck() {
  try {
    if (!dbInitialized || !pool) {
      await initializeDatabase();
    }

    const result = await query(
      "SELECT NOW() as timestamp, version() as db_version"
    );
    return {
      status: "healthy",
      timestamp: result.rows[0].timestamp,
      version: result.rows[0].db_version,
      connections: pool.totalCount,
      idle: pool.idleCount,
      waiting: pool.waitingCount,
    };
  } catch (error) {
    return {
      status: "unhealthy",
      error: error.message,
    };
  }
}

module.exports = {
  initializeDatabase,
  getPool,
  query,
  cachedQuery,
  clearQueryCache,
  transaction,
  closeDatabase,
  healthCheck,
};

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
      dbConfig = {
        host: process.env.DB_HOST || process.env.DB_ENDPOINT,
        port: parseInt(process.env.DB_PORT) || 5432,
        user: process.env.DB_USER || process.env.DB_USERNAME,
        password: process.env.DB_PASSWORD,
        database: process.env.DB_NAME || process.env.DB_DATABASE,
        max: parseInt(process.env.DB_POOL_MAX) || 5,
        idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
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
        console.warn(
          "No database configuration available. API will run in fallback mode with mock data."
        );
        dbInitialized = false;
        pool = null;
        return null; // Return null instead of throwing error
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

    const { generateCreateTableSQL, listTables } = require("./schemaValidator");

    // Priority tables that should be created first
    const priorityTables = [
      "stock_symbols",
      "price_daily",
      "user_api_keys",
      "portfolio_metadata",
      "portfolio_holdings",
      "portfolio_performance",
      "portfolio_transactions",
      "trading_alerts",
    ];

    // Get all table schemas
    const allTables = listTables();

    // Create priority tables first
    for (const tableName of priorityTables) {
      if (allTables.includes(tableName)) {
        try {
          const createSQL = generateCreateTableSQL(tableName);
          await query(createSQL);
          console.log(`✅ Created/verified table: ${tableName}`);
        } catch (error) {
          console.warn(
            `⚠️  Warning creating table ${tableName}:`,
            error.message
          );
        }
      }
    }

    // Create remaining tables
    for (const tableName of allTables) {
      if (!priorityTables.includes(tableName)) {
        try {
          const createSQL = generateCreateTableSQL(tableName);
          await query(createSQL);
          console.log(`✅ Created/verified table: ${tableName}`);
        } catch (error) {
          console.warn(
            `⚠️  Warning creating table ${tableName}:`,
            error.message
          );
        }
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
                INSERT INTO stock_symbols (symbol, security_name, exchange) VALUES
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
                    security_name = EXCLUDED.security_name,
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
                INSERT INTO price_daily (symbol, date, open_price, high_price, low_price, close_price, adj_close_price, volume, change_amount, change_percent) VALUES
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
                    close_price = EXCLUDED.close_price,
                    adj_close_price = EXCLUDED.adj_close_price,
                    volume = EXCLUDED.volume,
                    change_amount = EXCLUDED.change_amount,
                    change_percent = EXCLUDED.change_percent
            `;

      await query(insertPriceSQL);
      console.log("✅ Initial price data inserted");
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
 * Execute a database query
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

    // Only log slow queries (> 1000ms) or errors
    if (duration > 1000) {
      // console.log(`Query executed in ${duration}ms`, {
      //     rows: result.rowCount,
      //     query: text.slice(0, 100) + (text.length > 100 ? '...' : '')
      // });
    }

    return result;
  } catch (error) {
    console.error("Database query error:", {
      error: error.message,
      query: text.slice(0, 100) + (text.length > 100 ? "..." : ""),
      params: params,
    });

    // Check if this is a connection-related error (graceful degradation)
    if (
      error.message.includes("connect") ||
      error.message.includes("ENOTFOUND") ||
      error.message.includes("ECONNREFUSED")
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
  transaction,
  closeDatabase,
  healthCheck,
};

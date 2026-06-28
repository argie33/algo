// Environment variables should already be loaded by index.js at startup
// No need to load dotenv here - trust that env vars are available
// If DB_HOST or DB_SECRET_ARN missing, it will error below (which is correct behavior)

const {
  SecretsManagerClient,
  GetSecretValueCommand,
} = require("@aws-sdk/client-secrets-manager");
const { Pool } = require("pg");

// Lazy-initialize AWS SDK v3 client to avoid blocking at module load time
let secretsManager = null;
function getSecretsManagerClient() {
  if (!secretsManager) {
    secretsManager = new SecretsManagerClient({
      region:
        process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || "us-east-1",
    });
  }
  return secretsManager;
}

// Connection pool instance
let pool = null;
let dbInitialized = false;
let initPromise = null;
let indexesCreated = false; // guard: only run background index creation once per process

// Database configuration cache
let dbConfig = null;

/**
 * Safely parse an integer from an environment variable
 * Replaces: parseInt(process.env.VAR) || defaultValue
 * With: explicit NaN check and default handling
 *
 * @param {string} envVar - The environment variable value to parse
 * @param {number} defaultValue - The default value if envVar is missing or invalid
 * @returns {number} The parsed integer or the default value
 */
function parseIntSafe(envVar, defaultValue) {
  if (envVar === null || envVar === undefined || envVar === '') {
    return defaultValue;
  }
  const parsed = parseInt(envVar, 10);
  if (isNaN(parsed)) {
    return defaultValue;
  }
  return parsed;
}

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
    const isLocalDev = process.env.NODE_ENV === "development" && process.env.DB_HOST === "localhost";

    // In development with local DB_HOST, skip AWS Secrets Manager
    if (isLocalDev) {
      // Fall through to environment variables below
    } else if (secretArn) {
      try {
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        const client = getSecretsManagerClient();
        const result = await client.send(command);

        let secret;

        if (
          typeof result.SecretString === "object" &&
          result.SecretString !== null
        ) {
          secret = result.SecretString;
        } else if (typeof result.SecretString === "string") {
          try {
            secret = JSON.parse(result.SecretString);
            // SECURITY FIX S-10: Validate secret structure to ensure it has required fields
            if (!secret || typeof secret !== "object") {
              throw new Error("Secret must be a JSON object");
            }
            if (
              !secret.username ||
              !secret.password ||
              !secret.host ||
              !secret.dbname
            ) {
              throw new Error(
                "Secret missing required fields: username, password, host, dbname"
              );
            }
          } catch (parseError) {
            throw new Error(`Secret parsing failed: ${parseError.message}`);
          }
        } else if (result.SecretString === undefined && result.SecretBinary) {
          try {
            const decoded = Buffer.from(result.SecretBinary, "base64").toString(
              "utf-8"
            );
            secret = JSON.parse(decoded);
          } catch (decodeError) {
            throw new Error(
              `Secret binary decoding failed: ${decodeError.message}`
            );
          }
        } else {
          throw new Error(
            `Unexpected SecretString type: ${typeof result.SecretString}`
          );
        }

        dbConfig = {
          host: secret.host || process.env.DB_ENDPOINT,
          port: secret.port ? parseInt(secret.port, 10) : undefined,
          user: secret.username,
          password: secret.password,
          database: secret.dbname,
          max: parseIntSafe(process.env.DB_POOL_MAX, 10), // Increased for reserved concurrency
          min: parseIntSafe(process.env.DB_POOL_MIN, 2),
          idleTimeoutMillis: parseIntSafe(process.env.DB_POOL_IDLE_TIMEOUT, 10000),
          connectionTimeoutMillis: parseIntSafe(process.env.DB_CONNECT_TIMEOUT, 3000),
          acquireTimeoutMillis: parseIntSafe(process.env.DB_ACQUIRE_TIMEOUT, 3000),
          createTimeoutMillis: parseIntSafe(process.env.DB_CREATE_TIMEOUT, 3000),
          statement_timeout: parseIntSafe(process.env.DB_STATEMENT_TIMEOUT, 30000),
          query_timeout: parseIntSafe(process.env.DB_QUERY_TIMEOUT, 25000),
          ssl:
            process.env.DB_SSL === "false"
              ? false
              : {
                  rejectUnauthorized: true,
                  // Optional: provide CA certificate if using self-signed or custom CA
                  // ca: process.env.DB_CA_CERT ? Buffer.from(process.env.DB_CA_CERT, 'base64').toString() : undefined
                },
        };

        console.log(
          `Database config loaded from Secrets Manager: ${dbConfig.host}:${dbConfig.port}/${dbConfig.database}`
        );
        console.log(
          `SSL Config: DB_SSL env var = "${process.env.DB_SSL}", using SSL: ${JSON.stringify(dbConfig.ssl)}`
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
      const host = process.env.DB_HOST || process.env.DB_ENDPOINT;
      const user = process.env.DB_USER || process.env.DB_USERNAME || "postgres";
      const password = process.env.DB_PASSWORD;
      const database =
        process.env.DB_NAME || process.env.DB_DATABASE || "postgres";

      if (!host) {
        throw new Error("DB_HOST is required when using environment variables");
      }

      // SECURITY FIX S-13: Require explicit password (no empty default)
      if (!password) {
        throw new Error(
          "Database password (DB_PASSWORD) is required. Set via environment variable or provide DB_SECRET_ARN for AWS Secrets Manager."
        );
      }

      dbConfig = {
        host,
        port: process.env.DB_PORT ? parseInt(process.env.DB_PORT, 10) : undefined,
        user,
        password,
        database,
        // AWS Lambda optimized connection pool settings
        max: parseIntSafe(process.env.DB_POOL_MAX, 10), // Increased for reserved concurrency
        min: parseIntSafe(process.env.DB_POOL_MIN, 2), // Keep minimal connections
        idleTimeoutMillis: parseIntSafe(process.env.DB_POOL_IDLE_TIMEOUT, 10000), // Shorter idle timeout
        connectionTimeoutMillis: parseIntSafe(process.env.DB_CONNECT_TIMEOUT, 3000), // Fast timeout for Lambda
        acquireTimeoutMillis: parseIntSafe(process.env.DB_ACQUIRE_TIMEOUT, 3000), // Quick acquire
        createTimeoutMillis: parseIntSafe(process.env.DB_CREATE_TIMEOUT, 3000), // Fast creation
        reapIntervalMillis: parseIntSafe(process.env.DB_REAP_INTERVAL, 1000), // Pool maintenance
        createRetryIntervalMillis: parseIntSafe(process.env.DB_RETRY_INTERVAL, 100), // Fast retries
        statement_timeout: parseIntSafe(process.env.DB_STATEMENT_TIMEOUT, 30000), // 30s max query time
        query_timeout: parseIntSafe(process.env.DB_QUERY_TIMEOUT, 25000), // 25s max per query
        ssl:
          process.env.DB_SSL === "false"
            ? false
            : {
                rejectUnauthorized: true,
                // Optional: provide CA certificate if using self-signed or custom CA
                // ca: process.env.DB_CA_CERT ? Buffer.from(process.env.DB_CA_CERT, 'base64').toString() : undefined
              },
      };

      console.log(
        `Database config loaded from environment: ${dbConfig.host}:${dbConfig.port}/${dbConfig.database}`
      );
      console.log(
        `SSL Config: DB_SSL env var = "${process.env.DB_SSL}", using SSL: ${JSON.stringify(dbConfig.ssl)}`
      );
      return dbConfig;
    }

    // If no configuration is available, throw error to expose the issue
    const configError = new Error(
      "No database configuration found. Set DB_SECRET_ARN or DB_HOST environment variables."
    );
    configError.code = "NO_DB_CONFIG";
    throw configError;
  } catch (error) {
    // Re-throw configuration errors instead of silently returning null
    console.error(" Critical database configuration error:", {
      message: error.message,
      code: error.code,
      env: {
        DB_SECRET_ARN: process.env.DB_SECRET_ARN,
        DB_HOST: process.env.DB_HOST,
        DB_PORT: process.env.DB_PORT,
        DB_NAME: process.env.DB_NAME,
        DB_USER: process.env.DB_USER,
      },
    });
    throw error; // Always throw configuration errors
  }
}

/**
 * Validate database configuration
 * Ensures port is explicitly configured (not defaulted)
 */
function validateDbConfig(config) {
  if (!config) {
    throw new Error("Database configuration is required");
  }

  if (!config.host) {
    throw new Error("Database host (DB_HOST or DB_ENDPOINT) is required");
  }

  if (!config.port) {
    throw new Error(
      "Database port (DB_PORT) must be explicitly configured. " +
        "No default port is applied. Set DB_PORT in environment variables or Secrets Manager."
    );
  }

  if (!config.user) {
    throw new Error("Database user is required");
  }

  if (!config.database) {
    throw new Error("Database name is required");
  }
}

/**
 * Test database connection
 * Validates connectivity and port configuration
 */
async function testConnection() {
  try {
    const config = await getDbConfig();
    validateDbConfig(config);

    const testPool = new Pool({
      ...config,
      max: 1,
      connectionTimeoutMillis: 5000,
    });

    const client = await testPool.connect();
    const result = await client.query("SELECT NOW() as timestamp");
    client.release();
    await testPool.end();

    return {
      status: "ok",
      message: `Connected to ${config.host}:${config.port}/${config.database}`,
      timestamp: result.rows[0].timestamp,
    };
  } catch (error) {
    return {
      status: "error",
      message: error.message,
      error: error.code || "CONNECTION_FAILED",
    };
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
      config = await getDbConfig();

      if (!config) {
        const error = new Error(
          "Database configuration missing. Please set DB environment variables or DB_SECRET_ARN."
        );
        console.error(
          "No database configuration available. Application cannot function without database."
        );
        dbInitialized = false;
        pool = null;
        throw error;
      }

      validateDbConfig(config);

      pool = new Pool(config);
      const client = await pool.connect();
      await client.query("SELECT NOW()");
      client.release();
      dbInitialized = true;

      // Create indexes asynchronously in background — once per process lifetime only
      if (!indexesCreated) {
        indexesCreated = true;
        setImmediate(async () => {
          try {
            const indexClient = await pool.connect();
            // Check which indexes already exist to avoid catalog hits for existing ones
            const existingResult = await indexClient.query(
              "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename IN ('buy_sell_daily','buy_sell_weekly','buy_sell_monthly')"
            );
            const existingIndexes = new Set(
              existingResult.rows.map((r) => r.indexname)
            );
            const indexDefs = [
              [
                "idx_buy_sell_daily_date_signal",
                "CREATE INDEX CONCURRENTLY idx_buy_sell_daily_date_signal   ON buy_sell_daily   (date DESC, UPPER(signal))",
              ],
              [
                "idx_buy_sell_daily_symbol_date",
                "CREATE INDEX CONCURRENTLY idx_buy_sell_daily_symbol_date   ON buy_sell_daily   (symbol, date DESC)",
              ],
              [
                "idx_buy_sell_weekly_date_signal",
                "CREATE INDEX CONCURRENTLY idx_buy_sell_weekly_date_signal  ON buy_sell_weekly  (date DESC, UPPER(signal))",
              ],
              [
                "idx_buy_sell_weekly_symbol_date",
                "CREATE INDEX CONCURRENTLY idx_buy_sell_weekly_symbol_date  ON buy_sell_weekly  (symbol, date DESC)",
              ],
              [
                "idx_buy_sell_monthly_date_signal",
                "CREATE INDEX CONCURRENTLY idx_buy_sell_monthly_date_signal ON buy_sell_monthly (date DESC, UPPER(signal))",
              ],
              [
                "idx_buy_sell_monthly_symbol_date",
                "CREATE INDEX CONCURRENTLY idx_buy_sell_monthly_symbol_date ON buy_sell_monthly (symbol, date DESC)",
              ],
            ];
            for (const [name, sql] of indexDefs) {
              if (!existingIndexes.has(name)) {
                try {
                  await indexClient.query(sql);
                } catch (err) {
                  console.warn("Index creation warning:", err.message);
                }
              }
            }
            indexClient.release();
          } catch (err) {
            console.warn(
              "Warning: Background index creation failed:",
              err.message
            );
          }
        });
      }

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
      // CRITICAL FIX: Always throw database initialization errors instead of silently returning null
      // Silent failures prevent visibility into real database issues and cause API endpoints to return null
      console.error(" CRITICAL: Database initialization failed:", {
        error: error.message,
        code: error.code,
        config: config,
        env: error.env,
        stack: error.stack,
      });
      throw error; // Always throw connection errors to expose the real problem
    } finally {
      initPromise = null;
    }
  })();

  return initPromise;
}

/**
 * Create materialized views for performance optimization.
 * Creates on first run; refreshes concurrently on subsequent cold starts.
 */
async function initializeMaterializedViews() {
  try {
    if (!pool || !dbInitialized) {
      console.warn("Cannot create materialized views - database not connected");
      return false;
    }

    const client = await pool.connect();
    try {
      // Check which views already exist so we can refresh vs create
      const existing = await client.query(`
        SELECT matviewname FROM pg_matviews
        WHERE schemaname = 'public' AND matviewname IN ('mv_latest_prices', 'mv_stock_scores_full')
      `);
      const existingNames = new Set(existing.rows.map((r) => r.matviewname));

      // --- mv_latest_prices ---
      if (!existingNames.has("mv_latest_prices")) {
        await client.query(`
          CREATE MATERIALIZED VIEW mv_latest_prices AS
          SELECT DISTINCT ON (symbol)
            symbol,
            close as price,
            open,
            high,
            low,
            volume,
            date
          FROM price_daily
          ORDER BY symbol, date DESC;
        `);
        await client.query(
          "CREATE UNIQUE INDEX idx_mv_latest_prices_symbol ON mv_latest_prices (symbol);"
        );
      } else {
        // CONCURRENTLY requires a unique index; safe to call on warm containers
        try {
          await client.query(
            "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_latest_prices"
          );
        } catch (e) {
          // Fallback to non-concurrent refresh if unique index not ready
          await client.query("REFRESH MATERIALIZED VIEW mv_latest_prices");
        }
      }

      // --- mv_stock_scores_full ---
      if (!existingNames.has("mv_stock_scores_full")) {
        await client.query(`
          CREATE MATERIALIZED VIEW mv_stock_scores_full AS
          SELECT
            ss.symbol,
            ss.composite_score,
            ss.quality_score,
            ss.growth_score,
            ss.stability_score,
            ss.momentum_score,
            ss.value_score,
            ss.positioning_score,
            st.security_name
          FROM stock_scores ss
          LEFT JOIN stock_symbols st ON ss.symbol = st.symbol
          WHERE ss.composite_score IS NOT NULL;
        `);
        await client.query(
          "CREATE UNIQUE INDEX idx_mv_stock_scores_full_symbol ON mv_stock_scores_full (symbol);"
        );
      } else {
        try {
          await client.query(
            "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_stock_scores_full"
          );
        } catch (e) {
          await client.query("REFRESH MATERIALIZED VIEW mv_stock_scores_full");
        }
      }

      return true;
    } finally {
      client.release();
    }
  } catch (error) {
    console.warn(
      "Materialized views initialization warning (non-critical):",
      error.message
    );
    // Don't throw - views might already exist, application can continue
    return false;
  }
}

/**
 * Initialize database schema
 * Market data tables are created by loader scripts
 * Webapp tables are created by webapp-db-init.js
 */
async function initializeSchema() {
  try {
    // Create materialized views for performance
    await initializeMaterializedViews();

    // Fix portfolio_holdings schema to match code expectations
    try {
      await fixPortfolioHoldingsSchema();
    } catch (err) {
      console.warn("Portfolio holdings schema fix warning:", err.message);
    }

    // Import and run webapp table initialization if available
    try {
      // eslint-disable-next-line node/no-missing-require
      const { initializeWebappTables } = require("../webapp-db-init");
      await initializeWebappTables();
    } catch (err) {
      console.warn(
        "Webapp table initialization skipped (not critical):",
        err.message
      );
    }

    return true;
  } catch (error) {
    console.error("Schema initialization error:", error);
    // Don't throw - let the application continue with existing tables
    return false;
  }
}

/**
 * Fix portfolio_holdings schema issues:
 * 1. Change user_id from INTEGER to VARCHAR(255)
 * 2. Add missing columns: market_value, sector, unrealized_pl, unrealized_pl_percent
 */
async function fixPortfolioHoldingsSchema() {
  if (!pool || !dbInitialized) {
    return;
  }

  const client = await pool.connect();
  try {
    // Get current column info
    const columnsResult = await client.query(`
      SELECT column_name, data_type FROM information_schema.columns
      WHERE table_name = 'portfolio_holdings' AND table_schema = 'public'
    `);

    const columns = new Map(
      columnsResult.rows.map((r) => [r.column_name, r.data_type])
    );

    // Fix user_id type if it's wrong
    if (
      columns.has("user_id") &&
      columns.get("user_id") !== "character varying"
    ) {
      console.log(
        "Fixing portfolio_holdings.user_id type from INTEGER to VARCHAR(255)..."
      );
      // Create temp column with correct type
      await client.query(
        "ALTER TABLE portfolio_holdings ADD COLUMN user_id_new VARCHAR(255)"
      );
      // Copy and convert data
      await client.query(
        "UPDATE portfolio_holdings SET user_id_new = CAST(user_id AS VARCHAR(255))"
      );
      // Drop old column and rename
      await client.query("ALTER TABLE portfolio_holdings DROP COLUMN user_id");
      await client.query(
        "ALTER TABLE portfolio_holdings RENAME COLUMN user_id_new TO user_id"
      );
      // Restore NOT NULL constraint
      await client.query(
        "ALTER TABLE portfolio_holdings ALTER COLUMN user_id SET NOT NULL"
      );
      console.log("Fixed portfolio_holdings.user_id type");
    }

    // Add missing columns
    const columnsToAdd = {
      market_value: "DECIMAL(15,2)",
      sector: "VARCHAR(100)",
      unrealized_pl: "DECIMAL(15,2)",
      unrealized_pl_percent: "DECIMAL(8,4)",
      created_at: "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
      updated_at: "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    };

    for (const [colName, colType] of Object.entries(columnsToAdd)) {
      if (!columns.has(colName)) {
        console.log(`Adding missing column portfolio_holdings.${colName}...`);
        await client.query(
          `ALTER TABLE portfolio_holdings ADD COLUMN ${colName} ${colType}`
        );
      }
    }

    console.log("Portfolio holdings schema fixed");
  } finally {
    client.release();
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
 * Ensure database connection is available before executing operations
 * Throws with code 'DB_CONNECTION_FAILED' if connection is unavailable
 * Used by routes to validate connection hasn't dropped after middleware check
 */
function ensureConnection() {
  if (!pool || !dbInitialized) {
    const error = new Error("Database connection is no longer available");
    error.code = "DB_CONNECTION_FAILED";
    throw error;
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
      const result = await initializeDatabase();
      if (!result || !pool) {
        // Database is not available - throw error instead of fallback
        const error = new Error("Database connection failed");
        error.code = "DB_CONNECTION_FAILED";
        throw error;
      }
    }

    // Check if pool is still valid
    if (!pool) {
      const error = new Error("Database connection pool not available");
      error.code = "DB_POOL_NOT_AVAILABLE";
      throw error;
    }

    // CRITICAL: Declare these OUTSIDE try block so catch can access them
    const start = Date.now();
    let queryDuration = 0; // Initialize query duration - will be updated after query completes

    // Add query timeout protection for AWS Lambda
    const queryTimeout = parseIntSafe(process.env.DB_QUERY_TIMEOUT, 25000); // 25 seconds
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => {
        reject(
          new Error(
            `Query timeout after ${queryTimeout}ms: ${typeof text === "string" ? text.slice(0, 100) : JSON.stringify(text).slice(0, 100)}...`
          )
        );
      }, queryTimeout);
    });

    const result = await Promise.race([
      pool.query(text, params),
      timeoutPromise,
    ]);

    queryDuration = Date.now() - start; // Calculate duration AFTER query completes

    // Enhanced performance monitoring based on testing insights
    if (queryDuration > 5000) {
      console.error(`⚠️ VERY SLOW QUERY detected (${queryDuration}ms):`, {
        query: text.slice(0, 150) + (text.length > 150 ? "..." : ""),
        rows: result.rowCount,
        duration: `${queryDuration}ms`,
      });
    } else if (queryDuration > 1000) {
      console.warn(`⏱️ Slow query (${queryDuration}ms):`, {
        query:
          typeof text === "string"
            ? text.slice(0, 100) + (text.length > 100 ? "..." : "")
            : JSON.stringify(text).slice(0, 100) + "...",
        rows: result.rowCount,
        duration: `${queryDuration}ms`,
      });
    } else if (process.env.NODE_ENV === "development" && queryDuration > 500) {
      console.debug({
        query: text.slice(0, 80) + (text.length > 80 ? "..." : ""),
        rows: result.rowCount,
      });
    }

    return result;
  } catch (error) {
    console.error("Database query error:", {
      error: error.message,
      query:
        typeof text === "string"
          ? text.slice(0, 100) + (text.length > 100 ? "..." : "")
          : JSON.stringify(text).slice(0, 100) + "...",
      params: params?.length ? `${params.length} parameters` : "no parameters",
      code: error.code,
    });

    // Categorize connection-level errors (503 - Service Unavailable)
    const isConnectionError =
      error.message.includes("connect") ||
      error.message.includes("ENOTFOUND") ||
      error.message.includes("ECONNREFUSED") ||
      error.message.includes("ECONNRESET") ||
      error.message.includes("ECONNABORTED") ||
      error.message.includes("timeout") ||
      error.message.includes("not initialized") ||
      error.message.includes("no longer available") ||
      error.code === "ETIMEDOUT" ||
      error.code === "ECONNRESET" ||
      error.code === "ECONNABORTED" ||
      error.code === "DB_CONNECTION_FAILED" ||
      error.code === "DB_POOL_NOT_AVAILABLE";

    if (isConnectionError) {
      console.error("Database connection error - should return 503");
      // Mark error so routes can detect this is a connection failure (503), not a query failure (500)
      error.code = "DB_CONNECTION_FAILED";
      error.httpStatus = 503;
      throw error;
    }

    // Always throw errors to expose issues instead of silently returning null
    console.error("Database query error:", {
      code: error.code,
      message: error.message,
      query:
        typeof text === "string" ? text.substring(0, 200) : "non-string query",
    });
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
    initPromise = null; // Reset init promise to allow re-initialization
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

/**
 * DATA INTEGRITY HELPERS - NO FALLBACK DEFAULTS
 * These functions ensure we return real data only (null for missing data)
 */

/**
 * Safe float conversion - returns null if value is null/undefined, otherwise parses
 * @param {any} value - The value to parse
 * @returns {number|null} - Parsed float or null
 */
function safeFloat(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = parseFloat(value);
  return isNaN(parsed) ? null : parsed;
}

/**
 * Safe integer conversion - returns null if value is null/undefined, otherwise parses
 * @param {any} value - The value to parse
 * @returns {number|null} - Parsed integer or null
 */
function safeInt(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = parseInt(value);
  return isNaN(parsed) ? null : parsed;
}

/**
 * Safe fixed decimal - returns null if value is null/undefined, otherwise formats
 * @param {any} value - The value to format
 * @param {number} decimals - Number of decimal places
 * @returns {string|null} - Formatted decimal or null
 */
function safeFixed(value, decimals = 2) {
  const num = safeFloat(value);
  return num === null ? null : num.toFixed(decimals);
}

module.exports = {
  initializeDatabase,
  initializeSchema,
  getPool,
  ensureConnection,
  getDbConfig,
  validateDbConfig,
  testConnection,
  query,
  transaction,
  closeDatabase,
  healthCheck,
  safeFloat,
  safeInt,
  safeFixed,
};

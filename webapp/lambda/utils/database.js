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
        const client = getSecretsManagerClient();
        const result = await client.send(command);

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
          max: parseInt(process.env.DB_POOL_MAX) || 3, // Lambda-optimized
          min: parseInt(process.env.DB_POOL_MIN) || 1,
          idleTimeoutMillis:
            parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 10000,
          connectionTimeoutMillis:
            parseInt(process.env.DB_CONNECT_TIMEOUT) || 3000,
          acquireTimeoutMillis:
            parseInt(process.env.DB_ACQUIRE_TIMEOUT) || 3000,
          createTimeoutMillis: parseInt(process.env.DB_CREATE_TIMEOUT) || 3000,
          statement_timeout:
            parseInt(process.env.DB_STATEMENT_TIMEOUT) || 30000,
          query_timeout: parseInt(process.env.DB_QUERY_TIMEOUT) || 25000,
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
        password: process.env.DB_PASSWORD || "",
        database,
        // AWS Lambda optimized connection pool settings
        max: parseInt(process.env.DB_POOL_MAX) || 3, // Reduced for Lambda - avoid connection exhaustion
        min: parseInt(process.env.DB_POOL_MIN) || 1, // Keep minimal connections
        idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 10000, // Shorter idle timeout
        connectionTimeoutMillis:
          parseInt(process.env.DB_CONNECT_TIMEOUT) || 3000, // Fast timeout for Lambda
        acquireTimeoutMillis: parseInt(process.env.DB_ACQUIRE_TIMEOUT) || 3000, // Quick acquire
        createTimeoutMillis: parseInt(process.env.DB_CREATE_TIMEOUT) || 3000, // Fast creation
        reapIntervalMillis: parseInt(process.env.DB_REAP_INTERVAL) || 1000, // Pool maintenance
        createRetryIntervalMillis:
          parseInt(process.env.DB_RETRY_INTERVAL) || 100, // Fast retries
        statement_timeout: parseInt(process.env.DB_STATEMENT_TIMEOUT) || 30000, // 30s max query time
        query_timeout: parseInt(process.env.DB_QUERY_TIMEOUT) || 25000, // 25s max per query
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

    // If no configuration is available, throw error to expose the issue
    const configError = new Error(
      "No database configuration found. Set DB_SECRET_ARN or DB_HOST environment variables."
    );
    configError.code = "NO_DB_CONFIG";
    throw configError;
  } catch (error) {
    // Re-throw configuration errors instead of silently returning null
    console.error("❌ Critical database configuration error:", {
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
 * Initialize database connection pool
 */
async function initializeDatabase() {
  if (initPromise) return initPromise;
  if (dbInitialized && pool) return pool;

  initPromise = (async () => {
    let config = null;
    try {
      if (process.env.NODE_ENV !== "test") {
        console.log("Initializing database connection pool...");
      }
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

      pool = new Pool(config);
      const client = await pool.connect();
      await client.query("SELECT NOW()");
      client.release();
      dbInitialized = true;
      console.log("✅ Database connection pool initialized successfully");

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
      console.error("❌ CRITICAL: Database initialization failed:", {
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
 * Initialize database schema
 * Market data tables are created by loader scripts
 * Webapp tables are created by webapp-db-init.js
 */
async function initializeSchema() {
  try {
    console.log("🚀 Initializing database schema...");

    // Import and run webapp table initialization
    const { initializeWebappTables } = require('../webapp-db-init');
    await initializeWebappTables();

    console.log("✅ Database schema initialization completed");
    return true;
  } catch (error) {
    console.error("❌ Schema initialization error:", error);
    // Don't throw - let the application continue with existing tables
    return false;
  }
}

/**
 * Insert initial data
 * Initial data is handled by webapp-db-init.js and loader scripts
 */
async function insertInitialData() {
  console.log("📊 Initial data insertion handled by webapp-db-init.js");
  return true;
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
      if (process.env.NODE_ENV !== "test") {
        console.log("Database not initialized, attempting initialization...");
      }
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
    const queryTimeout = parseInt(process.env.DB_QUERY_TIMEOUT) || 25000; // 25 seconds
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => {
        reject(
          new Error(
            `Query timeout after ${queryTimeout}ms: ${typeof text === 'string' ? text.slice(0, 100) : JSON.stringify(text).slice(0, 100)}...`
          )
        );
      }, queryTimeout);
    });

    // Log query details for debugging BEFORE execution
    if (text && text.includes && (text.includes('company_profile') || text.includes('SELECT'))) {
      console.log(`[QUERY STARTING] Query:`, {
        query: typeof text === 'string' ? text.slice(0, 200) + (text.length > 200 ? "..." : "") : "NON_STRING",
        param_count: params ? params.length : 0,
        params_sample: params ? params.slice(0, 3) : []
      });
    }

    const result = await Promise.race([
      pool.query(text, params),
      timeoutPromise,
    ]);

    queryDuration = Date.now() - start; // Calculate duration AFTER query completes

    // Log result details for debugging
    if (text && text.includes && (text.includes('company_profile') || text.includes('SELECT'))) {
      console.log(`[QUERY RESULT] After ${queryDuration}ms:`, {
        rows_returned: result && result.rows ? result.rows.length : 0,
        has_rows_property: result && 'rows' in result,
        result_type: result ? typeof result : 'null',
        result_keys: result ? Object.keys(result) : []
      });
    }

    // Enhanced performance monitoring based on testing insights
    if (queryDuration > 5000) {
      console.error(`⚠️ VERY SLOW QUERY detected (${queryDuration}ms):`, {
        query: text.slice(0, 150) + (text.length > 150 ? "..." : ""),
        rows: result.rowCount,
        duration: `${queryDuration}ms`,
      });
    } else if (queryDuration > 1000) {
      console.warn(`⏱️ Slow query (${queryDuration}ms):`, {
        query: typeof text === 'string' ? text.slice(0, 100) + (text.length > 100 ? "..." : "") : JSON.stringify(text).slice(0, 100) + "...",
        rows: result.rowCount,
        duration: `${queryDuration}ms`,
      });
    } else if (process.env.NODE_ENV === "development" && queryDuration > 500) {
      console.log(`📊 Query performance (${queryDuration}ms):`, {
        query: text.slice(0, 80) + (text.length > 80 ? "..." : ""),
        rows: result.rowCount,
      });
    }

    return result;
  } catch (error) {
    console.error("Database query error:", {
      error: error.message,
      query: typeof text === 'string' ? text.slice(0, 100) + (text.length > 100 ? "..." : "") : JSON.stringify(text).slice(0, 100) + "...",
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
      console.error("Database connection error - no fallback available");
      error.message = `Database connection failed: ${error.message}`;
      throw error;
    }

    // Always throw errors to expose issues instead of silently returning null
    // Previous behavior masked real database problems and made debugging impossible
    console.error("Database query error:", {
      code: error.code,
      message: error.message,
      query: typeof text === 'string' ? text.substring(0, 200) : "non-string query"
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
  getDbConfig,
  query,
  transaction,
  closeDatabase,
  healthCheck,
  safeFloat,
  safeInt,
  safeFixed,
};

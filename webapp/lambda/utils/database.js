const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { Pool } = require('pg');

// Configure AWS SDK v3
const secretsManager = new SecretsManagerClient({
    region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
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
                console.log('Getting DB credentials from Secrets Manager...');
                const command = new GetSecretValueCommand({ SecretId: secretArn });
                const result = await secretsManager.send(command);
                
                console.log('Secrets Manager response type:', typeof result.SecretString);
                console.log('Secrets Manager response preview:', result.SecretString?.substring(0, 100));
                console.log('First 5 characters:', JSON.stringify(result.SecretString?.substring(0, 5)));
                console.log('Is string?', typeof result.SecretString === 'string');
                console.log('Full SecretString:', result.SecretString);
                
                let secret;
                
                // Check if SecretString is already an object (parsed by AWS SDK)
                if (typeof result.SecretString === 'object' && result.SecretString !== null) {
                    console.log('SecretString is already an object, using directly');
                    secret = result.SecretString;
                } else if (typeof result.SecretString === 'string') {
                    try {
                        secret = JSON.parse(result.SecretString);
                    } catch (parseError) {
                        console.error('Failed to parse SecretString as JSON:', parseError);
                        console.error('Raw SecretString type:', typeof result.SecretString);
                        console.error('Raw SecretString length:', result.SecretString?.length);
                        console.error('Raw SecretString (escaped):', JSON.stringify(result.SecretString));
                        throw new Error(`Secret parsing failed: ${parseError.message}. Raw value type: ${typeof result.SecretString}, length: ${result.SecretString?.length}`);
                    }
                } else {
                    throw new Error(`Unexpected SecretString type: ${typeof result.SecretString}`)
                }
                
                dbConfig = {
                    host: secret.host || process.env.DB_ENDPOINT,
                    port: parseInt(secret.port) || 5432,
                    user: secret.username,
                    password: secret.password,
                    database: secret.dbname,
                    max: parseInt(process.env.DB_POOL_MAX) || 5,
                    idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
                    connectionTimeoutMillis: parseInt(process.env.DB_CONNECT_TIMEOUT) || 10000,
                    ssl: process.env.DB_SSL === 'false' ? false : {
                        rejectUnauthorized: false
                    }
                };
                
                console.log(`Database config loaded from Secrets Manager: ${dbConfig.host}:${dbConfig.port}/${dbConfig.database}`);
                return dbConfig;
            } catch (secretError) {
                console.warn('Failed to get secrets from Secrets Manager, falling back to environment variables:', secretError.message);
            }
        }
        
        // Fallback to environment variables if available
        if (process.env.DB_HOST || process.env.DB_ENDPOINT) {
            console.log('Using database config from environment variables');
            dbConfig = {
                host: process.env.DB_HOST || process.env.DB_ENDPOINT,
                port: parseInt(process.env.DB_PORT) || 5432,
                user: process.env.DB_USER || process.env.DB_USERNAME,
                password: process.env.DB_PASSWORD,
                database: process.env.DB_NAME || process.env.DB_DATABASE,
                max: parseInt(process.env.DB_POOL_MAX) || 5,
                idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
                connectionTimeoutMillis: parseInt(process.env.DB_CONNECT_TIMEOUT) || 10000,
                ssl: process.env.DB_SSL === 'false' ? false : {
                    rejectUnauthorized: false
                }
            };
            
            console.log(`Database config loaded from environment: ${dbConfig.host}:${dbConfig.port}/${dbConfig.database}`);
            return dbConfig;
        }
        
        // If no configuration is available, return null to indicate no database
        console.warn('No database configuration found. Set DB_SECRET_ARN or DB_HOST environment variables.');
        return null;
        
    } catch (error) {
        console.error('Error getting DB config:', error);
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
            console.log('Initializing database connection pool...');
            config = await getDbConfig();
            
            if (!config) {
                console.warn('No database configuration available. API will run in fallback mode with mock data.');
                dbInitialized = false;
                pool = null;
                return null; // Return null instead of throwing error
            }
            
            pool = new Pool(config);
            const client = await pool.connect();
            await client.query('SELECT NOW()');
            client.release();
            dbInitialized = true;
            console.log('✅ Database connection pool initialized successfully');
            pool.on('error', (err) => {
                console.error('Database pool error:', err);
                dbInitialized = false;
            });
            return pool;
        } catch (error) {
            dbInitialized = false;
            pool = null;
            // Attach config and env info to the error for debugging
            if (typeof config === 'undefined') config = null;
            error.config = config;
            error.env = {
                DB_SECRET_ARN: process.env.DB_SECRET_ARN,
                DB_ENDPOINT: process.env.DB_ENDPOINT,
                DB_HOST: process.env.DB_HOST,
                DB_PORT: process.env.DB_PORT,
                DB_NAME: process.env.DB_NAME,
                DB_USER: process.env.DB_USER
            };
            console.warn('Database initialization failed. API will run in fallback mode:', {
                error: error.message,
                config: config,
                env: error.env
            });
            return null; // Return null instead of throwing error
        } finally {
            initPromise = null;
        }
    })();

    return initPromise;
}

/**
 * Get the connection pool instance
 */
function getPool() {
    if (!pool || !dbInitialized) {
        throw new Error('Database not initialized. Call initializeDatabase() first.');
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
            console.log('Database not initialized, initializing now...');
            const result = await initializeDatabase();
            if (!result || !pool) {
                // Database is not available, throw error with specific message
                throw new Error('Database not available - running in fallback mode');
            }
        }
        
        // Check if pool is still valid
        if (!pool) {
            throw new Error('Database connection pool not available');
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
        console.error('Database query error:', {
            error: error.message,
            query: text.slice(0, 100) + (text.length > 100 ? '...' : ''),
            params: params
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
        await client.query('BEGIN');
        const result = await callback(client);
        await client.query('COMMIT');
        return result;
    } catch (error) {
        await client.query('ROLLBACK');
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
        
        const result = await query('SELECT NOW() as timestamp, version() as db_version');
        return {
            status: 'healthy',
            timestamp: result.rows[0].timestamp,
            version: result.rows[0].db_version,
            connections: pool.totalCount,
            idle: pool.idleCount,
            waiting: pool.waitingCount
        };
    } catch (error) {
        return {
            status: 'unhealthy',
            error: error.message
        };
    }
}

module.exports = {
    initializeDatabase,
    getPool,
    query,
    transaction,
    closeDatabase,
    healthCheck
};

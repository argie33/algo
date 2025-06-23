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

/**
 * Get database configuration from AWS Secrets Manager
 */
async function getDbConfig() {
    if (dbConfig) {
        return dbConfig;
    }

    try {
        console.log('Getting DB credentials from Secrets Manager...');
        const secretArn = process.env.DB_SECRET_ARN;
        if (!secretArn) {
            throw new Error('DB_SECRET_ARN environment variable not set');
        }
        
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        const result = await secretsManager.send(command);
        const secret = JSON.parse(result.SecretString);
        
        dbConfig = {
            host: secret.host || process.env.DB_ENDPOINT,
            port: parseInt(secret.port) || 5432,
            user: secret.username,
            password: secret.password,
            database: secret.dbname,
            // Connection pool settings optimized for Lambda
            max: parseInt(process.env.DB_POOL_MAX) || 5,
            idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
            connectionTimeoutMillis: parseInt(process.env.DB_CONNECT_TIMEOUT) || 10000,
            // SSL configuration for RDS
            ssl: {
                rejectUnauthorized: false
            }
        };
        
        console.log(`Database config loaded: ${dbConfig.host}:${dbConfig.port}/${dbConfig.database}`);
        return dbConfig;
    } catch (error) {
        console.error('Error getting DB config:', error);
        throw error;
    }
}

/**
 * Initialize database connection pool
 */
async function initializeDatabase() {
    // Return existing initialization promise if in progress
    if (initPromise) {
        return initPromise;
    }

    // Return immediately if already initialized
    if (dbInitialized && pool) {
        return pool;
    }

    initPromise = (async () => {
        try {
            console.log('Initializing database connection pool...');
            
            // Get database configuration
            const config = await getDbConfig();
            
            // Create connection pool
            pool = new Pool(config);
            
            // Test the connection
            const client = await pool.connect();
            await client.query('SELECT NOW()');
            client.release();
            
            dbInitialized = true;
            console.log('✅ Database connection pool initialized successfully');
            
            // Handle pool errors
            pool.on('error', (err) => {
                console.error('Database pool error:', err);
                dbInitialized = false;
            });
            
            return pool;
        } catch (error) {
            console.error('Failed to initialize database:', error);
            dbInitialized = false;
            pool = null;
            throw error;
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
            await initializeDatabase();
        }
        
        const start = Date.now();
        const result = await pool.query(text, params);
        const duration = Date.now() - start;
        
        console.log(`Query executed in ${duration}ms`, {
            rows: result.rowCount,
            query: text.slice(0, 100) + (text.length > 100 ? '...' : '')
        });
        
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
        console.log('Closing database connections...');
        await pool.end();
        pool = null;
        dbInitialized = false;
        dbConfig = null;
        console.log('Database connections closed');
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

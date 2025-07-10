// Load environment variables first
require('dotenv').config();

const { Pool } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

// Global state
let pool = null;
let dbInitialized = false;
let dbConfig = null;

// Configure AWS SDK for Secrets Manager
const secretsManager = new SecretsManagerClient({
    region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
});

/**
 * Get database configuration from AWS Secrets Manager
 */
async function getDbConfig() {
    if (dbConfig) {
        return dbConfig;
    }

    try {
        const secretArn = process.env.DB_SECRET_ARN;
        if (!secretArn) {
            throw new Error('DB_SECRET_ARN environment variable not set');
        }

        console.log('Getting DB credentials from Secrets Manager...');
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        const response = await secretsManager.send(command);
        const secret = JSON.parse(response.SecretString);

        dbConfig = {
            host: secret.host || process.env.DB_ENDPOINT,
            port: parseInt(secret.port) || 5432,
            database: secret.dbname || 'stocks',
            user: secret.username,
            password: secret.password,
            ssl: {
                require: true,
                rejectUnauthorized: false
            },
            max: parseInt(process.env.DB_POOL_MAX) || 3,
            idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
            connectionTimeoutMillis: parseInt(process.env.DB_CONNECT_TIMEOUT) || 20000
        };

        console.log('✅ Database config loaded from Secrets Manager:');
        console.log(`   🏠 Host: ${dbConfig.host}`);
        console.log(`   🔌 Port: ${dbConfig.port}`);
        console.log(`   🗄️  Database: ${dbConfig.database}`);
        console.log(`   👤 User: ${dbConfig.user}`);
        console.log(`   🔒 SSL: enabled`);
        console.log(`   🏊 Pool Max: ${dbConfig.max}`);

        return dbConfig;
    } catch (error) {
        console.error('❌ Failed to get database config:', error.message);
        throw error;
    }
}

/**
 * Initialize database connection pool
 */
async function initializeDatabase() {
    if (dbInitialized && pool) {
        return pool;
    }

    try {
        console.log('🔄 Initializing database connection pool...');
        
        const config = await getDbConfig();
        pool = new Pool(config);

        // Test connection with simple query
        console.log('🧪 Testing database connection...');
        const start = Date.now();
        
        const client = await Promise.race([
            pool.connect(),
            new Promise((_, reject) => 
                setTimeout(() => reject(new Error('Connection timeout after 10 seconds')), 10000)
            )
        ]);
        
        await client.query('SELECT 1');
        client.release();
        
        const duration = Date.now() - start;
        console.log(`✅ Database ready in ${duration}ms`);

        dbInitialized = true;
        return pool;
    } catch (error) {
        console.error('❌ Database initialization failed:', error.message);
        throw error;
    }
}

/**
 * Get database connection pool
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
async function query(text, params) {
    if (!dbInitialized || !pool) {
        await initializeDatabase();
    }
    return pool.query(text, params);
}

/**
 * Execute a transaction
 */
async function transaction(callback) {
    if (!dbInitialized || !pool) {
        await initializeDatabase();
    }

    const client = await pool.connect();
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
 * Simple robust health check - tests database connectivity and basic query
 */
async function healthCheck() {
    try {
        if (!dbInitialized || !pool) {
            await initializeDatabase();
        }
        
        const client = await Promise.race([
            pool.connect(),
            new Promise((_, reject) => 
                setTimeout(() => reject(new Error('Health check timeout')), 5000)
            )
        ]);
        
        const result = await client.query('SELECT NOW() as timestamp, current_database() as db, version() as version');
        client.release();
        
        return {
            status: 'healthy',
            database: result.rows[0].db,
            timestamp: result.rows[0].timestamp,
            version: result.rows[0].version.split(' ')[0],
            note: 'Database connection verified - does not test application tables'
        };
    } catch (error) {
        return {
            status: 'unhealthy',
            error: error.message
        };
    }
}

/**
 * Close database connections
 */
async function closeDatabase() {
    if (pool) {
        await pool.end();
        pool = null;
        dbInitialized = false;
        dbConfig = null;
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
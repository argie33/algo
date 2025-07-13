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
        console.log('✅ Using cached database config');
        return dbConfig;
    }

    const configStart = Date.now();
    try {
        const secretArn = process.env.DB_SECRET_ARN;
        if (!secretArn) {
            throw new Error('DB_SECRET_ARN environment variable not set');
        }

        console.log(`🔑 Getting DB credentials from Secrets Manager: ${secretArn}`);
        const secretStart = Date.now();
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        const response = await secretsManager.send(command);
        console.log(`✅ Secrets Manager responded in ${Date.now() - secretStart}ms`);
        
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
 * Execute a database query with timeout and detailed logging
 */
async function query(text, params = [], timeoutMs = 10000) {
    const queryId = Math.random().toString(36).substr(2, 9);
    const startTime = Date.now();
    
    console.log(`🔍 [${queryId}] QUERY START: ${text.substring(0, 100)}...`);
    console.log(`🔍 [${queryId}] Params:`, params);
    console.log(`🔍 [${queryId}] Timeout: ${timeoutMs}ms`);
    
    try {
        // Check if we need to initialize database
        if (!dbInitialized || !pool) {
            console.log(`🔄 [${queryId}] Database not initialized, initializing...`);
            const initStart = Date.now();
            await initializeDatabase();
            console.log(`✅ [${queryId}] Database initialized in ${Date.now() - initStart}ms`);
        }
        
        console.log(`📡 [${queryId}] Executing query...`);
        const queryStart = Date.now();
        
        // Execute query with timeout
        const result = await Promise.race([
            pool.query(text, params),
            new Promise((_, reject) => 
                setTimeout(() => reject(new Error(`Query timeout after ${timeoutMs}ms`)), timeoutMs)
            )
        ]);
        
        const queryDuration = Date.now() - queryStart;
        const totalDuration = Date.now() - startTime;
        
        console.log(`✅ [${queryId}] Query completed in ${queryDuration}ms (total: ${totalDuration}ms)`);
        console.log(`✅ [${queryId}] Rows returned: ${result.rows?.length || 0}`);
        
        return result;
        
    } catch (error) {
        const errorDuration = Date.now() - startTime;
        console.error(`❌ [${queryId}] Query failed after ${errorDuration}ms:`, error.message);
        console.error(`❌ [${queryId}] Error details:`, {
            code: error.code,
            severity: error.severity,
            detail: error.detail,
            hint: error.hint,
            position: error.position,
            internalPosition: error.internalPosition,
            internalQuery: error.internalQuery,
            where: error.where,
            schema: error.schema,
            table: error.table,
            column: error.column,
            dataType: error.dataType,
            constraint: error.constraint
        });
        throw error;
    }
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
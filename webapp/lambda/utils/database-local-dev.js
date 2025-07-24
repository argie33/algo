/**
 * Local Development Database Configuration
 * Bypasses AWS Secrets Manager for local development
 */

require('dotenv').config();
const { Pool } = require('pg');
const logger = require('./logger');

let pool = null;
let dbConfig = null;

/**
 * Get database configuration for local development
 */
function getLocalDbConfig() {
    if (dbConfig) {
        return dbConfig;
    }

    console.log('🔧 Configuring local development database...');
    
    // Use local environment variables directly
    dbConfig = {
        host: process.env.DB_HOST || 'localhost',
        port: parseInt(process.env.DB_PORT) || 5432,
        database: process.env.DB_NAME || 'stocks',
        user: process.env.DB_USER || 'postgres',
        password: process.env.DB_PASSWORD || 'postgres',
        ssl: process.env.DB_SSL === 'true' ? { rejectUnauthorized: false } : false,
        max: parseInt(process.env.DB_POOL_MAX) || 3,
        idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
        connectionTimeoutMillis: parseInt(process.env.DB_CONNECT_TIMEOUT) || 20000
    };

    console.log('✅ Local database config loaded:');
    console.log(`   🏗️ Host: ${dbConfig.host}:${dbConfig.port}`);
    console.log(`   📚 Database: ${dbConfig.database}`);
    console.log(`   👤 User: ${dbConfig.user}`);
    console.log(`   🔒 SSL: ${dbConfig.ssl ? 'enabled' : 'disabled'}`);

    return dbConfig;
}

/**
 * Initialize local database pool
 */
async function initLocalDatabase() {
    if (pool) {
        console.log('✅ Using existing local database pool');
        return pool;
    }

    try {
        const config = getLocalDbConfig();
        pool = new Pool(config);

        // Test connection
        const client = await pool.connect();
        console.log('✅ Local database connection successful');
        
        // Quick health check
        const result = await client.query('SELECT NOW() as current_time, version() as pg_version');
        console.log(`📊 Database time: ${result.rows[0].current_time}`);
        console.log(`🐘 PostgreSQL version: ${result.rows[0].pg_version.split(' ')[0]}`);
        
        client.release();
        
        // Set up pool event handlers
        pool.on('error', (err) => {
            console.error('❌ Local database pool error:', err);
        });

        pool.on('connect', () => {
            console.log('🔌 New local database client connected');
        });

        pool.on('remove', () => {
            console.log('🔌 Local database client removed from pool');
        });

        return pool;
    } catch (error) {
        console.error('❌ Failed to initialize local database:', error.message);
        throw error;
    }
}

/**
 * Get database pool (create if not exists)
 */
async function getPool() {
    if (!pool) {
        await initLocalDatabase();
    }
    return pool;
}

/**
 * Execute a query with error handling
 */
async function query(text, params = []) {
    const dbPool = await getPool();
    const client = await dbPool.connect();
    
    try {
        const start = Date.now();
        const result = await client.query(text, params);
        const duration = Date.now() - start;
        
        if (duration > 1000) {
            console.warn(`⚠️ Slow query (${duration}ms): ${text.substring(0, 100)}...`);
        }
        
        return result;
    } catch (error) {
        console.error('❌ Database query error:', error.message);
        console.error('   Query:', text.substring(0, 200));
        throw error;
    } finally {
        client.release();
    }
}

/**
 * Check database health
 */
async function checkHealth() {
    try {
        const result = await query('SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema = $1', ['public']);
        const tableCount = parseInt(result.rows[0].table_count);
        
        if (tableCount < 5) {
            return {
                status: 'unhealthy',
                message: `Only ${tableCount} tables found. Run setup script.`,
                details: { tableCount }
            };
        }
        
        return {
            status: 'healthy',
            message: `Database operational with ${tableCount} tables`,
            details: { tableCount }
        };
    } catch (error) {
        return {
            status: 'unhealthy',
            message: error.message,
            details: { error: error.message }
        };
    }
}

/**
 * Close database connections
 */
async function closeConnections() {
    if (pool) {
        console.log('🔌 Closing local database connections...');
        await pool.end();
        pool = null;
        dbConfig = null;
        console.log('✅ Local database connections closed');
    }
}

module.exports = {
    getPool,
    query,
    checkHealth,
    closeConnections,
    initLocalDatabase
};
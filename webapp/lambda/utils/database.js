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
        console.log('✅ Database already initialized, returning existing pool');
        return pool;
    }

    const initStart = Date.now();
    try {
        console.log('🔄 Initializing database connection pool...');
        
        const configStart = Date.now();
        const config = await getDbConfig();
        console.log(`✅ Database config retrieved in ${Date.now() - configStart}ms`);
        
        // Create pool with optimized settings for Lambda
        const poolConfig = {
            ...config,
            max: 2, // Reduced for Lambda
            idleTimeoutMillis: 10000, // Shorter timeout
            connectionTimeoutMillis: 5000, // Faster connection timeout
            acquireTimeoutMillis: 5000, // Shorter acquire timeout
            createTimeoutMillis: 5000, // Shorter create timeout
            destroyTimeoutMillis: 5000, // Shorter destroy timeout
            createRetryIntervalMillis: 500, // Faster retry
            reapIntervalMillis: 1000 // More frequent cleanup
        };
        
        console.log(`🏊 Creating pool with config:`, {
            host: poolConfig.host,
            port: poolConfig.port,
            database: poolConfig.database,
            max: poolConfig.max,
            connectionTimeoutMillis: poolConfig.connectionTimeoutMillis
        });
        
        const poolStart = Date.now();
        pool = new Pool(poolConfig);
        console.log(`✅ Pool created in ${Date.now() - poolStart}ms`);

        // Add pool event listeners for monitoring
        pool.on('connect', () => {
            console.log('🔗 Pool: New client connected');
        });

        pool.on('acquire', () => {
            console.log('📤 Pool: Client acquired from pool');
        });

        pool.on('remove', () => {
            console.log('🗑️ Pool: Client removed from pool');
        });

        pool.on('error', (err) => {
            console.error('💥 Pool error:', err.message);
        });

        // Test connection with shorter timeout and simpler query
        console.log('🧪 Testing database connection...');
        const testStart = Date.now();
        
        const client = await Promise.race([
            pool.connect(),
            new Promise((_, reject) => 
                setTimeout(() => reject(new Error('Connection test timeout after 3 seconds')), 3000)
            )
        ]);
        
        console.log(`✅ Client connected in ${Date.now() - testStart}ms`);
        
        // Use the simplest possible query
        const queryStart = Date.now();
        await client.query('SELECT 1 as test');
        console.log(`✅ Test query completed in ${Date.now() - queryStart}ms`);
        
        client.release();
        
        const totalDuration = Date.now() - initStart;
        console.log(`✅ Database fully initialized in ${totalDuration}ms`);

        dbInitialized = true;
        return pool;
    } catch (error) {
        const errorDuration = Date.now() - initStart;
        console.error(`❌ Database initialization failed after ${errorDuration}ms:`, {
            message: error.message,
            code: error.code,
            detail: error.detail,
            hint: error.hint
        });
        
        // Reset state on failure
        pool = null;
        dbInitialized = false;
        dbConfig = null;
        
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
 * Get detailed pool status for monitoring
 */
function getPoolStatus() {
    if (!pool) {
        return {
            initialized: false,
            error: 'Pool not initialized'
        };
    }
    
    return {
        initialized: dbInitialized,
        totalCount: pool.totalCount,
        idleCount: pool.idleCount,
        waitingCount: pool.waitingCount,
        max: pool.options.max,
        connectionTimeoutMillis: pool.options.connectionTimeoutMillis,
        idleTimeoutMillis: pool.options.idleTimeoutMillis
    };
}

/**
 * Execute a database query with timeout and detailed logging
 */
async function query(text, params = [], timeoutMs = 3000) {
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
 * Check if a table exists in the database
 */
async function tableExists(tableName) {
    try {
        if (!dbInitialized || !pool) {
            await initializeDatabase();
        }
        const result = await query(`
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = $1
            )
        `, [tableName]);
        
        return result.rows[0].exists;
    } catch (error) {
        console.error(`Error checking if table ${tableName} exists:`, error);
        return false;
    }
}

/**
 * Check if multiple tables exist
 */
async function tablesExist(tableNames) {
    try {
        if (!dbInitialized || !pool) {
            await initializeDatabase();
        }
        const result = await query(`
            SELECT table_name, 
                   EXISTS (
                       SELECT FROM information_schema.tables 
                       WHERE table_schema = 'public' 
                       AND table_name = t.table_name
                   ) as exists
            FROM unnest($1::text[]) AS t(table_name)
        `, [tableNames]);
        
        const existsMap = {};
        result.rows.forEach(row => {
            existsMap[row.table_name] = row.exists;
        });
        
        return existsMap;
    } catch (error) {
        console.error('Error checking if tables exist:', error);
        const fallbackMap = {};
        tableNames.forEach(name => {
            fallbackMap[name] = false;
        });
        return fallbackMap;
    }
}

/**
 * Safe query that checks table existence first
 */
async function safeQuery(text, params = [], requiredTables = []) {
    if (requiredTables.length > 0) {
        const tableExistenceMap = await tablesExist(requiredTables);
        const missingTables = requiredTables.filter(table => !tableExistenceMap[table]);
        
        if (missingTables.length > 0) {
            throw new Error(`Required tables not found: ${missingTables.join(', ')}`);
        }
    }
    
    return await query(text, params);
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
    getPoolStatus,
    query,
    safeQuery,
    tableExists,
    tablesExist,
    transaction,
    closeDatabase,
    healthCheck
};
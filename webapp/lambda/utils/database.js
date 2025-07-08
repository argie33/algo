const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { Pool } = require('pg');

// Configure AWS SDK v3 - Updated to trigger deployment for database connection fix v2
const secretsManager = new SecretsManagerClient({
    region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
});

// Connection pool instance
let pool = null;
let dbInitialized = false;
let initPromise = null;

// Database configuration cache
let dbConfig = null;

// console.log('*** DATABASE.JS PATCHED VERSION RUNNING - v2.1.0 ***');
// console.log('*** CONFIG SCOPE FIX APPLIED - ' + new Date().toISOString() + ' ***');

/**
 * Get database configuration from AWS Secrets Manager or environment variables
 */
async function getDbConfig() {
    if (dbConfig) {
        return dbConfig;
    }

    try {
        const secretArn = process.env.DB_SECRET_ARN;
        
        console.log('Environment check:', {
            DB_SECRET_ARN: secretArn ? 'SET' : 'MISSING',
            DB_ENDPOINT: process.env.DB_ENDPOINT ? 'SET' : 'MISSING',
            AWS_REGION: process.env.AWS_REGION || 'MISSING',
            NODE_ENV: process.env.NODE_ENV || 'MISSING'
        });
        
        // If we have a secret ARN, use Secrets Manager
        if (secretArn) {
            try {
                console.log('Getting DB credentials from Secrets Manager...');
                const command = new GetSecretValueCommand({ SecretId: secretArn });
                const result = await secretsManager.send(command);
                const secret = JSON.parse(result.SecretString);
                
                dbConfig = {
                    host: secret.host || process.env.DB_ENDPOINT,
                    port: parseInt(secret.port) || 5432,
                    user: secret.username,
                    password: secret.password,
                    database: secret.dbname,
                    max: parseInt(process.env.DB_POOL_MAX) || 5,
                    idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
                    connectionTimeoutMillis: parseInt(process.env.DB_CONNECT_TIMEOUT) || 10000,
                    ssl: {
                        rejectUnauthorized: false,
                        require: true
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
                    rejectUnauthorized: false,
                    require: true
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
 * Tables should be created via deployment-time Lambda (initDatabase.js)
 * This function now just verifies connection
 */
async function verifyConnection() {
    try {
        console.log('Verifying database connection...');
        await query('SELECT 1 as test');
        console.log('✅ Database connection verified');
        return true;
    } catch (error) {
        console.error('❌ Database connection failed:', error);
        return false;
    }
}

/**
 * Initialize database connection pool
 */
async function initializeDatabase() {
    if (initPromise) {
        console.log('⏳ Database initialization already in progress, waiting...');
        return initPromise;
    }
    if (dbInitialized && pool) {
        console.log('📊 Database already initialized');
        return pool;
    }

    initPromise = (async () => {
        let config = null;
        try {
            console.log('🔄 Initializing database connection pool...');
            config = await getDbConfig();
            
            if (!config) {
                console.warn('⚠️  No database configuration available. API will run in fallback mode with mock data.');
                dbInitialized = false;
                pool = null;
                return null; // Return null instead of throwing error
            }
            
            console.log('🔗 Database config loaded:', {
                host: config.host,
                port: config.port,
                database: config.database,
                user: config.user,
                ssl: config.ssl ? 'enabled' : 'disabled'
            });
            
            pool = new Pool(config);
            console.log('🧪 Testing database connection...');
            const client = await pool.connect();
            const result = await client.query('SELECT NOW() as current_time');
            console.log('✅ Database connection test successful');
            console.log('⏰ Database time:', result.rows[0].current_time);
            client.release();
            
            // Verify database connection
            console.log('🔍 Verifying database connection...');
            await verifyConnection();
            console.log('✅ Database connection verified');
            
            dbInitialized = true;
            console.log('🎉 Database connection pool initialized successfully');
            pool.on('error', (err) => {
                console.error('❌ Database pool error:', err);
                dbInitialized = false;
            });
            return pool;
        } catch (error) {
            dbInitialized = false;
            pool = null;
            console.error('❌ Database initialization failed:', error);
            console.error('🔍 Error details:', {
                message: error.message,
                code: error.code,
                syscall: error.syscall,
                hostname: error.hostname,
                port: error.port
            });
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
            console.log('🔄 Database not initialized, initializing now...');
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
        
        // Add timeout to prevent hanging queries
        const timeoutPromise = new Promise((_, reject) => {
            setTimeout(() => reject(new Error('Query timeout after 30 seconds')), 30000);
        });
        
        const result = await Promise.race([
            pool.query(text, params),
            timeoutPromise
        ]);
        
        const duration = Date.now() - start;
        
        // Only log slow queries (> 1000ms) or errors
        if (duration > 1000) {
            console.log(`⚠️  Slow query executed in ${duration}ms`, {
                query: text.substring(0, 200) + (text.length > 200 ? '...' : ''),
                params: params ? params.slice(0, 5) : []
            });
        }
        
        return result;
    } catch (error) {
        console.error('❌ Database query error:', {
            error: error.message,
            code: error.code,
            query: text.substring(0, 200) + (text.length > 200 ? '...' : ''),
            params: params ? params.slice(0, 5) : []
        });
        
        // Handle specific database errors
        if (error.code === 'ECONNREFUSED') {
            throw new Error('Database connection refused - check if database is running');
        } else if (error.code === '28000') {
            throw new Error('Database authentication failed - check credentials');
        } else if (error.code === '3D000') {
            throw new Error('Database does not exist');
        } else if (error.message.includes('timeout')) {
            throw new Error('Database query timeout - query took too long to execute');
        }
        
        throw error;
    }
}

// Add connection health monitoring
setInterval(async () => {
    if (pool && dbInitialized) {
        try {
            const client = await pool.connect();
            await client.query('SELECT 1');
            client.release();
        } catch (error) {
            console.error('❌ Database connection health check failed:', error);
            dbInitialized = false;
        }
    }
}, 60000); // Check every minute
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
        console.log('🔄 Starting database health check...');
        
        if (!dbInitialized || !pool) {
            console.log('🔄 Database not initialized, initializing...');
            await initializeDatabase();
        }
        
        if (!pool) {
            throw new Error('Database connection pool not available');
        }
        
        console.log('🧪 Testing basic database connection...');
        const result = await query('SELECT NOW() as timestamp, version() as db_version');
        console.log('✅ Basic database connection test passed');
        
        // Populate health_status table with current status
        console.log('📊 Populating health_status table...');
        await populateHealthStatusTable();
        
        // Get table health data
        const tableHealthData = await query(`
            SELECT 
                table_name,
                status,
                record_count,
                last_updated,
                last_checked,
                is_stale,
                error,
                table_category,
                critical_table
            FROM health_status 
            ORDER BY critical_table DESC, table_name ASC
        `);
        
        console.log(`✅ Health check completed - found ${tableHealthData.rows.length} tables`);
        
        return {
            status: 'healthy',
            timestamp: result.rows[0].timestamp,
            version: result.rows[0].db_version,
            connections: pool.totalCount,
            idle: pool.idleCount,
            waiting: pool.waitingCount,
            tables: tableHealthData.rows
        };
    } catch (error) {
        console.error('❌ Health check failed:', error);
        return {
            status: 'unhealthy',
            error: error.message,
            timestamp: new Date().toISOString()
        };
    }
}

// Function to populate health_status table with actual table data
async function populateHealthStatusTable() {
    try {
        console.log('🔄 Checking table health status...');
        
        // Define important tables to monitor
        const tablesToMonitor = [
            { name: 'users', category: 'core', critical: true },
            { name: 'user_api_keys', category: 'core', critical: true },
            { name: 'portfolio_holdings', category: 'portfolio', critical: true },
            { name: 'portfolio_metadata', category: 'portfolio', critical: true },
            { name: 'stock_symbols', category: 'data', critical: true },
            { name: 'stock_symbols_enhanced', category: 'data', critical: false },
            { name: 'watchlists', category: 'features', critical: false },
            { name: 'watchlist_items', category: 'features', critical: false },
            { name: 'user_notifications', category: 'features', critical: false },
            { name: 'user_preferences', category: 'features', critical: false }
        ];
        
        for (const table of tablesToMonitor) {
            try {
                // Check if table exists and get row count
                const tableExists = await query(`
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = $1
                    ) as exists
                `, [table.name]);
                
                if (tableExists.rows[0].exists) {
                    const countResult = await query(`SELECT COUNT(*) as count FROM ${table.name}`);
                    const recordCount = parseInt(countResult.rows[0].count);
                    
                    // Get last updated info if the table has updated_at column
                    let lastUpdated = null;
                    try {
                        const updateResult = await query(`
                            SELECT MAX(updated_at) as last_updated 
                            FROM ${table.name} 
                            WHERE updated_at IS NOT NULL
                        `);
                        lastUpdated = updateResult.rows[0].last_updated;
                    } catch (e) {
                        // Column might not exist, that's okay
                    }
                    
                    // Determine status based on record count and criticality
                    let status = 'healthy';
                    let error = null;
                    
                    if (table.critical && recordCount === 0) {
                        status = 'critical';
                        error = 'Critical table has no data';
                    } else if (recordCount === 0) {
                        status = 'warning';
                        error = 'Table has no data';
                    }
                    
                    // Update health_status table
                    await query(`
                        INSERT INTO health_status (
                            table_name, status, record_count, last_updated, 
                            last_checked, error, table_category, critical_table
                        ) VALUES ($1, $2, $3, $4, NOW(), $5, $6, $7)
                        ON CONFLICT (table_name) DO UPDATE SET
                            status = EXCLUDED.status,
                            record_count = EXCLUDED.record_count,
                            last_updated = EXCLUDED.last_updated,
                            last_checked = NOW(),
                            error = EXCLUDED.error,
                            table_category = EXCLUDED.table_category,
                            critical_table = EXCLUDED.critical_table,
                            updated_at = NOW()
                    `, [
                        table.name,
                        status,
                        recordCount,
                        lastUpdated,
                        error,
                        table.category,
                        table.critical
                    ]);
                    
                    console.log(`✅ ${table.name}: ${status} (${recordCount} records)`);
                } else {
                    // Table doesn't exist
                    await query(`
                        INSERT INTO health_status (
                            table_name, status, record_count, last_checked, 
                            error, table_category, critical_table
                        ) VALUES ($1, $2, $3, NOW(), $4, $5, $6)
                        ON CONFLICT (table_name) DO UPDATE SET
                            status = EXCLUDED.status,
                            record_count = EXCLUDED.record_count,
                            last_checked = NOW(),
                            error = EXCLUDED.error,
                            updated_at = NOW()
                    `, [
                        table.name,
                        'missing',
                        0,
                        'Table does not exist',
                        table.category,
                        table.critical
                    ]);
                    
                    console.log(`❌ ${table.name}: missing`);
                }
            } catch (error) {
                console.error(`❌ Error checking table ${table.name}:`, error);
                
                // Record the error in health_status
                await query(`
                    INSERT INTO health_status (
                        table_name, status, record_count, last_checked, 
                        error, table_category, critical_table
                    ) VALUES ($1, $2, $3, NOW(), $4, $5, $6)
                    ON CONFLICT (table_name) DO UPDATE SET
                        status = EXCLUDED.status,
                        last_checked = NOW(),
                        error = EXCLUDED.error,
                        updated_at = NOW()
                `, [
                    table.name,
                    'error',
                    0,
                    error.message,
                    table.category,
                    table.critical
                ]);
            }
        }
        
        console.log('✅ Health status table populated successfully');
    } catch (error) {
        console.error('❌ Error populating health_status table:', error);
        throw error;
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

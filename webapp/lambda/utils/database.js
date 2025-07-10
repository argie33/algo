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
        
        console.log('🔍 Environment check:', {
            DB_SECRET_ARN: secretArn ? `SET (${secretArn.substring(0, 20)}...)` : 'MISSING',
            DB_ENDPOINT: process.env.DB_ENDPOINT ? `SET (${process.env.DB_ENDPOINT})` : 'MISSING',
            AWS_REGION: process.env.AWS_REGION || 'MISSING',
            NODE_ENV: process.env.NODE_ENV || 'MISSING',
            VPC_INFO: {
                LAMBDA_RUNTIME_API: process.env.AWS_LAMBDA_RUNTIME_API ? 'IN_LAMBDA' : 'LOCAL',
                ENI_INFO: process.env._LAMBDA_SERVER_PORT ? 'VPC_ENABLED' : 'NO_VPC'
            }
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
                        require: true,
                        rejectUnauthorized: true
                    }
                };
                
                console.log(`✅ Database config loaded from Secrets Manager:`);
                console.log(`   🏠 Host: ${dbConfig.host}`);
                console.log(`   🔌 Port: ${dbConfig.port}`);
                console.log(`   🗄️  Database: ${dbConfig.database}`);
                console.log(`   👤 User: ${dbConfig.user}`);
                console.log(`   🔒 SSL: ${dbConfig.ssl ? 'enabled' : 'disabled'}`);
                console.log(`   🏊 Pool Max: ${dbConfig.max}`);
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
                ssl: {
                    require: true,
                    rejectUnauthorized: true
                }
            };
            
            console.log(`✅ Database config loaded from environment:`);
            console.log(`   🏠 Host: ${dbConfig.host}`);
            console.log(`   🔌 Port: ${dbConfig.port}`);
            console.log(`   🗄️  Database: ${dbConfig.database}`);
            console.log(`   👤 User: ${dbConfig.user}`);
            console.log(`   🔒 SSL: ${dbConfig.ssl ? 'enabled' : 'disabled'}`);
            console.log(`   🏊 Pool Max: ${dbConfig.max}`);
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
            
            console.log('🔗 Database config summary:', {
                host: config.host,
                port: config.port,
                database: config.database,
                user: config.user,
                ssl: config.ssl ? 'enabled' : 'disabled',
                max_connections: config.max,
                connect_timeout: config.connectionTimeoutMillis + 'ms',
                idle_timeout: config.idleTimeoutMillis + 'ms'
            });
            
            pool = new Pool(config);
            console.log('🧪 Testing database connection...');
            
            // Add detailed connection logging
            const connectionStart = Date.now();
            console.log(`🔌 Attempting to connect to ${config.host}:${config.port}...`);
            
            const client = await pool.connect();
            const connectionTime = Date.now() - connectionStart;
            console.log(`⚡ Connection established in ${connectionTime}ms`);
            
            const queryStart = Date.now();
            const result = await client.query('SELECT NOW() as current_time, version() as db_version, current_database() as db_name, current_user as db_user');
            const queryTime = Date.now() - queryStart;
            
            console.log('✅ Database connection test successful');
            console.log(`   ⏰ Database time: ${result.rows[0].current_time}`);
            console.log(`   🗄️  Database name: ${result.rows[0].db_name}`);
            console.log(`   👤 Connected as: ${result.rows[0].db_user}`);
            console.log(`   📊 Version: ${result.rows[0].db_version.split(' ')[0]}`);
            console.log(`   ⚡ Query time: ${queryTime}ms`);
            
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
            console.error('🔍 Detailed error analysis:', {
                message: error.message,
                code: error.code,
                syscall: error.syscall,
                hostname: error.hostname,
                port: error.port,
                errno: error.errno,
                stack: error.stack?.split('\n')[0]
            });
            
            // Network connectivity debugging
            if (error.code === 'ECONNREFUSED') {
                console.error('❌ Connection refused - database server may be down or unreachable');
                console.error('🔍 Troubleshooting steps:');
                console.error('   1. Check if database server is running');
                console.error('   2. Verify host and port are correct');
                console.error('   3. Check security group allows inbound on port 5432');
                console.error('   4. Verify Lambda is in correct VPC/subnets');
            } else if (error.code === 'ETIMEDOUT') {
                console.error('⏱️  Connection timeout - network or firewall issue');
                console.error('🔍 Troubleshooting steps:');
                console.error('   1. Check VPC route tables');
                console.error('   2. Verify Lambda and DB are in compatible subnets');
                console.error('   3. Check security group rules');
                console.error('   4. Verify NAT Gateway/Internet Gateway if needed');
            } else if (error.code === 'ENOTFOUND') {
                console.error('🌐 DNS resolution failed - hostname not found');
                console.error('🔍 Troubleshooting steps:');
                console.error('   1. Verify DB_ENDPOINT/host is correct');
                console.error('   2. Check VPC DNS settings');
                console.error('   3. Ensure RDS endpoint is accessible from Lambda VPC');
            }
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
        
        // Handle specific database errors with detailed troubleshooting
        if (error.code === 'ECONNREFUSED') {
            throw new Error(`Database connection refused to ${dbConfig?.host || 'unknown'}:${dbConfig?.port || 'unknown'} - check if database is running and security groups allow access`);
        } else if (error.code === '28000') {
            throw new Error('Database authentication failed - check username/password in Secrets Manager');
        } else if (error.code === '3D000') {
            throw new Error(`Database '${dbConfig?.database || 'unknown'}' does not exist`);
        } else if (error.code === 'ETIMEDOUT') {
            throw new Error(`Connection timeout to ${dbConfig?.host || 'unknown'} - check VPC routing and security groups`);
        } else if (error.code === 'ENOTFOUND') {
            throw new Error(`DNS lookup failed for ${dbConfig?.host || 'unknown'} - check hostname and VPC DNS settings`);
        } else if (error.message.includes('timeout')) {
            throw new Error('Database query timeout - query took too long to execute');
        }
        
        throw error;
    }
}

// Add connection health monitoring with detailed logging
let healthCheckCount = 0;
setInterval(async () => {
    if (pool && dbInitialized) {
        healthCheckCount++;
        try {
            const start = Date.now();
            const client = await pool.connect();
            await client.query('SELECT 1');
            client.release();
            const duration = Date.now() - start;
            
            // Only log every 10th health check to reduce noise
            if (healthCheckCount % 10 === 0) {
                console.log(`✅ Database health check #${healthCheckCount} passed (${duration}ms) - Pool: ${pool.totalCount} total, ${pool.idleCount} idle`);
            }
        } catch (error) {
            console.error(`❌ Database connection health check #${healthCheckCount} failed:`, {
                error: error.message,
                code: error.code,
                pool_stats: pool ? {
                    total: pool.totalCount,
                    idle: pool.idleCount,
                    waiting: pool.waitingCount
                } : 'pool_unavailable'
            });
            dbInitialized = false;
        }
    }
}, 60000); // Check every minute

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
 * Test network connectivity to database host
 */
async function testNetworkConnectivity() {
    try {
        const config = await getDbConfig();
        if (!config) {
            return { status: 'no_config', message: 'No database configuration available' };
        }
        
        console.log(`🌐 Testing network connectivity to ${config.host}:${config.port}...`);
        
        // Use a simple TCP connection test with timeout
        const net = require('net');
        
        return new Promise((resolve) => {
            const socket = new net.Socket();
            const timeout = 10000; // 10 seconds
            
            const timer = setTimeout(() => {
                socket.destroy();
                resolve({
                    status: 'timeout',
                    message: `Connection timeout after ${timeout}ms`,
                    host: config.host,
                    port: config.port
                });
            }, timeout);
            
            socket.connect(config.port, config.host, () => {
                clearTimeout(timer);
                socket.destroy();
                resolve({
                    status: 'success',
                    message: 'TCP connection successful',
                    host: config.host,
                    port: config.port
                });
            });
            
            socket.on('error', (error) => {
                clearTimeout(timer);
                socket.destroy();
                resolve({
                    status: 'error',
                    message: error.message,
                    code: error.code,
                    host: config.host,
                    port: config.port
                });
            });
        });
    } catch (error) {
        return {
            status: 'error',
            message: error.message,
            error: error
        };
    }
}

/**
 * Health check for database
 */
async function healthCheck() {
    try {
        console.log('🔄 Starting comprehensive database health check...');
        
        // First test network connectivity
        console.log('🌐 Step 1: Testing network connectivity...');
        const networkTest = await testNetworkConnectivity();
        console.log(`🌐 Network test result: ${networkTest.status} - ${networkTest.message}`);
        
        if (!dbInitialized || !pool) {
            console.log('🔄 Step 2: Database not initialized, initializing...');
            await initializeDatabase();
        }
        
        if (!pool) {
            throw new Error('Database connection pool not available after initialization');
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
    healthCheck,
    testNetworkConnectivity
};

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
 * Create required tables if they don't exist
 */
async function createRequiredTables() {
    try {
        console.log('Checking and creating required tables...');
        
        // Users table (required for user management)
        await query(`
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(255) PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                phone VARCHAR(20),
                timezone VARCHAR(50) DEFAULT 'America/New_York',
                currency VARCHAR(10) DEFAULT 'USD',
                two_factor_enabled BOOLEAN DEFAULT FALSE,
                two_factor_secret VARCHAR(255),
                recovery_codes TEXT,
                deleted_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        `);
        
        // User indexes
        await query(`CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);`);
        await query(`CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON users(deleted_at);`);
        
        // User notification preferences
        await query(`
            CREATE TABLE IF NOT EXISTS user_notification_preferences (
                user_id VARCHAR(255) PRIMARY KEY REFERENCES users(id),
                email_notifications BOOLEAN DEFAULT TRUE,
                push_notifications BOOLEAN DEFAULT TRUE,
                price_alerts BOOLEAN DEFAULT TRUE,
                portfolio_updates BOOLEAN DEFAULT TRUE,
                market_news BOOLEAN DEFAULT FALSE,
                weekly_reports BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        `);
        
        // User theme preferences
        await query(`
            CREATE TABLE IF NOT EXISTS user_theme_preferences (
                user_id VARCHAR(255) PRIMARY KEY REFERENCES users(id),
                dark_mode BOOLEAN DEFAULT FALSE,
                primary_color VARCHAR(20) DEFAULT '#1976d2',
                chart_style VARCHAR(50) DEFAULT 'candlestick',
                layout VARCHAR(50) DEFAULT 'standard',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        `);
        
        // API Keys table
        await query(`
            CREATE TABLE IF NOT EXISTS user_api_keys (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                provider VARCHAR(50) NOT NULL,
                encrypted_api_key TEXT NOT NULL,
                key_iv VARCHAR(32) NOT NULL,
                key_auth_tag VARCHAR(32) NOT NULL,
                encrypted_api_secret TEXT,
                secret_iv VARCHAR(32),
                secret_auth_tag VARCHAR(32),
                user_salt VARCHAR(32) NOT NULL,
                is_sandbox BOOLEAN DEFAULT true,
                is_active BOOLEAN DEFAULT true,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                UNIQUE(user_id, provider)
            );
        `);
        
        // API Keys indexes
        await query(`CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id);`);
        await query(`CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider);`);
        await query(`CREATE INDEX IF NOT EXISTS idx_user_api_keys_active ON user_api_keys(is_active);`);
        
        // Portfolio holdings table
        await query(`
            CREATE TABLE IF NOT EXISTS portfolio_holdings (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                api_key_id INTEGER REFERENCES user_api_keys(id) ON DELETE CASCADE,
                symbol VARCHAR(10) NOT NULL,
                quantity DECIMAL(15, 6) NOT NULL,
                avg_cost DECIMAL(15, 4),
                current_price DECIMAL(15, 4),
                market_value DECIMAL(15, 2),
                unrealized_pl DECIMAL(15, 2),
                unrealized_plpc DECIMAL(8, 4),
                side VARCHAR(10) CHECK (side IN ('long', 'short')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, symbol, api_key_id)
            );
        `);
        
        // Portfolio metadata table
        await query(`
            CREATE TABLE IF NOT EXISTS portfolio_metadata (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                api_key_id INTEGER REFERENCES user_api_keys(id) ON DELETE CASCADE,
                total_equity DECIMAL(15, 2),
                total_market_value DECIMAL(15, 2),
                total_unrealized_pl DECIMAL(15, 2),
                total_unrealized_plpc DECIMAL(8, 4),
                account_type VARCHAR(50),
                last_sync TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, api_key_id)
            );
        `);
        
        // Health status table (with comprehensive structure)
        await query(`
            CREATE TABLE IF NOT EXISTS health_status (
                table_name VARCHAR(255) PRIMARY KEY,
                status VARCHAR(50) NOT NULL DEFAULT 'unknown',
                record_count BIGINT DEFAULT 0,
                missing_data_count BIGINT DEFAULT 0,
                last_updated TIMESTAMP WITH TIME ZONE,
                last_checked TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                is_stale BOOLEAN DEFAULT FALSE,
                error TEXT,
                table_category VARCHAR(100),
                critical_table BOOLEAN DEFAULT FALSE,
                expected_update_frequency INTERVAL DEFAULT '1 day',
                size_bytes BIGINT DEFAULT 0,
                last_vacuum TIMESTAMP WITH TIME ZONE,
                last_analyze TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        `);
        
        // Health status indexes
        await query(`CREATE INDEX IF NOT EXISTS idx_health_status_status ON health_status(status);`);
        await query(`CREATE INDEX IF NOT EXISTS idx_health_status_category ON health_status(table_category);`);
        await query(`CREATE INDEX IF NOT EXISTS idx_health_status_critical ON health_status(critical_table);`);
        
        console.log('✅ Required tables created successfully');
    } catch (error) {
        console.error('Error creating required tables:', error);
        throw error;
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
            
            // Create required tables
            console.log('🏗️  Creating required database tables...');
            await createRequiredTables();
            console.log('✅ Database tables created successfully');
            
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

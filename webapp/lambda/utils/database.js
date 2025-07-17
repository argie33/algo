// Load environment variables first
require('dotenv').config();

const { Pool } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { getTimeout, withDatabaseTimeout } = require('./timeoutManager');

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
        
        let secret;
        try {
            secret = JSON.parse(response.SecretString);
        } catch (parseError) {
            console.error('❌ Failed to parse secret JSON:', parseError.message);
            console.error('❌ Raw secret string:', response.SecretString);
            throw new Error(`Database configuration failed: ${parseError.message}`);
        }

        dbConfig = {
            host: secret.host || process.env.DB_ENDPOINT,
            port: parseInt(secret.port) || 5432,
            database: secret.dbname || 'stocks',
            user: secret.username,
            password: secret.password,
            ssl: false, // Match working ECS task configuration - no SSL for RDS in public subnets
            max: parseInt(process.env.DB_POOL_MAX) || 3,
            idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
            connectionTimeoutMillis: parseInt(process.env.DB_CONNECT_TIMEOUT) || 20000
        };

        console.log('✅ Database config loaded from Secrets Manager successfully');
        console.log(`   🔒 SSL: enabled`);
        console.log(`   🏊 Pool Max: ${dbConfig.max}`);

        return dbConfig;
    } catch (error) {
        console.error('❌ Failed to get database config:', error.message);
        throw error;
    }
}

/**
 * Calculate optimal pool configuration based on environment and expected load
 */
function calculateOptimalPoolConfig() {
    // Environment detection
    const isLambda = !!process.env.AWS_LAMBDA_FUNCTION_NAME;
    const nodeEnv = process.env.NODE_ENV || 'development';
    const isProduction = nodeEnv === 'production';
    
    // Lambda concurrent execution limits and expected load
    const lambdaConcurrency = parseInt(process.env.LAMBDA_CONCURRENT_EXECUTIONS) || 10;
    const expectedUsers = parseInt(process.env.EXPECTED_CONCURRENT_USERS) || 25;
    
    let poolConfig;
    
    if (isLambda) {
        // Lambda-specific pool configuration
        // Each Lambda execution needs 1-2 connections depending on the request
        const baseConnections = Math.min(lambdaConcurrency, 5); // Base connections
        const maxConnections = Math.min(lambdaConcurrency * 2, 20); // Max for bursts
        
        poolConfig = {
            min: Math.max(1, Math.floor(baseConnections / 2)), // Keep some connections alive
            max: maxConnections,
            // Aggressive acquisition for Lambda
            acquireTimeoutMillis: 8000,
            createTimeoutMillis: 15000,
        };
        
        console.log(`🏊 Lambda pool config: ${poolConfig.min}-${poolConfig.max} connections for ${lambdaConcurrency} concurrent executions`);
        
    } else {
        // Local development or container-based deployment
        const baseConnections = isProduction ? 
            Math.min(Math.ceil(expectedUsers / 3), 15) : // Production: assume 3 users per connection
            3; // Development: small pool
            
        const maxConnections = isProduction ?
            Math.min(expectedUsers, 50) : // Production: scale with users
            5; // Development: limited
            
        poolConfig = {
            min: Math.max(1, Math.floor(baseConnections / 2)),
            max: maxConnections,
            acquireTimeoutMillis: 10000,
            createTimeoutMillis: 20000,
        };
        
        console.log(`🏊 ${isProduction ? 'Production' : 'Development'} pool config: ${poolConfig.min}-${poolConfig.max} connections for ${expectedUsers} expected users`);
    }
    
    // Override from environment variables if provided
    if (process.env.DB_POOL_MIN) {
        poolConfig.min = parseInt(process.env.DB_POOL_MIN);
    }
    if (process.env.DB_POOL_MAX) {
        poolConfig.max = parseInt(process.env.DB_POOL_MAX);
    }
    
    // Validate configuration
    poolConfig.min = Math.max(1, poolConfig.min);
    poolConfig.max = Math.max(poolConfig.min, poolConfig.max);
    poolConfig.max = Math.min(poolConfig.max, 100); // Hard limit for safety
    
    console.log(`🎯 Final pool configuration: min=${poolConfig.min}, max=${poolConfig.max}`);
    
    return poolConfig;
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
        
        // Dynamic connection pool sizing based on Lambda concurrency
        const dynamicPoolConfig = calculateOptimalPoolConfig();
        
        const poolConfig = {
            ...config,
            ...dynamicPoolConfig,
            idleTimeoutMillis: 30000, // Longer timeout for Lambda
            connectionTimeoutMillis: 15000, // Longer timeout for cold starts
            acquireTimeoutMillis: 10000, // Longer acquire timeout for cold starts
            createTimeoutMillis: 15000, // Longer create timeout for cold starts
            destroyTimeoutMillis: 5000, // Keep destroy timeout short
            createRetryIntervalMillis: 1000, // Slower retry for stability
            reapIntervalMillis: 5000, // Less frequent cleanup for Lambda
            keepAlive: true, // Keep connections alive
            keepAliveInitialDelayMillis: 10000,
            // Advanced pool management
            allowExitOnIdle: false, // Don't exit when idle
            acquireTimeoutMillis: 8000, // Reasonable timeout for acquiring connections
            propagateCreateError: false, // Don't propagate connection creation errors immediately
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

        // Enhanced pool monitoring for concurrent user scaling
        pool.on('acquire', () => {
            console.log('📤 Pool: Client acquired from pool');
            updatePoolMetrics('acquire');
        });

        pool.on('release', () => {
            console.log('📥 Pool: Client released to pool');
            updatePoolMetrics('release');
        });

        // Test connection with shorter timeout and simpler query
        console.log('🧪 Testing database connection...');
        const testStart = Date.now();
        
        const client = await Promise.race([
            pool.connect(),
            new Promise((_, reject) => 
                setTimeout(() => reject(new Error('Connection test timeout after 15 seconds')), 15000)
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
        
        // Start pool monitoring for concurrent user scaling
        startPoolMonitoring();
        
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
 * Start pool monitoring for concurrent user scaling
 */
function startPoolMonitoring() {
    if (!pool) return;
    
    console.log('📊 Starting pool monitoring for concurrent user scaling...');
    
    // Pool monitoring only in development environment to avoid Lambda memory leaks
    if (process.env.NODE_ENV === 'development') {
        const monitorInterval = setInterval(() => {
            if (!pool || !dbInitialized) return;
            
            const status = getPoolStatus();
            const { metrics, recommendations } = status;
            
            // Log status if utilization is high or recommendations available
            if (metrics.utilizationPercent > 70 || recommendations.currentStats) {
                console.log(`📊 Pool Status: ${status.totalCount}/${status.max} connections (${metrics.utilizationPercent}% util), ${status.waitingCount} waiting`);
                
                if (recommendations.reason !== 'Current configuration optimal') {
                    console.log(`💡 ${recommendations.reason}`);
                }
            }
            
            // Warn on high utilization
            if (metrics.utilizationPercent > 90) {
                console.warn(`⚠️ Pool utilization very high (${metrics.utilizationPercent}%) - consider scaling up`);
            }
            
            // Warn on connection queue buildup
            if (status.waitingCount > 5) {
                console.warn(`⚠️ ${status.waitingCount} connections waiting - pool may be undersized`);
            }
            
            // Warn on high error rate
            if (metrics.errorRate > 0.1) {
                console.warn(`⚠️ High connection error rate: ${Math.round(metrics.errorRate * 100)}%`);
            }
            
        }, 30000); // Every 30 seconds
        
        console.log('✅ Pool monitoring started (development mode)');
        
        // Clear interval on process exit to prevent memory leaks
        process.on('exit', () => clearInterval(monitorInterval));
        process.on('SIGINT', () => clearInterval(monitorInterval));
        process.on('SIGTERM', () => clearInterval(monitorInterval));
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

// Pool metrics for monitoring and adaptive scaling
let poolMetrics = {
    acquireCount: 0,
    releaseCount: 0,
    peakConnections: 0,
    averageAcquireTime: 0,
    connectionErrors: 0,
    lastAcquireTime: 0,
    startTime: Date.now(),
    // Adaptive scaling metrics - fixed size arrays to prevent memory leaks
    recentAcquires: new Array(100).fill(0), // Circular buffer for last 100 acquires
    recentReleases: new Array(100).fill(0), // Circular buffer for last 100 releases
    acquireIndex: 0,
    releaseIndex: 0,
    adaptiveRecommendations: {
        suggestedMin: null,
        suggestedMax: null,
        lastRecommendation: 0
    }
};

/**
 * Update pool metrics for monitoring and adaptive scaling
 */
function updatePoolMetrics(event) {
    const now = Date.now();
    
    switch (event) {
        case 'acquire':
            poolMetrics.acquireCount++;
            poolMetrics.lastAcquireTime = now;
            
            // Use circular buffer to prevent memory leaks
            poolMetrics.recentAcquires[poolMetrics.acquireIndex] = now;
            poolMetrics.acquireIndex = (poolMetrics.acquireIndex + 1) % poolMetrics.recentAcquires.length;
            
            // Track peak connections
            if (pool && pool.totalCount > poolMetrics.peakConnections) {
                poolMetrics.peakConnections = pool.totalCount;
            }
            break;
            
        case 'release':
            poolMetrics.releaseCount++;
            
            // Use circular buffer to prevent memory leaks
            poolMetrics.recentReleases[poolMetrics.releaseIndex] = now;
            poolMetrics.releaseIndex = (poolMetrics.releaseIndex + 1) % poolMetrics.recentReleases.length;
            break;
            
        case 'error':
            poolMetrics.connectionErrors++;
            break;
    }
    
    // Generate adaptive recommendations every 2 minutes
    if (now - poolMetrics.adaptiveRecommendations.lastRecommendation > 120000) {
        generateAdaptiveRecommendations();
        poolMetrics.adaptiveRecommendations.lastRecommendation = now;
    }
}

/**
 * Generate adaptive pool sizing recommendations based on usage patterns
 */
function generateAdaptiveRecommendations() {
    if (!pool || poolMetrics.recentAcquires.length < 3) {
        return; // Not enough data
    }
    
    const now = Date.now();
    const fiveMinutesAgo = now - 300000;
    const recentAcquires = poolMetrics.recentAcquires.filter(time => time > fiveMinutesAgo);
    const recentReleases = poolMetrics.recentReleases.filter(time => time > fiveMinutesAgo);
    
    // Calculate concurrent connection usage pattern
    const avgAcquiresPerMinute = recentAcquires.length / 5;
    const avgReleasesPerMinute = recentReleases.length / 5;
    const currentUtilization = pool.totalCount / pool.options.max;
    
    let recommendations = {
        suggestedMin: pool.options.min,
        suggestedMax: pool.options.max,
        reason: 'Current configuration optimal'
    };
    
    // High utilization - recommend scaling up
    if (currentUtilization > 0.8 && avgAcquiresPerMinute > avgReleasesPerMinute) {
        recommendations.suggestedMax = Math.min(pool.options.max * 1.5, 50);
        recommendations.suggestedMin = Math.min(pool.options.min + 2, recommendations.suggestedMax / 2);
        recommendations.reason = 'High utilization detected - recommend scaling up';
    }
    
    // Low utilization - recommend scaling down (but conservatively)
    else if (currentUtilization < 0.3 && pool.options.max > 5) {
        recommendations.suggestedMax = Math.max(pool.options.max * 0.8, 5);
        recommendations.suggestedMin = Math.max(pool.options.min - 1, 1);
        recommendations.reason = 'Low utilization detected - consider scaling down';
    }
    
    // High error rate - recommend more conservative settings
    else if (poolMetrics.connectionErrors > 5) {
        recommendations.suggestedMax = Math.max(pool.options.max - 2, 3);
        recommendations.reason = 'High error rate - recommend more conservative pool size';
    }
    
    poolMetrics.adaptiveRecommendations = {
        ...recommendations,
        lastRecommendation: Date.now(),
        currentStats: {
            utilization: currentUtilization,
            acquiresPerMinute: avgAcquiresPerMinute,
            releasesPerMinute: avgReleasesPerMinute,
            errorRate: poolMetrics.connectionErrors / Math.max(poolMetrics.acquireCount, 1)
        }
    };
    
    // Log recommendations if significant change suggested
    if (Math.abs(recommendations.suggestedMax - pool.options.max) > 2) {
        console.log(`🎯 Pool scaling recommendation: ${pool.options.min}-${pool.options.max} → ${recommendations.suggestedMin}-${recommendations.suggestedMax} (${recommendations.reason})`);
    }
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
    
    const now = Date.now();
    const uptimeSeconds = Math.floor((now - poolMetrics.startTime) / 1000);
    
    return {
        initialized: dbInitialized,
        // Current pool state
        totalCount: pool.totalCount,
        idleCount: pool.idleCount,
        waitingCount: pool.waitingCount,
        min: pool.options.min,
        max: pool.options.max,
        connectionTimeoutMillis: pool.options.connectionTimeoutMillis,
        idleTimeoutMillis: pool.options.idleTimeoutMillis,
        // Performance metrics
        metrics: {
            ...poolMetrics,
            uptimeSeconds,
            utilizationPercent: Math.round((pool.totalCount / pool.options.max) * 100),
            acquiresPerSecond: poolMetrics.acquireCount / Math.max(uptimeSeconds, 1),
            errorRate: poolMetrics.connectionErrors / Math.max(poolMetrics.acquireCount, 1)
        },
        // Adaptive recommendations
        recommendations: poolMetrics.adaptiveRecommendations
    };
}

/**
 * Execute a database query with timeout and detailed logging
 */
async function query(text, params = [], timeoutMs = null) {
    // Use standardized timeout if not provided
    const actualTimeout = timeoutMs || getTimeout('database', 'query');
    const queryId = Math.random().toString(36).substr(2, 9);
    const startTime = Date.now();
    
    console.log(`🔍 [${queryId}] QUERY START: ${text.substring(0, 100)}...`);
    console.log(`🔍 [${queryId}] Params:`, params);
    console.log(`🔍 [${queryId}] Timeout: ${actualTimeout}ms`);
    
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
        
        // Execute query with optimized timeout implementation
        let timeoutHandle;
        const timeoutPromise = new Promise((_, reject) => {
            timeoutHandle = setTimeout(() => reject(new Error(`Query timeout after ${actualTimeout}ms`)), actualTimeout);
        });
        
        const result = await Promise.race([
            pool.query(text, params),
            timeoutPromise
        ]);
        
        // Clear timeout to prevent memory leaks
        clearTimeout(timeoutHandle);
        
        const queryDuration = Date.now() - queryStart;
        const totalDuration = Date.now() - startTime;
        
        console.log(`✅ [${queryId}] Query completed in ${queryDuration}ms (total: ${totalDuration}ms)`);
        console.log(`✅ [${queryId}] Rows returned: ${result.rows?.length || 0}`);
        
        // Track performance metrics
        try {
            const { performanceMonitor } = require('./performanceMonitor');
            const operation = text.trim().split(' ')[0].toUpperCase();
            const table = extractTableName(text);
            performanceMonitor.trackDbOperation(operation, table, queryDuration, true, queryId);
        } catch (perfError) {
            // Don't fail the query if performance monitoring fails
            console.warn('Performance monitoring failed:', perfError.message);
        }
        
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
        
        // Update pool metrics for connection errors
        updatePoolMetrics('error');
        
        // Track performance metrics for failed queries
        try {
            const { performanceMonitor } = require('./performanceMonitor');
            const operation = text.trim().split(' ')[0].toUpperCase();
            const table = extractTableName(text);
            performanceMonitor.trackDbOperation(operation, table, errorDuration, false, queryId);
        } catch (perfError) {
            console.warn('Performance monitoring failed:', perfError.message);
        }
        
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
 * Comprehensive database schema validation
 */
const REQUIRED_SCHEMA = {
    // Core user and authentication tables
    core: [
        'user_api_keys',
        'users'
    ],
    
    // Portfolio and trading tables
    portfolio: [
        'portfolio_holdings',
        'portfolio_metadata',
        'trading_orders'
    ],
    
    // Market data tables
    market_data: [
        'symbols',
        'stock_symbols', 
        'price_daily',
        'market_data'
    ],
    
    // Analytics and scoring tables
    analytics: [
        'buy_sell_daily',
        'buy_sell_weekly', 
        'buy_sell_monthly',
        'technicals_daily',
        'fundamentals',
        'scores'
    ],
    
    // Optional enhancement tables
    optional: [
        'patterns',
        'sentiment',
        'earnings',
        'risk_metrics',
        'alerts',
        'swing_trader',
        'company_profile',
        'key_metrics'
    ]
};

/**
 * Comprehensive database schema validation with detailed logging
 */
async function validateDatabaseSchema(requestId = 'schema-check') {
    const validationStart = Date.now();
    console.log(`🔍 [${requestId}] Starting comprehensive database schema validation`);
    
    try {
        // Initialize database if needed
        await initializeDatabase();
        console.log(`✅ [${requestId}] Database initialized for schema validation`);
        
        const allTables = [
            ...REQUIRED_SCHEMA.core,
            ...REQUIRED_SCHEMA.portfolio,
            ...REQUIRED_SCHEMA.market_data,
            ...REQUIRED_SCHEMA.analytics,
            ...REQUIRED_SCHEMA.optional
        ];
        
        console.log(`🔍 [${requestId}] Checking ${allTables.length} tables across schema categories`);
        
        // Check table existence
        const tableCheckStart = Date.now();
        const tableExistenceMap = await tablesExist(allTables);
        const tableCheckDuration = Date.now() - tableCheckStart;
        
        console.log(`✅ [${requestId}] Table existence check completed in ${tableCheckDuration}ms`);
        
        // Categorize results
        const validation = {
            core: {
                required: REQUIRED_SCHEMA.core,
                existing: REQUIRED_SCHEMA.core.filter(table => tableExistenceMap[table]),
                missing: REQUIRED_SCHEMA.core.filter(table => !tableExistenceMap[table])
            },
            portfolio: {
                required: REQUIRED_SCHEMA.portfolio,
                existing: REQUIRED_SCHEMA.portfolio.filter(table => tableExistenceMap[table]),
                missing: REQUIRED_SCHEMA.portfolio.filter(table => !tableExistenceMap[table])
            },
            market_data: {
                required: REQUIRED_SCHEMA.market_data,
                existing: REQUIRED_SCHEMA.market_data.filter(table => tableExistenceMap[table]),
                missing: REQUIRED_SCHEMA.market_data.filter(table => !tableExistenceMap[table])
            },
            analytics: {
                required: REQUIRED_SCHEMA.analytics,
                existing: REQUIRED_SCHEMA.analytics.filter(table => tableExistenceMap[table]),
                missing: REQUIRED_SCHEMA.analytics.filter(table => !tableExistenceMap[table])
            },
            optional: {
                required: REQUIRED_SCHEMA.optional,
                existing: REQUIRED_SCHEMA.optional.filter(table => tableExistenceMap[table]),
                missing: REQUIRED_SCHEMA.optional.filter(table => !tableExistenceMap[table])
            }
        };
        
        // Calculate overall health
        const totalRequired = REQUIRED_SCHEMA.core.length + REQUIRED_SCHEMA.portfolio.length + 
                             REQUIRED_SCHEMA.market_data.length + REQUIRED_SCHEMA.analytics.length;
        const totalExisting = validation.core.existing.length + validation.portfolio.existing.length +
                             validation.market_data.existing.length + validation.analytics.existing.length;
        const totalMissing = validation.core.missing.length + validation.portfolio.missing.length +
                            validation.market_data.missing.length + validation.analytics.missing.length;
        
        const schemaHealthPercentage = Math.round((totalExisting / totalRequired) * 100);
        
        // Determine criticality
        const criticalMissing = [];
        if (validation.core.missing.length > 0) criticalMissing.push(...validation.core.missing.map(t => `core.${t}`));
        if (validation.portfolio.missing.length > 0) criticalMissing.push(...validation.portfolio.missing.map(t => `portfolio.${t}`));
        
        const validationDuration = Date.now() - validationStart;
        
        // Comprehensive logging
        console.log(`📊 [${requestId}] Database schema validation completed in ${validationDuration}ms`, {
            overall: {
                healthPercentage: schemaHealthPercentage,
                totalRequired,
                totalExisting,
                totalMissing,
                optionalExisting: validation.optional.existing.length,
                optionalMissing: validation.optional.missing.length
            },
            categories: {
                core: `${validation.core.existing.length}/${validation.core.required.length}`,
                portfolio: `${validation.portfolio.existing.length}/${validation.portfolio.required.length}`,
                market_data: `${validation.market_data.existing.length}/${validation.market_data.required.length}`,
                analytics: `${validation.analytics.existing.length}/${validation.analytics.required.length}`,
                optional: `${validation.optional.existing.length}/${validation.optional.required.length}`
            }
        });
        
        // Log critical issues
        if (criticalMissing.length > 0) {
            console.error(`❌ [${requestId}] CRITICAL: Missing essential database tables:`, {
                criticalMissing,
                impact: 'Core application functionality will fail',
                recommendation: 'Run database initialization scripts immediately',
                affectedFeatures: getCriticalFeatureImpact(criticalMissing)
            });
        }
        
        // Log category-specific issues
        Object.entries(validation).forEach(([category, info]) => {
            if (info.missing.length > 0 && category !== 'optional') {
                console.error(`❌ [${requestId}] Missing ${category} tables:`, {
                    category,
                    missingTables: info.missing,
                    existingTables: info.existing,
                    impact: getCategoryImpact(category),
                    recommendation: `Create missing ${category} tables`
                });
            }
        });
        
        return {
            valid: criticalMissing.length === 0,
            healthPercentage: schemaHealthPercentage,
            validation,
            criticalMissing,
            totalRequired,
            totalExisting,
            validationDuration,
            requestId,
            timestamp: new Date().toISOString()
        };
        
    } catch (error) {
        const errorDuration = Date.now() - validationStart;
        console.error(`❌ [${requestId}] Database schema validation FAILED after ${errorDuration}ms:`, {
            error: error.message,
            errorStack: error.stack,
            impact: 'Cannot determine database schema health',
            recommendation: 'Check database connectivity and permissions'
        });
        
        return {
            valid: false,
            error: error.message,
            validationDuration: errorDuration,
            requestId,
            timestamp: new Date().toISOString()
        };
    }
}

/**
 * Get impact description for missing critical tables
 */
function getCriticalFeatureImpact(missingTables) {
    const impacts = [];
    
    if (missingTables.some(t => t.includes('user_api_keys'))) {
        impacts.push('API key management will fail');
    }
    if (missingTables.some(t => t.includes('portfolio'))) {
        impacts.push('Portfolio functionality will be broken');
    }
    if (missingTables.some(t => t.includes('trading'))) {
        impacts.push('Trading operations will fail');
    }
    if (missingTables.some(t => t.includes('market_data'))) {
        impacts.push('Market data display will be broken');
    }
    
    return impacts;
}

/**
 * Get category-specific impact description
 */
function getCategoryImpact(category) {
    const impacts = {
        core: 'User authentication and API key management will fail',
        portfolio: 'Portfolio tracking and management features will be broken',
        market_data: 'Stock data and market information will be unavailable',
        analytics: 'Trading signals and analysis features will not work'
    };
    
    return impacts[category] || 'Some application features may be limited';
}

/**
 * Safe query that checks table existence first with comprehensive validation
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
 * Execute multiple queries in a database transaction
 * Ensures data integrity for multi-step operations
 */
async function transaction(callback) {
    const transactionId = Math.random().toString(36).substr(2, 9);
    const startTime = Date.now();
    
    console.log(`🔄 [${transactionId}] Starting database transaction`);
    
    if (!dbInitialized || !pool) {
        console.log(`🔄 [${transactionId}] Database not initialized, initializing...`);
        await initializeDatabase();
    }
    
    const client = await pool.connect();
    
    try {
        console.log(`📋 [${transactionId}] BEGIN transaction`);
        await client.query('BEGIN');
        
        // Execute the callback with the transaction client
        const result = await callback(client);
        
        console.log(`✅ [${transactionId}] COMMIT transaction`);
        await client.query('COMMIT');
        
        const duration = Date.now() - startTime;
        console.log(`✅ [${transactionId}] Transaction completed successfully in ${duration}ms`);
        
        return result;
        
    } catch (error) {
        const duration = Date.now() - startTime;
        console.error(`❌ [${transactionId}] ROLLBACK transaction after ${duration}ms:`, error.message);
        
        try {
            await client.query('ROLLBACK');
            console.log(`🔄 [${transactionId}] Transaction rolled back successfully`);
        } catch (rollbackError) {
            console.error(`❌ [${transactionId}] Failed to rollback transaction:`, rollbackError.message);
        }
        
        throw error;
    } finally {
        client.release();
        console.log(`🔓 [${transactionId}] Database client released`);
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

/**
 * Warm up database connections to reduce cold start latency
 */
async function warmConnections() {
    console.log('🔥 Warming up database connections...');
    const warmStart = Date.now();
    
    try {
        // Initialize database if not already done
        if (!dbInitialized || !pool) {
            await initializeDatabase();
        }

        // Create and test connections up to pool max
        const maxConnections = 2; // Match our pool max
        const warmPromises = [];

        for (let i = 0; i < maxConnections; i++) {
            warmPromises.push(
                (async () => {
                    try {
                        const client = await pool.connect();
                        await client.query('SELECT 1'); // Simple test query
                        client.release();
                        console.log(`🔥 Connection ${i + 1} warmed successfully`);
                    } catch (error) {
                        console.warn(`⚠️ Failed to warm connection ${i + 1}:`, error.message);
                    }
                })()
            );
        }

        await Promise.all(warmPromises);
        console.log(`✅ Database connections warmed in ${Date.now() - warmStart}ms`);
        
    } catch (error) {
        console.error('❌ Failed to warm database connections:', error.message);
    }
}

/**
 * Lambda-optimized database initialization with connection warming
 */
async function initForLambda() {
    console.log('🚀 Initializing database for Lambda with connection warming...');
    const lambdaInitStart = Date.now();
    
    try {
        // Initialize database
        await initializeDatabase();
        
        // Warm connections to reduce future cold start latency
        await warmConnections();
        
        console.log(`🚀 Lambda database initialization complete in ${Date.now() - lambdaInitStart}ms`);
        return true;
        
    } catch (error) {
        console.error('❌ Lambda database initialization failed:', error.message);
        return false;
    }
}

/**
 * Extract table name from SQL query for performance tracking
 */
function extractTableName(sql) {
    try {
        const cleanSql = sql.trim().toLowerCase();
        
        // Match common SQL patterns
        const patterns = [
            /^insert\s+into\s+([a-zA-Z_][a-zA-Z0-9_]*)/,
            /^update\s+([a-zA-Z_][a-zA-Z0-9_]*)/,
            /^delete\s+from\s+([a-zA-Z_][a-zA-Z0-9_]*)/,
            /^select\s+.*?\s+from\s+([a-zA-Z_][a-zA-Z0-9_]*)/,
            /^create\s+table\s+([a-zA-Z_][a-zA-Z0-9_]*)/,
            /^drop\s+table\s+([a-zA-Z_][a-zA-Z0-9_]*)/,
            /^truncate\s+table\s+([a-zA-Z_][a-zA-Z0-9_]*)/,
            /^alter\s+table\s+([a-zA-Z_][a-zA-Z0-9_]*)/
        ];
        
        for (const pattern of patterns) {
            const match = cleanSql.match(pattern);
            if (match) {
                return match[1];
            }
        }
        
        return 'unknown';
    } catch (error) {
        return 'unknown';
    }
}

module.exports = {
    initializeDatabase,
    initForLambda,
    warmConnections,
    getPool,
    getPoolStatus,
    query,
    safeQuery,
    tableExists,
    tablesExist,
    validateDatabaseSchema,
    transaction,
    closeDatabase,
    healthCheck,
    REQUIRED_SCHEMA,
    extractTableName
};
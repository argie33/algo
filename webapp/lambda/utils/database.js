// Load environment variables first
require('dotenv').config();

// CIRCUIT BREAKER FIX: Use new database connection manager with integrated circuit breaker
const databaseManager = require('./databaseConnectionManager');

// Legacy imports for compatibility (will be removed in future versions)
const { Pool } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { getTimeout, withDatabaseTimeout } = require('./timeoutManager');
const ConnectionRetry = require('./connectionRetry');
const logger = require('./logger');

// Legacy global state (for backward compatibility)
let pool = null;
let dbInitialized = false;
let dbConfig = null;

// Initialize connection retry utility (legacy)
const connectionRetry = new ConnectionRetry({
    maxRetries: 3,
    initialDelay: 1000,
    maxDelay: 10000,
    backoffMultiplier: 2
});

// Configure AWS SDK for Secrets Manager
const secretsManager = new SecretsManagerClient({
    region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
});

/**
 * Get database secret from AWS Secrets Manager using direct SDK calls
 */
async function getDatabaseSecretDirect(secretArn) {
    try {
        console.log(`🔑 Getting secret from AWS Secrets Manager: ${secretArn}`);
        
        const command = new GetSecretValueCommand({
            SecretId: secretArn
        });
        
        const response = await secretsManager.send(command);
        
        if (response.SecretString) {
            const secret = JSON.parse(response.SecretString);
            console.log('✅ Successfully retrieved secret from AWS Secrets Manager');
            return secret;
        } else {
            throw new Error('Secret value is empty or binary format not supported');
        }
    } catch (error) {
        console.error('❌ Failed to get secret from AWS Secrets Manager:', error.message);
        throw new Error(`Failed to retrieve secret ${secretArn}: ${error.message}`);
    }
}

/**
 * Get database configuration from environment variables or AWS Secrets Manager with enhanced error handling
 */
async function getDbConfig() {
    if (dbConfig) {
        console.log('✅ Using cached database config');
        return dbConfig;
    }

    const configStart = Date.now();
    console.log('⏱️ Starting database config retrieval...');
    
    try {
        // First try AWS Secrets Manager in production/AWS environments
        if (process.env.DB_SECRET_ARN && process.env.NODE_ENV !== 'test' && !process.env.DB_SECRET_ARN.includes('${')) {
            console.log('🔐 Using AWS Secrets Manager for database configuration (PRIORITY)');
            
            const secretArn = process.env.DB_SECRET_ARN;
            console.log(`🔑 Getting credentials from Secrets Manager: ${secretArn}`);
            
            let secret;
            try {
                // Try diagnostic tool first
                const SecretsManagerDiagnostic = require('./secretsManagerDiagnostic');
                const diagnostic = new SecretsManagerDiagnostic();
                secret = await diagnostic.getSecret(secretArn);
            } catch (diagError) {
                console.warn('⚠️ Diagnostic tool failed, using direct AWS SDK:', diagError.message);
                
                const command = new GetSecretValueCommand({ SecretId: secretArn });
                const response = await secretsManager.send(command);
                secret = JSON.parse(response.SecretString);
            }

            // FIXED: Prioritize RDS endpoint from secrets, fallback to ENV vars, reject localhost in AWS
            const dbHost = secret.host || secret.endpoint || process.env.DB_ENDPOINT || process.env.DB_HOST;
            
            // AWS Production Security: Reject localhost connections in AWS Lambda environment
            if (process.env.AWS_LAMBDA_FUNCTION_NAME && (dbHost === 'localhost' || dbHost === '127.0.0.1')) {
                console.error('🚨 SECURITY ALERT: Lambda attempting localhost connection - forcing RDS endpoint');
                throw new Error('Invalid database host: localhost not allowed in AWS Lambda environment');
            }
            
            dbConfig = {
                host: dbHost,
                port: parseInt(secret.port) || parseInt(process.env.DB_PORT) || 5432,
                database: secret.dbname || secret.database || process.env.DB_NAME || 'stocks',
                user: secret.username || secret.user || process.env.DB_USER,
                password: secret.password,
                ssl: { rejectUnauthorized: false },
                max: parseInt(process.env.DB_POOL_MAX) || 3,
                idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
                connectionTimeoutMillis: parseInt(process.env.DB_CONNECT_TIMEOUT) || 20000
            };

            const configDuration = Date.now() - configStart;
            console.log(`✅ Database config loaded from AWS Secrets Manager (${configDuration}ms)`);
            console.log(`   🏗️ Host: ${dbConfig.host}:${dbConfig.port}`);
            console.log(`   📚 Database: ${dbConfig.database}`);
            console.log(`   👤 User: ${dbConfig.user}`);
            console.log(`   🔒 SSL: enabled`);

            return dbConfig;
        }

        // Fallback: try direct environment variables (for local development only)
        if (process.env.DB_HOST && process.env.DB_USER && process.env.DB_PASSWORD && process.env.NODE_ENV === 'development') {
            console.log('🔧 Using direct database environment variables (LOCAL DEVELOPMENT ONLY)');
            
            dbConfig = {
                host: process.env.DB_HOST || process.env.DB_ENDPOINT,
                port: parseInt(process.env.DB_PORT) || 5432,
                database: process.env.DB_NAME || process.env.DB_DATABASE || 'stocks',
                user: process.env.DB_USER || process.env.DB_USERNAME,
                password: process.env.DB_PASSWORD,
                ssl: process.env.DB_SSL === 'true' ? { rejectUnauthorized: false } : false,
                max: parseInt(process.env.DB_POOL_MAX) || 3,
                idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
                connectionTimeoutMillis: parseInt(process.env.DB_CONNECT_TIMEOUT) || 20000
            };

            const configDuration = Date.now() - configStart;
            console.log(`✅ Database config loaded from complete environment variables (${configDuration}ms)`);
            console.log(`   🔒 SSL: ${dbConfig.ssl ? 'enabled' : 'disabled'}`);
            console.log(`   🏊 Pool Max: ${dbConfig.max}`);
            console.log(`   🏗️ Host: ${dbConfig.host}:${dbConfig.port}`);
            console.log(`   📚 Database: ${dbConfig.database}`);
            console.log(`   👤 User: ${dbConfig.user}`);

            return dbConfig;
        }

        // Hybrid approach: use environment variables but get password from secret
        if (process.env.DB_HOST && process.env.DB_USER && process.env.DB_SECRET_ARN) {
            console.log('🔧 Using hybrid approach: env vars + secret for password');
            
            const secretArn = process.env.DB_SECRET_ARN;
            console.log(`🔑 Getting password from Secrets Manager: ${secretArn}`);
            
            let secret;
            try {
                // Try diagnostic tool first
                const SecretsManagerDiagnostic = require('./secretsManagerDiagnostic');
                const diagnostic = new SecretsManagerDiagnostic();
                
                const diagnosis = await diagnostic.diagnoseSecret(secretArn);
                if (diagnosis.success) {
                    secret = diagnosis.config;
                } else {
                    throw new Error(diagnosis.error);
                }
            } catch (diagnosticError) {
                console.warn('⚠️ Diagnostic tool failed, trying direct AWS SDK approach:', diagnosticError.message);
                // Fallback to direct AWS SDK call
                secret = await getDatabaseSecretDirect(secretArn);
            }
            
            dbConfig = {
                host: process.env.DB_HOST || process.env.DB_ENDPOINT || secret.host || secret.endpoint,
                port: parseInt(process.env.DB_PORT) || parseInt(secret.port) || 5432,
                database: process.env.DB_NAME || process.env.DB_DATABASE || secret.dbname || secret.database || 'stocks',
                user: process.env.DB_USER || process.env.DB_USERNAME || secret.username || secret.user,
                password: secret.password,  // Password from secret
                ssl: process.env.DB_SSL === 'true' ? { rejectUnauthorized: false } : false,
                max: parseInt(process.env.DB_POOL_MAX) || 3,
                idleTimeoutMillis: parseInt(process.env.DB_POOL_IDLE_TIMEOUT) || 30000,
                connectionTimeoutMillis: parseInt(process.env.DB_CONNECT_TIMEOUT) || 20000
            };

            const configDuration = Date.now() - configStart;
            console.log(`✅ Database config loaded from hybrid env vars + secret (${configDuration}ms)`);
            console.log(`   🔒 SSL: ${dbConfig.ssl ? 'enabled' : 'disabled'}`);
            console.log(`   🏊 Pool Max: ${dbConfig.max}`);
            console.log(`   🏗️ Host: ${dbConfig.host}:${dbConfig.port}`);
            console.log(`   📚 Database: ${dbConfig.database}`);
            console.log(`   👤 User: ${dbConfig.user}`);

            return dbConfig;
        }

        // Fallback to Secrets Manager if environment variables not available
        const secretArn = process.env.DB_SECRET_ARN;
        if (!secretArn || secretArn.includes('${') || secretArn === '${DB_SECRET_ARN}') {
            // Handle common deployment issues with placeholder values
            const errorMsg = `Database configuration incomplete. DB_SECRET_ARN is invalid or placeholder: "${secretArn}". Available: DB_HOST="${process.env.DB_HOST || 'undefined'}", DB_USER="${process.env.DB_USER || 'undefined'}", DB_PASSWORD="${process.env.DB_PASSWORD ? '[SET]' : 'undefined'}". Need either complete env vars or valid DB_SECRET_ARN.`;
            console.error('❌ Database configuration error:', errorMsg);
            
            // Return a stub configuration that allows health route to load but reports unhealthy status
            dbConfig = {
                host: 'localhost',
                port: 5432,
                database: 'unavailable',
                user: 'unavailable',
                password: 'unavailable',
                ssl: false,
                max: 1,
                idleTimeoutMillis: 1000,
                connectionTimeoutMillis: 1000,
                __isStub: true,
                __error: errorMsg
            };
            
            console.log('⚠️ Using stub database configuration - health checks will report service unavailable');
            return dbConfig;
        }

        console.log(`🔑 Getting DB credentials from Secrets Manager: ${secretArn}`);
        const secretStart = Date.now();
        
        // Use diagnostic tool to properly handle secret retrieval
        const SecretsManagerDiagnostic = require('./secretsManagerDiagnostic');
        const diagnostic = new SecretsManagerDiagnostic();
        
        const diagnosis = await diagnostic.diagnoseSecret(secretArn);
        console.log(`✅ Secrets Manager responded in ${Date.now() - secretStart}ms using method: ${diagnosis.method}`);
        
        if (!diagnosis.success) {
            throw new Error(`Secrets Manager diagnosis failed: ${diagnosis.error}`);
        }
        
        const secret = diagnosis.config;
        
        // Validate required fields
        const requiredFields = ['host', 'username', 'password', 'dbname'];
        const missingFields = requiredFields.filter(field => !secret[field]);
        
        if (missingFields.length > 0) {
            logger.error('Missing required database configuration fields', {
                missingFields,
                availableFields: Object.keys(secret),
                source: 'SecretsManager'
            });
            throw new Error(`Missing required database configuration fields: ${missingFields.join(', ')}`);
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
        console.log(`   🔒 SSL: disabled (matching working ECS task configuration)`);
        console.log(`   🏊 Pool Max: ${dbConfig.max}`);
        console.log(`   🏗️ Host: ${dbConfig.host}:${dbConfig.port}`);
        console.log(`   📚 Database: ${dbConfig.database}`);
        console.log(`   👤 User: ${dbConfig.user}`);

        return dbConfig;
    } catch (error) {
        logger.error('Failed to get database configuration', {
            error,
            message: error.message,
            code: error.code,
            stack: error.stack,
            environmentVariables: {
                DB_HOST: !!process.env.DB_HOST,
                DB_USER: !!process.env.DB_USER,
                DB_PASSWORD: !!process.env.DB_PASSWORD,
                DB_SECRET_ARN: !!process.env.DB_SECRET_ARN,
                DB_ENDPOINT: !!process.env.DB_ENDPOINT
            },
            troubleshooting: 'Set DB_HOST, DB_USER, DB_PASSWORD environment variables or configure AWS Secrets Manager'
        });
        
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
            // Connection timeouts optimized for Lambda cold starts
            idleTimeoutMillis: 900000, // 15 minutes (Lambda max execution time)
            connectionTimeoutMillis: 15000, // 15 seconds for initial connection
            acquireTimeoutMillis: dynamicPoolConfig.acquireTimeoutMillis || 8000, // Use dynamic config or default
            createTimeoutMillis: 15000, // 15 seconds for creating new connections
            destroyTimeoutMillis: 5000, // Quick cleanup
            createRetryIntervalMillis: 1000, // 1 second retry interval
            
            // Pool management optimized for serverless
            allowExitOnIdle: false, // Keep pool alive during Lambda execution
            propagateCreateError: false, // Handle connection errors gracefully
            lazy: true, // Create connections on demand
            
            // Connection health checks
            testOnBorrow: true, // Validate connections before use
            testOnReturn: false, // Skip validation on return for performance
            testWhileIdle: true, // Validate idle connections
            
            // Connection keep-alive for Lambda
            keepAlive: true,
            keepAliveInitialDelayMillis: 10000,
            
            // Eviction and cleanup (less aggressive for Lambda)
            evictionRunIntervalMillis: 30000, // Check every 30 seconds
            numTestsPerEvictionRun: 3, // Test up to 3 connections per run
            softIdleTimeoutMillis: 60000 // Soft idle threshold (1 minute)
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

        // Test connection with retry logic
        console.log('🧪 Testing database connection with retry logic...');
        
        const connectionTest = await connectionRetry.execute(async (attempt) => {
            const testStart = Date.now();
            
            const client = await Promise.race([
                pool.connect(),
                new Promise((_, reject) => 
                    setTimeout(() => reject(new Error('Connection test timeout after 15 seconds')), 15000)
                )
            ]);
            
            console.log(`✅ Client connected in ${Date.now() - testStart}ms (attempt ${attempt + 1})`);
            
            // Use the simplest possible query
            const queryStart = Date.now();
            await client.query('SELECT 1 as test');
            console.log(`✅ Test query completed in ${Date.now() - queryStart}ms`);
            
            client.release();
            return { connected: true, duration: Date.now() - testStart };
        }, 'database connection test');
        
        if (!connectionTest.success) {
            throw new Error(`Database connection test failed: ${connectionTest.error}`);
        }
        
        console.log(`🎯 Database connection test completed successfully in ${connectionTest.attempts} attempts`);
        
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
 * CIRCUIT BREAKER FIX: Execute a database query with circuit breaker protection
 * This function now uses the new database connection manager with integrated circuit breaker
 */
async function query(text, params = [], timeoutMs = null) {
    const queryId = Math.random().toString(36).substr(2, 9);
    const startTime = Date.now();
    
    console.log(`🔍 [${queryId}] QUERY START (Circuit Breaker): ${text.substring(0, 100)}...`);
    console.log(`🔍 [${queryId}] Params:`, params);
    if (timeoutMs) {
        console.log(`🔍 [${queryId}] Timeout: ${timeoutMs}ms`);
    }
    
    try {
        // Use timeout if specified, otherwise use database manager with circuit breaker protection
        let result;
        if (timeoutMs) {
            result = await withDatabaseTimeout(
                () => databaseManager.query(text, params),
                timeoutMs
            );
        } else {
            result = await databaseManager.query(text, params);
        }
        
        const duration = Date.now() - startTime;
        console.log(`✅ [${queryId}] Query completed in ${duration}ms`);
        console.log(`✅ [${queryId}] Rows returned: ${result?.rows?.length || 0}`);
        
        // Track performance metrics (legacy compatibility)
        try {
            const { performanceMonitor } = require('./performanceMonitor');
            const operation = text.trim().split(' ')[0].toUpperCase();
            const table = extractTableName(text);
            
            performanceMonitor.trackDbOperation(operation, table, duration, true, queryId);
        } catch (perfError) {
            // Performance monitoring is optional - don't fail the query
            console.warn(`⚠️ [${queryId}] Performance monitoring failed:`, perfError.message);
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
 * CIRCUIT BREAKER FIX: Health check using new database manager with circuit breaker
 */
async function healthCheck() {
    try {
        // Check if we're using stub configuration due to invalid DB_SECRET_ARN
        const config = await getDbConfig();
        if (config.__isStub) {
            return {
                status: 'configuration_error',
                error: 'Database configuration incomplete',
                details: config.__error,
                note: 'Database credentials are not properly configured. Check DB_SECRET_ARN environment variable.',
                configurationIssue: true
            };
        }
        
        // Use new database manager with circuit breaker protection
        const result = await databaseManager.query('SELECT NOW() as timestamp, current_database() as db, version() as version');
        
        return {
            status: 'healthy',
            database: result.rows[0].db,
            timestamp: result.rows[0].timestamp,
            version: result.rows[0].version.split(' ')[0],
            note: 'Database connection verified with circuit breaker protection'
        };
    } catch (error) {
        // Check if this is a circuit breaker error and provide helpful info
        if (error.message.includes('Circuit breaker is OPEN')) {
            return {
                status: 'circuit_breaker_open',
                error: error.message,
                note: 'Database access blocked by circuit breaker. Use emergency reset endpoint if needed.',
                recovery: 'POST /api/health/emergency/reset-circuit-breaker'
            };
        }
        
        return {
            status: 'unhealthy',
            error: error.message,
            note: 'Database connection failed - check configuration and network connectivity'
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
 * Check if multiple tables exist with test environment awareness
 */
async function tablesExist(tableNames) {
    try {
        // In test environment without real database, simulate missing tables
        if (process.env.NODE_ENV === 'test' && !process.env.USE_REAL_DB) {
            console.log('🧪 Test environment: simulating table existence check');
            const existsMap = {};
            tableNames.forEach(tableName => {
                // Simulate non-existent tables for testing safeQuery error handling
                existsMap[tableName] = tableName.includes('test_') || tableName === 'users';
            });
            return existsMap;
        }
        
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
        
        // For critical database connection errors, re-throw to allow caller to handle
        if (error.message && (
            error.message.includes('connection') || 
            error.message.includes('connect') ||
            error.message.includes('lost') ||
            error.message.includes('refused') ||
            error.message.includes('timeout')
        )) {
            throw error;
        }
        
        // For other errors, provide fallback behavior
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
        'users',
        'user_api_keys',
        'user_sessions',
        'security_events'
    ],
    
    // Portfolio and trading tables
    portfolio: [
        'portfolios',
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
 * Close database connections and clean up resources
 */
async function closeDatabase() {
    if (pool) {
        console.log('🔄 Closing database connections...');
        
        // Remove all event listeners to prevent memory leaks - Pool cleanup handles this automatically
        // pool.removeAllListeners(); // Removed - Pool doesn't have this method
        
        // Close the pool
        await pool.end();
        
        // Reset state
        pool = null;
        dbInitialized = false;
        dbConfig = null;
        
        console.log('✅ Database connections closed and resources cleaned up');
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
        if (!sql || typeof sql !== 'string') {
            return 'unknown';
        }
        
        const cleanSql = sql.trim().toLowerCase();
        
        if (!cleanSql) {
            return 'unknown';
        }
        
        // Handle CTE (Common Table Expression) queries - extract from the inner FROM clause
        const cteMatch = cleanSql.match(/with\s+\w+\s+as\s*\([^)]*from\s+([a-zA-Z_][a-zA-Z0-9_]*)/i);
        if (cteMatch) {
            return cteMatch[1];
        }
        
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
        // Log error for debugging but don't expose in production
        if (process.env.NODE_ENV !== 'production') {
            console.warn('📄 Table name extraction failed:', error.message);
        }
        return 'unknown';
    }
}

/**
 * Reset database state for testing purposes
 */
async function resetDatabaseState() {
    if (pool) {
        await pool.end();
        pool = null;
    }
    dbInitialized = false;
    dbConfig = null;
    console.log('🔄 Database state reset for testing');
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
    resetDatabaseState,
    REQUIRED_SCHEMA,
    extractTableName,
    calculateOptimalPoolConfig,
    getDbConfig
};
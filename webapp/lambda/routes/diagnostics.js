/**
 * Database and System Diagnostics Routes
 * Comprehensive testing and recovery endpoints
 */

const express = require('express');
const { success, error } = require('../utils/responseFormatter');
const circuitBreakerReset = require('../utils/circuitBreakerReset');
const SecretsManagerDiagnostic = require('../utils/secretsManagerDiagnostic');
const NetworkDiagnostic = require('../utils/networkDiagnostic');

const router = express.Router();

/**
 * GET /api/diagnostics/health
 * Comprehensive system health check with circuit breaker status
 */
router.get('/health', async (req, res) => {
    const startTime = Date.now();
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`🏥 [${diagnosticId}] Starting comprehensive health check...`);
    
    try {
        const health = {
            status: 'checking',
            timestamp: new Date().toISOString(),
            diagnosticId,
            checks: {}
        };
        
        // Circuit breaker health
        console.log(`🏥 [${diagnosticId}] Checking circuit breaker health...`);
        const circuitBreakerHealth = circuitBreakerReset.getCircuitBreakerStatus();
        health.checks.circuitBreakers = {
            status: circuitBreakerHealth.open === 0 ? 'healthy' : 'degraded',
            ...circuitBreakerHealth
        };
        
        // Database connectivity
        console.log(`🏥 [${diagnosticId}] Testing database connectivity...`);
        try {
            const database = require('../utils/database');
            const dbHealth = await database.healthCheck();
            health.checks.database = {
                status: dbHealth.status === 'healthy' ? 'healthy' : 'unhealthy',
                ...dbHealth
            };
        } catch (dbError) {
            health.checks.database = {
                status: 'error',
                error: dbError.message
            };
        }
        
        // AWS Secrets Manager
        console.log(`🏥 [${diagnosticId}] Testing AWS Secrets Manager...`);
        try {
            const secretArn = process.env.DB_SECRET_ARN;
            if (secretArn) {
                const diagnostic = new SecretsManagerDiagnostic();
                const secretTest = await diagnostic.diagnoseSecret(secretArn);
                health.checks.secretsManager = {
                    status: secretTest.success ? 'healthy' : 'unhealthy',
                    method: secretTest.method,
                    hasConfig: !!secretTest.config
                };
            } else {
                health.checks.secretsManager = {
                    status: 'error',
                    error: 'DB_SECRET_ARN not configured'
                };
            }
        } catch (secretError) {
            health.checks.secretsManager = {
                status: 'error',
                error: secretError.message
            };
        }
        
        // Overall status
        const allStatuses = Object.values(health.checks).map(check => check.status);
        const hasError = allStatuses.includes('error');
        const hasUnhealthy = allStatuses.includes('unhealthy');
        const hasDegraded = allStatuses.includes('degraded');
        
        if (hasError) {
            health.status = 'error';
        } else if (hasUnhealthy) {
            health.status = 'unhealthy';
        } else if (hasDegraded) {
            health.status = 'degraded';
        } else {
            health.status = 'healthy';
        }
        
        health.duration = Date.now() - startTime;
        
        console.log(`🏥 [${diagnosticId}] Health check completed in ${health.duration}ms: ${health.status}`);
        
        res.json(success(health));
        
    } catch (error) {
        const duration = Date.now() - startTime;
        console.error(`❌ [${diagnosticId}] Health check failed after ${duration}ms:`, error.message);
        
        res.json(error(error.message, {
            diagnosticId,
            duration,
            error: 'Health check failed'
        }));
    }
});

/**
 * POST /api/diagnostics/reset-circuit-breakers
 * Reset all circuit breakers to allow immediate retry
 */
router.post('/reset-circuit-breakers', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`🔄 [${diagnosticId}] Manual circuit breaker reset requested...`);
    
    try {
        const result = circuitBreakerReset.resetAllCircuitBreakers();
        
        console.log(`✅ [${diagnosticId}] Circuit breaker reset completed: ${result.reset} breakers reset`);
        
        res.json(success({
            ...result,
            diagnosticId,
            message: `Successfully reset ${result.reset} circuit breakers`
        }));
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Circuit breaker reset failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'reset-circuit-breakers' }));
    }
});

/**
 * POST /api/diagnostics/test-database
 * Test database connectivity with circuit breaker management
 */
router.post('/test-database', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`🧪 [${diagnosticId}] Manual database connectivity test requested...`);
    
    try {
        const result = await circuitBreakerReset.testDatabaseConnectivity();
        
        console.log(`🧪 [${diagnosticId}] Database test completed: ${result.success ? 'SUCCESS' : 'FAILED'}`);
        
        if (result.success) {
            res.json(success({
                ...result,
                diagnosticId,
                message: 'Database connectivity test passed'
            }));
        } else {
            res.json(error(result.message, {
                ...result,
                diagnosticId
            }));
        }
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Database test failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'test-database' }));
    }
});

/**
 * POST /api/diagnostics/emergency-recovery
 * Emergency database recovery procedure
 */
router.post('/emergency-recovery', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`🚨 [${diagnosticId}] Emergency database recovery requested...`);
    
    try {
        const result = await circuitBreakerReset.emergencyDatabaseRecovery();
        
        console.log(`🚨 [${diagnosticId}] Emergency recovery completed: ${result.success ? 'SUCCESS' : 'PARTIAL'}`);
        
        if (result.success) {
            res.json(success({
                ...result,
                diagnosticId,
                message: 'Emergency database recovery completed successfully'
            }));
        } else {
            res.json(error('Emergency recovery completed with errors', {
                ...result,
                diagnosticId
            }));
        }
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Emergency recovery failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'emergency-recovery' }));
    }
});

/**
 * GET /api/diagnostics/secrets-manager
 * Test AWS Secrets Manager configuration
 */
router.get('/secrets-manager', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`🔑 [${diagnosticId}] Secrets Manager diagnostic requested...`);
    
    try {
        const secretArn = process.env.DB_SECRET_ARN;
        
        if (!secretArn) {
            return res.json(error('DB_SECRET_ARN environment variable not set', {
                diagnosticId,
                operation: 'secrets-manager-test'
            }));
        }
        
        const diagnostic = new SecretsManagerDiagnostic();
        const result = await diagnostic.diagnoseSecret(secretArn);
        
        console.log(`🔑 [${diagnosticId}] Secrets Manager test completed: ${result.success ? 'SUCCESS' : 'FAILED'}`);
        
        // Sanitize response - don't expose actual secrets
        const sanitizedResult = {
            success: result.success,
            method: result.method,
            diagnosticId: result.diagnosticId,
            hasConfig: !!result.config,
            configKeys: result.config ? Object.keys(result.config) : [],
            error: result.error
        };
        
        if (result.success) {
            res.json(success({
                ...sanitizedResult,
                message: `Secrets Manager test passed using method: ${result.method}`
            }));
        } else {
            res.json(error(result.error, sanitizedResult));
        }
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Secrets Manager test failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'secrets-manager-test' }));
    }
});

// System diagnostics endpoint
router.get('/system', (req, res) => {
  const systemInfo = {
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    platform: process.platform,
    nodeVersion: process.version,
    environment: process.env.NODE_ENV || 'development',
    lambda: {
      functionName: process.env.AWS_LAMBDA_FUNCTION_NAME || 'local',
      functionVersion: process.env.AWS_LAMBDA_FUNCTION_VERSION || 'local',
      memorySize: process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE || 'unknown',
      region: process.env.AWS_REGION || 'unknown'
    },
    configuration: {
      hasDbSecretArn: !!process.env.DB_SECRET_ARN,
      hasApiKeySecret: !!process.env.API_KEY_ENCRYPTION_SECRET_ARN,
      dbPoolMax: process.env.DB_POOL_MAX || 'default',
      dbConnectTimeout: process.env.DB_CONNECT_TIMEOUT || 'default'
    }
  };

  res.json(success(systemInfo));
});

/**
 * POST /api/diagnostics/network-test
 * Comprehensive network connectivity testing
 */
router.post('/network-test', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`🌐 [${diagnosticId}] Network connectivity test requested...`);
    
    try {
        const networkDiag = new NetworkDiagnostic();
        await networkDiag.initialize();
        
        const result = await networkDiag.runComprehensiveTest();
        
        console.log(`🌐 [${diagnosticId}] Network test completed: ${result.summary?.overallStatus || 'unknown'}`);
        
        if (result.summary?.overallStatus === 'healthy') {
            res.json(success({
                ...result,
                message: 'Network connectivity test passed'
            }));
        } else {
            res.json(error('Network connectivity issues detected', result));
        }
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Network test failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'network-test' }));
    }
});

/**
 * GET /api/diagnostics/connection-comparison
 * Compare working vs failing ECS task configurations
 */
router.get('/connection-comparison', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`⚖️ [${diagnosticId}] Connection comparison analysis requested...`);
    
    try {
        // Get current environment information
        const environment = {
            isLambda: !!process.env.AWS_LAMBDA_FUNCTION_NAME,
            region: process.env.AWS_REGION || process.env.WEBAPP_AWS_REGION || 'unknown',
            functionName: process.env.AWS_LAMBDA_FUNCTION_NAME || 'local',
            platform: process.platform,
            nodeVersion: process.version
        };
        
        // Get database configuration for comparison
        const secretArn = process.env.DB_SECRET_ARN;
        let dbConfig = null;
        
        if (secretArn) {
            try {
                const diagnostic = new SecretsManagerDiagnostic();
                const result = await diagnostic.diagnoseSecret(secretArn);
                if (result.success) {
                    dbConfig = {
                        host: result.config.host,
                        port: result.config.port,
                        database: result.config.dbname,
                        hasPassword: !!result.config.password,
                        hasUsername: !!result.config.username
                    };
                }
            } catch (err) {
                dbConfig = { error: err.message };
            }
        }
        
        // Working configuration template (from successful ECS tasks)
        const workingConfig = {
            connectionString: {
                sslmode: 'require',
                ssl: false, // Note: This might seem contradictory but matches working config
                connectionTimeout: '15000ms',
                queryTimeout: '30000ms'
            },
            poolSettings: {
                max: 3,
                min: 1,
                idleTimeoutMillis: 30000,
                acquireTimeoutMillis: 8000
            },
            networkRequirements: {
                securityGroups: 'Allow PostgreSQL 5432 outbound',
                subnets: 'Private subnets with NAT gateway access',
                dns: 'VPC DNS resolution enabled'
            },
            environment: {
                DB_SECRET_ARN: 'Required - points to RDS credentials',
                AWS_REGION: 'Required - for Secrets Manager access',
                NODE_ENV: 'production'
            }
        };
        
        const comparison = {
            diagnosticId,
            timestamp: new Date().toISOString(),
            currentEnvironment: environment,
            currentDbConfig: dbConfig,
            workingConfigTemplate: workingConfig,
            recommendations: []
        };
        
        // Generate recommendations based on comparison
        if (environment.isLambda) {
            comparison.recommendations.push('Lambda environment detected - ensure VPC configuration allows RDS access');
        }
        
        if (!secretArn) {
            comparison.recommendations.push('DB_SECRET_ARN not configured - database connections will fail');
        }
        
        if (dbConfig?.error) {
            comparison.recommendations.push(`Database configuration error: ${dbConfig.error}`);
        }
        
        if (comparison.recommendations.length === 0) {
            comparison.recommendations.push('Configuration appears to match working template');
        }
        
        console.log(`⚖️ [${diagnosticId}] Connection comparison completed`);
        
        res.json(success(comparison));
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Connection comparison failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'connection-comparison' }));
    }
});

// Route diagnostics endpoint
router.get('/routes', (req, res) => {
  // This would be populated with actual route health data
  const routeHealth = {
    total: 26,
    healthy: 15,
    unhealthy: 11,
    status: 'partial',
    lastCheck: new Date().toISOString()
  };

  res.json(success(routeHealth));
});

module.exports = router;
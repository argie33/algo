const express = require('express');
const router = express.Router();
const { diagnosticSecretsManager } = require('../debug-secrets-local');
const { checkCloudFormationStatus } = require('../check-cloudformation-status');
const { resetAllCircuitBreakers, getCircuitBreakerStatus } = require('../utils/circuitBreakerReset');

/**
 * Infrastructure Diagnostics Routes
 * These routes help debug the database connection and ECS task execution issues
 */

// Test AWS Secrets Manager access and JSON parsing
router.get('/secrets-manager', async (req, res) => {
    try {
        console.log('🔍 Running Secrets Manager diagnostic...');
        
        // Capture console output
        const originalLog = console.log;
        const originalError = console.error;
        const logs = [];
        
        console.log = (...args) => {
            logs.push({ level: 'info', message: args.join(' ') });
            originalLog(...args);
        };
        
        console.error = (...args) => {
            logs.push({ level: 'error', message: args.join(' ') });
            originalError(...args);
        };
        
        try {
            await diagnosticSecretsManager();
            
            // Restore console
            console.log = originalLog;
            console.error = originalError;
            
            res.success({
                message: 'Secrets Manager diagnostic completed',
                logs,
                timestamp: new Date().toISOString(),
                environment: {
                    DB_SECRET_ARN: process.env.DB_SECRET_ARN ? 'SET' : 'NOT_SET',
                    AWS_REGION: process.env.AWS_REGION || 'us-east-1',
                    NODE_ENV: process.env.NODE_ENV || 'development'
                }
            });
            
        } catch (diagError) {
            console.log = originalLog;
            console.error = originalError;
            
            res.error('Secrets Manager diagnostic failed', {
                error: diagError.message,
                logs,
                stack: diagError.stack
            });
        }
        
    } catch (error) {
        console.error('❌ Diagnostic route error:', error);
        res.error('Failed to run Secrets Manager diagnostic', {
            error: error.message,
            correlationId: req.correlationId
        });
    }
});

// Test CloudFormation stack status
router.get('/cloudformation', async (req, res) => {
    try {
        console.log('🔍 Running CloudFormation diagnostic...');
        
        const originalLog = console.log;
        const originalError = console.error;
        const logs = [];
        
        console.log = (...args) => {
            logs.push({ level: 'info', message: args.join(' ') });
            originalLog(...args);
        };
        
        console.error = (...args) => {
            logs.push({ level: 'error', message: args.join(' ') });
            originalError(...args);
        };
        
        try {
            await checkCloudFormationStatus();
            
            console.log = originalLog;
            console.error = originalError;
            
            res.success({
                message: 'CloudFormation diagnostic completed',
                logs,
                timestamp: new Date().toISOString()
            });
            
        } catch (diagError) {
            console.log = originalLog;
            console.error = originalError;
            
            res.error('CloudFormation diagnostic failed', {
                error: diagError.message,
                logs,
                stack: diagError.stack
            });
        }
        
    } catch (error) {
        console.error('❌ CloudFormation diagnostic route error:', error);
        res.error('Failed to run CloudFormation diagnostic', {
            error: error.message,
            correlationId: req.correlationId
        });
    }
});

// Test database connection directly
router.get('/database-connection', async (req, res) => {
    try {
        console.log('🔍 Testing direct database connection...');
        
        const { initializeDatabase, healthCheck } = require('../utils/database');
        
        // Test database initialization
        const initStart = Date.now();
        try {
            console.log('🔄 Attempting database initialization...');
            await initializeDatabase();
            const initDuration = Date.now() - initStart;
            
            console.log(`✅ Database initialized in ${initDuration}ms`);
            
            // Test health check
            const healthStart = Date.now();
            const health = await healthCheck();
            const healthDuration = Date.now() - healthStart;
            
            console.log(`✅ Health check completed in ${healthDuration}ms`);
            
            res.success({
                message: 'Database connection test successful',
                initializationTime: initDuration,
                healthCheckTime: healthDuration,
                health,
                timestamp: new Date().toISOString()
            });
            
        } catch (dbError) {
            const errorDuration = Date.now() - initStart;
            console.error(`❌ Database connection failed after ${errorDuration}ms:`, dbError.message);
            
            res.error('Database connection test failed', {
                error: dbError.message,
                errorCode: dbError.code,
                duration: errorDuration,
                stack: dbError.stack?.split('\n').slice(0, 5), // Limit stack trace
                correlationId: req.correlationId
            });
        }
        
    } catch (error) {
        console.error('❌ Database diagnostic route error:', error);
        res.error('Failed to run database connection diagnostic', {
            error: error.message,
            correlationId: req.correlationId
        });
    }
});

// Run all diagnostics
router.get('/all', async (req, res) => {
    try {
        console.log('🔍 Running all infrastructure diagnostics...');
        
        const results = {
            timestamp: new Date().toISOString(),
            diagnostics: {}
        };
        
        // Test Secrets Manager
        try {
            console.log('📋 Step 1: Secrets Manager...');
            const secretsLogs = [];
            const originalLog = console.log;
            console.log = (...args) => secretsLogs.push(args.join(' '));
            
            await diagnosticSecretsManager();
            console.log = originalLog;
            
            results.diagnostics.secretsManager = {
                status: 'success',
                logs: secretsLogs
            };
        } catch (error) {
            results.diagnostics.secretsManager = {
                status: 'failed',
                error: error.message
            };
        }
        
        // Test Database Connection
        try {
            console.log('📋 Step 2: Database Connection...');
            const { healthCheck } = require('../utils/database');
            const health = await healthCheck();
            
            results.diagnostics.database = {
                status: 'success',
                health
            };
        } catch (error) {
            results.diagnostics.database = {
                status: 'failed',
                error: error.message,
                code: error.code
            };
        }
        
        res.success({
            message: 'All diagnostics completed',
            results,
            summary: {
                secretsManager: results.diagnostics.secretsManager?.status || 'failed',
                database: results.diagnostics.database?.status || 'failed'
            }
        });
        
    } catch (error) {
        console.error('❌ All diagnostics route error:', error);
        res.error('Failed to run all diagnostics', {
            error: error.message,
            correlationId: req.correlationId
        });
    }
});

// Circuit breaker management endpoints
router.get('/circuit-breaker/status', async (req, res) => {
    try {
        console.log('🔍 Getting circuit breaker status...');
        const status = getCircuitBreakerStatus();
        
        res.success({
            message: 'Circuit breaker status retrieved',
            ...status
        });
    } catch (error) {
        console.error('❌ Circuit breaker status error:', error);
        res.error('Failed to get circuit breaker status', {
            error: error.message,
            correlationId: req.correlationId
        });
    }
});

router.post('/circuit-breaker/reset', async (req, res) => {
    try {
        console.log('🔄 Resetting all circuit breakers...');
        const result = resetAllCircuitBreakers();
        
        res.success({
            message: 'Circuit breakers reset successfully',
            ...result
        });
    } catch (error) {
        console.error('❌ Circuit breaker reset error:', error);
        res.error('Failed to reset circuit breakers', {
            error: error.message,
            correlationId: req.correlationId
        });
    }
});

module.exports = router;
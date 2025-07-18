#!/usr/bin/env node

/**
 * Simple Database Connection Crisis Fix
 * 
 * Creates the key files needed to fix the circuit breaker OPEN issue
 */

const fs = require('fs');
const path = require('path');

function createDatabaseCircuitBreaker() {
  console.log('🔧 Creating enhanced database circuit breaker...');
  
  const circuitBreakerCode = `/**
 * Enhanced Database Circuit Breaker for Lambda Environment
 */
class DatabaseCircuitBreaker {
  constructor() {
    this.state = 'closed'; // 'closed', 'open', 'half-open'
    this.failures = 0;
    this.lastFailureTime = 0;
    this.successCount = 0;
    this.lastSuccessTime = Date.now();
    
    // Lambda-optimized thresholds
    this.failureThreshold = 10; // Increased from 5 to 10
    this.recoveryTimeout = 30000; // Reduced from 60s to 30s
    this.halfOpenMaxCalls = 5; // Increased from 3 to 5
    this.halfOpenSuccessThreshold = 3; // Need 3 successes to close
    
    // Health tracking
    this.totalRequests = 0;
    this.totalSuccesses = 0;
    this.totalFailures = 0;
    this.requestHistory = [];
  }
  
  async execute(operation, operationName = 'database-operation') {
    this.totalRequests++;
    
    // Check if circuit is open
    if (this.state === 'open') {
      const timeSinceLastFailure = Date.now() - this.lastFailureTime;
      if (timeSinceLastFailure < this.recoveryTimeout) {
        const remainingTime = Math.ceil((this.recoveryTimeout - timeSinceLastFailure) / 1000);
        throw new Error('Circuit breaker is OPEN. Database unavailable for ' + remainingTime + ' more seconds. Reason: Too many connection failures (' + this.failures + ' failures). Last failure: ' + new Date(this.lastFailureTime).toISOString());
      } else {
        // Transition to half-open for testing
        this.state = 'half-open';
        this.successCount = 0;
        console.log('🔄 Circuit breaker transitioning to HALF-OPEN for testing...');
      }
    }
    
    try {
      const startTime = Date.now();
      const result = await operation();
      const duration = Date.now() - startTime;
      
      // Record success
      this.recordSuccess(operationName, duration);
      
      return result;
    } catch (error) {
      // Record failure
      this.recordFailure(operationName, error);
      throw error;
    }
  }
  
  recordSuccess(operationName, duration) {
    this.totalSuccesses++;
    this.lastSuccessTime = Date.now();
    
    this.addToHistory('success', operationName, duration);
    
    if (this.state === 'half-open') {
      this.successCount++;
      console.log('✅ Circuit breaker half-open success ' + this.successCount + '/' + this.halfOpenSuccessThreshold + ' for ' + operationName);
      
      if (this.successCount >= this.halfOpenSuccessThreshold) {
        this.state = 'closed';
        this.failures = 0;
        this.successCount = 0;
        console.log('🔓 Circuit breaker CLOSED - database access restored');
      }
    } else if (this.state === 'closed') {
      // Reset failure count on successful operations
      this.failures = Math.max(0, this.failures - 1);
    }
  }
  
  recordFailure(operationName, error) {
    this.totalFailures++;
    this.failures++;
    this.lastFailureTime = Date.now();
    
    this.addToHistory('failure', operationName, 0, error.message);
    
    console.warn('⚠️ Database operation failed: ' + operationName + ' - ' + error.message + ' (failure ' + this.failures + '/' + this.failureThreshold + ')');
    
    if (this.failures >= this.failureThreshold) {
      this.state = 'open';
      console.error('🚨 Circuit breaker OPENED due to ' + this.failures + ' consecutive failures. Database access blocked for ' + (this.recoveryTimeout/1000) + ' seconds.');
    }
  }
  
  addToHistory(type, operation, duration, error = null) {
    this.requestHistory.push({
      timestamp: Date.now(),
      type,
      operation,
      duration,
      error
    });
    
    // Keep only last 100 records
    if (this.requestHistory.length > 100) {
      this.requestHistory = this.requestHistory.slice(-100);
    }
  }
  
  getStatus() {
    const now = Date.now();
    const timeSinceLastFailure = now - this.lastFailureTime;
    const timeSinceLastSuccess = now - this.lastSuccessTime;
    
    return {
      state: this.state,
      failures: this.failures,
      successCount: this.successCount,
      lastFailureTime: this.lastFailureTime,
      lastSuccessTime: this.lastSuccessTime,
      timeSinceLastFailure,
      timeSinceLastSuccess,
      totalRequests: this.totalRequests,
      totalSuccesses: this.totalSuccesses,
      totalFailures: this.totalFailures,
      successRate: this.totalRequests > 0 ? (this.totalSuccesses / this.totalRequests * 100).toFixed(2) + '%' : '0%',
      timeToRecovery: this.state === 'open' ? Math.max(0, this.recoveryTimeout - timeSinceLastFailure) : 0,
      isHealthy: this.state === 'closed' && this.failures < this.failureThreshold * 0.5,
      recentHistory: this.requestHistory.slice(-10)
    };
  }
  
  // Force reset circuit breaker (emergency use only)
  forceReset() {
    console.log('🔧 EMERGENCY: Force resetting circuit breaker...');
    this.state = 'closed';
    this.failures = 0;
    this.successCount = 0;
    this.lastFailureTime = 0;
    console.log('✅ Circuit breaker force reset completed');
  }
}

module.exports = DatabaseCircuitBreaker;`;

  const filePath = path.join(__dirname, 'webapp', 'lambda', 'utils', 'databaseCircuitBreaker.js');
  const dir = path.dirname(filePath);
  
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  
  fs.writeFileSync(filePath, circuitBreakerCode);
  console.log('✅ Created: ' + filePath);
}

function createDatabaseConnectionManager() {
  console.log('🔧 Creating database connection manager...');
  
  const connectionManagerCode = `/**
 * Database Connection Manager with Circuit Breaker Integration
 */
const { Pool } = require('pg');
const DatabaseCircuitBreaker = require('./databaseCircuitBreaker');

class DatabaseConnectionManager {
  constructor() {
    this.pool = null;
    this.circuitBreaker = new DatabaseCircuitBreaker();
    this.isInitialized = false;
    this.config = null;
    this.lastHealthCheck = 0;
    this.healthCheckInterval = 30000; // 30 seconds
  }
  
  async initialize() {
    if (this.isInitialized && this.pool) {
      return this.pool;
    }
    
    try {
      console.log('🔄 Initializing database connection with circuit breaker...');
      
      // Get database configuration
      this.config = await this.getDbConfig();
      
      // Create connection pool
      this.pool = new Pool({
        ...this.config,
        // Lambda-optimized settings
        max: 10, // Maximum connections
        min: 1,  // Minimum connections
        acquireTimeoutMillis: 15000, // 15 seconds
        createTimeoutMillis: 20000,  // 20 seconds
        destroyTimeoutMillis: 5000,  // 5 seconds
        idleTimeoutMillis: 30000,    // 30 seconds
        reapIntervalMillis: 1000,    // 1 second
        createRetryIntervalMillis: 200, // 200ms
        keepAlive: true,
        keepAliveInitialDelayMillis: 10000
      });
      
      // Test initial connection
      await this.testConnection();
      
      this.isInitialized = true;
      console.log('✅ Database connection initialized successfully');
      
      return this.pool;
    } catch (error) {
      console.error('❌ Database initialization failed:', error);
      this.pool = null;
      this.isInitialized = false;
      throw error;
    }
  }
  
  async getDbConfig() {
    // Try environment variables first
    if (process.env.DB_HOST && process.env.DB_USER && process.env.DB_PASSWORD) {
      console.log('🔧 Using direct environment variables');
      return {
        host: process.env.DB_HOST,
        port: parseInt(process.env.DB_PORT) || 5432,
        database: process.env.DB_NAME || 'stocks',
        user: process.env.DB_USER,
        password: process.env.DB_PASSWORD,
        ssl: process.env.DB_SSL === 'true' ? { rejectUnauthorized: false } : false
      };
    }
    
    // Fallback to AWS Secrets Manager
    if (process.env.DB_SECRET_ARN) {
      console.log('🔧 Using AWS Secrets Manager fallback');
      const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
      
      const client = new SecretsManagerClient({
        region: process.env.AWS_REGION || 'us-east-1'
      });
      
      try {
        const response = await client.send(new GetSecretValueCommand({
          SecretId: process.env.DB_SECRET_ARN
        }));
        
        // Enhanced JSON parsing with error handling
        let secret;
        try {
          secret = JSON.parse(response.SecretString);
        } catch (parseError) {
          console.error('❌ JSON parsing error for secret:', parseError);
          console.error('Secret string length:', response.SecretString?.length);
          console.error('Secret string preview:', response.SecretString?.substring(0, 100));
          throw new Error('Failed to parse database secret JSON: ' + parseError.message);
        }
        
        return {
          host: secret.host || process.env.DB_HOST,
          port: secret.port || parseInt(process.env.DB_PORT) || 5432,
          database: secret.dbname || secret.database || 'stocks',
          user: secret.username || secret.user,
          password: secret.password,
          ssl: false // Public subnet RDS typically doesn't use SSL
        };
      } catch (error) {
        console.error('❌ Failed to get secret from AWS Secrets Manager:', error);
        throw error;
      }
    }
    
    throw new Error('No database configuration found (no env vars or secret ARN)');
  }
  
  async testConnection() {
    return this.circuitBreaker.execute(async () => {
      const client = await this.pool.connect();
      try {
        await client.query('SELECT 1');
        return true;
      } finally {
        client.release();
      }
    }, 'connection-test');
  }
  
  async query(text, params = []) {
    // Initialize if needed
    if (!this.isInitialized) {
      await this.initialize();
    }
    
    // Periodic health check
    const now = Date.now();
    if (now - this.lastHealthCheck > this.healthCheckInterval) {
      try {
        await this.testConnection();
        this.lastHealthCheck = now;
      } catch (error) {
        console.warn('⚠️ Health check failed:', error.message);
      }
    }
    
    // Execute query through circuit breaker
    return this.circuitBreaker.execute(async () => {
      const client = await this.pool.connect();
      try {
        const result = await client.query(text, params);
        return result;
      } finally {
        client.release();
      }
    }, 'database-query');
  }
  
  getStatus() {
    return {
      initialized: this.isInitialized,
      pool: this.pool ? {
        totalCount: this.pool.totalCount,
        idleCount: this.pool.idleCount,
        waitingCount: this.pool.waitingCount
      } : null,
      circuitBreaker: this.circuitBreaker.getStatus()
    };
  }
  
  // Emergency recovery methods
  async forceReset() {
    console.log('🚨 EMERGENCY: Force resetting database connection...');
    this.circuitBreaker.forceReset();
    
    if (this.pool) {
      await this.pool.end();
      this.pool = null;
    }
    
    this.isInitialized = false;
    await this.initialize();
    console.log('✅ Database connection force reset completed');
  }
}

// Export singleton instance
module.exports = new DatabaseConnectionManager();`;

  const filePath = path.join(__dirname, 'webapp', 'lambda', 'utils', 'databaseConnectionManager.js');
  const dir = path.dirname(filePath);
  
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  
  fs.writeFileSync(filePath, connectionManagerCode);
  console.log('✅ Created: ' + filePath);
}

function createEmergencyEndpoints() {
  console.log('🔧 Creating emergency recovery endpoints...');
  
  const emergencyEndpointsCode = `/**
 * Emergency Database Recovery Endpoints
 */
const express = require('express');
const router = express.Router();

// Emergency circuit breaker reset endpoint
router.post('/emergency/reset-circuit-breaker', async (req, res) => {
  try {
    console.log('🚨 EMERGENCY: Circuit breaker reset requested');
    
    const databaseManager = require('../utils/databaseConnectionManager');
    const beforeStatus = databaseManager.getStatus();
    
    console.log('📊 Circuit breaker status before reset:', beforeStatus.circuitBreaker);
    
    // Force reset the circuit breaker and connection
    await databaseManager.forceReset();
    
    const afterStatus = databaseManager.getStatus();
    console.log('📊 Circuit breaker status after reset:', afterStatus.circuitBreaker);
    
    // Test the connection
    let testResult;
    try {
      await databaseManager.query('SELECT 1 as test');
      testResult = { success: true, message: 'Database connection restored' };
    } catch (error) {
      testResult = { success: false, error: error.message };
    }
    
    res.json({
      status: 'success',
      message: 'Circuit breaker emergency reset completed',
      beforeStatus: beforeStatus.circuitBreaker,
      afterStatus: afterStatus.circuitBreaker,
      connectionTest: testResult,
      timestamp: new Date().toISOString(),
      warning: 'This is an emergency procedure. Monitor the system closely.'
    });
    
  } catch (error) {
    console.error('❌ Emergency reset failed:', error);
    res.status(500).json({
      status: 'error',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Circuit breaker status monitoring endpoint
router.get('/circuit-breaker-status', async (req, res) => {
  try {
    const databaseManager = require('../utils/databaseConnectionManager');
    const status = databaseManager.getStatus();
    
    const circuitBreakerStatus = status.circuitBreaker;
    const isHealthy = circuitBreakerStatus.state === 'closed' && circuitBreakerStatus.isHealthy;
    
    res.json({
      status: isHealthy ? 'healthy' : 'degraded',
      circuitBreaker: circuitBreakerStatus,
      pool: status.pool,
      recommendations: generateCircuitBreakerRecommendations(circuitBreakerStatus),
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Circuit breaker status check failed:', error);
    res.status(500).json({
      status: 'error',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

function generateCircuitBreakerRecommendations(status) {
  const recommendations = [];
  
  if (status.state === 'open') {
    recommendations.push({
      level: 'critical',
      message: 'Circuit breaker is OPEN. Database access blocked for ' + Math.ceil(status.timeToRecovery/1000) + ' more seconds.',
      action: 'Wait for automatic recovery or use emergency reset endpoint: POST /api/health/emergency/reset-circuit-breaker'
    });
  }
  
  if (status.state === 'half-open') {
    recommendations.push({
      level: 'warning',
      message: 'Circuit breaker is testing recovery. Avoid heavy database operations.',
      action: 'Monitor closely and allow time for recovery validation'
    });
  }
  
  if (status.failures > 7) { // 70% of 10 threshold
    recommendations.push({
      level: 'warning',
      message: 'High failure rate detected (' + status.failures + ' failures). Circuit breaker may open soon.',
      action: 'Investigate database connectivity and consider scaling down operations'
    });
  }
  
  if (parseFloat(status.successRate) < 80) {
    recommendations.push({
      level: 'warning',
      message: 'Low success rate (' + status.successRate + '). Database performance issues detected.',
      action: 'Check database performance metrics and connection configuration'
    });
  }
  
  return recommendations;
}

module.exports = router;`;

  const filePath = path.join(__dirname, 'webapp', 'lambda', 'routes', 'emergency.js');
  const dir = path.dirname(filePath);
  
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  
  fs.writeFileSync(filePath, emergencyEndpointsCode);
  console.log('✅ Created: ' + filePath);
}

function createDeploymentGuide() {
  console.log('📋 Creating deployment guide...');
  
  const guideContent = `# DATABASE CONNECTION CRISIS FIX - DEPLOYMENT GUIDE

## CRITICAL ISSUE
Circuit breaker is OPEN, blocking all database access. This fix provides:
1. Enhanced circuit breaker with Lambda-optimized thresholds
2. Database connection manager with integrated circuit breaker
3. Emergency recovery endpoints

## FILES CREATED
1. webapp/lambda/utils/databaseCircuitBreaker.js
2. webapp/lambda/utils/databaseConnectionManager.js
3. webapp/lambda/routes/emergency.js

## DEPLOYMENT STEPS

### Step 1: Update Main Database Utility
Edit webapp/lambda/utils/database.js:

\`\`\`javascript
// Add at the top
const databaseManager = require('./databaseConnectionManager');

// Replace existing query function with:
async function query(text, params = []) {
  return databaseManager.query(text, params);
}

// Add health check function:
async function healthCheck() {
  try {
    await databaseManager.query('SELECT 1');
    return { status: 'healthy' };
  } catch (error) {
    return { status: 'unhealthy', error: error.message };
  }
}

module.exports = { query, healthCheck };
\`\`\`

### Step 2: Add Emergency Routes
Edit webapp/lambda/index.js (or main router):

\`\`\`javascript
// Add emergency routes
const emergencyRoutes = require('./routes/emergency');
app.use('/api/health', emergencyRoutes);
\`\`\`

### Step 3: Deploy to Lambda
\`\`\`bash
cd webapp/lambda
npm run package
npm run deploy-package
\`\`\`

## IMMEDIATE RECOVERY

### Check Circuit Breaker Status
\`\`\`bash
curl https://your-api-url/api/health/circuit-breaker-status
\`\`\`

### Emergency Reset (if needed)
\`\`\`bash
curl -X POST https://your-api-url/api/health/emergency/reset-circuit-breaker
\`\`\`

### Test Database
\`\`\`bash
curl https://your-api-url/api/health
\`\`\`

## KEY IMPROVEMENTS
- Failure threshold: 5 → 10 (more forgiving)
- Recovery timeout: 60s → 30s (faster recovery)
- Half-open calls: 3 → 5 (better testing)
- Enhanced SSL/JSON error handling
- Emergency manual recovery

## SUCCESS INDICATORS
✅ Circuit breaker state: closed
✅ Database queries succeed
✅ Health endpoint returns 200
✅ No "Circuit breaker is OPEN" errors

The circuit breaker will automatically attempt recovery every 30 seconds.
If automatic recovery fails, use the emergency reset endpoint.
`;

  const filePath = path.join(__dirname, 'DATABASE_CONNECTION_FIX_GUIDE.md');
  fs.writeFileSync(filePath, guideContent);
  console.log('✅ Created: ' + filePath);
}

// Main execution
function main() {
  console.log('🔧 DATABASE CONNECTION CRISIS FIX');
  console.log('='.repeat(50));
  console.log('');
  
  try {
    createDatabaseCircuitBreaker();
    createDatabaseConnectionManager();
    createEmergencyEndpoints();
    createDeploymentGuide();
    
    console.log('');
    console.log('🎉 DATABASE CONNECTION CRISIS FIX COMPLETED!');
    console.log('');
    console.log('📋 SUMMARY:');
    console.log('   ✅ Enhanced circuit breaker (10 failure threshold, 30s recovery)');
    console.log('   ✅ Database connection manager with circuit breaker integration');
    console.log('   ✅ Emergency recovery endpoints for manual intervention');
    console.log('   ✅ Deployment guide with step-by-step instructions');
    console.log('');
    console.log('🚀 NEXT STEPS:');
    console.log('   1. Review: DATABASE_CONNECTION_FIX_GUIDE.md');
    console.log('   2. Deploy: New files to Lambda function');
    console.log('   3. Test: Circuit breaker status and database connection');
    console.log('');
    console.log('⚠️  CRITICAL: This fix addresses the circuit breaker OPEN state!');
    
    return { success: true };
  } catch (error) {
    console.error('❌ Fix failed:', error.message);
    return { success: false, error: error.message };
  }
}

if (require.main === module) {
  const result = main();
  process.exit(result.success ? 0 : 1);
}

module.exports = main;
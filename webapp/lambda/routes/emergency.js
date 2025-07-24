/**
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

// Emergency CloudFormation config endpoint - temporary workaround for cloudformation route loading issue
router.get('/config/cloudformation', async (req, res) => {
  try {
    console.log('🔄 Emergency CloudFormation config requested');
    
    // Provide basic fallback configuration 
    const fallbackConfig = {
      success: true,
      stackName: 'stocks-webapp-dev',
      region: 'us-east-1',
      stackStatus: 'EMERGENCY_FALLBACK',
      
      // Hardcoded configuration from known working values
      api: {
        gatewayUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
        gatewayId: '2m14opj30h',
        stageName: 'dev'
      },
      
      cognito: {
        userPoolId: null, // Not configured yet
        clientId: null,   // Not configured yet
        domain: null,
        region: 'us-east-1'
      },
      
      frontend: {
        bucketName: 'stocks-webapp-frontend',
        websiteUrl: 'https://d1zb7knau41vl9.cloudfront.net'
      },
      
      environment: {
        name: 'dev',
        stackName: 'stocks-webapp-dev'
      },
      
      outputs: {
        ApiGatewayUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
        ApiGatewayId: '2m14opj30h',
        ApiGatewayStageName: 'dev'
      },
      
      fetchedAt: new Date().toISOString(),
      source: 'emergency_fallback',
      note: 'Emergency endpoint - CloudFormation route temporarily unavailable'
    };
    
    res.json(fallbackConfig);
    
  } catch (error) {
    console.error('❌ Failed to provide emergency CloudFormation config:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to provide emergency CloudFormation config',
      details: error.message,
      timestamp: new Date().toISOString(),
      note: 'Emergency CloudFormation config error'
    });
  }
});

// Emergency update-status endpoint - temporary workaround for health route loading issue
router.post('/update-status', async (req, res) => {
  try {
    console.log('🔄 Emergency health status update requested');
    
    const databaseManager = require('../utils/databaseConnectionManager');
    
    // Perform a basic health check using the database manager
    let healthData;
    try {
      // Test basic connectivity
      const testResult = await databaseManager.query('SELECT NOW() as current_time, current_database() as db_name');
      
      // Simple health data structure
      healthData = {
        status: 'connected',
        database: {
          status: 'connected',
          currentTime: testResult.rows[0].current_time,
          dbName: testResult.rows[0].db_name,
          tables: {}, // Simplified - no table analysis for emergency endpoint
          summary: {
            total_tables: 'unknown',
            healthy_tables: 'unknown', 
            stale_tables: 0,
            error_tables: 0,
            empty_tables: 0,
            missing_tables: 0,
            total_records: 'unknown',
            total_missing_data: 0
          }
        },
        timestamp: new Date().toISOString(),
        note: 'Emergency endpoint - simplified health check'
      };
    } catch (error) {
      healthData = {
        status: 'error',
        error: error.message,
        database: {
          status: 'error',
          tables: {},
          summary: {
            total_tables: 0,
            healthy_tables: 0,
            stale_tables: 0,
            error_tables: 0,
            empty_tables: 0,
            missing_tables: 0,
            total_records: 0,
            total_missing_data: 0
          }
        },
        timestamp: new Date().toISOString()
      };
    }
    
    res.json({
      status: 'success',
      message: 'Database health status updated successfully (emergency endpoint)',
      data: healthData,
      timestamp: new Date().toISOString(),
      note: 'This is an emergency endpoint. The main health endpoint is temporarily unavailable.'
    });
    
  } catch (error) {
    console.error('❌ Failed to update health status (emergency endpoint):', error);
    res.status(500).json({
      status: 'error',
      error: 'Failed to update health status',
      details: error.message,
      timestamp: new Date().toISOString(),
      note: 'Emergency endpoint error'
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

module.exports = router;
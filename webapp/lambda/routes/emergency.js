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
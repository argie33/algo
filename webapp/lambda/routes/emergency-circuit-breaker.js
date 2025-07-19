/**
 * Emergency Circuit Breaker Reset Route
 * CRITICAL: Provides immediate production fix for circuit breaker crisis
 */

const express = require('express');
const { resetAllCircuitBreakers, emergencyDatabaseRecovery, getCircuitBreakerStatus } = require('../utils/circuitBreakerReset');
const router = express.Router();

// Emergency reset all circuit breakers
router.post('/reset-all', async (req, res) => {
  console.log('🚨 EMERGENCY: Reset all circuit breakers requested');
  
  try {
    const result = resetAllCircuitBreakers();
    
    console.log('✅ Emergency circuit breaker reset completed:', result);
    
    res.json({
      success: true,
      message: 'Emergency circuit breaker reset completed',
      result,
      timestamp: new Date().toISOString(),
      nextSteps: [
        'Test database connectivity',
        'Monitor circuit breaker health',
        'Check application functionality'
      ]
    });
  } catch (error) {
    console.error('❌ Emergency circuit breaker reset failed:', error);
    res.status(500).json({
      success: false,
      error: error.message,
      message: 'Emergency circuit breaker reset failed',
      timestamp: new Date().toISOString()
    });
  }
});

// Emergency database recovery
router.post('/database-recovery', async (req, res) => {
  console.log('🚨 EMERGENCY: Database recovery procedure requested');
  
  try {
    const result = await emergencyDatabaseRecovery();
    
    const statusCode = result.success ? 200 : 500;
    
    res.status(statusCode).json({
      success: result.success,
      message: result.success ? 
        'Emergency database recovery completed successfully' : 
        'Emergency database recovery completed with errors',
      result,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('❌ Emergency database recovery failed:', error);
    res.status(500).json({
      success: false,
      error: error.message,
      message: 'Emergency database recovery failed',
      timestamp: new Date().toISOString()
    });
  }
});

// Get circuit breaker status
router.get('/status', (req, res) => {
  try {
    const status = getCircuitBreakerStatus();
    
    res.json({
      success: true,
      message: 'Circuit breaker status retrieved',
      status,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('❌ Failed to get circuit breaker status:', error);
    res.status(500).json({
      success: false,
      error: error.message,
      message: 'Failed to get circuit breaker status',
      timestamp: new Date().toISOString()
    });
  }
});

// Test database connectivity
router.post('/test-database', async (req, res) => {
  console.log('🧪 Testing database connectivity after circuit breaker reset');
  
  try {
    const circuitBreakerReset = require('../utils/circuitBreakerReset');
    const result = await circuitBreakerReset.testDatabaseConnectivity();
    
    const statusCode = result.success ? 200 : 500;
    
    res.status(statusCode).json({
      success: result.success,
      message: result.success ? 
        'Database connectivity test passed' : 
        'Database connectivity test failed',
      result,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('❌ Database connectivity test failed:', error);
    res.status(500).json({
      success: false,
      error: error.message,
      message: 'Database connectivity test failed',
      timestamp: new Date().toISOString()
    });
  }
});

// Health check with circuit breaker info
router.get('/health', (req, res) => {
  try {
    const status = getCircuitBreakerStatus();
    
    const isHealthy = status.open === 0 && status.halfOpen <= 1;
    
    res.status(isHealthy ? 200 : 503).json({
      success: isHealthy,
      message: isHealthy ? 'All circuit breakers healthy' : 'Circuit breakers need attention',
      health: {
        overall: isHealthy ? 'healthy' : 'degraded',
        totalBreakers: status.totalBreakers,
        healthy: status.healthy,
        open: status.open,
        halfOpen: status.halfOpen,
        needsAttention: status.needsAttention,
        recommendations: status.recommendations
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('❌ Circuit breaker health check failed:', error);
    res.status(500).json({
      success: false,
      error: error.message,
      message: 'Circuit breaker health check failed',
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
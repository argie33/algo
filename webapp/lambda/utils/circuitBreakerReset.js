/**
 * Circuit Breaker Reset Utility
 * Provides functionality to reset circuit breakers and emergency database recovery
 */

const timeoutHelper = require('./timeoutHelper');

/**
 * Reset all circuit breakers to allow immediate retry after configuration fixes
 */
function resetAllCircuitBreakers() {
  console.log('🔄 Resetting all circuit breakers...');
  
  const status = timeoutHelper.getCircuitBreakerStatus();
  const serviceKeys = Object.keys(status);
  
  if (serviceKeys.length === 0) {
    console.log('✅ No circuit breakers found to reset');
    return { reset: 0, services: [] };
  }
  
  let resetCount = 0;
  const resetServices = [];
  
  serviceKeys.forEach(serviceKey => {
    const breaker = timeoutHelper.circuitBreakers.get(serviceKey);
    if (breaker && breaker.state !== 'closed') {
      console.log(`🔄 Resetting circuit breaker for ${serviceKey} (was ${breaker.state})`);
      
      breaker.failures = 0;
      breaker.lastFailureTime = 0;
      breaker.state = 'closed';
      breaker.halfOpenCalls = 0;
      
      resetCount++;
      resetServices.push(serviceKey);
      
      console.log(`✅ Circuit breaker for ${serviceKey} reset to closed`);
    }
  });
  
  console.log(`✅ Reset ${resetCount} circuit breakers: ${resetServices.join(', ')}`);
  
  return {
    success: true,
    reset: resetCount,
    services: resetServices,
    message: 'Circuit breakers reset successfully',
    timestamp: new Date().toISOString()
  };
}

/**
 * Reset specific circuit breaker
 */
function resetCircuitBreaker(serviceKey) {
  console.log(`🔄 Resetting circuit breaker for ${serviceKey}...`);
  
  const breaker = timeoutHelper.circuitBreakers.get(serviceKey);
  
  if (!breaker) {
    console.log(`ℹ️ No circuit breaker found for ${serviceKey}`);
    return { found: false, serviceKey };
  }
  
  const oldState = breaker.state;
  const oldFailures = breaker.failures;
  
  breaker.failures = 0;
  breaker.lastFailureTime = 0;
  breaker.state = 'closed';
  breaker.halfOpenCalls = 0;
  
  console.log(`✅ Circuit breaker for ${serviceKey} reset: ${oldState} (${oldFailures} failures) → closed (0 failures)`);
  
  return {
    success: true,
    found: true,
    serviceKey,
    oldState,
    oldFailures,
    newState: 'closed',
    timestamp: new Date().toISOString()
  };
}

/**
 * Get circuit breaker status with health recommendations
 */
function getCircuitBreakerStatus() {
  const status = timeoutHelper.getCircuitBreakerStatus();
  const serviceKeys = Object.keys(status);
  
  const health = {
    totalBreakers: serviceKeys.length,
    healthy: 0,
    open: 0,
    halfOpen: 0,
    needsAttention: [],
    recommendations: [],
    circuitBreakers: status,
    timestamp: new Date().toISOString()
  };
  
  serviceKeys.forEach(serviceKey => {
    const breaker = status[serviceKey];
    
    switch (breaker.state) {
      case 'closed':
        health.healthy++;
        break;
      case 'open':
        health.open++;
        health.needsAttention.push({
          service: serviceKey,
          state: 'open',
          failures: breaker.failures,
          openFor: Math.round(breaker.timeSinceLastFailure / 1000) + ' seconds'
        });
        break;
      case 'half-open':
        health.halfOpen++;
        health.needsAttention.push({
          service: serviceKey,
          state: 'half-open',
          failures: breaker.failures
        });
        break;
    }
  });
  
  // Generate recommendations
  if (health.open > 0) {
    health.recommendations.push('Reset open circuit breakers to restore service availability');
  }
  
  if (health.halfOpen > 0) {
    health.recommendations.push('Monitor half-open circuit breakers for stability');
  }
  
  if (health.needsAttention.length === 0) {
    health.recommendations.push('All circuit breakers are healthy');
  }
  
  return health;
}

/**
 * Test database connectivity with circuit breaker management
 */
async function testDatabaseConnectivity() {
  console.log('🧪 Testing database connectivity with circuit breaker management...');
  
  try {
    // Reset database circuit breakers first
    resetCircuitBreaker('database-query');
    resetCircuitBreaker('database-connect');
    
    // Import database service
    const database = require('./database');
    
    // Test basic connectivity
    console.log('🔍 Testing database health check...');
    const healthResult = await database.healthCheck();
    
    if (healthResult.status === 'healthy') {
      console.log('✅ Database connectivity test passed');
      console.log('✅ Database:', healthResult.database);
      console.log('✅ Version:', healthResult.version);
      
      return {
        success: true,
        health: healthResult,
        message: 'Database connectivity restored'
      };
    } else {
      console.error('❌ Database health check failed:', healthResult.error);
      return {
        success: false,
        error: healthResult.error,
        message: 'Database connectivity test failed'
      };
    }
    
  } catch (error) {
    console.error('❌ Database connectivity test error:', error.message);
    
    // Check if it's a circuit breaker issue
    const health = getCircuitBreakerStatus();
    const dbBreakers = health.needsAttention.filter(item => 
      item.service.includes('database')
    );
    
    if (dbBreakers.length > 0) {
      console.error('❌ Database circuit breakers need attention:', dbBreakers);
    }
    
    return {
      success: false,
      error: error.message,
      circuitBreakerHealth: health,
      message: 'Database connectivity test failed with errors'
    };
  }
}

/**
 * Emergency database recovery procedure
 */
async function emergencyDatabaseRecovery() {
  console.log('🚨 Starting emergency database recovery procedure...');
  
  const recovery = {
    steps: [],
    success: false,
    timestamp: new Date().toISOString()
  };
  
  try {
    // Step 1: Reset all circuit breakers
    console.log('🔄 Step 1: Resetting all circuit breakers...');
    const resetResult = resetAllCircuitBreakers();
    recovery.steps.push({
      step: 'reset_circuit_breakers',
      success: resetResult.success,
      result: resetResult
    });
    
    // Step 2: Clear database connection cache
    console.log('🔄 Step 2: Clearing database connection cache...');
    try {
      const database = require('./database');
      await database.closeDatabase();
      recovery.steps.push({
        step: 'clear_database_cache',
        success: true,
        message: 'Database connections closed'
      });
    } catch (closeError) {
      recovery.steps.push({
        step: 'clear_database_cache',
        success: false,
        error: closeError.message
      });
    }
    
    // Step 3: Test connectivity
    console.log('🔄 Step 3: Testing database connectivity...');
    const connectivityResult = await testDatabaseConnectivity();
    recovery.steps.push({
      step: 'test_connectivity',
      success: connectivityResult.success,
      result: connectivityResult
    });
    
    // Step 4: Warm up connections if successful
    if (connectivityResult.success) {
      console.log('🔄 Step 4: Warming up database connections...');
      try {
        const database = require('./database');
        await database.warmConnections();
        recovery.steps.push({
          step: 'warm_connections',
          success: true,
          message: 'Database connections warmed'
        });
      } catch (warmError) {
        recovery.steps.push({
          step: 'warm_connections',
          success: false,
          error: warmError.message
        });
      }
    }
    
    recovery.success = recovery.steps.every(step => step.success);
    
    if (recovery.success) {
      console.log('✅ Emergency database recovery completed successfully');
    } else {
      console.error('❌ Emergency database recovery completed with errors');
    }
    
    return recovery;
    
  } catch (error) {
    console.error('❌ Emergency database recovery failed:', error.message);
    recovery.steps.push({
      step: 'recovery_procedure',
      success: false,
      error: error.message
    });
    
    return recovery;
  }
}

module.exports = {
  resetAllCircuitBreakers,
  resetCircuitBreaker,
  getCircuitBreakerStatus,
  testDatabaseConnectivity,
  emergencyDatabaseRecovery
};
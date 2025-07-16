/**
 * Circuit Breaker Reset Utility
 * Provides functionality to reset circuit breakers after SSL configuration fixes
 */

const timeoutHelper = require('./timeoutHelper');

/**
 * Reset all circuit breakers to allow immediate retry after configuration fixes
 */
function resetAllCircuitBreakers() {
  const helper = new timeoutHelper();
  
  // Clear all circuit breakers
  helper.circuitBreakers.clear();
  
  console.log('🔄 All circuit breakers have been reset');
  console.log('🔌 Database connections will be attempted immediately');
  
  return {
    success: true,
    message: 'Circuit breakers reset successfully',
    timestamp: new Date().toISOString()
  };
}

/**
 * Get circuit breaker status for monitoring
 */
function getCircuitBreakerStatus() {
  const helper = new timeoutHelper();
  const status = {};
  
  for (const [serviceKey, breaker] of helper.circuitBreakers.entries()) {
    status[serviceKey] = {
      state: breaker.state,
      failures: breaker.failures,
      lastFailureTime: breaker.lastFailureTime,
      timeToRecovery: breaker.state === 'open' ? 
        Math.max(0, breaker.timeout - (Date.now() - breaker.lastFailureTime)) : 0
    };
  }
  
  return {
    circuitBreakers: status,
    totalBreakers: helper.circuitBreakers.size,
    timestamp: new Date().toISOString()
  };
}

module.exports = {
  resetAllCircuitBreakers,
  getCircuitBreakerStatus
};
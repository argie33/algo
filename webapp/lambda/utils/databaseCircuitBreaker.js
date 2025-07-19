/**
 * Enhanced Database Circuit Breaker for Lambda Environment
 */
class DatabaseCircuitBreaker {
  constructor() {
    this.state = 'closed'; // 'closed', 'open', 'half-open'
    this.failures = 0;
    this.lastFailureTime = 0;
    this.successCount = 0;
    this.lastSuccessTime = Date.now();
    
    // PRODUCTION FIX: More resilient thresholds  
    this.failureThreshold = 20; // PRODUCTION FIX: Increased from 10 to 20
    this.recoveryTimeout = 10000; // PRODUCTION FIX: Reduced from 30s to 10s
    this.halfOpenMaxCalls = 10; // PRODUCTION FIX: Increased from 5 to 10
    this.halfOpenSuccessThreshold = 3; // Keep 3 successes to close
    
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

module.exports = DatabaseCircuitBreaker;
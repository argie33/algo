/**
 * Unified Circuit Breaker - Clean State Machine Design
 * 
 * FEATURES:
 * ✅ Single decision point eliminates state conflicts
 * ✅ Automatic cleanup with built-in memory management
 * ✅ Clear state transitions with predictable behavior
 * ✅ Unified interface consistent across all usage
 * ✅ Simplified global/user state coordination
 * ✅ Comprehensive metrics and monitoring
 */

const { CloudWatchClient, PutMetricDataCommand } = require('@aws-sdk/client-cloudwatch');

// Circuit States
const CircuitState = {
  CLOSED: 'CLOSED',       // Normal operation
  OPEN: 'OPEN',           // Circuit is open, requests blocked
  HALF_OPEN: 'HALF_OPEN'  // Testing if service recovered
};

// Circuit Breaker Configuration
const DEFAULT_CONFIG = {
  // Failure thresholds
  failureThreshold: 5,        // Failures before opening circuit
  successThreshold: 3,        // Successes to close from half-open
  
  // Time windows
  openTimeoutMs: 60000,       // How long to stay open (1 minute)
  rollingWindowMs: 60000,     // Rolling window for failure counting
  
  // Half-open behavior
  halfOpenMaxCalls: 5,        // Max calls in half-open state
  
  // User-specific settings
  userFailureThreshold: 3,    // Per-user failure threshold
  
  // Monitoring
  enableMetrics: true,
  metricsNamespace: 'FinancialPlatform/CircuitBreaker'
};

// State Management
class CircuitStateManager {
  constructor(config) {
    this.config = config;
    this.state = CircuitState.CLOSED;
    this.failures = 0;
    this.successes = 0;
    this.lastFailureTime = 0;
    this.lastSuccessTime = 0;
    this.nextAttempt = 0;
    this.halfOpenCalls = 0;
    this.operationHistory = [];
  }

  // Single decision point - eliminates conflicts
  canExecute() {
    const now = Date.now();
    this.cleanup(now);

    switch (this.state) {
      case CircuitState.CLOSED:
        return true;
        
      case CircuitState.OPEN:
        if (now >= this.nextAttempt) {
          this.transitionToHalfOpen();
          return true;
        }
        return false;
        
      case CircuitState.HALF_OPEN:
        return this.halfOpenCalls < this.config.halfOpenMaxCalls;
        
      default:
        return false;
    }
  }

  recordSuccess() {
    const now = Date.now();
    this.lastSuccessTime = now;
    this.operationHistory.push({ success: true, timestamp: now });

    switch (this.state) {
      case CircuitState.HALF_OPEN:
        this.successes++;
        if (this.successes >= this.config.successThreshold) {
          this.transitionToClosed();
        }
        break;
        
      case CircuitState.CLOSED:
        // Reset failure count on success
        this.failures = Math.max(0, this.failures - 1);
        break;
    }
  }

  recordFailure() {
    const now = Date.now();
    this.lastFailureTime = now;
    this.failures++;
    this.operationHistory.push({ success: false, timestamp: now });

    switch (this.state) {
      case CircuitState.CLOSED:
        if (this.failures >= this.config.failureThreshold) {
          this.transitionToOpen();
        }
        break;
        
      case CircuitState.HALF_OPEN:
        this.transitionToOpen();
        break;
    }
  }

  recordHalfOpenAttempt() {
    this.halfOpenCalls++;
  }

  // Clear state transitions
  transitionToOpen() {
    console.log(`🚨 Circuit breaker OPENING (failures: ${this.failures})`);
    this.state = CircuitState.OPEN;
    this.nextAttempt = Date.now() + this.config.openTimeoutMs;
    this.halfOpenCalls = 0;
    this.successes = 0;
  }

  transitionToHalfOpen() {
    console.log('🔄 Circuit breaker moving to HALF_OPEN');
    this.state = CircuitState.HALF_OPEN;
    this.halfOpenCalls = 0;
    this.successes = 0;
  }

  transitionToClosed() {
    console.log('✅ Circuit breaker CLOSED (service recovered)');
    this.state = CircuitState.CLOSED;
    this.failures = 0;
    this.successes = 0;
    this.halfOpenCalls = 0;
  }

  // Automatic cleanup
  cleanup(now) {
    const cutoff = now - this.config.rollingWindowMs;
    this.operationHistory = this.operationHistory.filter(op => op.timestamp > cutoff);

    // Reset failure count if outside rolling window
    if (this.lastFailureTime < cutoff && this.state === CircuitState.CLOSED) {
      this.failures = 0;
    }
  }

  getStatus() {
    const now = Date.now();
    return {
      state: this.state,
      failures: this.failures,
      successes: this.successes,
      halfOpenCalls: this.halfOpenCalls,
      nextAttemptMs: this.nextAttempt > now ? this.nextAttempt - now : 0,
      operationCount: this.operationHistory.length,
      lastFailureAge: this.lastFailureTime ? now - this.lastFailureTime : null,
      lastSuccessAge: this.lastSuccessTime ? now - this.lastSuccessTime : null
    };
  }

  reset() {
    this.state = CircuitState.CLOSED;
    this.failures = 0;
    this.successes = 0;
    this.halfOpenCalls = 0;
    this.nextAttempt = 0;
    this.operationHistory = [];
  }
}

// User State Manager with automatic cleanup
class UserStateManager {
  constructor(config) {
    this.config = config;
    this.userStates = new Map();
    this.cleanupInterval = 5 * 60 * 1000; // 5 minutes
    
    // Start automatic cleanup
    this.startCleanup();
  }

  getOrCreateState(userId) {
    if (!this.userStates.has(userId)) {
      this.userStates.set(userId, new CircuitStateManager({
        ...this.config,
        failureThreshold: this.config.userFailureThreshold
      }));
    }
    return this.userStates.get(userId);
  }

  canExecute(userId) {
    if (!userId) return true;
    
    const userState = this.getOrCreateState(userId);
    return userState.canExecute();
  }

  recordSuccess(userId) {
    if (!userId) return;
    
    const userState = this.getOrCreateState(userId);
    userState.recordSuccess();
  }

  recordFailure(userId) {
    if (!userId) return;
    
    const userState = this.getOrCreateState(userId);
    userState.recordFailure();
  }

  recordHalfOpenAttempt(userId) {
    if (!userId) return;
    
    const userState = this.getOrCreateState(userId);
    userState.recordHalfOpenAttempt();
  }

  startCleanup() {
    setInterval(() => {
      this.cleanup();
    }, this.cleanupInterval);
  }

  // Built-in memory management
  cleanup() {
    const now = Date.now();
    const staleThreshold = 30 * 60 * 1000; // 30 minutes
    const deletedUsers = [];

    for (const [userId, state] of this.userStates) {
      // Remove stale user states
      if (state.lastFailureTime === 0 && state.lastSuccessTime === 0) {
        this.userStates.delete(userId);
        deletedUsers.push(userId);
      } else if (state.lastFailureTime > 0 && 
                now - state.lastFailureTime > staleThreshold &&
                state.state === CircuitState.CLOSED) {
        this.userStates.delete(userId);
        deletedUsers.push(userId);
      }
    }

    if (deletedUsers.length > 0) {
      console.log(`🧹 Cleaned up ${deletedUsers.length} stale user circuit states`);
    }

    // Limit total user states to prevent memory issues
    if (this.userStates.size > 10000) {
      const sortedUsers = Array.from(this.userStates.entries())
        .sort(([,a], [,b]) => a.lastSuccessTime - b.lastSuccessTime)
        .slice(0, this.userStates.size - 5000);

      for (const [userId] of sortedUsers) {
        this.userStates.delete(userId);
      }
      
      console.warn(`🚨 Emergency cleanup: Reduced user states to ${this.userStates.size}`);
    }
  }

  getStats() {
    const states = Array.from(this.userStates.values());
    const openStates = states.filter(s => s.state === CircuitState.OPEN);
    const halfOpenStates = states.filter(s => s.state === CircuitState.HALF_OPEN);

    return {
      totalUsers: states.length,
      openCircuits: openStates.length,
      halfOpenCircuits: halfOpenStates.length,
      healthyUsers: states.length - openStates.length,
      healthRate: states.length > 0 ? 
        ((states.length - openStates.length) / states.length * 100).toFixed(1) + '%' : '100%'
    };
  }

  reset() {
    this.userStates.clear();
  }
}

// Circuit Open Error
class CircuitOpenError extends Error {
  constructor(retryAfterMs, isUser = false) {
    const retryAfterSeconds = Math.ceil(retryAfterMs / 1000);
    super(`Circuit breaker is OPEN. Retry after ${retryAfterSeconds} seconds.`);
    this.name = 'CircuitOpenError';
    this.retryAfterMs = retryAfterMs;
    this.retryAfterSeconds = retryAfterSeconds;
    this.isUserSpecific = isUser;
  }
}

// Main Unified Circuit Breaker
class UnifiedCircuitBreaker {
  constructor(options = {}) {
    this.config = { ...DEFAULT_CONFIG, ...options };
    this.globalState = new CircuitStateManager(this.config);
    this.userStateManager = new UserStateManager(this.config);
    
    // Metrics client
    if (this.config.enableMetrics) {
      this.cloudWatch = new CloudWatchClient({
        region: process.env.AWS_REGION || 'us-east-1'
      });
    }

    console.log('⚡ Unified Circuit Breaker initialized');
  }

  // Unified interface - single execution method
  async execute(operation, context = {}) {
    const { userId, operationName = 'default' } = context;
    const startTime = Date.now();

    // Single decision point
    const canExecute = this.canExecute(userId);
    if (!canExecute) {
      const retryAfter = this.getRetryAfterMs(userId);
      await this.recordMetric('CircuitBreakerBlocked', 1, userId);
      throw new CircuitOpenError(retryAfter, !!userId);
    }

    // Track half-open attempts
    if (this.globalState.state === CircuitState.HALF_OPEN) {
      this.globalState.recordHalfOpenAttempt();
    }
    if (userId && this.userStateManager.getOrCreateState(userId).state === CircuitState.HALF_OPEN) {
      this.userStateManager.recordHalfOpenAttempt(userId);
    }

    try {
      const result = await operation();
      const duration = Date.now() - startTime;
      
      await this.recordSuccess(userId, operationName, duration);
      return result;
    } catch (error) {
      const duration = Date.now() - startTime;
      
      await this.recordFailure(userId, operationName, error, duration);
      throw error;
    }
  }

  // Simplified state evaluation
  canExecute(userId) {
    const globalOk = this.globalState.canExecute();
    const userOk = this.userStateManager.canExecute(userId);
    
    return globalOk && userOk;
  }

  async recordSuccess(userId, operationName, duration) {
    this.globalState.recordSuccess();
    this.userStateManager.recordSuccess(userId);
    
    await this.recordMetric('OperationSuccess', 1, userId);
    await this.recordMetric('OperationDuration', duration, userId);
    
    console.log(`✅ Circuit breaker: Operation succeeded in ${duration}ms`);
  }

  async recordFailure(userId, operationName, error, duration) {
    this.globalState.recordFailure();
    this.userStateManager.recordFailure(userId);
    
    await this.recordMetric('OperationFailure', 1, userId);
    await this.recordMetric('OperationDuration', duration, userId);
    
    console.error(`❌ Circuit breaker: Operation failed in ${duration}ms - ${error.message}`);
  }

  getRetryAfterMs(userId) {
    const globalRetry = this.globalState.nextAttempt > Date.now() ? 
      this.globalState.nextAttempt - Date.now() : 0;
    
    let userRetry = 0;
    if (userId) {
      const userState = this.userStateManager.getOrCreateState(userId);
      userRetry = userState.nextAttempt > Date.now() ? 
        userState.nextAttempt - Date.now() : 0;
    }
    
    return Math.max(globalRetry, userRetry);
  }

  // Comprehensive status for monitoring
  getStatus(userId = null) {
    const globalStatus = this.globalState.getStatus();
    const userStats = this.userStateManager.getStats();
    
    const status = {
      global: {
        ...globalStatus,
        isHealthy: globalStatus.state !== CircuitState.OPEN
      },
      users: userStats,
      config: {
        failureThreshold: this.config.failureThreshold,
        userFailureThreshold: this.config.userFailureThreshold,
        openTimeoutMs: this.config.openTimeoutMs,
        halfOpenMaxCalls: this.config.halfOpenMaxCalls
      },
      timestamp: new Date().toISOString()
    };

    // Add user-specific status if requested
    if (userId) {
      const userState = this.userStateManager.getOrCreateState(userId);
      status.user = userState.getStatus();
    }

    return status;
  }

  // Health metrics for monitoring
  getHealthMetrics() {
    const globalStatus = this.globalState.getStatus();
    const userStats = this.userStateManager.getStats();
    
    return {
      healthy: globalStatus.state !== CircuitState.OPEN,
      globalState: globalStatus.state,
      globalFailures: globalStatus.failures,
      totalUsers: userStats.totalUsers,
      unhealthyUsers: userStats.openCircuits,
      halfOpenUsers: userStats.halfOpenCircuits,
      userHealthRate: userStats.healthRate,
      overallHealth: globalStatus.state === CircuitState.OPEN ? 'UNHEALTHY' : 
                    userStats.openCircuits > userStats.totalUsers * 0.1 ? 'DEGRADED' : 'HEALTHY'
    };
  }

  async recordMetric(metricName, value, userId = null) {
    if (!this.config.enableMetrics || !this.cloudWatch) {
      return;
    }

    try {
      const dimensions = [
        { Name: 'Service', Value: 'UnifiedCircuitBreaker' }
      ];

      if (userId) {
        // Mask user ID for privacy
        dimensions.push({ 
          Name: 'UserType', 
          Value: userId.startsWith('dev-') ? 'Development' : 'Production'
        });
      }

      await this.cloudWatch.send(new PutMetricDataCommand({
        Namespace: this.config.metricsNamespace,
        MetricData: [{
          MetricName: metricName,
          Value: value,
          Unit: metricName.includes('Duration') ? 'Milliseconds' : 'Count',
          Dimensions: dimensions,
          Timestamp: new Date()
        }]
      }));
    } catch (error) {
      console.warn('⚠️ Failed to record circuit breaker metric:', error.message);
    }
  }

  // Force reset for emergency situations
  forceReset(userId = null) {
    if (userId) {
      const userState = this.userStateManager.getOrCreateState(userId);
      userState.reset();
      console.log(`🚨 Circuit breaker force reset for user: ${userId}`);
    } else {
      this.globalState.reset();
      this.userStateManager.reset();
      console.log('🚨 Circuit breaker global force reset');
    }
  }

  // Create wrapper for specific services
  createServiceWrapper(serviceName, defaultContext = {}) {
    return {
      execute: (operation, context = {}) => {
        return this.execute(operation, {
          ...defaultContext,
          ...context,
          operationName: context.operationName || serviceName
        });
      },
      
      getStatus: (userId) => this.getStatus(userId),
      
      forceReset: (userId) => this.forceReset(userId)
    };
  }
}

module.exports = {
  UnifiedCircuitBreaker,
  CircuitState,
  CircuitOpenError
};
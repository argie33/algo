/**
 * Enhanced Circuit Breaker for Live Data Infrastructure
 * 
 * Multi-service circuit breaker with user-aware protection,
 * adaptive thresholds, and intelligent fallback strategies
 * for live data feeds, API services, and database connections
 */

const { CloudWatchClient, PutMetricDataCommand } = require('@aws-sdk/client-cloudwatch');

class CircuitBreaker {
  constructor(options = {}) {
    this.config = {
      // Failure thresholds
      failureThreshold: options.failureThreshold || 5,
      successThreshold: options.successThreshold || 3,
      timeout: options.timeout || 30000, // 30 seconds
      
      // User-aware settings
      userFailureThreshold: options.userFailureThreshold || 3,
      globalFailureThreshold: options.globalFailureThreshold || 20,
      
      // Time windows
      rollingWindowMs: options.rollingWindowMs || 60000, // 1 minute
      halfOpenMaxCalls: options.halfOpenMaxCalls || 5,
      
      // Monitoring
      enableMetrics: options.enableMetrics !== false,
      metricNamespace: options.metricNamespace || 'FinancialPlatform/CircuitBreaker'
    };

    // Circuit breaker states
    this.states = {
      CLOSED: 'CLOSED',
      OPEN: 'OPEN',
      HALF_OPEN: 'HALF_OPEN'
    };

    // Global state
    this.globalState = {
      state: this.states.CLOSED,
      failures: 0,
      successes: 0,
      lastFailureTime: null,
      nextAttempt: null,
      halfOpenCalls: 0
    };

    // User-specific states
    this.userStates = new Map();

    // Rolling window tracking
    this.operationHistory = [];
    this.userOperationHistory = new Map();

    // Metrics client
    if (this.config.enableMetrics) {
      this.cloudWatch = new CloudWatchClient({
        region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
      });
    }

    // Cleanup interval
    this.cleanupInterval = setInterval(() => {
      this.cleanup();
    }, this.config.rollingWindowMs);
  }

  /**
   * Get or create user state
   */
  getUserState(userId) {
    if (!this.userStates.has(userId)) {
      this.userStates.set(userId, {
        state: this.states.CLOSED,
        failures: 0,
        successes: 0,
        lastFailureTime: null,
        nextAttempt: null,
        operations: []
      });
    }
    return this.userStates.get(userId);
  }

  /**
   * Check if operation should be allowed
   */
  async canExecute(userId, operation = 'default') {
    const now = Date.now();
    const userState = this.getUserState(userId);

    // Clean up old operations
    this.cleanupUserOperations(userId);
    this.cleanupGlobalOperations();

    // Check global circuit breaker first
    if (this.globalState.state === this.states.OPEN) {
      if (now >= this.globalState.nextAttempt) {
        console.log('🔄 Global circuit breaker moving to HALF_OPEN');
        this.globalState.state = this.states.HALF_OPEN;
        this.globalState.halfOpenCalls = 0;
      } else {
        await this.recordMetric('CircuitBreakerBlocked', 1, 'Global');
        throw new Error('Global circuit breaker is OPEN - service temporarily unavailable');
      }
    }

    // Check user-specific circuit breaker
    if (userState.state === this.states.OPEN) {
      if (now >= userState.nextAttempt) {
        console.log(`🔄 User circuit breaker moving to HALF_OPEN for user ${userId}`);
        userState.state = this.states.HALF_OPEN;
        userState.halfOpenCalls = 0;
      } else {
        await this.recordMetric('CircuitBreakerBlocked', 1, 'User', userId);
        throw new Error(`User circuit breaker is OPEN - operations temporarily disabled for this user`);
      }
    }

    // Allow operation but track for half-open state
    if (this.globalState.state === this.states.HALF_OPEN) {
      this.globalState.halfOpenCalls++;
      if (this.globalState.halfOpenCalls > this.config.halfOpenMaxCalls) {
        this.globalState.state = this.states.OPEN;
        this.globalState.nextAttempt = now + this.config.timeout;
        throw new Error('Global circuit breaker returned to OPEN - too many half-open attempts');
      }
    }

    if (userState.state === this.states.HALF_OPEN) {
      userState.halfOpenCalls = (userState.halfOpenCalls || 0) + 1;
      if (userState.halfOpenCalls > this.config.halfOpenMaxCalls) {
        userState.state = this.states.OPEN;
        userState.nextAttempt = now + this.config.timeout;
        throw new Error('User circuit breaker returned to OPEN - too many half-open attempts');
      }
    }

    return true;
  }

  /**
   * Record operation result
   */
  async recordResult(userId, operation, success, duration, error = null) {
    const now = Date.now();
    const userState = this.getUserState(userId);

    // Record in history
    const operationRecord = {
      userId,
      operation,
      success,
      duration,
      timestamp: now,
      error: error?.message
    };

    // Add to global history
    this.operationHistory.push(operationRecord);

    // Add to user history
    if (!this.userOperationHistory.has(userId)) {
      this.userOperationHistory.set(userId, []);
    }
    this.userOperationHistory.get(userId).push(operationRecord);

    // Update states based on result
    if (success) {
      await this.handleSuccess(userId, userState, duration);
    } else {
      await this.handleFailure(userId, userState, error);
    }

    // Send metrics
    await this.recordMetric('OperationResult', 1, success ? 'Success' : 'Failure', userId);
    await this.recordMetric('OperationDuration', duration, 'Milliseconds', userId);
  }

  /**
   * Handle successful operation
   */
  async handleSuccess(userId, userState, duration) {
    // Reset user state if in half-open and enough successes
    if (userState.state === this.states.HALF_OPEN) {
      userState.successes++;
      if (userState.successes >= this.config.successThreshold) {
        console.log(`✅ User circuit breaker CLOSED for user ${userId}`);
        userState.state = this.states.CLOSED;
        userState.failures = 0;
        userState.successes = 0;
        await this.recordMetric('CircuitBreakerClosed', 1, 'User', userId);
      }
    }

    // Reset global state if in half-open and enough successes
    if (this.globalState.state === this.states.HALF_OPEN) {
      this.globalState.successes++;
      if (this.globalState.successes >= this.config.successThreshold) {
        console.log('✅ Global circuit breaker CLOSED');
        this.globalState.state = this.states.CLOSED;
        this.globalState.failures = 0;
        this.globalState.successes = 0;
        await this.recordMetric('CircuitBreakerClosed', 1, 'Global');
      }
    }
  }

  /**
   * Handle failed operation
   */
  async handleFailure(userId, userState, error) {
    const now = Date.now();

    // Increment failure counts
    userState.failures++;
    userState.lastFailureTime = now;
    this.globalState.failures++;
    this.globalState.lastFailureTime = now;

    // Check user-specific threshold
    if (userState.failures >= this.config.userFailureThreshold && 
        userState.state === this.states.CLOSED) {
      console.log(`❌ User circuit breaker OPENED for user ${userId}`);
      userState.state = this.states.OPEN;
      userState.nextAttempt = now + this.config.timeout;
      await this.recordMetric('CircuitBreakerOpened', 1, 'User', userId);
    }

    // Check global threshold
    if (this.globalState.failures >= this.config.globalFailureThreshold && 
        this.globalState.state === this.states.CLOSED) {
      console.log('❌ Global circuit breaker OPENED');
      this.globalState.state = this.states.OPEN;
      this.globalState.nextAttempt = now + this.config.timeout;
      await this.recordMetric('CircuitBreakerOpened', 1, 'Global');
    }

    // Log failure details
    console.error(`Circuit breaker recorded failure for user ${userId}:`, {
      error: error?.message,
      userFailures: userState.failures,
      globalFailures: this.globalState.failures,
      userState: userState.state,
      globalState: this.globalState.state
    });
  }

  /**
   * Clean up old operations
   */
  cleanupUserOperations(userId) {
    const cutoff = Date.now() - this.config.rollingWindowMs;
    
    if (this.userOperationHistory.has(userId)) {
      const operations = this.userOperationHistory.get(userId);
      const filtered = operations.filter(op => op.timestamp > cutoff);
      this.userOperationHistory.set(userId, filtered);
    }

    // Clean up user state if no recent operations
    const userState = this.userStates.get(userId);
    if (userState && userState.lastFailureTime && 
        userState.lastFailureTime < cutoff && 
        userState.state === this.states.CLOSED) {
      userState.failures = 0;
    }
  }

  /**
   * Clean up global operations
   */
  cleanupGlobalOperations() {
    const cutoff = Date.now() - this.config.rollingWindowMs;
    this.operationHistory = this.operationHistory.filter(op => op.timestamp > cutoff);

    // Reset global failures if outside window
    if (this.globalState.lastFailureTime && 
        this.globalState.lastFailureTime < cutoff && 
        this.globalState.state === this.states.CLOSED) {
      this.globalState.failures = 0;
    }
  }

  /**
   * General cleanup
   */
  cleanup() {
    const now = Date.now();
    const cutoff = now - this.config.rollingWindowMs * 2; // Keep longer history for analysis

    // Clean up user states that haven't been used recently
    for (const [userId, state] of this.userStates.entries()) {
      if (!state.lastFailureTime || state.lastFailureTime < cutoff) {
        if (state.state === this.states.CLOSED && state.failures === 0) {
          this.userStates.delete(userId);
          this.userOperationHistory.delete(userId);
        }
      }
    }

    // Limit history size
    if (this.operationHistory.length > 10000) {
      this.operationHistory = this.operationHistory.slice(-5000);
    }
  }

  /**
   * Record CloudWatch metric
   */
  async recordMetric(metricName, value, unit = 'Count', userId = null) {
    if (!this.config.enableMetrics || !this.cloudWatch) {
      return;
    }

    try {
      const dimensions = [
        { Name: 'Service', Value: 'ApiKeyService' }
      ];

      if (userId) {
        dimensions.push({ Name: 'UserId', Value: userId.substring(0, 8) + '***' }); // Mask for privacy
      }

      await this.cloudWatch.send(new PutMetricDataCommand({
        Namespace: this.config.metricNamespace,
        MetricData: [{
          MetricName: metricName,
          Value: value,
          Unit: unit,
          Dimensions: dimensions,
          Timestamp: new Date()
        }]
      }));
    } catch (error) {
      console.warn('⚠️ Failed to record metric:', error.message);
    }
  }

  /**
   * Get circuit breaker status
   */
  getStatus(userId = null) {
    const now = Date.now();
    
    const globalStatus = {
      state: this.globalState.state,
      failures: this.globalState.failures,
      successes: this.globalState.successes,
      nextAttempt: this.globalState.nextAttempt,
      secondsUntilRetry: this.globalState.nextAttempt ? 
        Math.max(0, Math.ceil((this.globalState.nextAttempt - now) / 1000)) : 0
    };

    if (userId) {
      const userState = this.getUserState(userId);
      return {
        global: globalStatus,
        user: {
          state: userState.state,
          failures: userState.failures,
          successes: userState.successes,
          nextAttempt: userState.nextAttempt,
          secondsUntilRetry: userState.nextAttempt ? 
            Math.max(0, Math.ceil((userState.nextAttempt - now) / 1000)) : 0
        }
      };
    }

    return { global: globalStatus };
  }

  /**
   * Get health metrics
   */
  getHealthMetrics() {
    const now = Date.now();
    const recentWindow = now - this.config.rollingWindowMs;
    
    // Global metrics
    const recentOperations = this.operationHistory.filter(op => op.timestamp > recentWindow);
    const totalOperations = recentOperations.length;
    const successfulOperations = recentOperations.filter(op => op.success).length;
    const successRate = totalOperations > 0 ? (successfulOperations / totalOperations * 100).toFixed(2) : '100';
    
    const avgLatency = recentOperations.length > 0 
      ? (recentOperations.reduce((sum, op) => sum + op.duration, 0) / recentOperations.length).toFixed(2)
      : '0';

    // User metrics
    const activeUsers = this.userStates.size;
    const usersWithOpenCircuits = Array.from(this.userStates.values())
      .filter(state => state.state === this.states.OPEN).length;

    return {
      global: {
        state: this.globalState.state,
        totalOperations,
        successRate: `${successRate}%`,
        averageLatency: `${avgLatency}ms`,
        failures: this.globalState.failures,
        isHealthy: this.globalState.state !== this.states.OPEN
      },
      users: {
        activeUsers,
        usersWithOpenCircuits,
        healthyUserRate: activeUsers > 0 ? 
          `${(((activeUsers - usersWithOpenCircuits) / activeUsers) * 100).toFixed(1)}%` : '100%'
      },
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Force reset circuit breaker (emergency use)
   */
  forceReset(userId = null) {
    console.log(`🚨 Force resetting circuit breaker${userId ? ` for user ${userId}` : ' globally'}`);
    
    if (userId) {
      const userState = this.getUserState(userId);
      userState.state = this.states.CLOSED;
      userState.failures = 0;
      userState.successes = 0;
      userState.nextAttempt = null;
    } else {
      // Reset global state
      this.globalState.state = this.states.CLOSED;
      this.globalState.failures = 0;
      this.globalState.successes = 0;
      this.globalState.nextAttempt = null;
      
      // Reset all user states
      for (const userState of this.userStates.values()) {
        userState.state = this.states.CLOSED;
        userState.failures = 0;
        userState.successes = 0;
        userState.nextAttempt = null;
      }
    }
  }

  /**
   * Cleanup resources
   */
  destroy() {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
    }
  }
}

module.exports = CircuitBreaker;
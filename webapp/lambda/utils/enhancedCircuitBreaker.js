/**
 * Enhanced Circuit Breaker System for Live Data Infrastructure
 * 
 * Multi-service circuit breaker with intelligent fallback strategies,
 * adaptive thresholds, and comprehensive monitoring for:
 * - Live data feeds (Alpaca, Polygon, Yahoo)
 * - API key services (Parameter Store, Database)
 * - Database connections
 * - WebSocket connections
 * - External API integrations
 */

const { createLogger } = require('./structuredLogger');
const intelligentCachingSystem = require('./intelligentCachingSystem');

class EnhancedCircuitBreaker {
  constructor(serviceName, options = {}) {
    this.serviceName = serviceName;
    this.logger = createLogger('financial-platform', `circuit-breaker-${serviceName}`);
    
    this.config = {
      // Failure thresholds
      failureThreshold: options.failureThreshold || 5,
      successThreshold: options.successThreshold || 3,
      timeout: options.timeout || 30000, // 30 seconds
      
      // Adaptive thresholds
      adaptiveThresholds: options.adaptiveThresholds !== false,
      maxFailureThreshold: options.maxFailureThreshold || 20,
      minFailureThreshold: options.minFailureThreshold || 3,
      
      // Time windows
      rollingWindowMs: options.rollingWindowMs || 60000, // 1 minute
      halfOpenMaxCalls: options.halfOpenMaxCalls || 5,
      
      // Service-specific configurations
      criticalService: options.criticalService || false,
      fallbackEnabled: options.fallbackEnabled !== false,
      cacheFallback: options.cacheFallback !== false,
      
      // User-aware settings
      userFailureThreshold: options.userFailureThreshold || 3,
      userTimeoutMs: options.userTimeoutMs || 10000,
      
      // Monitoring
      enableMetrics: options.enableMetrics !== false,
      enableAlerting: options.enableAlerting || false
    };

    // Circuit breaker states
    this.states = {
      CLOSED: 'CLOSED',           // Normal operation
      OPEN: 'OPEN',               // Blocking requests
      HALF_OPEN: 'HALF_OPEN',     // Testing recovery
      DEGRADED: 'DEGRADED'        // Partial functionality with fallbacks
    };

    // Global service state
    this.serviceState = {
      state: this.states.CLOSED,
      failures: 0,
      successes: 0,
      lastFailureTime: null,
      lastSuccessTime: null,
      nextAttempt: null,
      halfOpenCalls: 0,
      degradedMode: false,
      failureHistory: [], // Rolling window of failures
      responseTimeHistory: []
    };

    // User-specific states for user-aware protection
    this.userStates = new Map();
    
    // Service-specific fallback strategies
    this.fallbackStrategies = new Map();
    this.initializeFallbackStrategies();
    
    // Performance monitoring
    this.metrics = {
      totalRequests: 0,
      totalFailures: 0,
      totalSuccesses: 0,
      avgResponseTime: 0,
      stateTransitions: {
        closedToOpen: 0,
        openToHalfOpen: 0,
        halfOpenToClosed: 0,
        halfOpenToOpen: 0,
        toDegraded: 0,
        fromDegraded: 0
      }
    };
    
    // Start background monitoring
    this.startMonitoring();
  }

  /**
   * Execute function with circuit breaker protection
   */
  async execute(fn, options = {}) {
    const { userId, fallback, skipUserCheck = false, priority = 'normal' } = options;
    const startTime = Date.now();
    
    try {
      this.metrics.totalRequests++;
      
      // Check user-specific circuit breaker first (if applicable)
      if (userId && !skipUserCheck) {
        const userAllowed = this.checkUserState(userId);
        if (!userAllowed) {
          return this.handleUserBlocked(userId, fallback);
        }
      }
      
      // Check global service state
      const serviceAllowed = this.checkServiceState(priority);
      if (!serviceAllowed) {
        return this.handleServiceBlocked(fallback, options);
      }
      
      // Execute the function
      const result = await this.executeWithTimeout(fn, options);
      
      // Record success
      this.recordSuccess(userId, Date.now() - startTime);
      
      return {
        success: true,
        data: result,
        source: 'primary',
        responseTime: Date.now() - startTime,
        circuitBreakerState: this.serviceState.state
      };
      
    } catch (error) {
      // Record failure
      this.recordFailure(userId, error, Date.now() - startTime);
      
      // Handle failure with fallback
      return this.handleFailure(error, fallback, options);
    }
  }

  /**
   * Check if service is available for requests
   */
  checkServiceState(priority = 'normal') {
    const now = Date.now();
    
    switch (this.serviceState.state) {
      case this.states.CLOSED:
        return true;
        
      case this.states.OPEN:
        // Check if we should transition to half-open
        if (now >= this.serviceState.nextAttempt) {
          this.transitionToHalfOpen();
          return priority === 'high'; // Only allow high priority during half-open
        }
        return false;
        
      case this.states.HALF_OPEN:
        // Limit concurrent calls during half-open
        return this.serviceState.halfOpenCalls < this.config.halfOpenMaxCalls;
        
      case this.states.DEGRADED:
        // Allow requests but with reduced capacity
        return priority !== 'low';
        
      default:
        return false;
    }
  }

  /**
   * Check user-specific circuit breaker state
   */
  checkUserState(userId) {
    const userState = this.getUserState(userId);
    const now = Date.now();
    
    if (userState.failures >= this.config.userFailureThreshold) {
      if (userState.nextAttempt && now < userState.nextAttempt) {
        return false;
      }
      // Reset user state after timeout
      userState.failures = 0;
      userState.nextAttempt = null;
    }
    
    return true;
  }

  /**
   * Execute function with timeout protection
   */
  async executeWithTimeout(fn, options) {
    const timeout = options.timeout || this.config.timeout;
    
    return Promise.race([
      fn(),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Circuit breaker timeout')), timeout)
      )
    ]);
  }

  /**
   * Record successful execution
   */
  recordSuccess(userId, responseTime) {
    this.metrics.totalSuccesses++;
    this.updateResponseTime(responseTime);
    
    // Update service state
    this.serviceState.successes++;
    this.serviceState.lastSuccessTime = Date.now();
    this.serviceState.responseTimeHistory.push({
      time: Date.now(),
      duration: responseTime
    });
    
    // Trim history to rolling window
    this.trimHistories();
    
    // Update user state if applicable
    if (userId) {
      const userState = this.getUserState(userId);
      userState.successes++;
      userState.failures = Math.max(0, userState.failures - 1); // Gradual recovery
    }
    
    // Check for state transitions
    this.checkStateTransitions();
  }

  /**
   * Record failed execution
   */
  recordFailure(userId, error, responseTime) {
    this.metrics.totalFailures++;
    this.updateResponseTime(responseTime);
    
    // Update service state
    this.serviceState.failures++;
    this.serviceState.lastFailureTime = Date.now();
    this.serviceState.failureHistory.push({
      time: Date.now(),
      error: error.message,
      duration: responseTime
    });
    
    // Trim history to rolling window
    this.trimHistories();
    
    // Update user state if applicable
    if (userId) {
      const userState = this.getUserState(userId);
      userState.failures++;
      userState.lastFailure = Date.now();
      
      if (userState.failures >= this.config.userFailureThreshold) {
        userState.nextAttempt = Date.now() + this.config.userTimeoutMs;
      }
    }
    
    // Check for state transitions
    this.checkStateTransitions();
    
    this.logger.warn('Circuit breaker recorded failure', {
      service: this.serviceName,
      error: error.message,
      userId,
      currentState: this.serviceState.state,
      totalFailures: this.serviceState.failures
    });
  }

  /**
   * Check and perform state transitions
   */
  checkStateTransitions() {
    const recentFailures = this.getRecentFailures();
    const adaptiveThreshold = this.calculateAdaptiveThreshold();
    
    switch (this.serviceState.state) {
      case this.states.CLOSED:
        if (recentFailures >= adaptiveThreshold) {
          if (this.config.fallbackEnabled && recentFailures < adaptiveThreshold * 2) {
            this.transitionToDegraded();
          } else {
            this.transitionToOpen();
          }
        }
        break;
        
      case this.states.HALF_OPEN:
        if (this.serviceState.successes >= this.config.successThreshold) {
          this.transitionToClosed();
        } else if (recentFailures > 0) {
          this.transitionToOpen();
        }
        break;
        
      case this.states.DEGRADED:
        if (recentFailures >= adaptiveThreshold * 2) {
          this.transitionToOpen();
        } else if (recentFailures === 0 && this.serviceState.successes >= this.config.successThreshold) {
          this.transitionToClosed();
        }
        break;
    }
  }

  /**
   * Calculate adaptive failure threshold based on recent performance
   */
  calculateAdaptiveThreshold() {
    if (!this.config.adaptiveThresholds) {
      return this.config.failureThreshold;
    }
    
    const recentResponseTimes = this.serviceState.responseTimeHistory
      .filter(entry => Date.now() - entry.time < this.config.rollingWindowMs);
    
    if (recentResponseTimes.length === 0) {
      return this.config.failureThreshold;
    }
    
    const avgResponseTime = recentResponseTimes.reduce((sum, entry) => sum + entry.duration, 0) / recentResponseTimes.length;
    
    // Increase threshold for slow but working service
    let adaptiveThreshold = this.config.failureThreshold;
    if (avgResponseTime > 5000) { // Slow service
      adaptiveThreshold = Math.min(this.config.maxFailureThreshold, this.config.failureThreshold * 2);
    } else if (avgResponseTime < 1000) { // Fast service
      adaptiveThreshold = Math.max(this.config.minFailureThreshold, this.config.failureThreshold * 0.8);
    }
    
    return Math.floor(adaptiveThreshold);
  }

  /**
   * State transition methods
   */
  transitionToOpen() {
    const previousState = this.serviceState.state;
    this.serviceState.state = this.states.OPEN;
    this.serviceState.nextAttempt = Date.now() + this.config.timeout;
    this.serviceState.halfOpenCalls = 0;
    
    this.metrics.stateTransitions[`${previousState.toLowerCase()}ToOpen`]++;
    
    this.logger.error('Circuit breaker opened', {
      service: this.serviceName,
      previousState,
      failures: this.serviceState.failures,
      nextAttempt: new Date(this.serviceState.nextAttempt).toISOString()
    });
  }

  transitionToHalfOpen() {
    const previousState = this.serviceState.state;
    this.serviceState.state = this.states.HALF_OPEN;
    this.serviceState.halfOpenCalls = 0;
    this.serviceState.successes = 0;
    
    this.metrics.stateTransitions.openToHalfOpen++;
    
    this.logger.info('Circuit breaker half-opened', {
      service: this.serviceName,
      previousState
    });
  }

  transitionToClosed() {
    const previousState = this.serviceState.state;
    this.serviceState.state = this.states.CLOSED;
    this.serviceState.failures = 0;
    this.serviceState.successes = 0;
    this.serviceState.degradedMode = false;
    
    this.metrics.stateTransitions[`${previousState.toLowerCase()}ToClosed`]++;
    
    this.logger.info('Circuit breaker closed', {
      service: this.serviceName,
      previousState
    });
  }

  transitionToDegraded() {
    const previousState = this.serviceState.state;
    this.serviceState.state = this.states.DEGRADED;
    this.serviceState.degradedMode = true;
    
    this.metrics.stateTransitions.toDegraded++;
    
    this.logger.warn('Circuit breaker degraded', {
      service: this.serviceName,
      previousState,
      message: 'Service running with reduced capacity and fallbacks'
    });
  }

  /**
   * Handle different failure scenarios
   */
  async handleFailure(error, fallback, options) {
    // Try cache fallback first
    if (this.config.cacheFallback) {
      const cacheResult = await this.tryCacheFallback(options);
      if (cacheResult) {
        return {
          success: true,
          data: cacheResult,
          source: 'cache_fallback',
          circuitBreakerState: this.serviceState.state,
          warning: 'Data served from cache due to service failure'
        };
      }
    }
    
    // Try service-specific fallback
    const serviceFallback = this.fallbackStrategies.get(this.serviceName);
    if (serviceFallback) {
      try {
        const fallbackResult = await serviceFallback(options);
        return {
          success: true,
          data: fallbackResult,
          source: 'service_fallback',
          circuitBreakerState: this.serviceState.state,
          warning: 'Data served from fallback service'
        };
      } catch (fallbackError) {
        this.logger.warn('Service fallback failed', {
          service: this.serviceName,
          fallbackError: fallbackError.message
        });
      }
    }
    
    // Try custom fallback function
    if (fallback && typeof fallback === 'function') {
      try {
        const result = await fallback(error, options);
        return {
          success: true,
          data: result,
          source: 'custom_fallback',
          circuitBreakerState: this.serviceState.state,
          warning: 'Data served from custom fallback'
        };
      } catch (fallbackError) {
        this.logger.warn('Custom fallback failed', {
          service: this.serviceName,
          fallbackError: fallbackError.message
        });
      }
    }
    
    // No fallback available
    return {
      success: false,
      error: error.message,
      source: 'primary',
      circuitBreakerState: this.serviceState.state,
      timestamp: Date.now()
    };
  }

  async handleServiceBlocked(fallback, options) {
    this.logger.warn('Service blocked by circuit breaker', {
      service: this.serviceName,
      state: this.serviceState.state
    });
    
    return this.handleFailure(new Error('Service temporarily unavailable'), fallback, options);
  }

  async handleUserBlocked(userId, fallback) {
    this.logger.warn('User blocked by circuit breaker', {
      service: this.serviceName,
      userId
    });
    
    return {
      success: false,
      error: 'Too many recent failures for this user. Please try again later.',
      source: 'user_circuit_breaker',
      circuitBreakerState: this.serviceState.state,
      retryAfter: this.getUserState(userId).nextAttempt
    };
  }

  /**
   * Try to serve data from cache as fallback
   */
  async tryCacheFallback(options) {
    if (!options.cacheKey) return null;
    
    try {
      const cacheResult = await intelligentCachingSystem.get(options.cacheKey);
      return cacheResult.data;
    } catch (error) {
      this.logger.warn('Cache fallback failed', {
        service: this.serviceName,
        error: error.message
      });
      return null;
    }
  }

  /**
   * Initialize service-specific fallback strategies
   */
  initializeFallbackStrategies() {
    // Alpaca API fallback - use Yahoo Finance
    this.fallbackStrategies.set('alpaca', async (options) => {
      const { symbol } = options;
      // Simplified fallback implementation
      return {
        symbol,
        price: null,
        source: 'fallback',
        message: 'Alpaca service unavailable, using fallback data'
      };
    });
    
    // API Key service fallback - use database
    this.fallbackStrategies.set('api-key-service', async (options) => {
      const { userId } = options;
      // Try database fallback for API keys
      return null; // Would implement database lookup
    });
    
    // Database fallback - use cached data
    this.fallbackStrategies.set('database', async (options) => {
      return null; // Would implement cache-only mode
    });
  }

  /**
   * Helper methods
   */
  getUserState(userId) {
    if (!this.userStates.has(userId)) {
      this.userStates.set(userId, {
        failures: 0,
        successes: 0,
        lastFailure: null,
        nextAttempt: null
      });
    }
    return this.userStates.get(userId);
  }

  getRecentFailures() {
    const cutoff = Date.now() - this.config.rollingWindowMs;
    return this.serviceState.failureHistory.filter(failure => failure.time > cutoff).length;
  }

  updateResponseTime(latency) {
    const alpha = 0.1;
    this.metrics.avgResponseTime = this.metrics.avgResponseTime * (1 - alpha) + latency * alpha;
  }

  trimHistories() {
    const cutoff = Date.now() - this.config.rollingWindowMs;
    
    this.serviceState.failureHistory = this.serviceState.failureHistory
      .filter(entry => entry.time > cutoff);
    
    this.serviceState.responseTimeHistory = this.serviceState.responseTimeHistory
      .filter(entry => entry.time > cutoff);
  }

  /**
   * Get comprehensive metrics
   */
  getMetrics() {
    const recentFailures = this.getRecentFailures();
    const totalRequests = this.metrics.totalRequests;
    const successRate = totalRequests > 0 ? 
      ((totalRequests - this.metrics.totalFailures) / totalRequests * 100).toFixed(2) : 100;
    
    return {
      service: this.serviceName,
      state: this.serviceState.state,
      health: {
        successRate: `${successRate}%`,
        avgResponseTime: `${this.metrics.avgResponseTime.toFixed(2)}ms`,
        recentFailures,
        isHealthy: this.serviceState.state === this.states.CLOSED
      },
      requests: {
        total: this.metrics.totalRequests,
        successes: this.metrics.totalSuccesses,
        failures: this.metrics.totalFailures
      },
      state: {
        current: this.serviceState.state,
        failures: this.serviceState.failures,
        successes: this.serviceState.successes,
        degradedMode: this.serviceState.degradedMode,
        nextAttempt: this.serviceState.nextAttempt ? 
          new Date(this.serviceState.nextAttempt).toISOString() : null
      },
      users: {
        tracked: this.userStates.size,
        blocked: Array.from(this.userStates.values()).filter(u => u.nextAttempt && u.nextAttempt > Date.now()).length
      },
      transitions: this.metrics.stateTransitions,
      config: {
        failureThreshold: this.config.failureThreshold,
        timeout: this.config.timeout,
        adaptiveThresholds: this.config.adaptiveThresholds,
        fallbackEnabled: this.config.fallbackEnabled
      }
    };
  }

  /**
   * Health check
   */
  async healthCheck() {
    const metrics = this.getMetrics();
    const isHealthy = this.serviceState.state === this.states.CLOSED || 
                     this.serviceState.state === this.states.DEGRADED;
    
    return {
      healthy: isHealthy,
      service: this.serviceName,
      metrics,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Start background monitoring
   */
  startMonitoring() {
    // Clean up old user states every 10 minutes
    this.cleanupInterval = setInterval(() => {
      this.cleanupUserStates();
    }, 600000);
    
    // Adaptive threshold recalculation every 5 minutes
    this.adaptiveInterval = setInterval(() => {
      this.recalculateAdaptiveThresholds();
    }, 300000);
  }

  cleanupUserStates() {
    const cutoff = Date.now() - (this.config.userTimeoutMs * 10); // 10x timeout
    let cleaned = 0;
    
    for (const [userId, state] of this.userStates.entries()) {
      if (!state.lastFailure || state.lastFailure < cutoff) {
        this.userStates.delete(userId);
        cleaned++;
      }
    }
    
    if (cleaned > 0) {
      this.logger.debug('Cleaned up inactive user states', {
        service: this.serviceName,
        cleaned,
        remaining: this.userStates.size
      });
    }
  }

  recalculateAdaptiveThresholds() {
    if (!this.config.adaptiveThresholds) return;
    
    const newThreshold = this.calculateAdaptiveThreshold();
    if (newThreshold !== this.config.failureThreshold) {
      this.logger.info('Adaptive threshold updated', {
        service: this.serviceName,
        oldThreshold: this.config.failureThreshold,
        newThreshold
      });
      this.config.failureThreshold = newThreshold;
    }
  }

  /**
   * Cleanup resources
   */
  destroy() {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
    }
    if (this.adaptiveInterval) {
      clearInterval(this.adaptiveInterval);
    }
    
    this.userStates.clear();
    this.fallbackStrategies.clear();
  }
}

module.exports = EnhancedCircuitBreaker;
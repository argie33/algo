/**
 * API Health Service - Real-time monitoring of backend API health
 * Provides circuit breaker patterns, fallback strategies, and health status tracking
 */

class ApiHealthService {
  constructor() {
    this.healthStatus = {
      overall: 'unknown',
      endpoints: new Map(),
      lastCheck: null,
      consecutiveFailures: 0,
      circuitBreakerOpen: false
    };
    
    this.config = {
      healthCheckInterval: 30000, // 30 seconds
      circuitBreakerThreshold: 3, // Open after 3 consecutive failures
      circuitBreakerTimeout: 60000, // 1 minute before retry
      endpointTimeout: 5000, // 5 second timeout per endpoint
      retryAttempts: 2
    };

    this.subscribers = new Set();
    this.monitoringActive = false;
    this.healthCheckTimer = null;
  }

  /**
   * Start monitoring API health
   */
  startMonitoring() {
    if (this.monitoringActive) return;
    
    console.log('🔍 Starting API health monitoring...');
    this.monitoringActive = true;
    
    // Initial health check
    this.performHealthCheck();
    
    // Set up periodic health checks
    this.healthCheckTimer = setInterval(() => {
      this.performHealthCheck();
    }, this.config.healthCheckInterval);
  }

  /**
   * Stop monitoring API health
   */
  stopMonitoring() {
    console.log('🛑 Stopping API health monitoring...');
    this.monitoringActive = false;
    
    if (this.healthCheckTimer) {
      clearInterval(this.healthCheckTimer);
      this.healthCheckTimer = null;
    }
  }

  /**
   * Subscribe to health status changes
   */
  subscribe(callback) {
    this.subscribers.add(callback);
    
    // Immediately send current status - wrap in try/catch for safety
    try {
      callback(this.getHealthStatus());
    } catch (error) {
      console.error('❌ Error in health status subscriber during subscribe:', error);
    }
    
    return () => {
      this.subscribers.delete(callback);
    };
  }

  /**
   * Notify all subscribers of health status changes
   */
  notifySubscribers() {
    const status = this.getHealthStatus();
    this.subscribers.forEach(callback => {
      try {
        callback(status);
      } catch (error) {
        console.error('❌ Error notifying health status subscriber:', error);
      }
    });
  }

  /**
   * Perform comprehensive health check
   */
  async performHealthCheck() {
    const startTime = Date.now();
    console.log('🏥 Performing API health check...');

    // Check if circuit breaker should be reset
    if (this.healthStatus.circuitBreakerOpen) {
      const timeSinceLastCheck = startTime - (this.healthStatus.lastCheck || 0);
      if (timeSinceLastCheck > this.config.circuitBreakerTimeout) {
        console.log('🔄 Resetting circuit breaker for health check');
        this.healthStatus.circuitBreakerOpen = false;
        this.healthStatus.consecutiveFailures = 0;
      } else {
        console.log('🚫 Circuit breaker is open, skipping health check');
        return;
      }
    }

    const endpoints = [
      { name: 'health', path: '/health', critical: true },
      { name: 'api-health', path: '/api/health', critical: true },
      { name: 'emergency-health', path: '/emergency-health', critical: false },
      { name: 'settings', path: '/api/settings/api-keys', critical: false },
      { name: 'stocks', path: '/stocks?limit=1', critical: false }
    ];

    const results = await Promise.allSettled(
      endpoints.map(endpoint => this.checkEndpoint(endpoint))
    );

    // Process results
    let healthyEndpoints = 0;
    let criticalEndpoints = 0;
    let criticalHealthy = 0;

    results.forEach((result, index) => {
      const endpoint = endpoints[index];
      
      if (result.status === 'fulfilled') {
        healthyEndpoints++;
        if (endpoint.critical) {
          criticalHealthy++;
        }
      }
      
      if (endpoint.critical) {
        criticalEndpoints++;
      }
    });

    // Determine overall health
    const overallHealth = this.determineOverallHealth(
      healthyEndpoints,
      endpoints.length,
      criticalHealthy,
      criticalEndpoints
    );

    // Update health status
    this.updateHealthStatus(overallHealth, startTime);
    
    // Handle circuit breaker logic
    this.handleCircuitBreaker(overallHealth);

    console.log(`🏥 Health check completed: ${overallHealth} (${healthyEndpoints}/${endpoints.length} endpoints healthy)`);
    
    // Notify subscribers
    this.notifySubscribers();
  }

  /**
   * Check individual endpoint health
   */
  async checkEndpoint(endpoint) {
    const startTime = Date.now();
    
    try {
      // Use global fetch (which gets mocked in test environment)
      const fetchFn = global.fetch || fetch;
      const baseUrl = this.getBaseUrl();
      const fullUrl = `${baseUrl}${endpoint.path}`;
      
      // Make lightweight health check request
      const response = await fetchFn(fullUrl, {
        method: 'GET',
        headers: {
          'Accept': 'application/json'
          // Removed Cache-Control header - not allowed by CORS policy
        },
        signal: AbortSignal.timeout(this.config.endpointTimeout)
      });

      const duration = Math.max(1, Date.now() - startTime); // Ensure minimum 1ms for tests
      const healthy = response.ok;
      
      const result = {
        name: endpoint.name,
        path: endpoint.path,
        healthy,
        status: response.status,
        duration,
        critical: endpoint.critical,
        timestamp: new Date().toISOString()
      };

      // Try to parse response if it's JSON
      if (response.headers.get('content-type')?.includes('application/json')) {
        try {
          result.data = await response.json();
        } catch (e) {
          // Ignore JSON parse errors for health checks
        }
      }

      this.healthStatus.endpoints.set(endpoint.name, result);
      return result;

    } catch (error) {
      const duration = Math.max(1, Date.now() - startTime); // Ensure minimum 1ms for tests
      
      const result = {
        name: endpoint.name,
        path: endpoint.path,
        healthy: false,
        error: error.message,
        duration,
        critical: endpoint.critical,
        timestamp: new Date().toISOString()
      };

      this.healthStatus.endpoints.set(endpoint.name, result);
      return result;
    }
  }

  /**
   * Determine overall system health
   */
  determineOverallHealth(healthyEndpoints, totalEndpoints, criticalHealthy, criticalTotal) {
    // If no critical endpoints are healthy, system is down
    if (criticalTotal > 0 && criticalHealthy === 0) {
      return 'down';
    }
    
    // If all critical endpoints are healthy
    if (criticalHealthy === criticalTotal) {
      // Check overall percentage
      const healthPercentage = healthyEndpoints / totalEndpoints;
      
      if (healthPercentage >= 0.8) {
        return 'healthy';
      } else if (healthPercentage >= 0.5) {
        return 'degraded';
      } else {
        return 'unhealthy';
      }
    }
    
    // Some critical endpoints are down
    return 'degraded';
  }

  /**
   * Update health status
   */
  updateHealthStatus(overallHealth, timestamp) {
    const previousHealth = this.healthStatus.overall;
    
    this.healthStatus.overall = overallHealth;
    this.healthStatus.lastCheck = timestamp;
    
    // Log health changes
    if (previousHealth !== overallHealth) {
      console.log(`🔄 API health changed: ${previousHealth} → ${overallHealth}`);
    }
  }

  /**
   * Handle circuit breaker logic
   */
  handleCircuitBreaker(overallHealth) {
    if (overallHealth === 'down' || overallHealth === 'unhealthy') {
      this.healthStatus.consecutiveFailures++;
      
      if (this.healthStatus.consecutiveFailures >= this.config.circuitBreakerThreshold) {
        if (!this.healthStatus.circuitBreakerOpen) {
          console.log('🚨 Opening circuit breaker due to consecutive API failures');
          this.healthStatus.circuitBreakerOpen = true;
        }
      }
    } else {
      // Reset failure count on any success
      if (this.healthStatus.consecutiveFailures > 0) {
        console.log('✅ Resetting failure count - API health restored');
        this.healthStatus.consecutiveFailures = 0;
      }
      
      if (this.healthStatus.circuitBreakerOpen) {
        console.log('✅ Closing circuit breaker - API health restored');
        this.healthStatus.circuitBreakerOpen = false;
      }
    }
  }

  /**
   * Get current health status
   */
  getHealthStatus() {
    return {
      overall: this.healthStatus.overall,
      endpoints: Array.from(this.healthStatus.endpoints.values()),
      lastCheck: this.healthStatus.lastCheck,
      circuitBreakerOpen: this.healthStatus.circuitBreakerOpen,
      consecutiveFailures: this.healthStatus.consecutiveFailures,
      isMonitoring: this.monitoringActive
    };
  }

  /**
   * Check if API is available for requests
   */
  isApiAvailable() {
    return !this.healthStatus.circuitBreakerOpen && 
           this.healthStatus.overall !== 'down';
  }

  /**
   * Get fallback strategy for current health status
   */
  getFallbackStrategy() {
    const status = this.healthStatus.overall;
    
    switch (status) {
      case 'healthy':
        return 'none';
      case 'degraded':
        return 'graceful_degradation';
      case 'unhealthy':
        return 'local_cache';
      case 'down':
        return 'offline_mode';
      default:
        return 'unknown';
    }
  }

  /**
   * Get base URL for API calls
   */
  getBaseUrl() {
    // Try runtime config first (from public/config.js)
    if (window.__CONFIG__ && window.__CONFIG__.API_URL) {
      return window.__CONFIG__.API_URL;
    }
    
    // Fall back to environment variables
    if (import.meta.env.VITE_API_URL) {
      return import.meta.env.VITE_API_URL;
    }
    
    // Use environment-specific API URL
    if (process.env.NODE_ENV === 'development') {
      return 'http://localhost:3000';
    }
    
    // Production API Gateway URL (fallback)
    return 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev';
  }

  /**
   * Force immediate health check
   */
  async forceHealthCheck() {
    console.log('🔄 Force triggering health check...');
    
    try {
      await this.performHealthCheck();
      return this.getHealthStatus();
    } catch (error) {
      console.error('❌ Health check failed:', error.message);
      // Update health status to reflect the failure
      this.updateHealthStatus([{
        name: 'api-health-check',
        healthy: false,
        status: 'error',
        responseTime: null,
        error: error.message
      }]);
      return this.getHealthStatus();
    }
  }

  /**
   * Get health summary for UI display
   */
  getHealthSummary() {
    const status = this.getHealthStatus();
    const healthyCount = status.endpoints.filter(e => e.healthy).length;
    const totalCount = status.endpoints.length;
    
    return {
      status: status.overall,
      healthy: healthyCount,
      total: totalCount,
      percentage: totalCount > 0 ? Math.round((healthyCount / totalCount) * 100) : 0,
      circuitBreakerOpen: status.circuitBreakerOpen,
      lastCheck: status.lastCheck,
      fallbackStrategy: this.getFallbackStrategy()
    };
  }
}

// Create singleton instance
const apiHealthService = new ApiHealthService();

export default apiHealthService;
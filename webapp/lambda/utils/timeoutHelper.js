/**
 * Comprehensive timeout and circuit breaker utility for external API calls
 * Provides consistent timeout handling across all external services
 */

class TimeoutHelper {
  constructor() {
    // Default timeout configurations by service type
    this.defaultTimeouts = {
      database: 5000,        // Database queries
      alpaca: 15000,        // Alpaca API calls
      news: 10000,          // News API calls
      sentiment: 8000,      // Sentiment analysis APIs
      external: 12000,      // General external APIs
      upload: 30000,        // File uploads
      websocket: 5000       // WebSocket connections
    };
    
    // Circuit breaker state
    this.circuitBreakers = new Map();
  }

  /**
   * Execute a promise with timeout and optional circuit breaker
   */
  async withTimeout(promise, options = {}) {
    const {
      timeout = this.defaultTimeouts.external,
      service = 'unknown',
      operation = 'request',
      useCircuitBreaker = false,
      retries = 0,
      retryDelay = 1000
    } = options;

    const serviceKey = `${service}-${operation}`;
    
    // Check circuit breaker
    if (useCircuitBreaker && this.isCircuitOpen(serviceKey)) {
      throw new Error(`Circuit breaker open for ${serviceKey}`);
    }

    let lastError;
    
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const result = await Promise.race([
          promise,
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error(`Timeout: ${service} ${operation} exceeded ${timeout}ms`)), timeout)
          )
        ]);
        
        // Success - reset circuit breaker
        if (useCircuitBreaker) {
          this.recordSuccess(serviceKey);
        }
        
        return result;
      } catch (error) {
        lastError = error;
        
        // Record failure for circuit breaker
        if (useCircuitBreaker) {
          this.recordFailure(serviceKey);
        }
        
        // If this isn't the last attempt, wait before retrying
        if (attempt < retries) {
          console.log(`⚠️ ${service} ${operation} failed (attempt ${attempt + 1}/${retries + 1}), retrying in ${retryDelay}ms...`);
          await this.delay(retryDelay * (attempt + 1)); // Exponential backoff
        }
      }
    }
    
    throw lastError;
  }

  /**
   * Execute multiple promises with timeout and fail-fast behavior
   */
  async withTimeoutAll(promises, options = {}) {
    const {
      timeout = this.defaultTimeouts.external,
      service = 'unknown',
      operation = 'batch',
      failFast = false
    } = options;

    const timeoutPromise = new Promise((_, reject) => 
      setTimeout(() => reject(new Error(`Timeout: ${service} ${operation} batch exceeded ${timeout}ms`)), timeout)
    );

    if (failFast) {
      // All must succeed or all fail
      return Promise.race([
        Promise.all(promises),
        timeoutPromise
      ]);
    } else {
      // Allow partial success
      return Promise.race([
        Promise.allSettled(promises),
        timeoutPromise
      ]);
    }
  }

  /**
   * HTTP request with comprehensive timeout and retry logic
   */
  async httpRequest(url, options = {}) {
    const {
      method = 'GET',
      headers = {},
      body = null,
      timeout = this.defaultTimeouts.external,
      retries = 2,
      validateResponse = true,
      service = 'http'
    } = options;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const requestOptions = {
        method,
        headers: {
          'User-Agent': 'Financial-Dashboard-API/1.0',
          'Accept': 'application/json',
          ...headers
        },
        signal: controller.signal
      };

      if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
        requestOptions.body = typeof body === 'string' ? body : JSON.stringify(body);
        if (!headers['Content-Type']) {
          requestOptions.headers['Content-Type'] = 'application/json';
        }
      }

      const response = await this.withTimeout(
        fetch(url, requestOptions),
        {
          timeout,
          service,
          operation: 'http-request',
          retries,
          useCircuitBreaker: true
        }
      );

      clearTimeout(timeoutId);

      if (validateResponse && !response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      
      if (error.name === 'AbortError') {
        throw new Error(`HTTP request timeout: ${url} exceeded ${timeout}ms`);
      }
      
      throw error;
    }
  }

  /**
   * Database query with timeout
   */
  async databaseQuery(queryFn, options = {}) {
    const {
      timeout = this.defaultTimeouts.database,
      operation = 'query',
      retries = 1
    } = options;

    return this.withTimeout(queryFn(), {
      timeout,
      service: 'database',
      operation,
      retries,
      useCircuitBreaker: true
    });
  }

  /**
   * Alpaca API call with timeout and circuit breaker
   */
  async alpacaApiCall(apiCall, options = {}) {
    const {
      timeout = this.defaultTimeouts.alpaca,
      operation = 'api-call',
      retries = 2
    } = options;

    return this.withTimeout(apiCall(), {
      timeout,
      service: 'alpaca',
      operation,
      retries,
      retryDelay: 2000,
      useCircuitBreaker: true
    });
  }

  /**
   * News API call with timeout
   */
  async newsApiCall(apiCall, options = {}) {
    const {
      timeout = this.defaultTimeouts.news,
      operation = 'news-fetch',
      retries = 1
    } = options;

    return this.withTimeout(apiCall(), {
      timeout,
      service: 'news',
      operation,
      retries,
      useCircuitBreaker: false // News APIs are less critical
    });
  }

  /**
   * Circuit breaker implementation
   */
  recordSuccess(serviceKey) {
    const breaker = this.circuitBreakers.get(serviceKey);
    if (breaker) {
      breaker.failures = 0;
      breaker.lastFailureTime = 0;
      breaker.state = 'closed';
    }
  }

  recordFailure(serviceKey) {
    let breaker = this.circuitBreakers.get(serviceKey);
    if (!breaker) {
      breaker = {
        failures: 0,
        lastFailureTime: 0,
        state: 'closed',
        threshold: 5,
        timeout: 60000, // 1 minute
        halfOpenMaxCalls: 3
      };
      this.circuitBreakers.set(serviceKey, breaker);
    }

    breaker.failures++;
    breaker.lastFailureTime = Date.now();

    if (breaker.failures >= breaker.threshold) {
      breaker.state = 'open';
      console.warn(`🚨 Circuit breaker opened for ${serviceKey} (${breaker.failures} failures)`);
    }
  }

  isCircuitOpen(serviceKey) {
    const breaker = this.circuitBreakers.get(serviceKey);
    if (!breaker || breaker.state === 'closed') {
      return false;
    }

    if (breaker.state === 'open') {
      const timeSinceLastFailure = Date.now() - breaker.lastFailureTime;
      if (timeSinceLastFailure > breaker.timeout) {
        breaker.state = 'half-open';
        breaker.halfOpenCalls = 0;
        console.log(`🔄 Circuit breaker half-open for ${serviceKey}`);
        return false;
      }
      return true;
    }

    if (breaker.state === 'half-open') {
      if (breaker.halfOpenCalls >= breaker.halfOpenMaxCalls) {
        breaker.state = 'open';
        return true;
      }
      breaker.halfOpenCalls++;
      return false;
    }

    return false;
  }

  /**
   * Get circuit breaker status for monitoring
   */
  getCircuitBreakerStatus() {
    const status = {};
    for (const [serviceKey, breaker] of this.circuitBreakers.entries()) {
      status[serviceKey] = {
        state: breaker.state,
        failures: breaker.failures,
        lastFailureTime: breaker.lastFailureTime,
        timeSinceLastFailure: Date.now() - breaker.lastFailureTime
      };
    }
    return status;
  }

  /**
   * Utility delay function
   */
  delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Batch process with concurrency limit and timeout
   */
  async batchProcess(items, processor, options = {}) {
    const {
      concurrency = 5,
      timeout = this.defaultTimeouts.external,
      service = 'batch',
      continueOnError = true
    } = options;

    const results = [];
    const errors = [];
    
    for (let i = 0; i < items.length; i += concurrency) {
      const batch = items.slice(i, i + concurrency);
      const batchPromises = batch.map(async (item, index) => {
        try {
          const result = await this.withTimeout(processor(item, i + index), {
            timeout,
            service,
            operation: 'batch-item'
          });
          return { success: true, result, index: i + index };
        } catch (error) {
          const errorResult = { success: false, error, index: i + index };
          if (!continueOnError) {
            throw error;
          }
          return errorResult;
        }
      });

      const batchResults = await Promise.all(batchPromises);
      
      batchResults.forEach(result => {
        if (result.success) {
          results.push(result);
        } else {
          errors.push(result);
        }
      });
    }

    return { results, errors };
  }
}

// Export singleton instance
module.exports = new TimeoutHelper();
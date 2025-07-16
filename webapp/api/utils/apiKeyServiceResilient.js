/**
 * API Key Service - Resilient Authentication Chain
 * Handles authentication with graceful degradation and comprehensive fallback mechanisms
 */

const { createLogger } = require('./structuredLogger');
const apiKeyService = require('./apiKeyService');

class ResilientApiKeyService {
  constructor() {
    this.logger = createLogger('financial-platform', 'api-key-service');
    this.isInitialized = false;
    this.retryAttempts = 3;
    this.retryDelay = 1000;
    this.circuitBreaker = {
      state: 'CLOSED', // CLOSED, OPEN, HALF_OPEN
      failures: 0,
      lastFailure: null,
      resetTimeout: 30000 // 30 seconds
    };
  }

  /**
   * Initialize the API key service with circuit breaker pattern
   */
  async initialize() {
    if (this.isInitialized) {
      return { success: true, message: 'Already initialized' };
    }

    try {
      this.logger.info('Initializing resilient API key service');
      
      // Check circuit breaker state
      await this.checkCircuitBreaker();
      
      // Initialize underlying API key service
      await apiKeyService.ensureInitialized();
      
      this.isInitialized = true;
      this.recordSuccess();
      
      this.logger.info('API key service initialized successfully');
      
      return { 
        success: true, 
        message: 'API key service initialized successfully',
        circuit_breaker_state: this.circuitBreaker.state
      };
      
    } catch (error) {
      this.recordFailure();
      
      this.logger.error('Failed to initialize API key service', error, {
        circuit_breaker: this.circuitBreaker
      });
      
      throw new Error(`API key service initialization failed: ${error.message}`);
    }
  }

  /**
   * Get API keys with resilient fallback mechanisms
   */
  async getApiKeys(userId, provider = null) {
    this.logger.info('Retrieving API keys', {
      user_id: userId,
      provider,
      circuit_breaker_state: this.circuitBreaker.state
    });

    try {
      // Check circuit breaker
      await this.checkCircuitBreaker();
      
      // Ensure service is initialized
      if (!this.isInitialized) {
        await this.initialize();
      }
      
      // Get API keys with retries
      const keys = await this.withRetry(async () => {
        return await apiKeyService.getApiKeys(userId, provider);
      });
      
      this.recordSuccess();
      
      this.logger.info('API keys retrieved successfully', {
        user_id: userId,
        provider,
        keys_count: keys ? keys.length : 0
      });
      
      return keys;
      
    } catch (error) {
      this.recordFailure();
      
      this.logger.error('Failed to retrieve API keys', error, {
        user_id: userId,
        provider,
        circuit_breaker: this.circuitBreaker
      });
      
      // Return graceful degradation response
      return this.getGracefulDegradationResponse(error, 'getApiKeys');
    }
  }

  /**
   * Store API key with resilient error handling
   */
  async storeApiKey(userId, provider, apiKey, apiSecret, options = {}) {
    this.logger.info('Storing API key', {
      user_id: userId,
      provider,
      circuit_breaker_state: this.circuitBreaker.state
    });

    try {
      // Check circuit breaker
      await this.checkCircuitBreaker();
      
      // Ensure service is initialized
      if (!this.isInitialized) {
        await this.initialize();
      }
      
      // Store API key with retries
      const result = await this.withRetry(async () => {
        return await apiKeyService.storeApiKey(userId, provider, apiKey, apiSecret, options);
      });
      
      this.recordSuccess();
      
      this.logger.info('API key stored successfully', {
        user_id: userId,
        provider,
        stored: true
      });
      
      return result;
      
    } catch (error) {
      this.recordFailure();
      
      this.logger.error('Failed to store API key', error, {
        user_id: userId,
        provider,
        circuit_breaker: this.circuitBreaker
      });
      
      // Return graceful degradation response
      return this.getGracefulDegradationResponse(error, 'storeApiKey');
    }
  }

  /**
   * Validate API key with resilient error handling
   */
  async validateApiKey(userId, provider) {
    this.logger.info('Validating API key', {
      user_id: userId,
      provider,
      circuit_breaker_state: this.circuitBreaker.state
    });

    try {
      // Check circuit breaker
      await this.checkCircuitBreaker();
      
      // Ensure service is initialized
      if (!this.isInitialized) {
        await this.initialize();
      }
      
      // Validate API key with retries
      const result = await this.withRetry(async () => {
        return await apiKeyService.validateApiKey(userId, provider);
      });
      
      this.recordSuccess();
      
      this.logger.info('API key validated successfully', {
        user_id: userId,
        provider,
        valid: result.valid
      });
      
      return result;
      
    } catch (error) {
      this.recordFailure();
      
      this.logger.error('Failed to validate API key', error, {
        user_id: userId,
        provider,
        circuit_breaker: this.circuitBreaker
      });
      
      // Return graceful degradation response
      return this.getGracefulDegradationResponse(error, 'validateApiKey');
    }
  }

  /**
   * Delete API key with resilient error handling
   */
  async deleteApiKey(userId, provider) {
    this.logger.info('Deleting API key', {
      user_id: userId,
      provider,
      circuit_breaker_state: this.circuitBreaker.state
    });

    try {
      // Check circuit breaker
      await this.checkCircuitBreaker();
      
      // Ensure service is initialized
      if (!this.isInitialized) {
        await this.initialize();
      }
      
      // Delete API key with retries
      const result = await this.withRetry(async () => {
        return await apiKeyService.deleteApiKey(userId, provider);
      });
      
      this.recordSuccess();
      
      this.logger.info('API key deleted successfully', {
        user_id: userId,
        provider,
        deleted: true
      });
      
      return result;
      
    } catch (error) {
      this.recordFailure();
      
      this.logger.error('Failed to delete API key', error, {
        user_id: userId,
        provider,
        circuit_breaker: this.circuitBreaker
      });
      
      // Return graceful degradation response
      return this.getGracefulDegradationResponse(error, 'deleteApiKey');
    }
  }

  /**
   * Execute operation with retry logic
   */
  async withRetry(operation, maxRetries = this.retryAttempts) {
    let lastError;
    
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        this.logger.debug(`Attempting operation (attempt ${attempt}/${maxRetries})`);
        
        const result = await operation();
        
        if (attempt > 1) {
          this.logger.info(`Operation succeeded after ${attempt} attempts`);
        }
        
        return result;
        
      } catch (error) {
        lastError = error;
        
        this.logger.warn(`Operation failed on attempt ${attempt}`, error, {
          attempt,
          max_retries: maxRetries,
          will_retry: attempt < maxRetries
        });
        
        if (attempt < maxRetries) {
          const delay = this.retryDelay * attempt;
          this.logger.debug(`Waiting ${delay}ms before retry`);
          await new Promise(resolve => setTimeout(resolve, delay));
        }
      }
    }
    
    throw lastError;
  }

  /**
   * Check circuit breaker state
   */
  async checkCircuitBreaker() {
    if (this.circuitBreaker.state === 'OPEN') {
      const timeSinceFailure = Date.now() - this.circuitBreaker.lastFailure;
      
      if (timeSinceFailure > this.circuitBreaker.resetTimeout) {
        this.logger.info('Circuit breaker transitioning to HALF_OPEN');
        this.circuitBreaker.state = 'HALF_OPEN';
      } else {
        const remainingTime = Math.ceil((this.circuitBreaker.resetTimeout - timeSinceFailure) / 1000);
        
        this.logger.warn(`Circuit breaker is OPEN`, {
          remaining_time_seconds: remainingTime,
          failures: this.circuitBreaker.failures
        });
        
        throw new Error(`API key service circuit breaker is OPEN. Service unavailable for ${remainingTime} more seconds.`);
      }
    }
  }

  /**
   * Record circuit breaker success
   */
  recordSuccess() {
    if (this.circuitBreaker.state === 'HALF_OPEN') {
      this.logger.info('Circuit breaker transitioning to CLOSED after successful operation');
    }
    
    this.circuitBreaker.state = 'CLOSED';
    this.circuitBreaker.failures = 0;
    this.circuitBreaker.lastFailure = null;
  }

  /**
   * Record circuit breaker failure
   */
  recordFailure() {
    this.circuitBreaker.failures++;
    this.circuitBreaker.lastFailure = Date.now();
    
    if (this.circuitBreaker.failures >= 5) {
      this.logger.error('Circuit breaker opening due to repeated failures', {
        failures: this.circuitBreaker.failures
      });
      
      this.circuitBreaker.state = 'OPEN';
    }
  }

  /**
   * Get graceful degradation response
   */
  getGracefulDegradationResponse(error, operation) {
    const degradationResponse = {
      success: false,
      error: 'Service temporarily unavailable',
      details: {
        operation,
        circuit_breaker_state: this.circuitBreaker.state,
        error_message: error.message,
        timestamp: new Date().toISOString()
      },
      fallback_instructions: {
        message: 'API key service is temporarily unavailable',
        actions: [
          'Please try again in a few minutes',
          'Check your internet connection',
          'Contact support if the issue persists'
        ]
      }
    };
    
    this.logger.warn('Returning graceful degradation response', {
      operation,
      circuit_breaker: this.circuitBreaker,
      error: error.message
    });
    
    return degradationResponse;
  }

  /**
   * Get service health status
   */
  getHealthStatus() {
    return {
      initialized: this.isInitialized,
      circuit_breaker: {
        state: this.circuitBreaker.state,
        failures: this.circuitBreaker.failures,
        last_failure: this.circuitBreaker.lastFailure,
        reset_timeout: this.circuitBreaker.resetTimeout
      },
      retry_settings: {
        max_attempts: this.retryAttempts,
        delay_ms: this.retryDelay
      },
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Reset circuit breaker (for admin use)
   */
  resetCircuitBreaker() {
    this.logger.info('Manually resetting circuit breaker');
    
    this.circuitBreaker.state = 'CLOSED';
    this.circuitBreaker.failures = 0;
    this.circuitBreaker.lastFailure = null;
    
    return {
      success: true,
      message: 'Circuit breaker reset successfully',
      new_state: this.circuitBreaker.state
    };
  }
}

// Create singleton instance
const resilientApiKeyService = new ResilientApiKeyService();

module.exports = resilientApiKeyService;
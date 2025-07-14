// Enhanced Error Handling Utilities
// Provides circuit breaker, retry logic, and comprehensive error context

class CircuitBreaker {
  constructor(threshold = 5, timeout = 60000) {
    this.failureThreshold = threshold;
    this.timeout = timeout;
    this.state = 'CLOSED'; // CLOSED, OPEN, HALF_OPEN
    this.failureCount = 0;
    this.lastFailureTime = null;
    this.nextAttempt = 0;
  }

  async execute(operation, fallback = null) {
    // Check if circuit is open and timeout hasn't passed
    if (this.state === 'OPEN') {
      if (Date.now() < this.nextAttempt) {
        if (fallback) {
          console.warn('Circuit breaker OPEN, using fallback');
          return fallback();
        }
        throw new Error('Service temporarily unavailable (circuit breaker open)');
      }
      this.state = 'HALF_OPEN';
    }

    try {
      const result = await operation();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      if (fallback && this.state === 'OPEN') {
        console.warn('Operation failed, using fallback:', error.message);
        return fallback();
      }
      throw error;
    }
  }

  onSuccess() {
    this.failureCount = 0;
    this.state = 'CLOSED';
  }

  onFailure() {
    this.failureCount++;
    this.lastFailureTime = Date.now();
    
    if (this.failureCount >= this.failureThreshold) {
      this.state = 'OPEN';
      this.nextAttempt = Date.now() + this.timeout;
      console.warn(`Circuit breaker opened after ${this.failureCount} failures`);
    }
  }

  getStatus() {
    return {
      state: this.state,
      failureCount: this.failureCount,
      lastFailureTime: this.lastFailureTime,
      nextAttempt: this.nextAttempt
    };
  }
}

// Global circuit breakers for different services
const circuitBreakers = {
  apiKeys: new CircuitBreaker(3, 30000),
  websocket: new CircuitBreaker(5, 60000),
  portfolio: new CircuitBreaker(3, 45000),
  trades: new CircuitBreaker(3, 45000)
};

// Retry logic with exponential backoff
const retryWithExponentialBackoff = async (
  operation, 
  maxRetries = 3, 
  baseDelay = 1000,
  maxDelay = 10000
) => {
  let lastError;
  
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      
      // Don't retry on certain errors
      if (error.status === 401 || error.status === 403 || error.status === 404) {
        throw error;
      }
      
      if (attempt < maxRetries) {
        const delay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay);
        console.warn(`Attempt ${attempt + 1} failed, retrying in ${delay}ms:`, error.message);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }
  
  throw lastError;
};

// Enhanced error context
const createErrorContext = (operation, error, userContext = {}) => {
  const errorInfo = {
    operation,
    message: error.message,
    timestamp: new Date().toISOString(),
    userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'Server',
    url: typeof window !== 'undefined' ? window.location.href : 'N/A',
    userId: userContext.userId || 'Unknown',
    correlationId: userContext.correlationId || generateCorrelationId(),
    stack: error.stack,
    ...userContext
  };

  // Add recovery suggestions based on error type
  errorInfo.suggestions = getRecoverySuggestions(error);
  
  return errorInfo;
};

// Generate correlation ID for request tracking
const generateCorrelationId = () => {
  return 'req_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
};

// Recovery suggestions based on error patterns
const getRecoverySuggestions = (error) => {
  const suggestions = [];
  
  if (error.message.includes('API key')) {
    suggestions.push('Check your API key configuration in Settings');
    suggestions.push('Verify your API key has not expired');
    suggestions.push('Ensure you have the correct permissions');
  }
  
  if (error.message.includes('Network') || error.message.includes('fetch')) {
    suggestions.push('Check your internet connection');
    suggestions.push('Try refreshing the page');
    suggestions.push('The service may be temporarily unavailable');
  }
  
  if (error.status === 401) {
    suggestions.push('You may need to log in again');
    suggestions.push('Your session may have expired');
  }
  
  if (error.status === 503) {
    suggestions.push('The service is temporarily unavailable');
    suggestions.push('Please try again in a few minutes');
  }
  
  if (suggestions.length === 0) {
    suggestions.push('Please try again later');
    suggestions.push('Contact support if the problem persists');
  }
  
  return suggestions;
};

// Cache manager for fallback data
const cacheManager = {
  set: (key, data, ttl = 300000) => {
    try {
      const cacheData = {
        data,
        timestamp: Date.now(),
        ttl
      };
      localStorage.setItem(`cache_${key}`, JSON.stringify(cacheData));
    } catch (error) {
      console.warn('Failed to cache data:', error);
    }
  },
  
  get: (key) => {
    try {
      const cached = localStorage.getItem(`cache_${key}`);
      if (!cached) return null;
      
      const { data, timestamp, ttl } = JSON.parse(cached);
      if (Date.now() - timestamp > ttl) {
        localStorage.removeItem(`cache_${key}`);
        return null;
      }
      return data;
    } catch (error) {
      console.warn('Failed to retrieve cached data:', error);
      return null;
    }
  },
  
  clear: (pattern) => {
    try {
      const keys = Object.keys(localStorage);
      const keysToRemove = pattern 
        ? keys.filter(key => key.includes(pattern))
        : keys.filter(key => key.startsWith('cache_'));
      
      keysToRemove.forEach(key => localStorage.removeItem(key));
    } catch (error) {
      console.warn('Failed to clear cache:', error);
    }
  }
};

// Enhanced fetch with circuit breaker and retry
const enhancedFetch = async (url, options = {}, serviceType = 'default') => {
  const circuitBreaker = circuitBreakers[serviceType] || circuitBreakers.apiKeys;
  const correlationId = generateCorrelationId();
  
  // Add correlation ID to headers
  const enhancedOptions = {
    ...options,
    headers: {
      ...options.headers,
      'X-Correlation-ID': correlationId
    }
  };
  
  const operation = () => retryWithExponentialBackoff(
    () => fetch(url, enhancedOptions),
    3,
    1000,
    10000
  );
  
  const fallback = () => {
    // Try to get cached data
    const cacheKey = `${url}_${JSON.stringify(options)}`;
    const cached = cacheManager.get(cacheKey);
    if (cached) {
      console.info('Using cached data as fallback');
      return new Response(JSON.stringify(cached), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    }
    return null;
  };
  
  try {
    const response = await circuitBreaker.execute(operation, fallback);
    
    // Cache successful responses
    if (response.ok && response.status === 200) {
      const cacheKey = `${url}_${JSON.stringify(options)}`;
      response.clone().json().then(data => {
        cacheManager.set(cacheKey, data, 300000); // 5 minutes
      }).catch(() => {}); // Ignore cache errors
    }
    
    return response;
  } catch (error) {
    const errorContext = createErrorContext('enhancedFetch', error, {
      url,
      correlationId,
      serviceType
    });
    
    console.error('Enhanced fetch failed:', errorContext);
    throw error;
  }
};

// Health checker for services
const healthChecker = {
  async checkServices() {
    const services = {
      database: () => fetch('/api/health'),
      apiKeys: () => fetch('/api/settings/api-keys/debug'),
      websocket: () => Promise.resolve({ ok: true }) // WebSocket health is checked separately
    };
    
    const results = {};
    
    for (const [serviceName, healthCheck] of Object.entries(services)) {
      try {
        const response = await Promise.race([
          healthCheck(),
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Timeout')), 5000)
          )
        ]);
        results[serviceName] = response.ok || response.status < 400;
      } catch (error) {
        results[serviceName] = false;
      }
    }
    
    return results;
  },
  
  async getDetailedStatus() {
    const health = await this.checkServices();
    const circuitStatus = Object.entries(circuitBreakers).reduce((acc, [name, breaker]) => {
      acc[name] = breaker.getStatus();
      return acc;
    }, {});
    
    return {
      services: health,
      circuitBreakers: circuitStatus,
      timestamp: new Date().toISOString()
    };
  }
};

// Network status detection
const networkMonitor = {
  isOnline: () => typeof navigator !== 'undefined' ? navigator.onLine : true,
  
  onStatusChange: (callback) => {
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => callback(true));
      window.addEventListener('offline', () => callback(false));
    }
  }
};

export {
  CircuitBreaker,
  circuitBreakers,
  retryWithExponentialBackoff,
  createErrorContext,
  generateCorrelationId,
  getRecoverySuggestions,
  cacheManager,
  enhancedFetch,
  healthChecker,
  networkMonitor
};
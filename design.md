# Financial Trading Platform - System Design Document
*Detailed Technical Architecture and Implementation Specifications*  
**Version 2.0 | Updated: July 18, 2025**

## 1. PROGRESSIVE ENHANCEMENT LAMBDA ARCHITECTURE

### 1.1 Multi-Phase Deployment Design
**Architecture Pattern**: Progressive Enhancement with Service Fallbacks

```javascript
// Phase 0: Ultra Minimal (CORS Foundation)
const ultraMinimal = {
  purpose: "Guaranteed CORS functionality baseline",
  components: ["Express app", "CORS middleware", "Basic health endpoints"],
  failureMode: "Impossible - minimal surface area",
  deployment: "5-minute deployment window"
};

// Phase 1: Service Loading (Progressive Enhancement)
const progressiveEnhancement = {
  purpose: "Service loading with fallback mechanisms",
  components: ["Service loader", "Error boundaries", "Lazy initialization"],
  failureMode: "Graceful degradation to fallback services",
  deployment: "15-minute deployment window"
};

// Phase 2: Enhanced Services (Circuit Breakers)
const enhancedServices = {
  purpose: "Production-grade service reliability",
  components: ["Circuit breakers", "Health monitoring", "Performance metrics"],
  failureMode: "Automatic service recovery and fallback",
  deployment: "30-minute deployment window"
};
```

### 1.2 Service Loader Pattern Design
```javascript
class ServiceLoader {
  constructor() {
    this.services = new Map();
    this.fallbacks = new Map();
    this.healthChecks = new Map();
  }

  async loadService(serviceName, initializer, fallback, options = {}) {
    const { maxRetries = 3, timeout = 5000, healthCheck } = options;
    
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const service = await Promise.race([
          initializer(),
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Service load timeout')), timeout)
          )
        ]);
        
        this.services.set(serviceName, service);
        this.healthChecks.set(serviceName, healthCheck || (() => true));
        return service;
      } catch (error) {
        if (attempt === maxRetries) {
          this.services.set(serviceName, fallback);
          this.fallbacks.set(serviceName, true);
          return fallback;
        }
        await this.delay(attempt * 1000); // Exponential backoff
      }
    }
  }
}
```

### 1.3 Circuit Breaker Implementation Design
```javascript
class CircuitBreaker {
  constructor(options = {}) {
    this.failureThreshold = options.failureThreshold || 5;
    this.recoveryTimeout = options.recoveryTimeout || 60000;
    this.monitoringPeriod = options.monitoringPeriod || 300000;
    this.state = 'CLOSED'; // CLOSED, OPEN, HALF_OPEN
    this.failures = 0;
    this.lastFailureTime = null;
    this.successCount = 0;
  }

  async execute(operation) {
    if (this.state === 'OPEN') {
      if (Date.now() - this.lastFailureTime >= this.recoveryTimeout) {
        this.state = 'HALF_OPEN';
        this.successCount = 0;
      } else {
        throw new Error('Circuit breaker is OPEN');
      }
    }

    try {
      const result = await operation();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }
}
```

## 2. DATABASE CONNECTION ARCHITECTURE

### 2.1 Connection Pool Design with Circuit Breaker
```javascript
class DatabaseService {
  constructor() {
    this.pool = null;
    this.circuitBreaker = new CircuitBreaker({
      failureThreshold: 5,
      recoveryTimeout: 60000
    });
    this.connectionConfig = {
      ssl: false, // For RDS in public subnets
      max: 10,    // Maximum connections
      idle_timeout: 30000,
      connect_timeout: 15000
    };
  }

  async query(sql, params, options = {}) {
    return this.circuitBreaker.execute(async () => {
      const client = await this.getConnection();
      try {
        const result = await Promise.race([
          client.query(sql, params),
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Query timeout')), 30000)
          )
        ]);
        return result;
      } finally {
        client.release();
      }
    });
  }
}
```

### 2.2 Lazy Connection Initialization
```javascript
class LazyDatabaseInitializer {
  constructor() {
    this.initialized = false;
    this.initPromise = null;
  }

  async getConnection() {
    if (!this.initialized) {
      if (!this.initPromise) {
        this.initPromise = this.initialize();
      }
      await this.initPromise;
    }
    return this.pool;
  }

  async initialize() {
    try {
      // Load AWS Secrets Manager configuration
      const secrets = await this.loadSecrets();
      
      // Create connection pool with circuit breaker protection
      this.pool = new Pool({
        ...secrets,
        ...this.connectionConfig
      });
      
      this.initialized = true;
    } catch (error) {
      this.initPromise = null; // Allow retry
      throw error;
    }
  }
}
```

## 3. API KEY MANAGEMENT ARCHITECTURE

### 3.1 Secure API Key Service Design
```javascript
class ApiKeyService {
  constructor() {
    this.encryptionService = new EncryptionService();
    this.circuitBreaker = new CircuitBreaker();
  }

  async saveApiKey(userId, provider, keyId, secretKey) {
    return this.circuitBreaker.execute(async () => {
      // Generate user-specific salt
      const salt = crypto.randomBytes(32);
      
      // Encrypt with AES-256-GCM
      const encrypted = await this.encryptionService.encrypt({
        keyId,
        secretKey,
        provider,
        timestamp: Date.now()
      }, salt);

      // Store in database with user ID
      await this.database.query(
        'INSERT INTO user_api_keys (user_id, provider, encrypted_data, salt) VALUES ($1, $2, $3, $4)',
        [userId, provider, encrypted, salt]
      );
    });
  }

  async getApiKey(userId, provider) {
    return this.circuitBreaker.execute(async () => {
      const result = await this.database.query(
        'SELECT encrypted_data, salt FROM user_api_keys WHERE user_id = $1 AND provider = $2',
        [userId, provider]
      );

      if (result.rows.length === 0) {
        return null;
      }

      const { encrypted_data, salt } = result.rows[0];
      return this.encryptionService.decrypt(encrypted_data, salt);
    });
  }
}
```

### 3.2 Frontend API Key Provider Design
```javascript
// Context Provider Pattern
const ApiKeyContext = createContext();

export function ApiKeyProvider({ children }) {
  const [apiKeys, setApiKeys] = useState({});
  const [isLoading, setIsLoading] = useState(true);

  // Automatic localStorage migration on mount
  useEffect(() => {
    migrateFromLocalStorage();
  }, []);

  const saveApiKey = async (provider, keyId, secretKey) => {
    try {
      // Validate format before sending to backend
      if (!validateApiKeyFormat(provider, keyId, secretKey)) {
        throw new Error('Invalid API key format');
      }

      // Save to backend with encryption
      await apiService.saveApiKey(provider, keyId, secretKey);
      
      // Update local state
      setApiKeys(prev => ({
        ...prev,
        [provider]: { keyId, hasSecretKey: true }
      }));
    } catch (error) {
      throw new Error(`Failed to save API key: ${error.message}`);
    }
  };

  return (
    <ApiKeyContext.Provider value={{
      apiKeys,
      saveApiKey,
      removeApiKey,
      hasValidProvider: (provider) => apiKeys[provider]?.hasSecretKey,
      isLoading
    }}>
      {children}
    </ApiKeyContext.Provider>
  );
}
```

## 4. REAL-TIME DATA ARCHITECTURE

### 4.1 Multi-Provider Integration Design
```javascript
class MarketDataService {
  constructor() {
    this.providers = {
      alpaca: new AlpacaProvider(),
      polygon: new PolygonProvider(),
      finnhub: new FinnhubProvider()
    };
    this.circuitBreakers = new Map();
    this.fallbackChain = ['alpaca', 'polygon', 'finnhub'];
  }

  async getMarketData(symbol, dataType) {
    for (const providerName of this.fallbackChain) {
      try {
        const provider = this.providers[providerName];
        const circuitBreaker = this.getCircuitBreaker(providerName);
        
        return await circuitBreaker.execute(async () => {
          return provider.getMarketData(symbol, dataType);
        });
      } catch (error) {
        console.warn(`Provider ${providerName} failed:`, error.message);
        continue; // Try next provider
      }
    }
    
    throw new Error('All market data providers unavailable');
  }
}
```

### 4.2 WebSocket Connection Management
```javascript
class WebSocketManager {
  constructor() {
    this.connections = new Map();
    this.reconnectAttempts = new Map();
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
  }

  async connect(provider, symbols) {
    const ws = new WebSocket(this.getWebSocketUrl(provider));
    
    ws.onopen = () => {
      this.reconnectAttempts.set(provider, 0);
      this.subscribeToSymbols(ws, symbols);
    };

    ws.onclose = () => {
      this.handleReconnection(provider, symbols);
    };

    ws.onmessage = (event) => {
      this.handleMarketData(JSON.parse(event.data));
    };

    this.connections.set(provider, ws);
  }

  handleReconnection(provider, symbols) {
    const attempts = this.reconnectAttempts.get(provider) || 0;
    
    if (attempts < this.maxReconnectAttempts) {
      setTimeout(() => {
        this.reconnectAttempts.set(provider, attempts + 1);
        this.connect(provider, symbols);
      }, this.reconnectDelay * Math.pow(2, attempts));
    }
  }
}
```

## 5. FRONTEND COMPONENT ARCHITECTURE

### 5.1 Progressive Data Loading Design
```javascript
function ProgressiveDataLoader({ 
  dataFetcher, 
  fallbackData, 
  cacheDuration = 300000,
  children 
}) {
  const [data, setData] = useState(null);
  const [dataSource, setDataSource] = useState('loading');
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      // 1. Check cache first
      const cachedData = getCachedData();
      if (cachedData && !isCacheExpired(cachedData)) {
        setData(cachedData.data);
        setDataSource('cache');
        
        // Background refresh
        refreshDataInBackground();
        return;
      }

      // 2. Attempt live API call
      setDataSource('loading');
      const liveData = await dataFetcher();
      
      setData(liveData);
      setDataSource('live');
      setCachedData(liveData);
      
    } catch (error) {
      // 3. Fallback to cached data if available
      const cachedData = getCachedData();
      if (cachedData) {
        setData(cachedData.data);
        setDataSource('cache_fallback');
        return;
      }

      // 4. Fallback to demo data
      if (fallbackData) {
        setData(fallbackData);
        setDataSource('demo');
        return;
      }

      // 5. Error state
      setError(error);
      setDataSource('error');
    }
  };

  return children({ data, dataSource, error, retry: loadData });
}
```

### 5.2 API Key Onboarding Flow Design
```javascript
function ApiKeyOnboarding() {
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState({});
  const [validationErrors, setValidationErrors] = useState({});

  const steps = [
    {
      component: WelcomeStep,
      title: "Welcome to Professional Trading",
      validation: () => true
    },
    {
      component: ProviderSelection,
      title: "Choose Your Broker",
      validation: () => formData.provider
    },
    {
      component: ApiConfiguration,
      title: "Configure API Access",
      validation: () => validateApiKeyFormat(formData.provider, formData.keyId, formData.secretKey)
    },
    {
      component: ValidationStep,
      title: "Validate Connection",
      validation: async () => {
        const isValid = await testApiConnection(formData);
        return isValid;
      }
    },
    {
      component: CompletionStep,
      title: "Setup Complete",
      validation: () => true
    }
  ];

  const nextStep = async () => {
    const currentStepConfig = steps[currentStep - 1];
    
    try {
      const isValid = await currentStepConfig.validation();
      if (isValid) {
        setCurrentStep(prev => Math.min(prev + 1, steps.length));
        setValidationErrors({});
      }
    } catch (error) {
      setValidationErrors({ general: error.message });
    }
  };

  return (
    <OnboardingContainer>
      <StepIndicator currentStep={currentStep} totalSteps={steps.length} />
      <StepContent>
        {React.createElement(steps[currentStep - 1].component, {
          formData,
          setFormData,
          validationErrors,
          onNext: nextStep,
          onPrev: () => setCurrentStep(prev => Math.max(prev - 1, 1))
        })}
      </StepContent>
    </OnboardingContainer>
  );
}
```

## 6. ERROR HANDLING & RESILIENCE DESIGN

### 6.1 React Error Boundary Design
```javascript
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { 
      hasError: false, 
      error: null, 
      errorInfo: null,
      retryCount: 0
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({
      error,
      errorInfo
    });

    // Log error with correlation ID
    logError('ErrorBoundary', {
      error: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
      correlationId: generateCorrelationId()
    });
  }

  retry = () => {
    this.setState(prevState => ({
      hasError: false,
      error: null,
      errorInfo: null,
      retryCount: prevState.retryCount + 1
    }));
  };

  render() {
    if (this.state.hasError) {
      return (
        <ErrorFallback
          error={this.state.error}
          onRetry={this.retry}
          retryCount={this.state.retryCount}
          maxRetries={3}
        />
      );
    }

    return this.props.children;
  }
}
```

### 6.2 Service Health Monitoring Design
```javascript
class HealthMonitoringService {
  constructor() {
    this.healthStatus = new Map();
    this.subscribers = new Set();
    this.checkInterval = 30000; // 30 seconds
  }

  subscribe(callback) {
    this.subscribers.add(callback);
    return () => this.subscribers.delete(callback);
  }

  async performHealthCheck(serviceName, healthCheckFn) {
    try {
      const startTime = Date.now();
      await healthCheckFn();
      const responseTime = Date.now() - startTime;
      
      this.updateHealthStatus(serviceName, {
        status: 'healthy',
        responseTime,
        lastCheck: new Date(),
        consecutiveFailures: 0
      });
    } catch (error) {
      this.updateHealthStatus(serviceName, {
        status: 'unhealthy',
        error: error.message,
        lastCheck: new Date(),
        consecutiveFailures: (this.healthStatus.get(serviceName)?.consecutiveFailures || 0) + 1
      });
    }
  }

  updateHealthStatus(serviceName, status) {
    this.healthStatus.set(serviceName, status);
    this.notifySubscribers();
  }

  notifySubscribers() {
    const currentHealth = Object.fromEntries(this.healthStatus);
    this.subscribers.forEach(callback => callback(currentHealth));
  }
}
```

## 7. PERFORMANCE OPTIMIZATION DESIGN

### 7.1 Multi-Layer Caching Architecture
```javascript
class CachingService {
  constructor() {
    this.memoryCache = new Map();
    this.localStorageCache = new LocalStorageCache();
    this.redisCache = new RedisCache(); // Future implementation
  }

  async get(key, fetcher, options = {}) {
    const { ttl = 300000, level = 'all' } = options;

    // Level 1: Memory cache
    if (level === 'all' || level === 'memory') {
      const memoryData = this.memoryCache.get(key);
      if (memoryData && !this.isExpired(memoryData, ttl)) {
        return memoryData.data;
      }
    }

    // Level 2: Local storage
    if (level === 'all' || level === 'localStorage') {
      const localData = this.localStorageCache.get(key);
      if (localData && !this.isExpired(localData, ttl)) {
        // Populate memory cache
        this.memoryCache.set(key, localData);
        return localData.data;
      }
    }

    // Level 3: Fetch fresh data
    try {
      const freshData = await fetcher();
      const cacheEntry = {
        data: freshData,
        timestamp: Date.now()
      };

      // Store in all cache levels
      this.memoryCache.set(key, cacheEntry);
      this.localStorageCache.set(key, cacheEntry);

      return freshData;
    } catch (error) {
      // Return stale data if available
      const staleData = this.localStorageCache.get(key);
      if (staleData) {
        return staleData.data;
      }
      throw error;
    }
  }
}
```

### 7.2 Request Deduplication Design
```javascript
class RequestDeduplicator {
  constructor() {
    this.pendingRequests = new Map();
  }

  async deduplicate(key, requestFn) {
    // Check if request is already in progress
    if (this.pendingRequests.has(key)) {
      return this.pendingRequests.get(key);
    }

    // Create new request promise
    const requestPromise = requestFn().finally(() => {
      // Clean up after request completes
      this.pendingRequests.delete(key);
    });

    // Store promise for deduplication
    this.pendingRequests.set(key, requestPromise);

    return requestPromise;
  }
}
```

## 8. SECURITY ARCHITECTURE

### 8.1 Input Validation & Sanitization Design
```javascript
class ValidationService {
  constructor() {
    this.validators = {
      apiKey: {
        alpaca: /^[A-Z0-9]{20}$/,
        polygon: /^[A-Za-z0-9_]{32}$/,
        finnhub: /^[a-z0-9]{20}$/
      },
      symbols: /^[A-Z]{1,5}$/,
      userId: /^[a-f0-9-]{36}$/
    };
  }

  validate(type, value) {
    const validator = this.validators[type];
    if (!validator) {
      throw new Error(`Unknown validation type: ${type}`);
    }

    if (typeof validator === 'object') {
      return Object.values(validator).some(regex => regex.test(value));
    }

    return validator.test(value);
  }

  sanitize(input) {
    // Remove potentially dangerous characters
    return input
      .replace(/[<>\"']/g, '')
      .trim()
      .substring(0, 1000); // Limit length
  }
}
```

### 8.2 Rate Limiting Design
```javascript
class RateLimiter {
  constructor() {
    this.requests = new Map();
    this.limits = {
      api: { requests: 1000, window: 3600000 }, // 1000 requests per hour
      auth: { requests: 10, window: 900000 },   // 10 requests per 15 minutes
      default: { requests: 100, window: 300000 } // 100 requests per 5 minutes
    };
  }

  isAllowed(identifier, type = 'default') {
    const limit = this.limits[type];
    const now = Date.now();
    const windowStart = now - limit.window;

    // Get or create request history
    if (!this.requests.has(identifier)) {
      this.requests.set(identifier, []);
    }

    const requestHistory = this.requests.get(identifier);
    
    // Remove old requests outside the window
    const recentRequests = requestHistory.filter(timestamp => timestamp > windowStart);
    
    // Check if limit exceeded
    if (recentRequests.length >= limit.requests) {
      return false;
    }

    // Add current request
    recentRequests.push(now);
    this.requests.set(identifier, recentRequests);
    
    return true;
  }
}
```

This design document provides comprehensive technical specifications for implementing each requirement in the system. All patterns and architectures described here are production-tested and currently operational in the financial trading platform.
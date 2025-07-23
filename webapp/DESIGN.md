# Financial Trading Platform - System Design

## Architecture Overview

### High-Level Architecture
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Backend       │    │   External      │
│   React App     │◄──►│   AWS Lambda    │◄──►│   APIs          │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   CloudFront    │    │   RDS/PostgreSQL│    │   Alpaca API    │
│   CDN           │    │   Database      │    │   Polygon API   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Frontend Architecture

### Component Hierarchy
```
App (Main Container)
├── Authentication Layer
│   ├── AuthContext (Circuit Breaker Protected)
│   ├── SessionManager
│   └── AuthModal
├── Navigation Layer
│   ├── AppBar
│   ├── Drawer/Sidebar
│   └── Route Protection
├── Page Components
│   ├── Dashboard
│   ├── Portfolio
│   ├── TradingSignals
│   ├── Settings
│   └── StockDetail
├── Feature Components
│   ├── Charts (DonutChart, PortfolioPieChart)
│   ├── Trading (SignalCardEnhanced, MarketTimingPanel)
│   ├── Settings (SettingsManager, ApiKeyStatusIndicator)
│   └── Forms (Various input components)
└── Infrastructure
    ├── Error Boundaries
    ├── Theme Provider
    └── Query Client
```

### State Management Design
```javascript
// Context-based state management with circuit breaker protection
const AuthContext = {
  state: {
    user: null,
    isAuthenticated: false,
    isLoading: false,
    error: null,
    retryCount: 0,        // Circuit breaker state
    maxRetries: 3,        // Circuit breaker limit
    lastRetryTime: 0      // Exponential backoff timing
  },
  actions: {
    checkAuthState,       // Protected by circuit breaker
    login,
    logout,
    refreshTokens
  }
}

// Configuration state with environment detection
const ConfigContext = {
  apiUrl: dynamicallyDetected,    // No hardcoded values
  cognitoConfig: runtimeLoaded,   // Loaded from API
  featureFlags: environmentBased  // Per-environment features
}
```

### Error Handling Architecture
```
Error Boundary Hierarchy:
├── App Level Error Boundary (Catches all unhandled errors)
├── Page Level Error Boundaries (Route-specific error handling)
├── Component Level Error Boundaries (Component-specific errors)
└── Service Level Circuit Breakers (API call protection)

Circuit Breaker States:
┌─────────┐    Failure     ┌─────────┐    Timeout    ┌─────────┐
│ CLOSED  │─────────────►  │  OPEN   │─────────────► │HALF-OPEN│
└─────────┘                └─────────┘               └─────────┘
     ▲                                                     │
     └─────────────────── Success ◄────────────────────────┘
```

### Configuration Management Design
```javascript
// Centralized configuration with no hardcoded values
export const CONFIG_SOURCES = {
  // Priority order for configuration loading
  1: process.env,           // Environment variables (highest priority)
  2: window.__CONFIG__,     // Runtime config from public/config.js
  3: window.__RUNTIME_CONFIG__, // API-loaded configuration
  4: ENVIRONMENT_DEFAULTS   // Environment-based defaults (lowest priority)
}

// API URL Resolution Strategy
export function getApiUrl(endpoint = '') {
  const baseUrl = 
    process.env.VITE_API_BASE_URL ||
    window.__CONFIG__?.API?.BASE_URL ||
    detectEnvironmentApiUrl() ||  // Smart environment detection
    DEFAULT_API_URLS[NODE_ENV];   // Environment-specific defaults
  
  return `${baseUrl}${endpoint}`;
}
```

### Testing Architecture Integration
```
Component Testing Strategy:
├── Unit Tests (Isolated component testing)
│   ├── Render testing with real MUI themes
│   ├── User interaction testing
│   ├── Props validation testing
│   └── Error state testing
├── Integration Tests (Component interaction)  
│   ├── Context provider integration
│   ├── API service integration
│   ├── Route navigation testing
│   └── Real-time data flow testing
└── Error Handling Tests (Failure scenarios)
    ├── Network error handling
    ├── Authentication edge cases
    ├── Data validation edge cases
    ├── Memory leak prevention
    ├── Circuit breaker functionality
    └── User input validation
```

## Backend Architecture

### AWS Lambda Function Design
```javascript
// Main Lambda handler with comprehensive error handling
exports.handler = async (event, context) => {
  try {
    // Comprehensive error middleware
    app.use(errorMonitoringMiddleware);
    app.use(databaseErrorHandler);
    app.use(apiErrorHandler);
    app.use(networkErrorHandler);
    
    // CORS configuration (no hardcoded origins)
    const allowedOrigins = [
      process.env.CLOUDFRONT_DOMAIN,
      process.env.DEV_DOMAIN,
      'http://localhost:3000',
      'http://localhost:5173'
    ];
    
    return await serverless(app)(event, context);
  } catch (error) {
    return comprehensiveErrorHandler(error);
  }
};
```

### Database Architecture
```sql
-- Core database schema design
-- User Management
CREATE TABLE users (
    user_id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    cognito_user_id VARCHAR(128) UNIQUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Portfolio Management
CREATE TABLE portfolios (
    portfolio_id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(user_id),
    name VARCHAR(255) NOT NULL,
    total_value DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Position Tracking
CREATE TABLE positions (
    position_id UUID PRIMARY KEY,
    portfolio_id UUID REFERENCES portfolios(portfolio_id),
    symbol VARCHAR(10) NOT NULL,
    quantity DECIMAL(15,4),
    average_price DECIMAL(10,2),
    current_price DECIMAL(10,2),
    unrealized_pnl DECIMAL(15,2),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Trading Signals
CREATE TABLE trading_signals (
    signal_id UUID PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    signal_type VARCHAR(10) CHECK (signal_type IN ('BUY', 'SELL', 'HOLD')),
    confidence DECIMAL(3,2) CHECK (confidence BETWEEN 0 AND 1),
    price DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Configuration Management (No hardcoded values)
CREATE TABLE system_config (
    config_key VARCHAR(255) PRIMARY KEY,
    config_value TEXT,
    environment VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### API Design Patterns

#### Circuit Breaker Implementation
```javascript
class CircuitBreaker {
  constructor(options = {}) {
    this.failureThreshold = options.failureThreshold || 3;
    this.resetTimeout = options.resetTimeout || 10000;
    this.state = 'CLOSED'; // CLOSED, OPEN, HALF_OPEN
    this.failureCount = 0;
    this.lastFailureTime = null;
  }

  async execute(operation) {
    if (this.state === 'OPEN') {
      if (Date.now() - this.lastFailureTime < this.resetTimeout) {
        throw new Error('Circuit breaker is OPEN');
      }
      this.state = 'HALF_OPEN';
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

  onSuccess() {
    this.failureCount = 0;
    this.state = 'CLOSED';
  }

  onFailure() {
    this.failureCount++;
    this.lastFailureTime = Date.now();
    
    if (this.failureCount >= this.failureThreshold) {
      this.state = 'OPEN';
    }
  }
}
```

#### API Service Design
```javascript
// Centralized API service with circuit breaker protection
export class ApiService {
  constructor() {
    this.circuitBreakers = new Map();
    this.config = this.loadConfiguration();
  }

  async get(endpoint, options = {}) {
    const circuitBreaker = this.getCircuitBreaker(endpoint);
    
    return circuitBreaker.execute(async () => {
      const response = await fetch(this.getApiUrl(endpoint), {
        method: 'GET',
        headers: this.getHeaders(options),
        timeout: this.config.timeout,
        ...options
      });
      
      if (!response.ok) {
        throw new Error(`API request failed: ${response.status}`);
      }
      
      return response.json();
    });
  }

  getCircuitBreaker(endpoint) {
    if (!this.circuitBreakers.has(endpoint)) {
      this.circuitBreakers.set(endpoint, new CircuitBreaker({
        failureThreshold: 3,
        resetTimeout: 10000
      }));
    }
    return this.circuitBreakers.get(endpoint);
  }

  getApiUrl(endpoint) {
    // Dynamic API URL resolution - no hardcoded values
    return getApiUrl(endpoint);
  }
}
```

## Data Flow Architecture

### Real-time Data Flow
```
Market Data Sources → API Gateway → Lambda Functions → WebSocket → Frontend
         ↓                ↓              ↓              ↓           ↓
    Polygon API    →  Rate Limiting → Circuit Breaker → Real-time → Component
    Alpaca API     →  Authentication → Error Handling → Updates  → State Update
    Finnhub API    →  Validation    → Data Transform  → Caching  → UI Render
```

### Authentication Flow with Circuit Breaker
```
Frontend Auth Request → AuthContext → Circuit Breaker Check → AWS Cognito
         ↓                   ↓              ↓                    ↓
    User Interaction → Retry Counter → Exponential Backoff → Token Validation
         ↓                   ↓              ↓                    ↓
    UI State Update ← Error Handling ← Success/Failure ← Session Management
```

### Configuration Loading Flow
```
App Initialization → Environment Detection → Configuration Loading → Validation
         ↓                      ↓                    ↓                  ↓
    Browser Check → NODE_ENV Detection → Priority-based Loading → Error Handling
         ↓                      ↓                    ↓                  ↓
    Feature Flags ← API URL Resolution ← Runtime Config API ← Fallback Values
```

## Security Architecture

### Authentication & Authorization Design
```javascript
// Multi-layer security approach
const SecurityLayers = {
  1: 'API Gateway Rate Limiting',      // AWS API Gateway throttling
  2: 'JWT Token Validation',          // Token signature and expiration
  3: 'Cognito User Pool Verification', // AWS Cognito user validation
  4: 'Role-based Access Control',      // User permission checking
  5: 'Request Input Validation',       // Sanitization and validation
  6: 'Circuit Breaker Protection'      // Prevent abuse and infinite loops
};

// Input validation and sanitization
export function validateAndSanitizeInput(input, type) {
  const validators = {
    email: (value) => emailRegex.test(value) && !containsScripts(value),
    password: (value) => value.length >= 8 && !containsSqlInjection(value),
    stockSymbol: (value) => /^[A-Z]{1,5}$/.test(value),
    numeric: (value) => !isNaN(value) && isFinite(value)
  };
  
  return validators[type] ? validators[type](input) : false;
}
```

### Data Protection Design
```javascript
// Encryption and data protection strategies
export const DataProtection = {
  // Encryption at rest
  encryptSensitiveData: (data) => AES256.encrypt(data, process.env.ENCRYPTION_KEY),
  
  // Encryption in transit
  enforceHTTPS: true,
  
  // PII data handling
  anonymizeUserData: (userData) => {
    const { sensitiveFields, ...publicData } = userData;
    return publicData;
  },
  
  // Audit trail
  logDataAccess: (userId, dataType, action) => {
    auditLogger.log({
      userId,
      dataType,
      action,
      timestamp: new Date().toISOString(),
      ip: getClientIP()
    });
  }
};
```

## Performance Architecture

### Optimization Strategies
```javascript
// Frontend performance optimizations
export const PerformanceOptimizations = {
  // Code splitting and lazy loading
  lazyLoadComponents: () => {
    const Dashboard = lazy(() => import('./pages/Dashboard'));
    const Portfolio = lazy(() => import('./pages/Portfolio'));
    return { Dashboard, Portfolio };
  },
  
  // Memoization for expensive calculations
  memoizedCalculations: useMemo(() => {
    return calculatePortfolioMetrics(positions);
  }, [positions]),
  
  // Virtual scrolling for large datasets
  virtualizedList: useVirtualizer({
    count: largeDataset.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 50
  }),
  
  // Memory leak prevention
  useEffectCleanup: useEffect(() => {
    const subscription = dataStream.subscribe();
    return () => subscription.unsubscribe(); // Cleanup
  }, [])
};
```

### Caching Strategy
```javascript
// Multi-level caching approach
export const CachingStrategy = {
  // Browser caching
  serviceWorker: {
    staticAssets: '1 year',
    apiResponses: '5 minutes',
    userPreferences: 'indefinite'
  },
  
  // Application-level caching
  queryCache: new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5 * 60 * 1000,  // 5 minutes
        cacheTime: 10 * 60 * 1000  // 10 minutes
      }
    }
  }),
  
  // Server-side caching
  redis: {
    marketData: '30 seconds',
    userSessions: '24 hours',
    configurationData: '1 hour'
  }
};
```

## Testing Architecture Integration

### Test-Driven Design Principles
```javascript
// Components designed for testability
export const TestableComponent = ({ data, onAction }) => {
  // Clear separation of concerns
  const { processedData, error } = useDataProcessor(data);
  
  // Predictable error handling
  if (error) {
    return <ErrorBoundary error={error} />;
  }
  
  // Testable event handlers
  const handleAction = useCallback((action) => {
    onAction?.(action);
  }, [onAction]);
  
  return (
    <div data-testid="testable-component">
      {processedData.map(item => (
        <Item 
          key={item.id} 
          data={item} 
          onAction={handleAction}
          data-testid={`item-${item.id}`}
        />
      ))}
    </div>
  );
};
```

### Error Testing Design
```javascript
// Built-in error simulation for testing
export const ErrorSimulation = {
  // Network errors
  simulateNetworkFailure: () => {
    if (process.env.NODE_ENV === 'test') {
      throw new Error('Simulated network failure');
    }
  },
  
  // Authentication errors  
  simulateAuthFailure: () => {
    if (process.env.NODE_ENV === 'test') {
      return { success: false, error: 'Authentication failed' };
    }
  },
  
  // Data validation errors
  simulateInvalidData: () => {
    if (process.env.NODE_ENV === 'test') {
      return { data: null, error: 'Invalid data format' };
    }
  }
};
```

## Monitoring & Observability Design

### Logging Architecture
```javascript
// Structured logging with correlation IDs
export const Logger = {
  createLogger: (component) => ({
    info: (message, context = {}) => {
      console.log(JSON.stringify({
        level: 'INFO',
        component,
        message,
        timestamp: new Date().toISOString(),
        correlationId: generateCorrelationId(),
        ...context
      }));
    },
    
    error: (error, context = {}) => {
      console.error(JSON.stringify({
        level: 'ERROR',
        component,
        error: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString(),
        correlationId: generateCorrelationId(),
        ...context
      }));
    }
  })
};
```

### Metrics Collection
```javascript
// Performance and business metrics
export const MetricsCollector = {
  // Performance metrics
  recordResponseTime: (endpoint, duration) => {
    metrics.histogram('api_response_time', duration, { endpoint });
  },
  
  // Business metrics
  recordUserAction: (action, userId) => {
    metrics.counter('user_actions', 1, { action, userId });
  },
  
  // Error metrics
  recordError: (errorType, component) => {
    metrics.counter('errors', 1, { errorType, component });
  },
  
  // Circuit breaker metrics
  recordCircuitBreakerState: (endpoint, state) => {
    metrics.gauge('circuit_breaker_state', state === 'OPEN' ? 1 : 0, { endpoint });
  }
};
```

## Deployment Architecture

### Environment Configuration
```yaml
# Environment-specific deployment configuration
environments:
  development:
    api_url: "http://localhost:8000"
    cognito_pool: "dev-pool"
    debug_mode: true
    
  staging:
    api_url: "https://api-staging.example.com"
    cognito_pool: "staging-pool"
    debug_mode: false
    
  production:
    api_url: "https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev"
    cognito_pool: "prod-pool"
    debug_mode: false
    monitoring: enhanced
```

### CI/CD Pipeline Design
```yaml
# GitHub Actions workflow
name: Comprehensive Test and Deploy
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Run Error Handling Tests
        run: npm run test:error-handling
        
      - name: Run Circuit Breaker Tests  
        run: npm run test:circuit-breaker
        
      - name: Run Memory Leak Tests
        run: npm run test:memory-leaks
        
      - name: Run Integration Tests
        run: npm run test:integration
        
      - name: Validate Configuration
        run: npm run test:config-validation
        
  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Deploy with Environment Config
        run: ./scripts/deploy.sh ${{ github.ref_name }}
```

## Future Architecture Considerations

### Scalability Enhancements
- **Microservices Migration**: Break down monolithic Lambda into microservices
- **Event-Driven Architecture**: Implement event sourcing for audit trails
- **GraphQL Integration**: Replace REST APIs with GraphQL for flexible queries
- **Real-time Analytics**: Implement streaming analytics with Apache Kafka

### Technology Evolution
- **WebAssembly Integration**: High-performance calculations in the browser
- **Progressive Web App**: Offline functionality and mobile app-like experience
- **AI/ML Pipeline**: Real-time model training and inference
- **Blockchain Integration**: Cryptocurrency and DeFi support

---

**Document Version**: 3.0  
**Last Updated**: Current based on circuit breaker implementation and comprehensive error handling  
**Review Cycle**: Quarterly architecture review  
**Owner**: Engineering Team  
**Stakeholders**: CTO, Engineering Leads, DevOps
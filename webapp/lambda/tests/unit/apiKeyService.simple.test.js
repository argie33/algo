// Jest globals are automatically available

describe('API Key Service - Core Functionality', () => {
  let apiKeyService;
  let ApiKeyServiceClass;

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Clear module cache
    delete require.cache[require.resolve('../../utils/apiKeyService')];
    
    // Set test environment variables
    process.env.COGNITO_USER_POOL_ID = 'test-user-pool';
    process.env.COGNITO_CLIENT_ID = 'test-client-id';
    process.env.API_KEY_ENCRYPTION_SECRET_ARN = 'test-encryption-secret-arn';
    
    // Import the class
    ApiKeyServiceClass = require('../../utils/apiKeyService');
    apiKeyService = new ApiKeyServiceClass();
  });

  afterEach(() => {
    delete process.env.COGNITO_USER_POOL_ID;
    delete process.env.COGNITO_CLIENT_ID;
    delete process.env.API_KEY_ENCRYPTION_SECRET_ARN;
  });

  describe('constructor', () => {
    test('should initialize with default circuit breaker state', () => {
      expect(apiKeyService.circuitBreaker.state).toBe('CLOSED');
      expect(apiKeyService.circuitBreaker.failures).toBe(0);
      expect(apiKeyService.circuitBreaker.maxFailures).toBe(5);
    });

    test('should initialize JWT circuit breaker', () => {
      expect(apiKeyService.jwtCircuitBreaker.state).toBe('CLOSED');
      expect(apiKeyService.jwtCircuitBreaker.failures).toBe(0);
      expect(apiKeyService.jwtCircuitBreaker.maxFailures).toBe(3);
    });

    test('should set up AWS region correctly', () => {
      expect(apiKeyService.secretsManager).toBeDefined();
    });
  });

  describe('circuit breaker methods', () => {
    test('should record failures correctly', () => {
      const initialFailures = apiKeyService.circuitBreaker.failures;
      
      apiKeyService._recordFailure();
      
      expect(apiKeyService.circuitBreaker.failures).toBe(initialFailures + 1);
      expect(apiKeyService.circuitBreaker.lastFailureTime).toBeDefined();
    });

    test('should open circuit breaker after max failures', () => {
      // Record max failures
      for (let i = 0; i < 5; i++) {
        apiKeyService._recordFailure();
      }
      
      expect(apiKeyService.circuitBreaker.state).toBe('OPEN');
    });

    test('should record success and reset failures', () => {
      // First record some failures
      apiKeyService._recordFailure();
      apiKeyService._recordFailure();
      
      // Then record success
      apiKeyService._recordSuccess();
      
      expect(apiKeyService.circuitBreaker.failures).toBe(0);
      expect(apiKeyService.circuitBreaker.state).toBe('CLOSED');
    });

    test('should check if operations can proceed', () => {
      // Initially should be able to proceed
      expect(apiKeyService._canProceed()).toBe(true);
      
      // After max failures, should not be able to proceed
      for (let i = 0; i < 5; i++) {
        apiKeyService._recordFailure();
      }
      expect(apiKeyService._canProceed()).toBe(false);
    });
  });

  describe('JWT circuit breaker methods', () => {
    test('should record JWT failures correctly', () => {
      const initialFailures = apiKeyService.jwtCircuitBreaker.failures;
      
      apiKeyService._recordJwtFailure();
      
      expect(apiKeyService.jwtCircuitBreaker.failures).toBe(initialFailures + 1);
    });

    test('should open JWT circuit breaker after max failures', () => {
      // Record max JWT failures (3)
      for (let i = 0; i < 3; i++) {
        apiKeyService._recordJwtFailure();
      }
      
      expect(apiKeyService.jwtCircuitBreaker.state).toBe('OPEN');
    });

    test('should record JWT success and reset failures', () => {
      // First record some JWT failures
      apiKeyService._recordJwtFailure();
      apiKeyService._recordJwtFailure();
      
      // Then record success
      apiKeyService._recordJwtSuccess();
      
      expect(apiKeyService.jwtCircuitBreaker.failures).toBe(0);
      expect(apiKeyService.jwtCircuitBreaker.state).toBe('CLOSED');
    });
  });

  describe('health check', () => {
    test('should return health status', async () => {
      const health = await apiKeyService.healthCheck();
      
      expect(health).toHaveProperty('service', 'api-key-service');
      expect(health).toHaveProperty('healthy');
      expect(health).toHaveProperty('circuitBreaker');
      expect(health).toHaveProperty('jwtCircuitBreaker');
    });

    test('should report unhealthy when circuit breaker is open', async () => {
      // Open the circuit breaker
      for (let i = 0; i < 5; i++) {
        apiKeyService._recordFailure();
      }
      
      const health = await apiKeyService.healthCheck();
      
      expect(health.healthy).toBe(false);
      expect(health.circuitBreaker.state).toBe('OPEN');
    });
  });

  describe('parameter validation', () => {
    test('should validate empty token', async () => {
      const result = await apiKeyService.getUserApiKeys('');
      
      expect(result.success).toBe(false);
      expect(result.error).toBe('Authorization token is required');
    });

    test('should validate missing provider', async () => {
      const result = await apiKeyService.storeApiKey('token', '', 'key', 'secret');
      
      expect(result.success).toBe(false);
      expect(result.error).toBe('Provider is required');
    });

    test('should validate missing API key', async () => {
      const result = await apiKeyService.storeApiKey('token', 'provider', '', 'secret');
      
      expect(result.success).toBe(false);
      expect(result.error).toBe('API key is required');
    });
  });

  describe('error handling', () => {
    test('should handle errors gracefully', async () => {
      // This will fail because we haven't mocked the JWT verifier
      const result = await apiKeyService.validateJwtToken('invalid-token');
      
      expect(result.valid).toBe(false);
      expect(result.error).toBeDefined();
    });

    test('should return error when circuit breaker is open', async () => {
      // Open the circuit breaker
      for (let i = 0; i < 5; i++) {
        apiKeyService._recordFailure();
      }
      
      const result = await apiKeyService.getUserApiKeys('any-token');
      
      expect(result.success).toBe(false);
      expect(result.error).toBe('Service temporarily unavailable');
    });
  });
});
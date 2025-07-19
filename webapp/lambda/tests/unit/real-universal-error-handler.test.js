/**
 * UNIT TESTS: Universal Error Handler
 * Real implementation testing with zero mocks for business logic
 * Comprehensive coverage of error categorization, handling, and recovery strategies
 */

// Jest globals are automatically available in test environment

// Import the real implementation
const {
  asyncHandler,
  enrichErrorContext,
  categorizeError,
  determineSeverity,
  isRecoverable,
  generateUserMessage,
  formatErrorResponse,
  logError,
  errorHandlerMiddleware,
  handleDatabaseError,
  handleExternalServiceError
} = require('../../middleware/universalErrorHandler');

describe('Universal Error Handler Unit Tests', () => {
  let mockReq, mockRes, mockNext, mockLogger;
  
  beforeEach(() => {
    // Mock request object
    mockReq = {
      method: 'GET',
      path: '/api/test',
      params: { id: '123' },
      query: { filter: 'active' },
      headers: {
        'user-agent': 'Mozilla/5.0',
        'content-type': 'application/json',
        'origin': 'https://example.com'
      },
      correlationId: 'test-correlation-123',
      user: {
        sub: 'user-456',
        email: 'test@example.com',
        roles: ['user']
      },
      startTime: Date.now() - 1000 // 1 second ago
    };
    
    // Mock response object
    mockRes = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis()
    };
    
    // Mock next function
    mockNext = jest.fn();
    
    // Mock logger
    mockLogger = {
      info: jest.fn(),
      warn: jest.fn(),
      error: jest.fn(),
      getCorrelationId: jest.fn().mockReturnValue('test-correlation-123')
    };
    
    // Mock console methods to reduce noise
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
    
    // Reset environment
    process.env.NODE_ENV = 'test';
  });
  
  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('Error Categorization', () => {
    it('categorizes circuit breaker errors correctly', () => {
      const error = new Error('Circuit breaker is open for database service');
      expect(categorizeError(error)).toBe('CIRCUIT_BREAKER_ERROR');
    });

    it('categorizes database errors correctly', () => {
      const dbError1 = new Error('Connection to PostgreSQL failed');
      const dbError2 = { name: 'DatabaseError', message: 'Query timeout' };
      const dbError3 = new Error('database connection lost');
      
      expect(categorizeError(dbError1)).toBe('DATABASE_ERROR');
      expect(categorizeError(dbError2)).toBe('DATABASE_ERROR');
      expect(categorizeError(dbError3)).toBe('DATABASE_ERROR');
    });

    it('categorizes timeout errors correctly', () => {
      const timeoutError1 = { name: 'TimeoutError', message: 'Operation timed out' };
      const timeoutError2 = new Error('Request timed out after 30 seconds');
      const timeoutError3 = new Error('API request timeout occurred');
      
      expect(categorizeError(timeoutError1)).toBe('TIMEOUT_ERROR');
      expect(categorizeError(timeoutError2)).toBe('TIMEOUT_ERROR');
      expect(categorizeError(timeoutError3)).toBe('TIMEOUT_ERROR');
    });

    it('categorizes authentication errors correctly', () => {
      const authError1 = { code: 401, message: 'Unauthorized access' };
      const authError2 = new Error('JWT token expired');
      const authError3 = new Error('Invalid token provided');
      
      expect(categorizeError(authError1)).toBe('AUTHENTICATION_ERROR');
      expect(categorizeError(authError2)).toBe('AUTHENTICATION_ERROR');
      expect(categorizeError(authError3)).toBe('AUTHENTICATION_ERROR');
    });

    it('categorizes authorization errors correctly', () => {
      const authzError1 = { code: 403, message: 'Forbidden' };
      const authzError2 = new Error('Insufficient permissions');
      
      expect(categorizeError(authzError1)).toBe('AUTHORIZATION_ERROR');
      expect(categorizeError(authzError2)).toBe('AUTHORIZATION_ERROR');
    });

    it('categorizes validation errors correctly', () => {
      const validationError1 = { code: 400, message: 'Bad request' };
      const validationError2 = new Error('Validation failed for input');
      const validationError3 = new Error('Invalid email format');
      
      expect(categorizeError(validationError1)).toBe('VALIDATION_ERROR');
      expect(categorizeError(validationError2)).toBe('VALIDATION_ERROR');
      expect(categorizeError(validationError3)).toBe('VALIDATION_ERROR');
    });

    it('categorizes external service errors correctly', () => {
      const extError1 = new Error('Alpaca API connection failed');
      const extError2 = new Error('External service unavailable');
      const extError3 = new Error('Third-party API error occurred');
      
      expect(categorizeError(extError1)).toBe('EXTERNAL_SERVICE_ERROR');
      expect(categorizeError(extError2)).toBe('EXTERNAL_SERVICE_ERROR');
      expect(categorizeError(extError3)).toBe('EXTERNAL_SERVICE_ERROR');
    });

    it('categorizes rate limit errors correctly', () => {
      const rateLimitError1 = { code: 429, message: 'Too many requests' };
      const rateLimitError2 = new Error('Rate limit exceeded');
      
      expect(categorizeError(rateLimitError1)).toBe('RATE_LIMIT_ERROR');
      expect(categorizeError(rateLimitError2)).toBe('RATE_LIMIT_ERROR');
    });

    it('categorizes business logic errors correctly', () => {
      const businessError = { code: 422, message: 'Cannot process this operation' };
      expect(categorizeError(businessError)).toBe('BUSINESS_LOGIC_ERROR');
    });

    it('categorizes server errors correctly', () => {
      const serverError = { code: 500, message: 'Internal server error' };
      expect(categorizeError(serverError)).toBe('SERVER_ERROR');
    });

    it('returns UNKNOWN_ERROR for unrecognized errors', () => {
      const unknownError = new Error('Some weird error');
      expect(categorizeError(unknownError)).toBe('UNKNOWN_ERROR');
    });
  });

  describe('Severity Determination', () => {
    it('assigns CRITICAL severity to database and server errors', () => {
      const dbError = new Error('database connection failed');
      const serverError = { code: 500, message: 'Internal error' };
      
      expect(determineSeverity(dbError)).toBe('CRITICAL');
      expect(determineSeverity(serverError)).toBe('CRITICAL');
    });

    it('assigns HIGH severity to external service and circuit breaker errors', () => {
      const extError = new Error('Alpaca service down');
      const cbError = new Error('Circuit breaker open');
      
      expect(determineSeverity(extError)).toBe('HIGH');
      expect(determineSeverity(cbError)).toBe('HIGH');
    });

    it('assigns MEDIUM severity to auth and timeout errors', () => {
      const authError = { code: 401, message: 'Unauthorized' };
      const timeoutError = { name: 'TimeoutError', message: 'Timeout' };
      
      expect(determineSeverity(authError)).toBe('MEDIUM');
      expect(determineSeverity(timeoutError)).toBe('MEDIUM');
    });

    it('assigns LOW severity to validation and rate limit errors', () => {
      const validationError = { code: 400, message: 'Invalid input' };
      const rateLimitError = { code: 429, message: 'Too many requests' };
      
      expect(determineSeverity(validationError)).toBe('LOW');
      expect(determineSeverity(rateLimitError)).toBe('LOW');
    });

    it('returns UNKNOWN for unrecognized error types', () => {
      const unknownError = new Error('Mystery error');
      expect(determineSeverity(unknownError)).toBe('UNKNOWN');
    });
  });

  describe('Recoverability Assessment', () => {
    it('identifies recoverable errors correctly', () => {
      const timeoutError = { name: 'TimeoutError', message: 'Timeout' };
      const rateLimitError = { code: 429, message: 'Rate limited' };
      const extServiceError = new Error('Alpaca API down');
      const cbError = new Error('Circuit breaker open');
      
      expect(isRecoverable(timeoutError)).toBe(true);
      expect(isRecoverable(rateLimitError)).toBe(true);
      expect(isRecoverable(extServiceError)).toBe(true);
      expect(isRecoverable(cbError)).toBe(true);
    });

    it('identifies non-recoverable errors correctly', () => {
      const dbError = new Error('database connection failed');
      const authError = { code: 401, message: 'Unauthorized' };
      const validationError = { code: 400, message: 'Invalid input' };
      
      expect(isRecoverable(dbError)).toBe(false);
      expect(isRecoverable(authError)).toBe(false);
      expect(isRecoverable(validationError)).toBe(false);
    });
  });

  describe('User Message Generation', () => {
    it('generates appropriate user messages for each category', () => {
      expect(generateUserMessage({}, 'DATABASE_ERROR'))
        .toContain('technical difficulties');
      expect(generateUserMessage({}, 'AUTHENTICATION_ERROR'))
        .toContain('session has expired');
      expect(generateUserMessage({}, 'AUTHORIZATION_ERROR'))
        .toContain('permission');
      expect(generateUserMessage({}, 'VALIDATION_ERROR'))
        .toContain('check your input');
      expect(generateUserMessage({}, 'EXTERNAL_SERVICE_ERROR'))
        .toContain('trading partner');
      expect(generateUserMessage({}, 'RATE_LIMIT_ERROR'))
        .toContain('too many requests');
      expect(generateUserMessage({}, 'TIMEOUT_ERROR'))
        .toContain('took too long');
      expect(generateUserMessage({}, 'CIRCUIT_BREAKER_ERROR'))
        .toContain('temporarily unavailable');
    });

    it('uses custom message for business logic errors', () => {
      const error = { message: 'Insufficient funds for this transaction' };
      const message = generateUserMessage(error, 'BUSINESS_LOGIC_ERROR');
      expect(message).toBe('Insufficient funds for this transaction');
    });

    it('falls back to default message for unknown categories', () => {
      const message = generateUserMessage({}, 'UNKNOWN_CATEGORY');
      expect(message).toContain('unexpected error');
    });
  });

  describe('Error Context Enrichment', () => {
    it('enriches error with comprehensive context', () => {
      const error = new Error('Test error');
      const context = enrichErrorContext(error, mockReq, { customData: 'test' });
      
      expect(context).toMatchObject({
        name: 'Error',
        message: 'Test error',
        request: {
          method: 'GET',
          path: '/api/test',
          params: { id: '123' },
          query: { filter: 'active' },
          correlationId: 'test-correlation-123'
        },
        user: {
          id: 'user-456',
          email: 'test@example.com',
          roles: ['user']
        },
        performance: {
          requestStartTime: expect.any(Number),
          duration: expect.any(Number)
        },
        customData: 'test',
        category: expect.any(String),
        severity: expect.any(String),
        recoverable: expect.any(Boolean)
      });
      
      expect(context.stack).toBeDefined();
      expect(typeof context.request.timestamp).toBe('string');
    });

    it('handles missing user context gracefully', () => {
      const reqWithoutUser = { ...mockReq };
      delete reqWithoutUser.user;
      
      const error = new Error('Test error');
      const context = enrichErrorContext(error, reqWithoutUser);
      
      expect(context.user).toBe(null);
    });

    it('calculates performance metrics correctly', () => {
      const error = new Error('Test error');
      const context = enrichErrorContext(error, mockReq);
      
      expect(context.performance.duration).toBeGreaterThan(0);
      expect(context.performance.requestStartTime).toBe(mockReq.startTime);
    });
  });

  describe('Error Response Formatting', () => {
    it('formats error response with correct structure', () => {
      const error = new Error('Test validation error');
      error.code = 400;
      
      const { statusCode, response } = formatErrorResponse(error, mockReq);
      
      expect(statusCode).toBe(400);
      expect(response).toMatchObject({
        success: false,
        error: {
          code: 'VALIDATION_ERROR',
          message: expect.any(String),
          severity: 'low',
          recoverable: false,
          correlationId: 'test-correlation-123'
        },
        timestamp: expect.any(String)
      });
    });

    it('includes development details when NODE_ENV is development', () => {
      process.env.NODE_ENV = 'development';
      
      const error = new Error('Test error');
      const { response } = formatErrorResponse(error, mockReq);
      
      expect(response.error.details).toBeDefined();
      expect(response.error.details.originalMessage).toBe('Test error');
      expect(response.error.details.stack).toBeDefined();
    });

    it('excludes development details in production', () => {
      process.env.NODE_ENV = 'production';
      
      const error = new Error('Test error');
      const { response } = formatErrorResponse(error, mockReq);
      
      expect(response.error.details).toBeUndefined();
    });

    it('includes retry information for recoverable errors', () => {
      const error = { name: 'TimeoutError', message: 'Request timeout' };
      const { response } = formatErrorResponse(error, mockReq);
      
      expect(response.error.retryAfter).toBeDefined();
      expect(response.error.recovery).toBeDefined();
      expect(typeof response.error.retryAfter).toBe('number');
    });

    it('maps status codes correctly by category', () => {
      const testCases = [
        { error: { code: 401 }, expectedStatus: 401 },
        { error: { code: 403 }, expectedStatus: 403 },
        { error: { code: 400 }, expectedStatus: 400 },
        { error: { code: 429 }, expectedStatus: 429 },
        { error: new Error('database failed'), expectedStatus: 503 },
        { error: new Error('alpaca api down'), expectedStatus: 503 },
        { error: { name: 'TimeoutError' }, expectedStatus: 504 }
      ];
      
      testCases.forEach(({ error, expectedStatus }) => {
        const { statusCode } = formatErrorResponse(error, mockReq);
        expect(statusCode).toBe(expectedStatus);
      });
    });
  });

  describe('Async Handler Wrapper', () => {
    it('catches async errors and passes them to next', async () => {
      const testError = new Error('Async operation failed');
      const asyncRoute = async (req, res, next) => {
        throw testError;
      };
      
      const wrappedRoute = asyncHandler(asyncRoute);
      await wrappedRoute(mockReq, mockRes, mockNext);
      
      expect(mockNext).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Async operation failed',
          requestContext: expect.objectContaining({
            method: 'GET',
            path: '/api/test',
            correlationId: 'test-correlation-123',
            userId: 'user-456'
          })
        })
      );
    });

    it('handles non-promise functions gracefully', () => {
      const syncRoute = (req, res, next) => {
        res.json({ success: true });
      };
      
      const wrappedRoute = asyncHandler(syncRoute);
      const result = wrappedRoute(mockReq, mockRes, mockNext);
      
      expect(mockNext).not.toHaveBeenCalled();
      expect(result).toBeUndefined();
    });

    it('handles functions that return non-promise values', () => {
      const routeReturningValue = (req, res, next) => {
        return 'some value';
      };
      
      const wrappedRoute = asyncHandler(routeReturningValue);
      const result = wrappedRoute(mockReq, mockRes, mockNext);
      
      expect(result).toBe('some value');
      expect(mockNext).not.toHaveBeenCalled();
    });
  });

  describe('Error Handler Middleware', () => {
    it('processes error and sends formatted response', () => {
      const error = new Error('Test middleware error');
      error.code = 500;
      
      errorHandlerMiddleware(error, mockReq, mockRes, mockNext);
      
      expect(mockRes.status).toHaveBeenCalledWith(500);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          success: false,
          error: expect.objectContaining({
            code: 'SERVER_ERROR',
            message: expect.any(String),
            correlationId: 'test-correlation-123'
          })
        })
      );
    });

    it('handles errors without correlation ID gracefully', () => {
      const reqWithoutCorrelation = { ...mockReq };
      delete reqWithoutCorrelation.correlationId;
      
      const error = new Error('Test error');
      
      errorHandlerMiddleware(error, reqWithoutCorrelation, mockRes, mockNext);
      
      expect(mockRes.status).toHaveBeenCalled();
      expect(mockRes.json).toHaveBeenCalled();
    });
  });

  describe('Database Error Handler', () => {
    it('executes fallback function when provided', async () => {
      const dbError = new Error('Database connection failed');
      const fallbackData = { cached: true, data: [] };
      const fallbackFn = jest.fn().mockResolvedValue(fallbackData);
      
      const result = await handleDatabaseError(dbError, 'getUserData', fallbackFn);
      
      expect(fallbackFn).toHaveBeenCalled();
      expect(result).toEqual(fallbackData);
    });

    it('throws original error when fallback fails', async () => {
      const dbError = new Error('Database connection failed');
      const fallbackError = new Error('Fallback also failed');
      const fallbackFn = jest.fn().mockRejectedValue(fallbackError);
      
      await expect(
        handleDatabaseError(dbError, 'getUserData', fallbackFn)
      ).rejects.toThrow('Database connection failed');
      
      expect(fallbackFn).toHaveBeenCalled();
    });

    it('throws original error when no fallback provided', async () => {
      const dbError = new Error('Database connection failed');
      
      await expect(
        handleDatabaseError(dbError, 'getUserData')
      ).rejects.toThrow('Database connection failed');
    });
  });

  describe('External Service Error Handler', () => {
    it('throws retry error for retryable errors within retry limit', async () => {
      const timeoutError = { name: 'TimeoutError', message: 'Service timeout' };
      
      await expect(
        handleExternalServiceError(timeoutError, 'alpaca', 'getQuote', 0, 3)
      ).rejects.toMatchObject({
        name: 'TimeoutError',
        message: 'Service timeout',
        retryCount: 1
      });
    });

    it('throws original error when retry limit exceeded', async () => {
      const timeoutError = { name: 'TimeoutError', message: 'Service timeout' };
      
      await expect(
        handleExternalServiceError(timeoutError, 'alpaca', 'getQuote', 3, 3)
      ).rejects.toMatchObject({
        name: 'TimeoutError',
        message: 'Service timeout'
      });
    });

    it('throws original error for non-retryable errors', async () => {
      const authError = { code: 401, message: 'Unauthorized' };
      
      await expect(
        handleExternalServiceError(authError, 'alpaca', 'getQuote', 0, 3)
      ).rejects.toMatchObject({
        code: 401,
        message: 'Unauthorized'
      });
    });

    it('applies exponential backoff with maximum delay', async () => {
      jest.useFakeTimers();
      
      const timeoutError = { name: 'TimeoutError', message: 'Service timeout' };
      
      const errorPromise = handleExternalServiceError(
        timeoutError, 
        'alpaca', 
        'getQuote', 
        5, // High retry count for max delay test
        10
      );
      
      // Fast-forward time
      jest.advanceTimersByTime(30000); // Should max out at 30 seconds
      
      await expect(errorPromise).rejects.toMatchObject({
        retryCount: 6
      });
      
      jest.useRealTimers();
    });
  });

  describe('Error Logging', () => {
    it('logs errors with appropriate severity levels', () => {
      mockReq.logger = mockLogger;
      
      // Test critical error logging
      const criticalError = new Error('Database failure');
      logError(criticalError, mockReq);
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Critical error occurred',
        expect.any(Object)
      );
      
      // Test medium error logging
      const authError = { code: 401, message: 'Unauthorized' };
      logError(authError, mockReq);
      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Medium severity error',
        expect.any(Object)
      );
      
      // Test low error logging
      const validationError = { code: 400, message: 'Invalid input' };
      logError(validationError, mockReq);
      expect(mockLogger.info).toHaveBeenCalledWith(
        'Low severity error',
        expect.any(Object)
      );
    });

    it('triggers critical error alert for critical errors', () => {
      const criticalError = new Error('Database completely down');
      logError(criticalError, mockReq);
      
      expect(console.error).toHaveBeenCalledWith(
        '🚨 CRITICAL ERROR ALERT:',
        expect.objectContaining({
          correlationId: 'test-correlation-123',
          error: 'Database completely down',
          user: 'user-456',
          path: '/api/test'
        })
      );
    });

    it('uses fallback logger when request logger not available', () => {
      const errorWithoutLogger = new Error('Test error');
      
      // Should not throw even without request logger
      expect(() => logError(errorWithoutLogger, mockReq)).not.toThrow();
    });
  });

  describe('Edge Cases and Error Handling', () => {
    it('handles errors with undefined message', () => {
      const errorWithoutMessage = { name: 'WeirdError' };
      const category = categorizeError(errorWithoutMessage);
      expect(category).toBe('UNKNOWN_ERROR');
    });

    it('handles errors with null properties', () => {
      const nullError = { message: null, code: null };
      const context = enrichErrorContext(nullError, mockReq);
      expect(context.name).toBeDefined();
      expect(context.category).toBeDefined();
    });

    it('handles request objects with missing properties gracefully', () => {
      const minimalReq = { method: 'GET', path: '/test' };
      const error = new Error('Test error');
      
      const context = enrichErrorContext(error, minimalReq);
      expect(context.request.method).toBe('GET');
      expect(context.request.path).toBe('/test');
      expect(context.user).toBe(null);
    });

    it('handles circular reference in error objects', () => {
      const circularError = new Error('Circular error');
      circularError.circular = circularError;
      
      // Should not throw despite circular reference
      expect(() => enrichErrorContext(circularError, mockReq)).not.toThrow();
    });
  });
});
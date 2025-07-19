/**
 * Universal Error Handler Unit Tests
 * Tests individual components of the universal error handling system
 */

const {
  asyncHandler,
  enrichErrorContext,
  categorizeError,
  determineSeverity,
  isRecoverable,
  generateUserMessage,
  formatErrorResponse,
  logError,
  handleDatabaseError,
  handleExternalServiceError
} = require('../../middleware/universalErrorHandler');

describe('Universal Error Handler Unit Tests', () => {
  let mockReq, mockRes, mockNext, mockLogger;

  beforeEach(() => {
    mockReq = {
      method: 'POST',
      path: '/api/test',
      params: { id: 'test-id' },
      query: { page: '1' },
      body: { data: 'test' },
      headers: {
        'user-agent': 'test-agent',
        'content-type': 'application/json',
        'origin': 'https://test.com'
      },
      user: {
        sub: 'user-123',
        email: 'test@example.com',
        roles: ['trader']
      },
      correlationId: 'test-correlation-123',
      startTime: Date.now() - 1000
    };

    mockRes = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn()
    };

    mockNext = jest.fn();

    mockLogger = {
      info: jest.fn(),
      warn: jest.fn(),
      error: jest.fn()
    };

    mockReq.logger = mockLogger;
  });

  describe('Error Categorization Functions', () => {
    test('should categorize database errors correctly', () => {
      const errors = [
        { message: 'database connection failed', expected: 'DATABASE_ERROR' },
        { message: 'postgresql timeout', expected: 'DATABASE_ERROR' },
        { name: 'DatabaseError', expected: 'DATABASE_ERROR' }
      ];

      errors.forEach(({ message, name, expected }) => {
        const error = new Error(message);
        if (name) error.name = name;
        expect(categorizeError(error)).toBe(expected);
      });
    });

    test('should categorize authentication errors correctly', () => {
      const errors = [
        { code: 401, expected: 'AUTHENTICATION_ERROR' },
        { message: 'unauthorized access', expected: 'AUTHENTICATION_ERROR' },
        { message: 'jwt token expired', expected: 'AUTHENTICATION_ERROR' }
      ];

      errors.forEach(({ message, code, expected }) => {
        const error = new Error(message);
        if (code) error.code = code;
        expect(categorizeError(error)).toBe(expected);
      });
    });

    test('should categorize validation errors correctly', () => {
      const errors = [
        { code: 400, expected: 'VALIDATION_ERROR' },
        { message: 'validation failed', expected: 'VALIDATION_ERROR' },
        { message: 'invalid input data', expected: 'VALIDATION_ERROR' }
      ];

      errors.forEach(({ message, code, expected }) => {
        const error = new Error(message);
        if (code) error.code = code;
        expect(categorizeError(error)).toBe(expected);
      });
    });

    test('should categorize external service errors correctly', () => {
      const errors = [
        { message: 'alpaca api failed', expected: 'EXTERNAL_SERVICE_ERROR' },
        { message: 'api request timeout', expected: 'EXTERNAL_SERVICE_ERROR' },
        { message: 'external service unavailable', expected: 'EXTERNAL_SERVICE_ERROR' }
      ];

      errors.forEach(({ message, expected }) => {
        const error = new Error(message);
        expect(categorizeError(error)).toBe(expected);
      });
    });

    test('should categorize timeout errors correctly', () => {
      const errors = [
        { message: 'request timeout', expected: 'TIMEOUT_ERROR' },
        { message: 'operation timed out', expected: 'TIMEOUT_ERROR' },
        { name: 'TimeoutError', expected: 'TIMEOUT_ERROR' }
      ];

      errors.forEach(({ message, name, expected }) => {
        const error = new Error(message);
        if (name) error.name = name;
        expect(categorizeError(error)).toBe(expected);
      });
    });

    test('should categorize circuit breaker errors correctly', () => {
      const error = new Error('Circuit breaker is OPEN. Database unavailable for 30 more seconds');
      expect(categorizeError(error)).toBe('CIRCUIT_BREAKER_ERROR');
    });

    test('should categorize rate limit errors correctly', () => {
      const errors = [
        { code: 429, expected: 'RATE_LIMIT_ERROR' },
        { message: 'rate limit exceeded', expected: 'RATE_LIMIT_ERROR' },
        { message: 'too many requests', expected: 'RATE_LIMIT_ERROR' }
      ];

      errors.forEach(({ message, code, expected }) => {
        const error = new Error(message);
        if (code) error.code = code;
        expect(categorizeError(error)).toBe(expected);
      });
    });
  });

  describe('Error Severity Determination', () => {
    test('should determine CRITICAL severity for database and server errors', () => {
      const criticalErrors = [
        { message: 'database connection failed' },
        { code: 500 },
        { name: 'DatabaseError' }
      ];

      criticalErrors.forEach(({ message, code, name }) => {
        const error = new Error(message);
        if (code) error.code = code;
        if (name) error.name = name;
        expect(determineSeverity(error)).toBe('CRITICAL');
      });
    });

    test('should determine HIGH severity for external service and circuit breaker errors', () => {
      const highErrors = [
        { message: 'alpaca api failed' },
        { message: 'circuit breaker is open' },
        { message: 'external service timeout' }
      ];

      highErrors.forEach(({ message }) => {
        const error = new Error(message);
        expect(determineSeverity(error)).toBe('HIGH');
      });
    });

    test('should determine MEDIUM severity for auth and timeout errors', () => {
      const mediumErrors = [
        { code: 401 },
        { code: 403 },
        { message: 'request timeout' }
      ];

      mediumErrors.forEach(({ message, code }) => {
        const error = new Error(message);
        if (code) error.code = code;
        expect(determineSeverity(error)).toBe('MEDIUM');
      });
    });

    test('should determine LOW severity for validation and rate limit errors', () => {
      const lowErrors = [
        { code: 400 },
        { code: 429 },
        { message: 'validation failed' }
      ];

      lowErrors.forEach(({ message, code }) => {
        const error = new Error(message);
        if (code) error.code = code;
        expect(determineSeverity(error)).toBe('LOW');
      });
    });
  });

  describe('Error Recoverability Assessment', () => {
    test('should identify recoverable errors correctly', () => {
      const recoverableErrors = [
        { message: 'request timeout' },
        { code: 429 },
        { message: 'alpaca api failed' },
        { message: 'circuit breaker is open' }
      ];

      recoverableErrors.forEach(({ message, code }) => {
        const error = new Error(message);
        if (code) error.code = code;
        expect(isRecoverable(error)).toBe(true);
      });
    });

    test('should identify non-recoverable errors correctly', () => {
      const nonRecoverableErrors = [
        { message: 'database connection failed' },
        { code: 401 },
        { code: 403 },
        { code: 400 }
      ];

      nonRecoverableErrors.forEach(({ message, code }) => {
        const error = new Error(message);
        if (code) error.code = code;
        expect(isRecoverable(error)).toBe(false);
      });
    });
  });

  describe('User Message Generation', () => {
    test('should generate appropriate user messages for each error category', () => {
      const testCases = [
        { category: 'DATABASE_ERROR', expectedKeywords: ['technical difficulties'] },
        { category: 'AUTHENTICATION_ERROR', expectedKeywords: ['session', 'expired'] },
        { category: 'AUTHORIZATION_ERROR', expectedKeywords: ['permission'] },
        { category: 'VALIDATION_ERROR', expectedKeywords: ['input'] },
        { category: 'EXTERNAL_SERVICE_ERROR', expectedKeywords: ['trading partner', 'unavailable'] },
        { category: 'RATE_LIMIT_ERROR', expectedKeywords: ['too many requests'] },
        { category: 'TIMEOUT_ERROR', expectedKeywords: ['took too long'] },
        { category: 'CIRCUIT_BREAKER_ERROR', expectedKeywords: ['temporarily unavailable'] },
        { category: 'SERVER_ERROR', expectedKeywords: ['technical issues'] }
      ];

      testCases.forEach(({ category, expectedKeywords }) => {
        const message = generateUserMessage(new Error('test'), category);
        expectedKeywords.forEach(keyword => {
          expect(message.toLowerCase()).toContain(keyword.toLowerCase());
        });
      });
    });

    test('should provide fallback message for unknown categories', () => {
      const message = generateUserMessage(new Error('test'), 'UNKNOWN_CATEGORY');
      expect(message).toContain('unexpected error');
    });
  });

  describe('Error Context Enrichment', () => {
    test('should enrich error context with comprehensive information', () => {
      const error = new Error('Test error');
      error.name = 'TestError';
      error.stack = 'Error stack trace';

      const enrichedContext = enrichErrorContext(error, mockReq, { customField: 'customValue' });

      // Core error information
      expect(enrichedContext.name).toBe('TestError');
      expect(enrichedContext.message).toBe('Test error');
      expect(enrichedContext.stack).toBe('Error stack trace');

      // Request context
      expect(enrichedContext.request.method).toBe('POST');
      expect(enrichedContext.request.path).toBe('/api/test');
      expect(enrichedContext.request.correlationId).toBe('test-correlation-123');

      // User context
      expect(enrichedContext.user.id).toBe('user-123');
      expect(enrichedContext.user.email).toBe('test@example.com');

      // Performance context
      expect(enrichedContext.performance.duration).toBeGreaterThan(0);

      // Additional context
      expect(enrichedContext.customField).toBe('customValue');

      // Error categorization
      expect(enrichedContext.category).toBeDefined();
      expect(enrichedContext.severity).toBeDefined();
      expect(typeof enrichedContext.recoverable).toBe('boolean');
    });

    test('should handle requests without user context', () => {
      const reqWithoutUser = { ...mockReq };
      delete reqWithoutUser.user;

      const error = new Error('Test error');
      const enrichedContext = enrichErrorContext(error, reqWithoutUser);

      expect(enrichedContext.user).toBeNull();
      expect(enrichedContext.request.method).toBe('POST');
    });
  });

  describe('Error Response Formatting', () => {
    test('should format error responses with all required fields', () => {
      const error = new Error('Test database error');
      error.name = 'DatabaseError';

      const { statusCode, response } = formatErrorResponse(error, mockReq);

      expect(statusCode).toBe(503);
      expect(response.success).toBe(false);
      expect(response.error.code).toBe('DATABASE_ERROR');
      expect(response.error.severity).toBe('critical');
      expect(response.error.recoverable).toBe(false);
      expect(response.error.correlationId).toBe('test-correlation-123');
      expect(response.timestamp).toBeDefined();
    });

    test('should include retry information for recoverable errors', () => {
      const error = new Error('Request timeout');
      error.name = 'TimeoutError';

      const { statusCode, response } = formatErrorResponse(error, mockReq);

      expect(statusCode).toBe(504);
      expect(response.error.recoverable).toBe(true);
      expect(response.error.retryAfter).toBeDefined();
      expect(response.error.recovery).toBeDefined();
    });

    test('should override status codes based on error category', () => {
      const testCases = [
        { error: { message: 'unauthorized' }, expectedStatus: 401 },
        { error: { message: 'forbidden' }, expectedStatus: 403 },
        { error: { message: 'validation failed' }, expectedStatus: 400 },
        { error: { code: 429 }, expectedStatus: 429 },
        { error: { message: 'database failed' }, expectedStatus: 503 }
      ];

      testCases.forEach(({ error: errorProps, expectedStatus }) => {
        const error = new Error(errorProps.message || 'test');
        if (errorProps.code) error.code = errorProps.code;

        const { statusCode } = formatErrorResponse(error, mockReq);
        expect(statusCode).toBe(expectedStatus);
      });
    });
  });

  describe('Async Handler Wrapper', () => {
    test('should wrap async functions and catch errors', async () => {
      const asyncFunction = asyncHandler(async (req, res, next) => {
        throw new Error('Async error');
      });

      await asyncFunction(mockReq, mockRes, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.objectContaining({
        message: 'Async error',
        requestContext: expect.objectContaining({
          method: 'POST',
          path: '/api/test',
          correlationId: 'test-correlation-123'
        })
      }));
    });

    test('should pass through non-promise functions', () => {
      const syncFunction = asyncHandler((req, res, next) => {
        res.json({ success: true });
      });

      syncFunction(mockReq, mockRes, mockNext);

      expect(mockRes.json).toHaveBeenCalledWith({ success: true });
      expect(mockNext).not.toHaveBeenCalled();
    });

    test('should handle functions that return non-promise values', () => {
      const nonPromiseFunction = asyncHandler((req, res, next) => {
        return 'not a promise';
      });

      const result = nonPromiseFunction(mockReq, mockRes, mockNext);
      expect(result).toBe('not a promise');
      expect(mockNext).not.toHaveBeenCalled();
    });
  });

  describe('Error Logging', () => {
    test('should log errors with appropriate severity levels', () => {
      const testCases = [
        { error: { message: 'database failed' }, expectedLevel: 'error' },
        { error: { message: 'alpaca api failed' }, expectedLevel: 'error' },
        { error: { message: 'authentication failed' }, expectedLevel: 'warn' },
        { error: { message: 'validation failed' }, expectedLevel: 'info' }
      ];

      testCases.forEach(({ error: errorProps, expectedLevel }) => {
        const error = new Error(errorProps.message);
        logError(error, mockReq);

        expect(mockLogger[expectedLevel]).toHaveBeenCalled();
      });
    });

    test('should log critical errors with console alerts', () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation();
      
      const criticalError = new Error('Database connection failed');
      criticalError.name = 'DatabaseError';
      
      logError(criticalError, mockReq);

      expect(consoleSpy).toHaveBeenCalledWith(
        '🚨 CRITICAL ERROR ALERT:',
        expect.objectContaining({
          correlationId: 'test-correlation-123',
          error: 'Database connection failed'
        })
      );

      consoleSpy.mockRestore();
    });
  });

  describe('Database Error Handler', () => {
    test('should handle database errors without fallback', async () => {
      const databaseError = new Error('Connection timeout');
      
      await expect(handleDatabaseError(databaseError, 'SELECT users')).rejects.toThrow('Connection timeout');
    });

    test('should attempt fallback when provided', async () => {
      const databaseError = new Error('Connection timeout');
      const fallbackData = { cached: true, data: [] };
      const fallbackFn = jest.fn().mockResolvedValue(fallbackData);

      const result = await handleDatabaseError(databaseError, 'SELECT users', fallbackFn);

      expect(fallbackFn).toHaveBeenCalled();
      expect(result).toEqual(fallbackData);
    });

    test('should re-throw original error if fallback fails', async () => {
      const databaseError = new Error('Connection timeout');
      const fallbackError = new Error('Fallback failed');
      const fallbackFn = jest.fn().mockRejectedValue(fallbackError);

      await expect(handleDatabaseError(databaseError, 'SELECT users', fallbackFn)).rejects.toThrow('Connection timeout');
      expect(fallbackFn).toHaveBeenCalled();
    });
  });

  describe('External Service Error Handler', () => {
    test('should handle non-retryable errors immediately', async () => {
      const nonRetryableError = new Error('Authentication failed');
      nonRetryableError.status = 401;

      await expect(handleExternalServiceError(nonRetryableError, 'alpaca', 'getAccount')).rejects.toThrow('Authentication failed');
    });

    test('should indicate retry for retryable errors', async () => {
      const retryableError = new Error('Rate limit exceeded');
      retryableError.status = 429;

      await expect(handleExternalServiceError(retryableError, 'alpaca', 'getAccount', 0, 3)).rejects.toThrow();
    });

    test('should stop retrying after max attempts', async () => {
      const retryableError = new Error('Timeout');
      
      await expect(handleExternalServiceError(retryableError, 'alpaca', 'getAccount', 3, 3)).rejects.toThrow('Timeout');
    });
  });

  describe('Performance and Memory Efficiency', () => {
    test('should handle large error contexts efficiently', () => {
      const largeError = new Error('Large error');
      const largeContext = {
        largeData: 'x'.repeat(10000),
        arrays: Array(1000).fill('test'),
        objects: Array(100).fill().map((_, i) => ({ id: i, data: 'test' }))
      };

      const start = Date.now();
      const enrichedContext = enrichErrorContext(largeError, mockReq, largeContext);
      const duration = Date.now() - start;

      expect(duration).toBeLessThan(100); // Should process large contexts quickly
      expect(enrichedContext).toBeDefined();
    });

    test('should handle rapid error processing', () => {
      const start = Date.now();
      
      for (let i = 0; i < 1000; i++) {
        const error = new Error(`Error ${i}`);
        categorizeError(error);
        determineSeverity(error);
        isRecoverable(error);
      }
      
      const duration = Date.now() - start;
      expect(duration).toBeLessThan(1000); // Should categorize 1000 errors in under 1 second
    });
  });
});
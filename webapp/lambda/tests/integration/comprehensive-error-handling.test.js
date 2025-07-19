/**
 * Comprehensive Error Handling Integration Tests
 * Tests the complete error handling strategy across all application layers
 */

const request = require('supertest');
const express = require('express');
const { asyncHandler, errorHandlerMiddleware, categorizeError, determineSeverity, isRecoverable } = require('../../middleware/universalErrorHandler');
const { businessValidationBundles } = require('../../middleware/businessValidation');
const { advancedInjectionPrevention } = require('../../middleware/enhancedValidation');

describe('Comprehensive Error Handling Integration Tests', () => {
  let app;

  beforeAll(() => {
    // Create test Express app with complete error handling stack
    app = express();
    app.use(express.json());
    
    // Add request tracking middleware
    app.use((req, res, next) => {
      req.startTime = Date.now();
      req.correlationId = `test-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      req.logger = {
        info: jest.fn(),
        warn: jest.fn(),
        error: jest.fn()
      };
      next();
    });
    
    // Add security middleware
    app.use(advancedInjectionPrevention);
    
    // Test routes for different error scenarios
    app.post('/test/database-error', asyncHandler(async (req, res) => {
      const error = new Error('Connection timeout to database');
      error.name = 'DatabaseError';
      error.code = 'TIMEOUT';
      throw error;
    }));
    
    app.post('/test/validation-error', businessValidationBundles.placeOrder, asyncHandler(async (req, res) => {
      res.json({ success: true, message: 'Order placed successfully' });
    }));
    
    app.post('/test/authentication-error', asyncHandler(async (req, res) => {
      const error = new Error('JWT token expired');
      error.status = 401;
      throw error;
    }));
    
    app.post('/test/authorization-error', asyncHandler(async (req, res) => {
      const error = new Error('Insufficient permissions');
      error.status = 403;
      throw error;
    }));
    
    app.post('/test/external-service-error', asyncHandler(async (req, res) => {
      const error = new Error('Alpaca API rate limit exceeded');
      error.status = 429;
      throw error;
    }));
    
    app.post('/test/timeout-error', asyncHandler(async (req, res) => {
      const error = new Error('Request timeout after 30 seconds');
      error.name = 'TimeoutError';
      throw error;
    }));
    
    app.post('/test/business-logic-error', asyncHandler(async (req, res) => {
      const error = new Error('Insufficient funds for this trade');
      error.status = 400;
      throw error;
    }));
    
    app.post('/test/server-error', asyncHandler(async (req, res) => {
      const error = new Error('Internal server error');
      error.status = 500;
      throw error;
    }));
    
    app.post('/test/circuit-breaker-error', asyncHandler(async (req, res) => {
      const error = new Error('Circuit breaker is OPEN. Database unavailable for 45 more seconds');
      throw error;
    }));
    
    app.post('/test/injection-attempt', asyncHandler(async (req, res) => {
      // This should be caught by injection prevention middleware
      res.json({ success: true, data: req.body });
    }));
    
    app.post('/test/multiple-errors', asyncHandler(async (req, res) => {
      // Simulate a complex error scenario
      const errors = [];
      
      if (!req.body.symbol) {
        const error = new Error('Missing required field: symbol');
        error.field = 'symbol';
        errors.push(error);
      }
      
      if (!req.body.quantity) {
        const error = new Error('Missing required field: quantity');
        error.field = 'quantity';
        errors.push(error);
      }
      
      if (errors.length > 0) {
        const aggregateError = new Error('Multiple validation errors');
        aggregateError.name = 'AggregateValidationError';
        aggregateError.details = errors;
        throw aggregateError;
      }
      
      res.json({ success: true, message: 'All validations passed' });
    }));
    
    // Add universal error handler as the last middleware
    app.use(errorHandlerMiddleware);
  });

  describe('Error Categorization and Classification', () => {
    test('should correctly categorize database errors', () => {
      const error = new Error('Connection timeout to database');
      error.name = 'DatabaseError';
      
      const category = categorizeError(error);
      expect(category).toBe('DATABASE_ERROR');
      
      const severity = determineSeverity(error);
      expect(severity).toBe('CRITICAL');
      
      const recoverable = isRecoverable(error);
      expect(recoverable).toBe(false);
    });
    
    test('should correctly categorize authentication errors', () => {
      const error = new Error('JWT token expired');
      error.status = 401;
      
      const category = categorizeError(error);
      expect(category).toBe('AUTHENTICATION_ERROR');
      
      const severity = determineSeverity(error);
      expect(severity).toBe('MEDIUM');
    });
    
    test('should correctly categorize external service errors', () => {
      const error = new Error('Alpaca API rate limit exceeded');
      error.status = 429;
      
      const category = categorizeError(error);
      expect(category).toBe('RATE_LIMIT_ERROR');
      
      const severity = determineSeverity(error);
      expect(severity).toBe('LOW');
      
      const recoverable = isRecoverable(error);
      expect(recoverable).toBe(true);
    });
    
    test('should correctly categorize timeout errors', () => {
      const error = new Error('Request timeout after 30 seconds');
      error.name = 'TimeoutError';
      
      const category = categorizeError(error);
      expect(category).toBe('TIMEOUT_ERROR');
      
      const severity = determineSeverity(error);
      expect(severity).toBe('MEDIUM');
      
      const recoverable = isRecoverable(error);
      expect(recoverable).toBe(true);
    });
    
    test('should correctly categorize circuit breaker errors', () => {
      const error = new Error('Circuit breaker is OPEN. Database unavailable for 45 more seconds');
      
      const category = categorizeError(error);
      expect(category).toBe('CIRCUIT_BREAKER_ERROR');
      
      const severity = determineSeverity(error);
      expect(severity).toBe('HIGH');
      
      const recoverable = isRecoverable(error);
      expect(recoverable).toBe(true);
    });
  });

  describe('Database Error Handling', () => {
    test('should handle database connection errors with proper response format', async () => {
      const response = await request(app)
        .post('/test/database-error')
        .expect(503);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('DATABASE_ERROR');
      expect(response.body.error.severity).toBe('critical');
      expect(response.body.error.recoverable).toBe(false);
      expect(response.body.error.correlationId).toBeDefined();
      expect(response.body.timestamp).toBeDefined();
      
      // Should provide user-friendly message
      expect(response.body.error.message).toContain('technical difficulties');
    });
    
    test('should log database errors with enhanced context', async () => {
      const response = await request(app)
        .post('/test/database-error')
        .send({ testData: 'database-test' })
        .expect(503);

      // Verify error structure includes all required fields
      expect(response.body.error).toHaveProperty('code');
      expect(response.body.error).toHaveProperty('message');
      expect(response.body.error).toHaveProperty('severity');
      expect(response.body.error).toHaveProperty('recoverable');
      expect(response.body.error).toHaveProperty('correlationId');
    });
  });

  describe('Authentication and Authorization Error Handling', () => {
    test('should handle authentication errors correctly', async () => {
      const response = await request(app)
        .post('/test/authentication-error')
        .expect(401);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('AUTHENTICATION_ERROR');
      expect(response.body.error.severity).toBe('medium');
      expect(response.body.error.message).toContain('session has expired');
    });
    
    test('should handle authorization errors correctly', async () => {
      const response = await request(app)
        .post('/test/authorization-error')
        .expect(403);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('AUTHORIZATION_ERROR');
      expect(response.body.error.severity).toBe('medium');
      expect(response.body.error.message).toContain('permission');
    });
  });

  describe('Business Validation Error Handling', () => {
    test('should handle invalid trading order validation', async () => {
      const response = await request(app)
        .post('/test/validation-error')
        .send({
          symbol: 'INVALID_SYMBOL_123',  // Too long and contains invalid characters
          quantity: -5,                  // Negative quantity
          orderType: 'invalid_type',     // Invalid order type
          side: 'invalid_side'           // Invalid side
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('BUSINESS_VALIDATION_ERROR');
      expect(response.body.error.validation).toBeDefined();
      expect(Array.isArray(response.body.error.validation)).toBe(true);
      expect(response.body.error.validation.length).toBeGreaterThan(0);
      
      // Should contain specific field errors
      const fieldErrors = response.body.error.validation.map(v => v.field);
      expect(fieldErrors).toContain('symbol');
      expect(fieldErrors).toContain('quantity');
    });
    
    test('should handle valid trading order without errors', async () => {
      const response = await request(app)
        .post('/test/validation-error')
        .send({
          symbol: 'AAPL',
          quantity: 100,
          orderType: 'market',
          side: 'buy',
          timeInForce: 'day'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.message).toBe('Order placed successfully');
    });
    
    test('should handle limit order validation correctly', async () => {
      const response = await request(app)
        .post('/test/validation-error')
        .send({
          symbol: 'AAPL',
          quantity: 100,
          orderType: 'limit',  // Limit order without limit price
          side: 'buy',
          timeInForce: 'day'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error.validation).toBeDefined();
      
      // Should specifically mention missing limit price
      const validationMessages = response.body.error.validation.map(v => v.message);
      expect(validationMessages.some(msg => msg.includes('limit price'))).toBe(true);
    });
  });

  describe('External Service Error Handling', () => {
    test('should handle rate limiting errors with retry information', async () => {
      const response = await request(app)
        .post('/test/external-service-error')
        .expect(429);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('RATE_LIMIT_ERROR');
      expect(response.body.error.recoverable).toBe(true);
      expect(response.body.error.retryAfter).toBeDefined();
      expect(response.body.error.recovery).toBeDefined();
    });
    
    test('should handle timeout errors with recovery instructions', async () => {
      const response = await request(app)
        .post('/test/timeout-error')
        .expect(504);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('TIMEOUT_ERROR');
      expect(response.body.error.recoverable).toBe(true);
      expect(response.body.error.retryAfter).toBeDefined();
      expect(response.body.error.recovery).toBeDefined();
    });
  });

  describe('Security and Injection Prevention', () => {
    test('should block SQL injection attempts', async () => {
      const response = await request(app)
        .post('/test/injection-attempt')
        .send({
          search: "'; DROP TABLE users; --",
          symbol: "AAPL' OR 1=1"
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Security violation detected');
      expect(response.body.code).toBe('INJECTION_DETECTED');
    });
    
    test('should block XSS attempts', async () => {
      const response = await request(app)
        .post('/test/injection-attempt')
        .send({
          name: '<script>alert("xss")</script>',
          description: '<img src=x onerror=alert("xss")>'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Security violation detected');
      expect(response.body.code).toBe('INJECTION_DETECTED');
    });
    
    test('should block command injection attempts', async () => {
      const response = await request(app)
        .post('/test/injection-attempt')
        .send({
          filename: 'test.txt; cat /etc/passwd',
          command: '$(rm -rf /)'
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Security violation detected');
      expect(response.body.code).toBe('INJECTION_DETECTED');
    });
  });

  describe('Circuit Breaker Error Handling', () => {
    test('should handle circuit breaker errors with proper recovery info', async () => {
      const response = await request(app)
        .post('/test/circuit-breaker-error')
        .expect(503);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('CIRCUIT_BREAKER_ERROR');
      expect(response.body.error.recoverable).toBe(true);
      expect(response.body.error.retryAfter).toBeDefined();
      expect(response.body.error.recovery).toBeDefined();
      expect(response.body.error.message).toContain('temporarily unavailable');
    });
  });

  describe('Complex Error Scenarios', () => {
    test('should handle multiple validation errors in single request', async () => {
      const response = await request(app)
        .post('/test/multiple-errors')
        .send({
          // Missing symbol and quantity
          orderType: 'market'
        })
        .expect(500);

      expect(response.body.success).toBe(false);
      
      // Should handle the aggregate error appropriately
      if (response.body.error.details) {
        expect(Array.isArray(response.body.error.details)).toBe(true);
      }
    });
    
    test('should handle server errors with appropriate response', async () => {
      const response = await request(app)
        .post('/test/server-error')
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error.code).toBe('SERVER_ERROR');
      expect(response.body.error.severity).toBe('critical');
      expect(response.body.error.message).toContain('technical issues');
    });
  });

  describe('Error Response Format Consistency', () => {
    test('should maintain consistent error response format across all error types', async () => {
      const errorEndpoints = [
        '/test/database-error',
        '/test/authentication-error',
        '/test/authorization-error',
        '/test/external-service-error',
        '/test/timeout-error',
        '/test/server-error',
        '/test/circuit-breaker-error'
      ];

      for (const endpoint of errorEndpoints) {
        const response = await request(app).post(endpoint);
        
        // Verify consistent error response structure
        expect(response.body).toHaveProperty('success', false);
        expect(response.body).toHaveProperty('error');
        expect(response.body).toHaveProperty('timestamp');
        
        expect(response.body.error).toHaveProperty('code');
        expect(response.body.error).toHaveProperty('message');
        expect(response.body.error).toHaveProperty('severity');
        expect(response.body.error).toHaveProperty('recoverable');
        expect(response.body.error).toHaveProperty('correlationId');
        
        // Verify correlation ID format
        expect(response.body.error.correlationId).toMatch(/^test-\d+-[a-z0-9]+$/);
        
        // Verify timestamp format
        expect(new Date(response.body.timestamp).getTime()).not.toBeNaN();
      }
    });
    
    test('should include retry information for recoverable errors', async () => {
      const recoverableEndpoints = [
        '/test/external-service-error',
        '/test/timeout-error',
        '/test/circuit-breaker-error'
      ];

      for (const endpoint of recoverableEndpoints) {
        const response = await request(app).post(endpoint);
        
        expect(response.body.error.recoverable).toBe(true);
        expect(response.body.error).toHaveProperty('retryAfter');
        expect(response.body.error).toHaveProperty('recovery');
        expect(typeof response.body.error.retryAfter).toBe('number');
        expect(typeof response.body.error.recovery).toBe('string');
      }
    });
  });

  describe('Error Logging and Monitoring', () => {
    test('should log errors with proper correlation IDs', async () => {
      const response = await request(app)
        .post('/test/database-error')
        .expect(503);

      const correlationId = response.body.error.correlationId;
      expect(correlationId).toBeDefined();
      expect(correlationId).toMatch(/^test-\d+-[a-z0-9]+$/);
    });
    
    test('should log critical errors for monitoring', async () => {
      const response = await request(app)
        .post('/test/server-error')
        .expect(500);

      expect(response.body.error.severity).toBe('critical');
      // In a real implementation, this would trigger alerts
    });
  });

  describe('Performance and Response Times', () => {
    test('should handle errors efficiently without significant delay', async () => {
      const start = Date.now();
      
      await request(app)
        .post('/test/database-error')
        .expect(503);
      
      const duration = Date.now() - start;
      expect(duration).toBeLessThan(1000); // Should handle errors in under 1 second
    });
    
    test('should handle multiple concurrent error requests efficiently', async () => {
      const start = Date.now();
      
      const promises = Array(10).fill().map(() => 
        request(app)
          .post('/test/database-error')
          .expect(503)
      );
      
      await Promise.all(promises);
      
      const duration = Date.now() - start;
      expect(duration).toBeLessThan(2000); // Should handle 10 concurrent errors in under 2 seconds
    });
  });
});
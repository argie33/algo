// Jest globals are automatically available

describe('Logger Utility', () => {
  let logger;
  let consoleSpy;

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Clear module cache
    delete require.cache[require.resolve('../../utils/logger')];
    
    // Spy on console methods
    consoleSpy = {
      log: jest.spyOn(console, 'log').mockImplementation(),
      error: jest.spyOn(console, 'error').mockImplementation(),
      warn: jest.spyOn(console, 'warn').mockImplementation(),
      info: jest.spyOn(console, 'info').mockImplementation(),
      debug: jest.spyOn(console, 'debug').mockImplementation()
    };

    // Import logger
    logger = require('../../utils/logger');
  });

  afterEach(() => {
    // Restore console methods
    Object.values(consoleSpy).forEach(spy => spy.mockRestore());
    
    // Clean up environment variables
    delete process.env.NODE_ENV;
    delete process.env.LOG_LEVEL;
  });

  describe('log levels', () => {
    test('should log info messages', () => {
      logger.info('Test info message');
      
      expect(consoleSpy.info).toHaveBeenCalledWith(
        expect.stringContaining('INFO'),
        expect.stringContaining('Test info message')
      );
    });

    test('should log error messages', () => {
      logger.error('Test error message');
      
      expect(consoleSpy.error).toHaveBeenCalledWith(
        expect.stringContaining('ERROR'),
        expect.stringContaining('Test error message')
      );
    });

    test('should log warning messages', () => {
      logger.warn('Test warning message');
      
      expect(consoleSpy.warn).toHaveBeenCalledWith(
        expect.stringContaining('WARN'),
        expect.stringContaining('Test warning message')
      );
    });

    test('should log debug messages when debug is enabled', () => {
      process.env.LOG_LEVEL = 'debug';
      
      // Clear cache to reload with new env var
      delete require.cache[require.resolve('../../utils/logger')];
      logger = require('../../utils/logger');
      
      logger.debug('Test debug message');
      
      expect(consoleSpy.debug).toHaveBeenCalledWith(
        expect.stringContaining('DEBUG'),
        expect.stringContaining('Test debug message')
      );
    });

    test('should not log debug messages in production', () => {
      process.env.NODE_ENV = 'production';
      
      // Clear cache to reload with new env var
      delete require.cache[require.resolve('../../utils/logger')];
      logger = require('../../utils/logger');
      
      logger.debug('Test debug message');
      
      expect(consoleSpy.debug).not.toHaveBeenCalled();
    });
  });

  describe('structured logging', () => {
    test('should include timestamp in log entries', () => {
      logger.info('Test message');
      
      expect(consoleSpy.info).toHaveBeenCalledWith(
        expect.stringMatching(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/),
        expect.any(String)
      );
    });

    test('should log with context object', () => {
      const context = {
        userId: 'user-123',
        requestId: 'req-456',
        operation: 'test-operation'
      };
      
      logger.info('Test message with context', context);
      
      expect(consoleSpy.info).toHaveBeenCalledWith(
        expect.stringContaining('INFO'),
        expect.stringContaining('Test message with context'),
        expect.objectContaining(context)
      );
    });

    test('should handle error objects in context', () => {
      const error = new Error('Test error');
      error.stack = 'Error stack trace...';
      
      logger.error('Error occurred', { error });
      
      expect(consoleSpy.error).toHaveBeenCalledWith(
        expect.stringContaining('ERROR'),
        expect.stringContaining('Error occurred'),
        expect.objectContaining({
          error: expect.objectContaining({
            message: 'Test error',
            name: 'Error',
            stack: 'Error stack trace...'
          })
        })
      );
    });

    test('should sanitize sensitive data in context', () => {
      const context = {
        userId: 'user-123',
        password: 'secret-password',
        apiKey: 'secret-api-key',
        token: 'jwt-token'
      };
      
      logger.info('Test message with sensitive data', context);
      
      const logCall = consoleSpy.info.mock.calls[0];
      const loggedContext = logCall[2];
      
      expect(loggedContext.userId).toBe('user-123');
      expect(loggedContext.password).toBe('[REDACTED]');
      expect(loggedContext.apiKey).toBe('[REDACTED]');
      expect(loggedContext.token).toBe('[REDACTED]');
    });
  });

  describe('performance logging', () => {
    test('should log operation timing', () => {
      const startTime = Date.now();
      
      logger.logTiming('test-operation', startTime);
      
      expect(consoleSpy.info).toHaveBeenCalledWith(
        expect.stringContaining('INFO'),
        expect.stringContaining('test-operation completed'),
        expect.objectContaining({
          operation: 'test-operation',
          duration_ms: expect.any(Number)
        })
      );
    });

    test('should log slow operations as warnings', () => {
      const startTime = Date.now() - 5000; // 5 seconds ago
      
      logger.logTiming('slow-operation', startTime);
      
      expect(consoleSpy.warn).toHaveBeenCalledWith(
        expect.stringContaining('WARN'),
        expect.stringContaining('slow-operation completed (SLOW)'),
        expect.objectContaining({
          operation: 'slow-operation',
          duration_ms: expect.any(Number)
        })
      );
    });
  });

  describe('request logging', () => {
    test('should log HTTP requests', () => {
      const req = {
        method: 'GET',
        path: '/api/test',
        headers: { 'user-agent': 'test-agent' },
        ip: '127.0.0.1'
      };
      
      logger.logRequest(req);
      
      expect(consoleSpy.info).toHaveBeenCalledWith(
        expect.stringContaining('INFO'),
        expect.stringContaining('HTTP Request'),
        expect.objectContaining({
          method: 'GET',
          path: '/api/test',
          userAgent: 'test-agent',
          ip: '127.0.0.1'
        })
      );
    });

    test('should log HTTP responses', () => {
      const req = {
        method: 'GET',
        path: '/api/test'
      };
      const res = {
        statusCode: 200
      };
      const duration = 150;
      
      logger.logResponse(req, res, duration);
      
      expect(consoleSpy.info).toHaveBeenCalledWith(
        expect.stringContaining('INFO'),
        expect.stringContaining('HTTP Response'),
        expect.objectContaining({
          method: 'GET',
          path: '/api/test',
          statusCode: 200,
          duration_ms: 150
        })
      );
    });
  });

  describe('error logging', () => {
    test('should log errors with full stack traces', () => {
      const error = new Error('Test error');
      error.stack = 'Error: Test error\n    at test.js:1:1';
      
      logger.logError(error, { userId: 'user-123' });
      
      expect(consoleSpy.error).toHaveBeenCalledWith(
        expect.stringContaining('ERROR'),
        expect.stringContaining('Test error'),
        expect.objectContaining({
          error: expect.objectContaining({
            message: 'Test error',
            name: 'Error',
            stack: 'Error: Test error\n    at test.js:1:1'
          }),
          userId: 'user-123'
        })
      );
    });

    test('should handle errors without stack traces', () => {
      const error = { message: 'Simple error object' };
      
      logger.logError(error);
      
      expect(consoleSpy.error).toHaveBeenCalledWith(
        expect.stringContaining('ERROR'),
        expect.stringContaining('Simple error object'),
        expect.objectContaining({
          error: expect.objectContaining({
            message: 'Simple error object'
          })
        })
      );
    });
  });

  describe('database logging', () => {
    test('should log database queries', () => {
      const query = 'SELECT * FROM users WHERE id = $1';
      const params = ['user-123'];
      const duration = 25;
      
      logger.logQuery(query, params, duration);
      
      expect(consoleSpy.debug).toHaveBeenCalledWith(
        expect.stringContaining('DEBUG'),
        expect.stringContaining('Database Query'),
        expect.objectContaining({
          query,
          params,
          duration_ms: duration
        })
      );
    });

    test('should log slow database queries as warnings', () => {
      const query = 'SELECT * FROM users';
      const params = [];
      const duration = 1500; // 1.5 seconds
      
      logger.logQuery(query, params, duration);
      
      expect(consoleSpy.warn).toHaveBeenCalledWith(
        expect.stringContaining('WARN'),
        expect.stringContaining('Slow Database Query'),
        expect.objectContaining({
          query,
          params,
          duration_ms: duration
        })
      );
    });
  });
});
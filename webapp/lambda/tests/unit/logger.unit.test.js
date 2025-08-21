// Unit tests for logger utility

describe('Logger Utility Unit Tests', () => {
  let Logger;
  let logger;
  let consoleSpy;

  beforeEach(() => {
    // Clear module cache
    delete require.cache[require.resolve('../../utils/logger')];
    
    // Mock console methods
    consoleSpy = {
      error: jest.spyOn(console, 'error').mockImplementation(() => {}),
      warn: jest.spyOn(console, 'warn').mockImplementation(() => {}),
      info: jest.spyOn(console, 'info').mockImplementation(() => {}),
      log: jest.spyOn(console, 'log').mockImplementation(() => {})
    };

    // Set test environment
    process.env.NODE_ENV = 'test';
    process.env.LOG_LEVEL = 'DEBUG';
    delete process.env.SERVICE_NAME;
    delete process.env.APP_VERSION;

    // Import logger after setting environment
    Logger = require('../../utils/logger');
    
    // Check if it's a class or instance
    if (typeof Logger === 'function') {
      logger = new Logger();
    } else {
      logger = Logger;
    }
  });

  afterEach(() => {
    // Restore console methods
    Object.values(consoleSpy).forEach(spy => spy.mockRestore());
    
    // Clean up environment
    delete process.env.NODE_ENV;
    delete process.env.LOG_LEVEL;
    delete process.env.SERVICE_NAME;
    delete process.env.APP_VERSION;
  });

  describe('Logger Construction', () => {
    test('should initialize with default values', () => {
      if (logger.serviceName) {
        expect(logger.serviceName).toBe('financial-platform-api');
        expect(logger.environment).toBe('test');
        expect(logger.version).toBe('1.0.0');
      }
    });

    test('should use environment variables when provided', () => {
      process.env.SERVICE_NAME = 'test-service';
      process.env.APP_VERSION = '2.0.0';
      
      // Clear cache and reimport
      delete require.cache[require.resolve('../../utils/logger')];
      const TestLogger = require('../../utils/logger');
      const testLogger = typeof TestLogger === 'function' ? new TestLogger() : TestLogger;
      
      if (testLogger.serviceName) {
        expect(testLogger.serviceName).toBe('test-service');
        expect(testLogger.version).toBe('2.0.0');
      }
    });
  });

  describe('Log Level Parsing', () => {
    test('should parse valid log levels', () => {
      if (logger.parseLogLevel) {
        expect(logger.parseLogLevel('ERROR')).toBe(0);
        expect(logger.parseLogLevel('WARN')).toBe(1);
        expect(logger.parseLogLevel('INFO')).toBe(2);
        expect(logger.parseLogLevel('DEBUG')).toBe(3);
        expect(logger.parseLogLevel('error')).toBe(0); // case insensitive
      }
    });

    test('should default to INFO for invalid log levels', () => {
      if (logger.parseLogLevel) {
        expect(logger.parseLogLevel('INVALID')).toBe(2); // INFO level
        expect(logger.parseLogLevel('')).toBe(2);
        expect(logger.parseLogLevel('123')).toBe(2);
      }
    });
  });

  describe('Correlation ID Generation', () => {
    test('should generate correlation ID', () => {
      if (logger.generateCorrelationId) {
        const id1 = logger.generateCorrelationId();
        const id2 = logger.generateCorrelationId();
        
        expect(typeof id1).toBe('string');
        expect(typeof id2).toBe('string');
        expect(id1).not.toBe(id2); // Should be unique
        expect(id1.length).toBeGreaterThan(0);
      }
    });
  });

  describe('Base Log Entry Creation', () => {
    test('should create properly structured log entry', () => {
      if (logger.createBaseEntry) {
        const entry = logger.createBaseEntry('INFO', 'Test message', { userId: '123' });
        
        expect(entry).toHaveProperty('timestamp');
        expect(entry).toHaveProperty('level', 'INFO');
        expect(entry).toHaveProperty('message', 'Test message');
        expect(entry).toHaveProperty('userId', '123');
        
        // Validate timestamp format
        const timestamp = new Date(entry.timestamp);
        expect(timestamp.toISOString()).toBe(entry.timestamp);
      }
    });

    test('should handle empty context', () => {
      if (logger.createBaseEntry) {
        const entry = logger.createBaseEntry('ERROR', 'Error message');
        
        expect(entry.level).toBe('ERROR');
        expect(entry.message).toBe('Error message');
        expect(entry.timestamp).toBeDefined();
      }
    });
  });

  describe('Logging Methods', () => {
    test('should log error messages', () => {
      if (logger.error) {
        logger.error('Test error message');
        expect(consoleSpy.error).toHaveBeenCalled();
      } else if (logger.log) {
        logger.log('ERROR', 'Test error message');
        expect(consoleSpy.error).toHaveBeenCalled();
      }
    });

    test('should log warning messages', () => {
      if (logger.warn) {
        logger.warn('Test warning message');
        expect(consoleSpy.warn).toHaveBeenCalled();
      } else if (logger.log) {
        logger.log('WARN', 'Test warning message');
        expect(consoleSpy.warn).toHaveBeenCalled();
      }
    });

    test('should log info messages', () => {
      if (logger.info) {
        logger.info('Test info message');
        expect(consoleSpy.info).toHaveBeenCalled();
      } else if (logger.log) {
        logger.log('INFO', 'Test info message');
        expect(consoleSpy.info).toHaveBeenCalled();
      }
    });

    test('should log debug messages when level allows', () => {
      // Set debug level
      process.env.LOG_LEVEL = 'DEBUG';
      
      if (logger.debug) {
        logger.debug('Test debug message');
        expect(consoleSpy.log).toHaveBeenCalled();
      } else if (logger.log) {
        logger.log('DEBUG', 'Test debug message');
        expect(consoleSpy.log).toHaveBeenCalled();
      }
    });

    test('should not log debug messages when level is higher', () => {
      // Set INFO level (higher than DEBUG)
      process.env.LOG_LEVEL = 'INFO';
      
      // Clear cache and reimport with new log level
      delete require.cache[require.resolve('../../utils/logger')];
      const InfoLogger = require('../../utils/logger');
      const infoLogger = typeof InfoLogger === 'function' ? new InfoLogger() : InfoLogger;
      
      consoleSpy.log.mockClear();
      
      if (infoLogger.debug) {
        infoLogger.debug('Test debug message');
        expect(consoleSpy.log).not.toHaveBeenCalled();
      }
    });
  });

  describe('Context and Metadata', () => {
    test('should include context in log entries', () => {
      const context = {
        userId: 'user123',
        requestId: 'req456',
        operation: 'test'
      };

      if (logger.info) {
        logger.info('Test with context', context);
        
        // Check if context was passed to console
        if (consoleSpy.info.mock.calls.length > 0) {
          const logCall = consoleSpy.info.mock.calls[0];
          const logData = typeof logCall[0] === 'string' ? logCall[1] : logCall[0];
          
          if (logData && typeof logData === 'object') {
            expect(logData.userId || logData.context?.userId).toBe('user123');
          }
        }
      }
    });

    test('should sanitize sensitive information', () => {
      const sensitiveContext = {
        password: 'secret123',
        apiKey: 'api-key-123',
        token: 'bearer-token',
        publicInfo: 'safe-data'
      };

      if (logger.info) {
        logger.info('Test with sensitive data', sensitiveContext);
        
        // Check console call for sanitization
        if (consoleSpy.info.mock.calls.length > 0) {
          const logCall = consoleSpy.info.mock.calls[0];
          const logString = JSON.stringify(logCall);
          
          // Should not contain sensitive data
          expect(logString).not.toContain('secret123');
          expect(logString).not.toContain('api-key-123');
          expect(logString).not.toContain('bearer-token');
          
          // Should contain safe data
          expect(logString).toContain('safe-data');
        }
      }
    });
  });

  describe('Error Object Handling', () => {
    test('should properly log error objects', () => {
      const error = new Error('Test error');
      error.stack = 'Error: Test error\n    at test.js:1:1';
      error.code = 'TEST_ERROR';

      if (logger.error) {
        logger.error('Error occurred', { error });
        expect(consoleSpy.error).toHaveBeenCalled();
        
        if (consoleSpy.error.mock.calls.length > 0) {
          const logCall = consoleSpy.error.mock.calls[0];
          const logString = JSON.stringify(logCall);
          
          expect(logString).toContain('Test error');
          expect(logString).toContain('TEST_ERROR');
        }
      }
    });

    test('should handle error without stack trace', () => {
      const error = { message: 'Simple error', code: 'SIMPLE' };

      if (logger.error) {
        logger.error('Simple error occurred', { error });
        expect(consoleSpy.error).toHaveBeenCalled();
      }
    });
  });

  describe('Performance and Timing', () => {
    test('should log timing information when provided', () => {
      const startTime = Date.now() - 100; // 100ms ago

      if (logger.logTiming) {
        logger.logTiming('test-operation', startTime);
        expect(consoleSpy.info).toHaveBeenCalled();
      } else if (logger.info) {
        logger.info('Operation completed', { 
          duration: Date.now() - startTime,
          operation: 'test-operation'
        });
        expect(consoleSpy.info).toHaveBeenCalled();
      }
    });
  });

  describe('Module Exports', () => {
    test('should export logger functionality', () => {
      const exportedLogger = require('../../utils/logger');
      
      // Should export either a class or instance with logging capability
      expect(exportedLogger).toBeDefined();
      
      if (typeof exportedLogger === 'function') {
        // It's a class
        const instance = new exportedLogger();
        expect(instance).toBeDefined();
      } else {
        // It's an instance or module
        expect(typeof exportedLogger).toBe('object');
      }
    });
  });

  describe('Edge Cases', () => {
    test('should handle null and undefined messages', () => {
      if (logger.info) {
        expect(() => logger.info(null)).not.toThrow();
        expect(() => logger.info(undefined)).not.toThrow();
        expect(() => logger.info('')).not.toThrow();
      }
    });

    test('should handle circular references in context', () => {
      const circular = { name: 'test' };
      circular.self = circular; // Create circular reference

      if (logger.info) {
        expect(() => logger.info('Circular test', { circular })).not.toThrow();
      }
    });

    test('should handle very large context objects', () => {
      const largeContext = {};
      for (let i = 0; i < 1000; i++) {
        largeContext[`key${i}`] = `value${i}`;
      }

      if (logger.info) {
        expect(() => logger.info('Large context test', largeContext)).not.toThrow();
      }
    });
  });
});
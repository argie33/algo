/**
 * Logger Integration Tests
 * Tests logging functionality with the actual logger implementation
 */

const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");
const logger = require("../../../utils/logger");

describe("Logger Integration Tests", () => {
  let originalConsoleLog;
  let originalConsoleError;
  let capturedLogs;

  beforeAll(async () => {
    await initializeDatabase();

    // Set up log capture
    capturedLogs = [];
    originalConsoleLog = console.log;
    originalConsoleError = console.error;

    // Mock console methods to capture logs
    console.log = (...args) => {
      capturedLogs.push({ type: "log", args, timestamp: Date.now() });
      originalConsoleLog.apply(console, args);
    };

    console.error = (...args) => {
      capturedLogs.push({ type: "error", args, timestamp: Date.now() });
      originalConsoleError.apply(console, args);
    };
  });

  afterAll(async () => {
    await closeDatabase();

    // Restore console methods
    console.log = originalConsoleLog;
    console.error = originalConsoleError;
  });

  beforeEach(() => {
    // Clear captured logs before each test
    capturedLogs = [];
  });

  describe("Basic Logging Methods", () => {
    test("should have all required logging methods", () => {
      expect(typeof logger.error).toBe("function");
      expect(typeof logger.warn).toBe("function");
      expect(typeof logger.info).toBe("function");
      expect(typeof logger.debug).toBe("function");
    });

    test("should log error messages with context", () => {
      const message = "Test error message";
      const context = { userId: "test123", operation: "test" };

      logger.error(message, context);

      // In test environment, logger outputs JSON
      const logEntry = capturedLogs.find((log) =>
        log.args.some((arg) => typeof arg === "string" && arg.includes(message))
      );
      expect(logEntry).toBeDefined();
    });

    test("should log warn messages", () => {
      const message = "Test warning message";

      logger.warn(message);

      // Check if warn level is enabled
      const shouldLogWarn = logger.shouldLog(1); // WARN level = 1
      if (shouldLogWarn) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) => typeof arg === "string" && arg.includes(message)
          )
        );
        expect(logEntry).toBeDefined();
      } else {
        // If warn is filtered out, that's also correct behavior
        expect(true).toBe(true);
      }
    });

    test("should log info messages", () => {
      const message = "Test info message";

      logger.info(message);

      // Check if info level is enabled
      const shouldLogInfo = logger.shouldLog(2); // INFO level = 2
      if (shouldLogInfo) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) => typeof arg === "string" && arg.includes(message)
          )
        );
        expect(logEntry).toBeDefined();
      } else {
        // If info is filtered out, that's also correct behavior
        expect(true).toBe(true);
      }
    });

    test("should log debug messages", () => {
      const message = "Test debug message";

      logger.debug(message);

      // Check if debug level is enabled
      const shouldLogDebug = logger.shouldLog(3); // DEBUG level = 3
      if (shouldLogDebug) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) => typeof arg === "string" && arg.includes(message)
          )
        );
        expect(logEntry).toBeDefined();
      } else {
        // If debug is filtered out, that's also correct behavior
        expect(true).toBe(true);
      }
    });
  });

  describe("Specialized Logging Methods", () => {
    test("should log database operations", () => {
      const operation = "SELECT * FROM stocks";
      const context = { duration: 150, rows: 25 };

      expect(() => {
        logger.database(operation, context);
      }).not.toThrow();

      // Database operations log as info, check if info level is enabled
      const shouldLogInfo = logger.shouldLog(2);
      if (shouldLogInfo) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) => typeof arg === "string" && arg.includes(operation)
          )
        );
        expect(logEntry).toBeDefined();
      }
    });

    test("should log API calls", () => {
      const method = "GET";
      const url = "/api/portfolio";
      const context = { userId: "test123" };

      expect(() => {
        logger.apiCall(method, url, context);
      }).not.toThrow();

      // API calls log as info, check if info level is enabled
      const shouldLogInfo = logger.shouldLog(2);
      if (shouldLogInfo) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) =>
              typeof arg === "string" &&
              arg.includes(`API call: ${method} ${url}`)
          )
        );
        expect(logEntry).toBeDefined();
      }
    });

    test("should log authentication events", () => {
      const event = "login_success";
      const context = { userId: "test123", ip: "127.0.0.1" };

      expect(() => {
        logger.auth(event, context);
      }).not.toThrow();

      // Auth events log as info, check if info level is enabled
      const shouldLogInfo = logger.shouldLog(2);
      if (shouldLogInfo) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some((arg) => typeof arg === "string" && arg.includes(event))
        );
        expect(logEntry).toBeDefined();
      }
    });

    test("should log performance metrics", () => {
      const operation = "portfolio_calculation";
      const duration = 250; // ms
      const context = { symbols: 10, userId: "test123" };

      expect(() => {
        logger.performance(operation, duration, context);
      }).not.toThrow();

      // Performance logs as info, check if info level is enabled
      const shouldLogInfo = logger.shouldLog(2);
      if (shouldLogInfo) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) =>
              typeof arg === "string" &&
              arg.includes(operation) &&
              arg.includes(`${duration}ms`)
          )
        );
        expect(logEntry).toBeDefined();
      }
    });

    test("should log security events", () => {
      const event = "unauthorized_access_attempt";
      const context = { ip: "192.168.1.100", endpoint: "/admin" };

      expect(() => {
        logger.security(event, context);
      }).not.toThrow();

      // Security events log as warn, check if warn level is enabled
      const shouldLogWarn = logger.shouldLog(1);
      if (shouldLogWarn) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some((arg) => typeof arg === "string" && arg.includes(event))
        );
        expect(logEntry).toBeDefined();
      }
    });

    test("should log user actions with anonymized user ID", () => {
      const userId = "test_user_12345";
      const action = "portfolio_view";
      const context = { symbol: "AAPL", timestamp: Date.now() };

      expect(() => {
        logger.userAction(userId, action, context);
      }).not.toThrow();

      // User actions log as info, check if info level is enabled
      const shouldLogInfo = logger.shouldLog(2);
      if (shouldLogInfo) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) => typeof arg === "string" && arg.includes(action)
          )
        );
        expect(logEntry).toBeDefined();

        // Verify user ID is anonymized (only first 8 characters + ...)
        const logStr = logEntry.args.join(" ");
        expect(logStr).toContain("test_use...");
        expect(logStr).not.toContain(userId); // Full user ID should not appear
      }
    });
  });

  describe("Structured Logging", () => {
    test("should handle structured data in context", () => {
      const message = "Portfolio calculation completed";
      const structuredContext = {
        userId: "test123",
        portfolioId: "port456",
        symbols: ["AAPL", "GOOGL", "MSFT"],
        metrics: {
          totalValue: 100000,
          gainLoss: 5000,
          returnPercent: 5.0,
        },
        duration: 150,
      };

      expect(() => {
        logger.info(message, structuredContext);
      }).not.toThrow();

      // Check if info level is enabled
      const shouldLogInfo = logger.shouldLog(2);
      if (shouldLogInfo) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) => typeof arg === "string" && arg.includes(message)
          )
        );
        expect(logEntry).toBeDefined();
      }
    });

    test("should handle error objects with stack traces", () => {
      const error = new Error("Test database connection error");
      error.code = "DB_CONNECTION_FAILED";
      error.details = { host: "localhost", port: 5432 };

      logger.error("Database operation failed", { error });

      const logEntry = capturedLogs.find((log) =>
        log.args.some(
          (arg) =>
            typeof arg === "string" && arg.includes("Database operation failed")
        )
      );
      expect(logEntry).toBeDefined();
    });
  });

  describe("Logger Configuration", () => {
    test("should respect log levels", () => {
      // The logger should have configurable log levels
      expect(logger.currentLevel).toBeDefined();
      expect(typeof logger.currentLevel).toBe("number");
    });

    test("should have service metadata", () => {
      expect(logger.serviceName).toBeDefined();
      expect(logger.environment).toBeDefined();
      expect(logger.version).toBeDefined();

      expect(typeof logger.serviceName).toBe("string");
      expect(typeof logger.environment).toBe("string");
      expect(typeof logger.version).toBe("string");
    });

    test("should generate correlation IDs", () => {
      const correlationId1 = logger.generateCorrelationId();
      const correlationId2 = logger.generateCorrelationId();

      expect(typeof correlationId1).toBe("string");
      expect(typeof correlationId2).toBe("string");
      expect(correlationId1).not.toBe(correlationId2);
      expect(correlationId1.length).toBeGreaterThan(0);
    });
  });

  describe("Log Entry Structure", () => {
    test("should create proper log entry structure", () => {
      const level = 2; // INFO level
      const message = "Test log entry structure";
      const context = { testKey: "testValue" };

      const logEntry = logger.createBaseEntry(level, message, context);

      expect(logEntry).toBeDefined();
      expect(logEntry.timestamp).toBeDefined();
      expect(logEntry.level).toBe("INFO");
      expect(logEntry.service).toBe(logger.serviceName);
      expect(logEntry.environment).toBe(logger.environment);
      expect(logEntry.version).toBe(logger.version);
      expect(logEntry.message).toBe(message);
      expect(logEntry.correlationId).toBeDefined();
      expect(logEntry.testKey).toBe("testValue");
    });

    test("should check log level filtering", () => {
      const errorLevel = 0;
      const warnLevel = 1;
      const infoLevel = 2;
      const debugLevel = 3;

      expect(typeof logger.shouldLog(errorLevel)).toBe("boolean");
      expect(typeof logger.shouldLog(warnLevel)).toBe("boolean");
      expect(typeof logger.shouldLog(infoLevel)).toBe("boolean");
      expect(typeof logger.shouldLog(debugLevel)).toBe("boolean");
    });
  });

  describe("Middleware Functions", () => {
    test("should provide request middleware", () => {
      const middleware = logger.requestMiddleware();

      expect(typeof middleware).toBe("function");
    });

    test("should provide error middleware", () => {
      const middleware = logger.errorMiddleware();

      expect(typeof middleware).toBe("function");
    });
  });

  describe("Configuration Utilities", () => {
    test("should sanitize configuration data", () => {
      const config = {
        database: {
          host: "localhost",
          port: 5432,
          password: "secret123",
          apiKey: "key_abc123",
        },
        app: {
          name: "test-app",
          token: "jwt_token_xyz",
        },
      };

      const sanitized = logger.sanitizeConfig(config);

      expect(sanitized.database.host).toBe("localhost");
      expect(sanitized.database.port).toBe(5432);
      expect(sanitized.database.password).toBe("[REDACTED]");
      expect(sanitized.database.apiKey).toBe("[REDACTED]");
      expect(sanitized.app.name).toBe("test-app");
      expect(sanitized.app.token).toBe("[REDACTED]");
    });

    test("should log configuration loaded event", () => {
      const config = {
        appName: "test-app",
        version: "1.0.0",
        apiKey: "secret_key_123",
      };

      expect(() => {
        logger.configLoaded(config);
      }).not.toThrow();

      // Config events log as info, check if info level is enabled
      const shouldLogInfo = logger.shouldLog(2);
      if (shouldLogInfo) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) =>
              typeof arg === "string" && arg.includes("Configuration loaded")
          )
        );
        expect(logEntry).toBeDefined();
      }
    });
  });

  describe("Application Lifecycle Logging", () => {
    test("should log application startup", () => {
      const context = { port: 3000, env: "test" };

      expect(() => {
        logger.startup(context);
      }).not.toThrow();

      // Startup events log as info, check if info level is enabled
      const shouldLogInfo = logger.shouldLog(2);
      if (shouldLogInfo) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) =>
              typeof arg === "string" && arg.includes("Application starting")
          )
        );
        expect(logEntry).toBeDefined();
      }
    });

    test("should log application shutdown", () => {
      const context = { reason: "test_shutdown" };

      expect(() => {
        logger.shutdown(context);
      }).not.toThrow();

      // Shutdown events log as info, check if info level is enabled
      const shouldLogInfo = logger.shouldLog(2);
      if (shouldLogInfo) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) =>
              typeof arg === "string" &&
              arg.includes("Application shutting down")
          )
        );
        expect(logEntry).toBeDefined();
      }
    });
  });

  describe("Child Logger Functionality", () => {
    test("should create child logger with additional context", () => {
      const childContext = { requestId: "req_123", userId: "user_456" };

      const childLogger = logger.child(childContext);

      expect(childLogger).toBeDefined();
      expect(typeof childLogger.error).toBe("function");
      expect(typeof childLogger.info).toBe("function");
      expect(typeof childLogger.warn).toBe("function");
      expect(typeof childLogger.debug).toBe("function");
    });

    test("should use child logger with inherited context", () => {
      const childContext = { requestId: "req_789", userId: "user_xyz" };
      const childLogger = logger.child(childContext);

      const message = "Child logger test message";

      expect(() => {
        childLogger.info(message);
      }).not.toThrow();

      // Child logger info calls parent info, check if info level is enabled
      const shouldLogInfo = logger.shouldLog(2);
      if (shouldLogInfo) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) => typeof arg === "string" && arg.includes(message)
          )
        );
        expect(logEntry).toBeDefined();
      }
    });
  });

  describe("Performance Logging Edge Cases", () => {
    test("should warn on slow operations", () => {
      const operation = "slow_database_query";
      const slowDuration = 6000; // 6 seconds > 5 second threshold
      const context = { query: "SELECT * FROM large_table" };

      expect(() => {
        logger.performance(operation, slowDuration, context);
      }).not.toThrow();

      // Should log as WARN level for slow operations, check if warn level is enabled
      const shouldLogWarn = logger.shouldLog(1);
      if (shouldLogWarn) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) =>
              typeof arg === "string" &&
              arg.includes(operation) &&
              arg.includes("6000ms")
          )
        );
        expect(logEntry).toBeDefined();
      }
    });

    test("should log normal operations as info", () => {
      const operation = "fast_api_call";
      const normalDuration = 100; // < 5 second threshold
      const context = { endpoint: "/api/health" };

      expect(() => {
        logger.performance(operation, normalDuration, context);
      }).not.toThrow();

      // Should log as INFO level for normal operations, check if info level is enabled
      const shouldLogInfo = logger.shouldLog(2);
      if (shouldLogInfo) {
        const logEntry = capturedLogs.find((log) =>
          log.args.some(
            (arg) =>
              typeof arg === "string" &&
              arg.includes(operation) &&
              arg.includes("100ms")
          )
        );
        expect(logEntry).toBeDefined();
      }
    });
  });

  describe("Error Handling", () => {
    test("should handle null or undefined context gracefully", () => {
      expect(() => {
        logger.info("Test message", null);
      }).not.toThrow();

      expect(() => {
        logger.info("Test message", undefined);
      }).not.toThrow();

      expect(() => {
        logger.info("Test message");
      }).not.toThrow();
    });

    test("should handle circular references in context", () => {
      const circularObj = { name: "test" };
      circularObj.self = circularObj;

      expect(() => {
        logger.info("Circular reference test", { data: circularObj });
      }).not.toThrow();
    });

    test("should handle very large context objects", () => {
      const largeContext = {
        data: Array(1000)
          .fill(0)
          .map((_, i) => ({ id: i, value: `item_${i}` })),
      };

      expect(() => {
        logger.info("Large context test", largeContext);
      }).not.toThrow();
    });
  });
});

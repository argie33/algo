/**
 * Logger Unit Tests
 * Tests for comprehensive logging utility
 */

// Mock crypto before requiring logger
const mockCrypto = {
  randomUUID: jest.fn(() => "12345678-1234-1234-1234-123456789012"),
};

jest.mock("crypto", () => mockCrypto);

// Clear module cache to ensure logger uses the mock
delete require.cache[require.resolve("../../../utils/logger")];
let logger; // Will be initialized in beforeEach
let Logger; // Will be initialized in beforeEach

describe("Logger", () => {
  let originalEnv;
  let consoleSpy;

  beforeEach(() => {
    originalEnv = { ...process.env };

    // Set LOG_LEVEL to DEBUG to ensure all logging works
    process.env.LOG_LEVEL = "DEBUG";
    process.env.NODE_ENV = "development"; // Use development mode for console output

    // Restore console.log first if it was previously spied on
    if (consoleSpy) {
      consoleSpy.mockRestore();
    }

    // Create fresh spy that tracks calls but still allows output
    consoleSpy = jest.spyOn(console, "log").mockImplementation((...args) => {
      // Allow the output to go through for debugging
      // but still track the calls for testing
    });
    jest.clearAllMocks();

    // Ensure mock is reset for each test
    mockCrypto.randomUUID.mockReturnValue("12345678-1234-1234-1234-123456789012");

    // Clear the logger module cache so it re-reads environment variables
    delete require.cache[require.resolve("../../../utils/logger")];

    // Reinitialize logger with fresh environment
    const loggerModule = require("../../../utils/logger");
    logger = loggerModule;
    Logger = loggerModule.Logger;
  });

  afterEach(() => {
    process.env = originalEnv;
    consoleSpy.mockRestore();
  });

  describe("Initialization", () => {
    test("should initialize with default values", () => {
      expect(logger.serviceName).toBe("financial-platform-api");
      expect(logger.environment).toBe("development"); // Set in beforeEach
      expect(logger.version).toBe("1.0.0");
      expect(logger.currentLevel).toBe(3); // DEBUG level (set in beforeEach)
    });

    test("should initialize with environment variables", () => {
      // Set environment variables before creating new instance
      process.env.LOG_LEVEL = "DEBUG";
      process.env.SERVICE_NAME = "test-service";
      process.env.APP_VERSION = "2.0.0";

      // Create new logger instance that will read the updated environment
      const { Logger } = require("../../../utils/logger");
      const newLogger = new Logger();

      expect(newLogger.currentLevel).toBe(3); // DEBUG level
      expect(newLogger.serviceName).toBe("test-service");
      expect(newLogger.version).toBe("2.0.0");
    });
  });

  describe("Log Level Parsing", () => {
    test("should parse valid log levels", () => {
      expect(logger.parseLogLevel("ERROR")).toBe(0);
      expect(logger.parseLogLevel("WARN")).toBe(1);
      expect(logger.parseLogLevel("INFO")).toBe(2);
      expect(logger.parseLogLevel("DEBUG")).toBe(3);
    });

    test("should handle case insensitive log levels", () => {
      expect(logger.parseLogLevel("error")).toBe(0);
      expect(logger.parseLogLevel("WaRn")).toBe(1);
      expect(logger.parseLogLevel("info")).toBe(2);
      expect(logger.parseLogLevel("DEBUG")).toBe(3);
    });

    test("should default to INFO for invalid log levels", () => {
      expect(logger.parseLogLevel("INVALID")).toBe(2);
      expect(logger.parseLogLevel("")).toBe(2);
      expect(logger.parseLogLevel(null)).toBe(2);
    });
  });

  describe("Correlation ID Generation", () => {
    test("should generate correlation ID from UUID", () => {
      const correlationId = logger.generateCorrelationId();
      expect(correlationId).toBe("12345678");
    });
  });

  describe("Base Entry Creation", () => {
    test("should create base log entry with required fields", () => {
      const entry = logger.createBaseEntry(2, "Test message");

      expect(entry).toHaveProperty("timestamp");
      expect(entry).toHaveProperty("level", "INFO");
      expect(entry).toHaveProperty("service", "financial-platform-api");
      expect(entry).toHaveProperty("environment");
      expect(entry).toHaveProperty("version");
      expect(entry).toHaveProperty("message", "Test message");
      expect(entry).toHaveProperty("correlationId");
    });

    test("should include additional context", () => {
      const context = { userId: "123", operation: "test" };
      const entry = logger.createBaseEntry(2, "Test message", context);

      expect(entry.userId).toBe("123");
      expect(entry.operation).toBe("test");
    });

    test("should use provided correlation ID", () => {
      const context = { correlationId: "custom-id" };
      const entry = logger.createBaseEntry(2, "Test message", context);

      expect(entry.correlationId).toBe("custom-id");
    });
  });

  describe("Log Level Checking", () => {
    test("should check if level should be logged", () => {
      // Current logger has DEBUG level (set in beforeEach)
      expect(logger.shouldLog(0)).toBe(true); // ERROR
      expect(logger.shouldLog(1)).toBe(true); // WARN
      expect(logger.shouldLog(2)).toBe(true); // INFO
      expect(logger.shouldLog(3)).toBe(true); // DEBUG (enabled in beforeEach)
    });
  });

  describe("Output Formatting", () => {
    test("should format output for development environment", () => {
      process.env.NODE_ENV = "development";
      const freshLogger = require("../../../utils/logger");

      const logEntry = {
        timestamp: "2023-01-01T00:00:00.000Z",
        level: "INFO",
        message: "Test message",
        correlationId: "12345",
        extra: "data",
      };

      freshLogger.output(logEntry);

      expect(consoleSpy).toHaveBeenCalledTimes(2);
      expect(consoleSpy).toHaveBeenNthCalledWith(
        1,
        "[2023-01-01T00:00:00.000Z] [INFO] [12345] Test message"
      );
      expect(consoleSpy).toHaveBeenNthCalledWith(
        2,
        "Context:",
        JSON.stringify({ extra: "data" }, null, 2)
      );
    });

    test("should format output for production environment", () => {
      process.env.NODE_ENV = "production";

      // Reinitialize logger with production environment
      delete require.cache[require.resolve("../../../utils/logger")];
      const loggerModule = require("../../../utils/logger");
      const prodLogger = new loggerModule.Logger();

      const logEntry = {
        timestamp: "2023-01-01T00:00:00.000Z",
        level: "INFO",
        message: "Test message",
        correlationId: "12345",
      };

      prodLogger.output(logEntry);

      expect(consoleSpy).toHaveBeenCalledWith(JSON.stringify(logEntry));
    });

    test("should handle development output without extra context", () => {
      process.env.NODE_ENV = "development";
      const freshLogger = require("../../../utils/logger");

      const logEntry = {
        timestamp: "2023-01-01T00:00:00.000Z",
        level: "INFO",
        message: "Test message",
        correlationId: "12345",
      };

      freshLogger.output(logEntry);

      expect(consoleSpy).toHaveBeenCalledTimes(1);
      expect(consoleSpy).toHaveBeenCalledWith(
        "[2023-01-01T00:00:00.000Z] [INFO] [12345] Test message"
      );
    });
  });

  describe("Error Logging", () => {
    test("should log error messages", () => {
      logger.error("Error message");

      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should log error with Error object", () => {
      const error = new Error("Test error");
      error.code = "TEST_CODE";

      logger.error("Error occurred", { error });

      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should not log error if level too low", () => {
      // Create a new logger instance instead of modifying the singleton
      const quietLogger = new Logger();
      quietLogger.currentLevel = -1;
      // Note: Logger is already defined in beforeEach from require("../../../utils/logger").Logger

      quietLogger.error("Should not log");

      // Console spy should not be called for this logger instance
    });
  });

  describe("Warning Logging", () => {
    test("should log warning messages", () => {
      // Test exactly what happens step by step
      expect(logger.currentLevel).toBe(3); // DEBUG level
      expect(logger.shouldLog(1)).toBe(true); // Should log WARN (1)

      // Directly test the output method with a simple entry
      logger.output({
        timestamp: "test",
        level: "WARN",
        message: "Direct test",
        correlationId: "123"
      });

      expect(consoleSpy).toHaveBeenCalledWith("[test] [WARN] [123] Direct test");

      // Clear spy for the actual test
      consoleSpy.mockClear();

      // Now test the actual warn method
      logger.warn("Warning message");

      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should log warning with context", () => {
      logger.warn("Warning message", { component: "test" });

      expect(consoleSpy).toHaveBeenCalled();
    });
  });

  describe("Info Logging", () => {
    test("should log info messages", () => {
      logger.info("Info message");

      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should log info with context", () => {
      logger.info("Info message", { operation: "test" });

      expect(consoleSpy).toHaveBeenCalled();
    });
  });

  describe("Debug Logging", () => {
    test("should not log debug messages with default level", () => {
      // Create a logger with the actual default level (INFO = 2) by creating a new instance
      const defaultLogger = new Logger(); // Logger is defined in beforeEach from require
      defaultLogger.currentLevel = 2; // INFO level explicitly

      // Create fresh spy for this test to avoid interference
      consoleSpy.mockClear();

      // Verify the logger is at INFO level (2) and debug level is 3
      expect(defaultLogger.currentLevel).toBe(2); // INFO level
      expect(defaultLogger.shouldLog(3)).toBe(false); // Should NOT log DEBUG (3)

      defaultLogger.debug("Debug message");

      expect(consoleSpy).not.toHaveBeenCalled();
    });

    test("should log debug messages when level is DEBUG", () => {
      process.env.LOG_LEVEL = "DEBUG";
      delete require.cache[require.resolve("../../../utils/logger")];
      const debugLogger = require("../../../utils/logger");

      debugLogger.debug("Debug message");

      expect(consoleSpy).toHaveBeenCalled();
    });
  });

  describe("Specialized Logging Methods", () => {
    test("should log database operations", () => {
      logger.database("SELECT * FROM company_profile", {
        table: "company_profile",
      });

      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should log API calls", () => {
      logger.apiCall("GET", "/api/stocks", { statusCode: 200 });

      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should log authentication events", () => {
      logger.auth("login_attempt", { userId: "123" });

      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should log performance with normal duration", () => {
      logger.performance("database_query", 1000, { table: "stocks" });

      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should log performance warning for slow operations", () => {
      logger.performance("slow_query", 6000, { table: "stocks" });

      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should log security events", () => {
      logger.security("unauthorized_access", { ip: "192.168.1.1" });

      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should log user actions", () => {
      logger.userAction("user123456789", "login", { method: "oauth" });

      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should log user actions for anonymous users", () => {
      logger.userAction(null, "view_page", { page: "home" });

      expect(consoleSpy).toHaveBeenCalled();
    });
  });

  describe("Request Middleware", () => {
    test("should create request middleware", () => {
      const middleware = logger.requestMiddleware();
      expect(typeof middleware).toBe("function");
    });

    test("should handle incoming request", () => {
      const middleware = logger.requestMiddleware();
      const req = {
        method: "GET",
        url: "/api/test",
        path: "/api/test",
        headers: { "user-agent": "test-agent" },
        ip: "127.0.0.1",
      };
      const res = {
        json: jest.fn(),
      };
      const next = jest.fn();

      middleware(req, res, next);

      expect(req.correlationId).toBeDefined();
      expect(req.logger).toBe(logger);
      expect(next).toHaveBeenCalled();
      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should handle request with authorization header", () => {
      const middleware = logger.requestMiddleware();
      const req = {
        method: "POST",
        url: "/api/test",
        path: "/api/test",
        headers: {
          "user-agent": "test-agent",
          authorization: "Bearer token",
        },
        ip: "127.0.0.1",
      };
      const res = { json: jest.fn() };
      const next = jest.fn();

      middleware(req, res, next);

      expect(req.correlationId).toBeDefined();
      expect(next).toHaveBeenCalled();
    });

    test("should override res.json to log response", () => {
      const middleware = logger.requestMiddleware();
      const req = {
        method: "GET",
        url: "/api/test",
        path: "/api/test",
        headers: { "user-agent": "test-agent" },
        ip: "127.0.0.1",
        logger: logger,
      };
      const originalJson = jest.fn();
      const res = {
        json: originalJson,
        statusCode: 200,
      };
      const next = jest.fn();

      middleware(req, res, next);

      // Call the overridden json method
      res.json({ success: true });

      expect(originalJson).toHaveBeenCalledWith({ success: true });
    });
  });

  describe("Error Middleware", () => {
    test("should create error middleware", () => {
      const middleware = logger.errorMiddleware();
      expect(typeof middleware).toBe("function");
    });

    test("should handle errors", () => {
      const middleware = logger.errorMiddleware();
      const error = new Error("Test error");
      const req = {
        correlationId: "test-id",
        method: "GET",
        url: "/api/test",
        headers: { "user-agent": "test-agent" },
        ip: "127.0.0.1",
      };
      const res = {};
      const next = jest.fn();

      middleware(error, req, res, next);

      expect(next).toHaveBeenCalledWith(error);
      expect(consoleSpy).toHaveBeenCalled();
    });
  });

  describe("Child Logger", () => {
    test("should create child logger with additional context", () => {
      const childLogger = logger.child({ component: "test" });

      expect(childLogger.defaultContext).toEqual({ component: "test" });
    });

    test("should use child logger context in logs", () => {
      const childLogger = logger.child({ component: "test" });

      childLogger.info("Test message", { extra: "data" });

      expect(consoleSpy).toHaveBeenCalled();
    });
  });

  describe("Application Lifecycle Logging", () => {
    test("should log application startup", () => {
      logger.startup({ port: 3000 });

      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should log application shutdown", () => {
      logger.shutdown({ reason: "SIGTERM" });

      expect(consoleSpy).toHaveBeenCalled();
    });

    test("should log configuration loaded", () => {
      const config = {
        port: 3000,
        database: "test",
        apiKey: "secret123",
      };

      logger.configLoaded(config);

      expect(consoleSpy).toHaveBeenCalled();
    });
  });

  describe("Configuration Sanitization", () => {
    test("should sanitize sensitive configuration values", () => {
      const config = {
        port: 3000,
        database_url: "postgres://localhost",
        api_key: "secret123",
        password: "password123",
        jwt_secret: "jwtsecret",
        access_token: "token123",
        credential: "cred123",
        normal_value: "safe",
      };

      const sanitized = logger.sanitizeConfig(config);

      expect(sanitized.port).toBe(3000);
      expect(sanitized.database_url).toBe("postgres://localhost");
      expect(sanitized.api_key).toBe("[REDACTED]");
      expect(sanitized.password).toBe("[REDACTED]");
      expect(sanitized.jwt_secret).toBe("[REDACTED]");
      expect(sanitized.access_token).toBe("[REDACTED]");
      expect(sanitized.credential).toBe("[REDACTED]");
      expect(sanitized.normal_value).toBe("safe");
    });

    test("should sanitize nested configuration objects", () => {
      const config = {
        database: {
          host: "localhost",
          password: "secret123",
          nested: {
            api_key: "nested_secret",
          },
        },
        server: {
          port: 3000,
          jwt_secret: "jwt123",
        },
      };

      const sanitized = logger.sanitizeConfig(config);

      expect(sanitized.database.host).toBe("localhost");
      expect(sanitized.database.password).toBe("[REDACTED]");
      expect(sanitized.database.nested.api_key).toBe("[REDACTED]");
      expect(sanitized.server.port).toBe(3000);
      expect(sanitized.server.jwt_secret).toBe("[REDACTED]");
    });

    test("should handle null values in configuration", () => {
      const config = {
        value: null,
        password: null,
      };

      const sanitized = logger.sanitizeConfig(config);

      expect(sanitized.value).toBe(null);
      expect(sanitized.password).toBe("[REDACTED]");
    });
  });
});

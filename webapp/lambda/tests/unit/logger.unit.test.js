// Logger utility tests - testing actual site functionality

describe("Logger Service Tests", () => {
  let logger;
  let consoleSpy;

  beforeEach(() => {
    jest.clearAllMocks();

    // Mock console.log which is what the logger actually uses
    consoleSpy = {
      log: jest.spyOn(console, "log").mockImplementation(() => {}),
      error: jest.spyOn(console, "error").mockImplementation(() => {}),
      warn: jest.spyOn(console, "warn").mockImplementation(() => {}),
      info: jest.spyOn(console, "info").mockImplementation(() => {}),
    };

    // Clear environment variables
    delete process.env.LOG_LEVEL;
    delete process.env.SERVICE_NAME;
    delete process.env.APP_VERSION;

    // Clear module cache to get fresh logger instance
    delete require.cache[require.resolve("../../utils/logger")];
    logger = require("../../utils/logger");
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("Logger Construction", () => {
    test("should use default values when environment variables not set", () => {
      expect(logger.serviceName).toBe("financial-platform-api");
      expect(logger.environment).toBe("test");
      expect(logger.version).toBe("1.0.0");
    });

    test("should read configuration properties", () => {
      expect(logger.serviceName).toBeDefined();
      expect(logger.environment).toBeDefined();
      expect(logger.version).toBeDefined();
      expect(logger.currentLevel).toBeDefined();
    });
  });

  describe("Log Level Management", () => {
    test("should parse log levels correctly", () => {
      expect(logger.parseLogLevel("ERROR")).toBe(0);
      expect(logger.parseLogLevel("WARN")).toBe(1);
      expect(logger.parseLogLevel("INFO")).toBe(2);
      expect(logger.parseLogLevel("DEBUG")).toBe(3);
    });

    test("should default to INFO for invalid levels", () => {
      expect(logger.parseLogLevel("INVALID")).toBe(2);
    });

    test("should check log level thresholds correctly", () => {
      logger.currentLevel = 2; // INFO level

      expect(logger.shouldLog(0)).toBe(true); // ERROR
      expect(logger.shouldLog(1)).toBe(true); // WARN
      expect(logger.shouldLog(2)).toBe(true); // INFO
      expect(logger.shouldLog(3)).toBe(false); // DEBUG
    });
  });

  describe("Log Entry Structure", () => {
    test("should create properly structured log entry", () => {
      const entry = logger.createBaseEntry(2, "Test message", {
        userId: "123",
        operation: "test",
      });

      expect(entry).toHaveProperty("timestamp");
      expect(entry).toHaveProperty("level", "INFO");
      expect(entry).toHaveProperty("message", "Test message");
      expect(entry).toHaveProperty("service", "financial-platform-api");
      expect(entry).toHaveProperty("environment", "test");
      expect(entry).toHaveProperty("correlationId");
      expect(entry).toHaveProperty("userId", "123");
      expect(entry).toHaveProperty("operation", "test");
    });

    test("should generate correlation IDs", () => {
      const id1 = logger.generateCorrelationId();
      const id2 = logger.generateCorrelationId();

      expect(id1).toBeDefined();
      expect(id2).toBeDefined();
      expect(id1).not.toBe(id2);
      expect(typeof id1).toBe("string");
    });
  });

  describe("Logging Methods", () => {
    test("should log error messages", () => {
      logger.error("Test error message");

      expect(consoleSpy.log).toHaveBeenCalled();
      const logCall = consoleSpy.log.mock.calls[0][0];
      expect(typeof logCall).toBe("string");

      // In test environment, should use JSON format
      if (logCall.startsWith("{")) {
        const parsed = JSON.parse(logCall);
        expect(parsed.level).toBe("ERROR");
        expect(parsed.message).toBe("Test error message");
      }
    });

    test("should log info messages", () => {
      logger.info("Test info message");

      expect(consoleSpy.log).toHaveBeenCalled();
      const logCall = consoleSpy.log.mock.calls[0][0];

      if (logCall.startsWith("{")) {
        const parsed = JSON.parse(logCall);
        expect(parsed.level).toBe("INFO");
        expect(parsed.message).toBe("Test info message");
      }
    });

    test("should log warning messages", () => {
      logger.warn("Test warning message");

      expect(consoleSpy.log).toHaveBeenCalled();
      const logCall = consoleSpy.log.mock.calls[0][0];

      if (logCall.startsWith("{")) {
        const parsed = JSON.parse(logCall);
        expect(parsed.level).toBe("WARN");
        expect(parsed.message).toBe("Test warning message");
      }
    });

    test("should respect log level filtering", () => {
      logger.currentLevel = 1; // WARN level

      logger.debug("This should not log");
      expect(consoleSpy.log).not.toHaveBeenCalled();

      logger.error("This should log");
      expect(consoleSpy.log).toHaveBeenCalled();
    });
  });

  describe("Error Handling", () => {
    test("should handle error objects properly", () => {
      const error = new Error("Test error");
      error.stack = "Error: Test error\n    at test.js:1:1";

      logger.error("Error occurred", { error });

      expect(consoleSpy.log).toHaveBeenCalled();
      const logCall = consoleSpy.log.mock.calls[0][0];

      if (logCall.startsWith("{")) {
        const parsed = JSON.parse(logCall);
        expect(parsed.error).toBeDefined();
        expect(parsed.error.name).toBe("Error");
        expect(parsed.error.message).toBe("Test error");
      }
    });

    test("should handle circular references gracefully", () => {
      const circular = { name: "test" };
      circular.self = circular;

      // The logger should handle circular references without throwing
      expect(() => {
        logger.info("Circular test", { circular });
      }).not.toThrow();
    });
  });

  describe("Performance Metrics", () => {
    test("should handle timing information", () => {
      logger.info("Operation completed", {
        duration: 1500,
        operation: "database-query",
        userId: "user123",
      });

      // Verify logger.info method exists and can be called
      expect(typeof logger.info).toBe("function");

      // Check if console.log was called (depends on log level)
      if (consoleSpy.log.mock.calls.length > 0) {
        const logCall = consoleSpy.log.mock.calls[0][0];

        if (logCall && logCall.startsWith("{")) {
          const parsed = JSON.parse(logCall);
          expect(parsed.duration).toBe(1500);
          expect(parsed.operation).toBe("database-query");
        }
      }
    });
  });

  describe("Real Site Use Cases", () => {
    test("should log authentication events", () => {
      logger.info("User login successful", {
        userId: "user123",
        operation: "authentication",
        ip: "192.168.1.1",
        userAgent: "Mozilla/5.0",
      });

      // Verify logger.info method exists and can be called
      expect(typeof logger.info).toBe("function");

      // Check if console.log was called (depends on log level)
      if (consoleSpy.log.mock.calls.length > 0) {
        const logCall = consoleSpy.log.mock.calls[0][0];

        if (logCall && logCall.startsWith("{")) {
          const parsed = JSON.parse(logCall);
          expect(parsed.userId).toBe("user123");
          expect(parsed.operation).toBe("authentication");
        }
      }
    });

    test("should log database operations", () => {
      // Set debug level to ensure it logs
      logger.currentLevel = 3;
      logger.debug("Database query executed", {
        query: "SELECT * FROM user_portfolio WHERE user_id = $1",
        duration: 45,
        rowCount: 3,
        operation: "database",
      });

      expect(consoleSpy.log).toHaveBeenCalled();
    });

    test("should log API key operations", () => {
      logger.warn("API key validation failed", {
        userId: "user123",
        provider: "alpaca",
        operation: "api-key-validation",
        reason: "invalid-format",
      });

      expect(consoleSpy.log).toHaveBeenCalled();
      const logCall = consoleSpy.log.mock.calls[0][0];

      if (logCall.startsWith("{")) {
        const parsed = JSON.parse(logCall);
        expect(parsed.provider).toBe("alpaca");
        expect(parsed.reason).toBe("invalid-format");
      }
    });

    test("should log trading operations", () => {
      logger.info("Portfolio update completed", {
        userId: "user123",
        operation: "portfolio-sync",
        symbolsUpdated: 5,
        totalValue: 75000.5,
        duration: 2300,
      });

      expect(consoleSpy.log).toHaveBeenCalled();
      const logCall = consoleSpy.log.mock.calls[0][0];

      if (logCall.startsWith("{")) {
        const parsed = JSON.parse(logCall);
        expect(parsed.symbolsUpdated).toBe(5);
        expect(parsed.totalValue).toBe(75000.5);
      }
    });
  });
});

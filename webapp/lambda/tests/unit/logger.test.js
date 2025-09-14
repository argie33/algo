/**
 * Logger Tests
 * Tests logging functionality with different levels and environments
 */

const logger = require("../../utils/logger");

describe("Logger", () => {
  let originalEnv;
  let originalLogLevel;
  let originalConsoleLog;
  let originalCurrentLevel;
  let originalEnvironment;

  beforeEach(() => {
    originalEnv = process.env.NODE_ENV;
    originalLogLevel = process.env.LOG_LEVEL;
    originalConsoleLog = console.log;
    originalCurrentLevel = logger.currentLevel;
    originalEnvironment = logger.environment;
    
    console.log = jest.fn();
    
    // Set log level to DEBUG (3) to ensure all levels log
    logger.currentLevel = 3;
  });

  afterEach(() => {
    process.env.NODE_ENV = originalEnv;
    process.env.LOG_LEVEL = originalLogLevel;
    console.log = originalConsoleLog;
    logger.currentLevel = originalCurrentLevel;
    logger.environment = originalEnvironment;
    jest.clearAllMocks();
  });

  describe("Error Logging", () => {
    test("should log error messages", () => {
      logger.error("Test error message", { userId: "123" });
      
      expect(console.log).toHaveBeenCalled();
      const logCall = console.log.mock.calls[0][0];
      expect(typeof logCall).toBe("string");
      expect(logCall).toContain("ERROR");
      expect(logCall).toContain("Test error message");
    });

    test("should log error without context", () => {
      logger.error("Simple error");
      
      expect(console.log).toHaveBeenCalled();
    });
  });

  describe("Warning Logging", () => {
    test("should log warning messages", () => {
      logger.warn("Test warning message", { component: "test" });
      
      expect(console.log).toHaveBeenCalled();
      const logCall = console.log.mock.calls[0][0];
      expect(logCall).toContain("WARN");
      expect(logCall).toContain("Test warning message");
    });

    test("should log warning without context", () => {
      logger.warn("Simple warning");
      
      expect(console.log).toHaveBeenCalled();
    });
  });

  describe("Info Logging", () => {
    test("should log info messages", () => {
      logger.info("Test info message", { status: "success" });
      
      expect(console.log).toHaveBeenCalled();
      const logCall = console.log.mock.calls[0][0];
      expect(logCall).toContain("INFO");
      expect(logCall).toContain("Test info message");
    });

    test("should log info without context", () => {
      logger.info("Simple info");
      
      expect(console.log).toHaveBeenCalled();
    });
  });

  describe("Debug Logging", () => {
    test("should log debug messages", () => {
      logger.debug("Test debug message", { data: "test" });
      
      expect(console.log).toHaveBeenCalled();
      const logCall = console.log.mock.calls[0][0];
      expect(logCall).toContain("DEBUG");
      expect(logCall).toContain("Test debug message");
    });

    test("should log debug without context", () => {
      logger.debug("Simple debug");
      
      expect(console.log).toHaveBeenCalled();
    });
  });

  describe("Development Environment Pretty Printing", () => {
    test("should pretty print in development environment", () => {
      process.env.NODE_ENV = "development";
      logger.environment = "development"; // Update logger's cached environment
      
      // Clear any previous calls before testing
      console.log.mockClear();
      
      // Need extra context beyond the default fields to trigger pretty printing
      logger.error("Development error", { 
        userId: "123", 
        requestId: "abc",
        customField: "value",
        anotherField: "data" 
      });
      
      expect(console.log).toHaveBeenCalledTimes(2);
      
      // First call should be the pretty printed message
      const firstCall = console.log.mock.calls[0][0];
      expect(firstCall).toMatch(/\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\]/);
      expect(firstCall).toContain("[ERROR]");
      expect(firstCall).toContain("Development error");
      
      // Second call should be the context
      const secondCall = console.log.mock.calls[1][0];
      expect(secondCall).toBe("Context:");
    });

    test("should handle empty context in development", () => {
      process.env.NODE_ENV = "development";
      
      logger.error("Error without context");
      
      // Should only have one console.log call (no context)
      expect(console.log).toHaveBeenCalledTimes(1);
    });
  });

  describe("Production Environment JSON Logging", () => {
    test("should log JSON in production environment", () => {
      process.env.NODE_ENV = "production";
      logger.environment = "production"; // Update logger's cached environment
      console.log.mockClear(); // Clear any previous calls before testing
      
      logger.error("Production error", { userId: "123" });
      
      expect(console.log).toHaveBeenCalledTimes(1);
      const logCall = console.log.mock.calls[0][0];
      
      // Should be valid JSON
      expect(() => JSON.parse(logCall)).not.toThrow();
      
      const parsed = JSON.parse(logCall);
      expect(parsed.level).toBe("ERROR");
      expect(parsed.message).toBe("Production error");
      expect(parsed.userId).toBe("123");
    });
  });

  describe("Context Handling", () => {
    test("should handle complex context objects", () => {
      const complexContext = {
        user: { id: 123, name: "Test User" },
        request: { method: "POST", path: "/api/test" },
        performance: { duration: 150 }
      };
      
      logger.error("Complex context test", complexContext);
      
      expect(console.log).toHaveBeenCalled();
    });

    test("should handle error objects in context", () => {
      const testError = new Error("Test error object");
      testError.code = "TEST_ERROR";
      
      logger.error("Error with error object", { error: testError });
      
      expect(console.log).toHaveBeenCalled();
    });
  });
});
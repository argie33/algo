const errorTracker = require("../../../utils/errorTracker");

// Mock logger
jest.mock("../../../utils/logger", () => ({
  error: jest.fn(),
  warn: jest.fn(),
}));

const { error: mockError, warn: mockWarn } = require("../../../utils/logger");

describe("ErrorTracker", () => {
  let originalConsoleLog;

  beforeEach(() => {
    jest.clearAllMocks();
    originalConsoleLog = console.log;
    console.log = jest.fn();

    // Clear the singleton state
    errorTracker.clearHistory();

    // Mock Date.now and Math.random for consistent testing
    jest.spyOn(Date, "now").mockReturnValue(1640995200000); // 2022-01-01 00:00:00 -> 'kxv26800' in base36
    jest.spyOn(Math, "random").mockReturnValue(0.5); // -> 'i' when processed
  });

  afterEach(() => {
    jest.restoreAllMocks();
    console.log = originalConsoleLog;
  });

  describe("constructor and initialization", () => {
    it("should initialize with default values", () => {
      expect(errorTracker.errorHistory).toEqual([]);
      expect(errorTracker.errorCounts.size).toBe(0);
      expect(errorTracker.maxHistorySize).toBe(1000);
      expect(errorTracker.alertThresholds.database).toBe(5);
    });
  });

  describe("categorizeError", () => {
    it("should categorize database errors", () => {
      const dbError = new Error("Database connection failed");
      expect(errorTracker.categorizeError(dbError)).toBe("database");

      const pgError = new Error("Test error");
      pgError.stack = "Error at pg.connect";
      expect(errorTracker.categorizeError(pgError)).toBe("database");

      const timeoutError = new Error("Connection timeout");
      expect(errorTracker.categorizeError(timeoutError)).toBe("database");

      const connError = new Error("Test error");
      connError.code = "ECONNREFUSED";
      expect(errorTracker.categorizeError(connError)).toBe("database");
    });

    it("should categorize authentication errors", () => {
      const authError = new Error("Unauthorized access");
      expect(errorTracker.categorizeError(authError)).toBe("auth");

      const tokenError = new Error("Invalid token");
      expect(errorTracker.categorizeError(tokenError)).toBe("auth");

      const forbiddenError = new Error("Access forbidden");
      expect(errorTracker.categorizeError(forbiddenError)).toBe("auth");

      const statusError = new Error("Test error");
      statusError.statusCode = 401;
      expect(errorTracker.categorizeError(statusError)).toBe("auth");

      const status403Error = new Error("Test error");
      status403Error.statusCode = 403;
      expect(errorTracker.categorizeError(status403Error)).toBe("auth");
    });

    it("should categorize API errors", () => {
      const apiError = new Error("API request failed");
      expect(errorTracker.categorizeError(apiError)).toBe("api");

      const networkError = new Error("Network error");
      expect(errorTracker.categorizeError(networkError)).toBe("api");

      const serverError = new Error("Test error");
      serverError.statusCode = 500;
      expect(errorTracker.categorizeError(serverError)).toBe("api");

      const badGatewayError = new Error("Test error");
      badGatewayError.statusCode = 502;
      expect(errorTracker.categorizeError(badGatewayError)).toBe("api");
    });

    it("should categorize validation errors", () => {
      const validationError = new Error("Validation failed");
      expect(errorTracker.categorizeError(validationError)).toBe("validation");

      const invalidError = new Error("Invalid input");
      expect(errorTracker.categorizeError(invalidError)).toBe("validation");

      const requiredError = new Error("Field is required");
      expect(errorTracker.categorizeError(requiredError)).toBe("validation");

      const badRequestError = new Error("Test error");
      badRequestError.statusCode = 400;
      expect(errorTracker.categorizeError(badRequestError)).toBe("validation");
    });

    it("should categorize circuit breaker errors", () => {
      const circuitError = new Error("Circuit breaker is open");
      expect(errorTracker.categorizeError(circuitError)).toBe(
        "circuit_breaker"
      );

      const breakerError = new Error("Service breaker activated");
      expect(errorTracker.categorizeError(breakerError)).toBe(
        "circuit_breaker"
      );
    });

    it("should default to general category", () => {
      const generalError = new Error("Some random error");
      expect(errorTracker.categorizeError(generalError)).toBe("general");

      const unknownError = new Error("Unknown issue");
      expect(errorTracker.categorizeError(unknownError)).toBe("general");
    });
  });

  describe("calculateSeverity", () => {
    it("should assign critical severity correctly", () => {
      const serverError = new Error("Test error");
      serverError.statusCode = 500;
      expect(errorTracker.calculateSeverity(serverError)).toBe("critical");

      const dbError = new Error("Database connection lost");
      expect(errorTracker.calculateSeverity(dbError)).toBe("critical");

      const timeoutError = new Error("Connection timeout occurred");
      expect(errorTracker.calculateSeverity(timeoutError)).toBe("critical");

      const circuitError = new Error("Circuit breaker is open");
      expect(errorTracker.calculateSeverity(circuitError)).toBe("critical");
    });

    it("should assign high severity correctly", () => {
      const unauthorizedError = new Error("Test error");
      unauthorizedError.statusCode = 401;
      expect(errorTracker.calculateSeverity(unauthorizedError)).toBe("high");

      const forbiddenError = new Error("Test error");
      forbiddenError.statusCode = 403;
      expect(errorTracker.calculateSeverity(forbiddenError)).toBe("high");

      const authError = new Error("Unauthorized access attempt");
      expect(errorTracker.calculateSeverity(authError)).toBe("high");

      const keyError = new Error("Invalid API key provided");
      expect(errorTracker.calculateSeverity(keyError)).toBe("high");
    });

    it("should assign medium severity correctly", () => {
      const badRequestError = new Error("Test error");
      badRequestError.statusCode = 400;
      expect(errorTracker.calculateSeverity(badRequestError)).toBe("medium");

      const validationError = new Error("Validation failed");
      expect(errorTracker.calculateSeverity(validationError)).toBe("medium");

      const invalidError = new Error("Invalid input provided");
      expect(errorTracker.calculateSeverity(invalidError)).toBe("medium");
    });

    it("should default to low severity", () => {
      const generalError = new Error("Some minor issue");
      expect(errorTracker.calculateSeverity(generalError)).toBe("low");

      const warningError = new Error("Warning message");
      expect(errorTracker.calculateSeverity(warningError)).toBe("low");
    });
  });

  describe("trackError", () => {
    it("should track error with full context", () => {
      const error = new Error("Test error");
      error.code = "TEST_ERROR";
      error.statusCode = 500;

      const context = {
        correlationId: "test-123",
        userId: "user-456",
        route: "/api/test",
        method: "GET",
        userAgent: "Test Agent",
        ip: "127.0.0.1",
      };

      const errorId = errorTracker.trackError(error, context);

      expect(errorId).toBe("api-kxv26800-i");
      expect(mockError).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          message: "Test error",
          name: "Error",
          code: "TEST_ERROR",
          statusCode: 500,
          correlationId: "test-123",
          userId: "user-456",
          route: "/api/test",
          method: "GET",
          category: "api",
          severity: "critical",
        })
      );

      expect(errorTracker.errorHistory).toHaveLength(1);
    });

    it("should track error with minimal context", () => {
      const error = new Error("Simple error");
      const errorId = errorTracker.trackError(error);

      expect(errorId).toBe("gen-kxv26800-i");
      expect(mockError).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          message: "Simple error",
          category: "general",
          severity: "low",
        })
      );
    });

    it("should handle errors without stack trace", () => {
      const error = new Error("Error without stack");
      delete error.stack;

      const errorId = errorTracker.trackError(error);

      expect(errorId).toBeDefined();
      expect(mockError).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          message: "Error without stack",
          stack: undefined,
        })
      );
    });
  });

  describe("updateErrorCounts", () => {
    it("should track error counts by minute", () => {
      const errorData = {
        category: "database",
        timestamp: new Date().toISOString(),
      };

      errorTracker.updateErrorCounts(errorData);
      errorTracker.updateErrorCounts(errorData);

      const minuteKey = Math.floor(Date.now() / 60000);
      const countKey = `database:${minuteKey}`;

      expect(errorTracker.errorCounts.get(countKey)).toBe(2);
    });

    it("should clean up old error counts", () => {
      const oldTime = 1640995200000 - 6 * 60000; // 6 minutes ago
      Date.now.mockReturnValueOnce(oldTime);

      const oldErrorData = {
        category: "database",
        timestamp: new Date(oldTime).toISOString(),
      };

      errorTracker.updateErrorCounts(oldErrorData);

      // Reset to current time and add new error
      Date.now.mockReturnValue(1640995200000);
      const newErrorData = {
        category: "api",
        timestamp: new Date().toISOString(),
      };

      errorTracker.updateErrorCounts(newErrorData);

      // Old count should be cleaned up
      const oldMinuteKey = Math.floor(oldTime / 60000);
      const oldCountKey = `database:${oldMinuteKey}`;
      expect(errorTracker.errorCounts.has(oldCountKey)).toBe(false);

      // New count should exist
      const newMinuteKey = Math.floor(1640995200000 / 60000);
      const newCountKey = `api:${newMinuteKey}`;
      expect(errorTracker.errorCounts.has(newCountKey)).toBe(true);
    });
  });

  describe("addToHistory", () => {
    it("should add errors to history", () => {
      const errorData = { message: "Test error 1" };
      errorTracker.addToHistory(errorData);

      expect(errorTracker.errorHistory).toHaveLength(1);
      expect(errorTracker.errorHistory[0]).toEqual(errorData);
    });

    it("should maintain maximum history size", () => {
      const originalMaxSize = errorTracker.maxHistorySize;
      errorTracker.maxHistorySize = 3;

      for (let i = 0; i < 5; i++) {
        errorTracker.addToHistory({ message: `Error ${i}` });
      }

      expect(errorTracker.errorHistory).toHaveLength(3);
      expect(errorTracker.errorHistory[0].message).toBe("Error 2"); // First two should be removed
      expect(errorTracker.errorHistory[2].message).toBe("Error 4");

      errorTracker.maxHistorySize = originalMaxSize;
    });
  });

  describe("checkAlertThresholds", () => {
    it("should trigger alert when threshold is exceeded", () => {
      const errorData = {
        category: "database",
        timestamp: new Date().toISOString(),
      };

      // Add errors to exceed database threshold (5)
      for (let i = 0; i < 6; i++) {
        errorTracker.updateErrorCounts(errorData);
      }

      errorTracker.checkAlertThresholds(errorData);

      expect(mockWarn).toHaveBeenCalledWith(
        "Error Rate Alert",
        expect.objectContaining({
          category: "database",
          currentCount: 6,
          threshold: 5,
          severity: "high",
        })
      );

      expect(console.log).toHaveBeenCalledWith(
        "🚨 ALERT:",
        "High error rate detected: 6 database errors in the last minute (threshold: 5)"
      );
    });

    it("should not trigger alert when below threshold", () => {
      const errorData = {
        category: "database",
        timestamp: new Date().toISOString(),
      };

      // Add errors below threshold
      for (let i = 0; i < 3; i++) {
        errorTracker.updateErrorCounts(errorData);
      }

      errorTracker.checkAlertThresholds(errorData);

      expect(mockWarn).not.toHaveBeenCalled();
      expect(console.log).not.toHaveBeenCalled();
    });

    it("should use general threshold for unknown categories", () => {
      const errorData = {
        category: "unknown_category",
        timestamp: new Date().toISOString(),
      };

      // Add errors to exceed general threshold (15)
      for (let i = 0; i < 16; i++) {
        errorTracker.updateErrorCounts(errorData);
      }

      errorTracker.checkAlertThresholds(errorData);

      expect(mockWarn).toHaveBeenCalledWith(
        "Error Rate Alert",
        expect.objectContaining({
          currentCount: 16,
          threshold: 15,
        })
      );
    });

    it("should handle missing error count for category (branch coverage)", () => {
      const errorData = { category: "new_category", severity: "high" };

      // Don't add any errors, so count should default to 0 via || operator (line 205)
      errorTracker.checkAlertThresholds(errorData);

      // Should not trigger alert since count is 0
      expect(mockWarn).not.toHaveBeenCalled();
    });
  });

  describe("generateErrorId", () => {
    it("should generate unique error IDs", () => {
      const errorData1 = { category: "database" };
      const errorData2 = { category: "api" };

      const id1 = errorTracker.generateErrorId(errorData1);
      const id2 = errorTracker.generateErrorId(errorData2);

      expect(id1).toBe("dat-kxv26800-i");
      expect(id2).toBe("api-kxv26800-i");
      expect(id1).not.toBe(id2);
    });

    it("should handle short category names", () => {
      const errorData = { category: "ab" };
      const id = errorTracker.generateErrorId(errorData);

      expect(id).toBe("ab-kxv26800-i");
    });

    it("should truncate long category names", () => {
      const errorData = { category: "very_long_category_name" };
      const id = errorTracker.generateErrorId(errorData);

      expect(id).toBe("ver-kxv26800-i");
    });
  });

  describe("getErrorStats", () => {
    beforeEach(() => {
      // Add some test errors with different timestamps
      const baseTime = 1640995200000;

      // Current hour errors
      Date.now.mockReturnValue(baseTime);
      errorTracker.addToHistory({
        timestamp: new Date(baseTime).toISOString(),
        category: "database",
        severity: "critical",
      });

      Date.now.mockReturnValue(baseTime - 30 * 60000); // 30 minutes ago
      errorTracker.addToHistory({
        timestamp: new Date(baseTime - 30 * 60000).toISOString(),
        category: "api",
        severity: "high",
      });

      Date.now.mockReturnValue(baseTime - 2 * 60 * 60000); // 2 hours ago
      errorTracker.addToHistory({
        timestamp: new Date(baseTime - 2 * 60 * 60000).toISOString(),
        category: "database",
        severity: "medium",
      });

      // Reset to current time
      Date.now.mockReturnValue(baseTime);

      // Add current minute rates
      const currentMinute = Math.floor(baseTime / 60000);
      errorTracker.errorCounts.set(`database:${currentMinute}`, 3);
      errorTracker.errorCounts.set(`api:${currentMinute}`, 1);
    });

    it("should return comprehensive error statistics", () => {
      const stats = errorTracker.getErrorStats();

      expect(stats).toEqual({
        total: 3,
        lastHour: 2,
        byCategory: {
          database: 2,
          api: 1,
        },
        bySeverity: {
          critical: 1,
          high: 1,
          medium: 1,
        },
        currentMinuteRates: {
          database: 3,
          api: 1,
        },
      });
    });

    it("should handle empty error history", () => {
      errorTracker.clearHistory();

      const stats = errorTracker.getErrorStats();

      expect(stats).toEqual({
        total: 0,
        lastHour: 0,
        byCategory: {},
        bySeverity: {},
        currentMinuteRates: {},
      });
    });

    it("should exclude error counts from different minutes (branch coverage)", () => {
      errorTracker.clearHistory();

      const baseTime = 1640995200000;
      Date.now.mockReturnValue(baseTime);
      const currentMinute = Math.floor(baseTime / 60000);

      // Add counts for current minute and different minutes
      errorTracker.errorCounts.set(`database:${currentMinute}`, 2); // Should be included
      errorTracker.errorCounts.set(`api:${currentMinute - 1}`, 5); // Should be excluded (different minute)
      errorTracker.errorCounts.set(`auth:${currentMinute + 1}`, 3); // Should be excluded (different minute)

      const stats = errorTracker.getErrorStats();

      // Only the current minute count should be included (line 281 branch coverage)
      expect(stats.currentMinuteRates).toEqual({
        database: 2,
      });
    });
  });

  describe("getRecentErrors", () => {
    beforeEach(() => {
      // Add test errors in sequence
      for (let i = 0; i < 10; i++) {
        errorTracker.addToHistory({
          message: `Error ${i}`,
          timestamp: new Date(1640995200000 + i * 1000).toISOString(),
        });
      }
    });

    it("should return recent errors sorted by timestamp desc", () => {
      const recent = errorTracker.getRecentErrors(5);

      expect(recent).toHaveLength(5);
      expect(recent[0].message).toBe("Error 9"); // Most recent
      expect(recent[4].message).toBe("Error 5"); // 5th most recent
    });

    it("should default to 50 errors when no limit specified", () => {
      const recent = errorTracker.getRecentErrors();

      expect(recent).toHaveLength(10); // We only have 10 errors
    });

    it("should handle limit larger than available errors", () => {
      const recent = errorTracker.getRecentErrors(20);

      expect(recent).toHaveLength(10); // We only have 10 errors
    });

    it("should return empty array when no errors exist", () => {
      errorTracker.clearHistory();

      const recent = errorTracker.getRecentErrors();

      expect(recent).toEqual([]);
    });
  });

  describe("clearHistory", () => {
    it("should clear all error history and counts", () => {
      // Add some data first
      errorTracker.addToHistory({ message: "Test error" });
      errorTracker.errorCounts.set("test:123", 5);

      expect(errorTracker.errorHistory).toHaveLength(1);
      expect(errorTracker.errorCounts.size).toBe(1);

      errorTracker.clearHistory();

      expect(errorTracker.errorHistory).toHaveLength(0);
      expect(errorTracker.errorCounts.size).toBe(0);
    });
  });

  describe("middleware", () => {
    let middleware;
    let mockReq;
    let mockRes;
    let mockNext;

    beforeEach(() => {
      middleware = errorTracker.middleware();

      mockReq = {
        headers: { "x-correlation-id": "test-correlation-123" },
        user: { id: "user-456" },
        route: { path: "/api/test" },
        method: "POST",
        get: jest.fn().mockReturnValue("Test User Agent"),
        ip: "192.168.1.1",
        body: { test: "data" },
        query: { param: "value" },
        params: { id: "123" },
      };

      mockRes = {
        setHeader: jest.fn(),
      };

      mockNext = jest.fn();
    });

    it("should track error and add context from request", () => {
      const error = new Error("Middleware test error");

      middleware(error, mockReq, mockRes, mockNext);

      expect(mockError).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          message: "Middleware test error",
          context: expect.objectContaining({
            correlationId: "test-correlation-123",
            userId: "user-456",
            route: "/api/test",
            method: "POST",
            userAgent: "Test User Agent",
            ip: "192.168.1.1",
            body: { test: "data" },
            query: { param: "value" },
            params: { id: "123" },
          }),
        })
      );

      expect(mockRes.setHeader).toHaveBeenCalledWith(
        "X-Error-ID",
        "gen-kxv26800-i"
      );
      expect(mockNext).toHaveBeenCalledWith(error);
    });

    it("should handle request without correlation ID", () => {
      mockReq.headers = {};
      mockReq.id = "fallback-id-789";

      const error = new Error("Test error without correlation ID");

      middleware(error, mockReq, mockRes, mockNext);

      expect(mockError).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          context: expect.objectContaining({
            correlationId: "fallback-id-789",
          }),
        })
      );
    });

    it("should handle request without user", () => {
      delete mockReq.user;

      const error = new Error("Test error without user");

      middleware(error, mockReq, mockRes, mockNext);

      expect(mockError).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          context: expect.objectContaining({
            userId: undefined,
          }),
        })
      );
    });

    it("should handle request without route", () => {
      delete mockReq.route;

      const error = new Error("Test error without route");

      middleware(error, mockReq, mockRes, mockNext);

      expect(mockError).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          context: expect.objectContaining({
            route: undefined,
          }),
        })
      );
    });

    it("should handle minimal request object", () => {
      const minimalReq = {
        headers: {},
        method: "GET",
        get: jest.fn().mockReturnValue(undefined),
        body: {},
        query: {},
        params: {},
      };

      const error = new Error("Minimal request error");

      middleware(error, minimalReq, mockRes, mockNext);

      expect(mockError).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          message: "Minimal request error",
        })
      );

      expect(mockNext).toHaveBeenCalledWith(error);
    });
  });
});

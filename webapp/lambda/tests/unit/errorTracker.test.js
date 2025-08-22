/**
 * Unit Tests for Error Tracker Service
 * Tests error tracking, categorization, severity calculation, and alerting
 */

// Mock logger before requiring errorTracker
jest.mock("../../utils/logger", () => ({
  error: jest.fn(),
  warn: jest.fn(),
  info: jest.fn(),
  debug: jest.fn(),
}));

const logger = require("../../utils/logger");

describe("Error Tracker Service", () => {
  let errorTracker;

  beforeEach(() => {
    jest.clearAllMocks();

    // Clear module cache to get fresh instance
    delete require.cache[require.resolve("../../utils/errorTracker")];
    errorTracker = require("../../utils/errorTracker");

    // Clear error history for clean tests
    errorTracker.clearHistory();
  });

  describe("Error Tracking", () => {
    test("should track error with comprehensive context", () => {
      const testError = new Error("Test database connection failed");
      testError.code = "ECONNREFUSED";
      testError.statusCode = 500;

      const context = {
        correlationId: "test-123",
        userId: "user-456",
        route: "/api/test",
        method: "GET",
        userAgent: "test-agent",
        ip: "192.168.1.1",
      };

      const errorId = errorTracker.trackError(testError, context);

      // Verify logger was called with structured data
      expect(logger.error).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          message: "Test database connection failed",
          code: "ECONNREFUSED",
          statusCode: 500,
          correlationId: "test-123",
          userId: "user-456",
          route: "/api/test",
          method: "GET",
          userAgent: "test-agent",
          ip: "192.168.1.1",
          category: "database",
          severity: "critical",
        })
      );

      // Verify error ID is generated
      expect(errorId).toMatch(/^dat-[a-z0-9]+-[a-z0-9]+$/);

      // Verify error is stored in history
      const recentErrors = errorTracker.getRecentErrors(1);
      expect(recentErrors).toHaveLength(1);
      expect(recentErrors[0].message).toBe("Test database connection failed");
    });

    test("should handle error without context", () => {
      const testError = new Error("Simple error");
      const errorId = errorTracker.trackError(testError);

      expect(logger.error).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          message: "Simple error",
          category: "general",
          severity: "low",
        })
      );

      expect(errorId).toMatch(/^gen-[a-z0-9]+-[a-z0-9]+$/);
    });

    test("should generate unique error IDs", () => {
      const error1 = new Error("Error 1");
      const error2 = new Error("Error 2");

      const id1 = errorTracker.trackError(error1);
      const id2 = errorTracker.trackError(error2);

      expect(id1).not.toBe(id2);
      expect(id1).toMatch(/^gen-[a-z0-9]+-[a-z0-9]+$/);
      expect(id2).toMatch(/^gen-[a-z0-9]+-[a-z0-9]+$/);
    });
  });

  describe("Error Categorization", () => {
    test("should categorize database errors correctly", () => {
      const databaseErrors = [
        { message: "Database connection timeout", expected: "database" },
        {
          message: "Connection refused",
          code: "ECONNREFUSED",
          expected: "database",
        },
        {
          message: "Connection reset",
          code: "ECONNRESET",
          expected: "database",
        },
        {
          message: "PostgreSQL error",
          stack: "at pg.query",
          expected: "database",
        },
      ];

      databaseErrors.forEach(({ message, code, stack, expected }) => {
        const error = new Error(message);
        if (code) error.code = code;
        if (stack) error.stack = stack;

        errorTracker.trackError(error);

        expect(logger.error).toHaveBeenLastCalledWith(
          "Application Error",
          expect.objectContaining({
            category: expected,
          })
        );
      });
    });

    test("should categorize authentication errors correctly", () => {
      const authErrors = [
        { message: "Unauthorized access", expected: "auth" },
        { message: "Invalid token", expected: "auth" },
        { message: "Authentication failed", expected: "auth" },
        { statusCode: 401, expected: "auth" },
        { statusCode: 403, expected: "auth" },
      ];

      authErrors.forEach(({ message = "Test error", statusCode, expected }) => {
        const error = new Error(message);
        if (statusCode) error.statusCode = statusCode;

        errorTracker.trackError(error);

        expect(logger.error).toHaveBeenLastCalledWith(
          "Application Error",
          expect.objectContaining({
            category: expected,
          })
        );
      });
    });

    test("should categorize API errors correctly", () => {
      const apiErrors = [
        { message: "API request failed", expected: "api" },
        { message: "Network error", expected: "api" },
        { statusCode: 500, expected: "api" },
        { statusCode: 502, expected: "api" },
        { statusCode: 503, expected: "api" },
      ];

      apiErrors.forEach(({ message = "Test error", statusCode, expected }) => {
        const error = new Error(message);
        if (statusCode) error.statusCode = statusCode;

        errorTracker.trackError(error);

        expect(logger.error).toHaveBeenLastCalledWith(
          "Application Error",
          expect.objectContaining({
            category: expected,
          })
        );
      });
    });

    test("should categorize validation errors correctly", () => {
      const validationErrors = [
        { message: "Validation failed", expected: "validation" },
        { message: "Invalid input", expected: "validation" },
        { message: "Required field missing", expected: "validation" },
        { statusCode: 400, expected: "validation" },
      ];

      validationErrors.forEach(
        ({ message = "Test error", statusCode, expected }) => {
          const error = new Error(message);
          if (statusCode) error.statusCode = statusCode;

          errorTracker.trackError(error);

          expect(logger.error).toHaveBeenLastCalledWith(
            "Application Error",
            expect.objectContaining({
              category: expected,
            })
          );
        }
      );
    });

    test("should categorize circuit breaker errors correctly", () => {
      const circuitBreakerErrors = [
        { message: "Circuit breaker is open", expected: "circuit_breaker" },
        { message: "Circuit breaker activated", expected: "circuit_breaker" },
      ];

      circuitBreakerErrors.forEach(({ message, expected }) => {
        const error = new Error(message);

        errorTracker.trackError(error);

        expect(logger.error).toHaveBeenLastCalledWith(
          "Application Error",
          expect.objectContaining({
            category: expected,
          })
        );
      });
    });

    test("should default to general category for unrecognized errors", () => {
      const error = new Error("Some random error");
      errorTracker.trackError(error);

      expect(logger.error).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          category: "general",
        })
      );
    });
  });

  describe("Severity Calculation", () => {
    test("should assign critical severity correctly", () => {
      const criticalErrors = [
        { statusCode: 500 },
        { statusCode: 502 },
        { message: "Database connection failed" },
        { message: "Connection timeout" },
        { message: "Circuit breaker is open" },
      ];

      criticalErrors.forEach(({ message = "Test error", statusCode }) => {
        const error = new Error(message);
        if (statusCode) error.statusCode = statusCode;

        errorTracker.trackError(error);

        expect(logger.error).toHaveBeenLastCalledWith(
          "Application Error",
          expect.objectContaining({
            severity: "critical",
          })
        );
      });
    });

    test("should assign high severity correctly", () => {
      const highErrors = [
        { statusCode: 401 },
        { statusCode: 403 },
        { message: "Unauthorized access" },
        { message: "Forbidden resource" },
        { message: "Invalid API key" },
      ];

      highErrors.forEach(({ message = "Test error", statusCode }) => {
        const error = new Error(message);
        if (statusCode) error.statusCode = statusCode;

        errorTracker.trackError(error);

        expect(logger.error).toHaveBeenLastCalledWith(
          "Application Error",
          expect.objectContaining({
            severity: "high",
          })
        );
      });
    });

    test("should assign medium severity correctly", () => {
      const mediumErrors = [
        { statusCode: 400 },
        { message: "Validation error" },
        { message: "Invalid input data" },
      ];

      mediumErrors.forEach(({ message = "Test error", statusCode }) => {
        const error = new Error(message);
        if (statusCode) error.statusCode = statusCode;

        errorTracker.trackError(error);

        expect(logger.error).toHaveBeenLastCalledWith(
          "Application Error",
          expect.objectContaining({
            severity: "medium",
          })
        );
      });
    });

    test("should assign low severity by default", () => {
      const error = new Error("Some minor error");
      errorTracker.trackError(error);

      expect(logger.error).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          severity: "low",
        })
      );
    });
  });

  describe("Error Frequency Tracking", () => {
    test("should track error counts by category and minute", () => {
      const databaseError = new Error("Database error");
      databaseError.code = "ECONNREFUSED";

      // Track multiple database errors
      errorTracker.trackError(databaseError);
      errorTracker.trackError(databaseError);
      errorTracker.trackError(databaseError);

      const stats = errorTracker.getErrorStats();
      expect(stats.currentMinuteRates.database).toBe(3);
    });

    test("should trigger alert when threshold is exceeded", () => {
      // Spy on console.log for alert output
      const consoleSpy = jest.spyOn(console, "log").mockImplementation();

      const databaseError = new Error("Database connection failed");
      databaseError.code = "ECONNREFUSED";

      // Track errors to exceed database threshold (5)
      for (let i = 0; i < 6; i++) {
        errorTracker.trackError(databaseError);
      }

      // Verify alert was triggered
      expect(logger.warn).toHaveBeenCalledWith(
        "Error Rate Alert",
        expect.objectContaining({
          category: "database",
          currentCount: 6,
          threshold: 5,
          severity: "high",
        })
      );

      expect(consoleSpy).toHaveBeenCalledWith(
        "🚨 ALERT:",
        "High error rate detected: 6 database errors in the last minute (threshold: 5)"
      );

      consoleSpy.mockRestore();
    });

    test("should clean up old error counts", () => {
      const error = new Error("Test error");

      // Track an error
      errorTracker.trackError(error);

      // Mock time passage by directly manipulating the counts
      const oldTime = Math.floor(Date.now() / 60000) - 10; // 10 minutes ago
      errorTracker.errorCounts.set(`general:${oldTime}`, 5);

      // Track another error to trigger cleanup
      errorTracker.trackError(error);

      // Old counts should be cleaned up
      expect(errorTracker.errorCounts.has(`general:${oldTime}`)).toBe(false);
    });
  });

  describe("Error History Management", () => {
    test("should maintain error history with size limit", async () => {
      // Store original limit and set a smaller limit for testing
      const originalLimit = errorTracker.maxHistorySize;
      errorTracker.maxHistorySize = 3;

      try {
        const errors = [
          new Error("Error 1"),
          new Error("Error 2"),
          new Error("Error 3"),
          new Error("Error 4"),
        ];

        // Add errors with small delays to ensure different timestamps
        for (let i = 0; i < errors.length; i++) {
          errorTracker.trackError(errors[i]);
          if (i < errors.length - 1) {
            await new Promise(resolve => setTimeout(resolve, 1));
          }
        }

        const history = errorTracker.getRecentErrors();
        expect(history).toHaveLength(3);

        // Should keep the most recent errors (sorted by timestamp, newest first)
        const messages = history.map(h => h.message);
        expect(messages).toContain("Error 4");
        expect(messages).toContain("Error 3");
        expect(messages).toContain("Error 2");
        expect(messages).not.toContain("Error 1");
      } finally {
        // Restore original limit to prevent test interference
        errorTracker.maxHistorySize = originalLimit;
      }
    });

    test("should return recent errors in chronological order", async () => {
      const errors = [
        new Error("First error"),
        new Error("Second error"),
        new Error("Third error"),
      ];

      // Track errors with artificial delay to ensure different timestamps
      for (let i = 0; i < errors.length; i++) {
        await new Promise(resolve => setTimeout(() => {
          errorTracker.trackError(errors[i]);
          resolve();
        }, i + 1));
      }

      const recentErrors = errorTracker.getRecentErrors();
      expect(recentErrors[0].message).toBe("Third error");
      expect(recentErrors[1].message).toBe("Second error");
      expect(recentErrors[2].message).toBe("First error");
    });

    test("should clear history when requested", () => {
      errorTracker.trackError(new Error("Test error"));
      expect(errorTracker.getRecentErrors()).toHaveLength(1);

      errorTracker.clearHistory();
      expect(errorTracker.getRecentErrors()).toHaveLength(0);
      expect(errorTracker.errorCounts.size).toBe(0);
    });
  });

  describe("Error Statistics", () => {
    beforeEach(() => {
      errorTracker.clearHistory();
    });

    test("should provide comprehensive error statistics", () => {
      const errors = [
        { error: new Error("Database error"), code: "ECONNREFUSED" },
        { error: new Error("Auth error"), statusCode: 401 },
        { error: new Error("Validation error"), statusCode: 400 },
        { error: new Error("Database error"), code: "ECONNREFUSED" },
        { error: new Error("General error") },
      ];

      errors.forEach(({ error, code, statusCode }) => {
        if (code) error.code = code;
        if (statusCode) error.statusCode = statusCode;
        errorTracker.trackError(error);
      });

      const stats = errorTracker.getErrorStats();

      expect(stats.total).toBe(5);
      expect(stats.byCategory.database).toBe(2);
      expect(stats.byCategory.auth).toBe(1);
      expect(stats.byCategory.validation).toBe(1);
      expect(stats.byCategory.general).toBe(1);

      expect(stats.bySeverity.critical).toBe(2); // database errors
      expect(stats.bySeverity.high).toBe(1); // auth error
      expect(stats.bySeverity.medium).toBe(1); // validation error
      expect(stats.bySeverity.low).toBe(1); // general error
    });

    test("should count errors from last hour correctly", () => {
      // Track recent error
      errorTracker.trackError(new Error("Recent error"));

      // Mock old error by manipulating history
      const oldError = {
        timestamp: new Date(Date.now() - 7200000).toISOString(), // 2 hours ago
        message: "Old error",
        category: "general",
        severity: "low",
      };
      errorTracker.errorHistory.push(oldError);

      const stats = errorTracker.getErrorStats();
      expect(stats.lastHour).toBe(1); // Only recent error
      expect(stats.total).toBe(2); // Both errors in total
    });
  });

  describe("Express Middleware", () => {
    test("should create express middleware that tracks errors", () => {
      const middleware = errorTracker.middleware();
      expect(typeof middleware).toBe("function");
      expect(middleware.length).toBe(4); // Express error middleware signature
    });

    test("should track error from express middleware with request context", () => {
      const middleware = errorTracker.middleware();

      const mockError = new Error("Express error");
      const mockReq = {
        headers: { "x-correlation-id": "req-123" },
        user: { id: "user-456" },
        route: { path: "/api/test" },
        method: "POST",
        get: jest.fn().mockReturnValue("test-user-agent"),
        ip: "192.168.1.100",
        body: { test: "data" },
        query: { param: "value" },
        params: { id: "123" },
      };
      const mockRes = {
        setHeader: jest.fn(),
      };
      const mockNext = jest.fn();

      middleware(mockError, mockReq, mockRes, mockNext);

      // Verify error was tracked with context
      expect(logger.error).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          message: "Express error",
          correlationId: "req-123",
          userId: "user-456",
          route: "/api/test",
          method: "POST",
          userAgent: "test-user-agent",
          ip: "192.168.1.100",
        })
      );

      // Verify error ID header was set
      expect(mockRes.setHeader).toHaveBeenCalledWith(
        "X-Error-ID",
        expect.stringMatching(/^gen-[a-z0-9]+-[a-z0-9]+$/)
      );

      // Verify next was called
      expect(mockNext).toHaveBeenCalledWith(mockError);
    });

    test("should handle middleware with minimal request context", () => {
      const middleware = errorTracker.middleware();

      const mockError = new Error("Minimal express error");
      const mockReq = {
        headers: {},
        get: jest.fn().mockReturnValue(undefined),
        method: "GET",
      };
      const mockRes = {
        setHeader: jest.fn(),
      };
      const mockNext = jest.fn();

      middleware(mockError, mockReq, mockRes, mockNext);

      expect(logger.error).toHaveBeenCalledWith(
        "Application Error",
        expect.objectContaining({
          message: "Minimal express error",
          method: "GET",
        })
      );

      expect(mockNext).toHaveBeenCalledWith(mockError);
    });
  });
});

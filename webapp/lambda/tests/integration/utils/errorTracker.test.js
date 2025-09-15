/**
 * Error Tracker Integration Tests
 * Tests error logging, monitoring, and alert system
 */

const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");
const errorTracker = require("../../../utils/errorTracker");

describe("Error Tracker Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
    // Clear any existing error history for clean tests
    errorTracker.clearHistory();
  });

  afterAll(async () => {
    await closeDatabase();
  });

  beforeEach(() => {
    // Clear history before each test for isolation
    errorTracker.clearHistory();
  });

  describe("Error Tracking", () => {
    test("should track errors with context", () => {
      const testError = new Error("Test error for tracking");
      const context = {
        userId: "test_user",
        route: "/api/test",
        method: "GET",
        correlationId: "test-123",
      };

      const errorId = errorTracker.trackError(testError, context);

      expect(errorId).toBeDefined();
      expect(typeof errorId).toBe("string");
      expect(errorId).toMatch(/^[a-z]{3}-[a-z0-9]+-[a-z0-9]+$/); // Format: category-timestamp-random
    });

    test("should track errors with stack traces", () => {
      const error = new Error("Error with stack trace");
      const context = { route: "/test-service", method: "POST" };

      const errorId = errorTracker.trackError(error, context);
      const recentErrors = errorTracker.getRecentErrors(1);

      expect(recentErrors).toBeDefined();
      expect(recentErrors.length).toBe(1);
      expect(recentErrors[0].stack).toBeDefined();
      expect(recentErrors[0].message).toBe("Error with stack trace");
    });

    test("should categorize errors correctly", () => {
      const databaseError = new Error("Database connection failed");
      const authError = new Error("Unauthorized access");
      const validationError = new Error("Validation failed");

      errorTracker.trackError(databaseError);
      errorTracker.trackError(authError, { statusCode: 401 });
      errorTracker.trackError(validationError, { statusCode: 400 });

      const recentErrors = errorTracker.getRecentErrors(3);

      expect(recentErrors.length).toBe(3);

      const dbErr = recentErrors.find((e) => e.message.includes("Database"));
      const authErr = recentErrors.find((e) =>
        e.message.includes("Unauthorized")
      );
      const valErr = recentErrors.find((e) => e.message.includes("Validation"));

      expect(dbErr.category).toBe("database");
      expect(authErr.category).toBe("auth");
      expect(valErr.category).toBe("validation");
    });

    test("should calculate severity levels", () => {
      const criticalError = new Error("Database connection timeout");
      const highError = new Error("Unauthorized");
      const mediumError = new Error("Invalid input");
      const lowError = new Error("Minor issue");

      errorTracker.trackError(criticalError);
      errorTracker.trackError(highError, { statusCode: 401 });
      errorTracker.trackError(mediumError, { statusCode: 400 });
      errorTracker.trackError(lowError);

      const recentErrors = errorTracker.getRecentErrors(4);

      expect(recentErrors.length).toBe(4);

      const critical = recentErrors.find((e) => e.message.includes("timeout"));
      const high = recentErrors.find((e) => e.message.includes("Unauthorized"));
      const medium = recentErrors.find((e) => e.message.includes("Invalid"));
      const low = recentErrors.find((e) => e.message.includes("Minor"));

      expect(critical.severity).toBe("critical");
      expect(high.severity).toBe("high");
      expect(medium.severity).toBe("medium");
      expect(low.severity).toBe("low");
    });
  });

  describe("Error Statistics", () => {
    test("should provide error statistics", () => {
      // Track various errors
      errorTracker.trackError(new Error("Database error"));
      errorTracker.trackError(new Error("Auth error"), { statusCode: 401 });
      errorTracker.trackError(new Error("Validation error"), {
        statusCode: 400,
      });
      errorTracker.trackError(new Error("API error"), { statusCode: 500 });

      const stats = errorTracker.getErrorStats();

      expect(stats).toBeDefined();
      expect(stats.total).toBe(4);
      expect(stats.byCategory).toBeDefined();
      expect(stats.bySeverity).toBeDefined();
      expect(stats.lastHour).toBeDefined();
      expect(stats.currentMinuteRates).toBeDefined();

      // Check categories are counted
      expect(stats.byCategory.database).toBeGreaterThanOrEqual(1);
      expect(stats.byCategory.auth).toBeGreaterThanOrEqual(1);
      expect(stats.byCategory.validation).toBeGreaterThanOrEqual(1);
      expect(stats.byCategory.api).toBeGreaterThanOrEqual(1);
    });

    test("should track recent errors with limit", () => {
      // Track more errors than the limit
      for (let i = 0; i < 10; i++) {
        errorTracker.trackError(new Error(`Test error ${i}`));
      }

      const recent5 = errorTracker.getRecentErrors(5);
      const recent3 = errorTracker.getRecentErrors(3);

      expect(recent5.length).toBe(5);
      expect(recent3.length).toBe(3);

      // Check that we have the most recent errors (may not be in exact order due to timing)
      const messages = recent5.map((e) => e.message);
      expect(messages).toContain("Test error 9");
      expect(messages).toContain("Test error 8");
      expect(messages).toContain("Test error 7");
      expect(messages).toContain("Test error 6");
      expect(messages).toContain("Test error 5");
    });
  });

  describe("Error Frequency Tracking", () => {
    test("should track error counts by category and time", () => {
      // Generate multiple database errors
      for (let i = 0; i < 3; i++) {
        errorTracker.trackError(new Error("Connection failed"));
      }

      // Generate multiple auth errors
      for (let i = 0; i < 2; i++) {
        errorTracker.trackError(new Error("Unauthorized"), { statusCode: 401 });
      }

      const stats = errorTracker.getErrorStats();

      expect(stats.byCategory.database).toBe(3);
      expect(stats.byCategory.auth).toBe(2);
      expect(stats.total).toBe(5);
    });

    test("should handle concurrent error tracking", async () => {
      const promises = [];

      // Track 20 errors concurrently
      for (let i = 0; i < 20; i++) {
        promises.push(
          Promise.resolve(
            errorTracker.trackError(new Error(`Concurrent error ${i}`))
          )
        );
      }

      await Promise.all(promises);

      const stats = errorTracker.getErrorStats();
      expect(stats.total).toBe(20);

      const recentErrors = errorTracker.getRecentErrors(20);
      expect(recentErrors.length).toBe(20);
    });
  });

  describe("Alert System", () => {
    test("should track errors without triggering alerts for low volume", () => {
      // Track a few errors (below alert threshold)
      errorTracker.trackError(new Error("Database connection issue"));
      errorTracker.trackError(new Error("Database timeout"));

      const stats = errorTracker.getErrorStats();
      expect(stats.byCategory.database).toBe(2);

      // No specific alert tracking in current implementation
      // But errors should be logged and categorized properly
    });

    test("should handle different error categories simultaneously", () => {
      // Mix of different error types with unique messages
      const testId = Date.now();

      // Use exact keywords that trigger categorization
      errorTracker.trackError(
        new Error(`Database connection failed ${testId}`)
      );
      errorTracker.trackError(new Error(`Unauthorized access ${testId}`), {
        statusCode: 401,
      });
      errorTracker.trackError(new Error(`API request failed ${testId}`), {
        statusCode: 500,
      });
      errorTracker.trackError(new Error(`Validation failed ${testId}`), {
        statusCode: 400,
      });

      const stats = errorTracker.getErrorStats();

      // Verify we have the expected error categories
      const recentErrors = errorTracker.getRecentErrors(4);
      const categories = recentErrors.map((e) => e.category);

      expect(categories).toContain("database");
      expect(categories).toContain("auth");
      expect(categories).toContain("api");
      expect(categories).toContain("validation");
      expect(stats.total).toBe(4);
    });
  });

  describe("Error Context Tracking", () => {
    test("should preserve error context information", () => {
      const context = {
        userId: "user123",
        correlationId: "req-456",
        route: "/api/portfolio",
        method: "POST",
        userAgent: "test-agent",
        ip: "127.0.0.1",
      };

      errorTracker.trackError(new Error("Context test error"), context);

      const recentErrors = errorTracker.getRecentErrors(1);
      const error = recentErrors[0];

      expect(error.userId).toBe("user123");
      expect(error.correlationId).toBe("req-456");
      expect(error.route).toBe("/api/portfolio");
      expect(error.method).toBe("POST");
      expect(error.userAgent).toBe("test-agent");
      expect(error.ip).toBe("127.0.0.1");
      expect(error.context).toEqual(context);
    });

    test("should generate unique error IDs", () => {
      const error1 = errorTracker.trackError(new Error("Test 1"));
      const error2 = errorTracker.trackError(new Error("Test 2"));

      expect(error1).toBeDefined();
      expect(error2).toBeDefined();
      expect(error1).not.toBe(error2);
      expect(typeof error1).toBe("string");
      expect(typeof error2).toBe("string");
    });
  });

  describe("Error History Management", () => {
    test("should maintain error history with size limit", () => {
      const initialCount = 50;

      // Add initial errors
      for (let i = 0; i < initialCount; i++) {
        errorTracker.trackError(new Error(`History test ${i}`));
      }

      let stats = errorTracker.getErrorStats();
      expect(stats.total).toBe(initialCount);

      // Add more errors to test size limiting (maxHistorySize is 1000)
      for (let i = 0; i < 10; i++) {
        errorTracker.trackError(new Error(`Additional error ${i}`));
      }

      stats = errorTracker.getErrorStats();
      expect(stats.total).toBe(initialCount + 10);

      // Should still be within limits
      expect(stats.total).toBeLessThanOrEqual(1000);
    });

    test("should clear history when requested", () => {
      // Add some errors
      for (let i = 0; i < 5; i++) {
        errorTracker.trackError(new Error(`Clear test ${i}`));
      }

      let stats = errorTracker.getErrorStats();
      expect(stats.total).toBe(5);

      // Clear history
      errorTracker.clearHistory();

      stats = errorTracker.getErrorStats();
      expect(stats.total).toBe(0);
      expect(errorTracker.getRecentErrors().length).toBe(0);
    });
  });

  describe("Performance", () => {
    test("should handle high volume error logging efficiently", async () => {
      const startTime = Date.now();
      const promises = [];

      // Track 100 errors concurrently
      for (let i = 0; i < 100; i++) {
        promises.push(
          Promise.resolve(
            errorTracker.trackError(new Error(`Volume test ${i}`))
          )
        );
      }

      await Promise.all(promises);
      const duration = Date.now() - startTime;

      // Should complete quickly (less than 1 second for 100 errors)
      expect(duration).toBeLessThan(1000);

      const stats = errorTracker.getErrorStats();
      expect(stats.total).toBe(100);
    });

    test("should maintain performance for statistics retrieval", () => {
      // Add a moderate number of errors
      for (let i = 0; i < 50; i++) {
        errorTracker.trackError(new Error(`Perf test ${i}`));
      }

      const startTime = Date.now();

      // Perform multiple statistical operations
      const stats = errorTracker.getErrorStats();
      const recent = errorTracker.getRecentErrors(10);

      const duration = Date.now() - startTime;

      expect(duration).toBeLessThan(100); // Should be very fast (< 100ms)
      expect(stats).toBeDefined();
      expect(recent.length).toBe(10);
    });
  });

  describe("Integration Features", () => {
    test("should provide middleware integration capability", () => {
      const middleware = errorTracker.middleware();

      expect(middleware).toBeDefined();
      expect(typeof middleware).toBe("function");
      expect(middleware.length).toBe(4); // err, req, res, next parameters
    });

    test("should handle middleware error processing", () => {
      const middleware = errorTracker.middleware();
      const mockReq = {
        headers: { "x-correlation-id": "test-123" },
        method: "GET",
        route: { path: "/test" },
        ip: "127.0.0.1",
        get: jest.fn(() => "test-user-agent"),
        body: {},
        query: {},
        params: {},
      };
      const mockRes = {
        setHeader: jest.fn(),
      };
      const mockNext = jest.fn();
      const testError = new Error("Middleware test error");

      middleware(testError, mockReq, mockRes, mockNext);

      expect(mockRes.setHeader).toHaveBeenCalledWith(
        "X-Error-ID",
        expect.any(String)
      );
      expect(mockNext).toHaveBeenCalledWith(testError);

      const recentErrors = errorTracker.getRecentErrors(1);
      expect(recentErrors.length).toBe(1);
      expect(recentErrors[0].message).toBe("Middleware test error");
    });
  });
});

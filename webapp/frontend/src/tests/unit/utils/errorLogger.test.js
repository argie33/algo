/**
 * ErrorLogger Utility Unit Tests
 * Tests error logging functionality with circular reference protection
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  createComponentLogger,
  logApiError,
  logQueryError,
  logApiSuccess,
} from "../../../utils/errorLogger.js";

// Mock console methods
const consoleMock = {
  error: vi.fn(),
  warn: vi.fn(),
  info: vi.fn(),
  log: vi.fn(),
  group: vi.fn(),
  groupEnd: vi.fn(),
  time: vi.fn(),
  timeEnd: vi.fn(),
};

// Mock console globally
global.console = consoleMock;

describe("ErrorLogger Utility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("createComponentLogger", () => {
    it("creates a logger for a component", () => {
      const logger = createComponentLogger("TestComponent");

      expect(logger).toBeDefined();
      expect(typeof logger.error).toBe("function");
      expect(typeof logger.queryError).toBe("function");
      expect(typeof logger.success).toBe("function");
      expect(typeof logger.info).toBe("function");
    });

    it("logs basic messages", () => {
      const logger = createComponentLogger("TestComponent");
      const testError = new Error("test error");

      logger.error("operation", testError);
      logger.info("info message");
      logger.success("operation", { data: "test" });

      expect(consoleMock.group).toHaveBeenCalled();
      expect(consoleMock.log).toHaveBeenCalledWith(
        expect.stringContaining("ℹ️ [TestComponent] info message"),
        undefined
      );
      expect(consoleMock.log).toHaveBeenCalledWith(
        expect.stringContaining("TestComponent - operation succeeded"),
        expect.any(String)
      );
    });

    it("handles error objects", () => {
      const logger = createComponentLogger("TestComponent");
      const testError = new Error("Test error");

      logger.error("operation", testError);

      expect(consoleMock.group).toHaveBeenCalled();
      expect(consoleMock.log).toHaveBeenCalled();
      expect(consoleMock.groupEnd).toHaveBeenCalled();
    });

    it("handles circular references safely", () => {
      const logger = createComponentLogger("TestComponent");

      // Create circular reference
      const obj = { name: "test" };
      obj.self = obj;

      expect(() => logger.success("operation", obj)).not.toThrow();
      expect(consoleMock.log).toHaveBeenCalled();
    });

    it("handles function objects", () => {
      const logger = createComponentLogger("TestComponent");
      const testFunc = function namedFunction() {};

      expect(() =>
        logger.success("operation", { func: testFunc })
      ).not.toThrow();
      expect(consoleMock.log).toHaveBeenCalled();
    });

    it("handles null and undefined values", () => {
      const logger = createComponentLogger("TestComponent");

      logger.info("Null test", null);
      logger.info("Undefined test", undefined);

      expect(consoleMock.log).toHaveBeenCalledTimes(2);
    });

    it("includes component name in all log messages", () => {
      const componentName = "MyCustomComponent";
      const logger = createComponentLogger(componentName);
      const testError = new Error("test error");

      logger.info("test");
      logger.error("operation", testError);
      logger.success("operation", { data: "test" });

      expect(consoleMock.log).toHaveBeenCalled();
      expect(consoleMock.group).toHaveBeenCalled();
      expect(consoleMock.groupEnd).toHaveBeenCalled();
    });

    it("handles complex nested objects", () => {
      const logger = createComponentLogger("TestComponent");
      const complexObj = {
        level1: {
          level2: {
            level3: {
              data: "deep value",
              array: [1, 2, { nested: true }],
            },
          },
        },
      };

      logger.success("operation", complexObj);

      expect(consoleMock.log).toHaveBeenCalledWith(
        expect.stringContaining("TestComponent - operation succeeded"),
        expect.any(String)
      );
    });

    it("handles Date objects", () => {
      const logger = createComponentLogger("TestComponent");
      const testDate = new Date("2024-01-01T00:00:00.000Z");

      expect(() =>
        logger.success("operation", { timestamp: testDate })
      ).not.toThrow();
      expect(consoleMock.log).toHaveBeenCalled();
    });

    it("handles empty objects and arrays", () => {
      const logger = createComponentLogger("TestComponent");

      logger.success("operation1", {});
      logger.success("operation2", []);

      expect(consoleMock.log).toHaveBeenCalledTimes(2);
    });
  });

  describe("logApiError", () => {
    it("logs basic error information", () => {
      const error = new Error("Test error");

      logApiError("TestComponent", "fetchData", error);

      expect(consoleMock.group).toHaveBeenCalledWith(
        "❌ TestComponent - fetchData failed"
      );
      expect(consoleMock.log).toHaveBeenCalledWith(
        expect.stringContaining("📍 Component: TestComponent")
      );
      expect(consoleMock.log).toHaveBeenCalledWith(
        expect.stringContaining("🔄 Operation: fetchData")
      );
      expect(consoleMock.log).toHaveBeenCalledWith(
        expect.stringContaining("💥 Error: Test error")
      );
      expect(consoleMock.groupEnd).toHaveBeenCalled();
    });

    it("logs error with context information", () => {
      const error = new Error("API failed");
      const context = {
        url: "https://api.example.com/data",
        params: { id: 123 },
        status: 500,
        response: { message: "Internal server error" },
      };

      logApiError("ApiComponent", "getData", error, context);

      expect(consoleMock.log).toHaveBeenCalledWith(
        "🌐 URL: https://api.example.com/data"
      );
      expect(consoleMock.log).toHaveBeenCalledWith("🚦 Status: 500");
      expect(consoleMock.log).toHaveBeenCalledWith(
        "📋 Params:",
        expect.any(String)
      );
      expect(consoleMock.log).toHaveBeenCalledWith(
        "📡 Response:",
        expect.any(String)
      );
    });

    it("handles axios errors with additional details", () => {
      const axiosError = {
        message: "Request failed",
        isAxiosError: true,
        config: {
          url: "/api/test",
          method: "GET",
          baseURL: "https://api.example.com",
          timeout: 5000,
        },
        response: {
          status: 404,
          statusText: "Not Found",
          data: { error: "Resource not found" },
        },
      };

      logApiError("AxiosComponent", "fetchResource", axiosError);

      expect(consoleMock.log).toHaveBeenCalledWith(
        "🌐 Axios Error Details:",
        expect.any(String)
      );
    });

    it("handles stringification errors gracefully", () => {
      const error = new Error("Stringify error");

      // Mock JSON.stringify locally and restore it properly
      const stringifyMock = vi
        .spyOn(JSON, "stringify")
        .mockImplementationOnce(() => {
          throw new Error("Circular reference");
        });

      try {
        // Should not throw and should use safe fallback
        expect(() =>
          logApiError("StringifyComponent", "test", error)
        ).not.toThrow();

        // Should use safe fallback logging
        expect(consoleMock.log).toHaveBeenCalledWith(
          "📄 Full Error (safe fallback):",
          expect.objectContaining({
            name: "Error",
            message: "Stringify error",
          })
        );
      } finally {
        // Restore mock
        stringifyMock.mockRestore();
      }
    });

    it("handles non-Error objects", () => {
      const stringError = "Simple error string";

      logApiError("StringComponent", "processString", stringError);

      expect(consoleMock.log).toHaveBeenCalledWith(
        expect.stringContaining("💥 Error: Simple error string")
      );
    });
  });

  describe("logQueryError", () => {
    it("logs query errors with query key", () => {
      const error = new Error("Query failed");

      logQueryError("QueryComponent", "userProfile", error, { userId: 123 });

      expect(consoleMock.group).toHaveBeenCalledWith(
        "❌ QueryComponent - Query[userProfile] failed"
      );
      expect(consoleMock.log).toHaveBeenCalledWith(
        expect.stringContaining("🔄 Operation: Query[userProfile]")
      );
    });

    it("passes context correctly to logApiError", () => {
      const error = new Error("Query failed");
      const context = { userId: 456, page: 1 };

      logQueryError("QueryComponent", "userList", error, context);

      // Check that the final simplified log contains the merged context
      expect(consoleMock.log).toHaveBeenCalledWith(
        "❌ QueryComponent - Query[userList] failed:",
        expect.stringContaining("userList") // queryKey should be in context
      );
      expect(consoleMock.log).toHaveBeenCalledWith(
        "❌ QueryComponent - Query[userList] failed:",
        expect.stringContaining("456") // original context userId should be in context
      );
    });
  });

  describe("logApiSuccess", () => {
    it("logs successful operations with array result", () => {
      const result = [{ id: 1 }, { id: 2 }, { id: 3 }];

      logApiSuccess("SuccessComponent", "fetchUsers", result, { page: 1 });

      expect(consoleMock.log).toHaveBeenCalledWith(
        expect.stringContaining("✅ SuccessComponent - fetchUsers succeeded"),
        expect.stringContaining("3") // result size
      );
    });

    it("logs success with object result", () => {
      const result = { id: 1, name: "Test", data: "value" };

      logApiSuccess("ObjectComponent", "getUser", result);

      expect(consoleMock.log).toHaveBeenCalledWith(
        expect.stringContaining("✅ ObjectComponent - getUser succeeded"),
        expect.stringContaining("3") // object keys length
      );
    });

    it("logs success without result", () => {
      logApiSuccess("NoResultComponent", "deleteUser");

      expect(consoleMock.log).toHaveBeenCalledWith(
        expect.stringContaining("✅ NoResultComponent - deleteUser succeeded"),
        expect.stringContaining("N/A") // no result
      );
    });

    it("logs success with null result", () => {
      logApiSuccess("NullResultComponent", "clearCache", null);

      expect(consoleMock.log).toHaveBeenCalledWith(
        expect.stringContaining(
          "✅ NullResultComponent - clearCache succeeded"
        ),
        expect.stringContaining("N/A")
      );
    });
  });
});

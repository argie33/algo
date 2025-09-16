/**
 * Unit tests for ResponseFormatter
 */

const {
  success,
  error,
  paginated,
  validationError,
  notFound,
  unauthorized,
  forbidden,
  serverError,
} = require("../../../utils/responseFormatter");

describe("ResponseFormatter", () => {
  describe("success", () => {
    test("should format basic success response with default status code", () => {
      const data = { message: "Operation completed" };
      const result = success(data);

      expect(result).toEqual({
        response: {
          success: true,
          data,
          timestamp: expect.stringMatching(
            /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/
          ),
        },
        statusCode: 200,
      });
    });

    test("should format success response with custom status code", () => {
      const data = { id: 123 };
      const result = success(data, 201);

      expect(result.statusCode).toBe(201);
      expect(result.response.success).toBe(true);
      expect(result.response.data).toEqual(data);
    });

    test("should include metadata in response", () => {
      const data = { value: "test" };
      const meta = {
        requestId: "req-123",
        version: "1.0",
        cached: true,
      };

      const result = success(data, 200, meta);

      expect(result.response).toMatchObject({
        success: true,
        data,
        requestId: "req-123",
        version: "1.0",
        cached: true,
        timestamp: expect.any(String),
      });
    });

    test("should handle null and undefined data", () => {
      const nullResult = success(null);
      const undefinedResult = success(undefined);

      expect(nullResult.response.data).toBeNull();
      expect(undefinedResult.response.data).toBeUndefined();
    });

    test("should handle complex data objects", () => {
      const complexData = {
        stocks: [
          { symbol: "AAPL", price: 150.5 },
          { symbol: "GOOGL", price: 2800.25 },
        ],
        metadata: {
          total: 2,
          currency: "USD",
        },
      };

      const result = success(complexData);

      expect(result.response.data).toEqual(complexData);
      expect(result.response.success).toBe(true);
    });

    test("should preserve array data", () => {
      const arrayData = ["item1", "item2", "item3"];
      const result = success(arrayData);

      expect(result.response.data).toEqual(arrayData);
      expect(Array.isArray(result.response.data)).toBe(true);
    });
  });

  describe("error", () => {
    test("should format basic error response with default status code", () => {
      const message = "Something went wrong";
      const result = error(message);

      expect(result).toEqual({
        response: {
          success: false,
          error: message,
          timestamp: expect.stringMatching(
            /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/
          ),
          service: "financial-platform",
        },
        statusCode: 400,
      });
    });

    test("should format error response with custom status code", () => {
      const message = "Internal error";
      const result = error(message, 500);

      expect(result.statusCode).toBe(500);
      expect(result.response.error).toBe(message);
    });

    test("should include error details", () => {
      const message = "Database connection failed";
      const details = {
        code: "DB_CONNECTION_ERROR",
        retries: 3,
        lastAttempt: "2023-01-01T10:00:00Z",
      };

      const result = error(message, 503, details);

      expect(result.response).toMatchObject({
        success: false,
        error: message,
        service: "financial-platform",
        code: "DB_CONNECTION_ERROR",
        retries: 3,
        lastAttempt: "2023-01-01T10:00:00Z",
        timestamp: expect.any(String),
      });
    });

    test("should override default service when provided in details", () => {
      const details = { service: "custom-service" };
      const result = error("Test error", 400, details);

      expect(result.response.service).toBe("custom-service");
    });

    test("should handle empty details object", () => {
      const result = error("Test error", 400, {});

      expect(result.response.service).toBe("financial-platform");
      expect(result.response.success).toBe(false);
    });
  });

  describe("paginated", () => {
    test("should format paginated response with default pagination", () => {
      const data = [{ id: 1 }, { id: 2 }, { id: 3 }];
      const result = paginated(data, {});

      expect(result.response.success).toBe(true);
      expect(result.response.data).toEqual({
        items: data,
        pagination: {
          page: 1,
          limit: 50,
          total: 3,
          totalPages: 1,
          hasNext: false,
          hasPrev: false,
        },
      });
    });

    test("should format paginated response with custom pagination", () => {
      const data = Array.from({ length: 25 }, (_, i) => ({ id: i + 1 }));
      const pagination = {
        page: 2,
        limit: 10,
        total: 100,
        totalPages: 10,
        hasNext: true,
        hasPrev: true,
      };

      const result = paginated(data, pagination);

      expect(result.response.data).toEqual({
        items: data,
        pagination,
      });
    });

    test("should calculate totalPages correctly", () => {
      const data = [];
      const pagination = {
        total: 47,
        limit: 10,
      };

      const result = paginated(data, pagination);

      expect(result.response.data.pagination.totalPages).toBe(5); // Math.ceil(47/10)
    });

    test("should include metadata in paginated response", () => {
      const data = [{ symbol: "AAPL" }];
      const pagination = { page: 1, limit: 20 };
      const meta = {
        filters: { sector: "Technology" },
        sortBy: "market_cap",
      };

      const result = paginated(data, pagination, meta);

      expect(result.response.data.filters).toEqual({ sector: "Technology" });
      expect(result.response.data.sortBy).toBe("market_cap");
    });

    test("should handle empty data array", () => {
      const result = paginated([], { total: 0 });

      expect(result.response.data.items).toEqual([]);
      expect(result.response.data.pagination.total).toBe(0);
      expect(result.response.data.pagination.totalPages).toBe(0);
    });

    test("should use data length as default total", () => {
      const data = [1, 2, 3, 4, 5];
      const result = paginated(data, { page: 1 });

      expect(result.response.data.pagination.total).toBe(5);
    });
  });

  describe("validationError", () => {
    test("should format validation error with single error", () => {
      const singleError = "Symbol is required";
      const result = validationError(singleError);

      expect(result.statusCode).toBe(422);
      expect(result.response).toMatchObject({
        success: false,
        error: "Validation failed",
        errors: [singleError],
        type: "validation_error",
        service: "financial-platform-validation",
      });
    });

    test("should format validation error with multiple errors", () => {
      const errors = [
        "Symbol is required",
        "Price must be a positive number",
        "Date format is invalid",
      ];

      const result = validationError(errors);

      expect(result.response.errors).toEqual(errors);
    });

    test("should include default troubleshooting steps", () => {
      const result = validationError("Test error");

      expect(result.response.troubleshooting).toEqual({
        suggestion:
          "Check the provided data against the required format and constraints",
        requirements: "All required fields must be provided with valid values",
        steps: [
          "1. Review the specific validation errors listed above",
          "2. Ensure all required fields are included in your request",
          "3. Check data types and formats match the expected schema",
          "4. Verify numeric values are within acceptable ranges",
        ],
      });
    });

    test("should merge custom troubleshooting details", () => {
      const customTroubleshooting = {
        suggestion: "Custom suggestion",
        documentation: "https://docs.example.com",
      };

      const result = validationError("Error", customTroubleshooting);

      expect(result.response.troubleshooting).toMatchObject({
        suggestion: "Custom suggestion",
        documentation: "https://docs.example.com",
        requirements: "All required fields must be provided with valid values",
        steps: expect.any(Array),
      });
    });
  });

  describe("notFound", () => {
    test("should format not found error with default resource", () => {
      const result = notFound();

      expect(result.statusCode).toBe(404);
      expect(result.response).toMatchObject({
        success: false,
        error: "Resource not found",
        type: "not_found_error",
        service: "financial-platform",
      });
    });

    test("should format not found error with custom resource", () => {
      const result = notFound("Stock Symbol");

      expect(result.response.error).toBe("Stock Symbol not found");
    });

    test("should include default troubleshooting for not found", () => {
      const result = notFound("User");

      expect(result.response.troubleshooting.suggestion).toBe(
        "The requested user could not be located"
      );
      expect(result.response.troubleshooting.requirements).toBe(
        "User must exist in the system and be accessible to your account"
      );
      expect(result.response.troubleshooting.steps).toHaveLength(4);
    });

    test("should merge custom troubleshooting for not found", () => {
      const customTroubleshooting = {
        possibleCauses: ["Resource deleted", "Access denied"],
      };

      const result = notFound("Portfolio", customTroubleshooting);

      expect(result.response.troubleshooting.possibleCauses).toEqual([
        "Resource deleted",
        "Access denied",
      ]);
    });
  });

  describe("unauthorized", () => {
    test("should format unauthorized error with default message", () => {
      const result = unauthorized();

      expect(result.statusCode).toBe(401);
      expect(result.response).toMatchObject({
        success: false,
        error: "Unauthorized access",
        type: "unauthorized_error",
        service: "financial-platform-auth",
      });
    });

    test("should format unauthorized error with custom message", () => {
      const customMessage = "Token has expired";
      const result = unauthorized(customMessage);

      expect(result.response.error).toBe(customMessage);
    });

    test("should include auth-specific troubleshooting", () => {
      const result = unauthorized();

      expect(result.response.troubleshooting.suggestion).toBe(
        "Verify that you are logged in and have a valid authentication token"
      );
      expect(result.response.troubleshooting.requirements).toBe(
        "Valid JWT token in Authorization header (Bearer <token>)"
      );
      expect(result.response.troubleshooting.steps).toContain(
        "1. Check if you are logged in to the application"
      );
    });

    test("should merge custom troubleshooting for unauthorized", () => {
      const customTroubleshooting = {
        authEndpoint: "/api/auth/login",
      };

      const result = unauthorized("Session expired", customTroubleshooting);

      expect(result.response.troubleshooting.authEndpoint).toBe(
        "/api/auth/login"
      );
    });
  });

  describe("forbidden", () => {
    test("should format forbidden error with default message", () => {
      const result = forbidden();

      expect(result.statusCode).toBe(403);
      expect(result.response).toMatchObject({
        success: false,
        error: "Access forbidden",
        type: "forbidden_error",
        service: "financial-platform-auth",
      });
    });

    test("should format forbidden error with custom message", () => {
      const customMessage = "Premium feature requires subscription";
      const result = forbidden(customMessage);

      expect(result.response.error).toBe(customMessage);
    });

    test("should include permission-specific troubleshooting", () => {
      const result = forbidden();

      expect(result.response.troubleshooting.suggestion).toBe(
        "Check that your account has the required permissions for this resource"
      );
      expect(result.response.troubleshooting.requirements).toBe(
        "Sufficient user permissions or elevated access level"
      );
      expect(result.response.troubleshooting.steps).toContain(
        "2. Check if this feature requires premium access"
      );
    });
  });

  describe("serverError", () => {
    test("should format server error with default message", () => {
      const result = serverError();

      expect(result.statusCode).toBe(500);
      expect(result.response).toMatchObject({
        success: false,
        error: "Internal server error",
        type: "server_error",
        service: "financial-platform",
      });
    });

    test("should format server error with custom message", () => {
      const customMessage = "Database connection timeout";
      const result = serverError(customMessage);

      expect(result.response.error).toBe(customMessage);
    });

    test("should include server error troubleshooting", () => {
      const result = serverError();

      expect(result.response.troubleshooting.suggestion).toBe(
        "This is a temporary server issue. Please try again in a few moments"
      );
      expect(result.response.troubleshooting.steps).toContain(
        "1. Wait 30 seconds and try the request again"
      );
    });

    test("should include error details in server error", () => {
      const details = {
        errorId: "err-123",
        component: "database",
        stack: "Error at line 42...",
      };

      const result = serverError("Database failure", details);

      expect(result.response.errorId).toBe("err-123");
      expect(result.response.component).toBe("database");
      expect(result.response.stack).toBe("Error at line 42...");
    });
  });

  describe("edge cases and integration", () => {
    test("should handle timestamp generation consistently", () => {
      const result1 = success("data1");
      const result2 = error("error1");

      // Timestamps should be valid ISO strings
      expect(result1.response.timestamp).toMatch(
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/
      );
      expect(result2.response.timestamp).toMatch(
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/
      );
    });

    test("should maintain response structure consistency", () => {
      const successResult = success({ data: "test" });
      const errorResult = error("test error");

      // Both should have response and statusCode
      expect(successResult).toHaveProperty("response");
      expect(successResult).toHaveProperty("statusCode");
      expect(errorResult).toHaveProperty("response");
      expect(errorResult).toHaveProperty("statusCode");

      // Both responses should have success and timestamp
      expect(successResult.response).toHaveProperty("success");
      expect(successResult.response).toHaveProperty("timestamp");
      expect(errorResult.response).toHaveProperty("success");
      expect(errorResult.response).toHaveProperty("timestamp");
    });

    test("should handle special characters in messages", () => {
      const specialMessage =
        "Error with \"quotes\" and 'apostrophes' and <tags>";
      const result = error(specialMessage);

      expect(result.response.error).toBe(specialMessage);
    });

    test("should handle very long error messages", () => {
      const longMessage = "A".repeat(1000);
      const result = error(longMessage);

      expect(result.response.error).toBe(longMessage);
      expect(result.response.error.length).toBe(1000);
    });

    test("should preserve data types in success responses", () => {
      const mixedData = {
        string: "text",
        number: 42,
        boolean: true,
        null: null,
        undefined: undefined,
        array: [1, 2, 3],
        object: { nested: "value" },
      };

      const result = success(mixedData);

      expect(result.response.data).toEqual(mixedData);
      expect(typeof result.response.data.string).toBe("string");
      expect(typeof result.response.data.number).toBe("number");
      expect(typeof result.response.data.boolean).toBe("boolean");
    });
  });
});

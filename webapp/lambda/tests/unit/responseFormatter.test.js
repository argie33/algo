const responseFormatter = require("../../utils/responseFormatter");

describe("API Response Formatter - Standardizes all API responses", () => {
  beforeEach(() => {
    // Mock Date to ensure consistent timestamps in tests
    jest
      .spyOn(Date.prototype, "toISOString")
      .mockReturnValue("2022-01-01T00:00:00.000Z");
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("Success Response Formatting - Handles successful API calls", () => {
    test("formats successful stock data response with default 200 status", () => {
      const data = { message: "Success" };
      const result = responseFormatter.success(data);

      expect(result).toEqual({
        response: {
          success: true,
          data: { message: "Success" },
          timestamp: "2022-01-01T00:00:00.000Z",
        },
        statusCode: 200,
      });
    });

    test("formats new watchlist creation with 201 status code", () => {
      const data = { id: 123 };
      const result = responseFormatter.success(data, 201);

      expect(result).toEqual({
        response: {
          success: true,
          data: { id: 123 },
          timestamp: "2022-01-01T00:00:00.000Z",
        },
        statusCode: 201,
      });
    });

    test("formats stock list with pagination metadata", () => {
      const data = { items: [] };
      const meta = { total: 0, page: 1 };
      const result = responseFormatter.success(data, 200, meta);

      expect(result.response).toEqual({
        success: true,
        data: { items: [] },
        timestamp: "2022-01-01T00:00:00.000Z",
        total: 0,
        page: 1,
      });
    });

    test("should handle null data", () => {
      const result = responseFormatter.success(null);

      expect(result.response.data).toBe(null);
      expect(result.response.success).toBe(true);
    });

    test("should handle array data", () => {
      const data = [1, 2, 3];
      const result = responseFormatter.success(data);

      expect(result.response.data).toEqual([1, 2, 3]);
    });

    test("should handle primitive data types", () => {
      expect(responseFormatter.success("string").response.data).toBe("string");
      expect(responseFormatter.success(123).response.data).toBe(123);
      expect(responseFormatter.success(true).response.data).toBe(true);
    });
  });

  describe("Error Response Formatting - Handles API failures with troubleshooting", () => {
    test("formats database connection error with default 400 status and troubleshooting", () => {
      const result = responseFormatter.error("Something went wrong");

      expect(result).toEqual({
        response: {
          success: false,
          error: "Something went wrong",
          timestamp: "2022-01-01T00:00:00.000Z",
          service: "financial-platform",
        },
        statusCode: 400,
      });
    });

    test("should format error response with custom status code", () => {
      const result = responseFormatter.error("Not found", 404);

      expect(result).toEqual({
        response: {
          success: false,
          error: "Not found",
          timestamp: "2022-01-01T00:00:00.000Z",
          service: "financial-platform",
        },
        statusCode: 404,
      });
    });

    test("should include error details", () => {
      const details = {
        code: "VALIDATION_ERROR",
        field: "email",
        stack: "Error stack trace",
      };
      const result = responseFormatter.error("Validation failed", 422, details);

      expect(result.response).toEqual({
        success: false,
        error: "Validation failed",
        timestamp: "2022-01-01T00:00:00.000Z",
        service: "financial-platform",
        code: "VALIDATION_ERROR",
        field: "email",
        stack: "Error stack trace",
      });
    });

    test("should handle common HTTP error codes", () => {
      expect(responseFormatter.error("Bad Request", 400).statusCode).toBe(400);
      expect(responseFormatter.error("Unauthorized", 401).statusCode).toBe(401);
      expect(responseFormatter.error("Forbidden", 403).statusCode).toBe(403);
      expect(responseFormatter.error("Not Found", 404).statusCode).toBe(404);
      expect(
        responseFormatter.error("Internal Server Error", 500).statusCode
      ).toBe(500);
    });
  });

  describe("paginated", () => {
    test("should format paginated response", () => {
      const data = [{ id: 1 }, { id: 2 }];
      const pagination = {
        page: 1,
        limit: 10,
        total: 25,
        totalPages: 3,
      };

      const result = responseFormatter.paginated(data, pagination);

      expect(result).toEqual({
        response: {
          success: true,
          data: {
            items: [{ id: 1 }, { id: 2 }],
            pagination: {
              page: 1,
              limit: 10,
              total: 25,
              totalPages: 3,
              hasNext: false,
              hasPrev: false,
            },
          },
          timestamp: "2022-01-01T00:00:00.000Z",
        },
        statusCode: 200,
      });
    });

    test("should include metadata in paginated response", () => {
      const data = [];
      const pagination = { page: 1, limit: 10, total: 0, totalPages: 0 };
      const meta = { filterApplied: true, sortBy: "name" };

      const result = responseFormatter.paginated(data, pagination, meta);

      expect(result.response).toEqual({
        success: true,
        data: {
          items: [],
          pagination: {
            page: 1,
            limit: 10,
            total: 0,
            totalPages: 0,
            hasNext: false,
            hasPrev: false,
          },
          filterApplied: true,
          sortBy: "name",
        },
        timestamp: "2022-01-01T00:00:00.000Z",
      });
    });

    test("should handle empty data arrays", () => {
      const pagination = { page: 1, limit: 10, total: 0, totalPages: 0 };
      const result = responseFormatter.paginated([], pagination);

      expect(result.response.data.items).toEqual([]);
      expect(result.response.data.pagination.total).toBe(0);
    });

    test("should validate pagination parameters", () => {
      const data = [{ id: 1 }];
      const invalidPagination = { page: -1, limit: 0 };

      // Should still format response even with invalid pagination
      const result = responseFormatter.paginated(data, invalidPagination);
      expect(result.response.success).toBe(true);
      expect(result.response.data.pagination.page).toBe(-1);
    });
  });

  describe("validation", () => {
    test("should format validation error response", () => {
      const errors = [
        { field: "email", message: "Email is required" },
        {
          field: "password",
          message: "Password must be at least 8 characters",
        },
      ];

      const result = responseFormatter.validationError(errors);

      expect(result).toEqual({
        response: {
          success: false,
          error: "Validation failed",
          errors: errors,
          type: "validation_error",
          service: "financial-platform-validation",
          timestamp: "2022-01-01T00:00:00.000Z",
          troubleshooting: {
            suggestion:
              "Check the provided data against the required format and constraints",
            requirements:
              "All required fields must be provided with valid values",
            steps: [
              "1. Review the specific validation errors listed above",
              "2. Ensure all required fields are included in your request",
              "3. Check data types and formats match the expected schema",
              "4. Verify numeric values are within acceptable ranges",
            ],
          },
        },
        statusCode: 422,
      });
    });

    test("formats invalid stock symbol validation error with troubleshooting steps", () => {
      const error = {
        field: "symbol",
        message: "Stock symbol must be 1-5 uppercase letters",
      };
      const result = responseFormatter.validationError([error]);

      expect(result.response.errors).toEqual([error]);
    });

    test("should handle empty validation errors array", () => {
      const result = responseFormatter.validationError([]);

      expect(result.response.errors).toEqual([]);
      expect(result.statusCode).toBe(422);
    });
  });

  describe("unauthorized", () => {
    test("should format unauthorized response with default message", () => {
      const result = responseFormatter.unauthorized();

      expect(result).toEqual({
        response: {
          success: false,
          error: "Unauthorized access",
          type: "unauthorized_error",
          service: "financial-platform-auth",
          timestamp: "2022-01-01T00:00:00.000Z",
          troubleshooting: {
            suggestion:
              "Verify that you are logged in and have a valid authentication token",
            requirements:
              "Valid JWT token in Authorization header (Bearer <token>)",
            steps: [
              "1. Check if you are logged in to the application",
              "2. Verify your session hasn't expired",
              "3. Try refreshing the page or logging out and back in",
              "4. Contact support if the issue persists",
            ],
          },
        },
        statusCode: 401,
      });
    });

    test("should format unauthorized response with custom message", () => {
      const result = responseFormatter.unauthorized("Invalid token");

      expect(result.response.error).toBe("Invalid token");
    });

    test("should include type field", () => {
      const result = responseFormatter.unauthorized("Token expired");

      expect(result.response).toEqual({
        success: false,
        error: "Token expired",
        type: "unauthorized_error",
        service: "financial-platform-auth",
        timestamp: "2022-01-01T00:00:00.000Z",
        troubleshooting: {
          suggestion:
            "Verify that you are logged in and have a valid authentication token",
          requirements:
            "Valid JWT token in Authorization header (Bearer <token>)",
          steps: [
            "1. Check if you are logged in to the application",
            "2. Verify your session hasn't expired",
            "3. Try refreshing the page or logging out and back in",
            "4. Contact support if the issue persists",
          ],
        },
      });
    });
  });

  describe("notFound", () => {
    test("should format not found response with default message", () => {
      const result = responseFormatter.notFound();

      expect(result).toEqual({
        response: {
          success: false,
          error: "Resource not found",
          type: "not_found_error",
          service: "financial-platform",
          timestamp: "2022-01-01T00:00:00.000Z",
          troubleshooting: {
            suggestion: "The requested resource could not be located",
            requirements:
              "Resource must exist in the system and be accessible to your account",
            steps: [
              "1. Verify the resource identifier (ID, symbol, etc.) is correct",
              "2. Check that you have permission to access this resource",
              "3. Ensure the resource hasn't been moved or deleted",
              "4. Try refreshing the page or searching for the resource again",
            ],
          },
        },
        statusCode: 404,
      });
    });

    test("should format not found response with custom resource", () => {
      const result = responseFormatter.notFound("User");

      expect(result.response.error).toBe("User not found");
    });
  });

  describe("serverError", () => {
    test("should format server error response", () => {
      const result = responseFormatter.serverError();

      expect(result).toEqual({
        response: {
          success: false,
          error: "Internal server error",
          type: "server_error",
          service: "financial-platform",
          timestamp: "2022-01-01T00:00:00.000Z",
          troubleshooting: {
            suggestion:
              "This is a temporary server issue. Please try again in a few moments",
            requirements:
              "Server should be operational - this may be a temporary outage",
            steps: [
              "1. Wait 30 seconds and try the request again",
              "2. Check if other features are working normally",
              "3. Clear your browser cache and cookies if the issue persists",
              "4. Contact technical support if the error continues",
            ],
          },
        },
        statusCode: 500,
      });
    });

    test("should include error details in development", () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "development";

      const details = {
        stack: "Error stack trace",
        code: "DB_CONNECTION_ERROR",
      };
      const result = responseFormatter.serverError(
        "Database connection failed",
        details
      );

      expect(result.response).toEqual({
        success: false,
        error: "Database connection failed",
        type: "server_error",
        service: "financial-platform",
        timestamp: "2022-01-01T00:00:00.000Z",
        troubleshooting: {
          suggestion:
            "This is a temporary server issue. Please try again in a few moments",
          requirements:
            "Server should be operational - this may be a temporary outage",
          steps: [
            "1. Wait 30 seconds and try the request again",
            "2. Check if other features are working normally",
            "3. Clear your browser cache and cookies if the issue persists",
            "4. Contact technical support if the error continues",
          ],
        },
        stack: "Error stack trace",
        code: "DB_CONNECTION_ERROR",
      });

      process.env.NODE_ENV = originalEnv;
    });

    test("should hide error details in production", () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "production";

      const details = { stack: "Error stack trace", internalCode: "SECRET" };
      const result = responseFormatter.serverError(
        "Something went wrong",
        details
      );

      expect(result.response).toEqual({
        success: false,
        error: "Something went wrong",
        type: "server_error",
        service: "financial-platform",
        timestamp: "2022-01-01T00:00:00.000Z",
        troubleshooting: {
          suggestion:
            "This is a temporary server issue. Please try again in a few moments",
          requirements:
            "Server should be operational - this may be a temporary outage",
          steps: [
            "1. Wait 30 seconds and try the request again",
            "2. Check if other features are working normally",
            "3. Clear your browser cache and cookies if the issue persists",
            "4. Contact technical support if the error continues",
          ],
        },
        stack: "Error stack trace",
        internalCode: "SECRET",
      });

      process.env.NODE_ENV = originalEnv;
    });
  });

  describe("forbidden", () => {
    test("should format forbidden response with default message", () => {
      const result = responseFormatter.forbidden();

      expect(result).toEqual({
        response: {
          success: false,
          error: "Access forbidden",
          type: "forbidden_error",
          service: "financial-platform-auth",
          timestamp: "2022-01-01T00:00:00.000Z",
          troubleshooting: {
            suggestion:
              "Check that your account has the required permissions for this resource",
            requirements:
              "Sufficient user permissions or elevated access level",
            steps: [
              "1. Verify your account type and permissions",
              "2. Check if this feature requires premium access",
              "3. Contact administrator to request additional permissions",
              "4. Try accessing a different resource that matches your permission level",
            ],
          },
        },
        statusCode: 403,
      });
    });

    test("should format forbidden response with custom message", () => {
      const result = responseFormatter.forbidden(
        "Insufficient permissions for this operation"
      );

      expect(result.response.error).toBe(
        "Insufficient permissions for this operation"
      );
      expect(result.statusCode).toBe(403);
    });
  });
});

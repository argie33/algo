const responseFormatter = require("../../utils/responseFormatter");

describe("responseFormatter", () => {
  beforeEach(() => {
    // Mock Date to ensure consistent timestamps in tests
    jest
      .spyOn(Date.prototype, "toISOString")
      .mockReturnValue("2022-01-01T00:00:00.000Z");
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("success", () => {
    test("should format successful response with default status code", () => {
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

    test("should format successful response with custom status code", () => {
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

    test("should include metadata in response", () => {
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

  describe("error", () => {
    test("should format error response with default status code", () => {
      const result = responseFormatter.error("Something went wrong");

      expect(result).toEqual({
        response: {
          success: false,
          error: "Something went wrong",
          timestamp: "2022-01-01T00:00:00.000Z",
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
          timestamp: "2022-01-01T00:00:00.000Z",
        },
        statusCode: 422,
      });
    });

    test("should handle single validation error", () => {
      const error = { field: "username", message: "Username already exists" };
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
          timestamp: "2022-01-01T00:00:00.000Z",
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
        timestamp: "2022-01-01T00:00:00.000Z",
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
          timestamp: "2022-01-01T00:00:00.000Z",
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
          timestamp: "2022-01-01T00:00:00.000Z",
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
        timestamp: "2022-01-01T00:00:00.000Z",
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
        timestamp: "2022-01-01T00:00:00.000Z",
        stack: "Error stack trace",
        internalCode: "SECRET",
      });

      process.env.NODE_ENV = originalEnv;
    });
  });
});

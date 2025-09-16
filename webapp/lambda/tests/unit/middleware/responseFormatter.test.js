const express = require("express");
const request = require("supertest");
const responseFormatterMiddleware = require("../../../middleware/responseFormatter");

// Mock the responseFormatter utility
jest.mock("../../../utils/responseFormatter", () => ({
  success: jest.fn(),
  error: jest.fn(),
  paginated: jest.fn(),
  validationError: jest.fn(),
  notFound: jest.fn(),
  unauthorized: jest.fn(),
  forbidden: jest.fn(),
  serverError: jest.fn(),
}));

const responseFormatter = require("../../../utils/responseFormatter");

const app = express();
app.use(responseFormatterMiddleware);

describe("Response Formatter Middleware", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("Middleware Setup", () => {
    test("should add API version header", async () => {
      app.get("/test-header", (req, res) => {
        res.json({ test: true });
      });

      const response = await request(app).get("/test-header");
      expect(response.headers["api-version"]).toBe("v1.0");
    });

    test("should add all response methods to res object", async () => {
      let resMethods;
      app.get("/test-methods", (req, res) => {
        resMethods = {
          success: typeof res.success,
          error: typeof res.error,
          paginated: typeof res.paginated,
          validationError: typeof res.validationError,
          notFound: typeof res.notFound,
          unauthorized: typeof res.unauthorized,
          forbidden: typeof res.forbidden,
          serverError: typeof res.serverError,
        };
        res.json({ test: true });
      });

      await request(app).get("/test-methods");

      expect(resMethods.success).toBe("function");
      expect(resMethods.error).toBe("function");
      expect(resMethods.paginated).toBe("function");
      expect(resMethods.validationError).toBe("function");
      expect(resMethods.notFound).toBe("function");
      expect(resMethods.unauthorized).toBe("function");
      expect(resMethods.forbidden).toBe("function");
      expect(resMethods.serverError).toBe("function");
    });
  });

  describe("res.success method", () => {
    test("should call responseFormatter.success with correct parameters", async () => {
      const mockData = { result: "test" };
      const mockMeta = { total: 10 };

      responseFormatter.success.mockReturnValue({
        statusCode: 200,
        response: { success: true, data: mockData },
      });

      app.get("/test-success", (req, res) => {
        res.success(mockData, 200, mockMeta);
      });

      const response = await request(app).get("/test-success");

      expect(responseFormatter.success).toHaveBeenCalledWith(
        mockData,
        200,
        mockMeta
      );
      expect(response.status).toBe(200);
      expect(response.body).toEqual({ success: true, data: mockData });
    });

    test("should use default status code 200", async () => {
      const mockData = { result: "test" };

      responseFormatter.success.mockReturnValue({
        statusCode: 200,
        response: { success: true, data: mockData },
      });

      app.get("/test-success-default", (req, res) => {
        res.success(mockData);
      });

      await request(app).get("/test-success-default");

      expect(responseFormatter.success).toHaveBeenCalledWith(mockData, 200, {});
    });

    test("should use default empty meta object", async () => {
      const mockData = { result: "test" };

      responseFormatter.success.mockReturnValue({
        statusCode: 201,
        response: { success: true, data: mockData },
      });

      app.get("/test-success-no-meta", (req, res) => {
        res.success(mockData, 201);
      });

      await request(app).get("/test-success-no-meta");

      expect(responseFormatter.success).toHaveBeenCalledWith(mockData, 201, {});
    });
  });

  describe("res.error method", () => {
    test("should call responseFormatter.error with correct parameters", async () => {
      const mockMessage = "Test error";
      const mockDetails = { field: "email" };

      responseFormatter.error.mockReturnValue({
        statusCode: 400,
        response: { success: false, error: mockMessage },
      });

      app.get("/test-error", (req, res) => {
        res.error(mockMessage, 400, mockDetails);
      });

      const response = await request(app).get("/test-error");

      expect(responseFormatter.error).toHaveBeenCalledWith(
        mockMessage,
        400,
        mockDetails
      );
      expect(response.status).toBe(400);
      expect(response.body).toEqual({ success: false, error: mockMessage });
    });

    test("should use default status code 400", async () => {
      const mockMessage = "Test error";

      responseFormatter.error.mockReturnValue({
        statusCode: 400,
        response: { success: false, error: mockMessage },
      });

      app.get("/test-error-default", (req, res) => {
        res.error(mockMessage);
      });

      await request(app).get("/test-error-default");

      expect(responseFormatter.error).toHaveBeenCalledWith(
        mockMessage,
        400,
        {}
      );
    });
  });

  describe("res.paginated method", () => {
    test("should call responseFormatter.paginated with correct parameters", async () => {
      const mockData = [{ id: 1 }, { id: 2 }];
      const mockPagination = { page: 1, limit: 10, total: 100 };
      const mockMeta = { query: "test" };

      responseFormatter.paginated.mockReturnValue({
        statusCode: 200,
        response: { success: true, data: mockData, pagination: mockPagination },
      });

      app.get("/test-paginated", (req, res) => {
        res.paginated(mockData, mockPagination, mockMeta);
      });

      const response = await request(app).get("/test-paginated");

      expect(responseFormatter.paginated).toHaveBeenCalledWith(
        mockData,
        mockPagination,
        mockMeta
      );
      expect(response.status).toBe(200);
      expect(response.body).toEqual({
        success: true,
        data: mockData,
        pagination: mockPagination,
      });
    });

    test("should use default empty meta object", async () => {
      const mockData = [{ id: 1 }];
      const mockPagination = { page: 1, limit: 10, total: 1 };

      responseFormatter.paginated.mockReturnValue({
        statusCode: 200,
        response: { success: true, data: mockData },
      });

      app.get("/test-paginated-no-meta", (req, res) => {
        res.paginated(mockData, mockPagination);
      });

      await request(app).get("/test-paginated-no-meta");

      expect(responseFormatter.paginated).toHaveBeenCalledWith(
        mockData,
        mockPagination,
        {}
      );
    });
  });

  describe("res.validationError method", () => {
    test("should call responseFormatter.validationError with correct parameters", async () => {
      const mockErrors = [
        { field: "email", message: "Invalid email format" },
        { field: "password", message: "Password too short" },
      ];

      responseFormatter.validationError.mockReturnValue({
        statusCode: 422,
        response: { success: false, errors: mockErrors },
      });

      app.get("/test-validation-error", (req, res) => {
        res.validationError(mockErrors);
      });

      const response = await request(app).get("/test-validation-error");

      expect(responseFormatter.validationError).toHaveBeenCalledWith(
        mockErrors
      );
      expect(response.status).toBe(422);
      expect(response.body).toEqual({ success: false, errors: mockErrors });
    });
  });

  describe("res.notFound method", () => {
    test("should call responseFormatter.notFound with custom resource", async () => {
      const mockResource = "User";

      responseFormatter.notFound.mockReturnValue({
        statusCode: 404,
        response: { success: false, error: "User not found" },
      });

      app.get("/test-not-found", (req, res) => {
        res.notFound(mockResource);
      });

      const response = await request(app).get("/test-not-found");

      expect(responseFormatter.notFound).toHaveBeenCalledWith(mockResource);
      expect(response.status).toBe(404);
      expect(response.body).toEqual({
        success: false,
        error: "User not found",
      });
    });

    test("should use default resource name", async () => {
      responseFormatter.notFound.mockReturnValue({
        statusCode: 404,
        response: { success: false, error: "Resource not found" },
      });

      app.get("/test-not-found-default", (req, res) => {
        res.notFound();
      });

      await request(app).get("/test-not-found-default");

      expect(responseFormatter.notFound).toHaveBeenCalledWith("Resource");
    });
  });

  describe("res.unauthorized method", () => {
    test("should call responseFormatter.unauthorized with custom message", async () => {
      const mockMessage = "Invalid token";

      responseFormatter.unauthorized.mockReturnValue({
        statusCode: 401,
        response: { success: false, error: mockMessage },
      });

      app.get("/test-unauthorized", (req, res) => {
        res.unauthorized(mockMessage);
      });

      const response = await request(app).get("/test-unauthorized");

      expect(responseFormatter.unauthorized).toHaveBeenCalledWith(mockMessage);
      expect(response.status).toBe(401);
      expect(response.body).toEqual({ success: false, error: mockMessage });
    });

    test("should use default message", async () => {
      const defaultMessage = "Unauthorized access";

      responseFormatter.unauthorized.mockReturnValue({
        statusCode: 401,
        response: { success: false, error: defaultMessage },
      });

      app.get("/test-unauthorized-default", (req, res) => {
        res.unauthorized();
      });

      await request(app).get("/test-unauthorized-default");

      expect(responseFormatter.unauthorized).toHaveBeenCalledWith(
        defaultMessage
      );
    });
  });

  describe("res.forbidden method", () => {
    test("should call responseFormatter.forbidden with custom message", async () => {
      const mockMessage = "Insufficient permissions";

      responseFormatter.forbidden.mockReturnValue({
        statusCode: 403,
        response: { success: false, error: mockMessage },
      });

      app.get("/test-forbidden", (req, res) => {
        res.forbidden(mockMessage);
      });

      const response = await request(app).get("/test-forbidden");

      expect(responseFormatter.forbidden).toHaveBeenCalledWith(mockMessage);
      expect(response.status).toBe(403);
      expect(response.body).toEqual({ success: false, error: mockMessage });
    });

    test("should use default message", async () => {
      const defaultMessage = "Access forbidden";

      responseFormatter.forbidden.mockReturnValue({
        statusCode: 403,
        response: { success: false, error: defaultMessage },
      });

      app.get("/test-forbidden-default", (req, res) => {
        res.forbidden();
      });

      await request(app).get("/test-forbidden-default");

      expect(responseFormatter.forbidden).toHaveBeenCalledWith(defaultMessage);
    });
  });

  describe("res.serverError method", () => {
    test("should call responseFormatter.serverError with custom message and details", async () => {
      const mockMessage = "Database connection failed";
      const mockDetails = { host: "localhost", port: 5432 };

      responseFormatter.serverError.mockReturnValue({
        statusCode: 500,
        response: { success: false, error: mockMessage },
      });

      app.get("/test-server-error", (req, res) => {
        res.serverError(mockMessage, mockDetails);
      });

      const response = await request(app).get("/test-server-error");

      expect(responseFormatter.serverError).toHaveBeenCalledWith(
        mockMessage,
        mockDetails
      );
      expect(response.status).toBe(500);
      expect(response.body).toEqual({ success: false, error: mockMessage });
    });

    test("should use default message and empty details", async () => {
      const defaultMessage = "Internal server error";

      responseFormatter.serverError.mockReturnValue({
        statusCode: 500,
        response: { success: false, error: defaultMessage },
      });

      app.get("/test-server-error-default", (req, res) => {
        res.serverError();
      });

      await request(app).get("/test-server-error-default");

      expect(responseFormatter.serverError).toHaveBeenCalledWith(
        defaultMessage,
        {}
      );
    });
  });

  describe("Integration Tests", () => {
    test("should work with multiple methods in sequence", async () => {
      responseFormatter.success.mockReturnValue({
        statusCode: 200,
        response: { success: true, data: "test" },
      });

      responseFormatter.error.mockReturnValue({
        statusCode: 400,
        response: { success: false, error: "test error" },
      });

      app.get("/test-sequence", (req, res) => {
        if (req.query.type === "error") {
          return res.error("test error");
        }
        res.success("test");
      });

      const successResponse = await request(app).get("/test-sequence");
      const errorResponse = await request(app).get("/test-sequence?type=error");

      expect(successResponse.status).toBe(200);
      expect(errorResponse.status).toBe(400);
      expect(responseFormatter.success).toHaveBeenCalled();
      expect(responseFormatter.error).toHaveBeenCalled();
    });

    test("should maintain API version header across all responses", async () => {
      const methods = [
        {
          path: "/success",
          setup: () =>
            responseFormatter.success.mockReturnValue({
              statusCode: 200,
              response: {},
            }),
        },
        {
          path: "/error",
          setup: () =>
            responseFormatter.error.mockReturnValue({
              statusCode: 400,
              response: {},
            }),
        },
        {
          path: "/not-found",
          setup: () =>
            responseFormatter.notFound.mockReturnValue({
              statusCode: 404,
              response: {},
            }),
        },
        {
          path: "/unauthorized",
          setup: () =>
            responseFormatter.unauthorized.mockReturnValue({
              statusCode: 401,
              response: {},
            }),
        },
        {
          path: "/forbidden",
          setup: () =>
            responseFormatter.forbidden.mockReturnValue({
              statusCode: 403,
              response: {},
            }),
        },
        {
          path: "/server-error",
          setup: () =>
            responseFormatter.serverError.mockReturnValue({
              statusCode: 500,
              response: {},
            }),
        },
      ];

      methods.forEach((method) => {
        method.setup();
        app.get(method.path, (req, res) => {
          switch (method.path) {
            case "/success":
              res.success({});
              break;
            case "/error":
              res.error("error");
              break;
            case "/not-found":
              res.notFound();
              break;
            case "/unauthorized":
              res.unauthorized();
              break;
            case "/forbidden":
              res.forbidden();
              break;
            case "/server-error":
              res.serverError();
              break;
          }
        });
      });

      for (const method of methods) {
        const response = await request(app).get(method.path);
        expect(response.headers["api-version"]).toBe("v1.0");
      }
    });

    test("should handle chained method calls", async () => {
      let methodsCalled = [];

      app.get("/test-chain", (req, res) => {
        methodsCalled.push("middleware");

        // This should only call the first response method
        res.success({ test: true });
        methodsCalled.push("success");

        // This shouldn't execute because response was already sent
        try {
          res.error("error");
          methodsCalled.push("error");
        } catch (e) {
          methodsCalled.push("error-caught");
        }
      });

      responseFormatter.success.mockReturnValue({
        statusCode: 200,
        response: { success: true, data: { test: true } },
      });

      await request(app).get("/test-chain");

      expect(methodsCalled).toContain("middleware");
      expect(methodsCalled).toContain("success");
      // The error method may or may not be called depending on Express behavior
      expect(responseFormatter.success).toHaveBeenCalled();
    });
  });
});

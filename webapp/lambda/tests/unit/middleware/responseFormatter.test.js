const express = require("express");
const request = require("supertest");
const responseFormatterMiddleware = require("../../../middleware/responseFormatter");

const app = express();
app.use(responseFormatterMiddleware);

describe("Response Formatter Middleware", () => {
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
    test("should return success response with correct parameters", async () => {
      const mockData = { result: "test" };
      const mockMeta = { total: 10 };

      app.get("/test-success", (req, res) => {
        res.success(mockData, 200, mockMeta);
      });

      const response = await request(app).get("/test-success");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockData);
      expect(response.body.total).toBe(10);
      expect(response.body.timestamp).toBeDefined();
    });

    test("should use default status code 200", async () => {
      const mockData = { result: "test" };

      app.get("/test-success-default", (req, res) => {
        res.success(mockData);
      });

      const response = await request(app).get("/test-success-default");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockData);
    });

    test("should use custom status code", async () => {
      const mockData = { result: "created" };

      app.get("/test-success-201", (req, res) => {
        res.success(mockData, 201);
      });

      const response = await request(app).get("/test-success-201");

      expect(response.status).toBe(201);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual(mockData);
    });
  });

  describe("res.error method", () => {
    test("should return error response with correct parameters", async () => {
      const mockMessage = "Test error";
      const mockDetails = { field: "email" };

      app.get("/test-error", (req, res) => {
        res.error(mockMessage, 400, mockDetails);
      });

      const response = await request(app).get("/test-error");

      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe(mockMessage);
      expect(response.body.field).toBe("email");
      expect(response.body.timestamp).toBeDefined();
    });

    test("should use default status code 400", async () => {
      const mockMessage = "Test error";

      app.get("/test-error-default", (req, res) => {
        res.error(mockMessage);
      });

      const response = await request(app).get("/test-error-default");

      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe(mockMessage);
    });

    test("should include service in error response", async () => {
      const mockMessage = "Test error";

      app.get("/test-error-service", (req, res) => {
        res.error(mockMessage, 400, {});
      });

      const response = await request(app).get("/test-error-service");

      expect(response.body.service).toBe("financial-platform");
    });
  });

  describe("res.paginated method", () => {
    test("should return paginated response with custom pagination", async () => {
      const mockData = [{ id: 1 }, { id: 2 }];
      const mockPagination = { page: 1, limit: 10, total: 100 };
      const mockMeta = { query: "test" };

      app.get("/test-paginated", (req, res) => {
        res.paginated(mockData, mockPagination, mockMeta);
      });

      const response = await request(app).get("/test-paginated");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data.items).toEqual(mockData);
      expect(response.body.data.pagination.page).toBe(1);
      expect(response.body.data.pagination.limit).toBe(10);
      expect(response.body.data.pagination.total).toBe(100);
      expect(response.body.data.query).toBe("test");
    });

    test("should calculate pagination correctly", async () => {
      const mockData = [];
      const mockPagination = { total: 47, limit: 10 };

      app.get("/test-paginated-calc", (req, res) => {
        res.paginated(mockData, mockPagination);
      });

      const response = await request(app).get("/test-paginated-calc");

      expect(response.body.data.pagination.totalPages).toBe(5);
    });
  });

  describe("res.validationError method", () => {
    test("should return validation error response", async () => {
      const mockErrors = [
        { field: "email", message: "Invalid email format" },
        { field: "password", message: "Password too short" },
      ];

      app.get("/test-validation-error", (req, res) => {
        res.validationError(mockErrors);
      });

      const response = await request(app).get("/test-validation-error");

      expect(response.status).toBe(422);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Validation failed");
      expect(response.body.errors).toEqual(mockErrors);
      expect(response.body.type).toBe("validation_error");
      expect(response.body.troubleshooting).toBeDefined();
    });

    test("should convert single error to array", async () => {
      const singleError = "Email is required";

      app.get("/test-validation-single", (req, res) => {
        res.validationError(singleError);
      });

      const response = await request(app).get("/test-validation-single");

      expect(Array.isArray(response.body.errors)).toBe(true);
      expect(response.body.errors[0]).toBe(singleError);
    });
  });

  describe("res.notFound method", () => {
    test("should return not found error with custom resource", async () => {
      const mockResource = "User";

      app.get("/test-not-found", (req, res) => {
        res.notFound(mockResource);
      });

      const response = await request(app).get("/test-not-found");

      expect(response.status).toBe(404);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("User not found");
      expect(response.body.type).toBe("not_found_error");
      expect(response.body.troubleshooting).toBeDefined();
    });

    test("should use default resource name", async () => {
      app.get("/test-not-found-default", (req, res) => {
        res.notFound();
      });

      const response = await request(app).get("/test-not-found-default");

      expect(response.status).toBe(404);
      expect(response.body.error).toBe("Resource not found");
    });
  });

  describe("res.unauthorized method", () => {
    test("should return unauthorized error with custom message", async () => {
      const mockMessage = "Invalid token";

      app.get("/test-unauthorized", (req, res) => {
        res.unauthorized(mockMessage);
      });

      const response = await request(app).get("/test-unauthorized");

      expect(response.status).toBe(401);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe(mockMessage);
      expect(response.body.type).toBe("unauthorized_error");
      expect(response.body.troubleshooting).toBeDefined();
    });

    test("should use default message", async () => {
      const defaultMessage = "Unauthorized access";

      app.get("/test-unauthorized-default", (req, res) => {
        res.unauthorized();
      });

      const response = await request(app).get("/test-unauthorized-default");

      expect(response.status).toBe(401);
      expect(response.body.error).toBe(defaultMessage);
    });
  });

  describe("res.forbidden method", () => {
    test("should return forbidden error with custom message", async () => {
      const mockMessage = "Insufficient permissions";

      app.get("/test-forbidden", (req, res) => {
        res.forbidden(mockMessage);
      });

      const response = await request(app).get("/test-forbidden");

      expect(response.status).toBe(403);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe(mockMessage);
      expect(response.body.type).toBe("forbidden_error");
      expect(response.body.troubleshooting).toBeDefined();
    });

    test("should use default message", async () => {
      const defaultMessage = "Access forbidden";

      app.get("/test-forbidden-default", (req, res) => {
        res.forbidden();
      });

      const response = await request(app).get("/test-forbidden-default");

      expect(response.status).toBe(403);
      expect(response.body.error).toBe(defaultMessage);
    });
  });

  describe("res.serverError method", () => {
    test("should return server error with custom message and details", async () => {
      const mockMessage = "Database connection failed";
      const mockDetails = { host: "localhost", port: 5432 };

      app.get("/test-server-error", (req, res) => {
        res.serverError(mockMessage, mockDetails);
      });

      const response = await request(app).get("/test-server-error");

      expect(response.status).toBe(500);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe(mockMessage);
      expect(response.body.type).toBe("server_error");
      expect(response.body.host).toBe("localhost");
      expect(response.body.port).toBe(5432);
      expect(response.body.troubleshooting).toBeDefined();
    });

    test("should use default message and empty details", async () => {
      const defaultMessage = "Internal server error";

      app.get("/test-server-error-default", (req, res) => {
        res.serverError();
      });

      const response = await request(app).get("/test-server-error-default");

      expect(response.status).toBe(500);
      expect(response.body.error).toBe(defaultMessage);
    });
  });

  describe("Integration Tests", () => {
    test("should work with multiple methods in sequence", async () => {
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
      expect(successResponse.body.success).toBe(true);
      expect(errorResponse.body.success).toBe(false);
    });

    test("should maintain API version header across all responses", async () => {
      app.get("/api/success", (req, res) => res.success({}));
      app.get("/api/error", (req, res) => res.error("error"));
      app.get("/api/not-found", (req, res) => res.notFound());
      app.get("/api/unauthorized", (req, res) => res.unauthorized());
      app.get("/api/forbidden", (req, res) => res.forbidden());
      app.get("/api/server-error", (req, res) => res.serverError());

      const endpoints = [
        "/api/success",
        "/api/error",
        "/api/not-found",
        "/api/unauthorized",
        "/api/forbidden",
        "/api/server-error",
      ];

      for (const endpoint of endpoints) {
        const response = await request(app).get(endpoint);
        expect(response.headers["api-version"]).toBe("v1.0");
      }
    });

    test("should preserve data types in responses", async () => {
      const complexData = {
        string: "text",
        number: 42,
        boolean: true,
        array: [1, 2, 3],
        object: { nested: "value" },
      };

      app.get("/test-types", (req, res) => {
        res.success(complexData);
      });

      const response = await request(app).get("/test-types");

      expect(response.body.data).toEqual(complexData);
      expect(typeof response.body.data.string).toBe("string");
      expect(typeof response.body.data.number).toBe("number");
      expect(typeof response.body.data.boolean).toBe("boolean");
    });

    test("should generate valid timestamps", async () => {
      app.get("/test-timestamp", (req, res) => {
        res.success({ test: true });
      });

      const response = await request(app).get("/test-timestamp");

      expect(response.body.timestamp).toMatch(
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/
      );
    });
  });
});

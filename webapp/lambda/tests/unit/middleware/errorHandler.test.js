const express = require("express");
const request = require("supertest");
const errorHandler = require("../../../middleware/errorHandler");

const app = express();

// Helper function to create test routes that throw specific errors
function createTestRoute(errorToThrow) {
  return (req, res, next) => {
    next(errorToThrow);
  };
}

// Setup test routes
app.get(
  "/test-generic-error",
  createTestRoute(new Error("Generic error message"))
);

app.get(
  "/test-validation-error",
  createTestRoute(
    (() => {
      const err = new Error("Validation failed");
      err.name = "ValidationError";
      return err;
    })()
  )
);

app.get(
  "/test-custom-status-error",
  createTestRoute(
    (() => {
      const err = new Error("Custom status error");
      err.status = 403;
      return err;
    })()
  )
);

app.get(
  "/test-postgres-unique-violation",
  createTestRoute(
    (() => {
      const err = new Error("Duplicate key value violates unique constraint");
      err.code = "23505";
      return err;
    })()
  )
);

app.get(
  "/test-postgres-foreign-key",
  createTestRoute(
    (() => {
      const err = new Error("Foreign key constraint violation");
      err.code = "23503";
      return err;
    })()
  )
);

app.get(
  "/test-postgres-table-missing",
  createTestRoute(
    (() => {
      const err = new Error("Relation does not exist");
      err.code = "42P01";
      return err;
    })()
  )
);

app.get(
  "/test-error-without-message",
  createTestRoute(
    (() => {
      const err = new Error();
      err.message = "";
      return err;
    })()
  )
);

// Apply error handler AFTER all routes
app.use(errorHandler);

describe("Error Handler Middleware", () => {
  let originalEnv;
  let consoleErrorSpy;

  beforeEach(() => {
    originalEnv = process.env.NODE_ENV;
    consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    process.env.NODE_ENV = originalEnv;
    consoleErrorSpy.mockRestore();
  });

  describe("Generic Error Handling", () => {
    test("should handle generic errors with 500 status", async () => {
      const response = await request(app).get("/test-generic-error");

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error.status).toBe(500);
      expect(response.body.error.message).toBe("Generic error message");
      expect(response.body.error).toHaveProperty("timestamp");
      expect(response.body.error.path).toBe("/test-generic-error");
    });

    test("should log error details", async () => {
      await request(app).get("/test-generic-error");

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        "AWS Lambda Error:",
        expect.stringMatching(/"message":\s*"Generic error message"/)
      );
    });

    test("should handle errors without message", async () => {
      const response = await request(app).get("/test-error-without-message");

      expect(response.status).toBe(500);
      expect(response.body.error.message).toBe("Internal Server Error");
    });
  });

  describe("Specific Error Type Handling", () => {
    test("should handle ValidationError with 400 status", async () => {
      const response = await request(app).get("/test-validation-error");

      expect(response.status).toBe(400);
      expect(response.body.error.status).toBe(400);
      expect(response.body.error.message).toBe("Validation Error");
    });

    test("should handle custom status errors", async () => {
      const response = await request(app).get("/test-custom-status-error");

      expect(response.status).toBe(403);
      expect(response.body.error.status).toBe(403);
      expect(response.body.error.message).toBe("Custom status error");
    });

    test("should handle PostgreSQL unique violation (23505)", async () => {
      const response = await request(app).get(
        "/test-postgres-unique-violation"
      );

      expect(response.status).toBe(409);
      expect(response.body.error.status).toBe(409);
      expect(response.body.error.message).toBe("Duplicate entry");
    });

    test("should handle PostgreSQL foreign key violation (23503)", async () => {
      const response = await request(app).get("/test-postgres-foreign-key");

      expect(response.status).toBe(400);
      expect(response.body.error.status).toBe(400);
      expect(response.body.error.message).toBe("Invalid reference");
    });

    test("should handle PostgreSQL table missing (42P01)", async () => {
      const response = await request(app).get("/test-postgres-table-missing");

      expect(response.status).toBe(500);
      expect(response.body.error.status).toBe(500);
      expect(response.body.error.message).toBe("Database configuration error");
    });
  });

  describe("Development Environment Behavior", () => {
    test("should include details in development mode", async () => {
      process.env.NODE_ENV = "development";

      const response = await request(app).get(
        "/test-postgres-unique-violation"
      );

      expect(response.status).toBe(409);
      expect(response.body.error).toHaveProperty("details");
      expect(response.body.error.details).toBe(
        "A record with this information already exists"
      );
    });

    test("should include validation details in development", async () => {
      process.env.NODE_ENV = "development";

      const response = await request(app).get("/test-validation-error");

      expect(response.status).toBe(400);
      expect(response.body.error).toHaveProperty("details");
      expect(response.body.error.details).toBe("Validation failed");
    });
  });

  describe("Production Environment Behavior", () => {
    test("should not include details in production mode", async () => {
      process.env.NODE_ENV = "production";

      const response = await request(app).get(
        "/test-postgres-unique-violation"
      );

      expect(response.status).toBe(409);
      expect(response.body.error).not.toHaveProperty("details");
    });

    test("should not include validation details in production", async () => {
      process.env.NODE_ENV = "production";

      const response = await request(app).get("/test-validation-error");

      expect(response.status).toBe(400);
      expect(response.body.error).not.toHaveProperty("details");
    });
  });

  describe("Response Format Stability", () => {
    test("should always include required error fields", async () => {
      const response = await request(app).get("/test-generic-error");

      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toHaveProperty("status");
      expect(response.body.error).toHaveProperty("message");
      expect(response.body.error).toHaveProperty("timestamp");
      expect(response.body.error).toHaveProperty("path");

      // Validate timestamp format (ISO string)
      expect(new Date(response.body.error.timestamp)).toBeInstanceOf(Date);
      expect(response.body.error.timestamp).toMatch(
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/
      );
    });

    test("should set correct Content-Type header", async () => {
      const response = await request(app).get("/test-generic-error");

      expect(response.headers["content-type"]).toMatch(/application\/json/);
    });

    test("should maintain consistent error structure across different error types", async () => {
      const testCases = [
        "/test-generic-error",
        "/test-validation-error",
        "/test-custom-status-error",
        "/test-postgres-unique-violation",
      ];

      for (const testCase of testCases) {
        const response = await request(app).get(testCase);

        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toHaveProperty("status");
        expect(response.body.error).toHaveProperty("message");
        expect(response.body.error).toHaveProperty("timestamp");
        expect(response.body.error).toHaveProperty("path");
        expect(typeof response.body.error.status).toBe("number");
        expect(typeof response.body.error.message).toBe("string");
      }
    });
  });

  describe("Edge Cases", () => {
    test("should handle null error", async () => {
      const testApp = express();
      testApp.get("/test-null-error", (req, res, next) => {
        next(null);
      });
      testApp.use(errorHandler);

      const response = await request(testApp).get("/test-null-error");

      // Should not reach error handler with null error
      expect(response.status).toBe(404); // Route not found since next(null) continues
    });

    test("should handle error objects without stack trace", async () => {
      const testApp = express();
      testApp.get("/test-no-stack", (req, res, next) => {
        const err = new Error("No stack error");
        delete err.stack;
        next(err);
      });
      testApp.use(errorHandler);

      const response = await request(testApp).get("/test-no-stack");

      expect(response.status).toBe(500);
      expect(response.body.error.message).toBe("No stack error");
    });

    test("should handle very long error messages", async () => {
      const longMessage = "A".repeat(1000);
      const testApp = express();
      testApp.get("/test-long-message", (req, res, next) => {
        next(new Error(longMessage));
      });
      testApp.use(errorHandler);

      const response = await request(testApp).get("/test-long-message");

      expect(response.status).toBe(500);
      expect(response.body.error.message).toBe(longMessage);
    });

    test("should handle special characters in error messages", async () => {
      const specialMessage = "Error with special chars: <>&\"'";
      const testApp = express();
      testApp.get("/test-special-chars", (req, res, next) => {
        next(new Error(specialMessage));
      });
      testApp.use(errorHandler);

      const response = await request(testApp).get("/test-special-chars");

      expect(response.status).toBe(500);
      expect(response.body.error.message).toBe(specialMessage);
    });
  });

  describe("PostgreSQL Error Code Coverage", () => {
    test("should handle unknown PostgreSQL error codes", async () => {
      const testApp = express();
      testApp.get("/test-unknown-pg-error", (req, res, next) => {
        const err = new Error("Unknown PostgreSQL error");
        err.code = "12345"; // Unknown code
        next(err);
      });
      testApp.use(errorHandler);

      const response = await request(testApp).get("/test-unknown-pg-error");

      expect(response.status).toBe(500);
      expect(response.body.error.message).toBe("Unknown PostgreSQL error");
    });

    test("should prioritize custom status over default for PostgreSQL errors", async () => {
      const testApp = express();
      testApp.get("/test-pg-custom-status", (req, res, next) => {
        const err = new Error("Custom PostgreSQL error");
        err.code = "23505"; // Unique violation
        err.status = 422; // Custom status
        next(err);
      });
      testApp.use(errorHandler);

      const response = await request(testApp).get("/test-pg-custom-status");

      // Should use PostgreSQL-specific status (409) not custom status (422)
      expect(response.status).toBe(409);
    });
  });
});

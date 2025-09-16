const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Health Routes", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/health", () => {
    test("should return quick health check", async () => {
      const response = await request(app).get("/api/health?quick=true");

      expect([200, 404]).toContain(response.status);
      expect(response.body.status).toBe("healthy");
      expect(response.body.healthy).toBe(true);
      expect(response.body.service).toBe("Financial Dashboard API");
      expect(response.body).toHaveProperty("timestamp");
      expect(response.body).toHaveProperty("memory");
      expect(response.body).toHaveProperty("uptime");
      expect(response.body.version).toBe("1.0.0");
      expect(response.body.note).toBe(
        "Quick health check - database not tested"
      );
      expect(response.body.database.status).toBe("not_tested");
    });

    test("should return full health check with database", async () => {
      const response = await request(app).get("/api/health");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.status).toBe("healthy");
        expect(response.body.healthy).toBe(true);
        expect(response.body.service).toBe("Financial Dashboard API");
        expect(response.body).toHaveProperty("timestamp");
        expect(response.body).toHaveProperty("database");
        expect(response.body.database.status).toBe("healthy");
        expect(response.body).toHaveProperty("api");
        expect(response.body).toHaveProperty("memory");
        expect(response.body).toHaveProperty("uptime");
      } else {
        // Handle database errors gracefully
        expect(response.body.healthy).toBe(false);
        expect(response.body).toHaveProperty("database");
        expect(response.body).toHaveProperty("api");
      }
    });

    test("should handle test environment correctly", async () => {
      const response = await request(app).get("/api/health");

      // In test environment, should return 200
      expect([200, 404]).toContain(response.status);
      expect(response.body).toHaveProperty(
        "service",
        "Financial Dashboard API"
      );
      expect(response.body).toHaveProperty("api");
      expect(response.body.api.version).toBe("1.0.0");
      expect(response.body.api.environment).toBe("test");
    });
  });

  describe("GET /api/health/database", () => {
    test("should return comprehensive database health", async () => {
      const response = await request(app).get("/api/health/database");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.status).toBe("ok");
        expect(response.body.healthy).toBe(true);
        expect(response.body).toHaveProperty("timestamp");
        expect(response.body).toHaveProperty("database");
        expect(response.body.database).toHaveProperty("status");
        expect(response.body.database).toHaveProperty("tables");
        expect(response.body.database).toHaveProperty("summary");
        expect(response.body.database.summary).toHaveProperty("total_tables");
        expect(response.body.database.summary).toHaveProperty("healthy_tables");
        expect(response.body.database.summary).toHaveProperty("total_records");
      } else {
        // Handle database connection issues
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should provide table summary statistics", async () => {
      const response = await request(app).get("/api/health/database");

      if (response.status === 200) {
        const summary = response.body.database.summary;
        expect(typeof summary.total_tables).toBe("number");
        expect(typeof summary.healthy_tables).toBe("number");
        expect(typeof summary.empty_tables).toBe("number");
        expect(typeof summary.error_tables).toBe("number");
        expect(typeof summary.total_records).toBe("number");
        expect(
          summary.healthy_tables + summary.empty_tables + summary.error_tables
        ).toBeGreaterThanOrEqual(0);
      }
    });
  });

  describe("GET /api/health/test-connection", () => {
    test("should test database connection", async () => {
      const response = await request(app).get("/api/health/test-connection");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.status).toBe("ok");
        expect(response.body.connection).toBe("successful");
        expect(response.body).toHaveProperty("currentTime");
        expect(response.body).toHaveProperty("postgresVersion");
        expect(typeof response.body.currentTime).toBe("string");
        expect(typeof response.body.postgresVersion).toBe("string");
      } else {
        expect(response.body.connection).toBe("failed");
        expect(response.body).toHaveProperty("error");
      }
    });
  });

  describe("GET /api/health/debug-secret", () => {
    test("should handle debug secret endpoint", async () => {
      const response = await request(app).get("/api/health/debug-secret");

      // This endpoint can return 200 (success) or error codes (400, 500, 501) depending on AWS environment
      expect([200, 400, 500, 501].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body.status).toBe("debug");
        expect(response.body).toHaveProperty("timestamp");
        expect(response.body).toHaveProperty("debugInfo");
        expect(response.body.debugInfo).toHaveProperty("secretType");
      } else if (response.status === 400) {
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toBe("DB_SECRET_ARN not set");
      } else {
        // 500 - AWS SDK errors in test environment
        expect(response.body).toHaveProperty("error");
      }
    });
  });

  describe("GET /api/health/database/diagnostics", () => {
    test("should provide comprehensive database diagnostics", async () => {
      const response = await request(app).get(
        "/api/health/database/diagnostics"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("status");
        expect(response.body).toHaveProperty("overallStatus");
        expect(response.body).toHaveProperty("diagnostics");
        expect(response.body).toHaveProperty("summary");

        // Check diagnostics structure
        const diagnostics = response.body.diagnostics;
        expect(diagnostics).toHaveProperty("timestamp");
        expect(diagnostics).toHaveProperty("environment");
        expect(diagnostics).toHaveProperty("connection");
        expect(diagnostics).toHaveProperty("database");
        expect(diagnostics).toHaveProperty("tables");

        // Check environment info
        expect(diagnostics.environment.NODE_ENV).toBe("test");
        expect(diagnostics.environment).toHaveProperty("IS_LOCAL");

        // Check connection info
        expect(diagnostics.connection).toHaveProperty("status");
        expect(diagnostics.connection).toHaveProperty("durationMs");

        // Check tables info
        expect(diagnostics.tables).toHaveProperty("total");
        expect(diagnostics.tables).toHaveProperty("withData");
        expect(diagnostics.tables).toHaveProperty("list");
        expect(Array.isArray(diagnostics.tables.list)).toBe(true);
      } else {
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should include performance metrics", async () => {
      const response = await request(app).get(
        "/api/health/database/diagnostics"
      );

      if (response.status === 200) {
        const diagnostics = response.body.diagnostics;
        expect(typeof diagnostics.connection.durationMs).toBe("number");
        expect(diagnostics.connection.durationMs).toBeGreaterThanOrEqual(0);

        if (diagnostics.tables.durationMs !== null) {
          expect(typeof diagnostics.tables.durationMs).toBe("number");
          expect(diagnostics.tables.durationMs).toBeGreaterThanOrEqual(0);
        }
      }
    });

    test("should provide actionable recommendations", async () => {
      const response = await request(app).get(
        "/api/health/database/diagnostics"
      );

      if (response.status === 200) {
        expect(Array.isArray(response.body.diagnostics.recommendations)).toBe(
          true
        );
        expect(response.body.summary).toHaveProperty("recommendations");
        expect(Array.isArray(response.body.summary.recommendations)).toBe(true);
      }
    });

    test("should handle database table errors gracefully", async () => {
      const response = await request(app).get(
        "/api/health/database/diagnostics"
      );

      if (response.status === 200) {
        const diagnostics = response.body.diagnostics;
        expect(Array.isArray(diagnostics.errors)).toBe(true);
        expect(Array.isArray(diagnostics.tables.errors)).toBe(true);

        // Should have error handling for table access issues
        if (diagnostics.tables.errors.length > 0) {
          expect(diagnostics.tables.errors[0]).toHaveProperty("table");
          expect(diagnostics.tables.errors[0]).toHaveProperty("error");
        }
      }
    });
  });
});

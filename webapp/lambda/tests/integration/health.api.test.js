// Jest globals are automatically available
const request = require("supertest");

// Mock external dependencies
jest.mock("../../utils/database", () => ({
  healthCheck: jest.fn(),
  query: jest.fn(),
  initializeDatabase: jest.fn(),
  getPool: jest.fn(),
  closeDatabase: jest.fn(),
  transaction: jest.fn(),
}));

const { healthCheck, query, initializeDatabase, getPool } = require("../../utils/database");

describe("Health API Integration Tests", () => {
  let app;

  beforeEach(() => {
    jest.clearAllMocks();

    // Clear module cache
    delete require.cache[require.resolve("../../index")];

    // Mock environment variables
    process.env.NODE_ENV = "test";
    delete process.env.COGNITO_USER_POOL_ID;
    delete process.env.COGNITO_CLIENT_ID;

    // Set up default mocks for database functions
    query.mockResolvedValue({ rows: [{ ok: 1 }], rowCount: 1 });
    initializeDatabase.mockResolvedValue({});
    getPool.mockReturnValue({
      query: query,
      totalCount: 1,
      idleCount: 0,
      waitingCount: 0,
      connect: jest.fn().mockResolvedValue({}),
      end: jest.fn().mockResolvedValue({})
    });

    // Import app after setting up mocks
    app = require("../../index").app;
  });

  afterEach(() => {
    delete process.env.NODE_ENV;
  });

  describe("GET /health", () => {
    test("should return healthy status when all systems are operational", async () => {
      // Mock healthy database
      healthCheck.mockResolvedValue({
        healthy: true,
        latency_ms: 25,
        pool: {
          totalCount: 10,
          idleCount: 8,
          waitingCount: 0,
        },
      });

      const response = await request(app).get("/health").expect(200);

      expect(response.body).toMatchObject({
        status: "healthy",
        timestamp: expect.any(String),
        version: expect.any(String),
        environment: "test",
        services: expect.objectContaining({
          database: expect.objectContaining({
            status: "healthy",
            latency_ms: 25,
          }),
        }),
      });
    });

    test("should return unhealthy status when database is down", async () => {
      // Mock unhealthy database
      healthCheck.mockResolvedValue({
        healthy: false,
        error: "Connection timeout",
        latency_ms: null,
      });

      const response = await request(app).get("/health").expect(503);

      expect(response.body).toMatchObject({
        status: "unhealthy",
        services: expect.objectContaining({
          database: expect.objectContaining({
            status: "unhealthy",
            error: "Connection timeout",
          }),
        }),
      });
    });

    test("should return quick health check when quick parameter is true", async () => {
      const response = await request(app).get("/health?quick=true").expect(200);

      expect(response.body).toMatchObject({
        status: "healthy",
        timestamp: expect.any(String),
        environment: "test",
        quick: true,
      });

      // Should not call database health check for quick check
      expect(healthCheck).not.toHaveBeenCalled();
    });

    test("should include system information in health response", async () => {
      healthCheck.mockResolvedValue({
        healthy: true,
        latency_ms: 30,
      });

      const response = await request(app).get("/health").expect(200);

      expect(response.body).toMatchObject({
        system: expect.objectContaining({
          uptime: expect.any(Number),
          memory: expect.objectContaining({
            used: expect.any(Number),
            total: expect.any(Number),
            percentage: expect.any(Number),
          }),
          cpu: expect.objectContaining({
            usage: expect.any(Number),
          }),
        }),
      });
    });

    test("should handle database connection errors gracefully", async () => {
      healthCheck.mockRejectedValue(new Error("Database unavailable"));

      const response = await request(app).get("/health").expect(503);

      expect(response.body).toMatchObject({
        status: "unhealthy",
        services: expect.objectContaining({
          database: expect.objectContaining({
            status: "error",
            error: "Database unavailable",
          }),
        }),
      });
    });
  });

  describe("GET /health/detailed", () => {
    test("should return detailed health information", async () => {
      // Mock detailed health checks
      healthCheck.mockResolvedValue({
        healthy: true,
        latency_ms: 25,
        pool: {
          totalCount: 10,
          idleCount: 8,
          waitingCount: 0,
        },
      });

      query.mockResolvedValue({
        rows: [
          { table_name: "users", row_count: 1500 },
          { table_name: "api_keys", row_count: 150 },
        ],
      });

      const response = await request(app).get("/health/detailed").expect(200);

      expect(response.body).toMatchObject({
        status: "healthy",
        detailed: true,
        services: expect.objectContaining({
          database: expect.objectContaining({
            status: "healthy",
            tables: expect.arrayContaining([
              expect.objectContaining({
                table_name: "users",
                row_count: 1500,
              }),
            ]),
          }),
        }),
      });
    });
  });

  describe("GET /api/health", () => {
    test("should work with /api prefix", async () => {
      healthCheck.mockResolvedValue({
        healthy: true,
        latency_ms: 20,
      });

      const response = await request(app).get("/api/health").expect(200);

      expect(response.body).toMatchObject({
        status: "healthy",
        services: expect.objectContaining({
          database: expect.objectContaining({
            status: "healthy",
          }),
        }),
      });
    });
  });

  describe("Error handling", () => {
    test("should handle malformed quick parameter", async () => {
      await request(app).get("/health?quick=invalid").expect(200);

      // Should treat invalid quick parameter as false
      expect(healthCheck).toHaveBeenCalled();
    });

    test("should handle internal server errors", async () => {
      healthCheck.mockImplementation(() => {
        throw new Error("Unexpected error");
      });

      const response = await request(app).get("/health").expect(500);

      expect(response.body).toMatchObject({
        error: "Internal Server Error",
        message: expect.any(String),
      });
    });

    test("should set appropriate CORS headers", async () => {
      healthCheck.mockResolvedValue({
        healthy: true,
        latency_ms: 25,
      });

      const response = await request(app)
        .get("/health")
        .set("Origin", "https://example.com")
        .expect(200);

      // Response should have CORS headers
      expect(response.headers).toHaveProperty("access-control-allow-origin");
    });
  });

  describe("Performance metrics", () => {
    test("should include response time in health check", async () => {
      healthCheck.mockResolvedValue({
        healthy: true,
        latency_ms: 15,
      });

      const startTime = Date.now();
      const response = await request(app).get("/health").expect(200);
      const endTime = Date.now();

      expect(response.body.response_time_ms).toBeDefined();
      expect(response.body.response_time_ms).toBeGreaterThan(0);
      expect(response.body.response_time_ms).toBeLessThan(
        endTime - startTime + 50
      ); // Allow some margin
    });

    test("should track concurrent health check requests", async () => {
      healthCheck.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  healthy: true,
                  latency_ms: 10,
                }),
              100
            )
          )
      );

      // Make multiple concurrent requests
      const promises = [
        request(app).get("/health"),
        request(app).get("/health"),
        request(app).get("/health"),
      ];

      const responses = await Promise.all(promises);

      responses.forEach((response) => {
        expect(response.status).toBe(200);
        expect(response.body.status).toBe("healthy");
      });
    });
  });
});

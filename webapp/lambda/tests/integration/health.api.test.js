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

const { query, initializeDatabase, getPool } = require("../../utils/database");

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
      // Mock successful database query for test environment
      query.mockResolvedValue({ rows: [{ ok: 1 }], rowCount: 1 });

      const response = await request(app).get("/health").expect(200);

      expect(response.body).toMatchObject({
        status: "healthy",
        healthy: true,
        service: "Financial Dashboard API",
        timestamp: expect.any(String),
        environment: "test",
        database: expect.objectContaining({
          status: "connected",
          responseTime: expect.any(Number),
          tables: expect.objectContaining({
            user_portfolio: true,
            stock_prices: true,
            risk_alerts: true,
            user_api_keys: true,
          }),
        }),
        api: expect.objectContaining({
          version: "1.0.0",
          environment: "test"
        }),
        memory: expect.any(Object),
        uptime: expect.any(Number),
      });
    });

    test("should return unhealthy status when database is down", async () => {
      // Mock database query failure
      query.mockRejectedValue(new Error("Connection timeout"));

      const response = await request(app).get("/health").expect(503);

      expect(response.body).toMatchObject({
        status: "unhealthy",
        healthy: false,
        service: "Financial Dashboard API",
        timestamp: expect.any(String),
        environment: "test",
        database: expect.objectContaining({
          status: "disconnected",
          error: "Connection timeout",
        }),
        api: expect.objectContaining({
          version: "1.0.0",
          environment: "test"
        }),
        memory: expect.any(Object),
        uptime: expect.any(Number),
      });
    });

    test("should return quick health check when quick parameter is true", async () => {
      const response = await request(app).get("/health?quick=true").expect(200);

      expect(response.body).toMatchObject({
        status: "healthy",
        healthy: true,
        service: "Financial Dashboard API",
        timestamp: expect.any(String),
        environment: "test",
        memory: expect.any(Object),
        uptime: expect.any(Number),
        note: "Quick health check - database not tested",
        database: { status: "not_tested" },
        api: expect.objectContaining({
          version: "1.0.0",
          environment: "test"
        }),
      });

      // Should not call database query for quick check
      expect(query).not.toHaveBeenCalled();
    });

    test("should include system information in health response", async () => {
      query.mockResolvedValue({ rows: [{ ok: 1 }], rowCount: 1 });

      const response = await request(app).get("/health").expect(200);

      expect(response.body).toMatchObject({
        status: "healthy",
        healthy: true,
        service: "Financial Dashboard API",
        timestamp: expect.any(String),
        environment: "test",
        memory: expect.objectContaining({
          rss: expect.any(Number),
          heapTotal: expect.any(Number),
          heapUsed: expect.any(Number),
          external: expect.any(Number),
          arrayBuffers: expect.any(Number),
        }),
        uptime: expect.any(Number),
        database: expect.objectContaining({
          status: "connected",
        }),
        api: expect.objectContaining({
          version: "1.0.0",
          environment: "test"
        }),
      });
    });

    test("should handle database connection errors gracefully", async () => {
      query.mockRejectedValue(new Error("Database unavailable"));

      const response = await request(app).get("/health").expect(503);

      expect(response.body).toMatchObject({
        status: "unhealthy",
        healthy: false,
        service: "Financial Dashboard API",
        timestamp: expect.any(String),
        environment: "test",
        database: expect.objectContaining({
          status: "disconnected",
          error: "Database unavailable",
        }),
        api: expect.objectContaining({
          version: "1.0.0",
          environment: "test"
        }),
        memory: expect.any(Object),
        uptime: expect.any(Number),
      });
    });
  });

  describe("GET /health/database", () => {
    test("should return database health information", async () => {
      // Mock database health status table query
      query.mockResolvedValue({
        rows: [
          { 
            table_name: "stock_symbols", 
            status: "healthy", 
            record_count: 1500, 
            missing_data_count: 0,
            last_updated: new Date().toISOString(),
            last_checked: new Date().toISOString(),
            is_stale: false,
            error: null
          },
          { 
            table_name: "price_daily", 
            status: "healthy", 
            record_count: 25000, 
            missing_data_count: 0,
            last_updated: new Date().toISOString(),
            last_checked: new Date().toISOString(),
            is_stale: false,
            error: null
          },
        ],
        rowCount: 2
      });

      const response = await request(app).get("/health/database").expect(200);

      expect(response.body).toMatchObject({
        status: "ok",
        healthy: true,
        timestamp: expect.any(String),
        database: expect.objectContaining({
          status: "connected",
          tables: expect.objectContaining({
            stock_symbols: expect.objectContaining({
              status: "healthy",
              record_count: 1500,
            }),
            price_daily: expect.objectContaining({
              status: "healthy", 
              record_count: 25000,
            }),
          }),
          summary: expect.objectContaining({
            total_tables: 2,
            healthy_tables: 2,
          }),
        }),
        api: expect.objectContaining({
          version: "1.0.0",
          environment: "test"
        }),
        memory: expect.any(Object),
        uptime: expect.any(Number),
      });
    });
  });

  describe("GET /api/health", () => {
    test("should work with /api prefix", async () => {
      query.mockResolvedValue({ rows: [{ ok: 1 }], rowCount: 1 });

      const response = await request(app).get("/api/health").expect(200);

      expect(response.body).toMatchObject({
        status: "healthy",
        healthy: true,
        service: "Financial Dashboard API",
        timestamp: expect.any(String),
        environment: "test",
        database: expect.objectContaining({
          status: "connected",
        }),
        api: expect.objectContaining({
          version: "1.0.0",
          environment: "test"
        }),
      });
    });
  });

  describe("Error handling", () => {
    test("should handle malformed quick parameter", async () => {
      query.mockResolvedValue({ rows: [{ ok: 1 }], rowCount: 1 });
      
      const response = await request(app).get("/health?quick=invalid").expect(200);

      // Should treat invalid quick parameter as false and do full health check
      expect(response.body).toMatchObject({
        status: "healthy",
        healthy: true,
        database: expect.objectContaining({
          status: "connected",
        }),
      });
      expect(query).toHaveBeenCalled();
    });

    test("should handle internal server errors", async () => {
      // Mock a different type of error - like if the app itself crashes
      const originalQuery = query;
      query.mockImplementation(() => {
        throw new Error("Unexpected database error");
      });

      const response = await request(app).get("/health").expect(503);

      expect(response.body).toMatchObject({
        status: "unhealthy",
        healthy: false,
        database: expect.objectContaining({
          status: "disconnected",
          error: "Unexpected database error",
        }),
      });
      
      // Restore mock
      query.mockImplementation(originalQuery);
    });

    test("should set appropriate CORS headers", async () => {
      query.mockResolvedValue({ rows: [{ ok: 1 }], rowCount: 1 });

      const response = await request(app)
        .get("/health")
        .set("Origin", "https://d1copuy2oqlazx.cloudfront.net")
        .expect(200);

      // Response should have CORS headers for allowed origin
      expect(response.headers).toHaveProperty("access-control-allow-origin");
      expect(response.body).toMatchObject({
        status: "healthy",
        healthy: true,
      });
    });
  });

  describe("Performance metrics", () => {
    test("should include basic performance metrics in health check", async () => {
      query.mockResolvedValue({ rows: [{ ok: 1 }], rowCount: 1 });

      const startTime = Date.now();
      const response = await request(app).get("/health").expect(200);
      const endTime = Date.now();

      // Check that we get the response within reasonable time
      expect(endTime - startTime).toBeLessThan(1000); // Should respond within 1 second
      
      // Verify basic performance-related fields are included
      expect(response.body.uptime).toBeDefined();
      expect(response.body.uptime).toBeGreaterThanOrEqual(0);
      expect(response.body.memory).toBeDefined();
      expect(response.body.memory.heapUsed).toBeGreaterThan(0);
      expect(response.body.database.responseTime).toBeDefined();
    });

    test("should handle concurrent health check requests", async () => {
      query.mockResolvedValue({ rows: [{ ok: 1 }], rowCount: 1 });

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
        expect(response.body.healthy).toBe(true);
        expect(response.body.database.status).toBe("connected");
      });
    });
  });
});

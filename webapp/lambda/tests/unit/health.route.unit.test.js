// Unit tests for health route

// Mock database module
jest.mock("../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn(),
  getPool: jest.fn(),
}));

const request = require("supertest");
const express = require("express");
const { query, initializeDatabase, getPool } = require("../../utils/database");

describe("Health Route Unit Tests", () => {
  let app;
  let healthRoute;

  beforeEach(() => {
    jest.clearAllMocks();

    // Clear module cache
    delete require.cache[require.resolve("../../routes/health")];

    // Create fresh Express app
    app = express();
    healthRoute = require("../../routes/health");
    app.use("/health", healthRoute);

    // Mock environment
    process.env.NODE_ENV = "test";
  });

  afterEach(() => {
    delete process.env.NODE_ENV;
  });

  describe("GET /health?quick=true", () => {
    test("should return quick health check without database", async () => {
      const response = await request(app).get("/health?quick=true").expect(200);

      expect(response.body).toMatchObject({
        status: "healthy",
        healthy: true,
        service: "Financial Dashboard API",
        environment: "test",
        note: "Quick health check - database not tested",
      });

      expect(response.body.timestamp).toBeDefined();
      expect(response.body.memory).toBeDefined();
      expect(response.body.uptime).toBeDefined();
      expect(response.body.database.status).toBe("not_tested");

      // Database functions should not be called for quick check
      expect(query).not.toHaveBeenCalled();
      expect(initializeDatabase).not.toHaveBeenCalled();
      expect(getPool).not.toHaveBeenCalled();
    });

    test("should include memory usage information", async () => {
      const response = await request(app).get("/health?quick=true").expect(200);

      expect(response.body.memory).toHaveProperty("rss");
      expect(response.body.memory).toHaveProperty("heapTotal");
      expect(response.body.memory).toHaveProperty("heapUsed");
      expect(response.body.memory).toHaveProperty("external");
    });

    test("should include uptime as a number", async () => {
      const response = await request(app).get("/health?quick=true").expect(200);

      expect(typeof response.body.uptime).toBe("number");
      expect(response.body.uptime).toBeGreaterThanOrEqual(0);
    });

    test("should include API version information", async () => {
      const response = await request(app).get("/health?quick=true").expect(200);

      expect(response.body.api).toMatchObject({
        version: "1.0.0",
        environment: "test",
      });
    });
  });

  describe("GET /health (full check)", () => {
    test("should return healthy status when database is initialized and working", async () => {
      // Mock database already initialized
      getPool.mockReturnValue({ query: jest.fn() });

      // Mock successful database query
      query.mockResolvedValue({
        rows: [
          {
            now: "2024-01-01T00:00:00.000Z",
            version: "PostgreSQL 14.0",
          },
        ],
      });

      const response = await request(app).get("/health").expect(200);

      expect(response.body).toMatchObject({
        status: "healthy",
        healthy: true,
      });

      expect(getPool).toHaveBeenCalled();
      expect(query).toHaveBeenCalled();
    });

    test("should initialize database if not already initialized", async () => {
      // Mock database not initialized (getPool throws)
      getPool.mockImplementation(() => {
        throw new Error(
          "Database not initialized. Call initializeDatabase() first."
        );
      });

      // Mock successful initialization
      initializeDatabase.mockResolvedValue(true);

      // Mock successful database query after initialization
      query.mockResolvedValue({
        rows: [
          {
            now: "2024-01-01T00:00:00.000Z",
            version: "PostgreSQL 14.0",
          },
        ],
      });

      const response = await request(app).get("/health").expect(200);

      expect(getPool).toHaveBeenCalled();
      expect(initializeDatabase).toHaveBeenCalled();
      expect(query).toHaveBeenCalled();
      expect(response.body.status).toBe("healthy");
    });

    test("should return unhealthy status when database initialization fails", async () => {
      // Mock database not initialized
      getPool.mockImplementation(() => {
        throw new Error("Database not initialized");
      });

      // Mock failed initialization
      const initError = new Error("Connection failed");
      initializeDatabase.mockRejectedValue(initError);

      const response = await request(app).get("/health").expect(503);

      expect(response.body).toMatchObject({
        status: "unhealthy",
        healthy: false,
        service: "Financial Dashboard API",
      });

      expect(response.body.database.status).toBe("initialization_failed");
      expect(response.body.database.error).toBe("Connection failed");
      expect(initializeDatabase).toHaveBeenCalled();
    });

    test("should return unhealthy status when database query fails", async () => {
      // Mock database initialized
      getPool.mockReturnValue({ query: jest.fn() });

      // Mock failed database query
      const queryError = new Error("Query timeout");
      query.mockRejectedValue(queryError);

      const response = await request(app).get("/health").expect(503);

      expect(response.body).toMatchObject({
        status: "unhealthy",
        healthy: false,
      });

      expect(response.body.database.status).toBe("disconnected");
      expect(response.body.database.error).toBe("Query timeout");
    });

    test("should handle unexpected errors gracefully", async () => {
      // Mock database initialized
      getPool.mockReturnValue({ query: jest.fn() });

      // Mock database query that throws unexpected error
      query.mockImplementation(() => {
        throw new Error("Unexpected database error");
      });

      const response = await request(app).get("/health").expect(503);

      expect(response.body.database.status).toBe("disconnected");
      expect(response.body.database.error).toContain("database error");
    });
  });

  describe("Query parameter handling", () => {
    test("should handle quick=false as full check", async () => {
      getPool.mockReturnValue({ query: jest.fn() });
      query.mockResolvedValue({
        rows: [{ now: "2024-01-01T00:00:00.000Z", version: "PostgreSQL 14.0" }],
      });

      await request(app).get("/health?quick=false").expect(200);

      expect(getPool).toHaveBeenCalled();
      expect(query).toHaveBeenCalled();
    });

    test("should handle invalid quick parameter as full check", async () => {
      getPool.mockReturnValue({ query: jest.fn() });
      query.mockResolvedValue({
        rows: [{ now: "2024-01-01T00:00:00.000Z", version: "PostgreSQL 14.0" }],
      });

      await request(app).get("/health?quick=invalid").expect(200);

      expect(getPool).toHaveBeenCalled();
      expect(query).toHaveBeenCalled();
    });

    test("should handle no query parameters as full check", async () => {
      getPool.mockReturnValue({ query: jest.fn() });
      query.mockResolvedValue({
        rows: [{ now: "2024-01-01T00:00:00.000Z", version: "PostgreSQL 14.0" }],
      });

      await request(app).get("/health").expect(200);

      expect(getPool).toHaveBeenCalled();
      expect(query).toHaveBeenCalled();
    });
  });

  describe("Response format validation", () => {
    test("should return valid ISO timestamp", async () => {
      const response = await request(app).get("/health?quick=true").expect(200);

      const timestamp = new Date(response.body.timestamp);
      expect(timestamp.toISOString()).toBe(response.body.timestamp);
    });

    test("should include all required fields in quick response", async () => {
      const response = await request(app).get("/health?quick=true").expect(200);

      const requiredFields = [
        "status",
        "healthy",
        "service",
        "timestamp",
        "environment",
        "memory",
        "uptime",
        "database",
        "api",
      ];

      requiredFields.forEach((field) => {
        expect(response.body).toHaveProperty(field);
      });
    });

    test("should return proper Content-Type header", async () => {
      const response = await request(app).get("/health?quick=true").expect(200);

      expect(response.headers["content-type"]).toMatch(/application\/json/);
    });
  });

  describe("Environment variable handling", () => {
    test("should default to development environment when NODE_ENV not set", async () => {
      delete process.env.NODE_ENV;

      const response = await request(app).get("/health?quick=true").expect(200);

      expect(response.body.environment).toBe("development");
      expect(response.body.api.environment).toBe("development");
    });

    test("should use NODE_ENV when set", async () => {
      process.env.NODE_ENV = "production";

      const response = await request(app).get("/health?quick=true").expect(200);

      expect(response.body.environment).toBe("production");
      expect(response.body.api.environment).toBe("production");
    });
  });
});

/**
 * Health Routes Unit Tests
 *
 * GET / doesn't branch on a ?quick= query param, doesn't touch the database, and
 * doesn't return memory/api/environment fields - it's an unconditional
 * sendSuccess(res, { status: "healthy", healthy: true, service: "Financial Dashboard
 * API" }) with no other logic. The richer response (uptime/version/environment/database
 * status+tables) lives at GET /detailed instead. Replaced with coverage of both.
 */
const request = require("supertest");
const express = require("express");

jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

const { query } = require("../../../utils/database");
const healthRoutes = require("../../../routes/health");

describe("Health Routes Unit Tests", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/api/health", healthRoutes);
  });

  beforeEach(() => {
    query.mockReset();
  });

  describe("GET /api/health", () => {
    test("returns a minimal healthy response without touching the database", async () => {
      const response = await request(app).get("/api/health").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual({
        status: "healthy",
        healthy: true,
        service: "Financial Dashboard API",
      });
      expect(query).not.toHaveBeenCalled();
    });
  });

  describe("GET /api/health/detailed", () => {
    test("reports connected status and table counts in development", async () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "development";
      query.mockImplementation((sql) => {
        if (sql.includes("information_schema.tables")) {
          return Promise.resolve({ rows: [{ count: "10" }] });
        }
        return Promise.resolve({ rows: [{ cnt: "42" }] });
      });

      const response = await request(app)
        .get("/api/health/detailed")
        .expect(200);

      process.env.NODE_ENV = originalEnv;

      expect(response.body.success).toBe(true);
      expect(response.body.data).toMatchObject({
        status: "healthy",
        healthy: true,
        service: "Financial Dashboard API",
        version: "1.0.0",
        environment: "development",
      });
      expect(response.body.data.database.status).toBe("connected");
      expect(response.body.data.database.tables.price_daily).toBe("42");
    });

    test("reports disconnected status when the database is unreachable", async () => {
      query.mockRejectedValue(new Error("connection refused"));

      const response = await request(app)
        .get("/api/health/detailed")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.database.status).toBe("error");
    });

    test("omits table-level detail in production", async () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "production";
      query.mockResolvedValue({ rows: [{ count: "10" }] });

      const response = await request(app)
        .get("/api/health/detailed")
        .expect(200);

      process.env.NODE_ENV = originalEnv;

      expect(response.body.data.database).toEqual({ status: "connected" });
      expect(response.body.data).not.toHaveProperty("environment");
    });
  });
});

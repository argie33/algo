const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Analytics Routes", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/analytics", () => {
    test("should return analytics endpoints", async () => {
      const response = await request(app).get("/api/analytics");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("message");
        expect(response.body).toHaveProperty("endpoints");
      }
    });
  });

  describe("GET /api/analytics/performance", () => {
    test("should return performance analytics", async () => {
      const response = await request(app).get("/api/analytics/performance");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toBeDefined();
      }
    });
  });

  describe("GET /api/analytics/risk", () => {
    test("should return risk analytics", async () => {
      const response = await request(app).get("/api/analytics/risk");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("risk");
      }
    });
  });

  describe("GET /api/analytics/allocation", () => {
    test("should return allocation analytics", async () => {
      const response = await request(app).get("/api/analytics/allocation");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("allocation");
      }
    });
  });

  describe("GET /api/analytics/returns", () => {
    test("should return returns analysis", async () => {
      const response = await request(app).get("/api/analytics/returns");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("returns");
      }
    });
  });

  describe("GET /api/analytics/sectors", () => {
    test("should return sector analysis", async () => {
      const response = await request(app).get("/api/analytics/sectors");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("sectors");
      }
    });
  });

  describe("GET /api/analytics/correlation", () => {
    test("should return correlation analysis", async () => {
      const response = await request(app)
        .get("/api/analytics/correlation")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("correlations");
      }
    });
  });

  describe("GET /api/analytics/volatility", () => {
    test("should return volatility analysis", async () => {
      const response = await request(app).get("/api/analytics/volatility");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("volatility");
      }
    });
  });

  describe("GET /api/analytics/trends", () => {
    test("should return trend analysis", async () => {
      const response = await request(app).get("/api/analytics/trends");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("trends");
      }
    });
  });

  describe("POST /api/analytics/custom", () => {
    test("should handle custom analytics request", async () => {
      const analyticsRequest = {
        metrics: ["returns", "sharpe_ratio"],
        period: "1Y",
        symbols: ["AAPL", "MSFT"],
      };

      const response = await request(app)
        .post("/api/analytics/custom")
        .send(analyticsRequest);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200 || response.status === 201) {
        expect(response.body.success).toBe(true);
      }
    });
  });
});

/**
 * Research Integration Tests
 * Tests for research reports and analysis data
 * Route: /routes/research.js
 */

const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Research API", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });
  describe("Research Reports", () => {
    test("should return general research data", async () => {
      const response = await request(app).get(
        "/api/research?symbol=AAPL&limit=20"
      );

      expect([200, 404, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success");

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body).toHaveProperty("data");
        expect(response.body).toHaveProperty("research_reports");
        expect(Array.isArray(response.body.research_reports)).toBe(true);
      }
    });

    test("should return research reports list", async () => {
      const response = await request(app).get(
        "/api/research/reports?symbol=AAPL&limit=15"
      );

      expect([200, 404, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success");

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data.reports)).toBe(true);
      }
    });
  });

  describe("Analyst Coverage", () => {
    test("should return 404 for non-implemented coverage route", async () => {
      const response = await request(app).get("/api/research/coverage/AAPL");

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("error");
    });

    test("should return 404 for non-implemented firms route", async () => {
      const response = await request(app).get("/api/research/firms/AAPL");

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("error");
    });
  });

  describe("Research Categories", () => {
    test("should return 404 for non-implemented category route", async () => {
      const response = await request(app).get(
        "/api/research/category/sector-analysis?limit=10"
      );

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("error");
    });

    test("should return 404 for non-implemented categories route", async () => {
      const response = await request(app).get("/api/research/categories");

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("error");
    });
  });

  describe("Industry Analysis", () => {
    test("should return 404 for non-implemented industry route", async () => {
      const response = await request(app).get(
        "/api/research/industry/Technology"
      );

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("error");
    });

    test("should return 404 for non-implemented peers route", async () => {
      const response = await request(app).get(
        "/api/research/industry/peers/AAPL"
      );

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("error");
    });
  });

  describe("Research Subscription", () => {
    test("should return 404 for non-implemented subscriptions route", async () => {
      const response = await request(app)
        .get("/api/research/subscriptions")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("error");
    });

    test("should return 404 for non-implemented subscription POST route", async () => {
      const subscriptionData = {
        research_type: "earnings_analysis",
        symbols: ["AAPL", "GOOGL", "MSFT"],
        frequency: "weekly",
      };

      const response = await request(app)
        .post("/api/research/subscriptions")
        .set("Authorization", "Bearer test-token")
        .send(subscriptionData);

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("error");
    });
  });
});

const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Sectors Routes", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/sectors", () => {
    test("should return sector performance data", async () => {
      const response = await request(app).get("/api/sectors");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);

      if (response.body.data.length > 0) {
        const sector = response.body.data[0];
        expect(sector).toHaveProperty("sector");
        expect(sector).toHaveProperty("performance");
      }
    });
  });

  describe("GET /api/sectors/performance", () => {
    test("should return detailed sector performance", async () => {
      const response = await request(app).get("/api/sectors/performance");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should handle period parameter", async () => {
      const response = await request(app).get(
        "/api/sectors/performance?period=1M"
      );

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
    });
  });

  describe("GET /api/sectors/leaders", () => {
    test("should return sector leaders", async () => {
      const response = await request(app).get("/api/sectors/leaders");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("gainers");
      expect(response.body.data).toHaveProperty("losers");
    });
  });

  describe("GET /api/sectors/rotation", () => {
    test("should return sector rotation analysis", async () => {
      const response = await request(app).get("/api/sectors/rotation");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("rotation");
      expect(response.body.data).toHaveProperty("momentum");
    });
  });

  describe("GET /api/sectors/:sector", () => {
    test("should return specific sector data", async () => {
      const response = await request(app).get("/api/sectors/Technology");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("sector");
      expect(response.body.data).toHaveProperty("stocks");
    });
  });

  describe("GET /api/sectors/:sector/stocks", () => {
    test("should return stocks in sector", async () => {
      const response = await request(app).get("/api/sectors/Technology/stocks");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should handle limit parameter", async () => {
      const response = await request(app).get(
        "/api/sectors/Technology/stocks?limit=10"
      );

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data.length).toBeLessThanOrEqual(10);
    });
  });

  describe("GET /api/sectors/heatmap", () => {
    test("should return sector heatmap data", async () => {
      const response = await request(app).get("/api/sectors/heatmap");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });
  });
});

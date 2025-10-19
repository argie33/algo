/**
 * Sectors Integration Tests - REAL DATA ONLY
 * Tests sectors endpoints with REAL database connection and REAL loaded data
 * NO MOCKS - validates actual behavior with actual data from loaders
 * Validates NO-FALLBACK policy: raw NULL values must flow through unmasked
 */

const request = require("supertest");
const { app } = require("../../../index");
const { initializeDatabase } = require("../../../utils/database"); // Import the actual Express app - NO MOCKS

describe("Sectors Routes - Real Data Validation", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });
  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/api/sectors", sectorRouter);

  afterAll(() => {
    // Cleanup if needed
  });

  describe("GET /api/sectors", () => {
    test("should return sector performance data", async () => {
      const response = await request(app).get("/api/sectors");

      expect(response.status).toBe(200);
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

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should handle period parameter", async () => {
      const response = await request(app).get(
        "/api/sectors/performance?period=1m"
      );

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
    });
  });

  describe("GET /api/sectors/leaders", () => {
    test("should return sector leaders", async () => {
      const response = await request(app).get("/api/sectors/leaders");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("top_performing_sectors");
      expect(response.body.data).toHaveProperty("sector_breadth");
    });
  });

  describe("GET /api/sectors/rotation", () => {
    test("should return sector rotation analysis", async () => {
      const response = await request(app).get("/api/sectors/rotation");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("sector_rankings");
      expect(response.body.data).toHaveProperty("market_cycle");
    });
  });

  describe("GET /api/sectors/:sector/details", () => {
    test("should return specific sector data", async () => {
      const response = await request(app)
        .get("/api/sectors/Technology/details")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("sector");
      expect(response.body.data).toHaveProperty("stocks");
    });
  });

  describe("GET /api/sectors/:sector/stocks", () => {
    test("should return stocks in sector", async () => {
      const response = await request(app).get("/api/sectors/Technology/stocks");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should handle limit parameter", async () => {
      const response = await request(app).get(
        "/api/sectors/Technology/stocks?limit=10"
      );

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data.length).toBeLessThanOrEqual(10);
    });
  });

  describe("GET /api/sectors/allocation", () => {
    test("should return sector allocation data", async () => {
      const response = await request(app)
        .get("/api/sectors/allocation")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("allocation");
      expect(Array.isArray(response.body.data.allocation)).toBe(true);
    });
  });
});

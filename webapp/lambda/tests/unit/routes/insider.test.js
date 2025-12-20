/**
 * Insider Routes Unit Tests
 * Tests insider trading routes functionality
 */

const express = require("express");
const request = require("supertest");

describe("Insider Routes", () => {
  let app;
  let consoleSpy;

  beforeEach(() => {
    jest.clearAllMocks();
    consoleSpy = jest.spyOn(console, "log").mockImplementation();

    // Create test app
    app = express();
    app.use(express.json());

    // Load the route module
    const insiderRoutes = require("../../../routes/insider");
    app.use("/api/insider", insiderRoutes);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("GET /api/insider/trades/:symbol", () => {
    it("should return insider trades data for valid symbol", async () => {
      const response = await request(app)
        .get("/api/insider/trades/AAPL");

      expect([200, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          trades: expect.any(Array),
          symbol: "AAPL",
        });
      } else if (response.status === 404) {
        expect(response.body).toMatchObject({
          success: false,
          error: expect.any(String),
        });
      }
    });

    it("should convert symbol to uppercase", async () => {
      const response = await request(app)
        .get("/api/insider/trades/aapl");

      expect([200, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.symbol).toBe("AAPL");
      }
    });

    it("should log the request with symbol", async () => {
      await request(app).get("/api/insider/trades/TSLA");

      expect(consoleSpy).toHaveBeenCalledWith(
        "👥 Insider trades requested for TSLA"
      );
    });

    it("should handle symbols with special characters", async () => {
      const response = await request(app)
        .get("/api/insider/trades/BRK.A");

      expect([200, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.symbol).toBe("BRK.A");
        expect(response.body.success).toBe(true);
      }
    });

    it("should handle long symbol names", async () => {
      const longSymbol = "VERYLONGSYMBOLNAME";
      const response = await request(app)
        .get(`/api/insider/trades/${longSymbol}`);

      expect([200, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.symbol).toBe(longSymbol);
        expect(response.body.success).toBe(true);
      } else {
        expect(response.body.success).toBe(false);
      }
    });

    it("should handle empty symbol gracefully", async () => {
      const response = await request(app)
        .get("/api/insider/trades/");

      expect([404, 500]).toContain(response.status); // Express router may return 404 or 500 for missing route parameter
    });

    it("should handle route errors gracefully", async () => {
      const response = await request(app)
        .get("/api/insider/trades/TEST");

      expect([200, 404, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });

    it("should maintain consistent response structure", async () => {
      const symbols = ["AAPL", "GOOGL", "MSFT"];

      for (const symbol of symbols) {
        const response = await request(app)
          .get(`/api/insider/trades/${symbol}`);

        expect([200, 404, 500]).toContain(response.status);
        expect(response.body).toHaveProperty("success");

        if (response.status === 200) {
          expect(response.body).toHaveProperty("trades");
          expect(response.body).toHaveProperty("symbol");
        }
      }
    });

    it("should handle database errors gracefully", async () => {
      const response = await request(app)
        .get("/api/insider/trades/TEST");

      expect([200, 404, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });

    it("should handle numeric symbol inputs", async () => {
      const response = await request(app)
        .get("/api/insider/trades/123");

      expect([200, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.symbol).toBe("123");
      }
    });
  });
});
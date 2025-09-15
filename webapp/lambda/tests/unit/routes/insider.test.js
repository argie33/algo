const request = require("supertest");
const express = require("express");
const insiderRouter = require("../../../routes/insider");

const app = express();
app.use("/api/insider", insiderRouter);

describe("Insider Routes", () => {
  let consoleSpy;

  beforeEach(() => {
    consoleSpy = jest.spyOn(console, "log").mockImplementation();
    jest.spyOn(console, "error").mockImplementation();
    jest.clearAllMocks();
  });

  afterEach(() => {
    consoleSpy.mockRestore();
    jest.restoreAllMocks();
  });

  describe("GET /api/insider/trades/:symbol", () => {
    it("should return 501 status for not implemented endpoint", async () => {
      const response = await request(app)
        .get("/api/insider/trades/AAPL")
        .expect(501);

      expect(response.body).toEqual({
        success: false,
        error: "Insider trading data not implemented",
        details:
          "This endpoint requires SEC filing data integration which is not yet implemented.",
        troubleshooting: {
          suggestion:
            "Insider trading data requires integration with SEC EDGAR database",
          required_setup: [
            "SEC EDGAR API integration",
            "Insider trading database tables",
            "Real-time filing data pipeline",
          ],
          status: "Not implemented - requires SEC data integration",
        },
        symbol: "AAPL",
        timestamp: expect.any(String),
      });
    });

    it("should convert symbol to uppercase", async () => {
      const response = await request(app)
        .get("/api/insider/trades/aapl")
        .expect(501);

      expect(response.body.symbol).toBe("AAPL");
    });

    it("should log the request with symbol", async () => {
      await request(app).get("/api/insider/trades/TSLA");

      expect(consoleSpy).toHaveBeenCalledWith(
        "👥 Insider trades requested for TSLA - not implemented"
      );
    });

    it("should include valid ISO timestamp", async () => {
      const response = await request(app)
        .get("/api/insider/trades/GOOGL")
        .expect(501);

      const timestamp = response.body.timestamp;
      expect(timestamp).toMatch(
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/
      );
      expect(new Date(timestamp)).toBeInstanceOf(Date);
      expect(new Date(timestamp).getTime()).not.toBeNaN();
    });

    it("should handle symbols with special characters", async () => {
      const response = await request(app)
        .get("/api/insider/trades/BRK.A")
        .expect(501);

      expect(response.body.symbol).toBe("BRK.A");
      expect(response.body.success).toBe(false);
    });

    it("should handle long symbol names", async () => {
      const longSymbol = "VERYLONGSYMBOLNAME";
      const response = await request(app)
        .get(`/api/insider/trades/${longSymbol}`)
        .expect(501);

      expect(response.body.symbol).toBe(longSymbol);
      expect(consoleSpy).toHaveBeenCalledWith(
        `👥 Insider trades requested for ${longSymbol} - not implemented`
      );
    });

    it("should handle empty symbol gracefully", async () => {
      const response = await request(app)
        .get("/api/insider/trades/")
        .expect(404); // Express router will return 404 for missing route parameter
    });

    it("should handle route error and return 500", async () => {
      // Mock console.log to throw an error
      consoleSpy.mockImplementation(() => {
        throw new Error("Console logging failed");
      });

      const response = await request(app)
        .get("/api/insider/trades/AAPL")
        .expect(500);

      expect(response.body).toEqual({
        success: false,
        error: "Failed to fetch insider trades",
        message: "Console logging failed",
      });

      expect(console.error).toHaveBeenCalledWith(
        "Insider trades error:",
        expect.any(Error)
      );
    });

    it("should maintain consistent response structure for different symbols", async () => {
      const symbols = ["AAPL", "GOOGL", "MSFT", "AMZN"];

      for (const symbol of symbols) {
        const response = await request(app)
          .get(`/api/insider/trades/${symbol}`)
          .expect(501);

        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.body).toHaveProperty("details");
        expect(response.body).toHaveProperty("troubleshooting");
        expect(response.body).toHaveProperty("symbol", symbol);
        expect(response.body).toHaveProperty("timestamp");
        expect(response.body.troubleshooting).toHaveProperty("required_setup");
        expect(
          Array.isArray(response.body.troubleshooting.required_setup)
        ).toBe(true);
      }
    });

    it("should have consistent error message structure", async () => {
      const response = await request(app)
        .get("/api/insider/trades/TEST")
        .expect(501);

      expect(response.body.troubleshooting.required_setup).toHaveLength(3);
      expect(response.body.troubleshooting.required_setup).toContain(
        "SEC EDGAR API integration"
      );
      expect(response.body.troubleshooting.required_setup).toContain(
        "Insider trading database tables"
      );
      expect(response.body.troubleshooting.required_setup).toContain(
        "Real-time filing data pipeline"
      );
    });

    it("should handle numeric symbol inputs", async () => {
      const response = await request(app)
        .get("/api/insider/trades/123")
        .expect(501);

      expect(response.body.symbol).toBe("123");
      expect(response.body.success).toBe(false);
    });
  });
});

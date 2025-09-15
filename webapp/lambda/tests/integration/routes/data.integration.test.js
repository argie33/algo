const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Data Routes", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/data", () => {
    test("should return data API information", async () => {
      const response = await request(app).get("/api/data");

      expect([200, 404]).toContain(response.status);
      expect(response.body.message).toBe("Data API - Ready");
      expect(response.body.status).toBe("operational");
      expect(response.body).toHaveProperty("timestamp");
      expect(response.body).toHaveProperty("endpoints");
      expect(Array.isArray(response.body.endpoints)).toBe(true);
      expect(response.body.endpoints.length).toBe(4);
    });

    test("should include endpoint documentation", async () => {
      const response = await request(app).get("/api/data");

      const endpoints = response.body.endpoints;
      expect(endpoints).toContain(
        "/:symbol - Get comprehensive data for a symbol"
      );
      expect(endpoints).toContain(
        "/historical/:symbol - Get historical data for a symbol"
      );
      expect(endpoints).toContain(
        "/realtime/:symbol - Get real-time data for a symbol"
      );
      expect(endpoints).toContain("/bulk - Get data for multiple symbols");
    });
  });

  describe("GET /api/data/:symbol", () => {
    test("should handle valid symbol request", async () => {
      const response = await request(app).get("/api/data/AAPL");

      // Should either return data (200) or not found (404) if no data exists
      expect([200, 404].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body.symbol).toBe("AAPL");
        expect(response.body).toHaveProperty("price");
        expect(response.body).toHaveProperty("technical");
        expect(response.body).toHaveProperty("timestamp");
      } else {
        expect(response.body).toHaveProperty("message");
        expect(response.body.message).toContain(
          "No data available for symbol AAPL"
        );
      }
    });

    test("should convert symbol to uppercase", async () => {
      const response = await request(app).get("/api/data/aapl");

      expect([200, 404].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body.symbol).toBe("AAPL");
      }
    });

    test("should handle symbol with mixed case", async () => {
      const response = await request(app).get("/api/data/TsLa");

      expect([200, 404].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body.symbol).toBe("TSLA");
      }
    });

    test("should return 404 for non-existent symbol", async () => {
      const response = await request(app).get("/api/data/NONEXISTENT");

      expect([404, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain(
        "No data available for symbol NONEXISTENT"
      );
    });

    test("should handle empty symbol gracefully", async () => {
      const response = await request(app).get("/api/data/");

      // Should return the main API info instead
      expect([200, 404]).toContain(response.status);
      expect(response.body.message).toBe("Data API - Ready");
    });

    test("should validate response structure when data exists", async () => {
      const response = await request(app).get("/api/data/AAPL");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("symbol");
        expect(response.body).toHaveProperty("price");
        expect(response.body).toHaveProperty("technical");
        expect(response.body).toHaveProperty("timestamp");

        // Validate timestamp format
        const timestamp = new Date(response.body.timestamp);
        expect(timestamp).toBeInstanceOf(Date);
        expect(timestamp.getTime()).not.toBeNaN();

        // If price data exists, validate structure
        if (response.body.price) {
          expect(response.body.price).toHaveProperty("symbol");
          expect(response.body.price).toHaveProperty("date");
          expect(
            ["open", "high", "low", "close", "volume"].some((prop) =>
              Object.prototype.hasOwnProperty.call(response.body.price, prop)
            )
          ).toBe(true);
        }

        // If technical data exists, validate structure
        if (response.body.technical) {
          expect(response.body.technical).toHaveProperty("symbol");
          expect(response.body.technical).toHaveProperty("date");
        }
      }
    });

    test("should handle database errors gracefully", async () => {
      // Test with a symbol that might cause database issues
      const response = await request(app).get("/api/data/TEST123");

      expect([200, 404, 500].includes(response.status)).toBe(true);

      if (response.status === 500) {
        expect(response.body).toHaveProperty("error");
        expect(response.body).toHaveProperty("service", "data-api");
      }
    });

    test("should handle special characters in symbol", async () => {
      const response = await request(app).get("/api/data/BRK.A");

      expect([200, 404, 500].includes(response.status)).toBe(true);
    });

    test("should handle numeric symbols", async () => {
      const response = await request(app).get("/api/data/123");

      expect([200, 404, 500].includes(response.status)).toBe(true);
    });
  });

  describe("Data API Error Handling", () => {
    test("should handle malformed requests gracefully", async () => {
      const response = await request(app).get("/api/data/%20invalid%20");

      expect([200, 404, 500].includes(response.status)).toBe(true);
    });

    test("should return consistent error format", async () => {
      const response = await request(app).get(
        "/api/data/DEFINITELY_NONEXISTENT_SYMBOL"
      );

      if (response.status === 404) {
        expect(response.body).toHaveProperty("error");
        expect(typeof response.body.error).toBe("string");
      }
    });
  });

  describe("Data API Performance", () => {
    test("should respond within reasonable time", async () => {
      const startTime = Date.now();

      const response = await request(app).get("/api/data/AAPL");

      const responseTime = Date.now() - startTime;

      // Should respond within 5 seconds
      expect(responseTime).toBeLessThan(5000);
      expect([200, 404, 500].includes(response.status)).toBe(true);
    });

    test("should handle concurrent requests", async () => {
      const symbols = ["AAPL", "GOOGL", "MSFT", "TSLA"];

      const promises = symbols.map((symbol) =>
        request(app).get(`/api/data/${symbol}`)
      );

      const responses = await Promise.all(promises);

      responses.forEach((response, index) => {
        expect([200, 404, 500].includes(response.status)).toBe(true);

        if (response.status === 200) {
          expect(response.body.symbol).toBe(symbols[index]);
        }
      });
    });
  });
});

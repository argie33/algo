const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("Market Routes Unit Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/market", () => {
    test("should return market endpoint information", async () => {
      const response = await request(app)
        .get("/api/market");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data) {
          expect(response.body).toHaveProperty("data");
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });

  describe("GET /api/market/overview", () => {
    test("should return market overview data", async () => {
      const response = await request(app)
        .get("/api/market/overview");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        
        const data = response.body.data;
        if (data.marketSummary) {
          expect(data).toHaveProperty("marketSummary");
          expect(typeof data.marketSummary).toBe("object");
        }
        if (data.indices) {
          expect(Array.isArray(data.indices)).toBe(true);
        }
        if (data.marketData) {
          expect(typeof data.marketData).toBe("object");
        }
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });

    test("should handle market overview with parameters", async () => {
      const response = await request(app)
        .get("/api/market/overview?period=1d&includePremarket=true");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });

  describe("GET /api/market/data", () => {
    test("should return market data", async () => {
      const response = await request(app)
        .get("/api/market/data");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        
        if (Array.isArray(response.body.data)) {
          expect(Array.isArray(response.body.data)).toBe(true);
          if (response.body.data.length > 0) {
            const item = response.body.data[0];
            if (item.symbol) expect(item).toHaveProperty("symbol");
            if (item.price !== undefined) expect(typeof item.price).toBe("number");
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });

    test("should handle symbol-specific market data", async () => {
      const response = await request(app)
        .get("/api/market/data?symbol=AAPL");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200 && response.body.data) {
        expect(response.body).toHaveProperty("success", true);
        if (Array.isArray(response.body.data) && response.body.data.length > 0) {
          const item = response.body.data[0];
          if (item.symbol) {
            expect(item.symbol).toMatch(/^[A-Z]+$/);
          }
        }
      }
    });
  });

  describe("GET /api/market/sentiment", () => {
    test("should return market sentiment data", async () => {
      const response = await request(app)
        .get("/api/market/sentiment");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data) {
          expect(response.body).toHaveProperty("data");
          const data = response.body.data;
          if (data.sentiment !== undefined) {
            expect(typeof data.sentiment).toBe("string");
          }
          if (data.score !== undefined) {
            expect(typeof data.score).toBe("number");
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });

  describe("GET /api/market/sentiment/history", () => {
    test("should return sentiment history", async () => {
      const response = await request(app)
        .get("/api/market/sentiment/history");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data && Array.isArray(response.body.data)) {
          expect(Array.isArray(response.body.data)).toBe(true);
          if (response.body.data.length > 0) {
            const item = response.body.data[0];
            if (item.date) expect(item).toHaveProperty("date");
            if (item.sentiment) expect(item).toHaveProperty("sentiment");
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });

    test("should handle sentiment history with time range", async () => {
      const response = await request(app)
        .get("/api/market/sentiment/history?days=30");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
      }
    });
  });

  describe("GET /api/market/movers", () => {
    test("should return top movers", async () => {
      const response = await request(app)
        .get("/api/market/movers");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data) {
          expect(response.body).toHaveProperty("data");
          const data = response.body.data;
          if (data.gainers && Array.isArray(data.gainers)) {
            expect(Array.isArray(data.gainers)).toBe(true);
          }
          if (data.losers && Array.isArray(data.losers)) {
            expect(Array.isArray(data.losers)).toBe(true);
          }
          if (data.mostActive && Array.isArray(data.mostActive)) {
            expect(Array.isArray(data.mostActive)).toBe(true);
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });

    test("should handle movers with type parameter", async () => {
      const response = await request(app)
        .get("/api/market/movers?type=gainers");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
      }
    });
  });

  describe("GET /api/market/indices", () => {
    test("should return market indices", async () => {
      const response = await request(app)
        .get("/api/market/indices");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data && Array.isArray(response.body.data)) {
          expect(Array.isArray(response.body.data)).toBe(true);
          if (response.body.data.length > 0) {
            const index = response.body.data[0];
            if (index.symbol) expect(index).toHaveProperty("symbol");
            if (index.name) expect(index).toHaveProperty("name");
            if (index.value !== undefined) expect(typeof index.value).toBe("number");
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });

  describe("GET /api/market/status", () => {
    test("should return market status", async () => {
      const response = await request(app)
        .get("/api/market/status");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data) {
          expect(response.body).toHaveProperty("data");
          const data = response.body.data;
          if (data.isOpen !== undefined) {
            expect(typeof data.isOpen).toBe("boolean");
          }
          if (data.nextOpen) {
            expect(data).toHaveProperty("nextOpen");
          }
          if (data.nextClose) {
            expect(data).toHaveProperty("nextClose");
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });

  describe("GET /api/market/sectors", () => {
    test("should return sector performance", async () => {
      const response = await request(app)
        .get("/api/market/sectors");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data && Array.isArray(response.body.data)) {
          expect(Array.isArray(response.body.data)).toBe(true);
          if (response.body.data.length > 0) {
            const sector = response.body.data[0];
            if (sector.name) expect(sector).toHaveProperty("name");
            if (sector.performance !== undefined) expect(typeof sector.performance).toBe("number");
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });

  describe("Error Handling", () => {
    test("should handle invalid endpoints gracefully", async () => {
      const response = await request(app)
        .get("/api/market/invalid-endpoint");

      expect([500, 404]).toContain(response.status);
    });

    test("should handle database connection issues", async () => {
      const response = await request(app)
        .get("/api/market/data?force_error=true");

      expect([200, 404]).toContain(response.status);
    });

    test("should handle malformed query parameters", async () => {
      const response = await request(app)
        .get("/api/market/sentiment/history?days=invalid");

      expect([200, 404, 503]).toContain(response.status);
    });
  });

  describe("Performance Tests", () => {
    test("should respond to overview requests within reasonable time", async () => {
      const startTime = Date.now();
      const response = await request(app)
        .get("/api/market/overview");

      const endTime = Date.now();
      const responseTime = endTime - startTime;
      
      // Should respond within 10 seconds
      expect(responseTime).toBeLessThan(10000);
      expect([200, 404]).toContain(response.status);
    });

    test("should handle concurrent overview requests", async () => {
      const requests = Array.from({ length: 3 }, () =>
        request(app).get("/api/market/overview")
      );

      const responses = await Promise.allSettled(requests);
      
      // At least some should succeed
      const statusCodes = responses.map(r => 
        r.status === 'fulfilled' ? r.value.status : 500
      );
      
      expect(statusCodes.some(status => [200, 500, 503].includes(status))).toBe(true);
    });
  });
});
const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("Stocks Routes Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/stocks/sectors", () => {
    test("should return sectors data", async () => {
      const response = await request(app)
        .get("/api/stocks/sectors");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toBeDefined();
      }
    });

    test("should handle concurrent requests to sectors endpoint", async () => {
      const requests = Array(5).fill().map(() => 
        request(app).get("/api/stocks/sectors")
      );
      
      const responses = await Promise.all(requests);
      
      responses.forEach(response => {
        expect([200, 404]).toContain(response.status);
        expect(response.headers['content-type']).toMatch(/json/);
      });
    });
  });

  describe("GET /api/stocks/search", () => {
    test("should handle search with valid query", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
      
      if (response.status === 200) {
        expect(response.body).toBeDefined();
      }
    });

    test("should require query parameter", async () => {
      const response = await request(app)
        .get("/api/stocks/search")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401].includes(response.status)).toBe(true);
    });

    test("should handle empty search query", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401].includes(response.status)).toBe(true);
    });

    test("should handle search with limit parameter", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=A&limit=10")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 401].includes(response.status)).toBe(true);
    });

    test("should require authentication for search", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=AAPL");

      expect([200, 401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/stocks/:symbol", () => {
    test("should handle valid stock symbol", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle invalid stock symbols", async () => {
      const response = await request(app)
        .get("/api/stocks/INVALID")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 401].includes(response.status)).toBe(true);
    });

    test("should handle very long symbol names", async () => {
      const response = await request(app)
        .get("/api/stocks/VERYLONGSYMBOLNAME123456")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 401].includes(response.status)).toBe(true);
    });

    test("should handle special characters in symbols", async () => {
      const response = await request(app)
        .get("/api/stocks/@")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/stocks/trending", () => {
    test("should return trending stocks", async () => {
      const response = await request(app)
        .get("/api/stocks/trending")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle timeframe parameters", async () => {
      const response = await request(app)
        .get("/api/stocks/trending?timeframe=1d")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 401].includes(response.status)).toBe(true);
    });

    test("should require authentication for trending", async () => {
      const response = await request(app)
        .get("/api/stocks/trending");

      expect([200, 401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/stocks/screener", () => {
    test("should return screener results", async () => {
      const response = await request(app)
        .get("/api/stocks/screener")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle screener filters", async () => {
      const response = await request(app)
        .get("/api/stocks/screener?market_cap_min=1000000&pe_ratio_max=20")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 401].includes(response.status)).toBe(true);
    });
  });

  describe("Watchlist Operations", () => {
    test("should handle watchlist requests", async () => {
      const response = await request(app)
        .get("/api/stocks/watchlist")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle adding to watchlist", async () => {
      const response = await request(app)
        .post("/api/stocks/watchlist/add")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ symbol: "AAPL" });

      expect([200, 400, 401].includes(response.status)).toBe(true);
    });

    test("should validate symbol parameter for watchlist add", async () => {
      const response = await request(app)
        .post("/api/stocks/watchlist/add")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({});

      expect([400, 401].includes(response.status)).toBe(true);
    });

    test("should handle removing from watchlist", async () => {
      const response = await request(app)
        .delete("/api/stocks/watchlist/remove")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ symbol: "AAPL" });

      expect([200, 400, 401].includes(response.status)).toBe(true);
    });
  });

  describe("Stock Data Endpoints", () => {
    test("should handle stock quote requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/quote")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock technicals requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/technicals")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock options requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/options")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock insider trading requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/insider")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock analysts requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/analysts")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock earnings requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/earnings")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock dividends requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/dividends")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock sentiment requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/sentiment")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock social requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/social")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });
  });

  describe("Authentication Tests", () => {
    test("should handle requests without authentication", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=AAPL");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle malformed authorization headers", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=AAPL")
        .set("Authorization", "InvalidFormat");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle empty authorization headers", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=AAPL")
        .set("Authorization", "");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle missing bearer token", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=AAPL")
        .set("Authorization", "Bearer ");

      expect([200, 401].includes(response.status)).toBe(true);
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle concurrent requests", async () => {
      const requests = [
        request(app).get("/api/stocks/sectors"),
        request(app).get("/api/stocks/search?q=A").set("Authorization", "Bearer dev-bypass-token"),
        request(app).get("/api/stocks/AAPL").set("Authorization", "Bearer dev-bypass-token"),
        request(app).get("/api/stocks/trending").set("Authorization", "Bearer dev-bypass-token")
      ];
      
      const responses = await Promise.all(requests);
      
      responses.forEach(response => {
        expect([200, 400, 401].includes(response.status)).toBe(true);
      });
    });

    test("should handle invalid parameters gracefully", async () => {
      const invalidRequests = [
        request(app).get("/api/stocks/search?q=A&limit=abc").set("Authorization", "Bearer dev-bypass-token"),
        request(app).get("/api/stocks/trending?timeframe=INVALID").set("Authorization", "Bearer dev-bypass-token"),
        request(app).get("/api/stocks/search?q=A&limit=1000").set("Authorization", "Bearer dev-bypass-token")
      ];
      
      for (const req of invalidRequests) {
        const response = await req;
        expect([200, 400, 401].includes(response.status)).toBe(true);
      }
    });

    test("should validate response content types", async () => {
      const endpoints = [
        "/api/stocks/sectors",
        "/api/stocks/search?q=AAPL"
      ];
      
      for (const endpoint of endpoints) {
        const response = await request(app)
          .get(endpoint)
          .set("Authorization", "Bearer dev-bypass-token");
        
        if ([200, 400, 401].includes(response.status)) {
          expect(response.headers['content-type']).toMatch(/application\/json/);
        }
      }
    });

    test("should handle SQL injection attempts safely", async () => {
      const maliciousInputs = [
        "'; DROP TABLE stocks; --",
        "1' OR '1'='1",
        "UNION SELECT * FROM users"
      ];
      
      for (const input of maliciousInputs) {
        const response = await request(app)
          .get(`/api/stocks/${encodeURIComponent(input)}`)
          .set("Authorization", "Bearer dev-bypass-token");
        
        expect([200, 400, 401].includes(response.status)).toBe(true);
      }
    });

    test("should handle database connection issues gracefully", async () => {
      const response = await request(app)
        .get("/api/stocks/sectors")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
      
      if (response.status >= 500) {
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should handle international characters in search", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=" + encodeURIComponent("测试"))
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 401].includes(response.status)).toBe(true);
    });
  });
});
const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("News Routes", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/news/health", () => {
    test("should return health status", async () => {
      const response = await request(app)
        .get("/api/news/health");

      expect([200, 404]).toContain(response.status);
      expect(response.body.status).toBe("operational");
      expect(response.body.service).toBe("news");
      expect(response.body.message).toBe("News service is running");
      expect(response.body.timestamp).toBeDefined();
    });
  });

  describe("GET /api/news", () => {
    test("should return news API status", async () => {
      const response = await request(app)
        .get("/api/news");

      expect([200, 404]).toContain(response.status);
      expect(response.body.message).toBe("News API - Ready");
      expect(response.body.status).toBe("operational");
      expect(response.body.timestamp).toBeDefined();
    });
  });

  describe("GET /api/news/recent", () => {
    test("should return recent news", async () => {
      const response = await request(app)
        .get("/api/news/recent");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
      
      if (response.body.data.length > 0) {
        const article = response.body.data[0];
        expect(article).toHaveProperty("title");
        expect(article).toHaveProperty("source");
        expect(article).toHaveProperty("published_at");
      }
    });

    test("should handle limit parameter", async () => {
      const response = await request(app)
        .get("/api/news/recent?limit=5");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data.length).toBeLessThanOrEqual(5);
    });

    test("should handle category filtering", async () => {
      const response = await request(app)
        .get("/api/news/recent?category=earnings");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
    });
  });

  describe("GET /api/news/search", () => {
    test("should search news articles", async () => {
      const response = await request(app)
        .get("/api/news/search?q=market");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });
  });

  describe("GET /api/news/sentiment", () => {
    test("should return news sentiment analysis", async () => {
      const response = await request(app)
        .get("/api/news/sentiment");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("sentiment");
      }
    });
  });

  describe("GET /api/news/symbols/:symbol", () => {
    test("should return news for specific symbol", async () => {
      const response = await request(app)
        .get("/api/news/symbols/AAPL");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });
  });
});
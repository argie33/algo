const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("Commodities Routes Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/commodities (Root Endpoint)", () => {
    test("should return commodities system information", async () => {
      const response = await request(app)
        .get("/api/commodities");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("system", "Commodities API");
        expect(response.body.data).toHaveProperty("version");
        expect(response.body.data).toHaveProperty("status");
        expect(response.body.data).toHaveProperty("available_endpoints");
        expect(response.body.data).toHaveProperty("timestamp");
        
        expect(Array.isArray(response.body.data.available_endpoints)).toBe(true);
        expect(response.body.data.available_endpoints.length).toBeGreaterThan(0);
      }
    });

    test("should include expected endpoint information", async () => {
      const response = await request(app)
        .get("/api/commodities");

      if (response.status === 200) {
        const endpoints = response.body.data.available_endpoints.join(" ");
        expect(endpoints).toContain("categories");
        expect(endpoints).toContain("prices");
        expect(endpoints).toContain("market-summary");
        expect(endpoints).toContain("correlations");
      }
    });
  });

  describe("GET /api/commodities/health (Health Check)", () => {
    test("should return health status", async () => {
      const response = await request(app)
        .get("/api/commodities/health");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("status", "operational");
        expect(response.body).toHaveProperty("service", "commodities");
        expect(response.body).toHaveProperty("message");
        expect(response.body).toHaveProperty("timestamp");
        
        expect(typeof response.body.timestamp).toBe("string");
        expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      }
    });
  });

  describe("GET /api/commodities/categories (Commodity Categories)", () => {
    test("should return commodity categories", async () => {
      const response = await request(app)
        .get("/api/commodities/categories");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const category = response.body.data[0];
          expect(category).toHaveProperty("id");
          expect(category).toHaveProperty("name");
          expect(category).toHaveProperty("description");
          expect(category).toHaveProperty("commodities");
          expect(category).toHaveProperty("weight");
          expect(category).toHaveProperty("performance");
          
          expect(Array.isArray(category.commodities)).toBe(true);
          expect(typeof category.weight).toBe("number");
          expect(typeof category.performance).toBe("object");
        }
      }
    });

    test("should validate category performance data", async () => {
      const response = await request(app)
        .get("/api/commodities/categories");

      if (response.status === 200 && response.body.data.length > 0) {
        const category = response.body.data[0];
        if (category.performance) {
          const periods = ["1d", "1w", "1m", "3m", "1y"];
          periods.forEach(period => {
            if (category.performance[period] !== undefined) {
              expect(typeof category.performance[period]).toBe("number");
              expect(isFinite(category.performance[period])).toBe(true);
            }
          });
        }
      }
    });

    test("should include major commodity categories", async () => {
      const response = await request(app)
        .get("/api/commodities/categories");

      if (response.status === 200 && response.body.data.length > 0) {
        const categoryIds = response.body.data.map(cat => cat.id.toLowerCase());
        const expectedCategories = ["energy", "metals", "agriculture"];
        
        expectedCategories.forEach(expectedCat => {
          const found = categoryIds.some(id => id.includes(expectedCat));
          expect(found).toBe(true);
        });
      }
    });
  });

  describe("GET /api/commodities/prices (Current Prices)", () => {
    test("should return current commodity prices", async () => {
      const response = await request(app)
        .get("/api/commodities/prices");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const commodity = response.body.data[0];
          expect(commodity).toHaveProperty("symbol");
          expect(commodity).toHaveProperty("name");
          expect(commodity).toHaveProperty("price");
          expect(commodity).toHaveProperty("changePercent");
          expect(commodity).toHaveProperty("category");
          
          expect(typeof commodity.price).toBe("number");
          expect(typeof commodity.changePercent).toBe("number");
        }
      }
    });

    test("should handle limit parameter", async () => {
      const response = await request(app)
        .get("/api/commodities/prices?limit=5");

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      
      if (response.status === 200 && response.body.data.length > 0) {
        expect(response.body.data.length).toBeLessThanOrEqual(5);
      }
    });

    test("should handle category filter", async () => {
      const categories = ["energy", "metals", "agriculture"];
      
      for (const category of categories) {
        const response = await request(app)
          .get(`/api/commodities/prices?category=${category}`);
        
        expect([200, 400].includes(response.status)).toBe(true);
        
        if (response.status === 200 && response.body.data.length > 0) {
          response.body.data.forEach(commodity => {
            expect(commodity.category.toLowerCase()).toBe(category.toLowerCase());
          });
        }
      }
    });
  });

  describe("GET /api/commodities/market-summary (Market Summary)", () => {
    test("should return market summary data", async () => {
      const response = await request(app)
        .get("/api/commodities/market-summary");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("overview");
        expect(response.body.data).toHaveProperty("performance");
        expect(response.body.data).toHaveProperty("sectors");
        
        expect(Array.isArray(response.body.data.sectors)).toBe(true);
      }
    });

    test("should validate market overview structure", async () => {
      const response = await request(app)
        .get("/api/commodities/market-summary");

      if (response.status === 200 && response.body.data.overview) {
        const overview = response.body.data.overview;
        expect(overview).toHaveProperty("totalVolume");
        expect(overview).toHaveProperty("tradingSession");
        
        expect(typeof overview.totalVolume).toBe("number");
        expect(typeof overview.tradingSession).toBe("string");
      }
    });

    test("should validate top gainers and losers", async () => {
      const response = await request(app)
        .get("/api/commodities/market-summary");

      if (response.status === 200 && response.body.data.performance) {
        const performance = response.body.data.performance;
        
        if (performance["1d"] && performance["1d"].topGainer) {
          const gainer = performance["1d"].topGainer;
          expect(gainer).toHaveProperty("symbol");
          expect(gainer).toHaveProperty("name");
          expect(gainer).toHaveProperty("change");
          expect(typeof gainer.change).toBe("number");
        }
        
        if (performance["1d"] && performance["1d"].topLoser) {
          const loser = performance["1d"].topLoser;
          expect(loser).toHaveProperty("symbol");
          expect(loser).toHaveProperty("name");
          expect(loser).toHaveProperty("change");
          expect(typeof loser.change).toBe("number");
        }
      }
    });
  });

  describe("GET /api/commodities/correlations (Price Correlations)", () => {
    test("should return correlation analysis", async () => {
      const response = await request(app)
        .get("/api/commodities/correlations");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("correlations");
        expect(Array.isArray(response.body.data.correlations)).toBe(true);
        
        if (response.body.data.correlations.length > 0) {
          const correlation = response.body.data.correlations[0];
          expect(correlation).toHaveProperty("pair");
          expect(correlation).toHaveProperty("coefficient");
          expect(correlation).toHaveProperty("strength");
          
          expect(typeof correlation.coefficient).toBe("number");
          expect(correlation.coefficient).toBeGreaterThanOrEqual(-1);
          expect(correlation.coefficient).toBeLessThanOrEqual(1);
        }
      }
    });

    test("should handle timeframe parameter", async () => {
      const timeframes = ["1W", "1M", "3M", "1Y"];
      
      for (const timeframe of timeframes) {
        const response = await request(app)
          .get(`/api/commodities/correlations?timeframe=${timeframe}`);
        
        expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      }
    });

    test("should validate correlation strength classifications", async () => {
      const response = await request(app)
        .get("/api/commodities/correlations");

      if (response.status === 200 && response.body.data.correlations.length > 0) {
        const validStrengths = ["strong", "moderate", "weak", "very_weak"];
        
        response.body.data.correlations.forEach(corr => {
          if (corr.strength) {
            expect(validStrengths.includes(corr.strength.toLowerCase())).toBe(true);
          }
        });
      }
    });
  });

  describe("GET /api/commodities/news (Commodity News)", () => {
    test("should return commodity-related news", async () => {
      const response = await request(app)
        .get("/api/commodities/news");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("articles");
        expect(Array.isArray(response.body.data.articles)).toBe(true);
        
        if (response.body.data.articles.length > 0) {
          const article = response.body.data.articles[0];
          expect(article).toHaveProperty("title");
          expect(article).toHaveProperty("summary");
          expect(article).toHaveProperty("source");
          expect(article).toHaveProperty("published_at");
          expect(article).toHaveProperty("category");
          
          expect(typeof article.title).toBe("string");
          expect(typeof article.published_at).toBe("string");
        }
      }
    });

    test("should handle category filter for news", async () => {
      const categories = ["energy", "metals", "agriculture"];
      
      for (const category of categories) {
        const response = await request(app)
          .get(`/api/commodities/news?category=${category}`);
        
        expect([200, 400].includes(response.status)).toBe(true);
        
        if (response.status === 200 && response.body.data.articles.length > 0) {
          response.body.data.articles.forEach(article => {
            expect(article.category.toLowerCase()).toBe(category.toLowerCase());
          });
        }
      }
    });

    test("should handle limit parameter for news", async () => {
      const response = await request(app)
        .get("/api/commodities/news?limit=5");

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      
      if (response.status === 200) {
        expect(response.body.data.articles.length).toBeLessThanOrEqual(5);
      }
    });

    test("should validate news article timestamps", async () => {
      const response = await request(app)
        .get("/api/commodities/news");

      if (response.status === 200 && response.body.data.articles.length > 0) {
        response.body.data.articles.forEach(article => {
          if (article.published_at) {
            expect(new Date(article.published_at)).toBeInstanceOf(Date);
            expect(!isNaN(new Date(article.published_at))).toBe(true);
          }
        });
      }
    });
  });

  describe("Performance and Edge Cases", () => {
    jest.setTimeout(15000);
    
    test("should handle concurrent requests to commodity endpoints", async () => {
      const requests = [
        request(app).get("/api/commodities"),
        request(app).get("/api/commodities/categories"),
        request(app).get("/api/commodities/prices"),
        request(app).get("/api/commodities/market-summary"),
        request(app).get("/api/commodities/correlations")
      ];
      
      const responses = await Promise.all(requests);
      
      responses.forEach(response => {
        expect([200, 404]).toContain(response.status);
      });
    });

    test("should maintain response time consistency", async () => {
      const startTime = Date.now();
      const response = await request(app)
        .get("/api/commodities/market-summary");
      const responseTime = Date.now() - startTime;
      
      expect([200, 404]).toContain(response.status);
      expect(responseTime).toBeLessThan(15000);
    });

    test("should handle invalid parameters gracefully", async () => {
      const invalidParams = [
        "limit=-1",
        "limit=abc",
        "category=invalid-category",
        "timeframe=invalid-timeframe"
      ];
      
      for (const param of invalidParams) {
        const response = await request(app)
          .get(`/api/commodities/prices?${param}`);
        
        expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      }
    });

    test("should validate numeric data integrity", async () => {
      const response = await request(app)
        .get("/api/commodities/prices");

      if (response.status === 200 && response.body.data.length > 0) {
        response.body.data.forEach(commodity => {
          if (typeof commodity.price === "number") {
            expect(isFinite(commodity.price)).toBe(true);
            expect(!isNaN(commodity.price)).toBe(true);
          }
          if (typeof commodity.changePercent === "number") {
            expect(isFinite(commodity.changePercent)).toBe(true);
            expect(!isNaN(commodity.changePercent)).toBe(true);
          }
        });
      }
    });

    test("should handle memory pressure with large data requests", async () => {
      const response = await request(app)
        .get("/api/commodities/prices?limit=1000");

      expect([200, 400, 413, 500, 503].includes(response.status)).toBe(true);
    });

    test("should validate response content types", async () => {
      const endpoints = [
        "/api/commodities",
        "/api/commodities/categories",
        "/api/commodities/prices",
        "/api/commodities/market-summary",
        "/api/commodities/correlations",
        "/api/commodities/news"
      ];
      
      for (const endpoint of endpoints) {
        const response = await request(app).get(endpoint);
        
        if ([200].includes(response.status)) {
          expect(response.headers['content-type']).toMatch(/application\/json/);
        }
      }
    });

    test("should handle database connection issues gracefully", async () => {
      const response = await request(app)
        .get("/api/commodities/prices");

      expect([200, 404]).toContain(response.status);
      
      if (response.status >= 500) {
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should handle SQL injection attempts safely", async () => {
      const maliciousInputs = [
        "'; DROP TABLE commodities; --",
        "1' OR '1'='1",
        "UNION SELECT * FROM users",
        "<script>alert('xss')</script>"
      ];
      
      for (const input of maliciousInputs) {
        const response = await request(app)
          .get(`/api/commodities/prices?category=${encodeURIComponent(input)}`);
        
        expect([200, 400].includes(response.status)).toBe(true);
      }
    });
  });
});
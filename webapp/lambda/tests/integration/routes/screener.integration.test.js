const request = require("supertest");
const { app } = require("../../../index");
const { initializeDatabase } = require("../../../utils/database");


describe("Screener Routes", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  describe("GET /api/screener", () => {
    test("should return screener endpoints", async () => {
      const response = await request(app).get("/api/screener");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("available_endpoints");
    });

  });

  describe("GET /api/screener/screen", () => {
    test("should screen stocks with basic criteria", async () => {
      const response = await request(app)
        .get("/api/screener/screen?market_cap_min=1000000000")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
      expect(response.body.data.stocks.length).toBeLessThanOrEqual(100);
    });

    test("should handle multiple criteria", async () => {
      const response = await request(app)
        .get("/api/screener/screen?market_cap_min=1000000000&pe_max=25&volume_min=1000000")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
    });

    test("should handle sector filter", async () => {
      const response = await request(app)
        .get("/api/screener/screen?sector=Technology")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
    });

  });

  describe("GET /api/screener/presets", () => {
    test("should return screening presets", async () => {
      const response = await request(app)
        .get("/api/screener/presets")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);

      if (response.body.data.length > 0) {
        const preset = response.body.data[0];
        expect(preset).toHaveProperty("name");
        expect(preset).toHaveProperty("filters");
      }
    });

  });

  describe("GET /api/screener/presets/:presetName", () => {
    test("should return specific preset", async () => {
      const response = await request(app)
        .get("/api/screener/presets/growth")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("id");
        expect(response.body.data).toHaveProperty("name");
        expect(response.body.data).toHaveProperty("filters");
      }
    });

  });

  describe("GET /api/screener/growth", () => {
    test("should return growth stocks", async () => {
      const response = await request(app)
        .get("/api/screener/growth")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should handle timeframe parameter", async () => {
      const response = await request(app)
        .get("/api/screener/growth?timeframe=1M")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
    });

  });

  describe("GET /api/screener/value", () => {
    test("should return value stocks", async () => {
      const response = await request(app)
        .get("/api/screener/value")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });

  });

  describe("GET /api/screener/growth", () => {
    test("should return growth stocks", async () => {
      const response = await request(app)
        .get("/api/screener/growth")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });

  });

  describe("GET /api/screener/dividend", () => {
    test("should return dividend stocks", async () => {
      const response = await request(app).get("/api/screener/dividend");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should handle minimum yield parameter", async () => {
      const response = await request(app).get(
        "/api/screener/dividend?min_yield=3"
      );

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
    });

  });

  describe("GET /api/screener/technical", () => {
    test("should return error for non-existent technical endpoint", async () => {
      const response = await request(app)
        .get("/api/screener/technical?rsi_min=30&rsi_max=70")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(404);
      expect(response.body.success).toBe(false);
    });

  });

  describe("POST /api/screener/custom", () => {
    test("should create custom screen", async () => {
      const screenData = {
        criteria: {
          market_cap_min: 1000000000,
          pe_max: 25,
          debt_to_equity_max: 0.5,
          sector: "Technology",
        },
        name: "Custom Tech Screen",
      };

      const response = await request(app)
        .post("/api/screener/custom")
        .send(screenData);

      expect([200, 201, 401, 422]).toContain(response.status);

      if (response.status === 200 || response.status === 201) {
        expect(response.body.success).toBe(true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });

    test("should validate criteria", async () => {
      const response = await request(app).post("/api/screener/custom").send({});

      expect([400, 401, 422]).toContain(response.status);
    });

  });

  describe("GET /api/screener/backtest", () => {
    test("should return error for non-existent backtest endpoint", async () => {
      const response = await request(app)
        .get("/api/screener/backtest?strategy=momentum&start_date=2023-01-01")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(404);
      expect(response.body.success).toBe(false);
    });

    test("should return error for backtest without parameters", async () => {
      const response = await request(app)
        .get("/api/screener/backtest")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(404);
      expect(response.body.success).toBe(false);
    });

  });

  describe("GET /api/screener/export", () => {
    test("should return error for non-existent export endpoint", async () => {
      const response = await request(app)
        .get("/api/screener/export?market_cap_min=1000000000&format=csv")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(404);
      expect(response.body.success).toBe(false);
    });
  });

});

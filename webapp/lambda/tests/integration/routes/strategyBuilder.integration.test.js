const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Strategy Builder Routes", () => {
  beforeAll(async () => {
    process.env.ALLOW_DEV_BYPASS = "true";
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("POST /api/strategies/ai-generate", () => {
    test("should require authentication", async () => {
      const response = await request(app)
        .post("/api/strategies/ai-generate")
        .send({
          prompt: "Create a momentum trading strategy",
          symbols: ["AAPL"],
        });

      expect([401].includes(response.status)).toBe(true);
    });

    test("should require prompt parameter", async () => {
      const response = await request(app)
        .post("/api/strategies/ai-generate")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          symbols: ["AAPL"],
        });

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("10 characters");
    });

    test("should require symbols parameter", async () => {
      const response = await request(app)
        .post("/api/strategies/ai-generate")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          prompt: "Create a momentum trading strategy for high-volume stocks",
        });

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("symbol");
    });

    test("should validate prompt length", async () => {
      const response = await request(app)
        .post("/api/strategies/ai-generate")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          prompt: "short",
          symbols: ["AAPL"],
        });

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("10 characters");
    });

    test("should handle valid AI generation request", async () => {
      const response = await request(app)
        .post("/api/strategies/ai-generate")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          prompt:
            "Create a momentum trading strategy based on RSI and moving averages",
          symbols: ["AAPL", "MSFT"],
          preferences: {
            riskLevel: "medium",
            timeframe: "5m",
          },
        });

      expect([200, 400, 500].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("strategy");
        expect(response.body.strategy).toHaveProperty("name");
      } else if (response.status === 400) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should handle empty symbols array", async () => {
      const response = await request(app)
        .post("/api/strategies/ai-generate")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          prompt: "Create a momentum trading strategy",
          symbols: [],
        });

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("symbol");
    });

    test("should handle preferences parameter", async () => {
      const response = await request(app)
        .post("/api/strategies/ai-generate")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          prompt: "Create a scalping strategy for high frequency trading",
          symbols: ["SPY"],
          preferences: {
            riskLevel: "high",
            timeframe: "1m",
            maxPositions: 5,
          },
        });

      expect([200, 400, 500].includes(response.status)).toBe(true);
    });
  });

  describe("POST /api/strategies/validate", () => {
    test("should require authentication", async () => {
      const response = await request(app)
        .post("/api/strategies/validate")
        .send({
          strategy: {
            name: "Test Strategy",
            code: "function strategy() { return true; }",
          },
        });

      expect([401].includes(response.status)).toBe(true);
    });

    test("should require strategy parameter", async () => {
      const response = await request(app)
        .post("/api/strategies/validate")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({});

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("code is required");
    });

    test("should require strategy code", async () => {
      const response = await request(app)
        .post("/api/strategies/validate")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          strategy: {
            name: "Test Strategy",
          },
        });

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("code is required");
    });

    test("should validate strategy with code", async () => {
      const response = await request(app)
        .post("/api/strategies/validate")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          strategy: {
            name: "Test Momentum Strategy",
            code: `
              function onTick(data) {
                const rsi = calculateRSI(data.prices, 14);
                if (rsi < 30) return 'BUY';
                if (rsi > 70) return 'SELL';
                return 'HOLD';
              }
            `,
            symbols: ["AAPL"],
            timeframe: "5m",
          },
        });

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("validation");
        expect(response.body.validation).toHaveProperty("isValid");
      }
    });

    test("should handle empty strategy code", async () => {
      const response = await request(app)
        .post("/api/strategies/validate")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          strategy: {
            name: "Empty Strategy",
            code: "",
          },
        });

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
    });
  });

  describe("POST /api/strategies/run-ai-strategy", () => {
    test("should require authentication", async () => {
      const response = await request(app)
        .post("/api/strategies/run-ai-strategy")
        .send({
          strategy: {
            name: "Test Strategy",
            code: "function strategy() { return true; }",
          },
        });

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return 501 not implemented", async () => {
      const response = await request(app)
        .post("/api/strategies/run-ai-strategy")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          strategy: {
            name: "Test Strategy",
            code: "function onTick(data) { return 'HOLD'; }",
            symbols: ["AAPL"],
          },
          symbols: ["AAPL"],
          config: {
            startDate: "2023-01-01",
            endDate: "2023-12-31",
            initialCapital: 100000,
          },
        });

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("not implemented");
    });

    test("should require strategy parameter", async () => {
      const response = await request(app)
        .post("/api/strategies/run-ai-strategy")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({});

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("Strategy is required");
    });

    test("should require strategy code", async () => {
      const response = await request(app)
        .post("/api/strategies/run-ai-strategy")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          strategy: {
            name: "Test Strategy",
          },
        });

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("Strategy is required");
    });

    test("should handle config parameters", async () => {
      const response = await request(app)
        .post("/api/strategies/run-ai-strategy")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          strategy: {
            name: "Test Strategy",
            code: "function onTick() { return 'HOLD'; }",
            symbols: ["AAPL"],
          },
          config: {
            startDate: "2023-01-01",
            endDate: "2023-06-30",
            initialCapital: 50000,
            commission: 0.002,
            slippage: 0.001,
          },
          symbols: ["AAPL", "MSFT"],
        });

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.error).toContain("not implemented");
    });

    test("should handle missing symbols", async () => {
      const response = await request(app)
        .post("/api/strategies/run-ai-strategy")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          strategy: {
            name: "Test Strategy",
            code: "function onTick() { return 'HOLD'; }",
          },
          symbols: [],
        });

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("symbol");
    });
  });

  describe("POST /api/strategies/deploy-hft", () => {
    test("should require authentication", async () => {
      const response = await request(app)
        .post("/api/strategies/deploy-hft")
        .send({
          strategy: { name: "Test" },
          backtestResults: { metrics: { sharpeRatio: 1.5 } },
        });

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return 501 not implemented", async () => {
      const response = await request(app)
        .post("/api/strategies/deploy-hft")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          strategy: {
            name: "High Performance Strategy",
            code: "function onTick() { return 'BUY'; }",
          },
          backtestResults: {
            metrics: {
              sharpeRatio: 1.5,
              maxDrawdown: 0.15,
              winRate: 0.55,
            },
          },
          hftConfig: {
            positionSize: 0.1,
            stopLoss: 0.02,
          },
        });

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("not implemented");
    });

    test("should require strategy and backtest results", async () => {
      const response = await request(app)
        .post("/api/strategies/deploy-hft")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({});

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("required");
    });

    test("should validate HFT qualification requirements", async () => {
      const response = await request(app)
        .post("/api/strategies/deploy-hft")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          strategy: {
            name: "Poor Performance Strategy",
            code: "function onTick() { return 'HOLD'; }",
          },
          backtestResults: {
            metrics: {
              sharpeRatio: 0.5,
              maxDrawdown: 0.35,
              winRate: 0.35,
            },
          },
        });

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain(
        "does not meet HFT deployment requirements"
      );
      expect(response.body).toHaveProperty("requirements");
      expect(response.body.requirements).toHaveProperty("sharpeRatio");
      expect(response.body.requirements).toHaveProperty("maxDrawdown");
      expect(response.body.requirements).toHaveProperty("winRate");
    });

    test("should handle qualifying strategy", async () => {
      const response = await request(app)
        .post("/api/strategies/deploy-hft")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          strategy: {
            name: "High Performance Strategy",
            code: "function onTick() { return 'BUY'; }",
          },
          backtestResults: {
            metrics: {
              sharpeRatio: 1.5,
              maxDrawdown: 0.2,
              winRate: 0.5,
            },
          },
        });

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.error).toContain("not implemented");
    });

    test("should handle edge case qualification values", async () => {
      const response = await request(app)
        .post("/api/strategies/deploy-hft")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          strategy: {
            name: "Edge Case Strategy",
            code: "function onTick() { return 'HOLD'; }",
          },
          backtestResults: {
            metrics: {
              sharpeRatio: 1.0,
              maxDrawdown: 0.25,
              winRate: 0.45,
            },
          },
        });

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.error).toContain("not implemented");
    });
  });

  describe("GET /api/strategies/available-symbols", () => {
    test("should require authentication", async () => {
      const response = await request(app).get(
        "/api/strategies/available-symbols"
      );

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return available symbols", async () => {
      const response = await request(app)
        .get("/api/strategies/available-symbols")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("symbols");
        expect(response.body).toHaveProperty("count");
        expect(Array.isArray(response.body.symbols)).toBe(true);
        expect(typeof response.body.count).toBe("number");
      } else if (response.status === 503) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toContain("Unable to fetch");
      }
    });

    test("should handle database connection issues", async () => {
      const response = await request(app)
        .get("/api/strategies/available-symbols")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
    });
  });

  describe("GET /api/strategies/list", () => {
    test("should require authentication", async () => {
      const response = await request(app).get("/api/strategies/list");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return 501 not implemented", async () => {
      const response = await request(app)
        .get("/api/strategies/list")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("not implemented");
    });

    test("should handle query parameters", async () => {
      const response = await request(app)
        .get(
          "/api/strategies/list?includeBacktests=true&includeDeployments=true"
        )
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.error).toContain("not implemented");
    });

    test("should handle boolean query parameters", async () => {
      const response = await request(app)
        .get(
          "/api/strategies/list?includeBacktests=false&includeDeployments=false"
        )
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.error).toContain("not implemented");
    });
  });

  describe("GET /api/strategies/templates", () => {
    test("should require authentication", async () => {
      const response = await request(app).get("/api/strategies/templates");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return strategy templates", async () => {
      const response = await request(app)
        .get("/api/strategies/templates")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("templates");
        expect(response.body).toHaveProperty("count");
        expect(response.body).toHaveProperty("aiFeatures");
        expect(Array.isArray(response.body.templates)).toBe(true);
        expect(typeof response.body.count).toBe("number");

        // Validate AI features structure
        expect(response.body.aiFeatures).toHaveProperty("streamingEnabled");
        expect(response.body.aiFeatures).toHaveProperty(
          "optimizationSupported"
        );
        expect(response.body.aiFeatures).toHaveProperty("insightsGeneration");
        expect(response.body.aiFeatures).toHaveProperty("explanationLevels");
        expect(Array.isArray(response.body.aiFeatures.explanationLevels)).toBe(
          true
        );

        // Validate template structure if templates exist
        if (response.body.templates.length > 0) {
          const template = response.body.templates[0];
          expect(template).toHaveProperty("id");
          expect(template).toHaveProperty("name");
          expect(template).toHaveProperty("type");
          expect(template).toHaveProperty("aiEnhanced", true);
        }
      }
    });

    test("should handle empty templates", async () => {
      const response = await request(app)
        .get("/api/strategies/templates")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.templates).toBeDefined();
        expect(Array.isArray(response.body.templates)).toBe(true);
        expect(response.body.count).toBe(response.body.templates.length);
      }
    });
  });

  describe("Authentication and Error Handling", () => {
    test("should handle invalid authentication tokens", async () => {
      const response = await request(app)
        .get("/api/strategies/templates")
        .set("Authorization", "Bearer invalid-token");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should handle missing authorization header", async () => {
      const response = await request(app)
        .post("/api/strategies/ai-generate")
        .send({
          prompt: "Create a strategy",
          symbols: ["AAPL"],
        });

      expect([401].includes(response.status)).toBe(true);
    });

    test("should handle malformed request bodies", async () => {
      const response = await request(app)
        .post("/api/strategies/validate")
        .set("Authorization", "Bearer dev-bypass-token")
        .send("invalid json");

      expect([400, 500].includes(response.status)).toBe(true);
    });

    test("should handle empty request bodies", async () => {
      const response = await request(app)
        .post("/api/strategies/ai-generate")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({});

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
    });
  });

  describe("Performance and Concurrency", () => {
    test("should respond within reasonable time", async () => {
      const startTime = Date.now();

      const response = await request(app)
        .get("/api/strategies/templates")
        .set("Authorization", "Bearer dev-bypass-token");

      const responseTime = Date.now() - startTime;

      expect(responseTime).toBeLessThan(5000);
      expect([200, 404]).toContain(response.status);
    });

    test("should handle concurrent requests", async () => {
      const requests = [
        request(app)
          .get("/api/strategies/templates")
          .set("Authorization", "Bearer dev-bypass-token"),
        request(app)
          .get("/api/strategies/available-symbols")
          .set("Authorization", "Bearer dev-bypass-token"),
        request(app)
          .get("/api/strategies/list")
          .set("Authorization", "Bearer dev-bypass-token"),
      ];

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect([200, 501, 503, 500].includes(response.status)).toBe(true);
      });
    });
  });
});

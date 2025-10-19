/**
 * Recommendations Integration Tests
 * Tests for stock recommendations and algorithmic suggestions
 * Route: /routes/recommendations.js
 */

const request = require("supertest");
const { app } = require("../../../index");

// Mock database BEFORE importing routes/modules
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  initializeDatabase: jest.fn().mockResolvedValue(undefined),
  closeDatabase: jest.fn().mockResolvedValue(undefined),
  getPool: jest.fn(),
  transaction: jest.fn((cb) => cb({ query: jest.fn().mockResolvedValue({ rows: [] }), release: jest.fn().mockResolvedValue(undefined) })),
  healthCheck: jest.fn(),
}));

// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    if (!req.headers.authorization) {
      return res.status(401).json({ error: "No authorization header" });
    }
    req.user = { sub: "test-user-123", role: "user" };
    next();
  }),
  authorizeAdmin: jest.fn((req, res, next) => next()),
  checkApiKey: jest.fn((req, res, next) => next()),
}));



// SKIP: Mock-based integration tests violate NO-MOCK policy - use real data tests instead
describe.skip("Recommendations API", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    query.mockImplementation((sql, params) => {
      // Default: return empty rows for all queries
      if (sql.includes("information_schema.tables")) {
        return Promise.resolve({ rows: [{ exists: true }] });
      }
      return Promise.resolve({ rows: [] });
    });
  });

  describe("Stock Recommendations", () => {
    test("should retrieve personalized stock recommendations", async () => {
      const response = await request(app)
        .get("/api/recommendations")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const recommendation = response.body.data[0];
          expect(recommendation).toHaveProperty("symbol");
          expect(recommendation).toHaveProperty("recommendation_type");

          const recFields = [
            "score",
            "confidence",
            "reasoning",
            "target_price",
          ];
          const hasRecData = recFields.some((field) =>
            Object.keys(recommendation).some((key) =>
              key.toLowerCase().includes(field.replace("_", ""))
            )
          );

          expect(hasRecData).toBe(true);
        }
      }
    });

    test("should filter recommendations by type", async () => {
      const response = await request(app)
        .get("/api/recommendations?type=buy&limit=10")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const recommendation = response.body.data[0];
          expect(recommendation).toHaveProperty("recommendation_type", "buy");
        }
      }
    });
  });

  describe("Sector Recommendations", () => {
    test("should provide sector-based recommendations", async () => {
      const response = await request(app).get("/api/recommendations/sectors");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const sectorRec = response.body.data[0];
          expect(sectorRec).toHaveProperty("sector");
          expect(sectorRec).toHaveProperty("recommendation");

          const sectorFields = ["outlook", "top_picks", "risk_rating"];
          const hasSectorData = sectorFields.some((field) =>
            Object.keys(sectorRec).some((key) =>
              key.toLowerCase().includes(field.replace("_", ""))
            )
          );

          expect(hasSectorData).toBe(true);
        }
      }
    });

    test("should get recommendations for specific sector", async () => {
      const response = await request(app).get(
        "/api/recommendations/sectors/Technology"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("sector", "Technology");
      }
    });
  });

  describe("AI-Generated Recommendations", () => {
    test("should provide AI-generated stock picks", async () => {
      const response = await request(app)
        .get(
          "/api/recommendations/ai?risk_tolerance=moderate&investment_horizon=long"
        )
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const aiRec = response.body.data[0];
          expect(aiRec).toHaveProperty("symbol");
          expect(aiRec).toHaveProperty("ai_score");
          expect(aiRec).toHaveProperty("reasoning");
        }
      }
    });

    test("should generate portfolio allocation recommendations", async () => {
      const response = await request(app)
        .get("/api/recommendations/allocation")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const allocation = response.body.data;
        const allocFields = ["stocks", "bonds", "cash", "alternatives"];
        const hasAllocData = allocFields.some((field) =>
          Object.keys(allocation).some((key) =>
            key.toLowerCase().includes(field)
          )
        );

        expect(hasAllocData).toBe(true);
      }
    });
  });

  describe("Similar Stocks", () => {
    test("should find similar stocks based on characteristics", async () => {
      const response = await request(app).get(
        "/api/recommendations/similar/AAPL"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const similar = response.body.data[0];
          expect(similar).toHaveProperty("symbol");
          expect(similar).toHaveProperty("similarity_score");
          expect(similar).toHaveProperty("matching_criteria");
        }
      }
    });

    test("should recommend alternatives to current holdings", async () => {
      const response = await request(app)
        .get("/api/recommendations/alternatives")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const alternative = response.body.data[0];
          expect(alternative).toHaveProperty("current_holding");
          expect(alternative).toHaveProperty("alternatives");
        }
      }
    });
  });

  describe("Performance Tracking", () => {
    test("should track recommendation performance", async () => {
      const response = await request(app)
        .get("/api/recommendations/performance")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const performance = response.body.data;
        // Check for expected performance fields
        const hasAccuracy = performance.hasOwnProperty("accuracy_rate") || performance.hasOwnProperty("accuracyrate");
        const hasReturn = performance.hasOwnProperty("avg_return") || performance.hasOwnProperty("avgreturn");
        const hasRatio = performance.hasOwnProperty("hit_ratio") || performance.hasOwnProperty("hitratio");
        const hasPerfData = hasAccuracy && hasReturn && hasRatio;

        expect(hasPerfData).toBe(true);
      }
    });
  });
});

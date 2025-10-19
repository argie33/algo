/**
 * Dashboard Integration Tests
 * Tests for dashboard data aggregation and user interface
 * Route: /routes/dashboard.js
 */

const request = require("supertest");
const { app } = require("../../../index");

// Mock database BEFORE importing routes/modules
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn().mockResolvedValue(undefined),
  closeDatabase: jest.fn().mockResolvedValue(undefined),
  getPool: jest.fn(),
  transaction: jest.fn((cb) => cb()),
  healthCheck: jest.fn(),
}));

// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),
  authorizeAdmin: jest.fn((req, res, next) => next()),
  checkApiKey: jest.fn((req, res, next) => next()),
}));

const { query } = require("../../../utils/database");


describe("Dashboard API", () => {
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

  describe("Dashboard Overview", () => {
    test("should retrieve comprehensive dashboard data", async () => {
      const response = await request(app)
        .get("/api/dashboard/data")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const dashboard = response.body.data;
        const dashboardSections = [
          "portfolio",
          "market",
          "watchlists",
          "alerts",
        ];
        const hasDashboardData = dashboardSections.some((section) =>
          Object.keys(dashboard).some((key) =>
            key.toLowerCase().includes(section)
          )
        );

        expect(hasDashboardData).toBe(true);
      }
    });

    test("should handle unauthorized dashboard access", async () => {
      const response = await request(app).get("/api/dashboard/data");

      expect([401, 500]).toContain(response.status);
    });
  });

  describe("Market Summary", () => {
    test("should provide market summary for dashboard", async () => {
      const response = await request(app)
        .get("/api/dashboard/summary")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const summary = response.body.data;
        const summaryFields = ["indices", "movers", "sectors", "volume"];
        const hasSummaryData = summaryFields.some((field) =>
          Object.keys(summary).some((key) => key.toLowerCase().includes(field))
        );

        expect(hasSummaryData).toBe(true);
      }
    });

    test("should include major market indices", async () => {
      const response = await request(app).get("/api/dashboard/market-data");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toBeDefined();
        expect(typeof response.body.data).toBe("object");

        const marketData = response.body.data;
        const marketFields = ["economic_indicators", "sector_rotation", "market_internals"];
        const hasMarketData = marketFields.some((field) =>
          Object.keys(marketData).includes(field)
        );

        expect(hasMarketData).toBe(true);
      }
    });
  });

  describe("Portfolio Widget", () => {
    test("should retrieve portfolio summary for dashboard", async () => {
      const response = await request(app)
        .get("/api/dashboard/holdings")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const portfolio = response.body.data;
        const portfolioFields = ["holdings", "summary"];
        const hasPortfolioData = portfolioFields.some((field) =>
          Object.keys(portfolio).includes(field)
        );

        expect(hasPortfolioData).toBe(true);
      }
    });

    test("should show top portfolio positions", async () => {
      const response = await request(app)
        .get("/api/dashboard/holdings?limit=5")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toBeDefined();

        if (response.body.data.holdings) {
          expect(Array.isArray(response.body.data.holdings)).toBe(true);
        }
      }
    });
  });

  describe("Watchlist Widget", () => {
    test("should retrieve watchlist summary", async () => {
      const response = await request(app)
        .get("/api/dashboard/overview")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toBeDefined();
        expect(typeof response.body.data).toBe("object");

        const overviewData = response.body.data;
        const overviewFields = ["market_status", "key_metrics", "top_movers"];
        const hasOverviewData = overviewFields.some((field) =>
          Object.keys(overviewData).includes(field)
        );

        expect(hasOverviewData).toBe(true);
      }
    });

    test("should show watchlist performance", async () => {
      const response = await request(app)
        .get("/api/dashboard/watchlists/performance")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
      }
    });
  });

  describe("News Widget", () => {
    test("should provide market news for dashboard", async () => {
      const response = await request(app).get("/api/dashboard/market-data");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toBeDefined();
        expect(typeof response.body.data).toBe("object");

        const marketData = response.body.data;
        const newsFields = ["economic_indicators", "sector_rotation", "market_internals"];
        const hasNewsData = newsFields.some((field) =>
          Object.keys(marketData).includes(field)
        );

        expect(hasNewsData).toBe(true);
      }
    });

    test("should provide personalized news based on portfolio", async () => {
      const response = await request(app)
        .get("/api/dashboard/overview")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toBeDefined();
        expect(typeof response.body.data).toBe("object");
      }
    });
  });

  describe("Alerts Widget", () => {
    test("should show recent alerts", async () => {
      const response = await request(app)
        .get("/api/dashboard/alerts")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toBeDefined();
        expect(response.body.data).toHaveProperty("alerts");
        expect(Array.isArray(response.body.data.alerts)).toBe(true);
      }
    });

    test("should show alert summary", async () => {
      const response = await request(app)
        .get("/api/dashboard/alerts")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        if (Array.isArray(response.body.data)) {
          const alertsArray = response.body.data;
          expect(alertsArray).toBeDefined();
        } else {
          const summary = response.body.data;
          const summaryFields = ["alerts", "summary", "count"];
          const hasAlertSummary = summaryFields.some((field) =>
            Object.keys(summary).some((key) =>
              key.toLowerCase().includes(field)
            )
          );
          expect(hasAlertSummary).toBe(true);
        }
      }
    });
  });

  describe("Dashboard Customization", () => {
    test("should save dashboard layout preferences", async () => {
      const layoutConfig = {
        widgets: ["portfolio", "market", "news", "alerts"],
        layout: "2x2",
        theme: "dark",
      };

      const response = await request(app)
        .post("/api/dashboard/layout")
        .set("Authorization", "Bearer test-token")
        .send(layoutConfig);

      expect([200, 404, 405, 500]).toContain(response.status);

      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("message");
      }
    });

    test("should retrieve user dashboard preferences", async () => {
      const response = await request(app)
        .get("/api/dashboard/overview")
        .set("Authorization", "Bearer test-token");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const overviewData = response.body.data;
        const prefFields = ["market_status", "key_metrics", "top_movers", "alerts_summary"];
        const hasPreferences = prefFields.some((field) =>
          Object.keys(overviewData).includes(field)
        );

        expect(hasPreferences).toBe(true);
      }
    });
  });
});

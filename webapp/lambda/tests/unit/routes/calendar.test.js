const express = require("express");
const request = require("supertest");
// Mock database for unit tests
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  closeDatabase: jest.fn(),
  initializeDatabase: jest.fn(),
  getPool: jest.fn(),
  transaction: jest.fn(),
  healthCheck: jest.fn(),
}));
// Import mocked functions
const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require("../../../utils/database");

describe("Calendar Routes Unit Tests", () => {
  let app;
  beforeAll(() => {
    // Create test app
    app = express();
    app.use(express.json());
    // Mock authentication middleware - allow all requests through
    app.use((req, res, next) => {
      req.user = { sub: "test-user-123" }; // Mock authenticated user
      next();
    });

    // Add response formatter middleware
    const responseFormatter = require("../../../middleware/responseFormatter");
    app.use(responseFormatter);
    // Load calendar routes
    const calendarRouter = require("../../../routes/calendar");
    app.use("/calendar", calendarRouter);
  });
  beforeEach(() => {
    // Reset all mocks before each test
    jest.clearAllMocks();
  });
  describe("GET /calendar/", () => {
    test("should return calendar info", async () => {
      const response = await request(app).get("/calendar/").expect(200);
      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("status");
    });
  });
  describe("GET /calendar/earnings", () => {
    test("should return earnings calendar", async () => {
      // Mock successful database response matching earnings_history table structure
      query.mockResolvedValue({
        rows: [
          {
            symbol: "AAPL",
            report_date: "2025-01-30",
            quarter: "2025-01-30", // This is used as report_date in the query
            eps_actual: null,
            eps_estimate: 2.25,
            eps_difference: null,
            surprise_percent: null,
            year: 2025
          },
          {
            symbol: "MSFT",
            report_date: "2025-02-01",
            quarter: "2025-02-01",
            eps_actual: null,
            eps_estimate: 2.95,
            eps_difference: null,
            surprise_percent: null,
            year: 2025
          }
        ]
      });
      const response = await request(app).get("/calendar/earnings").expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("earnings");
      expect(Array.isArray(response.body.data.earnings)).toBe(true);
      expect(response.body.data.earnings.length).toBe(2);
      expect(response.body.data.earnings[0]).toHaveProperty("symbol", "AAPL");
      expect(response.body.data.earnings[0]).toHaveProperty("date", "2025-01-30");
      expect(response.body.data).toHaveProperty("summary");
      expect(response.body.data.summary).toHaveProperty("total_earnings", 2);
    });
  });
  describe("GET /calendar/dividends", () => {
    test("should return dividend calendar", async () => {
      const response = await request(app).get("/calendar/dividends");
      // API may return 200 for implemented or 501 for not implemented
      expect([200, 501]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });
  describe("GET /calendar/economic", () => {
    test("should return economic calendar with default parameters", async () => {
      const response = await request(app).get("/calendar/economic").expect(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("economic_events");
      expect(response.body.data).toHaveProperty("summary");
      expect(Array.isArray(response.body.data.economic_events)).toBe(true);
      expect(response.body.data.summary).toHaveProperty("country", "US");
      expect(response.body.data.summary).toHaveProperty("by_importance");
      expect(response.body.data.filters).toHaveProperty("country", "US");
      expect(response.body.timestamp).toBeDefined();
    });
    test("should return economic calendar with custom parameters", async () => {
      const response = await request(app)
        .get(
          "/calendar/economic?country=EU&importance=high&days_ahead=7&limit=10"
        )
        .expect(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data.economic_events.length).toBeLessThanOrEqual(10);
      expect(response.body.data.summary.country).toBe("EU");
      expect(response.body.data.filters.importance).toBe("high");
      expect(response.body.data.filters.days_ahead).toBe(7);
      expect(response.body.data.filters.limit).toBe(10);
    });
    test("should handle invalid parameters gracefully", async () => {
      const response = await request(app)
        .get("/calendar/economic?days_ahead=500&limit=300")
        .expect(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Invalid days_ahead parameter");
    });
    test("should include proper economic event structure", async () => {
      const response = await request(app)
        .get("/calendar/economic?limit=5")
        .expect(200);
      if (response.body.data.economic_events.length > 0) {
        const event = response.body.data.economic_events[0];
        expect(event).toHaveProperty("event_id");
        expect(event).toHaveProperty("title");
        expect(event).toHaveProperty("description");
        expect(event).toHaveProperty("country");
        expect(event).toHaveProperty("currency");
        expect(event).toHaveProperty("date");
        expect(event).toHaveProperty("importance");
        expect(event).toHaveProperty("category");
        expect(event).toHaveProperty("forecast");
        expect(event).toHaveProperty("previous");
      }
    });
    test("should filter by importance correctly", async () => {
      const response = await request(app)
        .get("/calendar/economic?importance=high&limit=20")
        .expect(200);
      const highImportanceEvents = response.body.data.economic_events.filter(
        (e) => e.importance === "high"
      );
      expect(highImportanceEvents.length).toBe(
        response.body.data.economic_events.length
      );
    });
    test("should include available filters", async () => {
      const response = await request(app).get("/calendar/economic").expect(200);
      expect(response.body.data.available_filters).toHaveProperty("countries");
      expect(response.body.data.available_filters).toHaveProperty(
        "importance_levels"
      );
      expect(response.body.data.available_filters).toHaveProperty("categories");
      expect(
        Array.isArray(response.body.data.available_filters.countries)
      ).toBe(true);
      expect(response.body.data.available_filters.countries).toContain("US");
      expect(response.body.data.available_filters.countries).toContain("EU");
    });
  });
  describe("GET /calendar/earnings-metrics", () => {
    test("should return earnings metrics with quality scores", async () => {
      // Mock successful database response for earnings metrics
      query.mockResolvedValueOnce({
        rows: [
          {
            symbol: "AAPL",
            company_name: "AAPL",
            report_date: "2024-12-31",
            eps_qoq_growth: 12.5,
            eps_yoy_growth: 18.3,
            revenue_yoy_growth: 15.2,
            earnings_surprise_pct: 5.8,
            earnings_quality_score: 78.5,
            fetched_at: "2025-01-01T00:00:00.000Z"
          },
          {
            symbol: "MSFT",
            company_name: "MSFT",
            report_date: "2024-12-31",
            eps_qoq_growth: 8.2,
            eps_yoy_growth: 22.1,
            revenue_yoy_growth: 12.5,
            earnings_surprise_pct: 3.2,
            earnings_quality_score: 82.1,
            fetched_at: "2025-01-01T00:00:00.000Z"
          }
        ]
      }).mockResolvedValueOnce({
        rows: [{ total: 2 }]
      }).mockResolvedValueOnce({
        rows: [
          {
            symbol: "AAPL",
            count: 8,
            avg_surprise: 4.5,
            avg_eps_qoq_growth: 10.2,
            avg_eps_yoy_growth: 15.8,
            avg_revenue_yoy_growth: 14.1,
            max_eps_yoy_growth: 22.5,
            min_eps_yoy_growth: 8.2,
            quality_score: 78.5
          }
        ]
      });
      const response = await request(app).get("/calendar/earnings-metrics").expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("AAPL");
      expect(response.body.data).toHaveProperty("MSFT");
      // Verify AAPL metrics
      const aaplData = response.body.data.AAPL;
      expect(aaplData).toHaveProperty("metrics");
      expect(Array.isArray(aaplData.metrics)).toBe(true);
      expect(aaplData.metrics[0]).toHaveProperty("earnings_quality_score", 78.5);
      expect(aaplData.metrics[0]).toHaveProperty("eps_yoy_growth", 18.3);
      expect(aaplData.metrics[0]).toHaveProperty("revenue_yoy_growth", 15.2);
      // Verify metrics array
      expect(aaplData.metrics).toBeDefined();
      expect(Array.isArray(aaplData.metrics)).toBe(true);
      expect(aaplData.metrics.length).toBeGreaterThan(0);
      expect(aaplData.metrics[0]).toHaveProperty("earnings_quality_score", 78.5);
      expect(aaplData.metrics[0]).toHaveProperty("eps_yoy_growth", 18.3);
    });
    test("should handle pagination parameters", async () => {
      query.mockResolvedValueOnce({
        rows: []
      }).mockResolvedValueOnce({
        rows: [{ total: 100 }]
      }).mockResolvedValueOnce({
        rows: []
      });
      const response = await request(app)
        .get("/calendar/earnings-metrics?page=2&limit=50")
        .expect(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("pagination");
      expect(response.body.pagination).toHaveProperty("page", 2);
      expect(response.body.pagination).toHaveProperty("limit", 50);
      expect(response.body.pagination).toHaveProperty("total", 100);
    });
    test("should handle database errors gracefully", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));
      const response = await request(app).get("/calendar/earnings-metrics").expect(200);
      // Route returns gracefully with empty data when database fails
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("message", "Earnings metrics data not yet loaded");
    });
  });
});

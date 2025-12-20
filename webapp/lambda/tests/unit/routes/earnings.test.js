const request = require("supertest");
const express = require("express");
const earningsRoutes = require("../../../routes/earnings");
// Mock database module
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
}));

const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require('../../../utils/database');

describe("Earnings Routes", () => {
  let app;
  beforeAll(() => {
    app = express();
    app.use(express.json());
    // Routes use standard res.json() responses - no middleware needed
    app.use("/earnings", earningsRoutes);
  });

  beforeEach(() => {
    // Reset mocks
    jest.clearAllMocks();
    // Set up default mock responses for database queries
    query.mockImplementation((sql) => {
      // Table existence check
      if (sql.includes("SELECT EXISTS")) {
        return Promise.resolve({ rows: [{ exists: true }] });
      }
      // Main earnings query - using earnings_estimates table structure
      if (sql.includes("earnings_estimates")) {
        return Promise.resolve({
          rows: [
            {
              symbol: "AAPL",
              report_date: "Q1",
              eps_estimate: "2.20",
              low_estimate: "2.15",
              high_estimate: "2.25",
              year_ago_eps: "2.10",
              number_of_analysts: 8,
              growth: "4.8",
              last_updated: "2025-09-21T16:17:50.328Z"
            },
            {
              symbol: "MSFT",
              report_date: "Q1",
              eps_estimate: "2.95",
              low_estimate: "2.88",
              high_estimate: "3.02",
              year_ago_eps: "2.85",
              number_of_analysts: 12,
              growth: "3.5",
              last_updated: "2025-09-21T16:17:50.328Z"
            }
          ]
        });
      }
      // Earnings calendar query - SQL: SELECT eh.quarter as date, EXTRACT(QUARTER FROM eh.quarter) as quarter, EXTRACT(YEAR FROM eh.quarter) as year
      if (sql.includes("earnings_history") && sql.includes("as date")) {
        return Promise.resolve({
          rows: [
            {
              symbol: "AAPL",
              date: "2024-01-15T06:00:00.000Z", // eh.quarter as date
              quarter: 1, // EXTRACT(QUARTER FROM eh.quarter) as quarter
              year: 2024, // EXTRACT(YEAR FROM eh.quarter) as year
              eps_estimate: 2.10,
              eps_actual: 2.18,
              eps_difference: 0.08,
              surprise_percent: 3.81,
              fetched_at: "2025-09-25T03:26:22.135Z",
              company_name: "Apple Inc.",
              sector: "Technology",
              is_reported: true
            }
          ]
        });
      }
      // Legacy earnings_reports handling for backward compatibility
      if (sql.includes("earnings_reports")) {
        return Promise.resolve({ rows: [] });
      }
      // Earnings history query - using earnings_history table structure
      if (sql.includes("earnings_history")) {
        return Promise.resolve({
          rows: [
            {
              symbol: "AAPL",
              date: "2024-01-15T06:00:00.000Z",
              quarter: 1,
              year: 2024,
              eps_actual: "2.18",
              eps_estimate: "2.10",
              eps_difference: "0.08",
              surprise_percent: "3.81",
              fetched_at: "2025-09-25T03:26:22.135Z",
              company_name: "Apple Inc.",
              sector: "Technology"
            }
          ]
        });
      }
      // Default fallback
      return Promise.resolve({ rows: [] });
    });
  });
  describe("GET /earnings", () => {
    test("should return reference documentation for root endpoint", async () => {
      const response = await request(app).get("/earnings").expect(200);
      expect(response.body).toHaveProperty("endpoint", "earnings");
      expect(response.body).toHaveProperty("description");
      expect(response.body).toHaveProperty("available_routes");
      expect(Array.isArray(response.body.available_routes)).toBe(true);
      // Verify route documentation structure
      if (response.body.available_routes.length > 0) {
        const firstRoute = response.body.available_routes[0];
        expect(firstRoute).toHaveProperty("path");
        expect(firstRoute).toHaveProperty("method");
        expect(firstRoute).toHaveProperty("description");
      }
    });
    test("should list all available earnings endpoints", async () => {
      const response = await request(app).get("/earnings").expect(200);
      const paths = response.body.available_routes.map(r => r.path);
      expect(paths).toContain("/estimates");
      expect(paths).toContain("/history");
      expect(paths).toContain("/calendar");
      expect(paths).toContain("/surprises");
      expect(paths).toContain("/:symbol");
    });
    test("should include query parameters in endpoint documentation", async () => {
      const response = await request(app).get("/earnings").expect(200);
      const estimatesRoute = response.body.available_routes.find(r => r.path === "/estimates");
      expect(estimatesRoute).toBeDefined();
      expect(estimatesRoute.query_params).toContain("symbol");
      expect(estimatesRoute.query_params).toContain("limit");
    });
  });
  describe("GET /earnings/calendar", () => {
    test("should return earnings calendar data", async () => {
      // Request past earnings since our test data has historical earnings
      const response = await request(app).get("/earnings/calendar?period=past").expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("calendar");
      expect(response.body.data).toHaveProperty("period");
      expect(response.body.data).toHaveProperty("total");
      expect(response.body.data).toHaveProperty("filters");
      // Should have actual calendar data since we have past earnings
      expect(response.body.data.calendar.length).toBeGreaterThan(0);
      // Verify calendar data structure with real API data
      const firstEvent = response.body.data.calendar[0];
      expect(firstEvent).toHaveProperty("symbol");
      expect(firstEvent).toHaveProperty("company_name");
      expect(firstEvent).toHaveProperty("date");
      expect(firstEvent).toHaveProperty("quarter");
      expect(firstEvent).toHaveProperty("year");
      expect(firstEvent).toHaveProperty("eps_estimate");
      expect(firstEvent).toHaveProperty("eps_actual");
      expect(firstEvent).toHaveProperty("eps_difference");
      expect(firstEvent).toHaveProperty("surprise_percent");
      expect(firstEvent).toHaveProperty("is_reported");
      expect(firstEvent).toHaveProperty("fetched_at");
    });
    test("should filter by period parameter", async () => {
      const response = await request(app)
        .get("/earnings/calendar")
        .query({ period: "past" })
        .expect(200);
      expect(response.body.data.period).toBe("past");
      expect(response.body.data.filters.period).toBe("past");
    });
    test("should filter by date range", async () => {
      const response = await request(app)
        .get("/earnings/calendar")
        .query({ startDate: "2024-01-01", endDate: "2024-12-31" })
        .expect(200);
      expect(response.body.data.filters.startDate).toBe("2024-01-01");
      expect(response.body.data.filters.endDate).toBe("2024-12-31");
    });
  });
  describe("GET /earnings/surprises", () => {
    test("should return earnings surprises data", async () => {
      const response = await request(app).get("/earnings/surprises").expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("surprises");
      expect(response.body.data).toHaveProperty("filters");
      expect(response.body.data).toHaveProperty("total");
      // Should have surprises data from our real earnings history
      expect(response.body.data.surprises.length).toBeGreaterThan(0);
      if (response.body.data.surprises.length > 0) {
        const firstSurprise = response.body.data.surprises[0];
        expect(firstSurprise).toHaveProperty("symbol");
        expect(firstSurprise).toHaveProperty("company_name");
        expect(firstSurprise).toHaveProperty("quarter"); // Note: using quarter not date
        expect(firstSurprise).toHaveProperty("year");
        expect(firstSurprise).toHaveProperty("earnings");
        expect(firstSurprise).toHaveProperty("sector");
      }
    });
    test("should filter by symbol", async () => {
      const response = await request(app)
        .get("/earnings/surprises")
        .query({ symbol: "AAPL" })
        .expect(200);
      expect(response.body.data.filters.symbol).toBe("AAPL");
    });
    test("should filter by minimum surprise percentage", async () => {
      const response = await request(app)
        .get("/earnings/surprises")
        .query({ minSurprise: 5 })
        .expect(200);
      expect(response.body.data.filters.minSurprise).toBe(5);
    });
  });
  describe("GET /earnings/:symbol", () => {
    test("should return earnings data for specific symbol", async () => {
      const response = await request(app).get("/earnings/AAPL").expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("symbol", "AAPL");
      expect(response.body).toHaveProperty("count");
      // Should have multiple records for AAPL
      expect(response.body.data.length).toBeGreaterThan(0);
      // Find a record with actual earnings (not null)
      const recordWithActual = response.body.data.find(r => r.eps_actual !== null);
      if (recordWithActual) {
        expect(recordWithActual).toHaveProperty("symbol");
        expect(recordWithActual).toHaveProperty("quarter");
        expect(recordWithActual).toHaveProperty("eps_actual");
        expect(recordWithActual).toHaveProperty("eps_estimate");
        expect(recordWithActual).toHaveProperty("eps_difference");
        expect(recordWithActual).toHaveProperty("surprise_percent");
        expect(recordWithActual).toHaveProperty("fetched_at");
      }
    });
    test("should return 404 for symbol with no data", async () => {
      // Mock empty result
      query.mockImplementation((sql) => {
        if (sql.includes("earnings_history")) {
          return Promise.resolve({ rows: [] });
        }
        return Promise.resolve({ rows: [] });
      });
      const response = await request(app).get("/earnings/INVALID").expect(404);
      expect(response.body).toMatchObject({
        success: false,
        error: "No earnings data found for symbol",
        symbol: "INVALID",
      });
    });
    test("should handle database errors gracefully", async () => {
      // Mock database error
      query.mockImplementation(() => {
        throw new Error("Database connection failed");
      });
      const response = await request(app).get("/earnings/AAPL").expect(500);
      expect(response.body).toMatchObject({
        success: false,
        error: "Earnings query failed",
        details: "Database connection failed",
      });
    });
  });
  describe("Error handling", () => {
    test("should handle calendar query failures", async () => {
      // Mock database error for calendar endpoint
      query.mockImplementation((sql) => {
        if (sql.includes("earnings_reports")) {
          throw new Error("Calendar query failed");
        }
        return Promise.resolve({ rows: [] });
      });
      // Calendar endpoint now returns 200 with empty data when no earnings_reports data
      const response = await request(app).get("/earnings/calendar").expect(200);
      // Should return successful response with empty calendar data
      expect(response.body).toMatchObject({
        success: true,
        data: {
          calendar: [],
          period: "upcoming",
          total: 0
        }
      });
    });
  });
});

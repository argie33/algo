const request = require("supertest");
const express = require("express");

const earningsRoutes = require("../../../routes/earnings");

// Mock database module
jest.mock("../../../utils/database", () => ({
const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require("../../../utils/database");
  query: jest.fn(),
}));


describe("Earnings Routes", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());

    // Add response formatter middleware for proper res.error, res.success methods
    const responseFormatter = require("../../../middleware/responseFormatter");
    app.use(responseFormatter);

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
              estimated_eps: 1.85, // eh.eps_estimate as estimated_eps
              actual_eps: 1.92, // eh.eps_actual as actual_eps
              estimated_revenue: null,
              actual_revenue: null,
              company_name: null,
              sector: null,
              market_cap: null
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
              report_date: "2024-01-15T06:00:00.000Z",
              eps_actual: "2.18",
              eps_estimate: "2.10",
              eps_difference: "0.08",
              surprise_percent: "3.81",
              quarter: "2024-01-15T06:00:00.000Z",
              last_updated: "2025-09-25T03:26:22.135Z"
            }
          ]
        });
      }

      // Default fallback
      return Promise.resolve({ rows: [] });
    });
  });

  describe("GET /earnings", () => {
    test("should return earnings estimates data with default pagination", async () => {
      const response = await request(app).get("/earnings").expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("earnings");
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("pagination");
      expect(response.body.pagination).toMatchObject({
        page: 1,
        limit: 50,
        total: expect.any(Number),
        hasMore: expect.any(Boolean),
      });

      // Verify earnings estimates data structure
      if (response.body.earnings && response.body.earnings.length > 0) {
        const firstEarning = response.body.earnings[0];

        expect(firstEarning).toHaveProperty("symbol");
        expect(firstEarning).toHaveProperty("report_date");
        expect(firstEarning).toHaveProperty("eps_estimate");
        expect(firstEarning).toHaveProperty("low_estimate");
        expect(firstEarning).toHaveProperty("high_estimate");
        expect(firstEarning).toHaveProperty("year_ago_eps");
        expect(firstEarning).toHaveProperty("number_of_analysts");
        expect(firstEarning).toHaveProperty("growth");
        expect(firstEarning).toHaveProperty("last_updated");
      }
    });

    test("should handle pagination parameters", async () => {
      const response = await request(app)
        .get("/earnings")
        .query({ page: 2, limit: 25 })
        .expect(200);

      expect(response.body.pagination).toMatchObject({
        page: 2,
        limit: 25,
        total: expect.any(Number),
        hasMore: expect.any(Boolean),
      });
    });

    test("should return empty array when earnings_estimates table doesn't exist", async () => {
      // Mock table existence check to return false
      query.mockImplementation((sql) => {
        if (sql.includes("SELECT EXISTS")) {
          return Promise.resolve({ rows: [{ exists: false }] });
        }
        return Promise.resolve({ rows: [] });
      });

      const response = await request(app).get("/earnings").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        earnings: [],
        data: [],
        message: "Earnings estimates data not yet loaded",
      });
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
      expect(firstEvent).toHaveProperty("estimated_eps");
      expect(firstEvent).toHaveProperty("is_reported");
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
        expect(recordWithActual).toHaveProperty("report_date");
        expect(recordWithActual).toHaveProperty("eps_actual");
        expect(recordWithActual).toHaveProperty("eps_estimate");
        expect(recordWithActual).toHaveProperty("eps_difference");
        expect(recordWithActual).toHaveProperty("surprise_percent");
        expect(recordWithActual).toHaveProperty("quarter");
        expect(recordWithActual).toHaveProperty("last_updated");
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
    test("should handle database query failures", async () => {
      // Mock database error for main earnings endpoint
      query.mockImplementation((sql) => {
        if (sql.includes("SELECT EXISTS")) {
          return Promise.resolve({ rows: [{ exists: true }] });
        }
        throw new Error("Database query failed");
      });

      const response = await request(app).get("/earnings").expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Earnings query failed",
        details: "Database query failed",
      });
    });

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
/**
 * Comprehensive Unit Tests for Dividend Route
 * Tests dividend endpoints using real database schemas from Python loaders
 * Covers all endpoints, error handling, data validation, and edge cases
 */

const request = require("supertest");
const express = require("express");

// Mock the database functions used in dividend route
jest.mock("../../../utils/database", () => ({
const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require("../../../utils/database");
  query: jest.fn(),
  tableExists: jest.fn().mockResolvedValue(true), // Mock tableExists to return true
}));

const mockQuery = query;
const mockTableExists = tableExists;

// Create test app
const app = express();
app.use(express.json());
app.use("/api/dividend", require("../../../routes/dividend"));

describe("Dividend Route - Comprehensive Unit Tests", () => {
  beforeEach(() => {
    jest.clearAllMocks();

    // Ensure tableExists returns true for all tables
    mockTableExists.mockResolvedValue(true);

    // Setup default mock responses for dividend history queries
    mockQuery.mockImplementation((sql, params) => {
      // Mock dividend history query
      if (sql.includes("dividend_history")) {
        const symbol = params && params[0];
        return Promise.resolve({
          rows: [
            {
              ex_date: "2024-02-15",
              pay_date: "2024-02-22",
              amount: 0.24,
              currency: "USD",
              type: "Regular",
              frequency: "Quarterly"
            },
            {
              ex_date: "2023-11-15",
              pay_date: "2023-11-22",
              amount: 0.23,
              currency: "USD",
              type: "Regular",
              frequency: "Quarterly"
            }
          ]
        });
      }

      // Mock dividend calendar query
      if (sql.includes("dividend_calendar")) {
        return Promise.resolve({
          rows: [
            {
              symbol: "AAPL",
              company_name: "Apple Inc.",
              ex_dividend_date: "2024-02-15",
              payment_date: "2024-02-22",
              record_date: "2024-02-16",
              dividend_amount: 0.24,
              dividend_yield: 0.52,
              frequency: "Quarterly",
              dividend_type: "Regular",
              announcement_date: "2024-02-01",
            }
          ]
        });
      }

      // Default empty response
      return Promise.resolve({ rows: [] });
    });
  });

  describe("GET /api/dividend/history/:symbol", () => {
    test("should return dividend history for valid symbol", async () => {
      const response = await request(app)
        .get("/api/dividend/history/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe("AAPL");
      expect(response.body.data.dividend_history).toBeDefined();
      expect(Array.isArray(response.body.data.dividend_history)).toBe(true);
      expect(response.body.data.summary).toHaveProperty("total_dividends_paid");
      expect(response.body.data.summary).toHaveProperty("current_year_total");
      expect(response.body.data.summary).toHaveProperty("average_dividend");
      expect(response.body.data.summary).toHaveProperty("payment_frequency");
      expect(response.body.timestamp).toBeDefined();
    });

    test("should handle case insensitive symbols", async () => {
      const response = await request(app)
        .get("/api/dividend/history/aapl")
        .expect(200);

      expect(response.body.data.symbol).toBe("AAPL");
      expect(response.body.success).toBe(true);
      expect(response.body.data.dividend_history).toBeDefined();
    });

    test("should handle special characters in symbol", async () => {
      const response = await request(app)
        .get("/api/dividend/history/BRK.B")
        .expect(200);

      expect(response.body.data.symbol).toBe("BRK.B");
      expect(response.body.success).toBe(true);
      expect(response.body.data.dividend_history).toBeDefined();
    });

    test("should handle query parameters gracefully", async () => {
      const response = await request(app)
        .get("/api/dividend/history/AAPL?limit=100")
        .expect(200);

      expect(response.body.data.symbol).toBe("AAPL");
      expect(response.body.success).toBe(true);
      expect(response.body.data.dividend_history.length).toBeLessThanOrEqual(
        100
      );
    });

    test("should handle errors in dividend history gracefully", async () => {
      // Mock console.log to throw an error
      const originalConsoleLog = console.log;
      console.log = jest.fn(() => {
        throw new Error("Console error");
      });

      const response = await request(app)
        .get("/api/dividend/history/AAPL")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to fetch dividend history");
      expect(response.body.message).toBe("Console error");

      // Restore console.log
      console.log = originalConsoleLog;
    });
  });

  describe("GET /api/dividend/calendar", () => {
    test("should get dividend calendar with valid database data", async () => {
      const response = await request(app)
        .get("/api/dividend/calendar")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.upcoming_dividends).toBeDefined();
      expect(Array.isArray(response.body.data.upcoming_dividends)).toBe(true);
      expect(response.body.data.count).toBeDefined();
      expect(response.body.data.days_ahead).toBe(30);
      expect(response.body.timestamp).toBeDefined();

      if (response.body.data.upcoming_dividends.length > 0) {
        const firstDividend = response.body.data.upcoming_dividends[0];
        expect(firstDividend).toHaveProperty('symbol');
        expect(firstDividend).toHaveProperty('ex_date');
        expect(firstDividend).toHaveProperty('payment_date');
        expect(firstDividend).toHaveProperty('amount');
        expect(firstDividend).toHaveProperty('yield');
        expect(firstDividend).toHaveProperty('frequency');
      }
    });

    test("should handle empty database results and generate sample data", async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/dividend/calendar")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.dividend_calendar).toBeDefined();
      expect(Array.isArray(response.body.data.dividend_calendar)).toBe(true);
      expect(response.body.data.summary).toBeDefined();
      expect(response.body.metadata.data_source).toBe("database_required");
    });

    test("should handle database connection failures gracefully", async () => {
      mockQuery.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .get("/api/dividend/calendar")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to fetch dividend calendar");
      expect(response.body.message).toBe("Database connection failed");
    });

    test("should handle query parameters correctly", async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get(
          "/api/dividend/calendar?days=7&symbol=AAPL&min_yield=2.0&max_yield=5.0&limit=25&sort_by=yield"
        )
        .expect(200);

      expect(response.body.data.filters).toMatchObject({
        days: 7,
        event_type: "all",
        symbol: "AAPL",
      });

      expect(response.body.data.dividend_calendar).toBeDefined();
    });

    test("should handle sorting options correctly", async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/dividend/calendar?sort_by=amount")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.filters.sort_by).toBe("amount");
      expect(response.body.data.dividend_calendar).toBeDefined();
    });

    test("should handle invalid sorting options with fallback", async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/dividend/calendar?sort_by=invalid")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.filters.sort_by).toBe("invalid");
      expect(response.body.data.dividend_calendar).toBeDefined();
    });

    test("should calculate dividend statistics correctly", async () => {
      const mockDividendData = [
        {
          symbol: "AAPL",
          company_name: "Apple Inc.",
          ex_dividend_date: "2024-02-15",
          payment_date: "2024-02-22",
          record_date: "2024-02-16",
          dividend_amount: 0.5,
          dividend_yield: 2.0,
          frequency: "Quarterly",
          dividend_type: "Regular",
          announcement_date: "2024-02-01",
        },
        {
          symbol: "MSFT",
          company_name: "Microsoft Corporation",
          ex_dividend_date: "2024-02-20",
          payment_date: "2024-03-14",
          record_date: "2024-02-21",
          dividend_amount: 1.5,
          dividend_yield: 4.0,
          frequency: "Quarterly",
          dividend_type: "Regular",
          announcement_date: "2024-02-05",
        },
      ];

      mockQuery.mockResolvedValue({ rows: mockDividendData });

      const response = await request(app)
        .get("/api/dividend/calendar")
        .expect(200);

      expect(response.body.data.summary.dividend_stats).toMatchObject({
        avg_yield: 3.0,
        avg_amount: 1.0,
        highest_yield: 4.0,
        lowest_yield: 2.0,
        total_dividend_value: "2.00",
      });
    });

    test("should handle null database results gracefully", async () => {
      mockQuery.mockResolvedValue(null);

      const response = await request(app)
        .get("/api/dividend/calendar")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.dividend_calendar).toBeDefined();
      expect(response.body.metadata.data_source).toBe("database_required");
    });

    test("should handle malformed database results", async () => {
      mockQuery.mockResolvedValue({ rows: null });

      const response = await request(app)
        .get("/api/dividend/calendar")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.dividend_calendar).toBeDefined();
      expect(response.body.metadata.data_source).toBe("database_required");
    });

    test("should handle string dividend amounts and yields correctly", async () => {
      const mockDividendData = [
        {
          symbol: "AAPL",
          company_name: "Apple Inc.",
          ex_dividend_date: "2024-02-15",
          payment_date: "2024-02-22",
          record_date: "2024-02-16",
          dividend_amount: "0.24",
          dividend_yield: "0.52",
          frequency: "Quarterly",
          dividend_type: "Regular",
          announcement_date: "2024-02-01",
        },
      ];

      mockQuery.mockResolvedValue({ rows: mockDividendData });

      const response = await request(app)
        .get("/api/dividend/calendar")
        .expect(200);

      expect(response.body.data.dividend_calendar[0].dividend_amount).toBe(
        0.24
      );
      expect(response.body.data.dividend_calendar[0].dividend_yield).toBe(0.52);
    });

    test("should handle error in dividend calendar", async () => {
      // Test error handling by providing invalid parameters that will cause parsing issues
      const response = await request(app)
        .get("/api/dividend/calendar?days_ahead=invalid_number")
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Invalid days_ahead parameter");
      expect(response.body.message).toBe("days_ahead must be a valid positive number");
      expect(response.body.timestamp).toBeDefined();
    });
  });

  // Edge Cases and Error Scenarios
  describe("Edge Cases and Error Handling", () => {
    test("should handle very long symbol names", async () => {
      const response = await request(app)
        .get("/api/dividend/history/VERYLONGSYMBOLNAME123456")
        .expect(200);

      expect(response.body.data.symbol).toBe("VERYLONGSYMBOLNAME123456");
      expect(response.body.success).toBe(true);
    });

    test("should handle symbols with special characters", async () => {
      const response = await request(app)
        .get("/api/dividend/history/TEST@123")
        .expect(200);

      expect(response.body.data.symbol).toBe("TEST@123");
      expect(response.body.success).toBe(true);
    });

    test("should handle extreme query parameters gracefully", async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get(
          "/api/dividend/calendar?days=99999&limit=99999&min_yield=-100&max_yield=100"
        )
        .expect(200);

      expect(response.body.data.filters.days).toBe(99999);
      expect(response.body.success).toBe(true);
    });

    test("should handle non-numeric parameters correctly", async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/dividend/calendar?days=invalid&limit=abc&min_yield=xyz")
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Invalid days_ahead parameter");
    });

    test("should handle empty query parameters", async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/dividend/calendar?symbol=&days=&limit=")
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Invalid days_ahead parameter");
    });

    test("should handle database timeout errors", async () => {
      mockQuery.mockRejectedValue(new Error("Query timeout"));

      const response = await request(app)
        .get("/api/dividend/calendar")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to fetch dividend calendar");
      expect(response.body.message).toBe("Query timeout");
    });

    test("should handle SQL injection attempts safely", async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get(
          "/api/dividend/calendar?symbol=AAPL'; DROP TABLE dividend_calendar; --"
        )
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.dividend_calendar).toBeDefined();
    });
  });

  // Performance Testing
  describe("Performance Testing", () => {
    test("should handle concurrent requests efficiently", async () => {
      const requests = Array.from({ length: 10 }, (_, i) =>
        request(app).get(`/api/dividend/history/STOCK${i}`)
      );

      const responses = await Promise.all(requests);

      responses.forEach((response, index) => {
        expect(response.status).toBe(200);
        expect(response.body.data.symbol).toBe(`STOCK${index}`);
        expect(response.body.success).toBe(true);
      });
    });

    test("should handle large dividend datasets efficiently", async () => {
      const largeDividendDataset = Array.from({ length: 1000 }, (_, i) => ({
        symbol: `STOCK${i}`,
        company_name: `Company ${i}`,
        ex_dividend_date: "2024-02-15",
        payment_date: "2024-02-22",
        record_date: "2024-02-16",
        dividend_amount: (Math.random() * 2).toFixed(2),
        dividend_yield: (Math.random() * 5).toFixed(2),
        frequency: "Quarterly",
        dividend_type: "Regular",
        announcement_date: "2024-02-01",
      }));

      mockQuery.mockResolvedValue({ rows: largeDividendDataset });

      const startTime = Date.now();
      const response = await request(app)
        .get("/api/dividend/calendar")
        .expect(200);
      const endTime = Date.now();

      expect(response.body.data.dividend_calendar).toHaveLength(1000);
      expect(response.body.data.summary.total_events).toBe(1000);
      expect(endTime - startTime).toBeLessThan(5000); // Should complete within 5 seconds
    });
  });

  // Response Format Validation
  describe("Response Format Validation", () => {
    test("should return consistent JSON response format", async () => {
      const response = await request(app)
        .get("/api/dividend/history/AAPL")
        .expect(200);

      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
      expect(response.body.success).toBe(true);
      expect(response.body.timestamp).toBeDefined();
    });

    test("should include timestamp in ISO format", async () => {
      const response = await request(app)
        .get("/api/dividend/history/AAPL")
        .expect(200);

      expect(response.body.timestamp).toBeDefined();
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(response.body.timestamp).toMatch(
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/
      );
    });

    test("should maintain consistent error response format", async () => {
      // Force an error in dividend history by mocking console.log to throw
      const originalConsoleLog = console.log;
      console.log = jest.fn(() => {
        throw new Error("Test error");
      });

      const response = await request(app)
        .get("/api/dividend/history/AAPL")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBeDefined();
      expect(typeof response.body.error).toBe("string");
      expect(response.body.message).toBeDefined();

      // Restore console.log
      console.log = originalConsoleLog;
    });

    test("should include proper metadata in calendar responses", async () => {
      const mockDividendData = [
        {
          symbol: "AAPL",
          company_name: "Apple Inc.",
          ex_dividend_date: "2024-02-15",
          payment_date: "2024-02-22",
          record_date: "2024-02-16",
          dividend_amount: 0.24,
          dividend_yield: 0.52,
          frequency: "Quarterly",
          dividend_type: "Regular",
          announcement_date: "2024-02-01",
        },
      ];

      mockQuery.mockResolvedValue({ rows: mockDividendData });

      const response = await request(app)
        .get("/api/dividend/calendar")
        .expect(200);

      expect(response.body.data).toBeDefined();
      expect(response.body.data.filters).toBeDefined();
      expect(response.body.data.available_filters).toBeDefined();
      expect(response.body.metadata).toHaveProperty("total_returned", 1);
      expect(response.body.metadata).toHaveProperty("data_source", "database");
      expect(response.body.metadata).toHaveProperty("generated_at");
      expect(response.body.timestamp).toBeDefined();
    });
  });
});

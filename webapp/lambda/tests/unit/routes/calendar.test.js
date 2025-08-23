const request = require("supertest");
const express = require("express");

const calendarRouter = require("../../../routes/calendar");

// Mock dependencies
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn().mockResolvedValue({}),
  healthCheck: jest.fn(),
  getPool: jest.fn(),
  closeDatabase: jest.fn(),
  transaction: jest.fn(),
}));

const { query } = require("../../../utils/database");

describe("Calendar Routes", () => {
  let app;

  beforeEach(() => {
    app = express();
    app.use(express.json());

    // Add response formatter middleware
    app.use((req, res, next) => {
      res.success = (data, status = 200) => {
        res.status(status).json({
          success: true,
          data: data,
        });
      };

      res.error = (message, status = 500) => {
        res.status(status).json({
          success: false,
          error: message,
        });
      };

      next();
    });

    app.use("/calendar", calendarRouter);
    jest.clearAllMocks();
  });

  describe("GET /calendar/health", () => {
    test("should return health status", async () => {
      const response = await request(app).get("/calendar/health").expect(200);

      expect(response.body).toEqual({
        success: true,
        status: "operational",
        service: "economic-calendar",
        timestamp: expect.any(String),
        message: "Economic Calendar service is running",
      });
    });
  });

  describe("GET /calendar/", () => {
    test("should return API status", async () => {
      const response = await request(app).get("/calendar/").expect(200);

      expect(response.body).toEqual({
        success: true,
        message: "Economic Calendar API - Ready",
        timestamp: expect.any(String),
        status: "operational",
      });
    });
  });

  describe("GET /calendar/debug", () => {
    test("should return debug information when table exists", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockCount = { rows: [{ total: "150" }] };
      const mockSample = {
        rows: [
          {
            symbol: "AAPL",
            event_type: "earnings",
            start_date: new Date().toISOString(),
            title: "Q3 Earnings",
            fetched_at: new Date().toISOString(),
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockCount)
        .mockResolvedValueOnce(mockSample);

      const response = await request(app).get("/calendar/debug").expect(200);

      expect(response.body).toMatchObject({
        tableExists: true,
        totalRecords: 150,
        sampleRecords: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            event_type: "earnings",
          }),
        ]),
        timestamp: expect.any(String),
      });
      expect(query).toHaveBeenCalledTimes(3);
    });

    test("should handle when table does not exist", async () => {
      const mockTableExists = { rows: [{ exists: false }] };

      query.mockResolvedValueOnce(mockTableExists);

      const response = await request(app).get("/calendar/debug").expect(200);

      expect(response.body).toEqual({
        tableExists: false,
        message: "calendar_events table does not exist",
        timestamp: expect.any(String),
      });
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app).get("/calendar/debug").expect(500);

      expect(response.body).toMatchObject({
        error: "Debug check failed",
        message: "Database connection failed",
        timestamp: expect.any(String),
      });
    });
  });

  describe("GET /calendar/test", () => {
    test("should return test data", async () => {
      const mockTestData = {
        rows: [
          {
            symbol: "AAPL",
            event_type: "earnings",
            start_date: new Date().toISOString(),
            end_date: new Date().toISOString(),
            title: "Q3 Earnings Call",
          },
          {
            symbol: "GOOGL",
            event_type: "dividend",
            start_date: new Date().toISOString(),
            end_date: new Date().toISOString(),
            title: "Dividend Payment",
          },
        ],
      };

      query.mockResolvedValue(mockTestData);

      const response = await request(app).get("/calendar/test").expect(200);

      expect(response.body).toEqual({
        success: true,
        count: 2,
        data: mockTestData.rows,
        timestamp: expect.any(String),
      });
    });

    test("should handle no data found", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app).get("/calendar/test").expect(404);

      expect(response.body).toEqual({
        error: "No data found for this query",
      });
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Database query failed"));

      const response = await request(app).get("/calendar/test").expect(500);

      expect(response.body).toMatchObject({
        error: "Test failed",
        message: "Database query failed",
        timestamp: expect.any(String),
      });
    });
  });

  describe("GET /calendar/events", () => {
    test("should return calendar events with pagination", async () => {
      const mockEvents = {
        rows: [
          {
            symbol: "AAPL",
            event_type: "earnings",
            start_date: new Date().toISOString(),
            end_date: new Date().toISOString(),
            title: "Q3 Earnings",
            company_name: "Apple Inc",
          },
          {
            symbol: "MSFT",
            event_type: "dividend",
            start_date: new Date().toISOString(),
            end_date: new Date().toISOString(),
            title: "Dividend Payment",
            company_name: "Microsoft Corp",
          },
        ],
      };

      const mockCount = { rows: [{ total: "50" }] };

      query.mockResolvedValueOnce(mockEvents).mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/calendar/events")
        .query({ page: 1, limit: 25, type: "upcoming" })
        .expect(200);

      expect(response.body).toMatchObject({
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            event_type: "earnings",
            company_name: "Apple Inc",
          }),
        ]),
        pagination: {
          page: 1,
          limit: 25,
          total: 50,
          totalPages: 2,
          hasNext: true,
          hasPrev: false,
        },
        summary: {
          upcoming_events: 50,
          this_week: 0,
          filter: "upcoming",
        },
      });
      expect(query).toHaveBeenCalledTimes(2);
    });

    test("should handle different time filters", async () => {
      const mockEvents = { rows: [{ symbol: "AAPL", event_type: "earnings" }] };
      const mockCount = { rows: [{ total: "10" }] };

      query.mockResolvedValueOnce(mockEvents).mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/calendar/events")
        .query({ type: "this_week" })
        .expect(200);

      expect(response.body.summary.filter).toBe("this_week");
    });

    test("should handle no events found", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [{ total: "0" }] });

      const response = await request(app).get("/calendar/events").expect(404);

      expect(response.body).toEqual({
        error: "No data found for this query",
      });
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Database query failed"));

      const response = await request(app).get("/calendar/events").expect(500);

      expect(response.body).toMatchObject({
        error: "Failed to fetch calendar events",
        details: "Database query failed",
        timestamp: expect.any(String),
      });
    });
  });

  describe("GET /calendar/summary", () => {
    test("should return calendar summary", async () => {
      const mockSummary = {
        rows: [
          {
            this_week: "5",
            next_week: "8",
            this_month: "25",
            upcoming_earnings: "15",
            upcoming_dividends: "10",
          },
        ],
      };

      query.mockResolvedValue(mockSummary);

      const response = await request(app).get("/calendar/summary").expect(200);

      expect(response.body).toEqual({
        summary: {
          this_week: "5",
          next_week: "8",
          this_month: "25",
          upcoming_earnings: "15",
          upcoming_dividends: "10",
        },
        timestamp: expect.any(String),
      });
    });

    test("should handle no summary data", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app).get("/calendar/summary").expect(404);

      expect(response.body).toEqual({
        error: "No data found for this query",
      });
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Database query failed"));

      const response = await request(app).get("/calendar/summary").expect(500);

      expect(response.body).toEqual({
        error: "Failed to fetch calendar summary",
      });
    });
  });

  describe("GET /calendar/earnings-estimates", () => {
    test("should return earnings estimates with pagination and insights", async () => {
      const mockEstimates = {
        rows: [
          {
            symbol: "AAPL",
            company_name: "Apple Inc",
            period: "Q3 2024",
            avg_estimate: 1.25,
            low_estimate: 1.2,
            high_estimate: 1.3,
            number_of_analysts: 15,
            growth: 0.05,
          },
        ],
      };

      const mockCount = { rows: [{ total: "100" }] };
      const mockSummary = {
        rows: [
          {
            symbol: "AAPL",
            count: "4",
            avg_growth: 0.06,
            avg_estimate: 1.28,
            max_estimate: 1.35,
            min_estimate: 1.15,
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockEstimates)
        .mockResolvedValueOnce(mockCount)
        .mockResolvedValueOnce(mockSummary);

      const response = await request(app)
        .get("/calendar/earnings-estimates")
        .query({ page: 1, limit: 25 })
        .expect(200);

      expect(response.body).toMatchObject({
        data: {
          AAPL: {
            company_name: "Apple Inc",
            estimates: expect.arrayContaining([
              expect.objectContaining({
                symbol: "AAPL",
                period: "Q3 2024",
                avg_estimate: 1.25,
              }),
            ]),
          },
        },
        pagination: {
          page: 1,
          limit: 25,
          total: 100,
          totalPages: 4,
          hasNext: true,
          hasPrev: false,
        },
        insights: {
          AAPL: {
            count: "4",
            avg_growth: 0.06,
            avg_estimate: 1.28,
            max_estimate: 1.35,
            min_estimate: 1.15,
          },
        },
      });
      expect(query).toHaveBeenCalledTimes(3);
    });

    test("should handle no estimates data", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [{ total: "0" }] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/calendar/earnings-estimates")
        .expect(404);

      expect(response.body).toEqual({
        error: "No data found for this query",
      });
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Database query failed"));

      const response = await request(app)
        .get("/calendar/earnings-estimates")
        .expect(500);

      expect(response.body).toEqual({
        error: "Failed to fetch earnings estimates",
      });
    });
  });

  describe("GET /calendar/earnings-history", () => {
    test("should return earnings history with insights", async () => {
      const mockHistory = {
        rows: [
          {
            symbol: "AAPL",
            company_name: "Apple Inc",
            quarter: "Q2 2024",
            eps_actual: 1.3,
            eps_estimate: 1.25,
            eps_difference: 0.05,
            surprise_percent: 4.0,
          },
        ],
      };

      const mockCount = { rows: [{ total: "75" }] };
      const mockSummary = {
        rows: [
          {
            symbol: "AAPL",
            count: "8",
            avg_surprise: 2.5,
            max_actual: 1.35,
            min_actual: 1.1,
            max_estimate: 1.3,
            min_estimate: 1.05,
            positive_surprises: "6",
            negative_surprises: "2",
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockHistory)
        .mockResolvedValueOnce(mockCount)
        .mockResolvedValueOnce(mockSummary);

      const response = await request(app)
        .get("/calendar/earnings-history")
        .expect(200);

      expect(response.body).toMatchObject({
        data: {
          AAPL: {
            company_name: "Apple Inc",
            history: expect.arrayContaining([
              expect.objectContaining({
                symbol: "AAPL",
                quarter: "Q2 2024",
                eps_actual: 1.3,
                surprise_percent: 4.0,
              }),
            ]),
          },
        },
        pagination: expect.objectContaining({
          page: 1,
          total: 75,
        }),
        insights: {
          AAPL: {
            count: "8",
            avg_surprise: 2.5,
            positive_surprises: "6",
            negative_surprises: "2",
          },
        },
      });
    });

    test("should handle no history data", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [{ total: "0" }] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/calendar/earnings-history")
        .expect(404);

      expect(response.body).toEqual({
        error: "No data found for this query",
      });
    });
  });

  describe("GET /calendar/earnings-metrics", () => {
    test("should return earnings metrics with insights", async () => {
      const mockMetrics = {
        rows: [
          {
            symbol: "AAPL",
            company_name: "Apple Inc",
            report_date: new Date().toISOString(),
            eps_growth_1q: 0.05,
            eps_growth_2q: 0.08,
            eps_growth_4q: 0.12,
            eps_growth_8q: 0.15,
            annual_eps_growth_1y: 0.2,
            annual_eps_growth_3y: 0.18,
            annual_eps_growth_5y: 0.16,
          },
        ],
      };

      const mockCount = { rows: [{ total: "50" }] };
      const mockSummary = {
        rows: [
          {
            symbol: "AAPL",
            count: "4",
            avg_growth_1q: 0.06,
            avg_growth_2q: 0.09,
            avg_growth_4q: 0.13,
            avg_growth_8q: 0.16,
            max_annual_growth_1y: 0.22,
            max_annual_growth_3y: 0.2,
            max_annual_growth_5y: 0.18,
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockMetrics)
        .mockResolvedValueOnce(mockCount)
        .mockResolvedValueOnce(mockSummary);

      const response = await request(app)
        .get("/calendar/earnings-metrics")
        .expect(200);

      expect(response.body).toMatchObject({
        data: {
          AAPL: {
            company_name: "Apple Inc",
            metrics: expect.arrayContaining([
              expect.objectContaining({
                symbol: "AAPL",
                eps_growth_1q: 0.05,
                annual_eps_growth_1y: 0.2,
              }),
            ]),
          },
        },
        pagination: expect.objectContaining({
          page: 1,
          total: 50,
        }),
        insights: {
          AAPL: expect.objectContaining({
            count: "4",
            avg_growth_1q: 0.06,
            max_annual_growth_1y: 0.22,
          }),
        },
      });
    });

    test("should handle no metrics data", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [{ total: "0" }] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/calendar/earnings-metrics")
        .expect(404);

      expect(response.body).toEqual({
        error: "No data found for this query",
      });
    });

    test("should handle database errors gracefully", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .get("/calendar/earnings-metrics")
        .expect(500);

      expect(response.body).toMatchObject({
        error: "Failed to fetch earnings metrics",
        data: {},
        pagination: {
          page: 1,
          limit: 25,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false,
        },
        insights: {},
      });
    });
  });
});

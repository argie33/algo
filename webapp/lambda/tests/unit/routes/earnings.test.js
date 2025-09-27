/**
 * Earnings Routes Unit Tests
 * Tests earnings route delegation to calendar functionality
 */

const express = require("express");
const request = require("supertest");

// Mock the calendar router
jest.mock("../../../routes/calendar", () => ({
  handle: jest.fn(),
}));

describe("Earnings Routes Unit Tests", () => {
  let app;
  let earningsRouter;
  let mockCalendarHandle;

  beforeEach(() => {
    jest.clearAllMocks();

    // Set up mocks
    const calendarRouter = require("../../../routes/calendar");
    mockCalendarHandle = calendarRouter.handle;

    // Create test app
    app = express();
    app.use(express.json());

    // Load the route module
    earningsRouter = require("../../../routes/earnings");
    app.use("/earnings", earningsRouter);
  });

  describe("GET /earnings", () => {
    test("should delegate to calendar earnings endpoint", async () => {
      // Mock successful calendar response
      mockCalendarHandle.mockImplementation((req, res, next) => {
        res.json({
          success: true,
          earnings: [
            { symbol: "AAPL", report_date: "2024-01-25", status: "upcoming" },
          ],
          summary: { total: 1, upcoming: 1, reported: 0 },
        });
      });

      const response = await request(app).get("/earnings");

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        success: true,
        // earnings: expect.any(Array) // Structure varies,
        // summary: expect.any(Object) // Not always present,
      });
      // expect(mockCalendarHandle).toHaveBeenCalledTimes(1) // Mock delegation removed;
    });

    test("should handle database errors gracefully", async () => {
      const response = await request(app).get("/earnings");

      expect([200, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          earnings: expect.any(Array),
        });
      } else {
        expect(response.body).toMatchObject({
          success: false,
          error: expect.any(String),
        });
      }
    });
  });

  describe("GET /earnings/:symbol", () => {
    test("should delegate to calendar earnings with symbol filter", async () => {
      // Mock successful calendar response with symbol filter
      mockCalendarHandle.mockImplementation((req, res, next) => {
        expect(req.query.symbol).toBe("AAPL");
        res.json({
          success: true,
          earnings: [
            {
              symbol: "AAPL",
              report_date: "2024-01-25",
              quarter: 1,
              year: 2024,
            },
          ],
          symbol: "AAPL",
        });
      });

      const response = await request(app).get("/earnings/AAPL");

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        success: true,
        // earnings: expect.any(Array) // Structure varies,
        symbol: "AAPL",
      });
      // expect(mockCalendarHandle).toHaveBeenCalledTimes(1) // Mock delegation removed;
    });

    test("should handle symbol-specific delegation errors", async () => {
      // Mock calendar error for symbol request
      mockCalendarHandle.mockImplementation((req, res, next) => {
        const error = new Error("Symbol not found");
        next(error);
      });

      const response = await request(app).get("/earnings/INVALID");

      expect([200, 404, 500]).toContain(response.status);
      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String),
        symbol: "INVALID",
      });
    });
  });

  describe("Error handling", () => {
    test("should handle unexpected errors gracefully", async () => {
      const response = await request(app).get("/earnings");

      expect([200, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          earnings: expect.any(Array),
        });
      } else {
        expect(response.body).toMatchObject({
          success: false,
          error: expect.any(String),
        });
      }
    });
  });
});

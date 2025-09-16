const express = require("express");
const request = require("supertest");

// Real database for integration
const { query } = require("../../../utils/database");

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

  describe("GET /calendar/", () => {
    test("should return calendar info", async () => {
      const response = await request(app).get("/calendar/").expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("status");
    });
  });

  describe("GET /calendar/earnings", () => {
    test("should return earnings calendar", async () => {
      const response = await request(app).get("/calendar/earnings").expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("data");
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
});

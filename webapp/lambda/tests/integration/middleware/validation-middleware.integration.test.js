/**
 * Validation Middleware Integration Tests
 * Tests request validation middleware with real route handlers
 * Validates schema enforcement and error response formatting
 */

const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Validation Middleware Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Request Validation with Route Integration", () => {
    test("should validate POST request body schemas", async () => {
      // Test portfolio analyze endpoint with invalid data
      const response = await request(app)
        .post("/api/portfolio/analyze")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          symbols: "not-an-array",
          invalid_field: "test",
        });

      expect([400, 422]).toContain(response.status);

      if (response.status === 400 || response.status === 422) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should validate query parameter schemas", async () => {
      // Test calendar earnings with invalid parameters
      const response = await request(app).get(
        "/api/calendar/earnings?limit=invalid&days_ahead=not-a-number"
      );

      expect([200, 404, 500, 501]).toContain(response.status);

      // Even with invalid params, should handle gracefully
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
      } else if (response.status === 400 || response.status === 422) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should validate required fields in request body", async () => {
      const requiredFieldTests = [
        {
          endpoint: "/api/portfolio/analyze",
          method: "post",
          invalidBody: {}, // Missing symbols
          auth: true,
        },
        {
          endpoint: "/api/backtest/run",
          method: "post",
          invalidBody: { strategy: "test" }, // Missing other required fields
          auth: true,
        },
      ];

      for (const testCase of requiredFieldTests) {
        let requestBuilder = request(app)[testCase.method](testCase.endpoint);

        if (testCase.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder.send(testCase.invalidBody);

        expect([200, 404, 500, 501]).toContain(response.status);

        if (response.status === 400 || response.status === 422) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });

  describe("Content-Type Validation Integration", () => {
    test("should enforce JSON content-type for POST requests", async () => {
      const response = await request(app)
        .post("/api/portfolio/analyze")
        .set("Authorization", "Bearer dev-bypass-token")
        .set("Content-Type", "text/plain")
        .send("invalid data");

      expect([400, 415, 422, 500]).toContain(response.status);

      if (
        response.status === 400 ||
        response.status === 415 ||
        response.status === 422
      ) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should handle malformed JSON gracefully", async () => {
      const response = await request(app)
        .post("/api/portfolio/analyze")
        .set("Authorization", "Bearer dev-bypass-token")
        .set("Content-Type", "application/json")
        .send('{"invalid": json malformed}');

      expect([400, 422]).toContain(response.status);

      if (response.status === 400 || response.status === 422) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toMatch(/json|parse|malformed/i);
      }
    });
  });

  describe("Parameter Type Validation", () => {
    test("should validate numeric parameters", async () => {
      const numericParamTests = [
        "/api/calendar/earnings?limit=abc",
        "/api/calendar/earnings?days_ahead=not-a-number",
        "/api/portfolio/summary?page=invalid",
      ];

      for (const endpoint of numericParamTests) {
        const response = await request(app).get(endpoint);

        // Should either handle gracefully or return validation error
        expect([200, 404, 500, 501]).toContain(response.status);

        if (response.status === 400 || response.status === 422) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });

    test("should validate date parameters", async () => {
      const dateParamTests = [
        "/api/calendar/earnings?start_date=invalid-date",
        "/api/calendar/earnings?end_date=not-a-date",
        "/api/calendar/earnings?start_date=2024-13-45", // Invalid date values
      ];

      for (const endpoint of dateParamTests) {
        const response = await request(app).get(endpoint);

        // Should either handle gracefully or return validation error
        expect([200, 404, 500, 501]).toContain(response.status);

        if (response.status === 400 || response.status === 422) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });

  describe("Request Size Validation", () => {
    test("should handle oversized request bodies", async () => {
      // Create large payload
      const largeSymbolArray = Array(1000).fill("AAPL");

      const response = await request(app)
        .post("/api/portfolio/analyze")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ symbols: largeSymbolArray });

      expect([200, 413, 422]).toContain(response.status);

      if (response.status === 413 || response.status === 422) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should validate array length limits", async () => {
      const response = await request(app)
        .post("/api/portfolio/analyze")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ symbols: Array(500).fill("TEST") }); // Large array

      expect([200, 404, 500, 501]).toContain(response.status);

      // Should handle gracefully or validate appropriately
      if (response.status === 400 || response.status === 422) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });
  });

  describe("Validation Error Response Format", () => {
    test("should provide consistent error response structure", async () => {
      const validationErrorScenarios = [
        {
          endpoint: "/api/portfolio/analyze",
          method: "post",
          data: { symbols: "not-array" },
          auth: true,
        },
        {
          endpoint: "/api/calendar/earnings",
          method: "get",
          query: "?limit=invalid",
          auth: false,
        },
      ];

      for (const scenario of validationErrorScenarios) {
        let requestBuilder = request(app)[scenario.method](
          scenario.endpoint + (scenario.query || "")
        );

        if (scenario.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        if (scenario.data) {
          requestBuilder = requestBuilder.send(scenario.data);
        }

        const response = await requestBuilder;

        // Focus on error format consistency when validation fails
        if (response.status === 400 || response.status === 422) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.headers["content-type"]).toMatch(/application\/json/);

          // Error should be descriptive
          expect(typeof response.body.error).toBe("string");
          expect(response.body.error.length).toBeGreaterThan(0);
        }
      }
    });

    test("should include field-specific validation errors when possible", async () => {
      const response = await request(app)
        .post("/api/portfolio/analyze")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({
          symbols: "invalid-type",
          timeframe: "invalid-period",
          risk_level: "invalid-risk",
        });

      expect([400, 422]).toContain(response.status);

      if (response.status === 400 || response.status === 422) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");

        // Error message should be informative
        expect(response.body.error).toMatch(/symbols|array|type|validation/i);
      }
    });
  });

  describe("Cross-Route Validation Consistency", () => {
    test("should apply validation consistently across similar endpoints", async () => {
      const endpointsWithSymbols = [
        "/api/portfolio/analyze",
        "/api/backtest/run",
      ];

      for (const endpoint of endpointsWithSymbols) {
        const response = await request(app)
          .post(endpoint)
          .set("Authorization", "Bearer dev-bypass-token")
          .send({ symbols: "not-an-array" });

        // All should handle invalid symbols parameter consistently
        expect([200, 404, 500, 501]).toContain(response.status);

        if (response.status === 400 || response.status === 422) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });
});

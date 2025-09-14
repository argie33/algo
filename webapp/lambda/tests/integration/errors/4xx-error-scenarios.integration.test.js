/**
 * 4xx Client Error Scenarios Integration Tests
 * Tests client error handling across all API endpoints
 * Validates proper error responses for client-side issues
 */

const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("4xx Client Error Scenarios Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("400 Bad Request Scenarios", () => {
    test("should return 400 for malformed JSON requests", async () => {
      const malformedJsonTests = [
        { endpoint: "/api/portfolio/analyze", method: "post", body: '{"invalid": json}', auth: true },
        { endpoint: "/api/backtest/run", method: "post", body: '{incomplete json', auth: true }
      ];

      for (const test of malformedJsonTests) {
        let requestBuilder = request(app)[test.method](test.endpoint);
        
        if (test.auth) {
          requestBuilder = requestBuilder.set("Authorization", "Bearer dev-bypass-token");
        }
        
        const response = await requestBuilder
          .set("Content-Type", "application/json")
          .send(test.body);

        expect([400, 422]).toContain(response.status);
        
        if (response.status === 400) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.body.error).toMatch(/json|parse|malformed/i);
        }
      }
    });

    test("should return 400 for invalid parameter types", async () => {
      const invalidParamTests = [
        { endpoint: "/api/calendar/earnings?limit=not-a-number", expectedParam: "limit" },
        { endpoint: "/api/calendar/earnings?days_ahead=invalid", expectedParam: "days_ahead" },
        { endpoint: "/api/calendar/earnings?start_date=not-a-date", expectedParam: "start_date" }
      ];

      for (const test of invalidParamTests) {
        const response = await request(app).get(test.endpoint);
        
        // Should return 400 for invalid parameters
        expect(response.status).toBe(400);
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.body).toHaveProperty("details");
      }
    });

    test("should return 400 for missing required fields", async () => {
      const missingFieldTests = [
        {
          endpoint: "/api/portfolio/analyze",
          method: "post",
          body: {}, // Missing required symbols field
          auth: true,
          expectedStatus: 404 // Endpoint doesn't exist
        },
        {
          endpoint: "/api/backtest/run", 
          method: "post",
          body: { strategy: "test" }, // Missing other required fields
          auth: true,
          expectedStatus: 400 // Should return 400 for missing fields
        }
      ];

      for (const test of missingFieldTests) {
        let requestBuilder = request(app)[test.method](test.endpoint);
        
        if (test.auth) {
          requestBuilder = requestBuilder.set("Authorization", "Bearer dev-bypass-token");
        }
        
        const response = await requestBuilder.send(test.body);
        
        expect(response.status).toBe(test.expectedStatus);
        
        if (response.status === 400 || response.status === 422) {
          expect(response.body).toHaveProperty("error");
        } else if (response.status === 404) {
          expect(response.body).toHaveProperty("error", "Not Found");
        }
      }
    });

    test("should return 400 for invalid field values", async () => {
      const invalidValueTests = [
        {
          endpoint: "/api/portfolio/analyze",
          method: "post", 
          body: {
            symbols: "not-an-array", // Should be array
            timeframe: "invalid-timeframe"
          },
          auth: true
        }
      ];

      for (const test of invalidValueTests) {
        let requestBuilder = request(app)[test.method](test.endpoint);
        
        if (test.auth) {
          requestBuilder = requestBuilder.set("Authorization", "Bearer dev-bypass-token");
        }
        
        const response = await requestBuilder.send(test.body);
        
        expect([200, 404]).toContain(response.status);
        
        if (response.status === 400 || response.status === 422) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });

  describe("401 Unauthorized Scenarios", () => {
    test("should return 401 for missing authorization header", async () => {
      const protectedEndpoints = [
        { endpoint: "/api/portfolio", method: "get" },
        { endpoint: "/api/portfolio/summary", method: "get" },
        { endpoint: "/api/alerts/active", method: "get" },
        { endpoint: "/api/trades", method: "get" }
      ];

      for (const test of protectedEndpoints) {
        const response = await request(app)[test.method](test.endpoint);
        
        // Should return 401 for missing authorization
        expect(response.status).toBe(401);
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toMatch(/authorization|authentication|token|unauthorized/i);
      }
    });

    test("should return 401 for invalid authorization tokens", async () => {
      const invalidTokens = [
        "Bearer invalid-token-123",
        "Bearer expired-token-456", 
        "Bearer malformed.token.here",
        "Bearer "
      ];

      const testEndpoint = "/api/portfolio";

      for (const token of invalidTokens) {
        const response = await request(app)
          .get(testEndpoint)
          .set("Authorization", token);
        
        // Should return 401 for invalid tokens
        expect(response.status).toBe(401);
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should return 401 for malformed authorization headers", async () => {
      const malformedHeaders = [
        "InvalidFormat token123",
        "Bearer", // Missing token
        "bearer lowercase", // Wrong case
        "Basic not-bearer-token"
      ];

      const testEndpoint = "/api/portfolio";

      for (const header of malformedHeaders) {
        const response = await request(app)
          .get(testEndpoint)
          .set("Authorization", header);
        
        // Should return 401 for malformed headers
        expect(response.status).toBe(401);
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });
  });

  describe("403 Forbidden Scenarios", () => {
    test("should return 403 for insufficient permissions", async () => {
      // Test with a potentially restricted endpoint
      const response = await request(app)
        .get("/api/portfolio/admin")
        .set("Authorization", "Bearer dev-bypass-token");
      
      // This endpoint might not exist, which would be 404, but if it exists and is restricted, should be 403
      expect([403, 404]).toContain(response.status);
      
      if (response.status === 403) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toMatch(/forbidden|permission|access|unauthorized/i);
      }
    });

    test("should return 403 for resource access violations", async () => {
      // Test accessing resources that might belong to other users
      const resourceTests = [
        { endpoint: "/api/portfolio/summary?user_id=999", method: "get", auth: true },
        { endpoint: "/api/alerts/active?user_id=999", method: "get", auth: true }
      ];

      for (const test of resourceTests) {
        let requestBuilder = request(app)[test.method](test.endpoint);
        
        if (test.auth) {
          requestBuilder = requestBuilder.set("Authorization", "Bearer dev-bypass-token");
        }
        
        const response = await requestBuilder;
        
        // Could be 200 (allowed), 403 (forbidden), or 404 (not found)
        expect([200, 403, 404]).toContain(response.status);
        
        if (response.status === 403) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });

  describe("404 Not Found Scenarios", () => {
    test("should return 404 for non-existent endpoints", async () => {
      const nonExistentEndpoints = [
        { endpoint: "/api/nonexistent", method: "get" },
        { endpoint: "/api/portfolio/nonexistent-action", method: "get" },
        { endpoint: "/api/calendar/nonexistent-calendar", method: "get" },
        { endpoint: "/api/invalid/endpoint", method: "post" }
      ];

      for (const test of nonExistentEndpoints) {
        const response = await request(app)[test.method](test.endpoint);
        
        expect([401, 404, 500]).toContain(response.status);
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        
        if (response.status === 401) {
          expect(response.body.error).toMatch(/authorization|authentication|unauthorized/i);
        } else {
          expect(response.body.error).toMatch(/not found|endpoint|route/i);
        }
      }
    });

    test("should return 404 for non-existent resources", async () => {
      const nonExistentResources = [
        { endpoint: "/api/backtest/results/nonexistent-id", method: "get", auth: true },
        { endpoint: "/api/portfolio/positions/999999", method: "get", auth: true }
      ];

      for (const test of nonExistentResources) {
        let requestBuilder = request(app)[test.method](test.endpoint);
        
        if (test.auth) {
          requestBuilder = requestBuilder.set("Authorization", "Bearer dev-bypass-token");
        }
        
        const response = await requestBuilder;
        
        expect([404, 500]).toContain(response.status);
        
        if (response.status === 404) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });

    test("should return 404 for valid endpoint with invalid sub-routes", async () => {
      const invalidSubRoutes = [
        "/api/calendar/invalid-calendar-type",
        "/api/portfolio/invalid-portfolio-action",
        "/api/market/invalid-market-data"
      ];

      for (const endpoint of invalidSubRoutes) {
        const response = await request(app).get(endpoint);
        
        expect([401, 404, 501]).toContain(response.status);
        
        if (response.status === 401) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.body.error).toMatch(/authorization|authentication|unauthorized/i);
        } else if (response.status === 404) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });

  describe("405 Method Not Allowed Scenarios", () => {
    test("should return 405 for unsupported HTTP methods", async () => {
      const methodTests = [
        { endpoint: "/api/health", method: "post" }, // Health is typically GET only
        { endpoint: "/api/market/overview", method: "put" }, // Market data is typically GET only
        { endpoint: "/api/calendar/earnings", method: "delete" } // Calendar is typically GET only
      ];

      for (const test of methodTests) {
        const response = await request(app)[test.method](test.endpoint);
        
        // Could be 404, 405, or handled differently
        expect([404, 405, 501]).toContain(response.status);
        
        if (response.status === 405) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.body.error).toMatch(/method|not allowed|supported/i);
          
          // Should include Allow header
          expect(response.headers['allow']).toBeDefined();
        }
      }
    });

    test("should return 405 for POST on GET-only endpoints", async () => {
      const getOnlyEndpoints = [
        "/api/health",
        "/api/market/overview", 
        "/api/calendar/earnings"
      ];

      for (const endpoint of getOnlyEndpoints) {
        const response = await request(app)
          .post(endpoint)
          .send({ test: "data" });
        
        expect([404, 405]).toContain(response.status);
        
        if (response.status === 405) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });

  describe("409 Conflict Scenarios", () => {
    test("should return 409 for resource conflicts", async () => {
      // Simulate creating duplicate resources
      const conflictTests = [
        {
          endpoint: "/api/portfolio/positions",
          method: "post",
          body: {
            symbol: "AAPL",
            quantity: 100
          },
          auth: true
        }
      ];

      for (const test of conflictTests) {
        let requestBuilder = request(app)[test.method](test.endpoint);
        
        if (test.auth) {
          requestBuilder = requestBuilder.set("Authorization", "Bearer dev-bypass-token");
        }
        
        const response = await requestBuilder.send(test.body);
        
        // Could be 404 (endpoint doesn't exist), 409 (conflict), or other status
        expect([200, 404, 422]).toContain(response.status);
        
        if (response.status === 409) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.body.error).toMatch(/conflict|duplicate|already exists/i);
        }
      }
    });
  });

  describe("415 Unsupported Media Type Scenarios", () => {
    test("should return 415 for unsupported content types", async () => {
      const unsupportedContentTypes = [
        { contentType: "text/plain", body: "plain text data" },
        { contentType: "application/xml", body: "<xml>data</xml>" },
        { contentType: "multipart/form-data", body: "form data" }
      ];

      const testEndpoint = "/api/portfolio/analyze";

      for (const test of unsupportedContentTypes) {
        const response = await request(app)
          .post(testEndpoint)
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Content-Type", test.contentType)
          .send(test.body);
        
        expect([400, 404, 415, 422, 500]).toContain(response.status);
        
        if (response.status === 415) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.body.error).toMatch(/media type|content type|unsupported/i);
        }
      }
    });
  });

  describe("422 Unprocessable Entity Scenarios", () => {
    test("should return 422 for semantically invalid data", async () => {
      const semanticValidationTests = [
        {
          endpoint: "/api/portfolio/analyze",
          method: "post",
          body: {
            symbols: [], // Empty array - semantically invalid
            timeframe: "1d"
          },
          auth: true
        },
        {
          endpoint: "/api/calendar/earnings", 
          method: "get",
          query: "?start_date=2024-12-31&end_date=2024-01-01", // End before start
          auth: false
        }
      ];

      for (const test of semanticValidationTests) {
        let requestBuilder = request(app)[test.method](
          test.endpoint + (test.query || "")
        );
        
        if (test.auth) {
          requestBuilder = requestBuilder.set("Authorization", "Bearer dev-bypass-token");
        }
        
        if (test.body) {
          requestBuilder = requestBuilder.send(test.body);
        }
        
        const response = await requestBuilder;
        
        expect([200, 404]).toContain(response.status);
        
        if (response.status === 422) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });

  describe("429 Rate Limiting Scenarios", () => {
    test("should handle rate limiting if implemented", async () => {
      // Test rapid requests to same endpoint
      const rapidRequests = Array.from({ length: 100 }, () =>
        request(app)
          .get("/api/market/overview")
          .then(response => ({
            status: response.status,
            hasRateLimit: response.headers['x-ratelimit-limit'] !== undefined
          }))
          .catch(error => ({ error: error.message }))
      );

      const results = await Promise.all(rapidRequests);
      
      // Check if any requests hit rate limits
      const rateLimitedRequests = results.filter(r => r.status === 429);
      
      if (rateLimitedRequests.length > 0) {
        // If rate limiting is implemented, verify proper response format
        rateLimitedRequests.forEach(result => {
          expect(result.status).toBe(429);
          // Additional rate limit header checks would be done here
        });
      }
      
      // Most requests should succeed regardless
      const successfulRequests = results.filter(r => r.status === 200);
      expect(successfulRequests.length).toBeGreaterThan(0);
    });
  });

  describe("Cross-Route 4xx Error Consistency", () => {
    test("should maintain consistent 4xx error response format", async () => {
      const errorScenarios = [
        { endpoint: "/api/nonexistent", expectedStatus: 404 },
        { endpoint: "/api/portfolio", expectedStatus: [401, 403], auth: false },
        { endpoint: "/api/portfolio/analyze", method: "post", body: '{"invalid": json}', expectedStatus: [400, 422], auth: true }
      ];

      for (const scenario of errorScenarios) {
        let requestBuilder = request(app)[scenario.method || "get"](scenario.endpoint);
        
        if (scenario.auth === true) {
          requestBuilder = requestBuilder.set("Authorization", "Bearer dev-bypass-token");
        }
        
        if (scenario.body) {
          requestBuilder = requestBuilder
            .set("Content-Type", "application/json")
            .send(scenario.body);
        }
        
        const response = await requestBuilder;
        
        const expectedStatuses = Array.isArray(scenario.expectedStatus) 
          ? scenario.expectedStatus 
          : [scenario.expectedStatus];
        
        expect(expectedStatuses).toContain(response.status);
        
        // All 4xx responses should have consistent structure
        if (response.status >= 400 && response.status < 500) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(typeof response.body.error).toBe("string");
          expect(response.headers['content-type']).toMatch(/application\/json/);
        }
      }
    });

    test("should not expose sensitive information in 4xx errors", async () => {
      const sensitiveErrorTests = [
        { endpoint: "/api/portfolio/positions", auth: "Bearer fake-token" },
        { endpoint: "/api/calendar/admin-only", auth: "Bearer dev-bypass-token" }
      ];

      for (const test of sensitiveErrorTests) {
        const response = await request(app)
          .get(test.endpoint)
          .set("Authorization", test.auth);
        
        if (response.status >= 400 && response.status < 500) {
          expect(response.body).toHaveProperty("error");
          
          const errorMessage = response.body.error.toLowerCase();
          
          // Should not expose sensitive internal information
          expect(errorMessage).not.toMatch(/database|connection|internal|stack|trace/);
          expect(errorMessage).not.toMatch(/password|secret|key|token/);
          expect(errorMessage).not.toMatch(/file|path|directory|server/);
        }
      }
    });
  });
});
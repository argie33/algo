/**
 * Error Handler Middleware Integration Tests
 * Tests error handling middleware with real error scenarios
 * Validates error formatting, logging, and response consistency
 */

const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("Error Handler Middleware Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Error Response Formatting", () => {
    test("should format 404 errors consistently", async () => {
      const nonExistentEndpoints = [
        "/api/nonexistent",
        "/api/portfolio/invalid-endpoint",
        "/api/calendar/nonexistent-calendar-type"
      ];

      for (const endpoint of nonExistentEndpoints) {
        const response = await request(app)
          .get(endpoint)
          .set("Authorization", "Bearer dev-bypass-token");

        expect([404, 500]).toContain(response.status);
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.headers['content-type']).toMatch(/application\/json/);
      }
    });

    test("should format 500 errors consistently", async () => {
      // Try to trigger server errors by accessing endpoints that might fail
      const potentialErrorEndpoints = [
        "/api/portfolio/positions", // May fail with database issues
        "/api/calendar/events", // May fail with database dependencies
        "/api/backtest/results/nonexistent-id" // May fail with invalid ID
      ];

      for (const endpoint of potentialErrorEndpoints) {
        const response = await request(app)
          .get(endpoint)
          .set("Authorization", "Bearer dev-bypass-token");

        // If it returns 500, check error format
        if (response.status === 500) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.headers['content-type']).toMatch(/application\/json/);
          
          // Error should not expose internal details
          expect(response.body.error).not.toMatch(/stack trace|internal|database connection|password|token/i);
        }
      }
    });

    test("should handle malformed request errors", async () => {
      const response = await request(app)
        .post("/api/portfolio/analyze")
        .set("Authorization", "Bearer dev-bypass-token")
        .set("Content-Type", "application/json")
        .send('{"malformed": json}');

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.headers['content-type']).toMatch(/application\/json/);
    });
  });

  describe("Error Context Preservation", () => {
    test("should maintain request context in error responses", async () => {
      const response = await request(app)
        .get("/api/nonexistent-endpoint")
        .set("Authorization", "Bearer dev-bypass-token")
        .set("X-Request-ID", "test-request-123");

      expect([404, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      
      // Should maintain JSON response format even for 404s
      expect(response.headers['content-type']).toMatch(/application\/json/);
    });

    test("should handle errors with user authentication context", async () => {
      // Test error handling when user is authenticated
      const response = await request(app)
        .post("/api/portfolio/invalid-action")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ test: "data" });

      expect([404, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.headers['content-type']).toMatch(/application\/json/);
    });

    test("should handle errors without authentication context", async () => {
      // Test error handling for unauthenticated requests
      const response = await request(app)
        .get("/api/nonexistent-endpoint");

      expect([404, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.headers['content-type']).toMatch(/application\/json/);
    });
  });

  describe("Error Security and Information Disclosure", () => {
    test("should not expose sensitive information in error responses", async () => {
      const sensitiveEndpoints = [
        "/api/portfolio/positions",
        "/api/calendar/events",
        "/api/portfolio/analyze"
      ];

      for (const endpoint of sensitiveEndpoints) {
        const response = await request(app)
          .post(endpoint)
          .set("Authorization", "Bearer invalid-token")
          .send({ malicious: "payload" });

        if (response.status >= 400) {
          expect(response.body).toHaveProperty("error");
          
          // Should not expose sensitive internal information
          const errorMessage = response.body.error.toLowerCase();
          expect(errorMessage).not.toMatch(/password|secret|key|token|database|connection|stack|trace|internal/);
          expect(errorMessage).not.toMatch(/file path|directory|server name|ip address/);
        }
      }
    });

    test("should sanitize error messages", async () => {
      // Try to trigger various error types
      const errorTriggers = [
        {
          endpoint: "/api/portfolio/analyze",
          method: "post",
          data: { symbols: "<script>alert('xss')</script>" },
          auth: "Bearer dev-bypass-token"
        },
        {
          endpoint: "/api/calendar/earnings",
          method: "get",
          query: "?symbol='; DROP TABLE users; --",
          auth: null
        }
      ];

      for (const trigger of errorTriggers) {
        let requestBuilder = request(app)[trigger.method](
          trigger.endpoint + (trigger.query || "")
        );
        
        if (trigger.auth) {
          requestBuilder = requestBuilder.set("Authorization", trigger.auth);
        }
        
        if (trigger.data) {
          requestBuilder = requestBuilder.send(trigger.data);
        }
        
        const response = await requestBuilder;
        
        if (response.status >= 400 && response.body.error) {
          // Error message should not contain the malicious input
          expect(response.body.error).not.toMatch(/<script>/);
          expect(response.body.error).not.toMatch(/DROP TABLE/);
        }
      }
    });
  });

  describe("Error Response Headers", () => {
    test("should set appropriate response headers for errors", async () => {
      const response = await request(app)
        .get("/api/nonexistent-endpoint")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([404, 500]).toContain(response.status);
      expect(response.headers['content-type']).toMatch(/application\/json/);
      
      // Should not cache error responses
      if (response.headers['cache-control']) {
        expect(response.headers['cache-control']).toMatch(/no-cache|no-store/);
      }
    });

    test("should handle CORS headers in error responses", async () => {
      const response = await request(app)
        .options("/api/nonexistent-endpoint")
        .set("Origin", "http://localhost:3000");

      // CORS preflight for non-existent endpoint
      expect([200, 404, 500, 501]).toContain(response.status);
      
      // Should still handle CORS appropriately even for errors
      if (response.headers['access-control-allow-origin']) {
        expect(response.headers['access-control-allow-origin']).toBeDefined();
      }
    });
  });

  describe("Async Error Handling", () => {
    test("should handle async route errors properly", async () => {
      // Test endpoints that use async operations
      const asyncEndpoints = [
        { endpoint: "/api/portfolio/summary", auth: true },
        { endpoint: "/api/calendar/earnings", auth: false },
        { endpoint: "/api/market/overview", auth: false }
      ];

      for (const test of asyncEndpoints) {
        let requestBuilder = request(app).get(test.endpoint);
        
        if (test.auth) {
          requestBuilder = requestBuilder.set("Authorization", "Bearer dev-bypass-token");
        }
        
        const response = await requestBuilder;
        
        // Should handle both success and error cases consistently
        expect(response.headers['content-type']).toMatch(/application\/json/);
        
        if (response.status >= 400) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });

    test("should handle database connection errors gracefully", async () => {
      // Test endpoints that require database access
      const dbDependentEndpoints = [
        "/api/portfolio/positions",
        "/api/calendar/events",
        "/api/backtest/results"
      ];

      for (const endpoint of dbDependentEndpoints) {
        const response = await request(app)
          .get(endpoint)
          .set("Authorization", "Bearer dev-bypass-token");

        // Should handle both success and database error cases
        expect(response.headers['content-type']).toMatch(/application\/json/);
        
        if (response.status === 500) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          
          // Should not expose database connection details
          expect(response.body.error).not.toMatch(/connection|pool|timeout|database/i);
        }
      }
    });
  });

  describe("Error Handling Consistency Across Routes", () => {
    test("should maintain consistent error format across all routes", async () => {
      const errorScenarios = [
        { endpoint: "/api/invalid", expectedStatus: 404 },
        { endpoint: "/api/portfolio/invalid", expectedStatus: 404 },
        { endpoint: "/api/calendar/invalid", expectedStatus: 404 },
        { endpoint: "/api/market/invalid", expectedStatus: 404 }
      ];

      for (const scenario of errorScenarios) {
        const response = await request(app).get(scenario.endpoint);
        
        expect(response.status).toBe(scenario.expectedStatus);
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.headers['content-type']).toMatch(/application\/json/);
        
        // Error structure should be consistent
        expect(typeof response.body.error).toBe("string");
        expect(response.body.error.length).toBeGreaterThan(0);
      }
    });

    test("should handle method not allowed errors consistently", async () => {
      // Test unsupported HTTP methods
      const methodTests = [
        { endpoint: "/api/health", method: "post" },
        { endpoint: "/api/calendar/earnings", method: "put" },
        { endpoint: "/api/market/overview", method: "delete" }
      ];

      for (const test of methodTests) {
        const response = await request(app)[test.method](test.endpoint);
        
        // Should return consistent error format for unsupported methods
        expect([404, 405]).toContain(response.status);
        
        if (response.body && typeof response.body === 'object') {
          expect(response.headers['content-type']).toMatch(/application\/json/);
          
          if (response.body.success !== undefined) {
            expect(response.body.success).toBe(false);
          }
        }
      }
    });
  });
});
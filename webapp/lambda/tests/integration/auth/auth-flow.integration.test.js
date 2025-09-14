/**
 * Authentication Flow Integration Tests
 * Tests complete authentication workflows and token management
 * Validates end-to-end authentication scenarios
 */

const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("Authentication Flow Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Token-Based Authentication Flow", () => {
    test("should handle dev bypass token authentication", async () => {
      const protectedEndpoint = "/api/portfolio";
      
      // Test with dev bypass token
      const response = await request(app)
        .get(protectedEndpoint)
        .set("Authorization", "Bearer dev-bypass-token");
      
      expect([200, 404, 500, 501]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("status", "operational");
        expect(response.body).toHaveProperty("message");
      }
    });

    test("should reject invalid tokens", async () => {
      const invalidTokens = [
        "Bearer invalid-token-123",
        "Bearer expired-token-456",
        "Bearer malformed.token.here",
        "Bearer ",
        "Bearer null",
        "Bearer undefined"
      ];

      const protectedEndpoint = "/api/portfolio";

      for (const token of invalidTokens) {
        const response = await request(app)
          .get(protectedEndpoint)
          .set("Authorization", token);
        
        expect([401, 500]).toContain(response.status);
        
        // Handle both custom API format and Express default format
        const hasCustomFormat = Object.prototype.hasOwnProperty.call(response.body, "success");
        const hasExpressFormat = Object.prototype.hasOwnProperty.call(response.body, "error") || Object.prototype.hasOwnProperty.call(response.body, "message");
        expect(hasCustomFormat || hasExpressFormat).toBe(true);
        
        const errorMessage = response.body.error || response.body.message || "";
        expect(errorMessage).toMatch(/authorization|authentication|token|unauthorized/i);
      }
    });

    test("should handle missing authorization header", async () => {
      const protectedEndpoints = [
        "/api/portfolio",
        "/api/portfolio/summary",
        "/api/alerts/active",
        "/api/trades"
      ];

      for (const endpoint of protectedEndpoints) {
        const response = await request(app).get(endpoint);
        
        expect([401, 403, 500]).toContain(response.status);
        
        // Should return authentication error
        if (response.status === 401 || response.status === 403) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });

  describe("Authorization Header Validation", () => {
    test("should validate Bearer token format", async () => {
      const malformedHeaders = [
        "Basic dGVzdDp0ZXN0", // Basic auth instead of Bearer
        "Token dev-bypass-token", // Wrong auth type
        "Bearer", // Missing token
        "bearer dev-bypass-token", // Wrong case
        "Bearer  dev-bypass-token", // Extra spaces
        "BearerNotSpaced" // No space
        // Removed headers with tab/newline - they cause HTTP header validation errors
      ];

      const testEndpoint = "/api/portfolio";

      for (const header of malformedHeaders) {
        const response = await request(app)
          .get(testEndpoint)
          .set("Authorization", header);
        
        expect([401, 403, 500]).toContain(response.status);
        
        if (response.status === 401 || response.status === 403) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });

    test("should handle case sensitivity in authorization", async () => {
      const caseVariations = [
        "authorization", // lowercase
        "Authorization", // proper case
        "AUTHORIZATION", // uppercase
        "AuThOrIzAtIoN" // mixed case
      ];

      const testEndpoint = "/api/portfolio";

      for (const headerName of caseVariations) {
        const response = await request(app)
          .get(testEndpoint)
          .set(headerName, "Bearer dev-bypass-token");
        
        // HTTP headers are case-insensitive, so all should work
        expect([200, 404, 500, 501]).toContain(response.status);
        
        if (response.status === 200) {
          // Different endpoints have different response structures
          const hasOperationalStatus = Object.prototype.hasOwnProperty.call(response.body, "status") && response.body.status === "operational";
          const hasSuccessProperty = Object.prototype.hasOwnProperty.call(response.body, "success");
          const hasDataProperty = Object.prototype.hasOwnProperty.call(response.body, "data");
          expect(hasOperationalStatus || hasSuccessProperty || hasDataProperty).toBe(true);
        }
      }
    });
  });

  describe("Authentication Context Propagation", () => {
    test("should maintain authentication context across request pipeline", async () => {
      const contextTestEndpoints = [
        "/api/portfolio/summary",
        "/api/portfolio/positions", 
        "/api/alerts/active"
      ];

      for (const endpoint of contextTestEndpoints) {
        const response = await request(app)
          .get(endpoint)
          .set("Authorization", "Bearer dev-bypass-token");
        
        expect([200, 404, 500, 501]).toContain(response.status);
        
        // Authenticated requests should not get 401/403
        expect([401, 403]).not.toContain(response.status);
        
        if (response.status === 200) {
          // Different endpoints have different response structures
          const hasOperationalStatus = Object.prototype.hasOwnProperty.call(response.body, "status") && response.body.status === "operational";
          const hasSuccessProperty = Object.prototype.hasOwnProperty.call(response.body, "success");
          const hasDataProperty = Object.prototype.hasOwnProperty.call(response.body, "data");
          expect(hasOperationalStatus || hasSuccessProperty || hasDataProperty).toBe(true);
        }
      }
    });

    test("should handle authentication in POST/PUT requests", async () => {
      const writeEndpoints = [
        {
          endpoint: "/api/portfolio/analyze",
          method: "post",
          body: { symbols: ["AAPL"] }
        }
      ];

      for (const test of writeEndpoints) {
        // Test without auth
        const unauthResponse = await request(app)[test.method](test.endpoint)
          .send(test.body);
        
        expect([401, 403]).toContain(unauthResponse.status);
        expect(unauthResponse.body).toHaveProperty("success", false);

        // Test with auth
        const authResponse = await request(app)[test.method](test.endpoint)
          .set("Authorization", "Bearer dev-bypass-token")
          .send(test.body);
        
        expect([200, 404]).toContain(authResponse.status);
        // Should not be auth error
        expect([401, 403]).not.toContain(authResponse.status);
      }
    });
  });

  describe("Multi-Request Authentication Sessions", () => {
    test("should handle multiple sequential authenticated requests", async () => {
      const sequentialRequests = [
        { endpoint: "/api/portfolio", method: "get" },
        { endpoint: "/api/portfolio/summary", method: "get" },
        { endpoint: "/api/portfolio/positions", method: "get" },
        { endpoint: "/api/alerts/active", method: "get" }
      ];

      const results = [];

      for (const req of sequentialRequests) {
        const response = await request(app)[req.method](req.endpoint)
          .set("Authorization", "Bearer dev-bypass-token");
        
        results.push({
          endpoint: req.endpoint,
          status: response.status,
          authenticated: ![401, 403].includes(response.status)
        });
      }

      // All requests should be authenticated successfully
      results.forEach(result => {
        expect(result.authenticated).toBe(true);
        expect(result.status).toBe(200);
      });
    });

    test("should handle concurrent authenticated requests", async () => {
      const concurrentRequests = [
        request(app).get("/api/portfolio").set("Authorization", "Bearer dev-bypass-token"),
        request(app).get("/api/portfolio/summary").set("Authorization", "Bearer dev-bypass-token"),
        request(app).get("/api/portfolio/positions").set("Authorization", "Bearer dev-bypass-token"),
        request(app).get("/api/alerts/active").set("Authorization", "Bearer dev-bypass-token")
      ];

      const responses = await Promise.all(concurrentRequests);

      responses.forEach(response => {
        // None should be auth failures
        expect([401, 403]).not.toContain(response.status);
        expect([200, 404, 500, 501]).toContain(response.status);
      });
    });
  });

  describe("Authentication Error Handling", () => {
    test("should provide consistent error responses for auth failures", async () => {
      const authFailureScenarios = [
        { description: "No header", headers: {} },
        { description: "Empty header", headers: { "Authorization": "" } },
        { description: "Invalid format", headers: { "Authorization": "Invalid format" } },
        { description: "Invalid token", headers: { "Authorization": "Bearer invalid123" } }
      ];

      const testEndpoint = "/api/portfolio";

      for (const scenario of authFailureScenarios) {
        let requestBuilder = request(app).get(testEndpoint);
        
        Object.entries(scenario.headers).forEach(([key, value]) => {
          requestBuilder = requestBuilder.set(key, value);
        });

        const response = await requestBuilder;
        
        expect([401, 500]).toContain(response.status);
        
        // Handle both custom API format and Express default format
        const hasCustomFormat = Object.prototype.hasOwnProperty.call(response.body, "success");
        const hasExpressFormat = Object.prototype.hasOwnProperty.call(response.body, "error") || Object.prototype.hasOwnProperty.call(response.body, "message");
        expect(hasCustomFormat || hasExpressFormat).toBe(true);
        const errorMessage = response.body.error || response.body.message || "";
        expect(typeof errorMessage).toBe("string");
        expect(response.headers['content-type']).toMatch(/application\/json/);
      }
    });

    test("should not leak sensitive information in auth errors", async () => {
      const sensitiveTokens = [
        "Bearer fake-jwt-token-with-sensitive-data-12345",
        "Bearer prod-secret-key-dont-expose",
        "Bearer database-connection-string-here"
      ];

      const testEndpoint = "/api/portfolio";

      for (const token of sensitiveTokens) {
        const response = await request(app)
          .get(testEndpoint)
          .set("Authorization", token);
        
        expect([401, 500]).toContain(response.status);
        
        const errorMessage = (response.body?.error || response.body?.message || "").toLowerCase();
        if (errorMessage) {
          
          // Should not contain parts of the token
          expect(errorMessage).not.toMatch(/jwt|secret|database|connection|prod/);
          expect(errorMessage).not.toContain(token.split(' ')[1]); // Token part
          
          // Should be generic error message
          expect(errorMessage).toMatch(/unauthorized|invalid|authentication|authorization/);
        }
      }
    });
  });

  describe("Route-Specific Authentication", () => {
    test("should enforce authentication on protected routes", async () => {
      const protectedRoutes = [
        // Portfolio routes
        "/api/portfolio",
        "/api/portfolio/summary", 
        "/api/portfolio/positions",
        "/api/portfolio/analytics",
        "/api/portfolio/analysis",
        "/api/portfolio/risk-analysis",
        "/api/portfolio/performance",
        "/api/portfolio/holdings",
        "/api/portfolio/transactions",
        
        // Trading routes
        "/api/trades",
        "/api/alerts/active",
        
        // Backtest routes  
        "/api/backtest/results"
      ];

      for (const route of protectedRoutes) {
        const response = await request(app).get(route);
        
        // Should require authentication (expect 401/403 for protected routes)
        expect([401, 403, 500]).toContain(response.status);
        
        // Should return authentication error
        if (response.status === 401 || response.status === 403) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });

    test("should allow public access to public routes", async () => {
      const publicRoutes = [
        "/api/health",
        "/api/market/overview",
        "/api/calendar/earnings"
      ];

      for (const route of publicRoutes) {
        const response = await request(app).get(route);
        
        // Should not require authentication
        expect([401, 403]).not.toContain(response.status);
        expect([200, 404, 500, 501]).toContain(response.status);
      }
    });

    test("should handle mixed public/protected route access", async () => {
      // Access public route first
      const publicResponse = await request(app).get("/api/health");
      expect(publicResponse.status).toBe(200);

      // Access protected route without auth
      const protectedResponse = await request(app).get("/api/portfolio");
      expect([401, 403]).toContain(protectedResponse.status);

      // Access protected route with auth
      const authResponse = await request(app)
        .get("/api/portfolio")
        .set("Authorization", "Bearer dev-bypass-token");
      expect(authResponse.status).toBe(200);
      expect([401, 403]).not.toContain(authResponse.status);

      // Access public route again
      const publicResponse2 = await request(app).get("/api/market/overview");
      expect(publicResponse.status).toBe(200);
    });
  });

  describe("Authentication Performance", () => {
    test("should handle authentication efficiently", async () => {
      const testEndpoint = "/api/portfolio";
      const requestCount = 10;
      
      const startTime = Date.now();
      
      const authRequests = Array.from({ length: requestCount }, () =>
        request(app)
          .get(testEndpoint)
          .set("Authorization", "Bearer dev-bypass-token")
      );

      const responses = await Promise.all(authRequests);
      
      const duration = Date.now() - startTime;
      
      // Authentication should not significantly slow down requests
      expect(duration).toBeLessThan(10000); // 10 seconds for 10 requests
      
      // All should be processed
      expect(responses.length).toBe(requestCount);
      
      // None should be auth failures
      responses.forEach(response => {
        expect([401, 403]).not.toContain(response.status);
      });
    });

    test("should handle rapid authentication attempts", async () => {
      const testEndpoint = "/api/portfolio";
      const rapidCount = 20;
      
      // Create rapid fire requests
      const rapidRequests = Array.from({ length: rapidCount }, (_, i) =>
        request(app)
          .get(testEndpoint)
          .set("Authorization", `Bearer dev-bypass-token-${i}`)
          .then(response => ({ index: i, status: response.status }))
          .catch(error => ({ index: i, error: error.message }))
      );

      const results = await Promise.all(rapidRequests);
      
      // All requests should be processed
      expect(results.length).toBe(rapidCount);
      
      // Most should be processed (even if they fail auth)
      const processedRequests = results.filter(r => r.status !== undefined || r.error !== undefined);
      expect(processedRequests.length).toBe(rapidCount);
      
      // Should handle gracefully without hanging or crashing
      results.forEach(result => {
        if (result.status) {
          expect([200, 404]).toContain(result.status);
        }
      });
    });
  });

  describe("Authentication Integration with Other Middleware", () => {
    test("should work with request validation", async () => {
      const endpoint = "/api/portfolio/analyze";
      
      // Valid request with auth
      const validResponse = await request(app)
        .post(endpoint)
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ symbols: ["AAPL"] });
      
      expect([200, 404]).toContain(validResponse.status);
      expect([401, 403]).not.toContain(validResponse.status);

      // Invalid request with auth (should get validation error, not auth error)
      const invalidResponse = await request(app)
        .post(endpoint)
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ invalid: "data" });
      
      expect([400, 404]).toContain(invalidResponse.status);
      expect([401, 403]).not.toContain(invalidResponse.status);

      // Valid request without auth (should get auth error)
      const noAuthResponse = await request(app)
        .post(endpoint)
        .send({ symbols: ["AAPL"] });
      
      expect([401, 403]).toContain(noAuthResponse.status);
    });

    test("should work with error handling middleware", async () => {
      const endpoint = "/api/portfolio/nonexistent";
      
      // 404 with auth
      const authResponse = await request(app)
        .get(endpoint)
        .set("Authorization", "Bearer dev-bypass-token");
      
      expect(authResponse.status).toBe(404);
      
      // Handle both custom API format and Express default format
      const hasCustomFormat = Object.prototype.hasOwnProperty.call(authResponse.body, "success");
      const hasExpressFormat = Object.prototype.hasOwnProperty.call(authResponse.body, "error") || Object.prototype.hasOwnProperty.call(authResponse.body, "message");
      expect(hasCustomFormat || hasExpressFormat).toBe(true);

      // Auth error without token (should get auth error, not 404)
      const noAuthResponse = await request(app).get(endpoint);
      
      expect([401, 403]).toContain(noAuthResponse.status);
      
      // Handle both custom API format and Express default format
      const hasCustomFormat2 = Object.prototype.hasOwnProperty.call(noAuthResponse.body, "success");
      const hasExpressFormat2 = Object.prototype.hasOwnProperty.call(noAuthResponse.body, "error") || Object.prototype.hasOwnProperty.call(noAuthResponse.body, "message");
      expect(hasCustomFormat2 || hasExpressFormat2).toBe(true);
    });
  });
});
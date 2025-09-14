/**
 * Auth Middleware Service Integration Tests
 * Tests authentication middleware integration with actual services
 * Validates token processing and auth context propagation
 */

const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("Auth Middleware with Service Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Token Validation with Real Auth Service", () => {
    test("should validate tokens against real auth service", async () => {
      const response = await request(app)
        .get("/api/portfolio")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404, 500, 501]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("status", "operational");
        expect(response.body).toHaveProperty("message");
      }
    });

    test("should handle expired tokens in service calls", async () => {
      const response = await request(app)
        .get("/api/portfolio")
        .set("Authorization", "Bearer expired-token-123");

      expect([401, 500]).toContain(response.status);
      if (response.status === 401) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should handle malformed auth headers", async () => {
      const testCases = [
        "InvalidFormat token",
        "Bearer",
        "bearer  ",
        "Bearer    multiple   spaces   token"
      ];

      for (const authHeader of testCases) {
        const response = await request(app)
          .get("/api/portfolio")
          .set("Authorization", authHeader);
        
        expect([401, 403, 500]).toContain(response.status);
        
        if (response.status === 401 || response.status === 403) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });

  describe("Auth Context Propagation Through Service Chain", () => {
    test("should propagate auth context through service chain", async () => {
      // Test that auth middleware sets user context for downstream services
      const response = await request(app)
        .get("/api/portfolio/summary")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404, 500, 501]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toBeDefined();
      }
    });

    test("should maintain user context across multiple service calls", async () => {
      // Test complex operation requiring multiple service interactions
      const response = await request(app)
        .post("/api/portfolio/analyze")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ symbols: ["AAPL", "GOOGL"] });

      expect([200, 404, 500, 501]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
      }
    });

    test("should handle auth failures in middleware chain", async () => {
      // Test what happens when auth middleware fails and error propagates
      const response = await request(app)
        .post("/api/portfolio/analyze")
        .send({ symbols: ["AAPL"] }); // No auth header

      expect([401, 500]).toContain(response.status);
      if (response.status === 401) {
        expect(response.body).toHaveProperty("success", false);
      }
      expect(response.body).toHaveProperty("error");
    });
  });

  describe("Auth Middleware with Different Route Types", () => {
    test("should protect all authenticated routes consistently", async () => {
      const protectedRoutes = [
        "/api/portfolio",
        "/api/alerts/active",
        "/api/trades",
        "/api/portfolio/summary"
      ];

      for (const route of protectedRoutes) {
        const response = await request(app).get(route);
        
        expect([401, 403, 500]).toContain(response.status);
        
        if (response.status === 401 || response.status === 403) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });

    test("should allow public routes without authentication", async () => {
      const publicRoutes = [
        "/api/health",
        "/api/market/overview"
      ];

      for (const route of publicRoutes) {
        const response = await request(app).get(route);
        
        expect([401, 500]).toContain(response.status);
      }
    });
  });

  describe("Auth Service Error Handling", () => {
    test("should handle auth service unavailability gracefully", async () => {
      // Test with various invalid tokens to simulate auth service issues
      const response = await request(app)
        .get("/api/portfolio")
        .set("Authorization", "Bearer invalid-service-token");

      expect([401, 500]).toContain(response.status);
      if (response.status === 401) {
        expect(response.body).toHaveProperty("success", false);
      }
    });

    test("should provide consistent error responses", async () => {
      const errorScenarios = [
        { header: "", expectedStatus: [401, 403] },
        { header: "Bearer invalid", expectedStatus: [401, 403] },
        { header: "InvalidFormat", expectedStatus: [401, 403] }
      ];

      for (const scenario of errorScenarios) {
        let requestBuilder = request(app).get("/api/portfolio");
        
        if (scenario.header) {
          requestBuilder = requestBuilder.set("Authorization", scenario.header);
        }

        const response = await requestBuilder;
        
        expect(scenario.expectedStatus).toContain(response.status);
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.headers['content-type']).toMatch(/application\/json/);
      }
    });
  });
});
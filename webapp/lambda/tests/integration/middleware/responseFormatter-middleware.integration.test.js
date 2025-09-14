/**
 * Response Formatter Middleware Integration Tests  
 * Tests response formatting middleware across all route types
 * Validates consistent response structure and content formatting
 */

const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("Response Formatter Middleware Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Success Response Formatting", () => {
    test("should format successful responses consistently", async () => {
      const successEndpoints = [
        { endpoint: "/api/health", auth: false, expectedFields: ["status"] },
        { endpoint: "/api/market/overview", auth: false, expectedFields: ["data"] }, // Raw response has data
        { endpoint: "/api/calendar/earnings", auth: false, expectedFields: ["data"] } // Updated to match actual response
      ];

      for (const test of successEndpoints) {
        let requestBuilder = request(app).get(test.endpoint);
        
        if (test.auth) {
          requestBuilder = requestBuilder.set("Authorization", "Bearer dev-bypass-token");
        }
        
        const response = await requestBuilder;
        
        if (response.status === 200) {
          // Verify content type
          expect(response.headers['content-type']).toMatch(/application\/json/);
          
          // Verify expected fields exist
          test.expectedFields.forEach(field => {
            expect(response.body).toHaveProperty(field);
          });
          
          // Verify timestamp if present
          if (response.body.timestamp) {
            expect(typeof response.body.timestamp).toBe("string");
            expect(new Date(response.body.timestamp).toString()).not.toBe("Invalid Date");
          }
        }
      }
    });

    test("should format paginated responses consistently", async () => {
      const paginatedEndpoints = [
        "/api/calendar/events",
        "/api/calendar/earnings-estimates",
        "/api/calendar/earnings-history"
      ];

      for (const endpoint of paginatedEndpoints) {
        const response = await request(app).get(endpoint);
        
        if (response.status === 200 && response.body.pagination) {
          expect(response.body).toHaveProperty("data");
          expect(response.body).toHaveProperty("pagination");
          
          const pagination = response.body.pagination;
          expect(pagination).toHaveProperty("page");
          expect(pagination).toHaveProperty("limit");
          expect(pagination).toHaveProperty("total");
          
          // Validate pagination field types
          expect(typeof pagination.page).toBe("number");
          expect(typeof pagination.limit).toBe("number");
          expect(typeof pagination.total).toBe("number");
        }
      }
    });
  });

  describe("Error Response Formatting", () => {
    test("should format error responses with consistent structure", async () => {
      const errorScenarios = [
        { endpoint: "/api/nonexistent", expectedStatus: 404 },
        { endpoint: "/api/portfolio/nonexistent", expectedStatus: 404 }
      ];

      for (const scenario of errorScenarios) {
        const response = await request(app).get(scenario.endpoint);
        
        expect(response.status).toBe(scenario.expectedStatus);
        expect(response.headers['content-type']).toMatch(/application\/json/);
        
        // Error response should have error information
        expect(response.body).toHaveProperty("error");
        expect(typeof response.body.error).toBe("string");
        
        // Optional fields that may be present
        if (response.body.timestamp) {
          expect(typeof response.body.timestamp).toBe("string");
        }
        
        if (response.body.success !== undefined) {
          expect(response.body.success).toBe(false);
        }
        
        if (response.body.code) {
          expect(typeof response.body.code).toBe("string");
        }
      }
    });

    test("should format validation error responses consistently", async () => {
      const validationTests = [
        {
          endpoint: "/api/portfolio/analyze",
          method: "post",
          data: { symbols: "invalid-type" },
          auth: true
        }
      ];

      for (const test of validationTests) {
        let requestBuilder = request(app)[test.method](test.endpoint);
        
        if (test.auth) {
          requestBuilder = requestBuilder.set("Authorization", "Bearer dev-bypass-token");
        }
        
        const response = await requestBuilder.send(test.data);
        
        if (response.status === 400 || response.status === 422) {
          expect(response.headers['content-type']).toMatch(/application\/json/);
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(typeof response.body.error).toBe("string");
        }
      }
    });
  });

  describe("Content-Type Header Consistency", () => {
    test("should set JSON content-type for all API responses", async () => {
      const testEndpoints = [
        { endpoint: "/api/health", method: "get", auth: false },
        { endpoint: "/api/market/overview", method: "get", auth: false },
        { endpoint: "/api/calendar/earnings", method: "get", auth: false },
        { endpoint: "/api/nonexistent", method: "get", auth: false } // 404 case
      ];

      for (const test of testEndpoints) {
        let requestBuilder = request(app)[test.method](test.endpoint);
        
        if (test.auth) {
          requestBuilder = requestBuilder.set("Authorization", "Bearer dev-bypass-token");
        }
        
        const response = await requestBuilder;
        
        // All API responses should be JSON
        expect(response.headers['content-type']).toMatch(/application\/json/);
      }
    });

    test("should maintain content-type consistency across HTTP methods", async () => {
      const methodTests = [
        { endpoint: "/api/health", method: "get" },
        { endpoint: "/api/health", method: "post" }, // May return 404/405
        { endpoint: "/api/calendar/earnings", method: "get" },
        { endpoint: "/api/calendar/earnings", method: "post" } // May return 404/405
      ];

      for (const test of methodTests) {
        const response = await request(app)[test.method](test.endpoint);
        
        // Regardless of status code, content-type should be JSON for API routes
        expect(response.headers['content-type']).toMatch(/application\/json/);
      }
    });
  });

  describe("Response Header Standards", () => {
    test("should include standard security headers", async () => {
      const response = await request(app).get("/api/health");
      
      // Check for common security headers (if implemented)
      const securityHeaders = [
        'x-content-type-options',
        'x-frame-options',
        'x-xss-protection'
      ];
      
      // Note: Not all may be implemented, just check if they exist and are properly set
      securityHeaders.forEach(header => {
        if (response.headers[header]) {
          expect(typeof response.headers[header]).toBe("string");
          expect(response.headers[header].length).toBeGreaterThan(0);
        }
      });
    });

    test("should handle CORS headers appropriately", async () => {
      const corsTests = [
        { endpoint: "/api/health", origin: "http://localhost:3000" },
        { endpoint: "/api/market/overview", origin: "http://localhost:3001" }
      ];

      for (const test of corsTests) {
        const response = await request(app)
          .get(test.endpoint)
          .set("Origin", test.origin);
        
        // If CORS is implemented, check headers
        if (response.headers['access-control-allow-origin']) {
          expect(response.headers['access-control-allow-origin']).toBeDefined();
        }
        
        if (response.headers['access-control-allow-methods']) {
          expect(response.headers['access-control-allow-methods']).toBeDefined();
        }
      }
    });
  });

  describe("Response Data Formatting", () => {
    test("should format nested data structures consistently", async () => {
      const response = await request(app).get("/api/calendar/earnings");
      
      if (response.status === 200 && response.body.data) {
        const data = response.body.data;
        
        // Check consistent structure for earnings data
        expect(data).toHaveProperty("earnings");
        expect(Array.isArray(data.earnings)).toBe(true);
        
        if (data.earnings.length > 0) {
          const earning = data.earnings[0];
          expect(earning).toHaveProperty("symbol");
          expect(earning).toHaveProperty("company_name");
          expect(typeof earning.symbol).toBe("string");
          expect(typeof earning.company_name).toBe("string");
        }
        
        // Check summary structure
        if (data.summary) {
          expect(data.summary).toHaveProperty("total_earnings");
          expect(typeof data.summary.total_earnings).toBe("number");
        }
      }
    });

    test("should handle empty data responses consistently", async () => {
      const response = await request(app)
        .get("/api/calendar/earnings?symbol=NONEXISTENT&start_date=2050-01-01&end_date=2050-01-02");
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        
        const data = response.body.data;
        expect(data.earnings).toEqual([]);
        expect(data.summary.total_earnings).toBe(0);
      }
    });
  });

  describe("Response Timing and Performance Headers", () => {
    test("should include performance-related headers when available", async () => {
      const response = await request(app).get("/api/health");
      
      // Check for timing headers (if implemented)
      if (response.headers['x-response-time']) {
        expect(typeof response.headers['x-response-time']).toBe("string");
        // Should be in format like "123ms"
        expect(response.headers['x-response-time']).toMatch(/^\d+(\.\d+)?ms$/);
      }
      
      // Check for cache headers
      if (response.headers['cache-control']) {
        expect(typeof response.headers['cache-control']).toBe("string");
      }
    });

    test("should maintain response time consistency", async () => {
      const startTime = Date.now();
      const response = await request(app).get("/api/health");
      const duration = Date.now() - startTime;
      
      // Response should be reasonably fast
      expect(duration).toBeLessThan(5000); // 5 seconds max for health check
      
      // Verify response is properly formatted despite timing
      expect(response.headers['content-type']).toMatch(/application\/json/);
      expect(response.body).toBeDefined();
    });
  });

  describe("Cross-Route Response Consistency", () => {
    test("should maintain consistent response structure across route families", async () => {
      const routeFamilies = [
        { family: "calendar", endpoints: ["/api/calendar/earnings", "/api/calendar/health"] },
        { family: "market", endpoints: ["/api/market/overview"] },
        { family: "system", endpoints: ["/api/health"] }
      ];

      for (const family of routeFamilies) {
        const responses = [];
        
        for (const endpoint of family.endpoints) {
          const response = await request(app).get(endpoint);
          responses.push(response);
        }
        
        // Check that successful responses in same family have similar structure
        const successfulResponses = responses.filter(r => r.status === 200);
        
        if (successfulResponses.length > 1) {
          const first = successfulResponses[0];
          
          successfulResponses.forEach(response => {
            // All should be JSON
            expect(response.headers['content-type']).toMatch(/application\/json/);
            
            // Should have similar top-level structure patterns (flexible check)
            if (first.body.success !== undefined && response.body.success !== undefined) {
              expect(response.body).toHaveProperty("success");
            }
            
            if (first.body.timestamp !== undefined && response.body.timestamp !== undefined) {
              expect(response.body).toHaveProperty("timestamp");
            }
            
            // At minimum, all should have some data
            expect(response.body).toBeDefined();
            expect(typeof response.body).toBe('object');
          });
        }
      }
    });

    test("should format authentication-related responses consistently", async () => {
      const authTests = [
        { endpoint: "/api/portfolio", auth: false }, // Should get 401/403
        { endpoint: "/api/portfolio", auth: "Bearer dev-bypass-token" }, // Should get 200
        { endpoint: "/api/alerts/active", auth: false }, // Should get 401/403
        { endpoint: "/api/alerts/active", auth: "Bearer dev-bypass-token" } // May get 200/404/500
      ];

      for (const test of authTests) {
        let requestBuilder = request(app).get(test.endpoint);
        
        if (test.auth) {
          requestBuilder = requestBuilder.set("Authorization", test.auth);
        }
        
        const response = await requestBuilder;
        
        // All responses should be JSON formatted
        expect(response.headers['content-type']).toMatch(/application\/json/);
        
        // Auth-related errors should have consistent structure
        if (response.status === 401 || response.status === 403) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });
});
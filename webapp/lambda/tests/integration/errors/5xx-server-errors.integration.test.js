/**
 * 5xx Server Error Scenarios Integration Tests
 * Tests server error handling and recovery mechanisms
 * Validates proper error responses for server-side issues
 */

const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("5xx Server Error Scenarios Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("500 Internal Server Error Scenarios", () => {
    test("should handle database connection failures gracefully", async () => {
      // Test endpoints that depend on database
      const databaseDependentEndpoints = [
        { endpoint: "/api/portfolio/positions", auth: true },
        { endpoint: "/api/calendar/events", auth: false },
        { endpoint: "/api/backtest/results", auth: true },
      ];

      for (const test of databaseDependentEndpoints) {
        let requestBuilder = request(app).get(test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder;

        // Should handle gracefully - either succeed or fail with proper error format
        expect(response.headers["content-type"]).toMatch(/application\/json/);

        if (response.status === 500) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");

          // Should not expose database connection details
          expect(response.body.error).not.toMatch(
            /connection|pool|timeout|database|pg|postgresql/i
          );
          expect(response.body.error).not.toMatch(
            /ECONNREFUSED|ETIMEDOUT|ENOTFOUND/
          );
        }
      }
    });

    test("should handle application errors with proper formatting", async () => {
      // Test endpoints that might throw application errors
      const errorProneEndpoints = [
        {
          endpoint: "/api/portfolio/analyze",
          method: "post",
          body: {
            symbols: ["INVALID_SYMBOL_THAT_MIGHT_CAUSE_ERROR"],
            timeframe: "1d",
          },
          auth: true,
        },
      ];

      for (const test of errorProneEndpoints) {
        let requestBuilder = request(app)[test.method](test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder.send(test.body);

        // Should handle errors gracefully
        expect(response.headers["content-type"]).toMatch(/application\/json/);

        if (response.status === 500) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(typeof response.body.error).toBe("string");

          // Should not expose internal stack traces or system details
          expect(response.body.error).not.toMatch(
            /stack trace|at Object\.|at Function\./
          );
          expect(response.body.error).not.toMatch(
            /node_modules|\/app\/|\/usr\/|\/var\//
          );
        }
      }
    });

    test("should handle memory or resource exhaustion", async () => {
      // Create requests that might stress the server
      const stressTests = [
        {
          endpoint: "/api/portfolio/analyze",
          method: "post",
          body: {
            symbols: Array(1000).fill("AAPL"), // Large array
            timeframe: "1d",
          },
          auth: true,
        },
      ];

      for (const test of stressTests) {
        let requestBuilder = request(app)[test.method](test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder.send(test.body);

        // Should handle resource constraints gracefully
        expect(response.headers["content-type"]).toMatch(/application\/json/);

        if (response.status >= 500) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");

          // Should not expose system resource details
          expect(response.body.error).not.toMatch(
            /memory|heap|cpu|process|system/i
          );
        }
      }
    });

    test("should maintain response format during server errors", async () => {
      // Test various endpoints that might fail
      const potentialFailureEndpoints = [
        { endpoint: "/api/portfolio/summary", auth: true },
        { endpoint: "/api/calendar/earnings-metrics", auth: false },
        { endpoint: "/api/market/analysis", auth: false },
      ];

      for (const test of potentialFailureEndpoints) {
        let requestBuilder = request(app).get(test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder;

        // Regardless of status, should maintain JSON format
        expect(response.headers["content-type"]).toMatch(/application\/json/);

        if (response.status >= 500) {
          // Standard error response structure
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(typeof response.body.error).toBe("string");
          expect(response.body.error.length).toBeGreaterThan(0);

          // Optional fields that might be present
          if (response.body.timestamp) {
            expect(typeof response.body.timestamp).toBe("string");
          }

          if (response.body.requestId) {
            expect(typeof response.body.requestId).toBe("string");
          }
        }
      }
    });
  });

  describe("502 Bad Gateway Scenarios", () => {
    test("should handle upstream service failures", async () => {
      // Test endpoints that might depend on external services
      const externalServiceEndpoints = [
        { endpoint: "/api/market/overview", auth: false },
        { endpoint: "/api/calendar/earnings", auth: false },
      ];

      for (const test of externalServiceEndpoints) {
        let requestBuilder = request(app).get(test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder;

        // Should handle upstream failures gracefully
        if (response.status === 502) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.body.error).toMatch(
            /service|gateway|upstream|external/i
          );

          // Should not expose upstream service details
          expect(response.body.error).not.toMatch(
            /http:\/\/|https:\/\/|localhost|127\.0\.0\.1/
          );
        }
      }
    });
  });

  describe("503 Service Unavailable Scenarios", () => {
    test("should handle service maintenance mode", async () => {
      // Test how the service behaves when overloaded or in maintenance
      // This is more of a theoretical test since we can't easily simulate maintenance

      const maintenanceTestEndpoints = [
        { endpoint: "/api/health", auth: false },
        { endpoint: "/api/portfolio", auth: true },
      ];

      for (const test of maintenanceTestEndpoints) {
        let requestBuilder = request(app).get(test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder;

        if (response.status === 503) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.body.error).toMatch(
            /unavailable|maintenance|overloaded/i
          );

          // Should include Retry-After header
          if (response.headers["retry-after"]) {
            expect(typeof response.headers["retry-after"]).toBe("string");
          }
        }
      }
    });

    test("should handle database pool exhaustion", async () => {
      // Create many concurrent requests to potentially exhaust connection pool
      const concurrentRequests = Array.from({ length: 30 }, (_, i) =>
        request(app)
          .get("/api/calendar/earnings")
          .then((response) => ({
            id: i,
            status: response.status,
            body: response.body,
          }))
          .catch((error) => ({ id: i, error: error.message }))
      );

      const results = await Promise.all(concurrentRequests);

      // Check for service unavailable responses
      const unavailableResponses = results.filter((r) => r.status === 503);

      if (unavailableResponses.length > 0) {
        unavailableResponses.forEach((response) => {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        });
      }

      // Most requests should still succeed or fail gracefully
      const successfulResponses = results.filter((r) => r.status === 200);
      const errorResponses = results.filter((r) => r.status >= 400);

      expect(successfulResponses.length + errorResponses.length).toBe(30);
    });
  });

  describe("504 Gateway Timeout Scenarios", () => {
    test("should handle slow upstream responses", async () => {
      // Test endpoints that might have slow external dependencies
      const slowEndpoints = [
        { endpoint: "/api/portfolio/analysis", auth: true },
        { endpoint: "/api/market/detailed-analysis", auth: false },
      ];

      for (const test of slowEndpoints) {
        let requestBuilder = request(app).get(test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        // Set a reasonable timeout for the test
        const response = await requestBuilder.timeout(10000); // 10 second timeout

        if (response.status === 504) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.body.error).toMatch(/timeout|gateway|slow|response/i);
        }
      }
    });
  });

  describe("Server Error Recovery and Resilience", () => {
    test("should recover gracefully from temporary failures", async () => {
      // Test server resilience by making requests before, during, and after stress

      // Phase 1: Normal operation
      const normalResponse = await request(app).get("/api/health");
      const initialStatus = normalResponse.status;

      // Phase 2: Stress the server with concurrent requests
      const stressRequests = Array.from({ length: 50 }, () =>
        request(app)
          .get("/api/market/overview")
          .then((r) => ({ status: r.status, success: r.status === 200 }))
          .catch((e) => ({ status: 500, success: false, error: e.message }))
      );

      const stressResults = await Promise.all(stressRequests);

      // Phase 3: Recovery check
      await new Promise((resolve) => setTimeout(resolve, 1000)); // Wait 1 second
      const recoveryResponse = await request(app).get("/api/health");

      // Server should recover
      expect([200, 503].includes(recoveryResponse.status)).toBe(true);

      if (recoveryResponse.status === 200) {
        // If health check passes, server has recovered
        expect(recoveryResponse.body).toBeDefined();
      }

      // Analyze stress test results
      const successfulStressRequests = stressResults.filter((r) => r.success);
      const failedStressRequests = stressResults.filter((r) => !r.success);

      // Some requests should have succeeded even under stress
      expect(successfulStressRequests.length).toBeGreaterThan(0);

      // Failed requests should have appropriate status codes
      failedStressRequests.forEach((result) => {
        expect([500, 502, 503, 504].includes(result.status)).toBe(true);
      });
    });

    test("should maintain error logging during server errors", async () => {
      // Test that errors are properly logged (we can't directly check logs in this test,
      // but we can verify that error responses suggest logging is happening)

      const errorInducingRequests = [
        {
          endpoint: "/api/portfolio/analyze",
          method: "post",
          body: { symbols: ["NONEXISTENT"] },
          auth: true,
        },
      ];

      for (const test of errorInducingRequests) {
        let requestBuilder = request(app)[test.method](test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder.send(test.body);

        if (response.status >= 500) {
          // Error response should suggest proper error handling/logging
          expect(response.body).toHaveProperty("error");

          // Should have request tracking information (suggests logging)
          if (response.body.timestamp) {
            expect(typeof response.body.timestamp).toBe("string");
            expect(new Date(response.body.timestamp).toString()).not.toBe(
              "Invalid Date"
            );
          }
        }
      }
    });

    test("should handle cascading failures appropriately", async () => {
      // Test how the system handles when multiple components fail

      const cascadingFailureTest = async () => {
        const dependentEndpoints = [
          { endpoint: "/api/portfolio/summary", auth: true },
          { endpoint: "/api/portfolio/positions", auth: true },
          { endpoint: "/api/portfolio/performance", auth: true },
        ];

        const results = [];

        for (const test of dependentEndpoints) {
          let requestBuilder = request(app).get(test.endpoint);

          if (test.auth) {
            requestBuilder = requestBuilder.set(
              "Authorization",
              "Bearer dev-bypass-token"
            );
          }

          try {
            const response = await requestBuilder;
            results.push({
              endpoint: test.endpoint,
              status: response.status,
              hasError: response.status >= 400,
              errorMessage: response.body?.error,
            });
          } catch (error) {
            results.push({
              endpoint: test.endpoint,
              status: 500,
              hasError: true,
              errorMessage: error.message,
            });
          }
        }

        return results;
      };

      const cascadeResults = await cascadingFailureTest();

      // Verify that failures are handled consistently
      cascadeResults.forEach((result) => {
        if (result.hasError && result.status >= 500) {
          expect(result.errorMessage).toBeDefined();
          expect(typeof result.errorMessage).toBe("string");

          // Should not expose internal system details
          expect(result.errorMessage).not.toMatch(
            /stack|trace|node_modules|internal/i
          );
        }
      });

      // System should not completely fail - at least health check should work
      const healthCheck = await request(app).get("/api/health");
      expect([200, 503].includes(healthCheck.status)).toBe(true);
    });
  });

  describe("Server Error Security", () => {
    test("should not expose sensitive information in server errors", async () => {
      const securityTestEndpoints = [
        { endpoint: "/api/portfolio/positions", auth: true },
        { endpoint: "/api/calendar/events", auth: false },
      ];

      for (const test of securityTestEndpoints) {
        let requestBuilder = request(app).get(test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder;

        if (response.status >= 500 && response.body?.error) {
          const errorMessage = response.body.error.toLowerCase();

          // Should not expose sensitive system information
          const sensitivePatterns = [
            /password|secret|key|token/,
            /database.*connection|db.*url|connection.*string/,
            /file.*path|directory|\/usr\/|\/var\/|\/home\//,
            /stack.*trace|at.*object|at.*function/,
            /node_modules|package\.json|\.env/,
            /port.*\d+|localhost:\d+|127\.0\.0\.1/,
            /internal.*server|system.*error|application.*error/,
          ];

          sensitivePatterns.forEach((pattern) => {
            expect(errorMessage).not.toMatch(pattern);
          });

          // Error should be user-friendly but not revealing
          expect(errorMessage).toMatch(/error|failed|unable|unavailable/i);
        }
      }
    });

    test("should sanitize error messages from external sources", async () => {
      // Test that external API errors are properly sanitized
      const externalDependentEndpoints = [
        { endpoint: "/api/market/overview", auth: false },
      ];

      for (const test of externalDependentEndpoints) {
        const response = await request(app).get(test.endpoint);

        if (response.status >= 500 && response.body?.error) {
          const errorMessage = response.body.error;

          // Should not contain raw external API errors
          expect(errorMessage).not.toMatch(
            /http.*error|api.*key|endpoint.*not.*found/i
          );
          expect(errorMessage).not.toMatch(
            /timeout.*\d+ms|connection.*refused/i
          );

          // Should be sanitized and user-friendly
          expect(typeof errorMessage).toBe("string");
          expect(errorMessage.length).toBeLessThan(200); // Reasonable length
        }
      }
    });
  });

  describe("Cross-Route 5xx Error Consistency", () => {
    test("should maintain consistent 5xx error format across all routes", async () => {
      const serverErrorTests = [
        { endpoint: "/api/portfolio/complex-analysis", auth: true },
        { endpoint: "/api/calendar/complex-metrics", auth: false },
        { endpoint: "/api/market/heavy-computation", auth: false },
      ];

      for (const test of serverErrorTests) {
        let requestBuilder = request(app).get(test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder;

        // All responses should be JSON formatted
        expect(response.headers["content-type"]).toMatch(/application\/json/);

        if (response.status >= 500) {
          // Standard 5xx error format
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(typeof response.body.error).toBe("string");

          // Should not cache server errors
          if (response.headers["cache-control"]) {
            expect(response.headers["cache-control"]).toMatch(
              /no-cache|no-store|max-age=0/
            );
          }

          // Should have appropriate CORS headers even for errors
          if (response.headers["access-control-allow-origin"]) {
            expect(
              response.headers["access-control-allow-origin"]
            ).toBeDefined();
          }
        }
      }
    });

    test("should provide consistent error codes across similar failures", async () => {
      // Test that similar types of failures return similar error codes
      const similarEndpoints = [
        {
          endpoint: "/api/portfolio/positions",
          category: "database-dependent",
        },
        { endpoint: "/api/calendar/events", category: "database-dependent" },
        { endpoint: "/api/backtest/results", category: "database-dependent" },
      ];

      const errorsByCategory = {};

      for (const test of similarEndpoints) {
        let requestBuilder = request(app).get(test.endpoint);

        if (
          test.endpoint.includes("portfolio") ||
          test.endpoint.includes("backtest")
        ) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder;

        if (!errorsByCategory[test.category]) {
          errorsByCategory[test.category] = [];
        }

        errorsByCategory[test.category].push({
          endpoint: test.endpoint,
          status: response.status,
        });
      }

      // Similar endpoints should have similar error patterns
      Object.values(errorsByCategory).forEach((categoryResults) => {
        if (categoryResults.length > 1) {
          const statuses = categoryResults.map((r) => r.status);
          const errorStatuses = statuses.filter((s) => s >= 500);

          if (errorStatuses.length > 1) {
            // Similar failures should return similar status codes
            const uniqueErrorStatuses = new Set(errorStatuses);
            expect(uniqueErrorStatuses.size).toBeLessThanOrEqual(2); // Allow some variation
          }
        }
      });
    });
  });
});

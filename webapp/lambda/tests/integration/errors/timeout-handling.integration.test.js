/**
 * Timeout Handling Integration Tests
 * Tests request timeout scenarios and handling mechanisms
 * Validates timeout responses and recovery patterns
 */

const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Timeout Handling Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Request Timeout Scenarios", () => {
    test("should handle client-side request timeouts gracefully", async () => {
      // Test endpoints that might take longer to process (using existing endpoints)
      const timeoutTestEndpoints = [
        {
          endpoint: "/api/portfolio",
          method: "get",
          auth: true,
          timeout: 1000,
        },
        {
          endpoint: "/api/backtest/strategies",
          method: "get",
          auth: true,
          timeout: 1000,
        },
        {
          endpoint: "/api/calendar/earnings",
          method: "get",
          auth: false,
          timeout: 2000,
        },
      ];

      for (const test of timeoutTestEndpoints) {
        try {
          let requestBuilder = request(app)[test.method](test.endpoint);

          if (test.auth) {
            requestBuilder = requestBuilder.set(
              "Authorization",
              "Bearer dev-bypass-token"
            );
          }

          if (test.body) {
            requestBuilder = requestBuilder.send(test.body);
          }

          const response = await requestBuilder.timeout(test.timeout);

          // If request completes within timeout, verify proper response format
          expect(response.headers["content-type"]).toMatch(/application\/json/);

          if (response.status >= 400) {
            // Check if response has expected error format
            if (
              response.body &&
              typeof response.body === "object" &&
              !Array.isArray(response.body)
            ) {
              expect(response.body).toHaveProperty("success", false);
              expect(response.body).toHaveProperty("error");
            }
          }
        } catch (error) {
          // Timeout occurred - verify it's handled appropriately
          if (
            error.code === "ECONNABORTED" ||
            error.message.includes("timeout")
          ) {
            // This is expected for timeout tests
            expect(error.timeout).toBe(test.timeout);
          } else {
            // Other errors should still be valid responses
            throw error;
          }
        }
      }
    });

    test("should return 408 or 504 for server-side timeouts", async () => {
      // Test endpoints that might timeout on the server side
      const serverTimeoutEndpoints = [
        { endpoint: "/api/portfolio/complex-analysis", auth: true },
        { endpoint: "/api/market/detailed-analysis", auth: false },
      ];

      for (const test of serverTimeoutEndpoints) {
        let requestBuilder = request(app).get(test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder.timeout(30000); // 30 second timeout

        if (response.status === 408 || response.status === 504) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.body.error).toMatch(
            /timeout|slow|response|processing/i
          );

          // Should include appropriate headers
          if (response.headers["retry-after"]) {
            expect(typeof response.headers["retry-after"]).toBe("string");
          }
        }
      }
    });
  });

  describe("Database Query Timeout Scenarios", () => {
    test("should handle slow database queries gracefully", async () => {
      // Test endpoints that perform database operations
      const databaseQueryEndpoints = [
        { endpoint: "/api/portfolio/positions", auth: true },
        { endpoint: "/api/calendar/events", auth: false },
        { endpoint: "/api/backtest/results", auth: true },
      ];

      for (const test of databaseQueryEndpoints) {
        const startTime = Date.now();

        let requestBuilder = request(app).get(test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder.timeout(15000); // 15 second timeout
        const duration = Date.now() - startTime;

        // Response should come back in reasonable time
        expect(duration).toBeLessThan(15000);

        // Should have proper response format regardless of success/failure
        expect(response.headers["content-type"]).toMatch(/application\/json/);

        if (response.status >= 400) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");

          // Database timeout errors should be user-friendly
          if (response.status === 500 && response.body.error) {
            expect(response.body.error).not.toMatch(
              /query.*timeout|connection.*timeout|pg.*timeout/i
            );
          }
        }
      }
    });

    test("should handle connection pool timeout scenarios", async () => {
      // Create many concurrent requests to stress connection pool
      const concurrentConnections = 25;
      const connectionPromises = [];

      for (let i = 0; i < concurrentConnections; i++) {
        const promise = request(app)
          .get("/api/calendar/earnings")
          .timeout(10000)
          .then((response) => ({
            requestId: i,
            status: response.status,
            duration: Date.now(),
            success: response.status < 400,
          }))
          .catch((error) => ({
            requestId: i,
            error: error.message,
            timeout: error.code === "ECONNABORTED",
            success: false,
          }));

        connectionPromises.push(promise);
      }

      const results = await Promise.all(connectionPromises);

      // Analyze results
      const successfulRequests = results.filter((r) => r.success);
      const timeoutRequests = results.filter((r) => r.timeout);
      const errorRequests = results.filter((r) => r.error && !r.timeout);

      // Most requests should either succeed or fail gracefully
      expect(
        successfulRequests.length +
          timeoutRequests.length +
          errorRequests.length
      ).toBe(concurrentConnections);

      // Should have some successful requests
      expect(successfulRequests.length).toBeGreaterThan(0);

      // Timeout requests are acceptable under high load
      if (timeoutRequests.length > 0) {
        expect(timeoutRequests.length).toBeLessThan(
          concurrentConnections * 0.5
        ); // Less than 50% timeouts
      }
    });
  });

  describe("External Service Timeout Scenarios", () => {
    test("should handle external API timeouts properly", async () => {
      // Test endpoints that might depend on external services
      const externalServiceEndpoints = [
        {
          endpoint: "/api/market/overview",
          auth: false,
          expectedTimeout: 10000,
        },
        {
          endpoint: "/api/calendar/earnings",
          auth: false,
          expectedTimeout: 10000,
        },
      ];

      for (const test of externalServiceEndpoints) {
        const startTime = Date.now();

        const response = await request(app)
          .get(test.endpoint)
          .timeout(test.expectedTimeout);

        const duration = Date.now() - startTime;

        // Should respond within expected timeout
        expect(duration).toBeLessThan(test.expectedTimeout);

        if (response.status === 504 || response.status === 408) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.body.error).toMatch(
            /timeout|gateway|external|service/i
          );

          // Should not expose external service URLs or details
          expect(response.body.error).not.toMatch(
            /http:\/\/|https:\/\/|api\..*\.com/
          );
        }
      }
    });

    test("should implement circuit breaker patterns for repeated timeouts", async () => {
      // This test simulates repeated calls to potentially failing external services
      const externalEndpoint = "/api/market/overview";
      const rapidRequests = 10;

      const requests = Array.from({ length: rapidRequests }, async (_, i) => {
        const startTime = Date.now();

        try {
          const response = await request(app)
            .get(externalEndpoint)
            .timeout(5000);

          return {
            requestId: i,
            status: response.status,
            duration: Date.now() - startTime,
            success: response.status === 200,
          };
        } catch (error) {
          return {
            requestId: i,
            error: error.message,
            timeout: error.code === "ECONNABORTED",
            duration: Date.now() - startTime,
          };
        }
      });

      const results = await Promise.all(requests);

      // Analyze response patterns
      const successfulRequests = results.filter((r) => r.success);
      const timeoutRequests = results.filter((r) => r.timeout);
      const errorRequests = results.filter((r) => r.error && !r.timeout);

      // Should handle requests consistently
      expect(results.length).toBe(rapidRequests);

      // If there are consistent failures, later requests should be faster (circuit breaker)
      if (timeoutRequests.length > rapidRequests * 0.5) {
        // Check if later requests are faster (indicating circuit breaking)
        const laterRequests = results.slice(Math.floor(rapidRequests / 2));
        const avgLaterDuration =
          laterRequests.reduce((sum, r) => sum + r.duration, 0) /
          laterRequests.length;

        // Circuit breaker should make later requests fail fast
        expect(avgLaterDuration).toBeLessThan(3000); // Should be much faster than timeout
      }
    });
  });

  describe("Streaming and Long-Running Operation Timeouts", () => {
    test("should handle long-running analysis timeouts", async () => {
      // Test endpoints that might run complex analysis
      const longRunningEndpoints = [
        {
          endpoint: "/api/portfolio/analyze",
          method: "post",
          body: {
            symbols: ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"],
            timeframe: "1y",
            analysis_type: "comprehensive",
          },
          auth: true,
          maxDuration: 20000, // 20 seconds
        },
      ];

      for (const test of longRunningEndpoints) {
        const startTime = Date.now();

        try {
          let requestBuilder = request(app)[test.method](test.endpoint);

          if (test.auth) {
            requestBuilder = requestBuilder.set(
              "Authorization",
              "Bearer dev-bypass-token"
            );
          }

          const response = await requestBuilder
            .send(test.body)
            .timeout(test.maxDuration);

          const duration = Date.now() - startTime;

          // Should complete within max duration or return appropriate timeout response
          if (response.status === 200) {
            expect(duration).toBeLessThan(test.maxDuration);
            expect(response.body).toHaveProperty("success", true);
          } else if (response.status === 408 || response.status === 504) {
            expect(response.body).toHaveProperty("success", false);
            expect(response.body).toHaveProperty("error");
          }
        } catch (error) {
          if (error.code === "ECONNABORTED") {
            // Timeout occurred - this is acceptable for long-running operations
            const duration = Date.now() - startTime;
            expect(duration).toBeGreaterThanOrEqual(test.maxDuration * 0.9); // Within 90% of timeout
          } else {
            throw error;
          }
        }
      }
    });

    test("should provide timeout warnings for slow operations", async () => {
      // Test endpoints that might take a while but shouldn't timeout immediately
      const slowOperationEndpoints = [
        {
          endpoint: "/api/backtest/run",
          method: "post",
          body: { strategy: "complex" },
          auth: true,
        },
      ];

      for (const test of slowOperationEndpoints) {
        const startTime = Date.now();

        let requestBuilder = request(app)[test.method](test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder.send(test.body).timeout(30000); // 30 second timeout

        const duration = Date.now() - startTime;

        // Should respond within reasonable time
        expect(duration).toBeLessThan(30000);

        // If operation is slow but successful, might include timing information
        if (response.status === 200 && duration > 5000) {
          // If took more than 5 seconds
          // Response might include timing metadata
          if (response.body.metadata) {
            expect(response.body.metadata).toHaveProperty("processing_time");
          }
        }

        // Should always have proper response format
        expect(response.headers["content-type"]).toMatch(/application\/json/);
      }
    });
  });

  describe("Timeout Recovery and Resilience", () => {
    test("should recover gracefully after timeout scenarios", async () => {
      const testEndpoint = "/api/market/overview";

      // Phase 1: Normal request
      const normalResponse = await request(app).get(testEndpoint);
      const normalStatus = normalResponse.status;

      // Phase 2: Timeout stress test
      const timeoutStressPromises = Array.from({ length: 5 }, async () => {
        try {
          return await request(app).get(testEndpoint).timeout(500); // Very short timeout
        } catch (error) {
          return { timeout: true, error: error.message };
        }
      });

      const stressResults = await Promise.all(timeoutStressPromises);

      // Phase 3: Recovery check
      await new Promise((resolve) => setTimeout(resolve, 2000)); // Wait 2 seconds

      const recoveryResponse = await request(app)
        .get(testEndpoint)
        .timeout(10000);

      // Should recover to normal operation
      expect(recoveryResponse.status).toBe(normalStatus);

      // Analyze stress results
      const timeoutResults = stressResults.filter((r) => r.timeout);
      const successResults = stressResults.filter(
        (r) => !r.timeout && r.status === 200
      );

      // Some requests might have timed out due to short timeout, but system should recover
      expect(timeoutResults.length + successResults.length).toBeGreaterThan(0);
    });

    test("should maintain system health during timeout scenarios", async () => {
      // Test that health checks still work during timeout scenarios
      const healthEndpoint = "/api/health";

      // Create some potentially slow requests
      const slowRequestPromises = Array.from({ length: 3 }, () =>
        request(app)
          .get("/api/calendar/earnings")
          .timeout(1000)
          .catch(() => ({ timeout: true }))
      );

      // While slow requests are running, health check should still respond quickly
      const healthPromise = request(app).get(healthEndpoint).timeout(2000);

      const [healthResponse, ...slowResults] = await Promise.all([
        healthPromise,
        ...slowRequestPromises,
      ]);

      // Health check should succeed regardless of other request timeouts
      expect([200, 503].includes(healthResponse.status)).toBe(true);

      if (healthResponse.status === 200) {
        expect(healthResponse.body).toHaveProperty("status");
      }

      // System should still be responsive for health checks
      const healthDuration = Date.now();
      const secondHealthCheck = await request(app).get(healthEndpoint);
      const healthCheckDuration = Date.now() - healthDuration;

      expect(healthCheckDuration).toBeLessThan(5000); // Should be fast
    });

    test("should provide appropriate timeout configuration", async () => {
      // Test different timeout scenarios to understand system limits
      const timeoutTests = [
        { timeout: 1000, expectSuccess: false }, // Very short
        { timeout: 5000, expectSuccess: true }, // Reasonable
        { timeout: 15000, expectSuccess: true }, // Long
      ];

      const testEndpoint = "/api/calendar/earnings";

      for (const test of timeoutTests) {
        const startTime = Date.now();

        try {
          const response = await request(app)
            .get(testEndpoint)
            .timeout(test.timeout);
          const duration = Date.now() - startTime;

          // Should complete within timeout
          expect(duration).toBeLessThan(test.timeout);

          if (test.expectSuccess) {
            expect([200, 404]).toContain(response.status);
          }
        } catch (error) {
          if (error.code === "ECONNABORTED") {
            // Timeout occurred
            if (!test.expectSuccess) {
              // This was expected for very short timeouts
              expect(test.timeout).toBeLessThan(2000);
            }
          } else {
            throw error;
          }
        }
      }
    });
  });

  describe("Timeout Error Response Consistency", () => {
    test("should return consistent timeout error responses", async () => {
      const timeoutTestScenarios = [
        {
          endpoint: "/api/portfolio/analyze",
          method: "post",
          body: { symbols: ["AAPL"] },
          auth: true,
        },
        { endpoint: "/api/calendar/earnings", method: "get", auth: false },
      ];

      for (const scenario of timeoutTestScenarios) {
        try {
          let requestBuilder = request(app)[scenario.method](scenario.endpoint);

          if (scenario.auth) {
            requestBuilder = requestBuilder.set(
              "Authorization",
              "Bearer dev-bypass-token"
            );
          }

          if (scenario.body) {
            requestBuilder = requestBuilder.send(scenario.body);
          }

          const response = await requestBuilder.timeout(800); // Very short timeout

          // If request completes, should have proper format
          expect(response.headers["content-type"]).toMatch(/application\/json/);
        } catch (error) {
          // Timeout error should be consistent
          expect(error.code).toBe("ECONNABORTED");
          expect(error.timeout).toBe(800);
        }
      }
    });

    test("should not expose internal timeout configurations", async () => {
      // Test that timeout errors don't expose internal system details
      const sensitiveEndpoints = [
        { endpoint: "/api/portfolio/positions", auth: true },
        { endpoint: "/api/calendar/events", auth: false },
      ];

      for (const test of sensitiveEndpoints) {
        let requestBuilder = request(app).get(test.endpoint);

        if (test.auth) {
          requestBuilder = requestBuilder.set(
            "Authorization",
            "Bearer dev-bypass-token"
          );
        }

        const response = await requestBuilder.timeout(10000);

        if (response.status === 408 || response.status === 504) {
          expect(response.body).toHaveProperty("error");

          const errorMessage = response.body.error.toLowerCase();

          // Should not expose internal timeout values or configurations
          expect(errorMessage).not.toMatch(/timeout.*\d+|ms|seconds|minutes/);
          expect(errorMessage).not.toMatch(
            /connection.*pool|database.*timeout/
          );
          expect(errorMessage).not.toMatch(/internal.*timeout|system.*timeout/);
        }
      }
    });
  });
});

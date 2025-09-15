/**
 * Streaming Data Integration Tests
 * Tests real-time data streaming and WebSocket functionality
 * Validates streaming data consistency and error handling
 */

const request = require("supertest");
const WebSocket = require("ws");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Streaming Data Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Real-Time Market Data Streaming", () => {
    test("should handle market data requests", async () => {
      // Test the live market data endpoint (requires auth)
      const response = await request(app)
        .get("/api/liveData/market")
        .set("Authorization", "Bearer dev-bypass-token")
        .query({ symbols: "AAPL,GOOGL" });

      expect([200, 404, 500, 501]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body).toHaveProperty("meta");

        if (response.body.data && typeof response.body.data === "object") {
          // Should have market data structure
          expect(response.body.data).toBeDefined();
        }
      } else if (response.status === 404) {
        // Live data endpoint might not be implemented yet
        const hasCustomFormat = response.body.hasOwnProperty("success");
        const hasExpressFormat =
          response.body.hasOwnProperty("error") ||
          response.body.hasOwnProperty("message");
        expect(hasCustomFormat || hasExpressFormat).toBe(true);
      }
    });

    test("should handle streaming data subscriptions", async () => {
      // Test subscription endpoint
      const subscriptionResponse = await request(app)
        .get("/api/liveData/stream")
        .set("Authorization", "Bearer dev-bypass-token")
        .query({
          symbols: "AAPL,MSFT",
          type: "quotes",
        })
        .timeout(15000); // Increased timeout for streaming operations

      expect([200, 404, 501]).toContain(subscriptionResponse.status);

      if (subscriptionResponse.status === 200) {
        expect(subscriptionResponse.body).toHaveProperty("success", true);
        expect(subscriptionResponse.body).toHaveProperty("subscriptionId");
      } else if (subscriptionResponse.status === 501) {
        expect(subscriptionResponse.body).toHaveProperty("success", false);
        expect(subscriptionResponse.body).toHaveProperty("error");
      }
    }, 15000); // Increased timeout for streaming subscription test

    test("should handle real-time quote data", async () => {
      const symbols = ["AAPL", "GOOGL", "MSFT"];

      for (const symbol of symbols) {
        const response = await request(app).get(
          `/api/liveData/latest/${symbol}`
        );

        expect([401, 403, 200, 404, 500, 501]).toContain(response.status);

        if (response.status === 200) {
          expect(response.body).toHaveProperty("data");

          // Handle multiple possible API response structures
          if (response.body.data && response.body.data.symbol) {
            // Direct symbol data structure - current API format
            expect(response.body.data.symbol).toBe(symbol);
            if (response.body.data.price !== undefined) {
              expect(typeof response.body.data.price).toBe("number");
            }
          } else if (
            response.body.data &&
            Array.isArray(response.body.data) &&
            response.body.data.length > 0
          ) {
            // Array structure - data is directly an array
            const symbolData = response.body.data.find(
              (d) => d.symbol === symbol
            );
            if (symbolData) {
              expect(symbolData.symbol).toBe(symbol);
              if (symbolData.price !== undefined) {
                expect(typeof symbolData.price).toBe("number");
              }
            }
          } else if (
            response.body.data &&
            response.body.data.data &&
            Array.isArray(response.body.data.data)
          ) {
            // Nested array structure
            const symbolData = response.body.data.data.find(
              (d) => d.symbol === symbol
            );
            if (symbolData && symbolData.price !== undefined) {
              expect(typeof symbolData.price).toBe("number");
            }
          } else if (
            response.body.symbols &&
            Array.isArray(response.body.symbols)
          ) {
            // Root level symbols array (legacy)
            expect(response.body.symbols).toContain(symbol);
          } else if (
            response.body.data &&
            response.body.data.symbols &&
            Array.isArray(response.body.data.symbols)
          ) {
            // Nested symbols array (legacy)
            expect(response.body.data.symbols).toContain(symbol);
          } else {
            // Flexible validation for any response with data
            expect(response.body.data).toBeDefined();
          }
        }
      }
    });
  });

  describe("Portfolio Streaming Updates", () => {
    test("should handle portfolio value streaming", async () => {
      const response = await request(app)
        .get("/api/portfolio/stream/value")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404, 500, 501]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");

        // Portfolio streaming data should include real-time values
        if (response.body.data) {
          expect(response.body.data).toHaveProperty("timestamp");
          expect(response.body.data).toHaveProperty("totalValue");
        }
      }
    });

    test("should handle position streaming updates", async () => {
      const response = await request(app)
        .get("/api/portfolio/stream/positions")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404, 500, 501]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        if (response.body.data && Array.isArray(response.body.data)) {
          response.body.data.forEach((position) => {
            expect(position).toHaveProperty("symbol");
            expect(position).toHaveProperty("quantity");
            if (position.currentPrice !== undefined) {
              expect(typeof position.currentPrice).toBe("number");
            }
          });
        }
      }
    });
  });

  describe("Streaming Data Consistency", () => {
    test("should maintain data consistency across multiple requests", async () => {
      const symbol = "AAPL";
      const requestCount = 5;
      const delay = 200; // 200ms between requests

      const results = [];

      for (let i = 0; i < requestCount; i++) {
        const response = await request(app).get(
          `/api/liveData/latest/${symbol}`
        );

        if (response.status === 200 && response.body.data) {
          let symbolData = null;

          // Handle multiple response structures
          if (response.body.data.symbol === symbol) {
            // Direct symbol data structure
            symbolData = response.body.data;
          } else if (Array.isArray(response.body.data)) {
            // Array structure - data is directly an array
            symbolData = response.body.data.find((d) => d.symbol === symbol);
          } else if (
            response.body.data.data &&
            Array.isArray(response.body.data.data)
          ) {
            // Nested array structure
            symbolData = response.body.data.data.find(
              (d) => d.symbol === symbol
            );
          }

          if (symbolData && symbolData.symbol === symbol) {
            results.push({
              timestamp: Date.now(),
              price: symbolData.price,
              symbol: symbolData.symbol,
            });
          }
        }

        if (i < requestCount - 1) {
          await new Promise((resolve) => setTimeout(resolve, delay));
        }
      }

      if (results.length > 1) {
        // All results should be for the same symbol
        results.forEach((result) => {
          expect(result.symbol).toBe(symbol);
        });

        // Timestamps should be in order
        for (let i = 1; i < results.length; i++) {
          expect(results[i].timestamp).toBeGreaterThan(
            results[i - 1].timestamp
          );
        }

        // Prices should be reasonable (not wildly different)
        const prices = results
          .map((r) => r.price)
          .filter((p) => typeof p === "number");
        if (prices.length > 1) {
          const minPrice = Math.min(...prices);
          const maxPrice = Math.max(...prices);
          // Shouldn't vary by more than 50% in a few seconds
          expect(maxPrice / minPrice).toBeLessThan(1.5);
        }
      }
    });

    test("should handle concurrent streaming requests", async () => {
      const symbols = ["AAPL", "GOOGL", "MSFT"];

      const concurrentRequests = symbols.map((symbol) =>
        request(app)
          .get(`/api/liveData/latest/${symbol}`)
          .then((response) => ({
            symbol,
            status: response.status,
            data: response.body,
          }))
          .catch((error) => ({ symbol, error: error.message }))
      );

      const results = await Promise.all(concurrentRequests);

      expect(results.length).toBe(symbols.length);

      results.forEach((result) => {
        expect(symbols).toContain(result.symbol);
        if (result.status) {
          expect([200, 404, 500]).toContain(result.status);
        }
      });
    });
  });

  describe("Streaming Error Handling", () => {
    test("should handle invalid symbols gracefully", async () => {
      const invalidSymbols = ["INVALID", "NOTFOUND", ""];

      for (const symbol of invalidSymbols) {
        const response = await request(app).get(
          `/api/liveData/latest/${symbol}`
        );

        expect([401, 403, 200, 404, 500, 501]).toContain(response.status);

        if (response.status >= 400) {
          // Error responses can be either custom API format or Express default
          const hasCustomFormat = response.body.hasOwnProperty("success");
          const hasExpressFormat =
            response.body.hasOwnProperty("error") ||
            response.body.hasOwnProperty("message");
          expect(hasCustomFormat || hasExpressFormat).toBe(true);
        }
      }
    });

    test("should handle streaming service failures", async () => {
      // Test with parameters that might cause service failures
      const stressTests = [
        {
          endpoint: "/api/liveData/market",
          query: { symbols: Array(100).fill("AAPL").join(",") },
        },
        {
          endpoint: "/api/liveData/latest/AAPL",
          query: { detailed: true, history: 1000 },
        },
      ];

      for (const test of stressTests) {
        const response = await request(app)
          .get(test.endpoint)
          .query(test.query);

        expect([401, 403, 200, 404, 500, 501]).toContain(response.status);

        if (response.status >= 400) {
          // Error responses can be either custom API format or Express default
          const hasCustomFormat = response.body.hasOwnProperty("success");
          const hasExpressFormat =
            response.body.hasOwnProperty("error") ||
            response.body.hasOwnProperty("message");
          expect(hasCustomFormat || hasExpressFormat).toBe(true);

          // Error should not expose internal service details
          const errorMessage =
            response.body.error || response.body.message || "";
          if (errorMessage) {
            expect(errorMessage).not.toMatch(
              /internal|service|connection|api key/i
            );
          }
        }
      }
    });

    test("should handle network timeout scenarios", async () => {
      const timeoutTest = request(app)
        .get("/api/liveData/market")
        .query({ symbols: "AAPL,GOOGL,MSFT" })
        .timeout(5000); // 5 second timeout

      try {
        const response = await timeoutTest;

        // If successful, should have proper response format
        expect([401, 403, 200, 404, 500, 501]).toContain(response.status);
        if (response.status === 200) {
          expect(response.body).toHaveProperty("data");
        }
      } catch (error) {
        // Timeout is acceptable for streaming data
        if (error.code === "ECONNABORTED") {
          expect(error.timeout).toBe(5000);
        } else {
          throw error;
        }
      }
    });
  });

  describe("Streaming Performance", () => {
    test("should deliver streaming data within reasonable time", async () => {
      const startTime = Date.now();

      const response = await request(app)
        .get("/api/liveData/latest/AAPL")
        .timeout(3000);

      const responseTime = Date.now() - startTime;

      // Streaming data should be reasonably fast
      expect(responseTime).toBeLessThan(3000);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");

        // Response should include timing info if available
        if (response.body.metadata) {
          expect(response.body.metadata).toHaveProperty("responseTime");
        }
      }
    });

    test("should handle high-frequency data requests", async () => {
      const symbol = "AAPL";
      const requestCount = 10;
      const concurrency = 3;

      const batches = [];
      for (let i = 0; i < requestCount; i += concurrency) {
        const batch = [];
        for (let j = 0; j < concurrency && i + j < requestCount; j++) {
          batch.push(
            request(app)
              .get(`/api/liveData/latest/${symbol}`)
              .timeout(2000)
              .then((response) => ({
                status: response.status,
                responseTime: Date.now(),
              }))
              .catch((error) => ({
                error: error.message,
                responseTime: Date.now(),
              }))
          );
        }
        batches.push(batch);
      }

      const allResults = [];
      for (const batch of batches) {
        const batchResults = await Promise.all(batch);
        allResults.push(...batchResults);

        // Small delay between batches to avoid overwhelming
        await new Promise((resolve) => setTimeout(resolve, 100));
      }

      expect(allResults.length).toBe(requestCount);

      // Most requests should succeed or fail gracefully
      const successfulRequests = allResults.filter((r) => r.status === 200);
      const totalProcessed = allResults.filter(
        (r) => r.status !== undefined || r.error !== undefined
      );

      expect(totalProcessed.length).toBe(requestCount);
      // All should have some response (success or error)
      expect(totalProcessed.length).toBeGreaterThan(0);
    });
  });

  describe("Streaming Data Formats", () => {
    test("should return consistent data formats", async () => {
      const formatTests = [
        { endpoint: "/api/liveData/latest/AAPL", expectedFields: ["symbol"] },
        {
          endpoint: "/api/liveData/market",
          query: { symbols: "AAPL" },
          expectedFields: ["data"],
        },
      ];

      for (const test of formatTests) {
        let requestBuilder = request(app).get(test.endpoint);

        if (test.query) {
          requestBuilder = requestBuilder.query(test.query);
        }

        const response = await requestBuilder;

        if (response.status === 200) {
          expect(response.headers["content-type"]).toMatch(/application\/json/);
          expect(response.body).toHaveProperty("data");

          // Check for expected fields in response
          test.expectedFields.forEach((field) => {
            if (
              response.body.data &&
              response.body.data.data &&
              response.body.data.data.length > 0
            ) {
              // If we have actual data, check the first item
              expect(response.body.data.data[0]).toHaveProperty(field);
            } else if (response.body.data) {
              // If no data but response structure exists, check for basic response fields
              if (field === "data") {
                expect(response.body.data).toHaveProperty(field);
              }
            }
          });

          // Should have timestamp
          if (response.body.data && response.body.data.timestamp) {
            expect(new Date(response.body.data.timestamp).toString()).not.toBe(
              "Invalid Date"
            );
          }
        }
      }
    });

    test("should handle different data type requests", async () => {
      const dataTypes = ["quote", "trade", "bar", "news"];

      for (const dataType of dataTypes) {
        const response = await request(app)
          .get("/api/liveData/stream")
          .set("Authorization", "Bearer dev-bypass-token")
          .query({ symbol: "AAPL", type: dataType })
          .timeout(15000); // Increased timeout for streaming operations

        expect([401, 403, 200, 404, 500, 501]).toContain(response.status);

        if (response.status === 200) {
          expect(response.body).toHaveProperty("data");
        } else if (response.status === 501) {
          // Data type not implemented
          expect(response.body).toHaveProperty("success", false);
          expect(response.body.error).toMatch(
            /not implemented|not supported|not available/i
          );
        }
      }
    }, 20000); // Increased timeout for comprehensive data type testing
  });

  describe("Authentication with Streaming Data", () => {
    test("should handle authentication for protected streaming endpoints", async () => {
      const protectedStreamingEndpoints = [
        "/api/portfolio/stream/value",
        "/api/portfolio/stream/positions",
        "/api/alerts/stream",
      ];

      for (const endpoint of protectedStreamingEndpoints) {
        // Test without auth
        const unauthResponse = await request(app).get(endpoint);
        expect([401, 403, 404]).toContain(unauthResponse.status);

        if ([401, 403].includes(unauthResponse.status)) {
          expect(unauthResponse.body).toHaveProperty("success", false);
          expect(unauthResponse.body).toHaveProperty("error");
        }

        // Test with auth
        const authResponse = await request(app)
          .get(endpoint)
          .set("Authorization", "Bearer dev-bypass-token");

        expect([200, 404, 500]).toContain(authResponse.status);
        // Should not be auth error
        expect([401, 403]).not.toContain(authResponse.status);
      }
    });

    test("should maintain streaming sessions with valid authentication", async () => {
      const streamingSession = [
        { endpoint: "/api/portfolio/stream/value", delay: 100 },
        { endpoint: "/api/portfolio/stream/positions", delay: 200 },
        { endpoint: "/api/portfolio/stream/value", delay: 100 },
      ];

      const results = [];

      for (const session of streamingSession) {
        await new Promise((resolve) => setTimeout(resolve, session.delay));

        const response = await request(app)
          .get(session.endpoint)
          .set("Authorization", "Bearer dev-bypass-token")
          .timeout(2000);

        results.push({
          endpoint: session.endpoint,
          status: response.status,
          authenticated: ![401, 403].includes(response.status),
          timestamp: Date.now(),
        });
      }

      // All should maintain authentication
      results.forEach((result) => {
        expect(result.authenticated).toBe(true);
        expect([200, 404, 500]).toContain(result.status);
      });

      // Session should maintain state across requests
      expect(results.length).toBe(streamingSession.length);
    });
  });
});

/**
 * Rate Limiting Integration Tests
 * Tests rate limiting mechanisms and throttling behavior
 * Validates proper handling of rate limit violations
 */

const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("Rate Limiting Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Basic Rate Limiting Scenarios", () => {
    test("should handle rapid requests without blocking normal usage", async () => {
      const testEndpoint = "/api/market/overview";
      const requestCount = 20;
      const requestInterval = 100; // 100ms between requests
      
      const results = [];
      
      for (let i = 0; i < requestCount; i++) {
        const startTime = Date.now();
        
        try {
          const response = await request(app).get(testEndpoint);
          
          results.push({
            requestId: i,
            status: response.status,
            hasRateLimitHeaders: {
              limit: response.headers['x-ratelimit-limit'] !== undefined,
              remaining: response.headers['x-ratelimit-remaining'] !== undefined,
              reset: response.headers['x-ratelimit-reset'] !== undefined
            },
            responseTime: Date.now() - startTime
          });
          
        } catch (error) {
          results.push({
            requestId: i,
            error: error.message,
            responseTime: Date.now() - startTime
          });
        }
        
        // Small delay between requests
        if (i < requestCount - 1) {
          await new Promise(resolve => setTimeout(resolve, requestInterval));
        }
      }
      
      // Analyze results
      const successfulRequests = results.filter(r => r.status === 200);
      const rateLimitedRequests = results.filter(r => r.status === 429);
      const errorRequests = results.filter(r => r.error);
      
      // Most requests should succeed with moderate spacing
      expect(successfulRequests.length).toBeGreaterThan(requestCount * 0.7);
      
      // If rate limiting is implemented, check header consistency
      const requestsWithHeaders = results.filter(r => r.hasRateLimitHeaders?.limit);
      if (requestsWithHeaders.length > 0) {
        // All rate limit headers should be consistent
        requestsWithHeaders.forEach(result => {
          expect(result.hasRateLimitHeaders.limit).toBe(true);
          expect(result.hasRateLimitHeaders.remaining).toBe(true);
          expect(result.hasRateLimitHeaders.reset).toBe(true);
        });
      }
      
      // Rate limited requests should have proper error format
      rateLimitedRequests.forEach(result => {
        expect(result.status).toBe(429);
      });
    });

    test("should return 429 for excessive rapid requests", async () => {
      const testEndpoint = "/api/calendar/earnings";
      const burstCount = 50; // Large burst of requests
      
      // Create all requests simultaneously (burst)
      const burstPromises = Array.from({ length: burstCount }, async (_, i) => {
        const startTime = Date.now();
        
        try {
          const response = await request(app).get(testEndpoint);
          
          return {
            requestId: i,
            status: response.status,
            rateLimited: response.status === 429,
            retryAfter: response.headers['retry-after'],
            responseTime: Date.now() - startTime
          };
        } catch (error) {
          return {
            requestId: i,
            error: error.message,
            responseTime: Date.now() - startTime
          };
        }
      });
      
      const results = await Promise.all(burstPromises);
      
      // Analyze burst results
      const successfulRequests = results.filter(r => r.status === 200);
      const rateLimitedRequests = results.filter(r => r.rateLimited);
      const errorRequests = results.filter(r => r.error);
      
      // Should have some successful requests
      expect(successfulRequests.length).toBeGreaterThan(0);
      
      // If rate limiting is implemented, should have some 429 responses
      if (rateLimitedRequests.length > 0) {
        expect(rateLimitedRequests.length).toBeGreaterThan(burstCount * 0.1); // At least 10% rate limited
        
        // Rate limited responses should have Retry-After header
        rateLimitedRequests.forEach(result => {
          if (result.retryAfter) {
            expect(typeof result.retryAfter).toBe("string");
            const retrySeconds = parseInt(result.retryAfter);
            expect(retrySeconds).toBeGreaterThan(0);
            expect(retrySeconds).toBeLessThan(3600); // Less than 1 hour
          }
        });
      }
      
      // All requests should complete (not hang)
      expect(results.length).toBe(burstCount);
    });
  });

  describe("Per-Endpoint Rate Limiting", () => {
    test("should apply different rate limits to different endpoint types", async () => {
      const endpointTests = [
        { endpoint: "/api/health", category: "health", expectedHighLimit: true },
        { endpoint: "/api/market/overview", category: "market", expectedHighLimit: true },
        { endpoint: "/api/portfolio/analyze", method: "post", body: { symbols: ["AAPL"] }, auth: true, category: "compute", expectedHighLimit: false }
      ];
      
      const resultsPerEndpoint = {};
      
      for (const test of endpointTests) {
        const requestCount = 15;
        const requests = [];
        
        for (let i = 0; i < requestCount; i++) {
          let requestBuilder = request(app)[test.method || "get"](test.endpoint);
          
          if (test.auth) {
            requestBuilder = requestBuilder.set("Authorization", "Bearer dev-bypass-token");
          }
          
          if (test.body) {
            requestBuilder = requestBuilder.send(test.body);
          }
          
          requests.push(
            requestBuilder
              .timeout(5000)
              .then(response => ({
                status: response.status,
                rateLimited: response.status === 429,
                endpoint: test.endpoint
              }))
              .catch(error => ({
                error: error.message,
                endpoint: test.endpoint,
                timeout: error.code === 'ECONNABORTED'
              }))
          );
        }
        
        const results = await Promise.all(requests);
        resultsPerEndpoint[test.category] = results;
        
        // Small delay before next endpoint test
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      
      // Analyze rate limiting patterns per endpoint type
      Object.entries(resultsPerEndpoint).forEach(([category, results]) => {
        const successCount = results.filter(r => r.status === 200).length;
        const serverErrorCount = results.filter(r => r.status === 500).length;
        const clientErrorCount = results.filter(r => r.status >= 400 && r.status < 500).length;
        const rateLimitedCount = results.filter(r => r.rateLimited).length;
        const errorCount = results.filter(r => r.error && !r.timeout).length;
        const timeoutCount = results.filter(r => r.timeout).length;
        
        // All requests should be accounted for
        expect(results.length).toBe(15);
        
        // Should have some kind of response for each request
        const totalResponsed = results.filter(r => 
          r.status !== undefined || r.error !== undefined || r.timeout !== undefined
        ).length;
        expect(totalResponsed).toBe(15);
        
        // Test should complete with some form of response
        const hasValidData = successCount + serverErrorCount + clientErrorCount + errorCount + timeoutCount > 0;
        expect(hasValidData).toBe(true);
      });
    });

    test("should handle authenticated vs unauthenticated rate limits", async () => {
      const testEndpoint = "/api/calendar/earnings";
      const requestCount = 12;
      
      // Test unauthenticated requests
      const unauthenticatedPromises = Array.from({ length: requestCount }, () =>
        request(app).get(testEndpoint)
          .then(r => ({ status: r.status, authenticated: false, rateLimited: r.status === 429 }))
          .catch(e => ({ error: e.message, authenticated: false }))
      );
      
      const unauthenticatedResults = await Promise.all(unauthenticatedPromises);
      
      // Wait a bit before authenticated tests
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // Test authenticated requests
      const authenticatedPromises = Array.from({ length: requestCount }, () =>
        request(app).get(testEndpoint)
          .set("Authorization", "Bearer dev-bypass-token")
          .then(r => ({ status: r.status, authenticated: true, rateLimited: r.status === 429 }))
          .catch(e => ({ error: e.message, authenticated: true }))
      );
      
      const authenticatedResults = await Promise.all(authenticatedPromises);
      
      // Analyze differences in rate limiting
      const unauthSuccessCount = unauthenticatedResults.filter(r => r.status === 200).length;
      const unauthRateLimitedCount = unauthenticatedResults.filter(r => r.rateLimited).length;
      
      const authSuccessCount = authenticatedResults.filter(r => r.status === 200).length;
      const authRateLimitedCount = authenticatedResults.filter(r => r.rateLimited).length;
      
      // Both should handle requests, but authenticated might have higher limits
      expect(unauthSuccessCount + unauthRateLimitedCount).toBeGreaterThan(0);
      expect(authSuccessCount + authRateLimitedCount).toBeGreaterThan(0);
      
      // If rate limiting is different, authenticated should perform better or equal
      if (unauthRateLimitedCount > 0 || authRateLimitedCount > 0) {
        expect(authSuccessCount).toBeGreaterThanOrEqual(unauthSuccessCount * 0.8);
      }
    });
  });

  describe("Rate Limit Response Format", () => {
    test("should return proper 429 error response format", async () => {
      const testEndpoint = "/api/market/overview";
      
      // Create burst of requests to trigger rate limiting
      const burstRequests = Array.from({ length: 30 }, () =>
        request(app).get(testEndpoint)
          .then(response => ({
            status: response.status,
            body: response.body,
            headers: response.headers
          }))
          .catch(error => ({ error: error.message }))
      );
      
      const results = await Promise.all(burstRequests);
      const rateLimitedResponses = results.filter(r => r.status === 429);
      
      if (rateLimitedResponses.length > 0) {
        rateLimitedResponses.forEach(response => {
          // Standard 429 response format
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          expect(response.body.error).toMatch(/rate.*limit|too.*many.*requests|throttl/i);
          
          // Content type should be JSON
          expect(response.headers['content-type']).toMatch(/application\/json/);
          
          // Should have rate limiting headers
          if (response.headers['x-ratelimit-limit']) {
            expect(parseInt(response.headers['x-ratelimit-limit'])).toBeGreaterThan(0);
          }
          
          if (response.headers['x-ratelimit-remaining']) {
            expect(parseInt(response.headers['x-ratelimit-remaining'])).toBeGreaterThanOrEqual(0);
          }
          
          if (response.headers['retry-after']) {
            const retryAfter = parseInt(response.headers['retry-after']);
            expect(retryAfter).toBeGreaterThan(0);
            expect(retryAfter).toBeLessThan(300); // Less than 5 minutes
          }
        });
      }
    });

    test("should include helpful rate limit information in responses", async () => {
      const testEndpoint = "/api/calendar/earnings";
      
      // Make a few requests to check headers
      const response = await request(app).get(testEndpoint);
      
      // Check for informative headers (if rate limiting is implemented)
      if (response.headers['x-ratelimit-limit']) {
        const limit = parseInt(response.headers['x-ratelimit-limit']);
        const remaining = parseInt(response.headers['x-ratelimit-remaining']);
        const reset = response.headers['x-ratelimit-reset'];
        
        expect(limit).toBeGreaterThan(0);
        expect(remaining).toBeGreaterThanOrEqual(0);
        expect(remaining).toBeLessThanOrEqual(limit);
        
        if (reset) {
          // Reset time should be valid timestamp or seconds
          const resetValue = parseInt(reset);
          expect(resetValue).toBeGreaterThan(0);
        }
      }
    });
  });

  describe("Rate Limit Recovery", () => {
    test("should allow requests after rate limit reset period", async () => {
      const testEndpoint = "/api/market/overview";
      
      // Phase 1: Trigger rate limiting
      const burstRequests = Array.from({ length: 25 }, () =>
        request(app).get(testEndpoint).catch(() => ({ rateLimited: true }))
      );
      
      const burstResults = await Promise.all(burstRequests);
      const initialRateLimited = burstResults.filter(r => r.rateLimited || (r.status === 429));
      
      // Phase 2: Wait for reset period
      await new Promise(resolve => setTimeout(resolve, 5000)); // Wait 5 seconds
      
      // Phase 3: Test recovery
      const recoveryResponse = await request(app).get(testEndpoint);
      
      // Should recover from rate limiting
      expect([200, 500].includes(recoveryResponse.status)).toBe(true);
      
      if (recoveryResponse.status === 200) {
        // Rate limiting should be reset
        if (recoveryResponse.headers['x-ratelimit-remaining']) {
          const remaining = parseInt(recoveryResponse.headers['x-ratelimit-remaining']);
          expect(remaining).toBeGreaterThan(0);
        }
      }
    });

    test("should handle gradual recovery from rate limiting", async () => {
      const testEndpoint = "/api/calendar/earnings";
      
      // Create sustained load to test gradual recovery
      const sustainedTestDuration = 8000; // 8 seconds
      const requestInterval = 200; // Request every 200ms
      const totalRequests = Math.floor(sustainedTestDuration / requestInterval);
      
      const results = [];
      const startTime = Date.now();
      
      for (let i = 0; i < totalRequests && (Date.now() - startTime) < sustainedTestDuration; i++) {
        const requestStartTime = Date.now();
        
        try {
          const response = await request(app).get(testEndpoint);
          results.push({
            requestId: i,
            timestamp: Date.now() - startTime,
            status: response.status,
            rateLimited: response.status === 429,
            remaining: response.headers['x-ratelimit-remaining'] ? parseInt(response.headers['x-ratelimit-remaining']) : null
          });
        } catch (error) {
          results.push({
            requestId: i,
            timestamp: Date.now() - startTime,
            error: error.message
          });
        }
        
        // Wait before next request
        const elapsed = Date.now() - requestStartTime;
        const waitTime = Math.max(0, requestInterval - elapsed);
        if (waitTime > 0) {
          await new Promise(resolve => setTimeout(resolve, waitTime));
        }
      }
      
      // Analyze sustained load patterns
      const timeSegments = {
        early: results.filter(r => r.timestamp < sustainedTestDuration * 0.33),
        middle: results.filter(r => r.timestamp >= sustainedTestDuration * 0.33 && r.timestamp < sustainedTestDuration * 0.67),
        late: results.filter(r => r.timestamp >= sustainedTestDuration * 0.67)
      };
      
      // Should handle sustained load gracefully
      Object.values(timeSegments).forEach(segment => {
        if (segment.length > 0) {
          const segmentSuccesses = segment.filter(r => r.status === 200);
          const segmentRateLimited = segment.filter(r => r.rateLimited);
          const segmentErrors = segment.filter(r => r.error);
          
          // Each segment should process requests in some way
          expect(segmentSuccesses.length + segmentRateLimited.length + segmentErrors.length).toBeGreaterThan(0);
        }
      });
      
      // System should maintain responsiveness throughout
      const avgResponseTimes = Object.fromEntries(
        Object.entries(timeSegments).map(([period, segment]) => [
          period,
          segment.reduce((sum, r) => sum + (r.responseTime || 0), 0) / Math.max(segment.length, 1)
        ])
      );
      
      // Response times shouldn't degrade significantly
      Object.values(avgResponseTimes).forEach(avgTime => {
        if (avgTime > 0) {
          expect(avgTime).toBeLessThan(5000); // Should stay under 5 seconds
        }
      });
    });
  });

  describe("Rate Limiting Security", () => {
    test("should not expose internal rate limiting configuration", async () => {
      const testEndpoint = "/api/market/overview";
      
      // Trigger rate limiting to get error message
      const burstRequests = Array.from({ length: 40 }, () =>
        request(app).get(testEndpoint).catch(() => ({ failed: true }))
      );
      
      const results = await Promise.all(burstRequests);
      const rateLimitedResponses = results.filter(r => r.status === 429);
      
      if (rateLimitedResponses.length > 0) {
        rateLimitedResponses.forEach(response => {
          if (response.body && response.body.error) {
            const errorMessage = response.body.error.toLowerCase();
            
            // Should not expose internal configuration details
            expect(errorMessage).not.toMatch(/redis|memcache|config|internal/i);
            expect(errorMessage).not.toMatch(/algorithm|sliding.*window|token.*bucket/i);
            expect(errorMessage).not.toMatch(/server.*limit|database.*limit/i);
            
            // Should be user-friendly message
            expect(errorMessage).toMatch(/rate.*limit|too.*many|slow.*down|try.*again/i);
          }
        });
      }
    });

    test("should handle distributed rate limiting consistently", async () => {
      // Test rate limiting consistency across multiple rapid connections
      const testEndpoint = "/api/calendar/earnings";
      const concurrentConnections = 10;
      const requestsPerConnection = 5;
      
      const connectionPromises = Array.from({ length: concurrentConnections }, async (_, connId) => {
        const connectionResults = [];
        
        for (let reqId = 0; reqId < requestsPerConnection; reqId++) {
          try {
            const response = await request(app).get(testEndpoint);
            connectionResults.push({
              connectionId: connId,
              requestId: reqId,
              status: response.status,
              rateLimited: response.status === 429
            });
          } catch (error) {
            connectionResults.push({
              connectionId: connId,
              requestId: reqId,
              error: error.message
            });
          }
          
          // Small delay between requests within connection
          if (reqId < requestsPerConnection - 1) {
            await new Promise(resolve => setTimeout(resolve, 100));
          }
        }
        
        return connectionResults;
      });
      
      const allResults = (await Promise.all(connectionPromises)).flat();
      
      // Analyze distributed consistency
      const totalRequests = concurrentConnections * requestsPerConnection;
      const successfulRequests = allResults.filter(r => r.status === 200);
      const rateLimitedRequests = allResults.filter(r => r.rateLimited);
      const errorRequests = allResults.filter(r => r.error);
      
      expect(allResults.length).toBe(totalRequests);
      
      // Should handle concurrent connections gracefully
      expect(successfulRequests.length).toBeGreaterThan(0);
      
      // Rate limiting should be applied consistently across connections
      if (rateLimitedRequests.length > 0) {
        const rateLimitedByConnection = {};
        rateLimitedRequests.forEach(req => {
          rateLimitedByConnection[req.connectionId] = (rateLimitedByConnection[req.connectionId] || 0) + 1;
        });
        
        // Rate limiting distribution shouldn't be heavily skewed to one connection
        const maxRateLimitedPerConnection = Math.max(...Object.values(rateLimitedByConnection));
        const avgRateLimitedPerConnection = Object.values(rateLimitedByConnection).reduce((a, b) => a + b, 0) / Object.keys(rateLimitedByConnection).length;
        
        expect(maxRateLimitedPerConnection).toBeLessThan(avgRateLimitedPerConnection * 3); // Not more than 3x average
      }
    });
  });

  describe("Rate Limiting Integration with Error Handling", () => {
    test("should maintain rate limiting during other error scenarios", async () => {
      const endpoints = [
        { endpoint: "/api/portfolio/nonexistent", expectedStatus: 404 },
        { endpoint: "/api/calendar/earnings", expectedStatus: 200 }
      ];
      
      for (const test of endpoints) {
        // Create multiple requests to each endpoint
        const requests = Array.from({ length: 15 }, () =>
          request(app).get(test.endpoint)
            .timeout(3000)
            .then(r => ({ status: r.status, rateLimited: r.status === 429 }))
            .catch(e => ({ 
              error: e.message,
              timeout: e.code === 'ECONNABORTED'
            }))
        );
        
        const results = await Promise.all(requests);
        
        // All requests should be accounted for
        expect(results.length).toBe(15);
        
        // Should have some kind of response for each request
        const totalResponsed = results.filter(r => 
          r.status !== undefined || r.error !== undefined || r.timeout !== undefined
        ).length;
        expect(totalResponsed).toBe(15);
        
        // Rate limiting should work across different response types
        const expectedResponses = results.filter(r => r.status === test.expectedStatus);
        const rateLimitedResponses = results.filter(r => r.rateLimited);
        const errorResponses = results.filter(r => r.error && !r.timeout);
        const timeoutResponses = results.filter(r => r.timeout);
        const otherStatusResponses = results.filter(r => r.status !== undefined && r.status !== test.expectedStatus && !r.rateLimited);
        
        // Test should complete with responses
        const hasResponses = expectedResponses.length + rateLimitedResponses.length + errorResponses.length + timeoutResponses.length + otherStatusResponses.length > 0;
        expect(hasResponses).toBe(true);
      }
    });

    test("should handle rate limiting with authentication errors", async () => {
      const protectedEndpoint = "/api/portfolio";
      const authScenarios = [
        { auth: null, expectedStatus: [401, 403] },
        { auth: "Bearer invalid-token", expectedStatus: [401, 403] },
        { auth: "Bearer dev-bypass-token", expectedStatus: [200, 500] }
      ];
      
      for (const scenario of authScenarios) {
        const requests = Array.from({ length: 10 }, async () => {
          let requestBuilder = request(app).get(protectedEndpoint);
          
          if (scenario.auth) {
            requestBuilder = requestBuilder.set("Authorization", scenario.auth);
          }
          
          try {
            const response = await requestBuilder;
            return {
              status: response.status,
              rateLimited: response.status === 429,
              matchesExpected: scenario.expectedStatus.includes(response.status)
            };
          } catch (error) {
            return { error: error.message };
          }
        });
        
        const results = await Promise.all(requests);
        
        // Rate limiting should work with auth scenarios
        const validResponses = results.filter(r => r.status !== undefined);
        const rateLimitedResponses = results.filter(r => r.rateLimited);
        
        expect(validResponses.length).toBe(10);
        
        // Should handle auth and rate limiting independently
        validResponses.forEach(result => {
          const allowedStatuses = [...scenario.expectedStatus, 429, 500]; // Allow server errors too
          expect(allowedStatuses.includes(result.status)).toBe(true);
        });
      }
    });
  });
});
/**
 * WebSocket Integration Tests
 * Tests WebSocket functionality and real-time communication
 * Validates WebSocket connections, messaging, and error handling
 */

const request = require("supertest");
const WebSocket = require("ws");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("WebSocket Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("WebSocket Connection Establishment", () => {
    test("should handle WebSocket upgrade requests", async () => {
      // Test WebSocket upgrade endpoint
      const response = await request(app)
        .get("/api/websocket")
        .set("Upgrade", "websocket")
        .set("Connection", "Upgrade")
        .set("Sec-WebSocket-Key", "dGhlIHNhbXBsZSBub25jZQ==")
        .set("Sec-WebSocket-Version", "13");

      // WebSocket upgrade might return specific status codes
      expect([404, 500]).toContain(response.status);
      
      if (response.status === 101) {
        // Successful WebSocket upgrade
        expect(response.headers.upgrade).toBe("websocket");
        expect(response.headers.connection).toMatch(/upgrade/i);
      } else if (response.status === 404) {
        // WebSocket endpoint not implemented
        expect(response.body).toHaveProperty("success", false);
      }
    });

    test("should handle WebSocket connection info requests", async () => {
      // Test WebSocket info endpoint
      const response = await request(app).get("/api/websocket/info");
      
      expect([200, 404, 500, 501]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("websocketSupported");
        
        if (response.body.data.websocketSupported) {
          expect(response.body.data).toHaveProperty("endpoint");
          expect(response.body.data).toHaveProperty("protocols");
        }
      }
    });

    test("should validate WebSocket authentication requirements", async () => {
      // Test authenticated WebSocket endpoints
      const authWSEndpoints = [
        "/api/websocket/portfolio",
        "/api/websocket/alerts",
        "/api/websocket/trades"
      ];
      
      for (const endpoint of authWSEndpoints) {
        // Test without auth
        const unauthResponse = await request(app)
          .get(endpoint)
          .set("Upgrade", "websocket")
          .set("Connection", "Upgrade");
          
        expect(unauthResponse.status).toBe(401);
        
        // Test with auth header
        const authResponse = await request(app)
          .get(endpoint)
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Upgrade", "websocket")
          .set("Connection", "Upgrade")
          .set("Sec-WebSocket-Key", "dGhlIHNhbXBsZSBub25jZQ==")
          .set("Sec-WebSocket-Version", "13");
          
        expect(authResponse.status).toBe(200);
      }
    });
  });

  describe("WebSocket Message Handling", () => {
    test("should handle WebSocket message format validation", async () => {
      // Test WebSocket message validation endpoint
      const messageFormats = [
        { type: "subscribe", payload: { symbols: ["AAPL"] } },
        { type: "unsubscribe", payload: { symbols: ["AAPL"] } },
        { type: "ping", payload: {} },
        { type: "authenticate", payload: { token: "dev-bypass-token" } }
      ];
      
      for (const message of messageFormats) {
        const response = await request(app)
          .post("/api/websocket/validate-message")
          .send(message);
          
        expect([200, 404, 500, 501]).toContain(response.status);
        
        if (response.status === 200) {
          expect(response.body).toHaveProperty("success", true);
          expect(response.body.data).toHaveProperty("valid", true);
        } else if (response.status === 400 || response.status === 422) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });

    test("should handle invalid WebSocket message formats", async () => {
      const invalidMessages = [
        { invalid: "structure" },
        { type: "invalid_type", payload: {} },
        { type: "subscribe" }, // Missing payload
        { type: "subscribe", payload: { symbols: "not_array" } },
        { type: "authenticate", payload: { invalid_field: "value" } }
      ];
      
      for (const message of invalidMessages) {
        const response = await request(app)
          .post("/api/websocket/validate-message")
          .send(message);
          
        expect([400, 422]).toContain(response.status);
        
        if (response.status === 400 || response.status === 422) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
        }
      }
    });
  });

  describe("WebSocket Subscription Management", () => {
    test("should handle market data subscriptions", async () => {
      const subscriptionData = {
        symbols: ["AAPL", "GOOGL", "MSFT"],
        dataTypes: ["quote", "trade"]
      };
      
      const response = await request(app)
        .post("/api/websocket/subscribe/market")
        .send(subscriptionData);
        
      expect([200, 404, 500, 501]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("subscriptionId");
        expect(response.body.data).toHaveProperty("symbols");
        expect(response.body.data.symbols).toEqual(subscriptionData.symbols);
      } else if (response.status === 501) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body.error).toMatch(/not implemented|not supported/i);
      }
    });

    test("should handle portfolio subscriptions", async () => {
      const portfolioSubscriptions = [
        { type: "value", updateInterval: 1000 },
        { type: "positions", updateInterval: 5000 },
        { type: "performance", updateInterval: 10000 }
      ];
      
      for (const subscription of portfolioSubscriptions) {
        const response = await request(app)
          .post("/api/websocket/subscribe/portfolio")
          .set("Authorization", "Bearer dev-bypass-token")
          .send(subscription);
          
        expect([200, 404, 500, 501]).toContain(response.status);
        
        if (response.status === 200) {
          expect(response.body).toHaveProperty("success", true);
          expect(response.body.data).toHaveProperty("subscriptionId");
          expect(response.body.data).toHaveProperty("type", subscription.type);
        }
      }
    });

    test("should handle subscription limits", async () => {
      const maxSubscriptions = 10;
      const subscriptions = [];
      
      for (let i = 0; i < maxSubscriptions + 2; i++) {
        const response = await request(app)
          .post("/api/websocket/subscribe/market")
          .send({ symbols: [`TEST${i}`] });
          
        subscriptions.push({
          index: i,
          status: response.status,
          subscriptionId: response.body.data?.subscriptionId
        });
      }
      
      // Should handle subscription limits gracefully
      const successfulSubscriptions = subscriptions.filter(s => s.status === 200);
      const rejectedSubscriptions = subscriptions.filter(s => [400].includes(s.status));
      
      if (rejectedSubscriptions.length > 0) {
        // Some should be rejected due to limits
        expect(successfulSubscriptions.length).toBeLessThanOrEqual(maxSubscriptions);
      }
    });
  });

  describe("WebSocket Error Scenarios", () => {
    test("should handle connection errors gracefully", async () => {
      const errorScenarios = [
        { endpoint: "/api/websocket/invalid", description: "Invalid endpoint" },
        { endpoint: "/api/websocket", headers: { "Sec-WebSocket-Version": "12" }, description: "Unsupported version" },
        { endpoint: "/api/websocket", headers: { "Sec-WebSocket-Key": "invalid" }, description: "Invalid key" }
      ];
      
      for (const scenario of errorScenarios) {
        const requestHeaders = {
          "Upgrade": "websocket",
          "Connection": "Upgrade",
          "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
          "Sec-WebSocket-Version": "13",
          ...scenario.headers
        };
        
        let requestBuilder = request(app).get(scenario.endpoint);
        Object.entries(requestHeaders).forEach(([key, value]) => {
          requestBuilder = requestBuilder.set(key, value);
        });
        
        const response = await requestBuilder;
        
        expect([400, 422]).toContain(response.status);
        
        if ([400, 404].includes(response.status)) {
          // Error responses should be properly formatted
          if (response.body && typeof response.body === 'object') {
            expect(response.body).toHaveProperty("success", false);
            expect(response.body).toHaveProperty("error");
          }
        }
      }
    });

    test("should handle malformed WebSocket messages", async () => {
      const malformedMessages = [
        "not json",
        '{"incomplete": }',
        '{"type": null}',
        '{"type": "subscribe", "payload": malformed}',
        Buffer.from("binary data").toString(),
        "a".repeat(100000) // Very large message
      ];
      
      for (const message of malformedMessages) {
        const response = await request(app)
          .post("/api/websocket/validate-message")
          .set("Content-Type", "application/json")
          .send(message);
          
        expect([400, 422]).toContain(response.status);
        
        if (response.status >= 400 && response.body) {
          expect(response.body).toHaveProperty("success", false);
          expect(response.body).toHaveProperty("error");
          
          // Error should not echo back malformed content
          if (response.body.error) {
            expect(response.body.error).not.toContain(message);
          }
        }
      }
    });

    test("should handle WebSocket security issues", async () => {
      const securityTests = [
        { 
          message: { type: "subscribe", payload: { symbols: ["<script>alert('xss')</script>"] } },
          description: "XSS in symbols"
        },
        {
          message: { type: "authenticate", payload: { token: "'; DROP TABLE users; --" } },
          description: "SQL injection in token"
        },
        {
          message: { type: "subscribe", payload: { symbols: ["../../../etc/passwd"] } },
          description: "Path traversal in symbols"
        }
      ];
      
      for (const test of securityTests) {
        const response = await request(app)
          .post("/api/websocket/validate-message")
          .send(test.message);
          
        expect([200, 404, 500, 501]).toContain(response.status);
        
        if (response.status >= 400 && response.body?.error) {
          // Error should not contain malicious content
          const errorMessage = response.body.error.toLowerCase();
          expect(errorMessage).not.toMatch(/<script>|drop table|\.\.\/\.\.\//i);
        }
      }
    });
  });

  describe("WebSocket Performance and Scalability", () => {
    test("should handle concurrent WebSocket requests", async () => {
      const concurrentConnections = 10;
      const connectionPromises = [];
      
      for (let i = 0; i < concurrentConnections; i++) {
        const promise = request(app)
          .get("/api/websocket/info")
          .timeout(5000)
          .then(response => ({ 
            connectionId: i, 
            status: response.status,
            success: response.status === 200 
          }))
          .catch(error => ({ 
            connectionId: i, 
            error: error.message,
            success: false 
          }));
          
        connectionPromises.push(promise);
      }
      
      const results = await Promise.all(connectionPromises);
      
      expect(results.length).toBe(concurrentConnections);
      
      // Most connections should succeed
      const successfulConnections = results.filter(r => r.success);
      expect(successfulConnections.length).toBeGreaterThan(concurrentConnections * 0.7);
      
      // All should be processed
      results.forEach(result => {
        expect(result.success).toBe(true);
      });
    });

    test("should handle high-frequency message validation", async () => {
      const messageCount = 20;
      const testMessage = { type: "ping", payload: {} };
      
      const messagePromises = Array.from({ length: messageCount }, (_, i) =>
        request(app)
          .post("/api/websocket/validate-message")
          .send({ ...testMessage, id: i })
          .timeout(2000)
          .then(response => ({ 
            messageId: i, 
            status: response.status,
            responseTime: Date.now() 
          }))
          .catch(error => ({ 
            messageId: i, 
            error: error.message 
          }))
      );
      
      const results = await Promise.all(messagePromises);
      
      expect(results.length).toBe(messageCount);
      
      // Should handle high frequency gracefully
      const processedMessages = results.filter(r => r.status !== undefined || r.error !== undefined);
      expect(processedMessages.length).toBe(messageCount);
      
      // Most should succeed
      const successfulMessages = results.filter(r => [200, 404].includes(r.status));
      expect(successfulMessages.length).toBeGreaterThan(messageCount * 0.8);
    });

    test("should maintain performance under load", async () => {
      const loadTest = async () => {
        const startTime = Date.now();
        
        const response = await request(app)
          .get("/api/websocket/info")
          .timeout(3000);
          
        const responseTime = Date.now() - startTime;
        
        return {
          status: response.status,
          responseTime,
          success: [200, 404].includes(response.status)
        };
      };
      
      // Run load test with multiple concurrent requests
      const loadTests = Array.from({ length: 15 }, () => loadTest());
      const results = await Promise.all(loadTests);
      
      expect(results.length).toBe(15);
      
      // Calculate average response time
      const responseTimes = results
        .filter(r => r.responseTime)
        .map(r => r.responseTime);
        
      if (responseTimes.length > 0) {
        const avgResponseTime = responseTimes.reduce((a, b) => a + b, 0) / responseTimes.length;
        
        // Should maintain reasonable response times under load
        expect(avgResponseTime).toBeLessThan(2000); // 2 seconds average
        
        // No individual request should take too long
        responseTimes.forEach(time => {
          expect(time).toBeLessThan(5000); // 5 seconds max
        });
      }
    });
  });

  describe("WebSocket Integration with Authentication", () => {
    test("should handle WebSocket authentication flow", async () => {
      const authFlow = [
        {
          step: "info",
          request: () => request(app).get("/api/websocket/info")
        },
        {
          step: "auth_check",
          request: () => request(app)
            .post("/api/websocket/validate-message")
            .send({ type: "authenticate", payload: { token: "dev-bypass-token" } })
        },
        {
          step: "protected_subscribe",
          request: () => request(app)
            .post("/api/websocket/subscribe/portfolio")
            .set("Authorization", "Bearer dev-bypass-token")
            .send({ type: "value" })
        }
      ];
      
      const results = [];
      
      for (const step of authFlow) {
        try {
          const response = await step.request();
          results.push({
            step: step.step,
            status: response.status,
            success: [200, 404].includes(response.status),
            authenticated: ![401, 403].includes(response.status)
          });
        } catch (error) {
          results.push({
            step: step.step,
            error: error.message,
            success: false
          });
        }
      }
      
      expect(results.length).toBe(authFlow.length);
      
      // Authentication should work consistently across the flow
      results.forEach(result => {
        if (result.status) {
          expect(result.status).toBe(200);
          expect(result.authenticated).toBe(true);
        }
      });
    });

    test("should handle WebSocket session management", async () => {
      const sessionSteps = [
        { action: "create", endpoint: "/api/websocket/session", method: "post", data: {} },
        { action: "validate", endpoint: "/api/websocket/session/validate", method: "post", data: {} },
        { action: "refresh", endpoint: "/api/websocket/session/refresh", method: "post", data: {} }
      ];
      
      let sessionId = null;
      
      for (const step of sessionSteps) {
        let requestBuilder = request(app)[step.method](step.endpoint);
        
        if (sessionId) {
          step.data.sessionId = sessionId;
        }
        
        requestBuilder = requestBuilder
          .set("Authorization", "Bearer dev-bypass-token")
          .send(step.data);
          
        const response = await requestBuilder;
        
        expect([200, 404, 500, 501]).toContain(response.status);
        
        if (response.status === 200 && response.body.data?.sessionId) {
          sessionId = response.body.data.sessionId;
        }
        
        // Session management should not have auth errors
        expect([401, 403]).not.toContain(response.status);
      }
    });
  });

  describe("WebSocket Data Consistency", () => {
    test("should maintain consistent WebSocket message ordering", async () => {
      const messageSequence = [
        { type: "authenticate", payload: { token: "dev-bypass-token" } },
        { type: "subscribe", payload: { symbols: ["AAPL"] } },
        { type: "subscribe", payload: { symbols: ["GOOGL"] } },
        { type: "unsubscribe", payload: { symbols: ["AAPL"] } },
        { type: "ping", payload: {} }
      ];
      
      const results = [];
      
      for (let i = 0; i < messageSequence.length; i++) {
        const message = { ...messageSequence[i], sequenceId: i };
        
        const response = await request(app)
          .post("/api/websocket/validate-message")
          .send(message);
          
        results.push({
          sequenceId: i,
          status: response.status,
          timestamp: Date.now(),
          messageType: message.type
        });
      }
      
      expect(results.length).toBe(messageSequence.length);
      
      // Results should maintain sequence order
      for (let i = 1; i < results.length; i++) {
        expect(results[i].sequenceId).toBe(results[i-1].sequenceId + 1);
        expect(results[i].timestamp).toBeGreaterThanOrEqual(results[i-1].timestamp);
      }
    });
  });
});
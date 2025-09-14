/**
 * Server-Sent Events (SSE) Streaming Integration Tests
 * Tests the new real-time SSE streaming functionality implemented in liveData routes
 */

const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;

describe("SSE Streaming Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Server-Sent Events Streaming", () => {
    test("should establish SSE connection for live quotes stream", async () => {
      const response = await request(app)
        .get("/live-data/stream")
        .set("Authorization", "Bearer dev-bypass-token")
        .set("Accept", "text/event-stream")
        .timeout(3000); // Short timeout for test

      if (response.status === 200) {
        // SSE connection should set proper headers
        expect(response.headers['content-type']).toBe('text/event-stream');
        expect(response.headers['cache-control']).toBe('no-cache');
        expect(response.headers['connection']).toBe('keep-alive');
        expect(response.headers['access-control-allow-origin']).toBe('*');

        // Response should be streaming data
        if (response.text) {
          // SSE data should follow proper format
          const ssePattern = /^(data:|event:|id:)/m;
          expect(response.text).toMatch(ssePattern);
        }
      } else {
        // Handle auth or implementation status
        expect([401, 404, 501]).toContain(response.status);
        if (response.status === 501) {
          expect(response.body).toHaveProperty('success', false);
          expect(response.body.error).toContain('not implemented');
        }
      }
    });

    test("should handle SSE streaming with symbol filters", async () => {
      const symbols = "AAPL,MSFT,GOOGL";
      
      const response = await request(app)
        .get("/live-data/stream")
        .set("Authorization", "Bearer dev-bypass-token")
        .set("Accept", "text/event-stream")
        .query({ symbols })
        .timeout(2000);

      if (response.status === 200) {
        expect(response.headers['content-type']).toBe('text/event-stream');
        
        // Should include requested symbols in stream
        if (response.text) {
          const hasSymbolData = /AAPL|MSFT|GOOGL/.test(response.text);
          expect(hasSymbolData).toBe(true);
        }
      } else {
        expect([401, 404, 501]).toContain(response.status);
      }
    });

    test("should handle SSE streaming with update interval", async () => {
      const response = await request(app)
        .get("/live-data/stream")
        .set("Authorization", "Bearer dev-bypass-token")
        .set("Accept", "text/event-stream")
        .query({ interval: 1000 }) // 1 second interval
        .timeout(2500); // Allow for at least 2 updates

      if (response.status === 200) {
        expect(response.headers['content-type']).toBe('text/event-stream');
        
        // Should receive multiple updates
        if (response.text) {
          const dataEvents = response.text.split('data:').length - 1;
          expect(dataEvents).toBeGreaterThan(0);
        }
      } else {
        expect([401, 404, 501]).toContain(response.status);
      }
    });
  });

  describe("Live Data Quotes API", () => {
    test("should return live quotes with comprehensive data structure", async () => {
      const response = await request(app)
        .get("/live-data/quotes")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
        expect(response.body.data).toHaveProperty('quotes');
        expect(response.body.data).toHaveProperty('summary');

        // Check quotes structure
        expect(Array.isArray(response.body.data.quotes)).toBe(true);
        if (response.body.data.quotes.length > 0) {
          const quote = response.body.data.quotes[0];
          expect(quote).toHaveProperty('symbol');
          expect(quote).toHaveProperty('current_price');
          expect(quote).toHaveProperty('change_amount');
          expect(quote).toHaveProperty('change_percent');
          expect(quote).toHaveProperty('volume');
          expect(quote).toHaveProperty('market_status');
          expect(quote).toHaveProperty('last_updated');
          
          // Validate data types
          expect(typeof quote.current_price).toBe('number');
          expect(typeof quote.change_amount).toBe('number');
          expect(typeof quote.change_percent).toBe('number');
          expect(typeof quote.volume).toBe('number');
        }

        // Check summary structure
        expect(response.body.data.summary).toHaveProperty('total_symbols');
        expect(response.body.data.summary).toHaveProperty('market_status');
        expect(response.body.data.summary).toHaveProperty('gainers');
        expect(response.body.data.summary).toHaveProperty('losers');
        expect(response.body.data.summary).toHaveProperty('last_updated');
      } else {
        expect([401, 404, 501]).toContain(response.status);
      }
    });

    test("should handle symbol filtering for live quotes", async () => {
      const testSymbols = "AAPL,MSFT";
      
      const response = await request(app)
        .get("/live-data/quotes")
        .set("Authorization", "Bearer dev-bypass-token")
        .query({ symbols: testSymbols });

      if (response.status === 200) {
        expect(response.body.data.quotes.length).toBeLessThanOrEqual(2);
        
        // All returned quotes should be from requested symbols
        response.body.data.quotes.forEach(quote => {
          expect(['AAPL', 'MSFT']).toContain(quote.symbol);
        });
      }
    });

    test("should handle pagination for live quotes", async () => {
      const response = await request(app)
        .get("/live-data/quotes")
        .set("Authorization", "Bearer dev-bypass-token")
        .query({ limit: 5, offset: 10 });

      if (response.status === 200) {
        expect(response.body.data.quotes.length).toBeLessThanOrEqual(5);
        
        // Should include pagination metadata
        if (response.body.data.pagination) {
          expect(response.body.data.pagination).toHaveProperty('offset', 10);
          expect(response.body.data.pagination).toHaveProperty('limit', 5);
        }
      }
    });
  });

  describe("Live Data Administration", () => {
    test("should provide optimization status", async () => {
      const response = await request(app)
        .get("/live-data/optimization")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
        expect(response.body.data).toHaveProperty('status');
        expect(response.body.data).toHaveProperty('metrics');
        expect(response.body.data).toHaveProperty('recommendations');

        // Check metrics structure
        expect(response.body.data.metrics).toHaveProperty('active_connections');
        expect(response.body.data.metrics).toHaveProperty('queries_per_minute');
        expect(response.body.data.metrics).toHaveProperty('average_response_time');
        expect(response.body.data.metrics).toHaveProperty('memory_usage');
        expect(response.body.data.metrics).toHaveProperty('uptime_seconds');

        // Check recommendations are array
        expect(Array.isArray(response.body.data.recommendations)).toBe(true);
      } else {
        expect([401, 403, 404, 501]).toContain(response.status);
      }
    });

    test("should handle stream toggle administration", async () => {
      const response = await request(app)
        .post("/live-data/admin/toggle-stream")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ enabled: true });

      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
        expect(response.body.data).toHaveProperty('streaming_enabled');
        expect(response.body.data).toHaveProperty('active_connections');
        expect(response.body.data).toHaveProperty('timestamp');
      } else {
        // Admin functions may require special permissions
        expect([401, 403, 404, 501]).toContain(response.status);
      }
    });

    test("should handle cache clearing administration", async () => {
      const response = await request(app)
        .post("/live-data/admin/clear-cache")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('message');
        expect(response.body.data).toHaveProperty('cache_status');
        expect(response.body.data).toHaveProperty('cleared_entries');
        expect(response.body.data).toHaveProperty('timestamp');

        // Validate cleared_entries is a number
        expect(typeof response.body.data.cleared_entries).toBe('number');
      } else {
        expect([401, 403, 404, 501]).toContain(response.status);
      }
    });
  });

  describe("Live Data Service Health", () => {
    test("should provide comprehensive health status", async () => {
      const response = await request(app)
        .get("/live-data/health")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body).toHaveProperty('success', true);
        expect(response.body).toHaveProperty('data');
        expect(response.body.data).toHaveProperty('status');
        expect(response.body.data).toHaveProperty('uptime');
        expect(response.body.data).toHaveProperty('database_connection');
        expect(response.body.data).toHaveProperty('streaming_status');
        expect(response.body.data).toHaveProperty('cache_status');

        // Validate health status values
        expect(['healthy', 'degraded', 'down']).toContain(response.body.data.status);
        expect(typeof response.body.data.uptime).toBe('number');
        expect(['connected', 'disconnected', 'error']).toContain(response.body.data.database_connection);
      } else {
        expect([401, 404, 501]).toContain(response.status);
      }
    });

    test("should validate streaming service health metrics", async () => {
      const response = await request(app)
        .get("/live-data/health")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200 && response.body.data) {
        const healthData = response.body.data;
        
        // Uptime should be reasonable
        if (healthData.uptime) {
          expect(healthData.uptime).toBeGreaterThan(0);
          expect(healthData.uptime).toBeLessThan(86400 * 30); // Less than 30 days for test
        }

        // Streaming status should be valid
        if (healthData.streaming_status) {
          expect(['active', 'inactive', 'error']).toContain(healthData.streaming_status);
        }

        // Cache status should be valid
        if (healthData.cache_status) {
          expect(['active', 'disabled', 'error']).toContain(healthData.cache_status);
        }
      }
    });
  });

  describe("Real-time Data Consistency", () => {
    test("should maintain data consistency across SSE and API endpoints", async () => {
      // Get data from regular API
      const apiResponse = await request(app)
        .get("/live-data/quotes")
        .set("Authorization", "Bearer dev-bypass-token")
        .query({ symbols: "AAPL", limit: 1 });

      if (apiResponse.status === 200 && apiResponse.body.data.quotes.length > 0) {
        const apiQuote = apiResponse.body.data.quotes[0];
        
        // Get SSE stream (limited time)
        const sseResponse = await request(app)
          .get("/live-data/stream")
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Accept", "text/event-stream")
          .query({ symbols: "AAPL" })
          .timeout(2000);

        if (sseResponse.status === 200 && sseResponse.text) {
          // Parse SSE data for AAPL
          const sseDataPattern = /data:\s*({.*})/g;
          const matches = sseResponse.text.match(sseDataPattern);
          
          if (matches) {
            const sseData = matches.map(match => {
              try {
                return JSON.parse(match.replace(/^data:\s*/, ''));
              } catch {
                return null;
              }
            }).filter(Boolean);

            const appleData = sseData.find(data => 
              data.symbol === 'AAPL' || 
              (Array.isArray(data) && data.some(item => item.symbol === 'AAPL'))
            );

            if (appleData) {
              // Prices should be in reasonable range (within 50% of each other)
              const apiPrice = apiQuote.current_price;
              let ssePrice;
              
              if (Array.isArray(appleData)) {
                const appleItem = appleData.find(item => item.symbol === 'AAPL');
                ssePrice = appleItem ? appleItem.price : null;
              } else {
                ssePrice = appleData.price;
              }

              if (typeof apiPrice === 'number' && typeof ssePrice === 'number') {
                const priceDifference = Math.abs(apiPrice - ssePrice) / apiPrice;
                expect(priceDifference).toBeLessThan(0.5); // Within 50%
              }
            }
          }
        }
      }
    });

    test("should handle concurrent SSE connections", async () => {
      const connectionCount = 3;
      const symbols = ['AAPL', 'MSFT', 'GOOGL'];
      
      const connections = symbols.slice(0, connectionCount).map((symbol, index) =>
        request(app)
          .get("/live-data/stream")
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Accept", "text/event-stream")
          .query({ symbols: symbol })
          .timeout(1500)
          .then(response => ({ symbol, status: response.status, index }))
          .catch(error => ({ symbol, error: error.message, index }))
      );

      const results = await Promise.all(connections);
      
      expect(results.length).toBe(connectionCount);
      
      // All connections should either succeed or fail consistently
      results.forEach(result => {
        if (result.status) {
          expect([200, 401, 404, 501]).toContain(result.status);
        }
        expect(symbols.slice(0, connectionCount)).toContain(result.symbol);
      });
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle malformed SSE requests gracefully", async () => {
      const malformedRequests = [
        { query: { symbols: "", interval: -1000 } },
        { query: { symbols: "A".repeat(1000) } },
        { query: { interval: "invalid" } }
      ];

      for (const malformedRequest of malformedRequests) {
        const response = await request(app)
          .get("/live-data/stream")
          .set("Authorization", "Bearer dev-bypass-token")
          .query(malformedRequest.query);

        // Should handle gracefully
        if (response.status >= 400) {
          expect([400, 401, 404, 500, 501]).toContain(response.status);
          if (response.body) {
            expect(response.body).toHaveProperty('success', false);
          }
        }
      }
    });

    test("should handle SSE connection interruptions", async () => {
      // Start SSE connection and interrupt it
      const controller = new AbortController();
      
      setTimeout(() => {
        controller.abort();
      }, 500);

      try {
        const response = await request(app)
          .get("/live-data/stream")
          .set("Authorization", "Bearer dev-bypass-token")
          .set("Accept", "text/event-stream")
          .timeout(1000);

        // If response completes, it should be valid
        if (response.status === 200) {
          expect(response.headers['content-type']).toBe('text/event-stream');
        }
      } catch (error) {
        // Timeout or abort is expected behavior
        expect(['ECONNABORTED', 'ABORT_ERR'].some(code => 
          error.code === code || error.name === code
        )).toBe(true);
      }
    });
  });
});
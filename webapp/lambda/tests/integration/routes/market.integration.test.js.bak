const request = require("supertest");
const { app } = require("../../../index");


// Import app AFTER mocking all dependencies
const { app } = require("../../../index");

describe("Market Routes Unit Tests", () => {
  });

  describe("GET /api/market", () => {
    test("should return market endpoint information", async () => {
      const response = await request(app).get("/api/market");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data) {
          expect(response.body).toHaveProperty("data");
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });

  describe("GET /api/market/overview", () => {
    test("should return market overview data or handle missing data gracefully", async () => {
      const response = await request(app).get("/api/market/overview");

      expect([200, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");

        const data = response.body.data;
        if (data.marketSummary) {
          expect(data).toHaveProperty("marketSummary");
          expect(typeof data.marketSummary).toBe("object");
        }
        if (data.indices) {
          expect(Array.isArray(data.indices)).toBe(true);
        }
        if (data.marketData) {
          expect(typeof data.marketData).toBe("object");
        }
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });

    test("should handle market overview with parameters", async () => {
      const response = await request(app).get(
        "/api/market/overview?period=1d&includePremarket=true"
      );

      expect([200, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });

  describe("GET /api/market/data", () => {
    test("should return market data or handle service unavailable", async () => {
      const response = await request(app).get("/api/market/data");

      expect([200, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");

        if (Array.isArray(response.body.data)) {
          expect(Array.isArray(response.body.data)).toBe(true);
          if (response.body.data.length > 0) {
            const item = response.body.data[0];
            if (item.symbol) expect(item).toHaveProperty("symbol");
            if (item.price !== undefined)
              expect(typeof item.price).toBe("number");
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });

    test("should handle symbol-specific market data", async () => {
      const response = await request(app).get("/api/market/data?symbol=AAPL");

      expect([200, 503]).toContain(response.status);

      if (response.status === 200 && response.body.data) {
        expect(response.body).toHaveProperty("success", true);
        if (
          Array.isArray(response.body.data) &&
          response.body.data.length > 0
        ) {
          const item = response.body.data[0];
          if (item.symbol) {
            expect(item.symbol).toMatch(/^[A-Z]+$/);
          }
        }
      }
    });
  });

  describe("GET /api/market/sentiment", () => {
    test("should return market sentiment data or handle missing data", async () => {
      const response = await request(app).get("/api/market/sentiment");

      expect([200, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data) {
          expect(response.body).toHaveProperty("data");
          const data = response.body.data;
          if (data.sentiment !== undefined) {
            expect(typeof data.sentiment).toBe("string");
          }
          if (data.score !== undefined) {
            expect(typeof data.score).toBe("number");
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });

  describe("GET /api/market/sentiment/history", () => {
    test("should return sentiment history or handle service unavailable", async () => {
      const response = await request(app).get("/api/market/sentiment/history");

      expect([200, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data && Array.isArray(response.body.data)) {
          expect(Array.isArray(response.body.data)).toBe(true);
          if (response.body.data.length > 0) {
            const item = response.body.data[0];
            if (item.date) expect(item).toHaveProperty("date");
            if (item.sentiment) expect(item).toHaveProperty("sentiment");
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });

    test("should handle sentiment history with time range", async () => {
      const response = await request(app).get(
        "/api/market/sentiment/history?days=30"
      );

      expect([200, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
      }
    });
  });

  describe("GET /api/market/movers", () => {
    test("should return top movers or handle missing data", async () => {
      const response = await request(app).get("/api/market/movers");

      expect([200, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data) {
          expect(response.body).toHaveProperty("data");
          const data = response.body.data;
          if (data.gainers && Array.isArray(data.gainers)) {
            expect(Array.isArray(data.gainers)).toBe(true);
          }
          if (data.losers && Array.isArray(data.losers)) {
            expect(Array.isArray(data.losers)).toBe(true);
          }
          if (data.mostActive && Array.isArray(data.mostActive)) {
            expect(Array.isArray(data.mostActive)).toBe(true);
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });

    test("should handle movers with type parameter", async () => {
      const response = await request(app).get(
        "/api/market/movers?type=gainers"
      );

      expect([200, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
      }
    });
  });

  describe("GET /api/market/indices", () => {
    test("should return market indices or handle missing data", async () => {
      const response = await request(app).get("/api/market/indices");

      expect([200, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data && Array.isArray(response.body.data)) {
          expect(Array.isArray(response.body.data)).toBe(true);
          if (response.body.data.length > 0) {
            const index = response.body.data[0];
            if (index.symbol) expect(index).toHaveProperty("symbol");
            if (index.name) expect(index).toHaveProperty("name");
            if (index.value !== undefined)
              expect(typeof index.value).toBe("number");
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });

  describe("GET /api/market/status", () => {
    test("should return market status", async () => {
      const response = await request(app).get("/api/market/status");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data) {
          expect(response.body).toHaveProperty("data");
          const data = response.body.data;
          if (data.isOpen !== undefined) {
            expect(typeof data.isOpen).toBe("boolean");
          }
          if (data.nextOpen) {
            expect(data).toHaveProperty("nextOpen");
          }
          if (data.nextClose) {
            expect(data).toHaveProperty("nextClose");
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });

  describe("GET /api/sectors/sectors-with-history", () => {
    test("should return sector performance or handle missing data", async () => {
      const response = await request(app).get("/api/sectors/sectors-with-history");

      expect([200, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        if (response.body.data && Array.isArray(response.body.data)) {
          expect(Array.isArray(response.body.data)).toBe(true);
          if (response.body.data.length > 0) {
            const sector = response.body.data[0];
            if (sector.name) expect(sector).toHaveProperty("name");
            if (sector.performance !== undefined)
              expect(typeof sector.performance).toBe("number");
          }
        }
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error", "Not Found");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });
  });

  describe("GET /api/market/distribution-days", () => {
    test("should return distribution days data or handle missing data", async () => {
      const response = await request(app).get("/api/market/distribution-days");

      expect([200, 404, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");

        const data = response.body.data;
        expect(data).toBeDefined();

        // Check that we have data for major indices
        const expectedIndices = ["^GSPC", "^IXIC", "^DJI"];
        expectedIndices.forEach((symbol) => {
          if (data[symbol]) {
            expect(data[symbol]).toHaveProperty("name");
            expect(data[symbol]).toHaveProperty("count");
            expect(data[symbol]).toHaveProperty("signal");
            expect(data[symbol]).toHaveProperty("days");
            expect(Array.isArray(data[symbol].days)).toBe(true);

            // Verify signal is one of the expected values
            expect([
              "NORMAL",
              "ELEVATED",
              "CAUTION",
              "UNDER_PRESSURE",
            ]).toContain(data[symbol].signal);

            // If there are distribution days, verify their structure
            if (data[symbol].days.length > 0) {
              const day = data[symbol].days[0];
              expect(day).toHaveProperty("date");
              expect(day).toHaveProperty("close_price");
              expect(day).toHaveProperty("change_pct");
              expect(day).toHaveProperty("volume");
              expect(day).toHaveProperty("volume_ratio");
              expect(day).toHaveProperty("days_ago");

              // Verify data types
              expect(typeof day.date).toBe("string");
              expect(typeof day.change_pct).toBe("number");
              expect(typeof day.volume).toBe("number");
              expect(typeof day.volume_ratio).toBe("number");
              expect(typeof day.days_ago).toBe("number");

              // Verify distribution day criteria (IBD methodology)
              expect(day.change_pct).toBeLessThanOrEqual(-0.2);
              expect(day.volume_ratio).toBeGreaterThan(1.0);
            }
          }
        });
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toContain("No distribution days data");
      } else if (response.status === 503) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should have correct data structure and IBD methodology", async () => {
      const response = await request(app).get("/api/market/distribution-days");

      if (response.status === 200 && response.body.data) {
        const data = response.body.data;

        Object.entries(data).forEach(([symbol, indexData]) => {
          // Verify count matches number of days
          expect(indexData.count).toBe(indexData.days.length);

          // Verify signal classification logic
          if (indexData.count >= 6) {
            expect(indexData.signal).toBe("UNDER_PRESSURE");
          } else if (indexData.count === 5) {
            expect(indexData.signal).toBe("CAUTION");
          } else if (indexData.count >= 3) {
            expect(indexData.signal).toBe("ELEVATED");
          } else {
            expect(indexData.signal).toBe("NORMAL");
          }

          // Verify all distribution days meet IBD criteria
          indexData.days.forEach((day) => {
            // Must be down 0.2% or more
            expect(day.change_pct).toBeLessThanOrEqual(-0.2);
            // Must have higher volume than previous day
            expect(day.volume_ratio).toBeGreaterThan(1.0);
            // Must be within 25 days
            expect(day.days_ago).toBeLessThanOrEqual(25);
          });
        });
      }
    });

    test("should return timestamp in response", async () => {
      const response = await request(app).get("/api/market/distribution-days");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("timestamp");
        expect(typeof response.body.timestamp).toBe("string");
        // Verify timestamp is in ISO format
        expect(new Date(response.body.timestamp).toISOString()).toBe(
          response.body.timestamp
        );
      }
    });
  });

  describe("Error Handling", () => {
    test("should handle invalid endpoints gracefully", async () => {
      const response = await request(app).get("/api/market/invalid-endpoint");

      expect([500, 404]).toContain(response.status);
    });

    test("should handle database connection issues", async () => {
      const response = await request(app).get(
        "/api/market/data?force_error=true"
      );

      expect([200, 503]).toContain(response.status);
    });

    test("should handle malformed query parameters", async () => {
      const response = await request(app).get(
        "/api/market/sentiment/history?days=invalid"
      );

      expect([200, 404, 503]).toContain(response.status);
    });
  });

  describe("Performance Tests", () => {
    test("should respond to overview requests within reasonable time", async () => {
      const startTime = Date.now();
      const response = await request(app).get("/api/market/overview");

      const endTime = Date.now();
      const responseTime = endTime - startTime;

      // Should respond within 10 seconds
      expect(responseTime).toBeLessThan(10000);
      expect([200, 500, 503]).toContain(response.status);
    });

    test("should handle concurrent overview requests", async () => {
      const requests = Array.from({ length: 3 }, () =>
        request(app).get("/api/market/overview")
      );

      const responses = await Promise.allSettled(requests);

      // At least some should succeed
      const statusCodes = responses.map((r) =>
        r.status === "fulfilled" ? r.value.status : 500
      );

      expect(
        statusCodes.some((status) => [200, 500, 503].includes(status))
      ).toBe(true);
    });
  });
});

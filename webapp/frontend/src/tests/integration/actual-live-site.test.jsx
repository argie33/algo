import { describe, it, expect, beforeAll } from "vitest";

const LIVE_API_BASE =
  "https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev";
const LIVE_FRONTEND_URLS = [
  "https://d1copuy2oqlazx.cloudfront.net",
  "https://d1zb7knau41vl9.cloudfront.net",
];

// Helper function to make HTTP requests to live API
const fetchFromLiveAPI = async (endpoint) => {
  const url = `${LIVE_API_BASE}${endpoint}`;
  try {
    const response = await fetch(url, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
    });

    return {
      ok: response.ok,
      status: response.status,
      data: response.ok ? await response.json() : null,
      error: !response.ok ? await response.text() : null,
    };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      data: null,
      error: error.message,
    };
  }
};

describe("Actual Live Site Integration Tests", () => {
  beforeAll(() => {
    console.log(`🌐 Testing live API: ${LIVE_API_BASE}`);
    console.log(`🌐 Testing live frontend: ${LIVE_FRONTEND_URLS.join(", ")}`);
  });

  describe("Live API Endpoints", () => {
    it("should have working health endpoint", async () => {
      const result = await fetchFromLiveAPI("/health");

      expect(result.ok).toBe(true);
      expect(result.status).toBe(200);
      expect(result.data).toBeDefined();
      expect(result.data.healthy).toBe(true);
    }, 10000);

    it("should have working market overview endpoint", async () => {
      const result = await fetchFromLiveAPI("/api/market/overview");

      expect(result.ok).toBe(true);
      expect(result.status).toBe(200);
      expect(result.data).toBeDefined();

      // Should have market data structure
      if (result.data.data) {
        expect(result.data.data).toHaveProperty("sentiment_indicators");
        expect(result.data.data).toHaveProperty("market_breadth");
      }
    }, 20000);

    it("should have working sectors endpoint (previously broken)", async () => {
      const result = await fetchFromLiveAPI("/api/market/sectors");

      expect(result.ok).toBe(true);
      expect(result.status).toBe(200);
      expect(result.data).toBeDefined();

      // Should return sectors data or fallback
      expect(result.data.success).toBe(true);
      expect(Array.isArray(result.data.data)).toBe(true);
    }, 10000);

    it("should have working technical analysis endpoints", async () => {
      const result = await fetchFromLiveAPI("/api/technical");

      expect(result.ok).toBe(true);
      expect(result.status).toBe(200);
      expect(result.data).toBeDefined();
    }, 10000);

    it("should have working news endpoints (sentiment data)", async () => {
      const result = await fetchFromLiveAPI("/api/news");

      expect(result.ok).toBe(true);
      expect(result.status).toBe(200);
      expect(result.data).toBeDefined();
    }, 10000);

    it("should properly protect authentication-required endpoints", async () => {
      // Test that protected endpoints return 401 without auth
      const result = await fetchFromLiveAPI("/api/portfolio/holdings");

      expect(result.status).toBe(401);
      expect(result.data?.error).toBe("Authentication required");
    }, 10000);
  });

  describe("API Performance", () => {
    it("should respond to health check quickly", async () => {
      const start = Date.now();
      const result = await fetchFromLiveAPI("/health");
      const duration = Date.now() - start;

      expect(result.ok).toBe(true);
      expect(duration).toBeLessThan(5000); // Should respond within 5 seconds
    }, 10000);

    it("should handle multiple concurrent requests", async () => {
      const promises = [
        fetchFromLiveAPI("/health"),
        fetchFromLiveAPI("/api/market/overview"),
        fetchFromLiveAPI("/api/market/sectors"),
        fetchFromLiveAPI("/api/technical"),
      ];

      const results = await Promise.all(promises);

      // All requests should succeed
      results.forEach((result) => {
        expect(result.ok).toBe(true);
        expect(result.status).toBe(200);
      });
    }, 25000);
  });

  describe("Error Handling", () => {
    it("should handle non-existent endpoints gracefully", async () => {
      const result = await fetchFromLiveAPI("/api/nonexistent/endpoint");

      // Should not return 500 error for missing endpoints
      expect(result.status).not.toBe(500);
      // Should return 404 or similar client error
      expect(result.status >= 400 && result.status < 500).toBe(true);
    }, 10000);

    it("should return proper error responses", async () => {
      const result = await fetchFromLiveAPI("/api/stocks/INVALID_SYMBOL");

      // Should handle invalid requests gracefully
      if (!result.ok) {
        expect(result.status >= 400).toBe(true);
        expect(result.status).not.toBe(500); // Should not crash
      }
    }, 10000);
  });

  describe("Data Quality", () => {
    it("should return properly structured market data", async () => {
      const result = await fetchFromLiveAPI("/api/market/overview");

      if (result.ok && result.data?.data) {
        const marketData = result.data.data;

        // Check for required data structures
        expect(marketData).toHaveProperty("sentiment_indicators");
        expect(marketData).toHaveProperty("market_breadth");
        expect(marketData).toHaveProperty("market_cap");

        // Validate data freshness
        if (marketData.timestamp) {
          const timestamp = new Date(marketData.timestamp);
          const age = Date.now() - timestamp.getTime();
          const maxAge = 24 * 60 * 60 * 1000; // 24 hours

          expect(age).toBeLessThan(maxAge);
        }
      }
    }, 10000);

    it("should return valid sectors data", async () => {
      const result = await fetchFromLiveAPI("/api/market/sectors");

      expect(result.ok).toBe(true);
      expect(result.data.success).toBe(true);
      expect(Array.isArray(result.data.data)).toBe(true);

      if (result.data.data.length > 0) {
        const sector = result.data.data[0];
        expect(sector).toHaveProperty("sector");
        expect(sector).toHaveProperty("avg_change");
        expect(sector).toHaveProperty("stock_count");
      }
    }, 10000);
  });

  describe("Frontend Accessibility", () => {
    it("should be able to reach at least one frontend URL", async () => {
      let workingUrl = null;

      for (const url of LIVE_FRONTEND_URLS) {
        try {
          const response = await fetch(url, { method: "HEAD" });
          if (response.ok) {
            workingUrl = url;
            break;
          }
        } catch (error) {
          // Continue to next URL
        }
      }

      expect(workingUrl).not.toBeNull();
      console.log(`✅ Working frontend URL: ${workingUrl}`);
    }, 15000);
  });
});

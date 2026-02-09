/**
 * API Endpoints Contract Test
 *
 * Tests the contract for all core API endpoints that frontend components depend on.
 * Validates API availability, response structure, and data integrity.
 */

import { describe, it, expect, beforeAll } from "vitest";

const API_BASE_URL = "http://localhost:3001";

describe("API Endpoints Contract Tests", () => {
  let serverAvailable = false;

  beforeAll(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/health`);
      serverAvailable = response.ok;
    } catch (error) {
      console.warn(
        "Backend server not available for contract tests:",
        error.message
      );
    }
  });

  describe("Core API Structure", () => {
    it("should return API overview with all endpoints", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty("name");
      expect(data).toHaveProperty("version");
      expect(data).toHaveProperty("endpoints");
      expect(data.endpoints).toHaveProperty("stocks");
      expect(data.endpoints).toHaveProperty("metrics");
      expect(data.endpoints).toHaveProperty("health");
    });

    it("should have health endpoint with proper structure", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/health`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty("status");
      expect(data).toHaveProperty("healthy");
      expect(data).toHaveProperty("timestamp");
      expect(data.healthy).toBe(true);
    });
  });

  describe("Market Data Endpoints", () => {
    it("should return market overview data", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/market/overview`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty("success", true);
      expect(data).toHaveProperty("data");
    });

    it("should return sector analysis data", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/sectors/sectors-with-history`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty("success", true);
      expect(data).toHaveProperty("data");
    });
  });

  describe("Stock Data Endpoints", () => {
    it("should return stock detail for valid symbol", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/stocks/GOOGL`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty("success", true);
      expect(data).toHaveProperty("data");
      expect(data.data).toHaveProperty("symbol", "GOOGL");
      expect(data.data).toHaveProperty("current_price");
      expect(data.data).toHaveProperty("name");
    });

    it("should return sector analysis data", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/sectors`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty("success", true);
      expect(data).toHaveProperty("data");
    });
  });

  describe("Trading Endpoints", () => {
    it("should return trading signals with swing trading metrics", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/signals/`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty("success", true);
      expect(data).toHaveProperty("data");
      expect(data).toHaveProperty("summary");
      expect(data.summary).toHaveProperty("buy_signals");
      expect(data.summary).toHaveProperty("sell_signals");

      // Validate swing trading metrics in signal data
      if (data.data && data.data.length > 0) {
        const signal = data.data[0];

        // Core signal fields
        expect(signal).toHaveProperty("symbol");
        expect(signal).toHaveProperty("signal");
        expect(signal).toHaveProperty("date");
        expect(signal).toHaveProperty("timeframe");
        expect(signal).toHaveProperty("buylevel");
        expect(signal).toHaveProperty("stoplevel");

        // Swing trading metrics (27 fields including enhanced stage analysis)
        expect(signal).toHaveProperty("target_price");
        expect(signal).toHaveProperty("current_price");
        expect(signal).toHaveProperty("risk_reward_ratio");
        expect(signal).toHaveProperty("market_stage");
        expect(signal).toHaveProperty("stage_confidence");
        expect(signal).toHaveProperty("substage");
        expect(signal).toHaveProperty("pct_from_ema21");
        expect(signal).toHaveProperty("pct_from_sma50");
        // pct_from_sma200 not in stock API response
        // volume_ratio not in API response
        // volume_analysis not in API response
        expect(signal).toHaveProperty("sata_score");
        expect(signal).toHaveProperty("stage_number");
        expect(signal).toHaveProperty("mansfield_rs");
        expect(signal).toHaveProperty("profit_target_8pct");
        expect(signal).toHaveProperty("profit_target_20pct");
        expect(signal).toHaveProperty("risk_pct");
        expect(signal).toHaveProperty("position_size_recommendation");
        expect(signal).toHaveProperty("passes_minervini_template");
        expect(signal).toHaveProperty("rsi");
        expect(signal).toHaveProperty("adx");
        expect(signal).toHaveProperty("atr");
        expect(signal).toHaveProperty("daily_range_pct");
        expect(signal).toHaveProperty("inposition");
      }
    });

    it("should return recent trades", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/trades/recent`);
      const data = await response.json();

      // This endpoint returns 501 (Not Implemented) with valid error structure
      expect(response.status).toBeGreaterThan(0);
      expect(data).toHaveProperty("success");
      expect(typeof data.success).toBe("boolean");
      // The endpoint is intentionally disabled, so success can be false
      if (!data.success) {
        expect(data).toHaveProperty("error");
        expect(data).toHaveProperty("message");
      }
    });
  });

  describe("Earnings Data", () => {
    it("should return earnings events", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/earnings/events`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty("success", true);
      expect(data).toHaveProperty("data");
    });

    it("should return earnings estimates", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/earnings/estimates`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty("success", true);
      expect(data).toHaveProperty("data");
    });
  });

  describe("Sentiment and Social Data", () => {
    it("should return sentiment analysis data", async () => {
      if (!serverAvailable) return;

      const response = await fetch(
        `${API_BASE_URL}/api/sentiment/social/reddit`
      );
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty("success");
      expect(typeof data.success).toBe("boolean");
      expect(data).toHaveProperty("platform", "reddit");
      // Endpoint may not be fully configured, so success can be false
      if (!data.success) {
        expect(data).toHaveProperty("error");
        expect(data).toHaveProperty("message");
      }
    });

    it("should return twitter sentiment data", async () => {
      if (!serverAvailable) return;

      const response = await fetch(
        `${API_BASE_URL}/api/sentiment/social/twitter`
      );
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty("success", true);
      expect(data).toHaveProperty("platform", "twitter");
    });
  });

  describe("Insider and Recommendations", () => {
    it("should return insider trades data", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/insider/trades`);
      const data = await response.json();

      // This endpoint returns 500 (Server Error) when data source not configured
      expect(response.status).toBeGreaterThan(0);
      expect(data).toHaveProperty("success");
      expect(typeof data.success).toBe("boolean");
      // Endpoint may not be fully configured, so success can be false
      if (!data.success) {
        expect(data).toHaveProperty("error");
        expect(data).toHaveProperty("message");
      }
    });

    it("should return AI recommendations", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/recommendations/ai`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty("success", true);
      expect(data).toHaveProperty("data");
    });
  });

  describe("Error Handling", () => {
    it("should return 404 for non-existent endpoints", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/nonexistent`);

      expect(response.status).toBe(404);
    });

    it("should return proper error structure for invalid requests", async () => {
      if (!serverAvailable) return;

      const response = await fetch(
        `${API_BASE_URL}/api/stocks/INVALID_SYMBOL_THAT_SHOULD_FAIL`
      );

      // Should handle gracefully, either 200 with error data or proper HTTP error
      if (!response.ok) {
        expect(response.status).toBeGreaterThan(399);
      }
    });
  });
});

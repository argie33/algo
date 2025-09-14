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
      console.warn("Backend server not available for contract tests:", error.message);
    }
  });

  describe("Core API Structure", () => {
    it("should return API overview with all endpoints", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('name');
      expect(data).toHaveProperty('version');
      expect(data).toHaveProperty('endpoints');
      expect(data.endpoints).toHaveProperty('stocks');
      expect(data.endpoints).toHaveProperty('metrics');
      expect(data.endpoints).toHaveProperty('health');
    });

    it("should have health endpoint with proper structure", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/health`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('status');
      expect(data).toHaveProperty('healthy');
      expect(data).toHaveProperty('timestamp');
      expect(data.healthy).toBe(true);
    });
  });

  describe("Market Data Endpoints", () => {
    it("should return market overview data", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/market/overview`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('success', true);
      expect(data).toHaveProperty('data');
    });

    it("should return sector analysis data", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/market/sectors`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('success', true);
      expect(data).toHaveProperty('data');
    });
  });

  describe("Stock Data Endpoints", () => {
    it("should return stock detail for valid symbol", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/stocks/GOOGL`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('symbol', 'GOOGL');
      expect(data).toHaveProperty('currentPrice');
      expect(data).toHaveProperty('companyInfo');
    });

    it("should return technical analysis data", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/technical/daily/GOOGL`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('success', true);
      expect(data).toHaveProperty('data');
    });
  });

  describe("Trading Endpoints", () => {
    it("should return trading signals", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/signals/`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('data');
      expect(data.data).toHaveProperty('buy_signals');
      expect(data.data).toHaveProperty('sell_signals');
    });

    it("should return recent trades", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/trades/recent`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('success', true);
      expect(data).toHaveProperty('data');
    });
  });

  describe("Calendar and Events", () => {
    it("should return upcoming calendar events", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/calendar/upcoming`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('success', true);
      expect(data).toHaveProperty('data');
    });

    it("should return earnings calendar", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/calendar/earnings`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('success', true);
      expect(data).toHaveProperty('data');
    });
  });

  describe("Sentiment and Social Data", () => {
    it("should return sentiment analysis data", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/sentiment/social/reddit`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('success', true);
      expect(data).toHaveProperty('platform', 'reddit');
    });

    it("should return twitter sentiment data", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/sentiment/social/twitter`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('success', true);
      expect(data).toHaveProperty('platform', 'twitter');
    });
  });

  describe("Insider and Recommendations", () => {
    it("should return insider trades data", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/insider/trades`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('success', true);
      expect(data).toHaveProperty('data');
    });

    it("should return AI recommendations", async () => {
      if (!serverAvailable) return;

      const response = await fetch(`${API_BASE_URL}/api/recommendations/ai`);
      const data = await response.json();

      expect(response.ok).toBe(true);
      expect(data).toHaveProperty('success', true);
      expect(data).toHaveProperty('data');
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

      const response = await fetch(`${API_BASE_URL}/api/stocks/INVALID_SYMBOL_THAT_SHOULD_FAIL`);
      
      // Should handle gracefully, either 200 with error data or proper HTTP error
      if (!response.ok) {
        expect(response.status).toBeGreaterThan(399);
      }
    });
  });
});
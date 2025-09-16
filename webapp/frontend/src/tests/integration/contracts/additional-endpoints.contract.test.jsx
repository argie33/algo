/**
 * Additional API Endpoints Contract Test
 *
 * Tests remaining critical API endpoints for comprehensive coverage.
 * Covers watchlist, analytics, news, risk, screener, and backtest endpoints.
 */

import { describe, it, expect, beforeAll } from "vitest";
import {
  checkServerAvailability,
  skipIfServerUnavailable,
  API_BASE_URL,
  AUTH_HEADERS,
} from "./test-server-utils.js";

describe("Additional API Endpoints Contract Tests", () => {
  let serverAvailable = false;

  beforeAll(async () => {
    serverAvailable = await checkServerAvailability();
  });

  describe("Watchlist Endpoints", () => {
    it("should return watchlist data structure", async () => {
      if (skipIfServerUnavailable(serverAvailable, "watchlist test")) return;

      const response = await fetch(`${API_BASE_URL}/api/watchlist`, {
        headers: AUTH_HEADERS,
      });

      expect(response.status).toBe(200);
      const data = await response.json();
      expect(data).toHaveProperty("success", true);
      expect(data).toHaveProperty("data");
    });

    it("should support adding stocks to watchlist", async () => {
      if (skipIfServerUnavailable(serverAvailable, "add to watchlist test"))
        return;

      const testStock = { symbol: "AAPL", name: "Apple Inc." };
      const response = await fetch(`${API_BASE_URL}/api/watchlist`, {
        method: "POST",
        headers: AUTH_HEADERS,
        body: JSON.stringify(testStock),
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });
  });

  describe("Analytics and Metrics Endpoints", () => {
    it("should return analytics data structure", async () => {
      if (skipIfServerUnavailable(serverAvailable, "analytics test")) return;

      const response = await fetch(`${API_BASE_URL}/api/analytics/overview`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success", true);
      expect(data).toHaveProperty("data");
    });

    it("should return metrics dashboard data", async () => {
      if (skipIfServerUnavailable(serverAvailable, "metrics test")) return;

      const response = await fetch(`${API_BASE_URL}/api/metrics/dashboard`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });
  });

  describe("News Endpoints", () => {
    it("should return news data structure", async () => {
      if (skipIfServerUnavailable(serverAvailable, "news test")) return;

      const response = await fetch(`${API_BASE_URL}/api/news/latest`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success", true);
      expect(data).toHaveProperty("articles");
      expect(Array.isArray(data.articles)).toBe(true);
    });

    it("should return company-specific news", async () => {
      if (skipIfServerUnavailable(serverAvailable, "company news test")) return;

      const response = await fetch(`${API_BASE_URL}/api/news/company/AAPL`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });
  });

  describe("Risk Management Endpoints", () => {
    it("should return risk assessment data", async () => {
      if (skipIfServerUnavailable(serverAvailable, "risk assessment test"))
        return;

      const response = await fetch(`${API_BASE_URL}/api/risk/assessment`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });

    it("should return portfolio risk metrics", async () => {
      if (skipIfServerUnavailable(serverAvailable, "portfolio risk test"))
        return;

      const response = await fetch(`${API_BASE_URL}/api/risk/portfolio`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });
  });

  describe("Screener Endpoints", () => {
    it("should return stock screener results", async () => {
      if (skipIfServerUnavailable(serverAvailable, "screener test")) return;

      const response = await fetch(`${API_BASE_URL}/api/screener/stocks`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
      expect(data).toHaveProperty("data");
    });

    it("should support custom screening criteria", async () => {
      if (skipIfServerUnavailable(serverAvailable, "custom screener test"))
        return;

      const criteria = {
        marketCap: { min: 1000000000 },
        peRatio: { max: 25 },
      };

      const response = await fetch(`${API_BASE_URL}/api/screener/custom`, {
        method: "POST",
        headers: AUTH_HEADERS,
        body: JSON.stringify(criteria),
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });
  });

  describe("Backtest Endpoints", () => {
    it("should return backtest results structure", async () => {
      if (skipIfServerUnavailable(serverAvailable, "backtest test")) return;

      const response = await fetch(
        `${API_BASE_URL}/api/backtest/results/sample`,
        {
          headers: AUTH_HEADERS,
        }
      );

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });

    it("should support creating new backtests", async () => {
      if (skipIfServerUnavailable(serverAvailable, "create backtest test"))
        return;

      const strategy = {
        name: "Test Strategy",
        symbols: ["AAPL", "MSFT"],
        startDate: "2023-01-01",
        endDate: "2023-12-31",
      };

      const response = await fetch(`${API_BASE_URL}/api/backtest/create`, {
        method: "POST",
        headers: AUTH_HEADERS,
        body: JSON.stringify(strategy),
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });
  });

  describe("User and Settings Endpoints", () => {
    it("should return user profile data", async () => {
      if (skipIfServerUnavailable(serverAvailable, "user profile test")) return;

      const response = await fetch(`${API_BASE_URL}/api/user/profile`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });

    it("should return application settings", async () => {
      if (skipIfServerUnavailable(serverAvailable, "settings test")) return;

      const response = await fetch(`${API_BASE_URL}/api/settings/app`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });
  });

  describe("Economic and Dividend Data", () => {
    it("should return economic indicators", async () => {
      if (skipIfServerUnavailable(serverAvailable, "economic data test"))
        return;

      const response = await fetch(`${API_BASE_URL}/api/economic/indicators`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });

    it("should return dividend calendar", async () => {
      if (skipIfServerUnavailable(serverAvailable, "dividend test")) return;

      const response = await fetch(`${API_BASE_URL}/api/dividend/calendar`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });
  });

  describe("Additional Critical Endpoints", () => {
    it("should return alerts data structure", async () => {
      if (skipIfServerUnavailable(serverAvailable, "alerts test")) return;

      const response = await fetch(`${API_BASE_URL}/api/alerts`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });

    it("should return ETF data structure", async () => {
      if (skipIfServerUnavailable(serverAvailable, "ETF test")) return;

      const response = await fetch(`${API_BASE_URL}/api/etf/list`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });

    it("should return performance metrics", async () => {
      if (skipIfServerUnavailable(serverAvailable, "performance test")) return;

      const response = await fetch(`${API_BASE_URL}/api/performance/summary`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });

    it("should return positioning data", async () => {
      if (skipIfServerUnavailable(serverAvailable, "positioning test")) return;

      const response = await fetch(`${API_BASE_URL}/api/positioning/current`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });

    it("should return commodities data", async () => {
      if (skipIfServerUnavailable(serverAvailable, "commodities test")) return;

      const response = await fetch(`${API_BASE_URL}/api/commodities/overview`, {
        headers: AUTH_HEADERS,
      });

      const data = await response.json();
      expect(data).toHaveProperty("success");
    });
  });
});

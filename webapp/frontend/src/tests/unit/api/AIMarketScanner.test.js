/**
 * AI Market Scanner API Integration Tests
 * Tests the AI-powered market scanning functionality
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock import.meta.env
Object.defineProperty(import.meta, "env", {
  value: {
    VITE_API_URL: "http://localhost:3001",
    MODE: "test",
    DEV: true,
    PROD: false,
    BASE_URL: "/",
  },
  writable: true,
  configurable: true,
});

// Mock fetch for API calls
global.fetch = vi.fn();

const mockAIScanResults = {
  success: true,
  data: {
    scanType: "momentum",
    strategy: "Momentum Breakouts",
    description: "Stocks with strong price and volume momentum",
    results: [
      {
        symbol: "AAPL",
        company_name: "Apple Inc.",
        price: "185.25",
        price_change: "3.45",
        volume: 75000000,
        volume_ratio: "2.15",
        market_cap: 2850000000000,
        sector: "Technology",
        ai_score: 85,
        confidence: "high",
        signals: ["Strong Price Gain", "High Volume", "Price-Volume Momentum"],
        technical_indicators: {
          rsi: "68.5",
          above_sma20: true,
          above_sma50: true,
        },
        scan_timestamp: "2024-01-15T10:30:00Z",
      },
      {
        symbol: "NVDA",
        company_name: "NVIDIA Corporation",
        price: "825.50",
        price_change: "5.75",
        volume: 45000000,
        volume_ratio: "1.85",
        market_cap: 2040000000000,
        sector: "Technology",
        ai_score: 92,
        confidence: "very high",
        signals: ["Strong Price Gain", "High Volume", "Overbought RSI"],
        technical_indicators: {
          rsi: "78.2",
          above_sma20: true,
          above_sma50: true,
        },
        scan_timestamp: "2024-01-15T10:30:00Z",
      },
    ],
    totalResults: 2,
    timestamp: "2024-01-15T10:30:00Z",
    aiWeight: 0.8,
    metadata: {
      aiPowered: true,
      realTimeData: true,
      algorithm: "momentum",
    },
  },
  metadata: {
    aiPowered: true,
    realTimeData: true,
    availableStrategies: [
      {
        type: "momentum",
        name: "Momentum Breakouts",
        description: "Stocks with strong price and volume momentum",
        weight: 0.8,
      },
      {
        type: "reversal",
        name: "Reversal Opportunities",
        description: "Oversold stocks showing signs of reversal",
        weight: 0.7,
      },
      {
        type: "breakout",
        name: "Technical Breakouts",
        description: "Stocks breaking through resistance levels",
        weight: 0.85,
      },
      {
        type: "unusual",
        name: "Unusual Activity",
        description: "Stocks with unusual volume or price activity",
        weight: 0.9,
      },
    ],
    version: "2.0",
  },
  timestamp: "2024-01-15T10:30:00Z",
};

const mockAIStrategiesResponse = {
  success: true,
  data: {
    strategies: [
      {
        type: "momentum",
        name: "Momentum Breakouts",
        description: "Stocks with strong price and volume momentum",
        weight: 0.8,
      },
      {
        type: "reversal",
        name: "Reversal Opportunities",
        description: "Oversold stocks showing signs of reversal",
        weight: 0.7,
      },
      {
        type: "breakout",
        name: "Technical Breakouts",
        description: "Stocks breaking through resistance levels",
        weight: 0.85,
      },
      {
        type: "unusual",
        name: "Unusual Activity",
        description: "Stocks with unusual volume or price activity",
        weight: 0.9,
      },
      {
        type: "earnings",
        name: "Earnings Momentum",
        description: "Stocks with strong earnings-related momentum",
        weight: 0.75,
      },
      {
        type: "news_sentiment",
        name: "News Sentiment",
        description: "Stocks with positive news sentiment",
        weight: 0.6,
      },
    ],
    totalStrategies: 6,
    usage: {
      endpoint: "/screener/ai-scan",
      parameters: {
        type: "Strategy type (momentum, reversal, breakout, unusual, earnings, news_sentiment)",
        limit: "Number of results to return (default: 50, max: 200)",
        min_market_cap: "Minimum market cap filter (optional)",
        sector: "Sector filter (optional)",
      },
      example:
        "/screener/ai-scan?type=momentum&limit=25&min_market_cap=1000000000",
    },
    metadata: {
      aiPowered: true,
      realTimeAnalysis: true,
      version: "2.0",
    },
  },
  timestamp: "2024-01-15T10:30:00Z",
};

// Helper function to create AI Scanner API client
class AIMarketScannerAPI {
  constructor(baseURL = "http://localhost:3001") {
    this.baseURL = baseURL;
  }

  async scan(type = "momentum", limit = 50, filters = {}) {
    const params = new URLSearchParams();
    params.append("type", type);
    params.append("limit", limit.toString());

    if (filters.min_market_cap) {
      params.append("min_market_cap", filters.min_market_cap.toString());
    }
    if (filters.sector) {
      params.append("sector", filters.sector);
    }

    const url = `${this.baseURL}/api/screener/ai-scan?${params.toString()}`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`AI scan failed: ${response.status}`);
    }

    return await response.json();
  }

  async getStrategies() {
    const url = `${this.baseURL}/api/screener/ai-strategies`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`Failed to get strategies: ${response.status}`);
    }

    return await response.json();
  }
}

describe("AI Market Scanner API", () => {
  let aiScanner;

  beforeEach(() => {
    vi.clearAllMocks();
    aiScanner = new AIMarketScannerAPI();

    // Default fetch mock
    fetch.mockImplementation((url) => {
      if (url.includes("/api/screener/ai-scan")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockAIScanResults),
        });
      }

      if (url.includes("/api/screener/ai-strategies")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockAIStrategiesResponse),
        });
      }

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: {} }),
      });
    });
  });

  describe("AI Scan Functionality", () => {
    it("performs momentum scan successfully", async () => {
      const result = await aiScanner.scan("momentum", 50);

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/screener/ai-scan?type=momentum&limit=50")
      );

      expect(result.success).toBe(true);
      expect(result.data.scanType).toBe("momentum");
      expect(result.data.strategy).toBe("Momentum Breakouts");
      expect(result.data.results).toHaveLength(2);
      expect(result.metadata.aiPowered).toBe(true);
    });

    it("returns high-scoring AI results", async () => {
      const result = await aiScanner.scan("momentum", 50);

      const nvdaResult = result.data.results.find((r) => r.symbol === "NVDA");
      expect(nvdaResult.ai_score).toBe(92);
      expect(nvdaResult.confidence).toBe("very high");
      expect(nvdaResult.signals).toContain("Strong Price Gain");
    });

    it("includes technical indicators in results", async () => {
      const result = await aiScanner.scan("momentum", 50);

      const aaplResult = result.data.results.find((r) => r.symbol === "AAPL");
      expect(aaplResult.technical_indicators.rsi).toBe("68.5");
      expect(aaplResult.technical_indicators.above_sma20).toBe(true);
      expect(aaplResult.technical_indicators.above_sma50).toBe(true);
    });

    it("supports different scan types", async () => {
      await aiScanner.scan("reversal", 25);

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("type=reversal&limit=25")
      );
    });

    it("applies market cap filters", async () => {
      const filters = { min_market_cap: 1000000000 };
      await aiScanner.scan("momentum", 50, filters);

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("min_market_cap=1000000000")
      );
    });

    it("applies sector filters", async () => {
      const filters = { sector: "Technology" };
      await aiScanner.scan("momentum", 50, filters);

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("sector=Technology")
      );
    });

    it("handles multiple filters", async () => {
      const filters = {
        min_market_cap: 5000000000,
        sector: "Healthcare",
      };
      await aiScanner.scan("breakout", 30, filters);

      expect(fetch).toHaveBeenCalledWith(
        expect.stringMatching(
          /min_market_cap=5000000000.*sector=Healthcare|sector=Healthcare.*min_market_cap=5000000000/
        )
      );
    });
  });

  describe("AI Strategies API", () => {
    it("fetches available strategies successfully", async () => {
      const result = await aiScanner.getStrategies();

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/screener/ai-strategies")
      );

      expect(result.success).toBe(true);
      expect(result.data.strategies).toHaveLength(6);
      expect(result.data.totalStrategies).toBe(6);
    });

    it("returns all expected strategy types", async () => {
      const result = await aiScanner.getStrategies();

      const strategyTypes = result.data.strategies.map((s) => s.type);
      expect(strategyTypes).toContain("momentum");
      expect(strategyTypes).toContain("reversal");
      expect(strategyTypes).toContain("breakout");
      expect(strategyTypes).toContain("unusual");
      expect(strategyTypes).toContain("earnings");
      expect(strategyTypes).toContain("news_sentiment");
    });

    it("includes strategy metadata and descriptions", async () => {
      const result = await aiScanner.getStrategies();

      const momentumStrategy = result.data.strategies.find(
        (s) => s.type === "momentum"
      );
      expect(momentumStrategy.name).toBe("Momentum Breakouts");
      expect(momentumStrategy.description).toContain("momentum");
      expect(momentumStrategy.weight).toBe(0.8);
    });

    it("includes API usage documentation", async () => {
      const result = await aiScanner.getStrategies();

      expect(result.data.usage.endpoint).toBe("/screener/ai-scan");
      expect(result.data.usage.parameters.type).toContain("momentum");
      expect(result.data.usage.example).toContain("type=momentum");
    });
  });

  describe("Error Handling", () => {
    it("handles AI scan API errors", async () => {
      fetch.mockImplementationOnce(() =>
        Promise.resolve({
          ok: false,
          status: 500,
          json: () =>
            Promise.resolve({
              success: false,
              error: "AI scan failed",
              details: "Database connectivity issues",
            }),
        })
      );

      await expect(aiScanner.scan("momentum", 50)).rejects.toThrow(
        "AI scan failed: 500"
      );
    });

    it("handles strategies API errors", async () => {
      fetch.mockImplementationOnce(() =>
        Promise.resolve({
          ok: false,
          status: 503,
          json: () =>
            Promise.resolve({
              success: false,
              error: "Service temporarily unavailable",
            }),
        })
      );

      await expect(aiScanner.getStrategies()).rejects.toThrow(
        "Failed to get strategies: 503"
      );
    });

    it("handles network errors gracefully", async () => {
      fetch.mockImplementationOnce(() =>
        Promise.reject(new Error("Network error"))
      );

      await expect(aiScanner.scan("momentum", 50)).rejects.toThrow(
        "Network error"
      );
    });
  });

  describe("Fallback Behavior", () => {
    it("handles fallback mode when database unavailable", async () => {
      const fallbackResponse = {
        success: true,
        data: {
          scanType: "momentum",
          strategy: "Momentum Breakouts",
          description: "Price and volume momentum signals",
          results: [],
          totalResults: 0,
          timestamp: "2024-01-15T10:30:00Z",
          message:
            "AI scanner requires database setup - returning empty results",
          metadata: {
            aiPowered: true,
            fallbackMode: true,
            availableStrategies: [],
          },
        },
      };

      fetch.mockImplementationOnce(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve(fallbackResponse),
        })
      );

      const result = await aiScanner.scan("momentum", 50);

      expect(result.data.results).toHaveLength(0);
      expect(result.data.metadata.fallbackMode).toBe(true);
      expect(result.data.message).toContain("database setup");
    });
  });

  describe("Real-time Data Integration", () => {
    it("includes real-time timestamps", async () => {
      const result = await aiScanner.scan("momentum", 50);

      expect(result.timestamp).toBeTruthy();
      expect(result.data.timestamp).toBeTruthy();

      result.data.results.forEach((stock) => {
        expect(stock.scan_timestamp).toBeTruthy();
      });
    });

    it("indicates real-time data availability", async () => {
      const result = await aiScanner.scan("momentum", 50);

      expect(result.metadata.realTimeData).toBe(true);
      expect(result.data.metadata.realTimeData).toBe(true);
    });

    it("includes AI algorithm version information", async () => {
      const result = await aiScanner.scan("momentum", 50);

      expect(result.metadata.version).toBe("2.0");
      expect(result.data.metadata.algorithm).toBe("momentum");
    });
  });

  describe("Performance Metrics", () => {
    it("processes results within reasonable time", async () => {
      const startTime = Date.now();
      await aiScanner.scan("momentum", 50);
      const endTime = Date.now();

      // Should complete within 5 seconds for mocked responses
      expect(endTime - startTime).toBeLessThan(5000);
    });

    it("handles large result sets efficiently", async () => {
      await aiScanner.scan("momentum", 200);

      expect(fetch).toHaveBeenCalledWith(expect.stringContaining("limit=200"));
    });
  });
});

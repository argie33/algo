/**
 * AI Strategy Generator Service Integration Tests
 * Tests the complete AI strategy generation workflow with real service integration
 */

const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let AIStrategyGenerator;
let app;

describe("AI Strategy Generator Service Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
    AIStrategyGenerator = require("../../../services/aiStrategyGenerator");
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Service Initialization", () => {
    test("should initialize service with proper configuration", () => {
      const generator = new AIStrategyGenerator();
      
      expect(generator).toBeInstanceOf(AIStrategyGenerator);
      expect(generator.aiConfig).toHaveProperty("model", "claude-3-haiku");
      expect(generator.aiConfig).toHaveProperty("maxTokens", 4000);
      expect(generator.aiConfig).toHaveProperty("temperature", 0.1);
      expect(generator.assetTypePatterns).toHaveProperty("stock");
      expect(generator.assetTypePatterns).toHaveProperty("crypto");
      expect(generator.assetTypePatterns).toHaveProperty("etf");
    });

    test("should generate unique correlation IDs", () => {
      const generator1 = new AIStrategyGenerator();
      const generator2 = new AIStrategyGenerator();
      
      expect(generator1.correlationId).toBeDefined();
      expect(generator2.correlationId).toBeDefined();
      expect(generator1.correlationId).not.toBe(generator2.correlationId);
    });
  });

  describe("Strategy Generation Workflow", () => {
    let generator;

    beforeEach(() => {
      generator = new AIStrategyGenerator();
    });

    test("should generate strategy from natural language description", async () => {
      const description = "Buy when RSI is below 30 and sell when RSI is above 70";
      const preferences = {
        risk_level: "medium",
        timeframe: "1day",
        asset_type: "stock"
      };

      const result = await generator.generateStrategy(description, preferences);

      expect(result).toHaveProperty("success", true);
      expect(result).toHaveProperty("strategy");
      expect(result.strategy).toHaveProperty("code");
      expect(result.strategy).toHaveProperty("explanation");
      expect(result.strategy).toHaveProperty("parameters");
      expect(result.strategy.code).toContain("rsi");
      expect(result.strategy.code).toContain("def run_strategy");
    });

    test("should handle different asset types", async () => {
      const description = "Simple moving average crossover strategy";
      
      const stockResult = await generator.generateStrategy(description, {
        risk_level: "low",
        timeframe: "1hour",
        asset_type: "stock"
      });

      const cryptoResult = await generator.generateStrategy(description, {
        risk_level: "high", 
        timeframe: "15min",
        asset_type: "crypto"
      });

      expect(stockResult.success).toBe(true);
      expect(cryptoResult.success).toBe(true);
      expect(stockResult.strategy.code).toContain("sma");
      expect(cryptoResult.strategy.code).toContain("sma");
    });

    test("should validate generated strategies", async () => {
      const description = "Buy AAPL when price increases by 5%";
      const preferences = {
        risk_level: "medium",
        timeframe: "1day",
        asset_type: "stock"
      };

      const result = await generator.generateStrategy(description, preferences);

      expect(result.success).toBe(true);
      expect(result.strategy).toHaveProperty("validation");
      expect(result.strategy.validation).toHaveProperty("valid", true);
      expect(result.strategy.validation).toHaveProperty("errors");
      expect(Array.isArray(result.strategy.validation.errors)).toBe(true);
    });

    test("should handle complex multi-indicator strategies", async () => {
      const description = "Buy when RSI < 30 AND MACD > signal line AND volume > 20-day average, sell when RSI > 70";
      const preferences = {
        risk_level: "high",
        timeframe: "1hour",
        asset_type: "stock"
      };

      const result = await generator.generateStrategy(description, preferences);

      expect(result.success).toBe(true);
      expect(result.strategy.code).toContain("rsi");
      expect(result.strategy.code).toContain("macd");
      expect(result.strategy.code).toContain("volume");
      expect(result.strategy.parameters.length).toBeGreaterThan(2);
    });
  });

  describe("Strategy Optimization", () => {
    let generator;

    beforeEach(() => {
      generator = new AIStrategyGenerator();
    });

    test("should optimize strategy parameters", async () => {
      const strategy = {
        code: "def run_strategy(data, rsi_period=14, rsi_low=30, rsi_high=70):",
        parameters: [
          { name: "rsi_period", type: "int", value: 14, min: 5, max: 50 },
          { name: "rsi_low", type: "float", value: 30, min: 10, max: 40 },
          { name: "rsi_high", type: "float", value: 70, min: 60, max: 90 }
        ]
      };

      const result = await generator.optimizeStrategy(strategy, {
        optimization_method: "grid_search",
        metric: "sharpe_ratio"
      });

      expect(result).toHaveProperty("success", true);
      expect(result).toHaveProperty("optimizedParameters");
      expect(result).toHaveProperty("performance");
      expect(Array.isArray(result.optimizedParameters)).toBe(true);
    });

    test("should provide optimization explanations", async () => {
      const strategy = {
        code: "def run_strategy(data, sma_fast=10, sma_slow=20):",
        parameters: [
          { name: "sma_fast", type: "int", value: 10, min: 5, max: 20 },
          { name: "sma_slow", type: "int", value: 20, min: 15, max: 50 }
        ]
      };

      const result = await generator.optimizeStrategy(strategy, {
        optimization_method: "bayesian",
        metric: "total_return"
      });

      expect(result.success).toBe(true);
      expect(result).toHaveProperty("explanation");
      expect(typeof result.explanation).toBe("string");
      expect(result.explanation.length).toBeGreaterThan(50);
    });
  });

  describe("Strategy Explanation and Documentation", () => {
    let generator;

    beforeEach(() => {
      generator = new AIStrategyGenerator();
    });

    test("should explain strategy logic clearly", async () => {
      const description = "Momentum strategy using RSI and volume";
      const preferences = {
        risk_level: "medium",
        timeframe: "1day",
        asset_type: "stock"
      };

      const result = await generator.generateStrategy(description, preferences);

      expect(result.success).toBe(true);
      expect(result.strategy.explanation).toContain("RSI");
      expect(result.strategy.explanation).toContain("volume");
      expect(result.strategy.explanation.length).toBeGreaterThan(100);
    });

    test("should provide educational content", async () => {
      const strategy = {
        code: "def run_strategy(data): # RSI strategy",
        description: "RSI oversold/overbought strategy"
      };

      const result = await generator.explainStrategy(strategy);

      expect(result).toHaveProperty("success", true);
      expect(result).toHaveProperty("explanation");
      expect(result).toHaveProperty("educational_content");
      expect(result.educational_content).toHaveProperty("concepts");
      expect(result.educational_content).toHaveProperty("risks");
      expect(result.educational_content).toHaveProperty("best_practices");
    });
  });

  describe("Error Handling and Edge Cases", () => {
    let generator;

    beforeEach(() => {
      generator = new AIStrategyGenerator();
    });

    test("should handle invalid strategy descriptions gracefully", async () => {
      const invalidDescription = "";
      const preferences = {
        risk_level: "medium",
        timeframe: "1day",
        asset_type: "stock"
      };

      const result = await generator.generateStrategy(invalidDescription, preferences);

      expect(result).toHaveProperty("success", false);
      expect(result).toHaveProperty("error");
      expect(result.error).toContain("description");
    });

    test("should handle malformed preferences", async () => {
      const description = "Simple SMA crossover";
      const invalidPreferences = {
        risk_level: "invalid_level",
        timeframe: "invalid_timeframe",
        asset_type: "invalid_type"
      };

      const result = await generator.generateStrategy(description, invalidPreferences);

      expect(result).toHaveProperty("success", false);
      expect(result).toHaveProperty("error");
      expect(result.error).toMatch(/preferences|validation/);
    });

    test("should fallback to templates when AI is unavailable", async () => {
      // Simulate AI service unavailable
      generator.bedrockService = null;
      generator.aiConfig.fallbackToTemplates = true;

      const description = "RSI strategy";
      const preferences = {
        risk_level: "medium",
        timeframe: "1day",
        asset_type: "stock"
      };

      const result = await generator.generateStrategy(description, preferences);

      expect(result.success).toBe(true);
      expect(result.strategy.code).toContain("def run_strategy");
      expect(result).toHaveProperty("fallback_used", true);
    });

    test("should handle timeout scenarios", async () => {
      const description = "Complex multi-factor model with 20+ indicators";
      const preferences = {
        risk_level: "high",
        timeframe: "1min",
        asset_type: "crypto"
      };

      // Set a very short timeout for testing
      const originalTimeout = generator.aiConfig.timeout;
      generator.aiConfig.timeout = 100; // 100ms

      const result = await generator.generateStrategy(description, preferences);

      // Should either succeed quickly or fail gracefully with timeout
      expect(typeof result.success).toBe("boolean");
      if (!result.success) {
        expect(result.error).toMatch(/timeout|time|limit/i);
      }

      // Restore original timeout
      generator.aiConfig.timeout = originalTimeout;
    }, 10000);
  });

  describe("Performance and Metrics", () => {
    let generator;

    beforeEach(() => {
      generator = new AIStrategyGenerator();
    });

    test("should track generation performance metrics", async () => {
      const description = "Simple RSI strategy";
      const preferences = {
        risk_level: "medium",
        timeframe: "1day",
        asset_type: "stock"
      };

      const startTime = Date.now();
      const result = await generator.generateStrategy(description, preferences);
      const endTime = Date.now();

      expect(result.success).toBe(true);
      expect(result).toHaveProperty("metadata");
      expect(result.metadata).toHaveProperty("generation_time_ms");
      expect(result.metadata.generation_time_ms).toBeGreaterThan(0);
      expect(result.metadata.generation_time_ms).toBeLessThan(endTime - startTime + 100);
    });

    test("should handle concurrent strategy generation requests", async () => {
      const requests = [];
      for (let i = 0; i < 3; i++) {
        requests.push(
          generator.generateStrategy(`RSI strategy ${i}`, {
            risk_level: "medium",
            timeframe: "1day",
            asset_type: "stock"
          })
        );
      }

      const results = await Promise.all(requests);

      results.forEach((result, index) => {
        expect(result.success).toBe(true);
        expect(result.strategy.code).toContain("rsi");
        expect(result.metadata.correlationId).toBeDefined();
      });

      // All correlation IDs should be different
      const correlationIds = results.map(r => r.metadata.correlationId);
      const uniqueIds = new Set(correlationIds);
      expect(uniqueIds.size).toBe(correlationIds.length);
    });
  });

  describe("Integration with Backend Services", () => {
    test("should integrate with database for strategy storage", async () => {
      const generator = new AIStrategyGenerator();
      const description = "Test strategy for storage";
      const preferences = {
        risk_level: "low",
        timeframe: "1hour",
        asset_type: "stock"
      };

      const result = await generator.generateStrategy(description, preferences);

      expect(result.success).toBe(true);
      
      // Test storage capability
      if (result.strategy && result.strategy.metadata) {
        expect(result.strategy.metadata).toHaveProperty("storage_ready", true);
        expect(result.strategy.metadata).toHaveProperty("schema_version");
      }
    });

    test("should provide strategy export formats", async () => {
      const generator = new AIStrategyGenerator();
      const strategy = {
        code: "def run_strategy(data): pass",
        description: "Test strategy",
        parameters: []
      };

      const exportResult = await generator.exportStrategy(strategy, "json");

      expect(exportResult).toHaveProperty("success", true);
      expect(exportResult).toHaveProperty("exported_strategy");
      expect(typeof exportResult.exported_strategy).toBe("string");
    });
  });
});
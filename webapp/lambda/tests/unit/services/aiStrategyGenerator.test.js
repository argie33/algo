const AIStrategyGenerator = require("../../../services/aiStrategyGenerator");

// Mock dependencies
jest.mock("../../../utils/logger", () => ({
  createLogger: jest.fn().mockReturnValue({
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  }),
}));

describe("AIStrategyGenerator Service", () => {
  let generator;
  let mockLogger;

  beforeEach(() => {
    generator = new AIStrategyGenerator();
    mockLogger = generator.logger;
    jest.clearAllMocks();
  });

  describe("Constructor and Initialization", () => {
    test("should initialize with default configuration", () => {
      expect(generator).toBeInstanceOf(AIStrategyGenerator);
      expect(generator.correlationId).toMatch(/^ai-strategy-\d+-[a-z0-9]+$/);
      expect(generator.aiConfig).toMatchObject({
        model: "claude-3-haiku",
        maxTokens: 4000,
        temperature: 0.1,
        fallbackToTemplates: true,
        streamingEnabled: false,
      });
    });

    test("should have predefined asset type patterns", () => {
      expect(generator.assetTypePatterns).toHaveProperty("stock");
      expect(generator.assetTypePatterns).toHaveProperty("crypto");
      expect(generator.assetTypePatterns).toHaveProperty("etf");

      expect(generator.assetTypePatterns.stock.indicators).toContain("sma");
      expect(generator.assetTypePatterns.stock.indicators).toContain("rsi");
      expect(generator.assetTypePatterns.stock.timeframes).toContain("1day");
      expect(generator.assetTypePatterns.stock.actions).toEqual(["buy", "sell", "hold"]);
    });

    test("should have strategy templates", () => {
      expect(generator.strategyTemplates).toHaveProperty("momentum");
      expect(generator.strategyTemplates).toHaveProperty("mean_reversion");
      expect(generator.strategyTemplates).toHaveProperty("breakout");

      expect(generator.strategyTemplates.momentum).toHaveProperty("description");
      expect(generator.strategyTemplates.momentum).toHaveProperty("code");
      expect(generator.strategyTemplates.momentum).toHaveProperty("parameters");
    });
  });

  describe("generateCorrelationId", () => {
    test("should generate unique correlation IDs", () => {
      const id1 = generator.generateCorrelationId();
      const id2 = generator.generateCorrelationId();

      expect(id1).toMatch(/^ai-strategy-\d+-[a-z0-9]+$/);
      expect(id2).toMatch(/^ai-strategy-\d+-[a-z0-9]+$/);
      expect(id1).not.toBe(id2);
    });
  });

  describe("generateFromNaturalLanguage", () => {
    test("should generate strategy with AI when enabled", async () => {
      const prompt = "Create a momentum strategy for stocks";
      const symbols = ["AAPL", "MSFT", "GOOGL"];
      const options = { timeframe: "1day" };

      // Mock successful AI generation
      jest.spyOn(generator, "generateWithClaude").mockResolvedValue({
        success: true,
        strategy: {
          name: "AI Momentum Strategy",
          description: "AI-generated momentum strategy",
          code: "# AI generated code",
          parameters: { window: 10 },
        },
        metadata: {
          aiGenerated: true,
          confidence: 0.85,
        },
      });

      const result = await generator.generateFromNaturalLanguage(prompt, symbols, options);

      expect(result.success).toBe(true);
      expect(result.strategy.name).toBe("AI Momentum Strategy");
      expect(result.metadata.aiGenerated).toBe(true);
      expect(mockLogger.info).toHaveBeenCalledWith(
        "Generating AI-powered strategy from natural language",
        expect.objectContaining({
          prompt: expect.any(String),
          symbolCount: 3,
          correlationId: generator.correlationId,
          aiEnabled: true,
        })
      );
    });

    test("should fallback to templates when AI fails", async () => {
      const prompt = "Create a momentum strategy for stocks";
      const symbols = ["AAPL"];

      // Mock AI failure
      jest.spyOn(generator, "generateWithClaude").mockResolvedValue({
        success: false,
        error: "AI service unavailable",
      });

      jest.spyOn(generator, "generateWithTemplates").mockResolvedValue({
        success: true,
        strategy: {
          name: "Template Momentum Strategy",
          description: "Template-based strategy",
          code: "# Template code",
        },
        source: "template",
      });

      const result = await generator.generateFromNaturalLanguage(prompt, symbols);

      expect(result.success).toBe(true);
      expect(result.strategy.name).toBe("Template Momentum Strategy");
      expect(result.source).toBe("template");
      expect(mockLogger.warn).toHaveBeenCalledWith(
        "AI generation failed, falling back to templates",
        expect.objectContaining({
          error: "AI service unavailable",
        })
      );
    });

    test("should handle errors gracefully", async () => {
      const prompt = "Invalid prompt";

      // Mock both AI and template failure
      jest.spyOn(generator, "generateWithClaude").mockRejectedValue(new Error("Service error"));
      jest.spyOn(generator, "generateWithTemplates").mockRejectedValue(new Error("Template error"));

      const result = await generator.generateFromNaturalLanguage(prompt);

      expect(result.success).toBe(false);
      expect(result.error).toContain("Failed to generate strategy");
      expect(mockLogger.error).toHaveBeenCalledWith(
        "Strategy generation failed",
        expect.objectContaining({
          error: expect.any(Error),
        })
      );
    });
  });

  describe("generateWithClaude", () => {
    test("should attempt Claude generation but fail due to configuration", async () => {
      const prompt = "Create a trading strategy";
      const symbols = ["AAPL"];

      const result = await generator.generateWithClaude(prompt, symbols);

      expect(result.success).toBe(false);
      expect(result.error).toContain("Claude AI service not configured");
      expect(mockLogger.warn).toHaveBeenCalledWith(
        "Claude AI service not available, using template fallback"
      );
    });

    test("should handle Claude configuration errors", async () => {
      const prompt = "Create a strategy";

      // Test the actual implementation
      const result = await generator.generateWithClaude(prompt);

      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
    });
  });

  describe("generateWithTemplates", () => {
    test("should generate momentum strategy from template", async () => {
      const prompt = "momentum strategy using moving averages";
      const symbols = ["AAPL", "MSFT"];

      const result = await generator.generateWithTemplates(prompt, symbols);

      expect(result.success).toBe(true);
      expect(result.strategy.name).toContain("Momentum");
      expect(result.strategy.code).toBeDefined();
      expect(result.strategy.parameters).toHaveProperty("short_window");
      expect(result.strategy.parameters).toHaveProperty("long_window");
      expect(result.source).toBe("template");
    });

    test("should generate mean reversion strategy from template", async () => {
      const prompt = "mean reversion using RSI";
      const symbols = ["TSLA"];

      const result = await generator.generateWithTemplates(prompt, symbols);

      expect(result.success).toBe(true);
      expect(result.strategy.name).toContain("Mean Reversion");
      expect(result.strategy.parameters).toHaveProperty("rsi_period");
      expect(result.strategy.parameters).toHaveProperty("oversold_threshold");
    });

    test("should generate breakout strategy from template", async () => {
      const prompt = "breakout strategy with bollinger bands";
      const symbols = ["BTC"];

      const result = await generator.generateWithTemplates(prompt, symbols);

      expect(result.success).toBe(true);
      expect(result.strategy.name).toContain("Breakout");
      expect(result.strategy.parameters).toHaveProperty("bb_period");
      expect(result.strategy.parameters).toHaveProperty("bb_std");
    });

    test("should default to momentum strategy for unrecognized prompts", async () => {
      const prompt = "some unknown strategy type";
      const symbols = ["SPY"];

      const result = await generator.generateWithTemplates(prompt, symbols);

      expect(result.success).toBe(true);
      expect(result.strategy.name).toContain("Momentum");
    });

    test("should handle empty symbols gracefully", async () => {
      const prompt = "momentum strategy";
      const symbols = [];

      const result = await generator.generateWithTemplates(prompt, symbols);

      expect(result.success).toBe(true);
      expect(result.strategy.symbols).toEqual([]);
    });
  });

  describe("parseIntent", () => {
    test("should parse buy intent correctly", async () => {
      const prompts = [
        "buy when price goes up",
        "long position on momentum",
        "purchase stocks with strong growth",
      ];

      for (const prompt of prompts) {
        const intent = await generator.parseIntent(prompt);
        expect(intent.action).toBe("buy");
      }
    });

    test("should parse sell intent correctly", async () => {
      const prompts = [
        "sell when RSI is overbought",
        "short the market on reversal",
        "exit positions when declining",
      ];

      for (const prompt of prompts) {
        const intent = await generator.parseIntent(prompt);
        expect(intent.action).toBe("sell");
      }
    });

    test("should parse strategy types correctly", async () => {
      const testCases = [
        { prompt: "momentum strategy with moving averages", expectedType: "momentum" },
        { prompt: "mean reversion using RSI", expectedType: "mean_reversion" },
        { prompt: "breakout trading with bollinger bands", expectedType: "breakout" },
        { prompt: "trend following approach", expectedType: "momentum" },
      ];

      for (const testCase of testCases) {
        const intent = await generator.parseIntent(testCase.prompt);
        expect(intent.strategyType).toBe(testCase.expectedType);
      }
    });

    test("should identify indicators from prompt", async () => {
      const prompt = "use RSI and MACD with bollinger bands for signals";
      const intent = await generator.parseIntent(prompt);

      expect(intent.indicators).toContain("rsi");
      expect(intent.indicators).toContain("macd");
      expect(intent.indicators).toContain("bollinger");
    });

    test("should identify timeframes from prompt", async () => {
      const testCases = [
        { prompt: "daily trading strategy", expected: "1day" },
        { prompt: "hourly signals", expected: "1hour" },
        { prompt: "5 minute scalping", expected: "5min" },
        { prompt: "weekly analysis", expected: "1week" },
      ];

      for (const testCase of testCases) {
        const intent = await generator.parseIntent(testCase.prompt);
        expect(intent.timeframe).toBe(testCase.expected);
      }
    });

    test("should default to unknown action for ambiguous prompts", async () => {
      const prompt = "analyze market conditions";
      const intent = await generator.parseIntent(prompt);

      expect(intent.action).toBe("unknown");
    });
  });

  describe("generateStrategyCode", () => {
    test("should generate code for momentum strategy", async () => {
      const intent = {
        action: "buy",
        strategyType: "momentum",
        indicators: ["sma", "volume"],
        timeframe: "1day",
      };
      const symbols = ["AAPL"];

      const code = await generator.generateStrategyCode(intent, "momentum", symbols);

      expect(code).toContain("def momentum_strategy");
      expect(code).toContain("short_window");
      expect(code).toContain("long_window");
      expect(code).toContain("context.buy");
      expect(code).toContain("context.sell");
      expect(code).toContain("AAPL");
    });

    test("should generate code for mean reversion strategy", async () => {
      const intent = {
        action: "buy",
        strategyType: "mean_reversion",
        indicators: ["rsi"],
        timeframe: "1hour",
      };
      const symbols = ["MSFT"];

      const code = await generator.generateStrategyCode(intent, "mean_reversion", symbols);

      expect(code).toContain("def mean_reversion_strategy");
      expect(code).toContain("rsi_period");
      expect(code).toContain("oversold_threshold");
      expect(code).toContain("overbought_threshold");
      expect(code).toContain("MSFT");
    });

    test("should generate code for breakout strategy", async () => {
      const intent = {
        action: "buy",
        strategyType: "breakout",
        indicators: ["bollinger", "volume"],
        timeframe: "15min",
      };
      const symbols = ["GOOGL"];

      const code = await generator.generateStrategyCode(intent, "breakout", symbols);

      expect(code).toContain("def breakout_strategy");
      expect(code).toContain("bb_period");
      expect(code).toContain("bb_std");
      expect(code).toContain("volume_threshold");
      expect(code).toContain("GOOGL");
    });

    test("should handle multiple symbols in generated code", async () => {
      const intent = { action: "buy", strategyType: "momentum" };
      const symbols = ["AAPL", "MSFT", "GOOGL"];

      const code = await generator.generateStrategyCode(intent, "momentum", symbols);

      symbols.forEach(symbol => {
        expect(code).toContain(symbol);
      });
    });

    test("should include proper error handling in generated code", async () => {
      const intent = { action: "buy", strategyType: "momentum" };
      const symbols = ["SPY"];

      const code = await generator.generateStrategyCode(intent, "momentum", symbols);

      expect(code).toContain("try:");
      expect(code).toContain("except Exception as e:");
      expect(code).toContain("print(f\"Error: {e}\")");
    });
  });

  describe("validateStrategy", () => {
    test("should validate complete strategy successfully", async () => {
      const strategy = {
        name: "Test Strategy",
        description: "A test strategy",
        code: "def test_strategy(): pass",
        parameters: { window: 10 },
        symbols: ["AAPL"],
      };

      const result = await generator.validateStrategy(strategy);

      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    test("should identify missing required fields", async () => {
      const incompleteStrategy = {
        name: "Incomplete Strategy",
        // missing description, code, parameters
      };

      const result = await generator.validateStrategy(incompleteStrategy);

      expect(result.valid).toBe(false);
      expect(result.errors.length).toBeGreaterThan(0);
      expect(result.errors).toEqual(
        expect.arrayContaining([
          expect.stringContaining("description"),
          expect.stringContaining("code"),
          expect.stringContaining("parameters"),
        ])
      );
    });

    test("should validate code syntax", async () => {
      const strategyWithBadCode = {
        name: "Bad Code Strategy",
        description: "Strategy with syntax errors",
        code: "def bad_code( invalid syntax",
        parameters: { window: 10 },
        symbols: ["AAPL"],
      };

      const result = await generator.validateStrategy(strategyWithBadCode);

      expect(result.valid).toBe(false);
      expect(result.errors).toEqual(
        expect.arrayContaining([
          expect.stringContaining("syntax"),
        ])
      );
    });

    test("should validate parameter types", async () => {
      const strategyWithBadParams = {
        name: "Bad Params Strategy",
        description: "Strategy with invalid parameters",
        code: "def strategy(): pass",
        parameters: {
          window: "not_a_number",
          threshold: null,
        },
        symbols: ["AAPL"],
      };

      const result = await generator.validateStrategy(strategyWithBadParams);

      expect(result.valid).toBe(false);
      expect(result.errors.length).toBeGreaterThan(0);
    });

    test("should provide validation warnings for potential issues", async () => {
      const strategy = {
        name: "Risky Strategy",
        description: "A potentially risky strategy",
        code: "def risky_strategy(): context.buy(99999999)", // Very large position
        parameters: { window: 1 }, // Very short window
        symbols: ["PENNY_STOCK"],
      };

      const result = await generator.validateStrategy(strategy);

      expect(result.warnings).toBeDefined();
      expect(result.warnings.length).toBeGreaterThan(0);
    });
  });

  describe("Template Methods", () => {
    test("should return momentum template code", () => {
      const code = generator.getMomentumTemplate();

      expect(code).toContain("def momentum_strategy");
      expect(code).toContain("short_window");
      expect(code).toContain("long_window");
      expect(typeof code).toBe("string");
      expect(code.length).toBeGreaterThan(100);
    });

    test("should return mean reversion template code", () => {
      const code = generator.getMeanReversionTemplate();

      expect(code).toContain("def mean_reversion_strategy");
      expect(code).toContain("rsi_period");
      expect(code).toContain("oversold_threshold");
      expect(typeof code).toBe("string");
      expect(code.length).toBeGreaterThan(100);
    });

    test("should return breakout template code", () => {
      const code = generator.getBreakoutTemplate();

      expect(code).toContain("def breakout_strategy");
      expect(code).toContain("bb_period");
      expect(code).toContain("volume_threshold");
      expect(typeof code).toBe("string");
      expect(code.length).toBeGreaterThan(100);
    });
  });

  describe("AI Helper Methods", () => {
    test("should build system prompt", async () => {
      const symbols = ["AAPL", "MSFT"];
      const options = { timeframe: "1day" };

      const prompt = await generator.buildSystemPrompt(symbols, options);

      expect(typeof prompt).toBe("string");
      expect(prompt).toContain("trading strategy");
      expect(prompt).toContain("Python");
      expect(prompt.length).toBeGreaterThan(50);
    });

    test("should build user prompt", async () => {
      const prompt = "Create a momentum strategy";
      const symbols = ["AAPL"];
      const options = { risk: "low" };

      const userPrompt = await generator.buildUserPrompt(prompt, symbols, options);

      expect(typeof userPrompt).toBe("string");
      expect(userPrompt).toContain(prompt);
      expect(userPrompt).toContain("AAPL");
      expect(userPrompt).toContain("low");
    });

    test("should generate AI metadata", async () => {
      const strategy = { name: "Test Strategy" };
      const prompt = "test prompt";

      const metadata = await generator.generateAIMetadata(strategy, prompt);

      expect(metadata).toHaveProperty("aiConfidence");
      expect(metadata).toHaveProperty("complexityScore");
      expect(metadata).toHaveProperty("estimatedAccuracy");
      expect(typeof metadata.aiConfidence).toBe("number");
      expect(metadata.aiConfidence).toBeGreaterThanOrEqual(0);
      expect(metadata.aiConfidence).toBeLessThanOrEqual(1);
    });

    test("should generate AI visual config", async () => {
      const strategy = { indicators: ["sma", "rsi"] };

      const config = await generator.generateAIVisualConfig(strategy);

      expect(config).toBeDefined();
      expect(typeof config).toBe("object");
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle null or undefined prompts", async () => {
      const results = await Promise.allSettled([
        generator.generateFromNaturalLanguage(null),
        generator.generateFromNaturalLanguage(undefined),
        generator.generateFromNaturalLanguage(""),
      ]);

      results.forEach(result => {
        expect(result.status).toBe("fulfilled");
        expect(result.value.success).toBe(false);
      });
    });

    test("should handle very long prompts", async () => {
      const longPrompt = "a".repeat(10000);

      const result = await generator.generateFromNaturalLanguage(longPrompt);

      expect(result).toHaveProperty("success");
      // Should handle gracefully, either succeed or fail cleanly
    });

    test("should handle special characters in prompts", async () => {
      const specialPrompt = "Create strategy with symbols: $AAPL, @MSFT, #GOOGL!";

      const result = await generator.generateFromNaturalLanguage(specialPrompt);

      expect(result).toHaveProperty("success");
    });

    test("should handle empty symbols array", async () => {
      const prompt = "momentum strategy";
      const result = await generator.generateFromNaturalLanguage(prompt, []);

      expect(result.success).toBe(true);
      expect(result.strategy.symbols).toEqual([]);
    });

    test("should handle very large symbols array", async () => {
      const prompt = "momentum strategy";
      const manySymbols = Array(1000).fill().map((_, i) => `STOCK${i}`);

      const result = await generator.generateFromNaturalLanguage(prompt, manySymbols);

      expect(result).toHaveProperty("success");
    });

    test("should handle invalid options gracefully", async () => {
      const prompt = "momentum strategy";
      const invalidOptions = {
        timeframe: "invalid",
        risk: null,
        nested: { invalid: true },
      };

      const result = await generator.generateFromNaturalLanguage(prompt, ["AAPL"], invalidOptions);

      expect(result).toHaveProperty("success");
    });

    test("should maintain correlation ID consistency", () => {
      const initialId = generator.correlationId;
      
      // Should maintain same ID throughout instance lifecycle
      expect(generator.correlationId).toBe(initialId);
      
      // New instance should have different ID
      const newGenerator = new AIStrategyGenerator();
      expect(newGenerator.correlationId).not.toBe(initialId);
    });

    test("should handle concurrent strategy generation requests", async () => {
      const promises = Array(5).fill().map(() =>
        generator.generateFromNaturalLanguage("momentum strategy", ["AAPL"])
      );

      const results = await Promise.all(promises);

      results.forEach(result => {
        expect(result).toHaveProperty("success");
      });
    });
  });

  describe("Integration with Logger", () => {
    test("should log strategy generation attempts", async () => {
      await generator.generateFromNaturalLanguage("test strategy", ["AAPL"]);

      expect(mockLogger.info).toHaveBeenCalledWith(
        "Generating AI-powered strategy from natural language",
        expect.objectContaining({
          correlationId: generator.correlationId,
        })
      );
    });

    test("should log errors appropriately", async () => {
      // Force an error by mocking template generation to fail
      jest.spyOn(generator, "generateWithTemplates").mockRejectedValue(new Error("Template error"));

      await generator.generateFromNaturalLanguage("test strategy");

      expect(mockLogger.error).toHaveBeenCalledWith(
        "Strategy generation failed",
        expect.objectContaining({
          error: expect.any(Error),
        })
      );
    });

    test("should log warnings for fallback scenarios", async () => {
      // Mock AI failure to trigger fallback
      jest.spyOn(generator, "generateWithClaude").mockResolvedValue({
        success: false,
        error: "AI unavailable",
      });

      jest.spyOn(generator, "generateWithTemplates").mockResolvedValue({
        success: true,
        strategy: { name: "Template Strategy" },
      });

      await generator.generateFromNaturalLanguage("test strategy");

      expect(mockLogger.warn).toHaveBeenCalledWith(
        "AI generation failed, falling back to templates",
        expect.objectContaining({
          error: "AI unavailable",
        })
      );
    });
  });
});
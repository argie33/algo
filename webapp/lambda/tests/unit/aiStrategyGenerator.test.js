/**
 * AI Strategy Generator Unit Tests
 * Tests for NLP-based AI strategy generation functionality
 */

const AIStrategyGenerator = require("../../services/aiStrategyGenerator");

// Mock logger
jest.mock("../../utils/logger", () => ({
  info: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
}));

describe("AI Strategy Generator", () => {
  let generator;

  beforeEach(() => {
    generator = new AIStrategyGenerator();
    jest.clearAllMocks();
  });

  describe("Natural Language Processing", () => {
    it("should parse momentum strategy request", async () => {
      const prompt = "Create a momentum strategy that buys when RSI is above 70 and sells when below 30";
      const symbols = ["AAPL", "MSFT"];
      const options = { userId: "test-user" };

      const result = await generator.generateFromNaturalLanguage(prompt, symbols, options);

      expect(result.success).toBe(true);
      expect(result.strategy).toBeDefined();
      expect(result.strategy.name).toContain("Momentum");
      expect(result.strategy.strategyType).toBe("momentum");
      expect(result.strategy.symbols).toEqual(symbols);
      expect(result.strategy.code).toContain("RSI");
      expect(result.strategy.parameters).toHaveProperty("rsi_threshold");
    });

    it("should parse mean reversion strategy request", async () => {
      const prompt = "Build a mean reversion strategy using Bollinger Bands with 20-period SMA";
      const symbols = ["TSLA"];
      const options = { userId: "test-user", riskLevel: "moderate" };

      const result = await generator.generateFromNaturalLanguage(prompt, symbols, options);

      expect(result.success).toBe(true);
      expect(result.strategy.name).toContain("Mean Reversion");
      expect(result.strategy.strategyType).toBe("mean_reversion");
      expect(result.strategy.code).toContain("bollinger");
      expect(result.strategy.code).toContain("SMA");
      expect(result.strategy.parameters).toHaveProperty("sma_period", 20);
    });

    it("should parse breakout strategy request", async () => {
      const prompt = "Design a breakout strategy that enters positions when price breaks above resistance with high volume";
      const symbols = ["GOOGL"];
      const options = { userId: "test-user" };

      const result = await generator.generateFromNaturalLanguage(prompt, symbols, options);

      expect(result.success).toBe(true);
      expect(result.strategy.strategyType).toBe("breakout");
      expect(result.strategy.code).toContain("volume");
      expect(result.strategy.code).toContain("resistance");
    });

    it("should handle risk management keywords", async () => {
      const prompt = "Create a conservative momentum strategy with 2% stop loss and 3% take profit";
      const symbols = ["SPY"];
      const options = { userId: "test-user", riskLevel: "conservative" };

      const result = await generator.generateFromNaturalLanguage(prompt, symbols, options);

      expect(result.success).toBe(true);
      expect(result.strategy.riskManagement).toBeDefined();
      expect(result.strategy.riskManagement.stopLoss).toBe(0.02);
      expect(result.strategy.riskManagement.takeProfit).toBe(0.03);
      expect(result.strategy.riskLevel).toBe("conservative");
    });

    it("should detect technical indicators in prompt", async () => {
      const prompt = "Use MACD crossover with RSI above 50 and volume greater than average";
      const symbols = ["NVDA"];
      
      const result = await generator.generateFromNaturalLanguage(prompt, symbols);

      expect(result.success).toBe(true);
      expect(result.strategy.technicalIndicators).toContain("MACD");
      expect(result.strategy.technicalIndicators).toContain("RSI");
      expect(result.strategy.technicalIndicators).toContain("Volume");
      expect(result.strategy.code).toContain("macd");
      expect(result.strategy.code).toContain("rsi");
    });

    it("should handle time-based constraints", async () => {
      const prompt = "Create a day trading strategy that only trades during market hours 9:30-4:00";
      const symbols = ["QQQ"];
      
      const result = await generator.generateFromNaturalLanguage(prompt, symbols);

      expect(result.success).toBe(true);
      expect(result.strategy.timeConstraints).toBeDefined();
      expect(result.strategy.timeConstraints.tradingHours).toEqual({
        start: "09:30",
        end: "16:00"
      });
      expect(result.strategy.code).toContain("trading_hours");
    });

    it("should extract position sizing information", async () => {
      const prompt = "Allocate 5% of portfolio per trade with maximum 3 positions";
      const symbols = ["IWM"];
      
      const result = await generator.generateFromNaturalLanguage(prompt, symbols);

      expect(result.success).toBe(true);
      expect(result.strategy.positionSizing).toBeDefined();
      expect(result.strategy.positionSizing.allocationPercent).toBe(0.05);
      expect(result.strategy.positionSizing.maxPositions).toBe(3);
    });
  });

  describe("Strategy Code Generation", () => {
    it("should generate valid Python-like strategy code", async () => {
      const prompt = "Simple RSI strategy";
      const symbols = ["AAPL"];
      
      const result = await generator.generateFromNaturalLanguage(prompt, symbols);

      expect(result.success).toBe(true);
      expect(result.strategy.code).toContain("def");
      expect(result.strategy.code).toContain("rsi");
      expect(result.strategy.code).toContain("return");
      
      // Should have proper structure
      expect(result.strategy.code).toMatch(/def initialize\(.*\):/);
      expect(result.strategy.code).toMatch(/def handle_data\(.*\):/);
    });

    it("should include data validation in generated code", async () => {
      const prompt = "MACD momentum strategy";
      const symbols = ["MSFT"];
      
      const result = await generator.generateFromNaturalLanguage(prompt, symbols);

      expect(result.strategy.code).toContain("if data is None");
      expect(result.strategy.code).toContain("return");
      expect(result.strategy.code).toContain("len(data)");
    });

    it("should generate risk management code", async () => {
      const prompt = "Strategy with 1.5% stop loss";
      const symbols = ["TSLA"];
      
      const result = await generator.generateFromNaturalLanguage(prompt, symbols);

      expect(result.strategy.code).toContain("stop_loss");
      expect(result.strategy.code).toContain("0.015");
      expect(result.strategy.code).toContain("current_price");
    });

    it("should handle multiple symbols in code", async () => {
      const prompt = "Multi-symbol momentum strategy";
      const symbols = ["AAPL", "MSFT", "GOOGL"];
      
      const result = await generator.generateFromNaturalLanguage(prompt, symbols);

      expect(result.strategy.code).toContain("symbols");
      expect(result.strategy.code).toContain("for symbol in");
      symbols.forEach(symbol => {
        expect(result.strategy.code).toContain(`"${symbol}"`);
      });
    });
  });

  describe("Strategy Validation", () => {
    const validStrategy = {
      name: "Test Strategy",
      code: `
def initialize(context):
    context.symbols = ["AAPL"]
    context.rsi_threshold = 70

def handle_data(context, data):
    for symbol in context.symbols:
        if data is None or len(data) < 20:
            return
        rsi = calculate_rsi(data[symbol])
        if rsi > context.rsi_threshold:
            order(symbol, 100)
      `,
      strategyType: "momentum"
    };

    it("should validate correct strategy structure", async () => {
      const validation = await generator.validateStrategy(validStrategy);

      expect(validation.isValid).toBe(true);
      expect(validation.errors).toHaveLength(0);
      expect(validation.score).toBeGreaterThan(0.7);
    });

    it("should detect missing initialize function", async () => {
      const invalidStrategy = {
        ...validStrategy,
        code: `
def handle_data(context, data):
    pass
        `
      };

      const validation = await generator.validateStrategy(invalidStrategy);

      expect(validation.isValid).toBe(false);
      expect(validation.errors).toContain("Missing required initialize() function");
    });

    it("should detect missing handle_data function", async () => {
      const invalidStrategy = {
        ...validStrategy,
        code: `
def initialize(context):
    context.symbols = ["AAPL"]
        `
      };

      const validation = await generator.validateStrategy(invalidStrategy);

      expect(validation.isValid).toBe(false);
      expect(validation.errors).toContain("Missing required handle_data() function");
    });

    it("should validate data validation presence", async () => {
      const strategyWithoutValidation = {
        ...validStrategy,
        code: `
def initialize(context):
    context.symbols = ["AAPL"]

def handle_data(context, data):
    rsi = calculate_rsi(data["AAPL"])
    if rsi > 70:
        order("AAPL", 100)
        `
      };

      const validation = await generator.validateStrategy(strategyWithoutValidation);

      expect(validation.warnings).toContain("Strategy should include data validation checks");
      expect(validation.score).toBeLessThan(0.8);
    });

    it("should check for risk management", async () => {
      const strategyWithoutRisk = {
        ...validStrategy,
        code: `
def initialize(context):
    context.symbols = ["AAPL"]

def handle_data(context, data):
    if data is None:
        return
    order("AAPL", 100)  # No risk management
        `
      };

      const validation = await generator.validateStrategy(strategyWithoutRisk);

      expect(validation.warnings).toContain("Consider adding risk management (stop loss, position sizing)");
    });

    it("should validate technical indicator usage", async () => {
      const validation = await generator.validateStrategy(validStrategy);

      expect(validation.technicalIndicators).toContain("RSI");
      expect(validation.complexity).toBe("medium");
    });

    it("should detect potential infinite loops", async () => {
      const loopStrategy = {
        ...validStrategy,
        code: `
def initialize(context):
    context.symbols = ["AAPL"]

def handle_data(context, data):
    while True:
        order("AAPL", 100)
        `
      };

      const validation = await generator.validateStrategy(loopStrategy);

      expect(validation.errors).toContain("Potential infinite loop detected - use caution with while loops");
    });
  });

  describe("Strategy Templates", () => {
    it("should have predefined strategy templates", () => {
      expect(generator.strategyTemplates).toBeDefined();
      expect(generator.strategyTemplates.momentum).toBeDefined();
      expect(generator.strategyTemplates.mean_reversion).toBeDefined();
      expect(generator.strategyTemplates.breakout).toBeDefined();
      expect(generator.strategyTemplates.arbitrage).toBeDefined();
    });

    it("should have complete template structure", () => {
      const template = generator.strategyTemplates.momentum;
      
      expect(template).toHaveProperty('description');
      expect(template).toHaveProperty('parameters');
      expect(template).toHaveProperty('complexity');
      expect(template).toHaveProperty('riskLevel');
      expect(template).toHaveProperty('timeframe');
      expect(template).toHaveProperty('codeTemplate');
    });

    it("should generate strategy from template", async () => {
      const template = generator.strategyTemplates.momentum;
      const symbols = ["AAPL"];
      const parameters = {
        rsi_threshold: 70,
        position_size: 100
      };

      const strategy = generator.generateFromTemplate("momentum", symbols, parameters);

      expect(strategy.name).toContain("Momentum");
      expect(strategy.strategyType).toBe("momentum");
      expect(strategy.code).toContain("rsi");
      expect(strategy.code).toContain("70");
      expect(strategy.parameters).toEqual(parameters);
    });
  });

  describe("Performance Metrics", () => {
    it("should estimate strategy performance metrics", async () => {
      const strategy = {
        name: "Test Strategy",
        strategyType: "momentum",
        riskLevel: "moderate",
        technicalIndicators: ["RSI", "MACD"]
      };

      const metrics = generator.estimatePerformance(strategy);

      expect(metrics).toHaveProperty('expectedReturn');
      expect(metrics).toHaveProperty('expectedVolatility');
      expect(metrics).toHaveProperty('sharpeRatio');
      expect(metrics).toHaveProperty('maxDrawdown');
      expect(metrics).toHaveProperty('winRate');
      expect(metrics).toHaveProperty('confidenceLevel');

      // Validate ranges
      expect(metrics.expectedReturn).toBeGreaterThan(-1);
      expect(metrics.expectedReturn).toBeLessThan(2);
      expect(metrics.expectedVolatility).toBeGreaterThan(0);
      expect(metrics.winRate).toBeGreaterThanOrEqual(0);
      expect(metrics.winRate).toBeLessThanOrEqual(1);
    });

    it("should adjust metrics based on risk level", async () => {
      const conservativeStrategy = {
        name: "Conservative Strategy",
        strategyType: "mean_reversion",
        riskLevel: "conservative"
      };

      const aggressiveStrategy = {
        name: "Aggressive Strategy", 
        strategyType: "momentum",
        riskLevel: "aggressive"
      };

      const conservativeMetrics = generator.estimatePerformance(conservativeStrategy);
      const aggressiveMetrics = generator.estimatePerformance(aggressiveStrategy);

      expect(conservativeMetrics.expectedVolatility)
        .toBeLessThan(aggressiveMetrics.expectedVolatility);
      expect(conservativeMetrics.maxDrawdown)
        .toBeLessThan(aggressiveMetrics.maxDrawdown);
    });
  });

  describe("Error Handling", () => {
    it("should handle empty prompt", async () => {
      const result = await generator.generateFromNaturalLanguage("", ["AAPL"]);

      expect(result.success).toBe(false);
      expect(result.error).toContain("prompt");
    });

    it("should handle empty symbols array", async () => {
      const result = await generator.generateFromNaturalLanguage("Create a momentum strategy", []);

      expect(result.success).toBe(false);
      expect(result.error).toContain("symbols");
    });

    it("should handle invalid strategy type", async () => {
      const prompt = "Create a quantum entanglement trading strategy";
      const result = await generator.generateFromNaturalLanguage(prompt, ["AAPL"]);

      expect(result.success).toBe(true);
      // Should default to a valid strategy type
      expect(['momentum', 'mean_reversion', 'breakout', 'arbitrage'])
        .toContain(result.strategy.strategyType);
    });

    it("should handle validation of malformed code", async () => {
      const malformedStrategy = {
        name: "Bad Strategy",
        code: "this is not valid python code {[}]",
        strategyType: "momentum"
      };

      const validation = await generator.validateStrategy(malformedStrategy);

      expect(validation.isValid).toBe(false);
      expect(validation.errors.length).toBeGreaterThan(0);
    });

    it("should handle null/undefined strategy", async () => {
      const validation1 = await generator.validateStrategy(null);
      const validation2 = await generator.validateStrategy(undefined);

      expect(validation1.isValid).toBe(false);
      expect(validation2.isValid).toBe(false);
      expect(validation1.errors).toContain("Strategy cannot be null or undefined");
      expect(validation2.errors).toContain("Strategy cannot be null or undefined");
    });
  });

  describe("Natural Language Understanding", () => {
    it("should understand complex strategy descriptions", async () => {
      const complexPrompt = `
        Create a sophisticated momentum strategy that:
        1. Uses 14-period RSI and MACD for entry signals
        2. Implements 2% stop loss and 4% take profit
        3. Only trades during high volatility periods (VIX > 20)
        4. Limits position size to 3% of portfolio per trade
        5. Avoids trading 30 minutes before and after market close
      `;
      
      const result = await generator.generateFromNaturalLanguage(complexPrompt, ["SPY"]);

      expect(result.success).toBe(true);
      expect(result.strategy.parameters.rsi_period).toBe(14);
      expect(result.strategy.riskManagement.stopLoss).toBe(0.02);
      expect(result.strategy.riskManagement.takeProfit).toBe(0.04);
      expect(result.strategy.positionSizing.allocationPercent).toBe(0.03);
      expect(result.strategy.code).toContain("vix");
      expect(result.strategy.timeConstraints).toBeDefined();
    });

    it("should understand comparative language", async () => {
      const prompt = "Buy when RSI is higher than 70 but lower than 85";
      const result = await generator.generateFromNaturalLanguage(prompt, ["AAPL"]);

      expect(result.success).toBe(true);
      expect(result.strategy.code).toContain("rsi > 70");
      expect(result.strategy.code).toContain("rsi < 85");
    });

    it("should understand negation", async () => {
      const prompt = "Don't trade when volume is below average";
      const result = await generator.generateFromNaturalLanguage(prompt, ["MSFT"]);

      expect(result.success).toBe(true);
      expect(result.strategy.code).toContain("volume >= average_volume");
    });

    it("should understand conditional logic", async () => {
      const prompt = "If RSI > 70 then sell, else if RSI < 30 then buy";
      const result = await generator.generateFromNaturalLanguage(prompt, ["TSLA"]);

      expect(result.success).toBe(true);
      expect(result.strategy.code).toContain("if rsi > 70:");
      expect(result.strategy.code).toContain("elif rsi < 30:");
      expect(result.strategy.code).toContain("order_target_percent");
    });
  });

  describe("Integration with Portfolio Analytics", () => {
    it("should consider portfolio correlation in multi-symbol strategies", async () => {
      const prompt = "Create a diversified strategy across tech and finance sectors";
      const symbols = ["AAPL", "MSFT", "JPM", "BAC"];
      
      const result = await generator.generateFromNaturalLanguage(prompt, symbols);

      expect(result.success).toBe(true);
      expect(result.strategy.diversification).toBeDefined();
      expect(result.strategy.sectorWeights).toBeDefined();
      expect(result.strategy.code).toContain("sector_allocation");
    });

    it("should include portfolio rebalancing logic", async () => {
      const prompt = "Rebalance portfolio monthly to maintain equal weights";
      const symbols = ["SPY", "QQQ", "IWM"];
      
      const result = await generator.generateFromNaturalLanguage(prompt, symbols);

      expect(result.success).toBe(true);
      expect(result.strategy.rebalancing).toBeDefined();
      expect(result.strategy.rebalancing.frequency).toBe("monthly");
      expect(result.strategy.code).toContain("rebalance");
      expect(result.strategy.code).toContain("equal_weight");
    });
  });
});
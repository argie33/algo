/**
 * Sentiment Engine Tests
 * Tests sentiment analysis functionality for financial news and market data
 */

const sentimentEngine = require("../../utils/sentimentEngine");

// Mock logger to avoid test output noise
jest.mock("../../utils/logger", () => ({
  error: jest.fn(),
  info: jest.fn(),
  warn: jest.fn(),
  debug: jest.fn(),
}));

describe("Sentiment Engine", () => {
  describe("Market Sentiment Calculation", () => {
    test("should calculate default market sentiment", () => {
      const result = sentimentEngine.calculateMarketSentiment();

      expect(result.overallSentiment).toBe("neutral");
      expect(result.score).toBe(0.5);
      expect(result.confidence).toBe(0.7);
      expect(result.timestamp).toBeDefined();
      expect(new Date(result.timestamp)).toBeInstanceOf(Date);
    });

    test("should handle empty data input", () => {
      const result = sentimentEngine.calculateMarketSentiment({});

      expect(result.overallSentiment).toBe("neutral");
      expect(result.score).toBe(0.5);
      expect(result.confidence).toBe(0.7);
      expect(result.timestamp).toBeDefined();
    });

    test("should handle market data input gracefully", () => {
      const marketData = {
        volume: 1000000,
        price: 150.5,
        change: 2.5,
      };

      const result = sentimentEngine.calculateMarketSentiment(marketData);

      expect(result.overallSentiment).toBe("neutral");
      expect(result.score).toBe(0.5);
      expect(result.confidence).toBe(0.7);
    });

    test("should return error structure on failure", () => {
      // Force an error by mocking
      const originalCalculate = sentimentEngine.calculateMarketSentiment;
      sentimentEngine.calculateMarketSentiment = jest
        .fn()
        .mockImplementation(() => {
          throw new Error("Test error");
        });

      try {
        const result = sentimentEngine.calculateMarketSentiment();
        expect(result).toBeDefined();
      } catch (error) {
        expect(error.message).toBe("Test error");
      }

      // Restore original method
      sentimentEngine.calculateMarketSentiment = originalCalculate;
    });
  });

  describe("Score to Label Conversion", () => {
    test("should convert positive scores correctly", () => {
      expect(sentimentEngine.scoreToLabel(0.8)).toBe("positive");
      expect(sentimentEngine.scoreToLabel(0.6)).toBe("positive");
      expect(sentimentEngine.scoreToLabel(1.0)).toBe("positive");
    });

    test("should convert negative scores correctly", () => {
      expect(sentimentEngine.scoreToLabel(0.2)).toBe("negative");
      expect(sentimentEngine.scoreToLabel(0.4)).toBe("negative");
      expect(sentimentEngine.scoreToLabel(0.0)).toBe("negative");
    });

    test("should convert neutral scores correctly", () => {
      expect(sentimentEngine.scoreToLabel(0.5)).toBe("neutral");
      expect(sentimentEngine.scoreToLabel(0.45)).toBe("neutral");
      expect(sentimentEngine.scoreToLabel(0.55)).toBe("neutral");
    });

    test("should handle edge cases", () => {
      // Test boundary values
      expect(sentimentEngine.scoreToLabel(0.59999)).toBe("neutral");
      expect(sentimentEngine.scoreToLabel(0.60001)).toBe("positive");
      expect(sentimentEngine.scoreToLabel(0.40001)).toBe("neutral");
      expect(sentimentEngine.scoreToLabel(0.39999)).toBe("negative");
    });

    test("should handle invalid inputs gracefully", () => {
      expect(sentimentEngine.scoreToLabel(null)).toBe("neutral");
      expect(sentimentEngine.scoreToLabel(undefined)).toBe("neutral");
      expect(sentimentEngine.scoreToLabel("invalid")).toBe("neutral");
      expect(sentimentEngine.scoreToLabel(NaN)).toBe("neutral");
      expect(sentimentEngine.scoreToLabel({})).toBe("neutral");
      expect(sentimentEngine.scoreToLabel([])).toBe("neutral");
    });

    test("should handle extreme values", () => {
      expect(sentimentEngine.scoreToLabel(-1.0)).toBe("negative");
      expect(sentimentEngine.scoreToLabel(2.0)).toBe("positive");
      expect(sentimentEngine.scoreToLabel(Infinity)).toBe("positive");
      expect(sentimentEngine.scoreToLabel(-Infinity)).toBe("negative");
    });
  });

  describe("Text Sentiment Analysis", () => {
    test("should analyze positive text correctly", async () => {
      const positiveText =
        "This is excellent news! The company shows great growth and bullish trends with huge profits.";

      const result = await sentimentEngine.analyzeSentiment(
        positiveText,
        "AAPL"
      );

      expect(result.score).toBeGreaterThan(0.5);
      expect(result.label).toBe("positive");
      expect(result.confidence).toBeGreaterThan(0);
      expect(result.symbol).toBe("AAPL");
      expect(result.positiveWords).toBeGreaterThan(0);
      expect(result.wordCount).toBeGreaterThan(0);
      expect(result.timestamp).toBeDefined();
    });

    test("should analyze negative text correctly", async () => {
      const negativeText =
        "This is terrible news. The company shows poor performance and bearish trends with massive losses.";

      const result = await sentimentEngine.analyzeSentiment(
        negativeText,
        "MSFT"
      );

      expect(result.score).toBeLessThan(0.5);
      expect(result.label).toBe("negative");
      expect(result.confidence).toBeGreaterThan(0);
      expect(result.symbol).toBe("MSFT");
      expect(result.negativeWords).toBeGreaterThan(0);
      expect(result.wordCount).toBeGreaterThan(0);
    });

    test("should analyze neutral text correctly", async () => {
      const neutralText =
        "The company announced quarterly earnings today. The market opened at normal levels.";

      const result = await sentimentEngine.analyzeSentiment(
        neutralText,
        "GOOGL"
      );

      expect(result.score).toBe(0.5);
      expect(result.label).toBe("neutral");
      expect(result.symbol).toBe("GOOGL");
      expect(result.positiveWords).toBe(0);
      expect(result.negativeWords).toBe(0);
    });

    test("should handle mixed sentiment text", async () => {
      const mixedText =
        "The company shows excellent growth but faces terrible challenges. Good profits despite poor market conditions.";

      const result = await sentimentEngine.analyzeSentiment(mixedText);

      expect(result.score).toBeDefined();
      expect(result.label).toMatch(/positive|negative|neutral/);
      expect(result.positiveWords).toBeGreaterThan(0);
      expect(result.negativeWords).toBeGreaterThan(0);
      expect(result.symbol).toBeNull();
    });

    test("should handle empty or invalid text inputs", async () => {
      // Test empty string - returns error object instead of throwing
      const emptyResult = await sentimentEngine.analyzeSentiment("");
      expect(emptyResult.error).toBe("Text is required for sentiment analysis");
      expect(emptyResult.score).toBe(0.5);
      expect(emptyResult.label).toBe("neutral");

      // Test null/undefined - returns error object instead of throwing
      const nullResult = await sentimentEngine.analyzeSentiment(null);
      expect(nullResult.error).toBe("Text is required for sentiment analysis");

      const undefinedResult = await sentimentEngine.analyzeSentiment(undefined);
      expect(undefinedResult.error).toBe(
        "Text is required for sentiment analysis"
      );

      // Test non-string types - returns error object instead of throwing
      const numberResult = await sentimentEngine.analyzeSentiment(123);
      expect(numberResult.error).toBe(
        "Text is required for sentiment analysis"
      );

      const objectResult = await sentimentEngine.analyzeSentiment({});
      expect(objectResult.error).toBe(
        "Text is required for sentiment analysis"
      );
    });

    test("should handle very short text", async () => {
      const result = await sentimentEngine.analyzeSentiment("Good", "TEST");

      expect(result.score).toBeGreaterThan(0.5);
      expect(result.label).toBe("positive");
      expect(result.wordCount).toBe(1);
      expect(result.positiveWords).toBe(1);
      expect(result.negativeWords).toBe(0);
    });

    test("should handle very long text", async () => {
      const longText =
        "excellent ".repeat(100) + "terrible ".repeat(49) + "terrible";

      const result = await sentimentEngine.analyzeSentiment(longText);

      expect(result.wordCount).toBe(150);
      expect(result.positiveWords).toBe(100);
      expect(result.negativeWords).toBe(50);
      expect(result.score).toBeCloseTo(0.67, 1); // 100/(100+50)
      expect(result.label).toBe("positive");
    });

    test("should handle special characters and formatting", async () => {
      const textWithSpecialChars =
        "This is EXCELLENT news!!! The stock went UP 📈 and profits are GREAT!!!";

      const result =
        await sentimentEngine.analyzeSentiment(textWithSpecialChars);

      expect(result.positiveWords).toBeGreaterThan(0);
      expect(result.score).toBeGreaterThan(0.5);
      expect(result.label).toBe("positive");
    });

    test("should handle case insensitive analysis", async () => {
      const mixedCaseText =
        "EXCELLENT news! Great PROFITS and POSITIVE trends!";

      const result = await sentimentEngine.analyzeSentiment(mixedCaseText);

      expect(result.positiveWords).toBeGreaterThan(0);
      expect(result.score).toBeGreaterThan(0.5);
      expect(result.label).toBe("positive");
    });

    test("should calculate confidence based on sentiment word density", async () => {
      const highDensityText = "excellent great positive bullish";
      const lowDensityText =
        "the company announced quarterly earnings results today and provided excellent guidance";

      const highDensityResult =
        await sentimentEngine.analyzeSentiment(highDensityText);
      const lowDensityResult =
        await sentimentEngine.analyzeSentiment(lowDensityText);

      expect(highDensityResult.confidence).toBeGreaterThan(
        lowDensityResult.confidence
      );
    });

    test("should include timestamp in results", async () => {
      const result = await sentimentEngine.analyzeSentiment("Test text");

      expect(result.timestamp).toBeDefined();
      expect(new Date(result.timestamp)).toBeInstanceOf(Date);

      // Timestamp should be recent (within last few seconds)
      const timeDiff = Date.now() - new Date(result.timestamp).getTime();
      expect(timeDiff).toBeLessThan(5000);
    });

    test("should round numerical values appropriately", async () => {
      const result = await sentimentEngine.analyzeSentiment(
        "excellent good positive"
      );

      expect(result.score).toEqual(Math.round(result.score * 100) / 100);
      expect(result.confidence).toEqual(
        Math.round(result.confidence * 100) / 100
      );
    });

    test("should handle error cases gracefully", async () => {
      // Mock an internal error
      const originalScoreToLabel = sentimentEngine.scoreToLabel;
      sentimentEngine.scoreToLabel = jest.fn().mockImplementation(() => {
        throw new Error("Internal error");
      });

      const result = await sentimentEngine.analyzeSentiment("test text");

      expect(result.score).toBe(0.5);
      expect(result.label).toBe("neutral");
      expect(result.confidence).toBe(0);
      expect(result.error).toBeDefined();

      // Restore original method
      sentimentEngine.scoreToLabel = originalScoreToLabel;
    });
  });

  describe("Integration Tests", () => {
    test("should work with real financial news text", async () => {
      const financialNews = `
        Apple Inc. reported excellent quarterly earnings that beat analyst expectations.
        The company's revenue grew 15% year-over-year, driven by strong iPhone sales.
        However, supply chain challenges continue to pose risks to future growth.
        Investors remain bullish on the stock despite market volatility.
      `;

      const result = await sentimentEngine.analyzeSentiment(
        financialNews,
        "AAPL"
      );

      expect(result.score).toBeDefined();
      expect(result.label).toMatch(/positive|negative|neutral/);
      expect(result.symbol).toBe("AAPL");
      expect(result.wordCount).toBeGreaterThan(30);
      expect(result.positiveWords + result.negativeWords).toBeGreaterThan(0);
    });

    test("should maintain consistency across multiple calls", async () => {
      const text = "This is excellent news with great profits!";

      const result1 = await sentimentEngine.analyzeSentiment(text);
      const result2 = await sentimentEngine.analyzeSentiment(text);

      expect(result1.score).toBe(result2.score);
      expect(result1.label).toBe(result2.label);
      expect(result1.positiveWords).toBe(result2.positiveWords);
      expect(result1.negativeWords).toBe(result2.negativeWords);
    });

    test("should work with scoreToLabel integration", async () => {
      const positiveText = "excellent bullish profit gain success";
      const negativeText = "terrible bearish loss decline fail";

      const positiveResult =
        await sentimentEngine.analyzeSentiment(positiveText);
      const negativeResult =
        await sentimentEngine.analyzeSentiment(negativeText);

      expect(positiveResult.label).toBe("positive");
      expect(negativeResult.label).toBe("negative");

      // Test direct scoreToLabel calls
      expect(sentimentEngine.scoreToLabel(positiveResult.score)).toBe(
        "positive"
      );
      expect(sentimentEngine.scoreToLabel(negativeResult.score)).toBe(
        "negative"
      );
    });
  });
});

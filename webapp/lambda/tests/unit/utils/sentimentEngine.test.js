/**
 * Unit tests for SentimentEngine
 */

// Mock logger
const mockLogger = {
  error: jest.fn(),
  warn: jest.fn(),
  info: jest.fn(),
};
jest.mock("../../../utils/logger", () => mockLogger);

const sentimentEngine = require("../../../utils/sentimentEngine");

describe("SentimentEngine", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("calculateMarketSentiment", () => {
    test("should return neutral sentiment with default values", () => {
      const result = sentimentEngine.calculateMarketSentiment();

      expect(result).toEqual({
        overallSentiment: "neutral",
        score: 0.5,
        confidence: 0.7,
        timestamp: expect.stringMatching(
          /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/
        ),
      });
    });

    test("should accept data parameter", () => {
      const testData = { someData: "value" };
      const result = sentimentEngine.calculateMarketSentiment(testData);

      expect(result.overallSentiment).toBe("neutral");
      expect(result.score).toBe(0.5);
      expect(result.confidence).toBe(0.7);
    });

    test("should handle errors gracefully", () => {
      // Force an error by mocking Date constructor to throw
      const originalDate = Date;
      global.Date = jest.fn(() => {
        throw new Error("Date error");
      });
      global.Date.now = originalDate.now;

      const result = sentimentEngine.calculateMarketSentiment();

      expect(result).toEqual({
        overallSentiment: "neutral",
        score: 0.5,
        confidence: 0,
        error: "Date error",
      });

      expect(mockLogger.error).toHaveBeenCalledWith(
        "Market sentiment calculation failed:",
        expect.any(Error)
      );

      // Restore Date
      global.Date = originalDate;
    });
  });

  describe("scoreToLabel", () => {
    test('should return "positive" for high scores', () => {
      expect(sentimentEngine.scoreToLabel(0.6)).toBe("positive");
      expect(sentimentEngine.scoreToLabel(0.8)).toBe("positive");
      expect(sentimentEngine.scoreToLabel(1.0)).toBe("positive");
    });

    test('should return "negative" for low scores', () => {
      expect(sentimentEngine.scoreToLabel(0.4)).toBe("negative");
      expect(sentimentEngine.scoreToLabel(0.2)).toBe("negative");
      expect(sentimentEngine.scoreToLabel(0.0)).toBe("negative");
    });

    test('should return "neutral" for middle scores', () => {
      expect(sentimentEngine.scoreToLabel(0.5)).toBe("neutral");
      expect(sentimentEngine.scoreToLabel(0.45)).toBe("neutral");
      expect(sentimentEngine.scoreToLabel(0.55)).toBe("neutral");
    });

    test("should handle invalid inputs", () => {
      expect(sentimentEngine.scoreToLabel(null)).toBe("neutral");
      expect(sentimentEngine.scoreToLabel(undefined)).toBe("neutral");
      expect(sentimentEngine.scoreToLabel("not a number")).toBe("neutral");
      expect(sentimentEngine.scoreToLabel(NaN)).toBe("neutral");
    });

    test("should handle errors gracefully", () => {
      // Mock the function to throw an error
      const originalScoreToLabel = sentimentEngine.scoreToLabel;
      sentimentEngine.scoreToLabel = jest.fn(() => {
        throw new Error("Conversion error");
      });

      // Call the original function with mocked implementation
      sentimentEngine.scoreToLabel = originalScoreToLabel;

      // Force an error by mocking isNaN to throw
      const originalIsNaN = global.isNaN;
      global.isNaN = jest.fn(() => {
        throw new Error("isNaN error");
      });

      const result = sentimentEngine.scoreToLabel(0.5);

      expect(result).toBe("neutral");
      expect(mockLogger.error).toHaveBeenCalledWith(
        "Score to label conversion failed:",
        expect.any(Error)
      );

      // Restore
      global.isNaN = originalIsNaN;
    });
  });

  describe("analyzeSentiment", () => {
    test("should analyze positive sentiment text", async () => {
      const positiveText =
        "This is great news! The stock is bullish and shows excellent gains.";

      const result = await sentimentEngine.analyzeSentiment(
        positiveText,
        "AAPL"
      );

      expect(result.score).toBeGreaterThan(0.5);
      expect(result.label).toBe("positive");
      expect(result.confidence).toBeGreaterThan(0.3);
      expect(result.symbol).toBe("AAPL");
      expect(result.positiveWords).toBeGreaterThan(0);
      expect(result.negativeWords).toBe(0);
      expect(result.wordCount).toBe(12); // Actual word count
      expect(result.timestamp).toMatch(
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/
      );
    });

    test("should analyze negative sentiment text", async () => {
      const negativeText =
        "This is terrible news. The stock is bearish with poor performance and losses.";

      const result = await sentimentEngine.analyzeSentiment(negativeText);

      expect(result.score).toBeLessThan(0.5);
      expect(result.label).toBe("negative");
      expect(result.confidence).toBeGreaterThan(0.3);
      expect(result.symbol).toBeNull();
      expect(result.positiveWords).toBe(0);
      expect(result.negativeWords).toBeGreaterThan(0);
      expect(result.wordCount).toBe(13);
    });

    test("should analyze neutral text", async () => {
      const neutralText = "The company released quarterly earnings today.";

      const result = await sentimentEngine.analyzeSentiment(
        neutralText,
        "TSLA"
      );

      expect(result.score).toBe(0.5);
      expect(result.label).toBe("neutral");
      expect(result.confidence).toBe(0.3);
      expect(result.symbol).toBe("TSLA");
      expect(result.positiveWords).toBe(0);
      expect(result.negativeWords).toBe(0);
      expect(result.wordCount).toBe(6);
    });

    test("should analyze mixed sentiment text", async () => {
      const mixedText =
        "Good profits this quarter but bad outlook for next year.";

      const result = await sentimentEngine.analyzeSentiment(mixedText);

      // "Good" and "profits" are positive, "bad" is negative = 2 positive, 1 negative
      expect(result.score).toBe(0.67); // 2/(2+1) = 0.67
      expect(result.label).toBe("positive"); // 0.67 > 0.6
      expect(result.positiveWords).toBe(2);
      expect(result.negativeWords).toBe(1);
      expect(result.wordCount).toBe(10);
    });

    test("should handle case insensitive matching", async () => {
      const upperCaseText = "EXCELLENT PROFITS AND GREAT SUCCESS!";

      const result = await sentimentEngine.analyzeSentiment(upperCaseText);

      expect(result.score).toBe(1.0); // All positive words
      expect(result.label).toBe("positive");
      expect(result.positiveWords).toBe(4); // excellent, profits, great, success
    });

    test("should handle partial word matches", async () => {
      const partialText = "The profitability looks good with successful gains.";

      const result = await sentimentEngine.analyzeSentiment(partialText);

      expect(result.positiveWords).toBeGreaterThan(0); // Should match "good", "success", "gain"
      expect(result.label).toBe("positive");
    });

    test("should calculate confidence based on sentiment word density", async () => {
      const highDensityText =
        "good great excellent positive bullish profit success";
      const lowDensityText =
        "The quarterly earnings report was released today and it shows good results overall.";

      const highDensityResult =
        await sentimentEngine.analyzeSentiment(highDensityText);
      const lowDensityResult =
        await sentimentEngine.analyzeSentiment(lowDensityText);

      expect(highDensityResult.confidence).toBeGreaterThan(
        lowDensityResult.confidence
      );
    });

    test("should handle empty or invalid text input", async () => {
      const emptyResult = await sentimentEngine.analyzeSentiment("");
      const nullResult = await sentimentEngine.analyzeSentiment(null);
      const undefinedResult = await sentimentEngine.analyzeSentiment(undefined);

      [emptyResult, nullResult, undefinedResult].forEach((result) => {
        expect(result.score).toBe(0.5);
        expect(result.label).toBe("neutral");
        expect(result.confidence).toBe(0);
        expect(result.error).toBe("Text is required for sentiment analysis");
        expect(result.symbol).toBeNull();
      });
    });

    test("should handle non-string input", async () => {
      const numberResult = await sentimentEngine.analyzeSentiment(123);
      const objectResult = await sentimentEngine.analyzeSentiment({
        text: "hello",
      });
      const arrayResult = await sentimentEngine.analyzeSentiment([
        "hello",
        "world",
      ]);

      [numberResult, objectResult, arrayResult].forEach((result) => {
        expect(result.score).toBe(0.5);
        expect(result.label).toBe("neutral");
        expect(result.confidence).toBe(0);
        expect(result.error).toBe("Text is required for sentiment analysis");
      });
    });

    test("should round score and confidence to 2 decimal places", async () => {
      const text = "good excellent great"; // 3 positive words out of 3 total

      const result = await sentimentEngine.analyzeSentiment(text);

      expect(result.score.toString()).toMatch(/^\d+(\.\d{1,2})?$/);
      expect(result.confidence.toString()).toMatch(/^\d+(\.\d{1,2})?$/);
    });

    test("should cap confidence at 0.8", async () => {
      // Create text with very high sentiment word density
      const highDensityText = Array(20).fill("excellent").join(" ");

      const result = await sentimentEngine.analyzeSentiment(highDensityText);

      expect(result.confidence).toBeLessThanOrEqual(0.8);
    });

    test("should handle symbol parameter correctly", async () => {
      const text = "good news";

      const withSymbol = await sentimentEngine.analyzeSentiment(text, "MSFT");
      const withoutSymbol = await sentimentEngine.analyzeSentiment(text);
      const withNullSymbol = await sentimentEngine.analyzeSentiment(text, null);

      expect(withSymbol.symbol).toBe("MSFT");
      expect(withoutSymbol.symbol).toBeNull();
      expect(withNullSymbol.symbol).toBeNull();
    });

    test("should handle errors during analysis gracefully", async () => {
      // Mock split to throw an error
      const originalSplit = String.prototype.split;
      String.prototype.split = jest.fn(() => {
        throw new Error("Split error");
      });

      const result = await sentimentEngine.analyzeSentiment("test text");

      expect(result.score).toBe(0.5);
      expect(result.label).toBe("neutral");
      expect(result.confidence).toBe(0);
      expect(result.error).toBe("Split error");
      expect(mockLogger.error).toHaveBeenCalledWith(
        "Sentiment analysis failed:",
        expect.any(Error)
      );

      // Restore
      String.prototype.split = originalSplit;
    });

    test("should handle edge case with only whitespace", async () => {
      const whitespaceText = "   \t  \n  ";

      const result = await sentimentEngine.analyzeSentiment(whitespaceText);

      expect(result.score).toBe(0.5);
      expect(result.label).toBe("neutral");
      expect(result.confidence).toBe(0.3);
      expect(result.positiveWords).toBe(0);
      expect(result.negativeWords).toBe(0);
      expect(result.wordCount).toBeGreaterThan(0); // whitespace creates empty strings when split
    });

    test("should validate all required fields in response", async () => {
      const result = await sentimentEngine.analyzeSentiment("test");

      expect(result).toHaveProperty("score");
      expect(result).toHaveProperty("label");
      expect(result).toHaveProperty("confidence");
      expect(result).toHaveProperty("symbol");
      expect(result).toHaveProperty("wordCount");
      expect(result).toHaveProperty("positiveWords");
      expect(result).toHaveProperty("negativeWords");
      expect(result).toHaveProperty("timestamp");

      expect(typeof result.score).toBe("number");
      expect(typeof result.label).toBe("string");
      expect(typeof result.confidence).toBe("number");
      expect(typeof result.wordCount).toBe("number");
      expect(typeof result.positiveWords).toBe("number");
      expect(typeof result.negativeWords).toBe("number");
      expect(typeof result.timestamp).toBe("string");
    });
  });

  describe("integration tests", () => {
    test("should maintain consistent scoring across multiple calls", async () => {
      const text = "This is excellent news with great profits!";

      const result1 = await sentimentEngine.analyzeSentiment(text);
      const result2 = await sentimentEngine.analyzeSentiment(text);
      const result3 = await sentimentEngine.analyzeSentiment(text);

      expect(result1.score).toBe(result2.score);
      expect(result2.score).toBe(result3.score);
      expect(result1.label).toBe(result2.label);
      expect(result2.label).toBe(result3.label);
    });

    test("should handle complex real-world text samples", async () => {
      const complexText = `
        Apple Inc. reported excellent quarterly earnings with great profits exceeding expectations.
        However, the company also mentioned some challenges ahead including poor market conditions
        and potential losses in certain segments. Overall, the bullish sentiment remains strong
        despite these negative factors. Analysts remain positive about the company's success.
      `;

      const result = await sentimentEngine.analyzeSentiment(
        complexText,
        "AAPL"
      );

      expect(result.score).toBeGreaterThan(0.5); // More positive than negative words
      expect(result.label).toBe("positive");
      expect(result.symbol).toBe("AAPL");
      expect(result.positiveWords).toBeGreaterThan(result.negativeWords);
      expect(result.confidence).toBeGreaterThan(0.3);
      expect(result.wordCount).toBeGreaterThan(40);
    });
  });
});

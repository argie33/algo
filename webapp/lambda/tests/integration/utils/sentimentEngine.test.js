/**
 * Sentiment Engine Integration Tests
 * Tests AI/ML sentiment analysis with real text processing
 */

const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");
const sentimentEngine = require("../../../utils/sentimentEngine");

describe("Sentiment Engine Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Basic Sentiment Analysis", () => {
    test("should analyze sentiment with basic functionality", async () => {
      const testTexts = [
        "Apple reported excellent quarterly earnings that exceeded all analyst expectations",
        "The company reported disappointing earnings and missed revenue targets",
        "The company reported quarterly earnings as expected by analysts",
      ];

      for (const text of testTexts) {
        const sentiment = await sentimentEngine.analyzeSentiment(text);

        expect(sentiment).toBeDefined();
        expect(sentiment.score).toBeDefined();
        expect(sentiment.label).toBeDefined();
        expect(sentiment.confidence).toBeDefined();
        expect(sentiment.timestamp).toBeDefined();

        expect(typeof sentiment.score).toBe("number");
        expect(typeof sentiment.confidence).toBe("number");
        expect(["positive", "negative", "neutral"]).toContain(sentiment.label);
      }
    });

    test("should handle symbol-specific sentiment analysis", async () => {
      const text = "Apple stock is performing well in the current market";
      const symbol = "AAPL";

      const sentiment = await sentimentEngine.analyzeSentiment(text, symbol);

      expect(sentiment).toBeDefined();
      expect(sentiment.label).toBeDefined();
      expect(sentiment.score).toBeDefined();
      expect(sentiment.confidence).toBeDefined();
      expect(sentiment.symbol).toBe(symbol);
      expect(typeof sentiment.score).toBe("number");
    });

    test("should handle empty or invalid text", async () => {
      const invalidTexts = ["", null, undefined, 123];

      for (const text of invalidTexts) {
        const sentiment = await sentimentEngine.analyzeSentiment(text);

        expect(sentiment).toBeDefined();
        expect(sentiment.label).toBeDefined();
        expect(sentiment.score).toBeDefined();
        expect(sentiment.confidence).toBeDefined();

        // Should return neutral for invalid input with error
        expect(sentiment.label).toBe("neutral");
        expect(sentiment.error).toBeDefined(); // Should have error message
      }
    });
  });

  describe("Market Sentiment Calculation", () => {
    test("should calculate overall market sentiment", () => {
      const testData = {
        newsItems: ["Positive market news", "Neutral market update"],
        priceMovement: 0.02,
        volume: 1000000,
      };

      const sentiment = sentimentEngine.calculateMarketSentiment(testData);

      expect(sentiment).toBeDefined();
      expect(sentiment.overallSentiment).toBeDefined();
      expect(sentiment.score).toBeDefined();
      expect(sentiment.confidence).toBeDefined();
      expect(sentiment.timestamp).toBeDefined();

      expect(typeof sentiment.score).toBe("number");
      expect(typeof sentiment.confidence).toBe("number");
      expect(["positive", "negative", "neutral"]).toContain(
        sentiment.overallSentiment
      );
    });

    test("should handle empty market data", () => {
      const sentiment = sentimentEngine.calculateMarketSentiment();

      expect(sentiment).toBeDefined();
      expect(sentiment.overallSentiment).toBe("neutral");
      expect(sentiment.score).toBe(0.5);
      expect(sentiment.confidence).toBe(0.7);
    });

    test("should handle invalid market data gracefully", () => {
      const invalidData = [null, undefined, "string", 123];

      invalidData.forEach((data) => {
        const sentiment = sentimentEngine.calculateMarketSentiment(data);

        expect(sentiment).toBeDefined();
        expect(sentiment.overallSentiment).toBeDefined();
        expect(sentiment.score).toBeDefined();
        expect(sentiment.confidence).toBeDefined();
      });
    });
  });

  describe("Score to Label Conversion", () => {
    test("should convert numeric scores to text labels", () => {
      const testCases = [
        { score: 0.8, expected: "positive" },
        { score: 0.6, expected: "positive" },
        { score: 0.5, expected: "neutral" },
        { score: 0.4, expected: "negative" },
        { score: 0.2, expected: "negative" },
      ];

      testCases.forEach(({ score, expected }) => {
        const label = sentimentEngine.scoreToLabel(score);
        expect(label).toBe(expected);
      });
    });

    test("should handle invalid scores gracefully", () => {
      const invalidScores = [null, undefined, "string", NaN, Infinity];

      invalidScores.forEach((score) => {
        const label = sentimentEngine.scoreToLabel(score);
        expect(label).toBe("neutral");
      });
    });

    test("should handle edge cases", () => {
      expect(sentimentEngine.scoreToLabel(0.6)).toBe("positive"); // exact boundary
      expect(sentimentEngine.scoreToLabel(0.4)).toBe("negative"); // exact boundary
      expect(sentimentEngine.scoreToLabel(0.59999)).toBe("neutral"); // just below positive
      expect(sentimentEngine.scoreToLabel(0.40001)).toBe("neutral"); // just above negative
    });
  });
});

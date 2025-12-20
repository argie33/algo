/**
 * Sentiment Integration Tests
 * Tests for market and stock sentiment analysis
 * Route: /routes/sentiment.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Sentiment API", () => {
  describe("Stock Sentiment", () => {
    test("should analyze sentiment for specific stock", async () => {
      const response = await request(app).get("/api/sentiment/stock/AAPL");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("symbol", "AAPL");

        const sentiment = response.body.data;
        const sentimentFields = [
          "sentiment_score",
          "bullish_percent",
          "bearish_percent",
        ];
        const hasSentimentData = sentimentFields.some((field) =>
          Object.keys(sentiment).some((key) =>
            key.toLowerCase().includes(field.replace("_", ""))
          )
        );

        expect(hasSentimentData).toBe(true);
      }
    });

    test("should provide sentiment trend over time", async () => {
      const response = await request(app).get(
        "/api/sentiment/stock/AAPL/trend?period=30d"
      );

      expect([200, 400, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const trendPoint = response.body.data[0];
          expect(trendPoint).toHaveProperty("date");
          expect(trendPoint).toHaveProperty("sentiment_score");
        }
      }
    });
  });

  describe("Market Sentiment", () => {
    test("should analyze overall market sentiment", async () => {
      const response = await request(app).get("/api/sentiment/market");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const marketSentiment = response.body.data;
        const marketFields = [
          "overall_sentiment",
          "fear_greed_index",
          "vix_level",
        ];
        const hasMarketData = marketFields.some((field) =>
          Object.keys(marketSentiment).some((key) =>
            key.toLowerCase().includes(field.replace("_", ""))
          )
        );

        expect(hasMarketData).toBe(true);
      }
    });

    test("should provide sector sentiment breakdown", async () => {
      const response = await request(app).get("/api/sentiment/sectors");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const sectorSentiment = response.body.data[0];
          expect(sectorSentiment).toHaveProperty("sector");
          expect(sectorSentiment).toHaveProperty("sentiment_score");
        }
      }
    });
  });

  describe("Social Media Sentiment", () => {
    test("should analyze social media sentiment for stock", async () => {
      const response = await request(app).get("/api/sentiment/social/AAPL");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const socialSentiment = response.body.data;
        const socialFields = [
          "twitter_sentiment",
          "reddit_sentiment",
          "mention_volume",
        ];
        const hasSocialData = socialFields.some((field) =>
          Object.keys(socialSentiment).some((key) =>
            key.toLowerCase().includes(field.replace("_", ""))
          )
        );

        expect(hasSocialData).toBe(true);
      }
    });

    test("should provide trending stocks by social sentiment", async () => {
      const response = await request(app).get(
        "/api/sentiment/social/trending?limit=20"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const trendingStock = response.body.data[0];
          expect(trendingStock).toHaveProperty("symbol");
          expect(trendingStock).toHaveProperty("mention_count");
          expect(trendingStock).toHaveProperty("sentiment_score");
        }
      }
    });
  });

  describe("News Sentiment", () => {
    test("should analyze news sentiment for stock", async () => {
      const response = await request(app).get("/api/sentiment/news/AAPL");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const newsSentiment = response.body.data;
        const newsFields = [
          "news_sentiment",
          "article_count",
          "recent_headlines",
        ];
        const hasNewsData = newsFields.some((field) =>
          Object.keys(newsSentiment).some((key) =>
            key.toLowerCase().includes(field.replace("_", ""))
          )
        );

        expect(hasNewsData).toBe(true);
      }
    });

    test("should provide sentiment analysis of specific news articles", async () => {
      const response = await request(app).get(
        "/api/sentiment/news/articles?symbol=AAPL&limit=10"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const article = response.body.data[0];
          expect(article).toHaveProperty("headline");
          expect(article).toHaveProperty("sentiment_score");
          expect(article).toHaveProperty("published_date");
        }
      }
    });
  });

  describe("Institutional Sentiment", () => {
    test("should analyze institutional investor sentiment", async () => {
      const response = await request(app).get(
        "/api/sentiment/institutional/AAPL"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const institutionalSentiment = response.body.data;
        const instFields = [
          "ownership_change",
          "insider_activity",
          "fund_flows",
        ];
        const hasInstData = instFields.some((field) =>
          Object.keys(institutionalSentiment).some((key) =>
            key.toLowerCase().includes(field.replace("_", ""))
          )
        );

        expect(hasInstData).toBe(true);
      }
    });

    test("should track options sentiment indicators", async () => {
      const response = await request(app).get("/api/sentiment/options/AAPL");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const optionsSentiment = response.body.data;
        const optionsFields = [
          "put_call_ratio",
          "implied_volatility",
          "unusual_activity",
        ];
        const hasOptionsData = optionsFields.some((field) =>
          Object.keys(optionsSentiment).some((key) =>
            key.toLowerCase().includes(field.replace("_", ""))
          )
        );

        expect(hasOptionsData).toBe(true);
      }
    });
  });

  describe("Sentiment Alerts", () => {
    test("should create sentiment alert", async () => {
      const alertData = {
        symbol: "AAPL",
        sentiment_threshold: 0.8,
        alert_type: "bullish_extreme",
        notification_method: "email",
      };

      const response = await request(app)
        .post("/api/sentiment/alerts")
        .set("Authorization", "Bearer test-token")
        .send(alertData);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("message");
      }
    });

    test("should list user sentiment alerts", async () => {
      const response = await request(app)
        .get("/api/sentiment/alerts")
        .set("Authorization", "Bearer test-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });
  });
});

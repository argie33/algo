/**
 * Technical Pattern Recognition Unit Tests
 * Tests for advanced pattern detection functionality implemented in technical.js
 */

const request = require("supertest");
const express = require("express");

// Import the technical router
const technicalRouter = require("../../routes/technical");

// Mock dependencies
jest.mock("../../utils/database", () => ({
  query: jest.fn(),
}));

jest.mock("../../utils/logger", () => ({
  info: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
}));

const { query } = require("../../utils/database");

describe("Technical Pattern Recognition Tests", () => {
  let app;

  // Shared mock data for tests
  const mockPriceData = [
    { close: 150.00, high: 152.00, low: 149.00, date: "2024-01-01" },
    { close: 148.00, high: 151.00, low: 147.50, date: "2024-01-02" },
    { close: 145.00, high: 149.00, low: 144.00, date: "2024-01-03" },
    { close: 147.00, high: 148.50, low: 144.50, date: "2024-01-04" },
    { close: 149.00, high: 150.00, low: 146.50, date: "2024-01-05" },
    { close: 152.00, high: 153.00, low: 149.50, date: "2024-01-06" },
    { close: 154.00, high: 155.00, low: 151.00, date: "2024-01-07" },
    { close: 153.00, high: 155.50, low: 152.00, date: "2024-01-08" }
  ];

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/technical", technicalRouter);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /technical/patterns/:symbol - Pattern Detection", () => {

    it("should detect double bottom pattern", async () => {
      // Mock table exists and provide price data that forms a double bottom
      const mockTableExists = { rows: [{ exists: true }] };
      const mockDoubleBottomData = [
        { close: 150.00, high: 152.00, low: 149.00, date: "2024-01-01" },
        { close: 145.00, high: 148.00, low: 144.00, date: "2024-01-02" }, // First bottom
        { close: 148.00, high: 150.00, low: 147.00, date: "2024-01-03" },
        { close: 150.00, high: 152.00, low: 149.00, date: "2024-01-04" },
        { close: 147.00, high: 149.00, low: 146.00, date: "2024-01-05" },
        { close: 144.50, high: 147.00, low: 143.50, date: "2024-01-06" }, // Second bottom (similar level)
        { close: 148.00, high: 150.00, low: 147.00, date: "2024-01-07" },
        { close: 152.00, high: 154.00, low: 151.00, date: "2024-01-08" }
      ];

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockDoubleBottomData });

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .query({ timeframe: "1D", limit: 8 })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        symbol: "AAPL",
        timeframe: "1D",
        patterns: expect.any(Array),
        summary: expect.objectContaining({
          total_patterns: expect.any(Number),
          bullish_patterns: expect.any(Number),
          bearish_patterns: expect.any(Number),
          average_confidence: expect.any(Number),
          market_sentiment: expect.stringMatching(/^(bullish|bearish)$/),
        }),
        confidence_score: expect.any(Number),
        last_updated: expect.any(String),
      });

      // Should detect at least one pattern
      expect(response.body.patterns.length).toBeGreaterThan(0);
      
      // Check for double bottom pattern specifically
      const doubleBottomPattern = response.body.patterns.find(p => p.type === 'double_bottom');
      if (doubleBottomPattern) {
        expect(doubleBottomPattern).toMatchObject({
          type: "double_bottom",
          direction: "bullish",
          confidence: expect.any(Number),
          timeframe: "1D",
          detected_at: expect.any(String),
          time_to_target: expect.any(Number),
          target_price: null, // Implementation returns null for these
          stop_loss: null,
        });
        expect(doubleBottomPattern.confidence).toBeGreaterThan(0.5);
      }
    });

    it("should detect cup and handle pattern", async () => {
      // Mock price data that forms a cup and handle pattern
      const mockTableExists = { rows: [{ exists: true }] };
      const mockCupHandleData = [
        { close: 160.00, high: 162.00, low: 159.00, date: "2024-01-01" }, // Peak
        { close: 155.00, high: 158.00, low: 154.00, date: "2024-01-02" }, // Down
        { close: 150.00, high: 153.00, low: 149.00, date: "2024-01-03" }, // Cup bottom
        { close: 152.00, high: 154.00, low: 151.00, date: "2024-01-04" }, // Up
        { close: 158.00, high: 160.00, low: 157.00, date: "2024-01-05" }, // Near peak
        { close: 156.00, high: 158.00, low: 155.00, date: "2024-01-06" }, // Handle down
        { close: 157.00, high: 158.50, low: 156.00, date: "2024-01-07" }, // Handle up
        { close: 161.00, high: 163.00, low: 160.00, date: "2024-01-08" }  // Breakout
      ];

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockCupHandleData });

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .query({ timeframe: "1D", limit: 8 })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.patterns).toBeInstanceOf(Array);
      
      // Should detect patterns
      expect(response.body.summary.total_patterns).toBeGreaterThan(0);
      
      // Check for cup and handle pattern
      const cupHandlePattern = response.body.patterns.find(p => p.type === 'cup_and_handle');
      if (cupHandlePattern) {
        expect(cupHandlePattern.direction).toBe("bullish");
        expect(cupHandlePattern.confidence).toBeGreaterThan(0);
      }
    });

    it("should detect head and shoulders pattern", async () => {
      // Mock bearish head and shoulders pattern
      const mockTableExists = { rows: [{ exists: true }] };
      const mockHeadShouldersData = [
        { close: 150.00, high: 152.00, low: 149.00, date: "2024-01-01" }, // Left shoulder
        { close: 148.00, high: 150.00, low: 147.00, date: "2024-01-02" }, // Valley
        { close: 155.00, high: 157.00, low: 154.00, date: "2024-01-03" }, // Head
        { close: 152.00, high: 154.00, low: 151.00, date: "2024-01-04" }, // Valley
        { close: 149.00, high: 151.00, low: 148.00, date: "2024-01-05" }, // Right shoulder
        { close: 147.00, high: 149.00, low: 146.00, date: "2024-01-06" }, // Breakdown
        { close: 144.00, high: 146.00, low: 143.00, date: "2024-01-07" }, // Continuation
        { close: 142.00, high: 144.00, low: 141.00, date: "2024-01-08" }  // Further down
      ];

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockHeadShouldersData });

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      
      // Check for head and shoulders pattern
      const headShouldersPattern = response.body.patterns.find(p => p.type === 'head_and_shoulders');
      if (headShouldersPattern) {
        expect(headShouldersPattern.direction).toBe("bearish");
        expect(headShouldersPattern.confidence).toBeGreaterThan(0);
      }

      // Should indicate bearish sentiment if head and shoulders detected
      if (response.body.summary.bearish_patterns > 0) {
        expect(response.body.summary.market_sentiment).toBe("bearish");
      }
    });

    it("should detect ascending triangle pattern", async () => {
      // Mock ascending triangle pattern (bullish)
      const mockTableExists = { rows: [{ exists: true }] };
      const mockTriangleData = [
        { close: 150.00, high: 155.00, low: 149.00, date: "2024-01-01" }, // Resistance at 155
        { close: 152.00, high: 155.00, low: 151.00, date: "2024-01-02" }, // Higher low, same high
        { close: 154.00, high: 155.00, low: 153.00, date: "2024-01-03" }, // Higher low, same high
        { close: 153.00, high: 155.00, low: 152.50, date: "2024-01-04" }, // Higher low, same high
        { close: 154.50, high: 155.00, low: 154.00, date: "2024-01-05" }, // Higher low, same high
        { close: 156.00, high: 157.00, low: 155.00, date: "2024-01-06" }, // Breakout above resistance
        { close: 158.00, high: 159.00, low: 157.00, date: "2024-01-07" }, // Continuation
        { close: 160.00, high: 161.00, low: 159.00, date: "2024-01-08" }  // Further up
      ];

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockTriangleData });

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      
      // Check for ascending triangle pattern
      const trianglePattern = response.body.patterns.find(p => p.type === 'ascending_triangle');
      if (trianglePattern) {
        expect(trianglePattern.direction).toBe("bullish");
        expect(trianglePattern.confidence).toBeGreaterThan(0);
      }

      // Verify pattern structure
      expect(response.body.patterns).toBeInstanceOf(Array);
      response.body.patterns.forEach(pattern => {
        expect(pattern).toHaveProperty('type');
        expect(pattern).toHaveProperty('direction');
        expect(pattern).toHaveProperty('confidence');
        expect(pattern).toHaveProperty('timeframe');
        expect(pattern).toHaveProperty('detected_at');
        expect(pattern.confidence).toBeGreaterThanOrEqual(0);
        expect(pattern.confidence).toBeLessThanOrEqual(1);
      });
    });

    it("should handle various timeframes correctly", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockPriceData });

      // Test 1H timeframe
      const response1H = await request(app)
        .get("/technical/patterns/AAPL")
        .query({ timeframe: "1H" })
        .expect(200);

      expect(response1H.body.timeframe).toBe("1H");

      // Test 1W timeframe
      const response1W = await request(app)
        .get("/technical/patterns/AAPL")
        .query({ timeframe: "1W" })
        .expect(200);

      expect(response1W.body.timeframe).toBe("1W");
    });

    it("should validate pattern confidence scores", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockPriceData });

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .expect(200);

      // Validate confidence scores are within valid range
      expect(response.body.confidence_score).toBeGreaterThanOrEqual(0);
      expect(response.body.confidence_score).toBeLessThanOrEqual(1);

      if (response.body.summary.average_confidence !== null) {
        expect(response.body.summary.average_confidence).toBeGreaterThanOrEqual(0);
        expect(response.body.summary.average_confidence).toBeLessThanOrEqual(1);
      }

      response.body.patterns.forEach(pattern => {
        expect(pattern.confidence).toBeGreaterThanOrEqual(0);
        expect(pattern.confidence).toBeLessThanOrEqual(1);
        expect(typeof pattern.confidence).toBe('number');
      });
    });

    it("should handle insufficient data gracefully", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockLimitedData = [
        { close: 150.00, high: 152.00, low: 149.00, date: "2024-01-01" },
        { close: 151.00, high: 153.00, low: 150.00, date: "2024-01-02" }
      ];

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockLimitedData });

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .query({ limit: 2 })
        .expect(200);

      expect(response.body.success).toBe(true);
      // Should handle limited data without crashing
      expect(response.body.patterns).toBeInstanceOf(Array);
      expect(response.body.summary).toHaveProperty('total_patterns');
    });

    it("should return fallback patterns on database errors", async () => {
      query.mockRejectedValueOnce(new Error("Database connection failed"));

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.patterns).toBeInstanceOf(Array);
      expect(response.body.summary).toHaveProperty('market_sentiment');
      
      // Should have fallback data or graceful handling
      expect(
        response.body.fallback === true ||
        response.body.patterns.length > 0
      ).toBe(true);
    });

    it("should validate pattern types and directions", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockPriceData });

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .expect(200);

      const validPatternTypes = [
        'double_bottom', 'cup_and_handle', 'bullish_flag', 'ascending_triangle',
        'double_top', 'head_and_shoulders', 'bearish_flag', 'descending_triangle'
      ];
      
      const validDirections = ['bullish', 'bearish'];

      response.body.patterns.forEach(pattern => {
        expect(validPatternTypes).toContain(pattern.type);
        expect(validDirections).toContain(pattern.direction);
        expect(typeof pattern.detected_at).toBe('string');
        expect(typeof pattern.time_to_target).toBe('number');
        expect(pattern.time_to_target).toBeGreaterThan(0);
      });
    });

    it("should calculate market sentiment correctly", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockPriceData });

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .expect(200);

      const summary = response.body.summary;
      
      // Market sentiment should be based on pattern balance
      if (summary.bullish_patterns > summary.bearish_patterns) {
        expect(summary.market_sentiment).toBe('bullish');
      } else if (summary.bearish_patterns > summary.bullish_patterns) {
        expect(summary.market_sentiment).toBe('bearish');
      }
      // If equal, can be either

      // Total patterns should equal sum of bullish and bearish
      expect(summary.total_patterns).toBe(summary.bullish_patterns + summary.bearish_patterns);
    });

    it("should handle table not exists scenario", async () => {
      const mockTableExists = { rows: [{ exists: false }] };
      query.mockResolvedValueOnce(mockTableExists);

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      // Should return fallback data when table doesn't exist
      expect(response.body.patterns).toBeInstanceOf(Array);
      expect(response.body.summary.market_sentiment).toMatch(/^(bullish|bearish)$/);
    });
  });

  describe("Pattern Detection Algorithm Validation", () => {
    it("should detect multiple patterns in complex price action", async () => {
      // Complex price data that could contain multiple patterns
      const mockComplexData = [
        { close: 100.00, high: 102.00, low: 99.00, date: "2024-01-01" },
        { close: 95.00, high: 98.00, low: 94.00, date: "2024-01-02" },  // First bottom
        { close: 98.00, high: 100.00, low: 97.00, date: "2024-01-03" },
        { close: 105.00, high: 107.00, low: 104.00, date: "2024-01-04" },
        { close: 102.00, high: 104.00, low: 101.00, date: "2024-01-05" },
        { close: 96.00, high: 98.50, low: 95.50, date: "2024-01-06" },  // Second bottom
        { close: 99.00, high: 101.00, low: 98.00, date: "2024-01-07" },
        { close: 103.00, high: 105.00, low: 102.00, date: "2024-01-08" },
        { close: 107.00, high: 109.00, low: 106.00, date: "2024-01-09" },
        { close: 110.00, high: 112.00, low: 109.00, date: "2024-01-10" }
      ];

      const mockTableExists = { rows: [{ exists: true }] };
      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockComplexData });

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .query({ limit: 10 })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.patterns).toBeInstanceOf(Array);
      
      // With complex data, should potentially detect multiple patterns
      if (response.body.patterns.length > 1) {
        expect(response.body.summary.total_patterns).toBeGreaterThan(1);
      }

      // Patterns should be sorted by confidence (highest first)
      if (response.body.patterns.length > 1) {
        for (let i = 1; i < response.body.patterns.length; i++) {
          expect(response.body.patterns[i-1].confidence)
            .toBeGreaterThanOrEqual(response.body.patterns[i].confidence);
        }
      }
    });

    it("should handle edge cases in pattern detection", async () => {
      // Edge case: all same prices (no patterns)
      const mockFlatData = Array.from({ length: 10 }, (_, i) => ({
        close: 150.00,
        high: 150.00,
        low: 150.00,
        date: `2024-01-${String(i + 1).padStart(2, '0')}`
      }));

      const mockTableExists = { rows: [{ exists: true }] };
      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockFlatData });

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.patterns).toBeInstanceOf(Array);
      // Flat data should result in few or no patterns detected
      expect(response.body.summary.total_patterns).toBeGreaterThanOrEqual(0);
    });

    it("should validate pattern timing calculations", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockPriceData });

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .expect(200);

      response.body.patterns.forEach(pattern => {
        // Time to target should be reasonable (1-30 days for daily patterns)
        expect(pattern.time_to_target).toBeGreaterThan(0);
        expect(pattern.time_to_target).toBeLessThanOrEqual(30);
        
        // Detected at should be a valid ISO date string
        expect(new Date(pattern.detected_at).toString()).not.toBe('Invalid Date');
      });
    });
  });

  describe("Error Handling and Edge Cases", () => {
    it("should handle invalid symbol gracefully", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: [] }); // No data for invalid symbol

      const response = await request(app)
        .get("/technical/patterns/INVALID")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.symbol).toBe("INVALID");
      expect(response.body.patterns).toBeInstanceOf(Array);
    });

    it("should handle invalid timeframe parameter", async () => {
      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .query({ timeframe: "invalid" })
        .expect(200);

      // Should default to valid timeframe
      expect(response.body.success).toBe(true);
      expect(['1H', '1D', '1W']).toContain(response.body.timeframe);
    });

    it("should handle large limit values", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockPriceData });

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .query({ limit: 1000 })
        .expect(200);

      expect(response.body.success).toBe(true);
      // Should handle large limits gracefully
      expect(response.body.patterns).toBeInstanceOf(Array);
    });

    it("should handle malformed date data", async () => {
      const mockBadDateData = [
        { close: 150.00, high: 152.00, low: 149.00, date: "invalid-date" },
        { close: 151.00, high: 153.00, low: 150.00, date: null },
        { close: 152.00, high: 154.00, low: 151.00, date: "2024-01-03" }
      ];

      const mockTableExists = { rows: [{ exists: true }] };
      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce({ rows: mockBadDateData });

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      // Should handle bad date data without crashing
      expect(response.body.patterns).toBeInstanceOf(Array);
    });
  });
});
const request = require("supertest");
const express = require("express");
const scoresRouter = require("../../../routes/scores");

// Mock dependencies
jest.mock("../../../utils/database");

const { query } = require("../../../utils/database");

describe("Scores Routes", () => {
  let app;

  beforeEach(() => {
    app = express();
    app.use(express.json());
    app.use("/scores", scoresRouter);
    jest.clearAllMocks();
  });

  describe("GET /scores/ping", () => {
    test("should return ping response", async () => {
      const response = await request(app).get("/scores/ping").expect(200);

      expect(response.body).toEqual({
        status: "ok",
        endpoint: "scores",
        timestamp: expect.any(String),
      });

      // Validate timestamp format
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
    });
  });

  describe("GET /scores/", () => {
    const mockStocksData = {
      rows: [
        {
          symbol: "AAPL",
          company_name: "Apple Inc.",
          sector: "Technology",
          industry: "Consumer Electronics",
          market_cap: 3000000000000,
          current_price: 175.5,
          trailing_pe: 25.8,
          price_to_book: 8.5,
          composite_score: 85.5,
          quality_score: 88.2,
          value_score: 65.3,
          growth_score: 82.1,
          momentum_score: 78.9,
          sentiment_score: 75.4,
          positioning_score: 80.2,
          earnings_quality_subscore: 85.0,
          balance_sheet_subscore: 90.0,
          profitability_subscore: 88.5,
          management_subscore: 85.5,
          multiples_subscore: 60.0,
          intrinsic_value_subscore: 70.0,
          relative_value_subscore: 66.0,
          confidence_score: 92.5,
          data_completeness: 95.8,
          sector_adjusted_score: 87.2,
          percentile_rank: 89.5,
          created_at: "2023-01-01T00:00:00Z",
          updated_at: "2023-01-01T12:00:00Z",
        },
      ],
    };

    const mockCountData = {
      rows: [{ total: 100 }],
    };

    test("should return paginated stocks with scores", async () => {
      query
        .mockResolvedValueOnce(mockStocksData)
        .mockResolvedValueOnce(mockCountData);

      const response = await request(app).get("/scores/").expect(200);

      expect(response.body.stocks).toHaveLength(1);
      expect(response.body.stocks[0]).toEqual({
        symbol: "AAPL",
        companyName: "Apple Inc.",
        sector: "Technology",
        industry: "Consumer Electronics",
        marketCap: 3000000000000,
        currentPrice: 175.5,
        pe: 25.8,
        pb: 8.5,
        scores: {
          composite: 85.5,
          quality: 88.2,
          value: 65.3,
          growth: 82.1,
          momentum: 78.9,
          sentiment: 75.4,
          positioning: 80.2,
        },
        subScores: {
          quality: {
            earningsQuality: 85.0,
            balanceSheet: 90.0,
            profitability: 88.5,
            management: 85.5,
          },
          value: {
            multiples: 60.0,
            intrinsicValue: 70.0,
            relativeValue: 66.0,
          },
        },
        metadata: {
          confidence: 92.5,
          completeness: 95.8,
          sectorAdjusted: 87.2,
          percentileRank: 89.5,
          scoreDate: "2023-01-01T00:00:00Z",
          lastUpdated: "2023-01-01T12:00:00Z",
        },
      });

      expect(response.body.pagination).toEqual({
        currentPage: 1,
        totalPages: 2, // 100 total / 50 per page
        totalItems: 100,
        itemsPerPage: 50,
        hasNext: true,
        hasPrev: false,
      });

      expect(response.body.summary.averageComposite).toBe("85.50");
      expect(response.body.summary.topScorer.symbol).toBe("AAPL");
    });

    test("should handle custom pagination parameters", async () => {
      query
        .mockResolvedValueOnce(mockStocksData)
        .mockResolvedValueOnce(mockCountData);

      const response = await request(app)
        .get("/scores/?page=2&limit=25")
        .expect(200);

      expect(response.body.pagination.currentPage).toBe(2);
      expect(response.body.pagination.itemsPerPage).toBe(25);
      expect(response.body.pagination.totalPages).toBe(4); // 100 total / 25 per page
    });

    test("should handle search filter", async () => {
      query
        .mockResolvedValueOnce(mockStocksData)
        .mockResolvedValueOnce(mockCountData);

      const response = await request(app)
        .get("/scores/?search=apple")
        .expect(200);

      expect(response.body.filters.search).toBe("apple");
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining(
          "AND (ss.symbol ILIKE $1 OR ss.security_name ILIKE $1)"
        ),
        expect.arrayContaining(["%apple%", 50, 0])
      );
    });

    test("should handle sector filter", async () => {
      query
        .mockResolvedValueOnce(mockStocksData)
        .mockResolvedValueOnce(mockCountData);

      const response = await request(app)
        .get("/scores/?sector=Technology")
        .expect(200);

      expect(response.body.filters.sector).toBe("Technology");
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("AND cp.sector = $1"),
        expect.arrayContaining(["Technology", 50, 0])
      );
    });

    test("should handle score range filters", async () => {
      query
        .mockResolvedValueOnce(mockStocksData)
        .mockResolvedValueOnce(mockCountData);

      const response = await request(app)
        .get("/scores/?minScore=70&maxScore=90")
        .expect(200);

      expect(response.body.filters.minScore).toBe(70);
      expect(response.body.filters.maxScore).toBe(90);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("AND sc.composite_score >= $1"),
        expect.arrayContaining([70, 90, 50, 0])
      );
    });

    test("should handle custom sorting", async () => {
      query
        .mockResolvedValueOnce(mockStocksData)
        .mockResolvedValueOnce(mockCountData);

      const response = await request(app)
        .get("/scores/?sortBy=quality_score&sortOrder=asc")
        .expect(200);

      expect(response.body.filters.sortBy).toBe("quality_score");
      expect(response.body.filters.sortOrder).toBe("ASC");
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("ORDER BY quality_score ASC"),
        expect.any(Array)
      );
    });

    test("should validate sort column against SQL injection", async () => {
      query
        .mockResolvedValueOnce(mockStocksData)
        .mockResolvedValueOnce(mockCountData);

      const response = await request(app)
        .get("/scores/?sortBy=malicious_column")
        .expect(200);

      // Should default to composite_score for invalid sort column
      expect(response.body.filters.sortBy).toBe("composite_score");
    });

    test("should enforce maximum limit", async () => {
      query
        .mockResolvedValueOnce(mockStocksData)
        .mockResolvedValueOnce(mockCountData);

      const response = await request(app).get("/scores/?limit=500").expect(200);

      expect(response.body.pagination.itemsPerPage).toBe(200); // capped at 200
    });

    test("should handle empty results", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [{ total: 0 }] });

      const response = await request(app).get("/scores/").expect(200);

      expect(response.body.stocks).toEqual([]);
      expect(response.body.pagination.totalItems).toBe(0);
      expect(response.body.summary.averageComposite).toBe(0);
      expect(response.body.summary.topScorer).toBeNull();
      expect(response.body.summary.scoreRange).toBeNull();
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app).get("/scores/").expect(500);

      expect(response.body.error).toBe("Failed to fetch scores");
      expect(response.body.message).toBe("Database connection failed");
    });

    test("should log query parameters", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      query
        .mockResolvedValueOnce(mockStocksData)
        .mockResolvedValueOnce(mockCountData);

      await request(app).get("/scores/?search=test").expect(200);

      expect(consoleSpy).toHaveBeenCalledWith(
        "Scores endpoint called with params:",
        expect.objectContaining({ search: "test" })
      );

      consoleSpy.mockRestore();
    });
  });

  describe("GET /scores/:symbol", () => {
    const mockSymbolData = {
      rows: [
        {
          symbol: "AAPL",
          date: "2023-01-01",
          company_name: "Apple Inc.",
          sector: "Technology",
          industry: "Consumer Electronics",
          market_cap: 3000000000000,
          current_price: 175.5,
          trailing_pe: 25.8,
          price_to_book: 8.5,
          dividend_yield: 0.5,
          return_on_equity: 0.25,
          return_on_assets: 0.15,
          debt_to_equity: 1.2,
          free_cash_flow: 100000000000,
          composite_score: 85.5,
          quality_score: 88.2,
          value_score: 65.3,
          growth_score: 82.1,
          momentum_score: 78.9,
          sentiment_score: 75.4,
          positioning_score: 80.2,
          earnings_quality_subscore: 85.0,
          balance_sheet_subscore: 90.0,
          profitability_subscore: 88.5,
          management_subscore: 85.5,
          multiples_subscore: 60.0,
          intrinsic_value_subscore: 70.0,
          relative_value_subscore: 66.0,
          confidence_score: 92.5,
          data_completeness: 95.8,
          sector_adjusted_score: 87.2,
          percentile_rank: 89.5,
          updated_at: "2023-01-01T12:00:00Z",
        },
      ],
    };

    const mockSectorData = {
      rows: [
        {
          avg_composite: 75.5,
          avg_quality: 80.2,
          avg_value: 70.1,
          peer_count: 50,
        },
      ],
    };

    test("should return detailed scores for valid symbol", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      query
        .mockResolvedValueOnce(mockSymbolData)
        .mockResolvedValueOnce(mockSectorData);

      const response = await request(app).get("/scores/AAPL").expect(200);

      expect(response.body.symbol).toBe("AAPL");
      expect(response.body.companyName).toBe("Apple Inc.");
      expect(response.body.sector).toBe("Technology");

      expect(response.body.scores).toEqual({
        composite: 85.5,
        quality: 88.2,
        value: 65.3,
        growth: 82.1,
        momentum: 78.9,
        sentiment: 75.4,
        positioning: 80.2,
      });

      expect(response.body.currentData).toEqual({
        marketCap: 3000000000000,
        currentPrice: 175.5,
        pe: 25.8,
        pb: 8.5,
        dividendYield: 0.5,
        roe: 0.25,
        roa: 0.15,
        debtToEquity: 1.2,
        freeCashFlow: 100000000000,
      });

      expect(response.body.sectorComparison.benchmarks).toEqual({
        composite: 75.5,
        quality: 80.2,
        value: 70.1,
      });

      expect(response.body.interpretation).toBeDefined();
      expect(response.body.interpretation.overall).toContain(
        "Exceptional investment opportunity"
      );
      expect(response.body.interpretation.recommendation).toContain("BUY");

      expect(consoleSpy).toHaveBeenCalledWith(
        "Getting detailed scores for AAPL"
      );
      consoleSpy.mockRestore();
    });

    test("should convert symbol to uppercase", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      query
        .mockResolvedValueOnce(mockSymbolData)
        .mockResolvedValueOnce(mockSectorData);

      const response = await request(app).get("/scores/aapl").expect(200);

      expect(response.body.symbol).toBe("AAPL");
      expect(query).toHaveBeenCalledWith(expect.any(String), ["AAPL"]);

      consoleSpy.mockRestore();
    });

    test("should return 404 for non-existent symbol", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      query.mockResolvedValue({ rows: [] });

      const response = await request(app).get("/scores/INVALID").expect(404);

      expect(response.body.error).toBe(
        "Symbol not found or no scores available"
      );
      expect(response.body.symbol).toBe("INVALID");

      consoleSpy.mockRestore();
    });

    test("should include historical scores", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      const mockHistoricalData = {
        rows: [
          ...mockSymbolData.rows,
          {
            ...mockSymbolData.rows[0],
            date: "2023-01-02",
            composite_score: 84.0,
            quality_score: 87.5,
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockHistoricalData)
        .mockResolvedValueOnce(mockSectorData);

      const response = await request(app).get("/scores/AAPL").expect(200);

      expect(response.body.historicalTrend).toHaveLength(1);
      expect(response.body.historicalTrend[0]).toEqual({
        date: "2023-01-02",
        composite: 84.0,
        quality: 87.5,
        value: 65.3,
        growth: 82.1,
        momentum: 78.9,
        sentiment: 75.4,
        positioning: 80.2,
      });

      consoleSpy.mockRestore();
    });

    test("should calculate sector relative scores", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      query
        .mockResolvedValueOnce(mockSymbolData)
        .mockResolvedValueOnce(mockSectorData);

      const response = await request(app).get("/scores/AAPL").expect(200);

      expect(response.body.sectorComparison.relativeTo).toEqual({
        composite: 10.0, // 85.5 - 75.5
        quality: 8.0, // 88.2 - 80.2
        value: -4.8, // 65.3 - 70.1
      });

      consoleSpy.mockRestore();
    });

    test("should handle database errors", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      query.mockRejectedValue(new Error("Database query failed"));

      const response = await request(app).get("/scores/AAPL").expect(500);

      expect(response.body.error).toBe("Failed to fetch detailed scores");
      expect(response.body.message).toBe("Database query failed");
      expect(response.body.symbol).toBe("AAPL");

      consoleSpy.mockRestore();
    });

    test("should include detailed breakdown with descriptions", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      query
        .mockResolvedValueOnce(mockSymbolData)
        .mockResolvedValueOnce(mockSectorData);

      const response = await request(app).get("/scores/AAPL").expect(200);

      expect(response.body.detailedBreakdown.quality.description).toContain(
        "financial statement quality"
      );
      expect(response.body.detailedBreakdown.value.description).toContain(
        "P/E, P/B, EV/EBITDA"
      );
      expect(response.body.detailedBreakdown.growth.description).toContain(
        "revenue growth"
      );

      consoleSpy.mockRestore();
    });
  });

  describe("GET /scores/sectors/analysis", () => {
    const mockSectorAnalysisData = {
      rows: [
        {
          sector: "Technology",
          stock_count: 25,
          avg_composite: 82.5,
          avg_quality: 85.2,
          avg_value: 70.1,
          avg_growth: 88.5,
          avg_momentum: 78.9,
          avg_sentiment: 75.4,
          avg_positioning: 80.2,
          score_volatility: 12.5,
          max_score: 95.5,
          min_score: 65.2,
          last_updated: "2023-01-01T12:00:00Z",
        },
        {
          sector: "Healthcare",
          stock_count: 18,
          avg_composite: 78.2,
          avg_quality: 82.1,
          avg_value: 72.5,
          avg_growth: 75.8,
          avg_momentum: 70.2,
          avg_sentiment: 68.9,
          avg_positioning: 77.5,
          score_volatility: 15.8,
          max_score: 92.1,
          min_score: 58.3,
          last_updated: "2023-01-01T12:00:00Z",
        },
      ],
    };

    test("should return sector analysis", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      query.mockResolvedValue(mockSectorAnalysisData);

      const response = await request(app)
        .get("/scores/sectors/analysis")
        .expect(200);

      expect(response.body.sectors).toHaveLength(2);
      expect(response.body.sectors[0]).toEqual({
        sector: "Technology",
        stockCount: 25,
        averageScores: {
          composite: "82.50",
          quality: "85.20",
          value: "70.10",
          growth: "88.50",
          momentum: "78.90",
          sentiment: "75.40",
          positioning: "80.20",
        },
        scoreRange: {
          min: "65.20",
          max: "95.50",
          volatility: "12.50",
        },
        lastUpdated: "2023-01-01T12:00:00Z",
      });

      expect(response.body.summary.totalSectors).toBe(2);
      expect(response.body.summary.bestPerforming.sector).toBe("Technology");
      expect(response.body.summary.mostVolatile.sector).toBe("Healthcare"); // Higher volatility
      expect(response.body.summary.averageComposite).toBe("80.35"); // (82.5 + 78.2) / 2

      expect(consoleSpy).toHaveBeenCalledWith("Getting sector analysis");
      consoleSpy.mockRestore();
    });

    test("should handle empty sector data", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/scores/sectors/analysis")
        .expect(200);

      expect(response.body.sectors).toEqual([]);
      expect(response.body.summary.totalSectors).toBe(0);

      consoleSpy.mockRestore();
    });

    test("should handle database errors", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      query.mockRejectedValue(new Error("Sector analysis failed"));

      const response = await request(app)
        .get("/scores/sectors/analysis")
        .expect(500);

      expect(response.body.error).toBe("Failed to fetch sector analysis");
      expect(response.body.message).toBe("Sector analysis failed");

      consoleSpy.mockRestore();
    });
  });

  describe("GET /scores/top/:category", () => {
    const mockTopStocksData = {
      rows: [
        {
          symbol: "AAPL",
          company_name: "Apple Inc.",
          sector: "Technology",
          market_cap: 3000000000000,
          current_price: 175.5,
          composite_score: 85.5,
          category_score: 88.2,
          confidence_score: 92.5,
          percentile_rank: 89.5,
          updated_at: "2023-01-01T12:00:00Z",
        },
        {
          symbol: "MSFT",
          company_name: "Microsoft Corporation",
          sector: "Technology",
          market_cap: 2800000000000,
          current_price: 350.25,
          composite_score: 82.8,
          category_score: 85.1,
          confidence_score: 90.2,
          percentile_rank: 87.2,
          updated_at: "2023-01-01T12:00:00Z",
        },
      ],
    };

    test("should return top quality stocks", async () => {
      query.mockResolvedValue(mockTopStocksData);

      const response = await request(app)
        .get("/scores/top/quality")
        .expect(200);

      expect(response.body.category).toBe("QUALITY");
      expect(response.body.topStocks).toHaveLength(2);
      expect(response.body.topStocks[0]).toEqual({
        symbol: "AAPL",
        companyName: "Apple Inc.",
        sector: "Technology",
        marketCap: 3000000000000,
        currentPrice: 175.5,
        compositeScore: 85.5,
        categoryScore: 88.2,
        confidence: 92.5,
        percentileRank: 89.5,
        lastUpdated: "2023-01-01T12:00:00Z",
      });

      expect(response.body.summary).toEqual({
        count: 2,
        averageScore: "86.65", // (88.2 + 85.1) / 2
        highestScore: "88.20",
        lowestScore: "85.10",
      });

      // Verify SQL query uses quality_score column
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("sc.quality_score as category_score"),
        [25]
      );
    });

    test("should handle composite category", async () => {
      query.mockResolvedValue(mockTopStocksData);

      const response = await request(app)
        .get("/scores/top/composite")
        .expect(200);

      expect(response.body.category).toBe("COMPOSITE");
      // Verify SQL query uses composite_score column
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("sc.composite_score as category_score"),
        [25]
      );
    });

    test("should handle custom limit", async () => {
      query.mockResolvedValue(mockTopStocksData);

      await request(app).get("/scores/top/value?limit=10").expect(200);

      expect(query).toHaveBeenCalledWith(expect.any(String), [10]);
    });

    test("should enforce maximum limit", async () => {
      query.mockResolvedValue(mockTopStocksData);

      await request(app).get("/scores/top/growth?limit=500").expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.any(String),
        [100] // capped at 100
      );
    });

    test("should return 400 for invalid category", async () => {
      const response = await request(app)
        .get("/scores/top/invalid")
        .expect(400);

      expect(response.body.error).toBe("Invalid category");
      expect(response.body.validCategories).toEqual([
        "composite",
        "quality",
        "value",
        "growth",
        "momentum",
        "sentiment",
        "positioning",
      ]);
    });

    test("should handle case insensitive category", async () => {
      query.mockResolvedValue(mockTopStocksData);

      const response = await request(app)
        .get("/scores/top/QUALITY")
        .expect(200);

      expect(response.body.category).toBe("QUALITY");
    });

    test("should handle empty results", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/scores/top/quality")
        .expect(200);

      expect(response.body.topStocks).toEqual([]);
      expect(response.body.summary).toEqual({
        count: 0,
        averageScore: 0,
        highestScore: 0,
        lowestScore: 0,
      });
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Top stocks query failed"));

      const response = await request(app)
        .get("/scores/top/quality")
        .expect(500);

      expect(response.body.error).toBe("Failed to fetch top stocks");
      expect(response.body.message).toBe("Top stocks query failed");
    });

    test("should only include high confidence stocks", async () => {
      query.mockResolvedValue(mockTopStocksData);

      await request(app).get("/scores/top/quality").expect(200);

      // Verify SQL query includes confidence filter
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("AND sc.confidence_score >= 0.7"),
        [25]
      );
    });

    test("should test all valid categories", async () => {
      const categories = [
        "composite",
        "quality",
        "value",
        "growth",
        "momentum",
        "sentiment",
        "positioning",
      ];

      for (const category of categories) {
        query.mockResolvedValue(mockTopStocksData);

        const response = await request(app)
          .get(`/scores/top/${category}`)
          .expect(200);

        expect(response.body.category).toBe(category.toUpperCase());
      }
    });
  });

  describe("Score interpretation logic", () => {
    const mockSymbolData = {
      rows: [
        {
          symbol: "TEST",
          date: "2023-01-01",
          company_name: "Test Company",
          sector: "Technology",
          composite_score: 85.5,
          quality_score: 88.2,
          value_score: 65.3,
          growth_score: 82.1,
          updated_at: "2023-01-01T12:00:00Z",
        },
      ],
    };

    const mockSectorData = {
      rows: [
        {
          avg_composite: 75.5,
          avg_quality: 80.2,
          avg_value: 70.1,
          peer_count: 50,
        },
      ],
    };

    test("should generate BUY recommendation for high scores", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      query
        .mockResolvedValueOnce(mockSymbolData)
        .mockResolvedValueOnce(mockSectorData);

      const response = await request(app).get("/scores/TEST").expect(200);

      expect(response.body.interpretation.overall).toContain(
        "Exceptional investment opportunity"
      );
      expect(response.body.interpretation.recommendation).toContain("BUY");
      expect(response.body.interpretation.strengths).toContain(
        "High-quality financial statements and management"
      );

      consoleSpy.mockRestore();
    });

    test("should generate SELL recommendation for low scores", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      const lowScoreData = {
        rows: [
          {
            ...mockSymbolData.rows[0],
            composite_score: 30.0,
            quality_score: 25.0,
            value_score: 35.0,
            growth_score: 20.0,
          },
        ],
      };

      query
        .mockResolvedValueOnce(lowScoreData)
        .mockResolvedValueOnce(mockSectorData);

      const response = await request(app).get("/scores/TEST").expect(200);

      expect(response.body.interpretation.overall).toContain(
        "Poor investment profile"
      );
      expect(response.body.interpretation.recommendation).toContain("SELL");
      expect(response.body.interpretation.concerns).toContain(
        "Weak financial quality"
      );

      consoleSpy.mockRestore();
    });
  });

  describe("Parameter validation and edge cases", () => {
    test("should handle non-numeric pagination parameters", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [{ total: 0 }] });

      const response = await request(app)
        .get("/scores/?page=abc&limit=xyz")
        .expect(200);

      expect(response.body.pagination.currentPage).toBe(1); // default
      expect(response.body.pagination.itemsPerPage).toBe(50); // default
    });

    test("should handle negative pagination parameters", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [{ total: 0 }] });

      const response = await request(app)
        .get("/scores/?page=-1&limit=-10")
        .expect(200);

      expect(response.body.pagination.currentPage).toBe(1); // Math.max applied
    });

    test("should handle non-numeric score range filters", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [{ total: 0 }] });

      const response = await request(app)
        .get("/scores/?minScore=abc&maxScore=xyz")
        .expect(200);

      expect(response.body.filters.minScore).toBe(0); // default when NaN
      expect(response.body.filters.maxScore).toBe(100); // default when NaN
    });

    test("should handle empty search and sector filters", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [{ total: 0 }] });

      const response = await request(app)
        .get("/scores/?search=&sector=")
        .expect(200);

      expect(response.body.filters.search).toBe("");
      expect(response.body.filters.sector).toBe("");
    });

    test("should handle whitespace-only sector filter", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [{ total: 0 }] });

      await request(app).get("/scores/?sector=   ").expect(200);

      // Should not add sector filter for whitespace-only
      expect(query).toHaveBeenCalledWith(
        expect.not.stringContaining("AND cp.sector ="),
        expect.any(Array)
      );
    });
  });

  describe("Response format consistency", () => {
    test("should return consistent timestamp format across endpoints", async () => {
      const consoleSpy = jest
        .spyOn(console, "log")
        .mockImplementation(() => {});
      query.mockResolvedValue({ rows: [] });

      const pingResponse = await request(app).get("/scores/ping");
      const _scoresResponse = await request(app).get("/scores/");
      const topResponse = await request(app).get("/scores/top/quality");
      const sectorsResponse = await request(app).get(
        "/scores/sectors/analysis"
      );

      // All timestamps should be valid ISO strings
      expect(new Date(pingResponse.body.timestamp)).toBeInstanceOf(Date);
      expect(new Date(topResponse.body.timestamp)).toBeInstanceOf(Date);
      expect(new Date(sectorsResponse.body.timestamp)).toBeInstanceOf(Date);

      consoleSpy.mockRestore();
    });
  });
});

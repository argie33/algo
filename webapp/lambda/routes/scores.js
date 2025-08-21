const express = require("express");
const { query } = require("../utils/database");

const router = express.Router();

// Basic ping endpoint
router.get("/ping", (req, res) => {
  res.json({
    status: "ok",
    endpoint: "scores",
    timestamp: new Date().toISOString(),
  });
});

// Get comprehensive scores for all stocks with filtering and pagination
router.get("/", async (req, res) => {
  try {
    console.log("Scores endpoint called with params:", req.query);

    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = (page - 1) * limit;
    const search = req.query.search || "";
    const sector = req.query.sector || "";
    const minScore = parseFloat(req.query.minScore) || 0;
    const maxScore = parseFloat(req.query.maxScore) || 100;
    const sortBy = req.query.sortBy || "composite_score";
    const sortOrder = req.query.sortOrder || "desc";

    let whereClause = "WHERE 1=1";
    const params = [];
    let paramCount = 0;

    // Add search filter
    if (search) {
      paramCount++;
      whereClause += ` AND (ss.symbol ILIKE $${paramCount} OR ss.security_name ILIKE $${paramCount})`;
      params.push(`%${search}%`);
    }

    // Add sector filter
    if (sector && sector.trim() !== "") {
      paramCount++;
      whereClause += ` AND cp.sector = $${paramCount}`;
      params.push(sector);
    }

    // Add score range filters
    if (minScore > 0) {
      paramCount++;
      whereClause += ` AND sc.composite_score >= $${paramCount}`;
      params.push(minScore);
    }

    if (maxScore < 100) {
      paramCount++;
      whereClause += ` AND sc.composite_score <= $${paramCount}`;
      params.push(maxScore);
    }

    // Validate sort column to prevent SQL injection
    const validSortColumns = [
      "symbol",
      "composite_score",
      "quality_score",
      "value_score",
      "growth_score",
      "momentum_score",
      "sentiment_score",
      "positioning_score",
      "market_cap",
      "sector",
    ];

    const safeSort = validSortColumns.includes(sortBy)
      ? sortBy
      : "composite_score";
    const safeOrder = sortOrder.toLowerCase() === "asc" ? "ASC" : "DESC";

    // Main query to get stocks with scores
    const stocksQuery = `
      SELECT 
        ss.symbol,
        ss.security_name as company_name,
        cp.sector,
        cp.industry,
        cp.market_cap,
        cp.current_price,
        cp.trailing_pe,
        cp.price_to_book,
        
        -- Main Scores
        sc.composite_score,
        sc.quality_score,
        sc.value_score,
        sc.growth_score,
        sc.momentum_score,
        sc.sentiment_score,
        sc.positioning_score,
        
        -- Sub-scores for detailed analysis
        sc.earnings_quality_subscore,
        sc.balance_sheet_subscore,
        sc.profitability_subscore,
        sc.management_subscore,
        sc.multiples_subscore,
        sc.intrinsic_value_subscore,
        sc.relative_value_subscore,
        
        -- Metadata
        sc.confidence_score,
        sc.data_completeness,
        sc.sector_adjusted_score,
        sc.percentile_rank,
        sc.created_at as score_date,
        sc.updated_at as last_updated
        
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.symbol
      LEFT JOIN stock_scores sc ON ss.symbol = sc.symbol 
        AND sc.date = (
          SELECT MAX(date) 
          FROM stock_scores sc2 
          WHERE sc2.symbol = ss.symbol
        )
      ${whereClause}
      AND sc.composite_score IS NOT NULL
      ORDER BY ${safeSort} ${safeOrder}
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    const stocksResult = await query(stocksQuery, params);

    // Get total count for pagination
    const countQuery = `
      SELECT COUNT(DISTINCT ss.symbol) as total
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.symbol
      LEFT JOIN stock_scores sc ON ss.symbol = sc.symbol 
        AND sc.date = (
          SELECT MAX(date) 
          FROM stock_scores sc2 
          WHERE sc2.symbol = ss.symbol
        )
      ${whereClause}
      AND sc.composite_score IS NOT NULL
    `;

    const countResult = await query(countQuery, params.slice(0, paramCount));
    const totalStocks = parseInt(countResult.rows[0].total);

    // Format the response
    const stocks = stocksResult.rows.map((row) => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      industry: row.industry,
      marketCap: row.market_cap,
      currentPrice: row.current_price,
      pe: row.trailing_pe,
      pb: row.price_to_book,

      scores: {
        composite: parseFloat(row.composite_score) || 0,
        quality: parseFloat(row.quality_score) || 0,
        value: parseFloat(row.value_score) || 0,
        growth: parseFloat(row.growth_score) || 0,
        momentum: parseFloat(row.momentum_score) || 0,
        sentiment: parseFloat(row.sentiment_score) || 0,
        positioning: parseFloat(row.positioning_score) || 0,
      },

      subScores: {
        quality: {
          earningsQuality: parseFloat(row.earnings_quality_subscore) || 0,
          balanceSheet: parseFloat(row.balance_sheet_subscore) || 0,
          profitability: parseFloat(row.profitability_subscore) || 0,
          management: parseFloat(row.management_subscore) || 0,
        },
        value: {
          multiples: parseFloat(row.multiples_subscore) || 0,
          intrinsicValue: parseFloat(row.intrinsic_value_subscore) || 0,
          relativeValue: parseFloat(row.relative_value_subscore) || 0,
        },
      },

      metadata: {
        confidence: parseFloat(row.confidence_score) || 0,
        completeness: parseFloat(row.data_completeness) || 0,
        sectorAdjusted: parseFloat(row.sector_adjusted_score) || 0,
        percentileRank: parseFloat(row.percentile_rank) || 0,
        scoreDate: row.score_date,
        lastUpdated: row.last_updated,
      },
    }));

    res.json({
      stocks,
      pagination: {
        currentPage: page,
        totalPages: Math.ceil(totalStocks / limit),
        totalItems: totalStocks,
        itemsPerPage: limit,
        hasNext: offset + limit < totalStocks,
        hasPrev: page > 1,
      },
      filters: {
        search,
        sector,
        minScore,
        maxScore,
        sortBy: safeSort,
        sortOrder: safeOrder,
      },
      summary: {
        averageComposite:
          stocks.length > 0
            ? (
                stocks.reduce((sum, s) => sum + s.scores.composite, 0) /
                stocks.length
              ).toFixed(2)
            : 0,
        topScorer: stocks.length > 0 ? stocks[0] : null,
        scoreRange:
          stocks.length > 0
            ? {
                min: Math.min(...stocks.map((s) => s.scores.composite)).toFixed(
                  2
                ),
                max: Math.max(...stocks.map((s) => s.scores.composite)).toFixed(
                  2
                ),
              }
            : null,
      },
    });
  } catch (error) {
    console.error("Error in scores endpoint:", error);
    res.status(500).json({
      error: "Failed to fetch scores",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get detailed scores for a specific stock
router.get("/:symbol", async (req, res) => {
  try {
    const symbol = req.params.symbol.toUpperCase();
    console.log(`Getting detailed scores for ${symbol}`);

    // Get latest scores with historical data
    const scoresQuery = `
      SELECT 
        sc.*,
        ss.security_name as company_name,
        cp.sector,
        cp.industry,
        cp.market_cap,
        cp.current_price,
        cp.trailing_pe,
        cp.price_to_book,
        cp.dividend_yield,
        cp.return_on_equity,
        cp.return_on_assets,
        cp.debt_to_equity,
        cp.free_cash_flow
      FROM stock_scores sc
      LEFT JOIN stock_symbols ss ON sc.symbol = ss.symbol
      LEFT JOIN company_profile cp ON sc.symbol = cp.symbol
      WHERE sc.symbol = $1
      ORDER BY sc.date DESC
      LIMIT 12
    `;

    const scoresResult = await query(scoresQuery, [symbol]);

    if (scoresResult.rows.length === 0) {
      return res.status(404).json({
        error: "Symbol not found or no scores available",
        symbol,
        timestamp: new Date().toISOString(),
      });
    }

    const latestScore = scoresResult.rows[0];
    const historicalScores = scoresResult.rows.slice(1);

    // Get sector benchmark data
    const sectorQuery = `
      SELECT 
        AVG(composite_score) as avg_composite,
        AVG(quality_score) as avg_quality,
        AVG(value_score) as avg_value,
        COUNT(*) as peer_count
      FROM stock_scores sc
      LEFT JOIN company_profile cp ON sc.symbol = cp.symbol
      WHERE cp.sector = $1
      AND sc.date = $2
      AND sc.composite_score IS NOT NULL
    `;

    const sectorResult = await query(sectorQuery, [
      latestScore.sector,
      latestScore.date,
    ]);
    const sectorBenchmark = sectorResult.rows[0];

    // Format comprehensive response
    const response = {
      symbol,
      companyName: latestScore.company_name,
      sector: latestScore.sector,
      industry: latestScore.industry,

      currentData: {
        marketCap: latestScore.market_cap,
        currentPrice: latestScore.current_price,
        pe: latestScore.trailing_pe,
        pb: latestScore.price_to_book,
        dividendYield: latestScore.dividend_yield,
        roe: latestScore.return_on_equity,
        roa: latestScore.return_on_assets,
        debtToEquity: latestScore.debt_to_equity,
        freeCashFlow: latestScore.free_cash_flow,
      },

      scores: {
        composite: parseFloat(latestScore.composite_score) || 0,
        quality: parseFloat(latestScore.quality_score) || 0,
        value: parseFloat(latestScore.value_score) || 0,
        growth: parseFloat(latestScore.growth_score) || 0,
        momentum: parseFloat(latestScore.momentum_score) || 0,
        sentiment: parseFloat(latestScore.sentiment_score) || 0,
        positioning: parseFloat(latestScore.positioning_score) || 0,
      },

      detailedBreakdown: {
        quality: {
          overall: parseFloat(latestScore.quality_score) || 0,
          components: {
            earningsQuality:
              parseFloat(latestScore.earnings_quality_subscore) || 0,
            balanceSheet: parseFloat(latestScore.balance_sheet_subscore) || 0,
            profitability: parseFloat(latestScore.profitability_subscore) || 0,
            management: parseFloat(latestScore.management_subscore) || 0,
          },
          description:
            "Measures financial statement quality, balance sheet strength, profitability metrics, and management effectiveness",
        },

        value: {
          overall: parseFloat(latestScore.value_score) || 0,
          components: {
            multiples: parseFloat(latestScore.multiples_subscore) || 0,
            intrinsicValue:
              parseFloat(latestScore.intrinsic_value_subscore) || 0,
            relativeValue: parseFloat(latestScore.relative_value_subscore) || 0,
          },
          description:
            "Analyzes P/E, P/B, EV/EBITDA ratios, DCF intrinsic value, and peer comparison",
        },

        growth: {
          overall: parseFloat(latestScore.growth_score) || 0,
          components: {
            revenueGrowth: parseFloat(latestScore.revenue_growth_subscore) || 0,
            earningsGrowth:
              parseFloat(latestScore.earnings_growth_subscore) || 0,
            sustainableGrowth:
              parseFloat(latestScore.sustainable_growth_subscore) || 0,
          },
          description:
            "Evaluates revenue growth, earnings growth quality, and growth sustainability",
        },

        momentum: {
          overall: parseFloat(latestScore.momentum_score) || 0,
          components: {
            priceMomentum: parseFloat(latestScore.price_momentum_subscore) || 0,
            fundamentalMomentum:
              parseFloat(latestScore.fundamental_momentum_subscore) || 0,
            technicalMomentum:
              parseFloat(latestScore.technical_momentum_subscore) || 0,
          },
          description:
            "Tracks price trends, earnings revisions, and technical indicators",
        },

        sentiment: {
          overall: parseFloat(latestScore.sentiment_score) || 0,
          components: {
            analystSentiment:
              parseFloat(latestScore.analyst_sentiment_subscore) || 0,
            socialSentiment:
              parseFloat(latestScore.social_sentiment_subscore) || 0,
            newsSentiment: parseFloat(latestScore.news_sentiment_subscore) || 0,
          },
          description:
            "Aggregates analyst recommendations, social media sentiment, and news sentiment",
        },

        positioning: {
          overall: parseFloat(latestScore.positioning_score) || 0,
          components: {
            institutional: parseFloat(latestScore.institutional_subscore) || 0,
            insider: parseFloat(latestScore.insider_subscore) || 0,
            shortInterest: parseFloat(latestScore.short_interest_subscore) || 0,
          },
          description:
            "Monitors institutional ownership, insider trading, and short interest dynamics",
        },
      },

      sectorComparison: {
        sectorName: latestScore.sector,
        peerCount: parseInt(sectorBenchmark.peer_count) || 0,
        benchmarks: {
          composite: parseFloat(sectorBenchmark.avg_composite) || 0,
          quality: parseFloat(sectorBenchmark.avg_quality) || 0,
          value: parseFloat(sectorBenchmark.avg_value) || 0,
        },
        relativeTo: {
          composite:
            (parseFloat(latestScore.composite_score) || 0) -
            (parseFloat(sectorBenchmark.avg_composite) || 0),
          quality:
            (parseFloat(latestScore.quality_score) || 0) -
            (parseFloat(sectorBenchmark.avg_quality) || 0),
          value:
            (parseFloat(latestScore.value_score) || 0) -
            (parseFloat(sectorBenchmark.avg_value) || 0),
        },
      },

      historicalTrend: historicalScores.map((row) => ({
        date: row.date,
        composite: parseFloat(row.composite_score) || 0,
        quality: parseFloat(row.quality_score) || 0,
        value: parseFloat(row.value_score) || 0,
        growth: parseFloat(row.growth_score) || 0,
        momentum: parseFloat(row.momentum_score) || 0,
        sentiment: parseFloat(row.sentiment_score) || 0,
        positioning: parseFloat(row.positioning_score) || 0,
      })),

      metadata: {
        scoreDate: latestScore.date,
        confidence: parseFloat(latestScore.confidence_score) || 0,
        completeness: parseFloat(latestScore.data_completeness) || 0,
        sectorAdjusted: parseFloat(latestScore.sector_adjusted_score) || 0,
        percentileRank: parseFloat(latestScore.percentile_rank) || 0,
        marketRegime: latestScore.market_regime || "normal",
        lastUpdated: latestScore.updated_at,
      },

      interpretation: generateScoreInterpretation(latestScore),

      timestamp: new Date().toISOString(),
    };

    res.json(response);
  } catch (error) {
    console.error("Error getting detailed scores:", error);
    res.status(500).json({
      error: "Failed to fetch detailed scores",
      message: error.message,
      symbol: req.params.symbol,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get sector analysis and rankings
router.get("/sectors/analysis", async (req, res) => {
  try {
    console.log("Getting sector analysis");

    const sectorQuery = `
      SELECT 
        cp.sector,
        COUNT(*) as stock_count,
        AVG(sc.composite_score) as avg_composite,
        AVG(sc.quality_score) as avg_quality,
        AVG(sc.value_score) as avg_value,
        AVG(sc.growth_score) as avg_growth,
        AVG(sc.momentum_score) as avg_momentum,
        AVG(sc.sentiment_score) as avg_sentiment,
        AVG(sc.positioning_score) as avg_positioning,
        STDDEV(sc.composite_score) as score_volatility,
        MAX(sc.composite_score) as max_score,
        MIN(sc.composite_score) as min_score,
        MAX(sc.updated_at) as last_updated
      FROM company_profile cp
      INNER JOIN stock_scores sc ON cp.symbol = sc.symbol
      WHERE sc.date = (
        SELECT MAX(date) FROM stock_scores sc2 WHERE sc2.symbol = cp.symbol
      )
      AND cp.sector IS NOT NULL
      AND sc.composite_score IS NOT NULL
      GROUP BY cp.sector
      HAVING COUNT(*) >= 5
      ORDER BY avg_composite DESC
    `;

    const sectorResult = await query(sectorQuery);

    const sectors = sectorResult.rows.map((row) => ({
      sector: row.sector,
      stockCount: parseInt(row.stock_count),
      averageScores: {
        composite: parseFloat(row.avg_composite).toFixed(2),
        quality: parseFloat(row.avg_quality).toFixed(2),
        value: parseFloat(row.avg_value).toFixed(2),
        growth: parseFloat(row.avg_growth).toFixed(2),
        momentum: parseFloat(row.avg_momentum).toFixed(2),
        sentiment: parseFloat(row.avg_sentiment).toFixed(2),
        positioning: parseFloat(row.avg_positioning).toFixed(2),
      },
      scoreRange: {
        min: parseFloat(row.min_score).toFixed(2),
        max: parseFloat(row.max_score).toFixed(2),
        volatility: parseFloat(row.score_volatility).toFixed(2),
      },
      lastUpdated: row.last_updated,
    }));

    // Handle empty sectors data safely
    const summary = {
      totalSectors: sectors.length,
      bestPerforming: sectors.length > 0 ? sectors[0] : null,
      mostVolatile: sectors.length > 0 ? sectors.reduce((prev, current) =>
        parseFloat(prev.scoreRange.volatility) >
        parseFloat(current.scoreRange.volatility)
          ? prev
          : current
      ) : null,
      averageComposite: sectors.length > 0 ? (
        sectors.reduce(
          (sum, s) => sum + parseFloat(s.averageScores.composite),
          0
        ) / sectors.length
      ).toFixed(2) : "0.00",
    };

    res.json({
      sectors,
      summary,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error in sector analysis:", error);
    res.status(500).json({
      error: "Failed to fetch sector analysis",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get top scoring stocks by category
router.get("/top/:category", async (req, res) => {
  try {
    const category = req.params.category.toLowerCase();
    const limit = Math.min(parseInt(req.query.limit) || 25, 100);

    const validCategories = [
      "composite",
      "quality",
      "value",
      "growth",
      "momentum",
      "sentiment",
      "positioning",
    ];
    if (!validCategories.includes(category)) {
      return res.status(400).json({
        error: "Invalid category",
        validCategories,
        timestamp: new Date().toISOString(),
      });
    }

    const scoreColumn =
      category === "composite" ? "composite_score" : `${category}_score`;

    const topStocksQuery = `
      SELECT 
        ss.symbol,
        ss.security_name as company_name,
        cp.sector,
        cp.market_cap,
        cp.current_price,
        sc.composite_score,
        sc.${scoreColumn} as category_score,
        sc.confidence_score,
        sc.percentile_rank,
        sc.updated_at
      FROM stock_scores sc
      INNER JOIN stock_symbols ss ON sc.symbol = ss.symbol
      LEFT JOIN company_profile cp ON sc.symbol = cp.symbol
      WHERE sc.date = (
        SELECT MAX(date) FROM stock_scores sc2 WHERE sc2.symbol = sc.symbol
      )
      AND sc.${scoreColumn} IS NOT NULL
      AND sc.confidence_score >= 0.7
      ORDER BY sc.${scoreColumn} DESC
      LIMIT $1
    `;

    const result = await query(topStocksQuery, [limit]);

    const topStocks = result.rows.map((row) => ({
      symbol: row.symbol,
      companyName: row.company_name,
      sector: row.sector,
      marketCap: row.market_cap,
      currentPrice: row.current_price,
      compositeScore: parseFloat(row.composite_score),
      categoryScore: parseFloat(row.category_score),
      confidence: parseFloat(row.confidence_score),
      percentileRank: parseFloat(row.percentile_rank),
      lastUpdated: row.updated_at,
    }));

    res.json({
      category: category.toUpperCase(),
      topStocks,
      summary: {
        count: topStocks.length,
        averageScore:
          topStocks.length > 0
            ? (
                topStocks.reduce((sum, s) => sum + s.categoryScore, 0) /
                topStocks.length
              ).toFixed(2)
            : 0,
        highestScore:
          topStocks.length > 0 ? topStocks[0].categoryScore.toFixed(2) : 0,
        lowestScore:
          topStocks.length > 0
            ? topStocks[topStocks.length - 1].categoryScore.toFixed(2)
            : 0,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error getting top stocks:", error);
    res.status(500).json({
      error: "Failed to fetch top stocks",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

function generateScoreInterpretation(scoreData) {
  const composite = parseFloat(scoreData.composite_score) || 0;
  const quality = parseFloat(scoreData.quality_score) || 0;
  const value = parseFloat(scoreData.value_score) || 0;
  const growth = parseFloat(scoreData.growth_score) || 0;

  let interpretation = {
    overall: "",
    strengths: [],
    concerns: [],
    recommendation: "",
  };

  // Overall assessment
  if (composite >= 80) {
    interpretation.overall =
      "Exceptional investment opportunity with strong fundamentals across multiple factors";
  } else if (composite >= 70) {
    interpretation.overall =
      "Strong investment candidate with solid fundamentals";
  } else if (composite >= 60) {
    interpretation.overall = "Reasonable investment option with mixed signals";
  } else if (composite >= 50) {
    interpretation.overall =
      "Below-average investment profile with some concerns";
  } else {
    interpretation.overall = "Poor investment profile with significant risks";
  }

  // Identify strengths
  if (quality >= 75)
    interpretation.strengths.push(
      "High-quality financial statements and management"
    );
  if (value >= 75)
    interpretation.strengths.push("Attractive valuation with margin of safety");
  if (growth >= 75)
    interpretation.strengths.push("Strong growth prospects and momentum");

  // Identify concerns
  if (quality <= 40)
    interpretation.concerns.push(
      "Weak financial quality and balance sheet concerns"
    );
  if (value <= 40)
    interpretation.concerns.push("Overvalued relative to fundamentals");
  if (growth <= 40) interpretation.concerns.push("Limited growth prospects");

  // Investment recommendation
  if (composite >= 80 && quality >= 70) {
    interpretation.recommendation =
      "BUY - Strong fundamentals with attractive risk-adjusted returns";
  } else if (composite >= 70) {
    interpretation.recommendation = "BUY - Solid investment opportunity";
  } else if (composite >= 60) {
    interpretation.recommendation = "HOLD - Monitor for improvements";
  } else if (composite >= 50) {
    interpretation.recommendation = "WEAK HOLD - Consider reducing position";
  } else {
    interpretation.recommendation = "SELL - Poor fundamentals warrant exit";
  }

  return interpretation;
}

module.exports = router;

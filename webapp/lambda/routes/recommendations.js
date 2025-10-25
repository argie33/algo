const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Get stock recommendations
router.get("/", authenticateToken, async (req, res) => {
  try {
    const {
      symbol,
      category = "all", // all, buy, sell, hold
      analyst = "all",
      limit = 20,
      timeframe = "recent",
    } = req.query;

    try {
      console.log(
        `📊 Stock recommendations requested - symbol: ${symbol || "all"}, category: ${category}`
      );
    } catch (e) {
      // Ignore console logging errors
    }

    // Build query based on filters
    let whereClause = "WHERE 1=1";
    let queryParams = [];
    let paramIndex = 1;

    // Symbol filter
    if (symbol) {
      whereClause += ` AND symbol = $${paramIndex}`;
      queryParams.push(symbol.toUpperCase());
      paramIndex++;
    }

    // Category filter (to_grade)
    if (category !== "all") {
      whereClause += ` AND LOWER(to_grade) LIKE $${paramIndex}`;
      let ratingPattern;
      if (category === "buy") ratingPattern = "%buy%";
      else if (category === "sell") ratingPattern = "%sell%";
      else if (category === "hold") ratingPattern = "%hold%";
      else ratingPattern = `%${category.toLowerCase()}%`;
      queryParams.push(ratingPattern);
      paramIndex++;
    }

    // Analyst firm filter
    if (analyst !== "all") {
      whereClause += ` AND LOWER(firm) LIKE $${paramIndex}`;
      queryParams.push(`%${analyst.toLowerCase()}%`);
      paramIndex++;
    }

    // Timeframe filter
    if (timeframe === "recent") {
      whereClause += ` AND date >= CURRENT_DATE - INTERVAL '30 days'`;
    } else if (timeframe === "week") {
      whereClause += ` AND date >= CURRENT_DATE - INTERVAL '7 days'`;
    } else if (timeframe === "month") {
      whereClause += ` AND date >= CURRENT_DATE - INTERVAL '30 days'`;
    }

    const recommendationsQuery = `
      SELECT
        symbol,
        firm as analyst_firm,
        to_grade as rating,
        action,
        from_grade,
        to_grade,
        date as date_published,
        details,
        NULL as target_price,
        NULL as current_price,
        NULL as upside_potential,
        CASE
          WHEN LOWER(to_grade) LIKE '%buy%' OR LOWER(to_grade) LIKE '%strong buy%' THEN 'buy'
          WHEN LOWER(to_grade) LIKE '%sell%' OR LOWER(to_grade) LIKE '%strong sell%' THEN 'sell'
          WHEN LOWER(to_grade) LIKE '%hold%' THEN 'hold'
          ELSE LOWER(COALESCE(to_grade, action))
        END as recommendation_type,
        fetched_at
      FROM analyst_upgrade_downgrade
      ${whereClause}
      ORDER BY date DESC, symbol ASC
      LIMIT $${paramIndex}
    `;

    queryParams.push(Math.max(1, Math.min(parseInt(limit) || 20, 100)));
    const result = await query(recommendationsQuery, queryParams);

    if (result.rows.length === 0) {
      return res.json({
        success: true,
        data: [],
        recommendations: [],
        summary: {
          total_recommendations: 0,
          buy_count: 0,
          hold_count: 0,
          sell_count: 0,
        },
        message: symbol
          ? `No recommendations found for ${symbol.toUpperCase()}`
          : "No recommendations found matching criteria",
        filters: {
          symbol,
          category,
          analyst,
          timeframe,
          limit: parseInt(limit),
        },
        timestamp: new Date().toISOString(),
      });
    }

    const recommendations = result.rows.map((row) => ({
      symbol: row.symbol,
      analyst_firm: row.analyst_firm,
      rating: row.rating,
      recommendation_type: row.recommendation_type,
      target_price: parseFloat(row.target_price) || 0,
      current_price: parseFloat(row.current_price) || 0,
      upside_potential: parseFloat(row.upside_potential) || 0,
      upside_percentage:
        row.current_price > 0
          ? ((parseFloat(row.target_price) - parseFloat(row.current_price)) /
              parseFloat(row.current_price)) *
            100
          : 0,
      date_published: row.date_published,
      date_updated: row.date_updated,
      // Additional fields
      reasoning: row.details || `${row.recommendation_type} recommendation from ${row.analyst_firm}`,
    }));

    // Calculate summary statistics
    const summary = {
      total_recommendations: recommendations.length,
      buy_count: recommendations.filter((r) => r.recommendation_type === "buy")
        .length,
      hold_count: recommendations.filter(
        (r) => r.recommendation_type === "hold"
      ).length,
      sell_count: recommendations.filter(
        (r) => r.recommendation_type === "sell"
      ).length,
      avg_target_price:
        recommendations.reduce((sum, r) => sum + r.target_price, 0) /
        recommendations.length,
      avg_upside:
        recommendations.reduce((sum, r) => sum + r.upside_percentage, 0) /
        recommendations.length,
    };

    res.json({
      success: true,
      data: recommendations,
      recommendations,
      summary,
      filters: { symbol, category, analyst, timeframe, limit: parseInt(limit) },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    try {
      console.error("Recommendations error:", error);
    } catch (e) {
      // Ignore console logging errors
    }
    if (res.serverError) {
      res.serverError("Failed to fetch recommendations", {
        error: error.message,
        details: error.message,
        timestamp: new Date().toISOString(),
      });
    } else {
      res.status(500).json({
        success: false,
        error: "Failed to fetch recommendations",
        details: error.message,
        timestamp: new Date().toISOString(),
      });
    }
  }
});

// Get analyst coverage for specific symbol
router.get("/analysts/:symbol", authenticateToken, async (req, res) => {
  try {
    const { symbol } = req.params;
    const { limit = 10 } = req.query;

    try {
      console.log(`👨‍💼 Analyst coverage requested for ${symbol.toUpperCase()}`);
    } catch (e) {
      // Ignore console logging errors
    }

    // Get analyst coverage for specific symbol
    const coverageQuery = `
      SELECT
        firm as analyst_firm,
        to_grade as rating,
        0 as target_price,
        0 as current_price,
        date as date_published,
        fetched_at as date_updated,
        CASE
          WHEN 0 > 0 THEN
            ROUND(((0 - 0) / 0 * 100)::numeric, 2)
          ELSE 0
        END as upside_percentage,
        CASE
          WHEN LOWER(to_grade) LIKE '%buy%' OR LOWER(to_grade) LIKE '%strong buy%' THEN 'buy'
          WHEN LOWER(to_grade) LIKE '%sell%' OR LOWER(to_grade) LIKE '%strong sell%' THEN 'sell'
          WHEN LOWER(to_grade) LIKE '%hold%' THEN 'hold'
          ELSE LOWER(COALESCE(to_grade, action))
        END as recommendation_type
      FROM analyst_upgrade_downgrade
      WHERE symbol = $1
      ORDER BY date DESC, firm
      LIMIT $2
    `;

    const result = await query(coverageQuery, [
      symbol.toUpperCase(),
      Math.max(1, Math.min(parseInt(limit) || 10, 100)),
    ]);

    if (result.rows.length === 0) {
      return res.json({
        success: true,
        symbol: symbol.toUpperCase(),
        coverage: [],
        consensus: {
          total_analysts: 0,
          buy_ratings: 0,
          hold_ratings: 0,
          sell_ratings: 0,
          avg_target_price: 0,
          price_range: { min: 0, max: 0 },
        },
        message: `No analyst coverage found for ${symbol.toUpperCase()}`,
        timestamp: new Date().toISOString(),
      });
    }

    const coverage = result.rows.map((row) => ({
      analyst_firm: row.analyst_firm,
      rating: row.rating,
      recommendation_type: row.recommendation_type,
      target_price: parseFloat(row.target_price) || 0,
      current_price: parseFloat(row.current_price) || 0,
      upside_percentage: parseFloat(row.upside_percentage) || 0,
      date_published: row.date_published,
      date_updated: row.date_updated,
    }));

    // Calculate consensus data
    const targetPrices = coverage
      .filter((c) => c.target_price > 0)
      .map((c) => c.target_price);
    const consensus = {
      total_analysts: coverage.length,
      buy_ratings: coverage.filter((c) => c.recommendation_type === "buy")
        .length,
      hold_ratings: coverage.filter((c) => c.recommendation_type === "hold")
        .length,
      sell_ratings: coverage.filter((c) => c.recommendation_type === "sell")
        .length,
      avg_target_price:
        targetPrices.length > 0
          ? targetPrices.reduce((sum, price) => sum + price, 0) /
            targetPrices.length
          : 0,
      price_range: {
        min: targetPrices.length > 0 ? Math.min(...targetPrices) : 0,
        max: targetPrices.length > 0 ? Math.max(...targetPrices) : 0,
      },
    };

    res.json({
      success: true,
      symbol: symbol.toUpperCase(),
      coverage,
      analysts: coverage, // Alias for test compatibility
      consensus,
      limit: Math.max(1, Math.min(parseInt(limit) || 10, 100)),
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    try {
      console.error(`Analyst coverage error for ${req.params.symbol}:`, error);
    } catch (e) {
      // Ignore console logging errors
    }
    if (res.serverError) {
      res.serverError("Failed to fetch analyst coverage", {
        error: error.message,
        details: error.message,
        symbol: req.params.symbol.toUpperCase(),
        timestamp: new Date().toISOString(),
      });
    } else {
      res.status(500).json({
        success: false,
        error: "Failed to fetch analyst coverage",
        details: error.message,
        symbol: req.params.symbol.toUpperCase(),
        timestamp: new Date().toISOString(),
      });
    }
  }
});

// AI-powered stock recommendations endpoint (not implemented)
router.get("/ai", authenticateToken, async (req, res) => {
  res.status(501).json({
    success: false,
    error: "AI recommendations not implemented",
    message: "This feature requires ML model training and deployment",
    timestamp: new Date().toISOString(),
  });
});

// Get sector-based recommendations (not implemented)
router.get("/sectors", async (req, res) => {
  res.status(501).json({
    success: false,
    error: "Sector recommendations not implemented",
    message: "This feature requires sector analysis implementation",
    timestamp: new Date().toISOString(),
  });
});

// Get recommendations for specific sector (not implemented)
router.get("/sectors/:sector", async (req, res) => {
  res.status(501).json({
    success: false,
    error: "Sector recommendations not implemented",
    message: "This feature requires sector analysis implementation",
    timestamp: new Date().toISOString(),
  });
});

// Get portfolio allocation recommendations (not implemented)
router.get("/allocation", authenticateToken, async (req, res) => {
  res.status(501).json({
    success: false,
    error: "Allocation recommendations not implemented",
    message: "This feature requires portfolio analysis implementation",
    timestamp: new Date().toISOString(),
  });
});

// Get similar stocks (not implemented)
router.get("/similar/:symbol", async (req, res) => {
  res.status(501).json({
    success: false,
    error: "Similar stocks not implemented",
    message: "This feature requires similarity analysis implementation",
    timestamp: new Date().toISOString(),
  });
});

// Get alternative recommendations for holdings (not implemented)
router.get("/alternatives", authenticateToken, async (req, res) => {
  res.status(501).json({
    success: false,
    error: "Alternative recommendations not implemented",
    message: "This feature requires alternative analysis implementation",
    timestamp: new Date().toISOString(),
  });
});

// Get recommendation performance tracking (not implemented)
router.get("/performance", authenticateToken, async (req, res) => {
  res.status(501).json({
    success: false,
    error: "Performance tracking not implemented",
    message: "This feature requires performance tracking implementation",
    timestamp: new Date().toISOString(),
  });
});

module.exports = router;

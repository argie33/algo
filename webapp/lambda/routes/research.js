const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Get research reports and analysis
router.get("/", async (req, res) => {
  try {
    const {
      symbol,
      category = "all", // all, earnings, market, sector, company
      source = "all",
      limit = 15,
      days = 30,
    } = req.query;

    console.log(
      `📋 Research reports requested - symbol: ${symbol || "all"}, category: ${category}`
    );

    // Build filters
    let whereClause = "WHERE 1=1";
    let params = [];
    let paramIndex = 1;

    if (symbol) {
      whereClause += ` AND symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // Analyst recommendations as research insights
    const recommendationsQuery = `
      SELECT 
        symbol,
        analyst_name,
        firm,
        rating,
        price_target,
        recommendation_date,
        'analyst_recommendation' as type,
        'Analyst Recommendation' as title,
        CONCAT(analyst_name, ' from ', firm, ' rates ', symbol, ' as ', rating, 
               CASE WHEN price_target IS NOT NULL 
                    THEN CONCAT(' with price target $', price_target) 
                    ELSE '' END) as summary
      FROM analyst_recommendations 
      ${whereClause}
      AND recommendation_date >= CURRENT_DATE - INTERVAL '${isNaN(parseInt(days)) ? 30 : parseInt(days)} days'
      ORDER BY recommendation_date DESC
      LIMIT $${paramIndex}
    `;
    params.push(parseInt(limit));

    // Try to query analyst recommendations table
    let recommendationsResult, newsResult;

    try {
      recommendationsResult = await query(recommendationsQuery, params);
      console.log(
        `✅ Found ${recommendationsResult.rows.length} analyst recommendations`
      );
    } catch (error) {
      console.log(
        "❌ Analyst recommendations table not available:",
        error.message
      );
      recommendationsResult = { rows: [] };
    }

    // Try to query news articles table
    try {
      const newsQuery = `
        SELECT 
          symbol, title, summary, source, published_at, url,
          'news' as type
        FROM news_articles 
        ${whereClause}
        AND published_at >= CURRENT_DATE - INTERVAL '${isNaN(parseInt(days)) ? 30 : parseInt(days)} days'
        ORDER BY published_at DESC
        LIMIT ${isNaN(parseInt(limit)) ? 15 : parseInt(limit)}
      `;
      newsResult = await query(newsQuery, params.slice(0, -1));
      console.log(`✅ Found ${newsResult.rows.length} news articles`);
    } catch (error) {
      console.log("❌ News articles table not available:", error.message);
      newsResult = { rows: [] };
    }

    // Combine research data
    const research = [
      ...recommendationsResult.rows.map((row) => ({
        id: `rec_${row.symbol}_${row.recommendation_date}`,
        type: row.type,
        title: row.title,
        summary: row.summary,
        symbol: row.symbol,
        source: row.firm || "Analyst",
        author: row.analyst_name,
        published_at: row.recommendation_date,
        metadata: {
          rating: row.rating,
          price_target: row.price_target,
          firm: row.firm,
        },
      })),
      ...newsResult.rows.map((row, index) => ({
        id: `news_${row.symbol}_${index}`,
        type: row.type,
        title: row.title,
        summary: row.summary,
        symbol: row.symbol,
        source: row.source,
        published_at: row.published_at,
        url: row.url,
      })),
    ];

    // Sort by publication date
    research.sort(
      (a, b) => new Date(b.published_at) - new Date(a.published_at)
    );

    res.json({
      success: true,
      data: {
        research: research.slice(0, parseInt(limit)),
        total: research.length,
        filters: {
          symbol: symbol || null,
          category,
          source,
          limit: parseInt(limit),
          days: parseInt(days),
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Research reports error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch research reports",
      details: error.message,
    });
  }
});

// Get specific research report details
router.get("/report/:id", async (req, res) => {
  try {
    const { id } = req.params;

    // Parse ID to determine type and lookup key
    const [type, symbol, date] = id.split("_");

    if (type === "rec") {
      // Look up analyst recommendation
      const result = await query(
        `
        SELECT 
          symbol,
          analyst_name,
          firm,
          rating,
          price_target,
          recommendation_date,
          notes
        FROM analyst_recommendations 
        WHERE symbol = $1 AND recommendation_date::text LIKE $2
        ORDER BY recommendation_date DESC
        LIMIT 1
      `,
        [symbol, `${date}%`]
      );

      if (result.rows.length === 0) {
        return res.status(404).json({
          success: false,
          error: "Research report not found",
          message: `Research report ${id} not found in database`,
        });
      }

      const report = result.rows[0];
      res.json({
        success: true,
        data: {
          id,
          type: "analyst_recommendation",
          symbol: report.symbol,
          title: `${report.analyst_name} - ${report.symbol} Rating`,
          author: report.analyst_name,
          firm: report.firm,
          published_at: report.recommendation_date,
          content: {
            rating: report.rating,
            price_target: report.price_target,
            notes: report.notes,
          },
        },
      });
    } else {
      return res.status(404).json({
        success: false,
        error: "Research report not found",
        message: `Research report ${id} not found`,
      });
    }
  } catch (error) {
    console.error("Research report detail error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch research report details",
      details: error.message,
    });
  }
});

// Get research reports (alias for root endpoint for consistency)
router.get("/reports", async (req, res) => {
  // Redirect to main research endpoint
  req.url = "/";
  return router.handle(req, res);
});

// Search research reports
router.get("/reports/search", async (req, res) => {
  try {
    const {
      query,
      category = "all",
      author = "all",
      period = "month",
      limit = 20,
    } = req.query;

    console.log(`🔍 Research search requested - query: ${query}`);

    // For now, return the same structure as getResearchReports but filtered
    // In a real implementation, this would search through research content
    const mockResults = {
      success: true,
      data: {
        reports: [
          {
            id: "search-1",
            title: `Search Results for "${query}"`,
            summary: "Research reports matching your search query",
            author: "Research Team",
            publishedAt: new Date().toISOString(),
            category: "Search Results",
            rating: "Neutral",
            pages: 1,
            downloads: 0,
            isFavorited: false,
            keyPoints: [`Found results related to ${query}`],
          },
        ],
        total: 1,
      },
    };

    res.json(mockResults);
  } catch (error) {
    console.error("Research search error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to search research reports",
      details: error.message,
    });
  }
});

// Get report categories
router.get("/reports/categories", async (req, res) => {
  try {
    console.log(`📋 Research categories requested`);

    const mockCategories = {
      success: true,
      data: {
        categories: [
          { id: "market", name: "Market Analysis", count: 15 },
          { id: "sector", name: "Sector Analysis", count: 8 },
          { id: "company", name: "Company Reports", count: 12 },
          { id: "economic", name: "Economic Research", count: 6 },
        ],
        popular: [
          { id: "market", name: "Market Analysis", count: 15 },
          { id: "sector", name: "Sector Analysis", count: 8 },
        ],
      },
    };

    res.json(mockCategories);
  } catch (error) {
    console.error("Research categories error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch report categories",
      details: error.message,
    });
  }
});

module.exports = router;
